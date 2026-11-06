"""Camera discovery and live streaming.

Finds:
  * every camera Windows lists in Device Manager (USB webcams, built-in cameras,
    DroidCam/Iriun virtual cameras, capture cards)
  * Wi-Fi / network cameras on the same network: phones running IP Webcam,
    RTSP/ONVIF CCTV cameras (port 554/8554) and MJPEG cameras
"""
import concurrent.futures as cf
import ipaddress
import os
import socket
import threading
import time
import urllib.request
from dataclasses import dataclass

import cv2

WINDOWS = os.name == "nt"

RTSP_PATHS = ["", "live", "stream1", "h264", "11", "live/ch00_0", "onvif1",
              "cam/realmonitor?channel=1&subtype=0", "Streaming/Channels/101", "videoMain"]
HTTP_PATHS = ["video", "videofeed", "mjpg/video.mjpg", "video.mjpg", "stream"]


@dataclass
class CameraInfo:
    name: str
    source: object          # int index or URL string
    kind: str               # "Local" or "Network"
    detail: str = ""

    @property
    def label(self):
        extra = f"  ({self.detail})" if self.detail else ""
        return f"[{self.kind}] {self.name}{extra}"


# ----------------------------------------------------------------------------
# local cameras
def _directshow_names():
    if not WINDOWS:
        return []
    try:
        from pygrabber.dshow_graph import FilterGraph
        return FilterGraph().get_input_devices()
    except Exception:
        return []


def find_local_cameras(max_index: int = 10):
    names = _directshow_names()
    api = cv2.CAP_DSHOW if WINDOWS else cv2.CAP_ANY
    found = []
    limit = max(max_index, len(names))
    for i in range(limit):
        cap = cv2.VideoCapture(i, api)
        try:
            if not cap.isOpened():
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            h, w = frame.shape[:2]
            name = names[i] if i < len(names) else f"Camera {i}"
            found.append(CameraInfo(name, i, "Local", f"{w}x{h}"))
        finally:
            cap.release()
    return found


# ----------------------------------------------------------------------------
# network cameras
def local_subnets():
    """IPv4 /24 networks this computer is connected to (Wi-Fi, Ethernet, hotspot)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
    try:  # the address used for outgoing traffic (works even without DNS)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    nets = []
    for ip in ips:
        if ip.startswith("127.") or ip.startswith("169.254."):
            continue
        net = ipaddress.ip_network(f"{ip}/24", strict=False)
        if net not in nets:
            nets.append(net)
    return nets


def _port_open(ip, port, timeout=0.35):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_stream(ip, port):
    for path in HTTP_PATHS:
        url = f"http://{ip}:{port}/{path}"
        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:
                ctype = r.headers.get("Content-Type", "")
                if "multipart" in ctype or "image" in ctype or "video" in ctype:
                    return url
        except Exception:
            continue
    return None


def _rtsp_stream(ip, port, quick=True):
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|timeout;3000000")
    for path in (RTSP_PATHS[:4] if quick else RTSP_PATHS):
        url = f"rtsp://{ip}:{port}/{path}"
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        ok = cap.isOpened() and cap.read()[0]
        cap.release()
        if ok:
            return url
    return None


def scan_network(progress=None, stop=None):
    """Scan the local network for cameras. Takes ~5-20 s for a /24 network."""
    hosts = []
    for net in local_subnets():
        hosts += [str(h) for h in net.hosts()]
    ports = (8080, 554, 8554, 81, 4747)
    found = []
    candidates = []
    total = len(hosts)
    done = 0
    with cf.ThreadPoolExecutor(max_workers=128) as pool:
        futs = {pool.submit(lambda ip: [p for p in ports if _port_open(ip, p)], ip): ip for ip in hosts}
        for fut in cf.as_completed(futs):
            done += 1
            if progress and done % 16 == 0:
                progress(done, total)
            if stop is not None and stop():
                break
            open_ports = fut.result()
            if open_ports:
                candidates.append((futs[fut], open_ports))
    for ip, open_ports in candidates:
        for port in open_ports:
            if port in (554, 8554):
                url = _rtsp_stream(ip, port)
                if url:
                    found.append(CameraInfo(f"RTSP camera {ip}", url, "Network", "CCTV / IP camera"))
                else:
                    found.append(CameraInfo(f"RTSP camera {ip}", f"rtsp://{ip}:{port}/", "Network",
                                            "needs path or password"))
            elif port == 4747:
                found.append(CameraInfo(f"DroidCam {ip}", f"http://{ip}:4747/video", "Network", "phone"))
            else:
                url = _http_stream(ip, port)
                if url:
                    found.append(CameraInfo(f"Phone / IP camera {ip}", url, "Network", "MJPEG"))
    if progress:
        progress(total, total)
    return found


def parse_source(text: str):
    """Typed address -> something cv2.VideoCapture can open."""
    t = (text or "").strip()
    if t.isdigit():
        return int(t)
    low = t.lower()
    if low.startswith(("rtsp://", "http://", "https://")) or os.path.isfile(t):
        return t
    if t:   # "192.168.1.5" or "192.168.1.5:8080" -> IP Webcam app
        host = t if ":" in t else f"{t}:8080"
        return f"http://{host}/video"
    return None


# ----------------------------------------------------------------------------
class LiveStream:
    """Background reader that always keeps the newest frame and reconnects on drop."""

    def __init__(self, source, width=1920, height=1080):
        self.source = source
        self.size = (width, height)
        self._cap = None
        self._frame = None
        self._seq = 0
        self._lock = threading.Lock()
        self._alive = False
        self._thread = None
        self.error = ""
        self.connected = False

    def _open(self):
        if isinstance(self.source, int):
            cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW if WINDOWS else cv2.CAP_ANY)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.size[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.size[1])
        else:
            if str(self.source).lower().startswith("rtsp"):
                os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
            cap = cv2.VideoCapture(self.source)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def start(self, wait_s=10.0):
        self._alive = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        end = time.time() + wait_s
        while time.time() < end and self._frame is None:
            time.sleep(0.05)
        return self._frame is not None

    def _run(self):
        misses = 0
        while self._alive:
            if self._cap is None or not self._cap.isOpened():
                self._cap = self._open()
                if not self._cap.isOpened():
                    self.connected = False
                    self.error = f"Could not open camera: {self.source}"
                    time.sleep(1.0)
                    continue
            ok, frame = self._cap.read()
            if not ok or frame is None:
                misses += 1
                if misses > 25:
                    self.connected = False
                    self._cap.release()
                    self._cap = None
                    misses = 0
                    time.sleep(0.5)
                continue
            misses = 0
            self.connected, self.error = True, ""
            with self._lock:
                self._frame = frame
                self._seq += 1
        if self._cap is not None:
            self._cap.release()

    def latest(self):
        with self._lock:
            return (self._seq, None) if self._frame is None else (self._seq, self._frame.copy())

    def stop(self):
        self._alive = False
        if self._thread:
            self._thread.join(timeout=2)
