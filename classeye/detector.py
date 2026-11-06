"""YOLOv8 object and pose detection with ONNX Runtime (no PyTorch needed in the app)."""
from dataclasses import dataclass

import cv2
import numpy as np

PERSON, PHONE, BOOK = 0, 67, 73


@dataclass
class Det:
    box: np.ndarray          # x1, y1, x2, y2
    score: float
    cls: int
    kpts: np.ndarray = None  # (17, 3): x, y, confidence - pose model only


class YoloModel:
    def __init__(self, path, conf=0.3, iou=0.45):
        import onnxruntime as ort
        prefer = ["CUDAExecutionProvider", "DmlExecutionProvider", "CoreMLExecutionProvider",
                  "CPUExecutionProvider"]
        avail = ort.get_available_providers()
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(path, opts, providers=[p for p in prefer if p in avail])
        inp = self.sess.get_inputs()[0]
        self.name = inp.name
        self.size = inp.shape[2] if isinstance(inp.shape[2], int) else 640
        self.conf, self.iou = conf, iou

    def __call__(self, image, classes=None, conf=None):
        blob, scale, pad = letterbox(image, self.size)
        raw = self.sess.run(None, {self.name: blob})[0]
        return decode(raw, scale, pad, image.shape[:2], conf or self.conf, self.iou, classes)


def letterbox(image, size):
    h, w = image.shape[:2]
    scale = min(size / h, size / w)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    canvas = np.full((size, size, 3), 114, np.uint8)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas[py:py + nh, px:px + nw] = cv2.resize(image, (nw, nh))
    blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    return np.ascontiguousarray(blob), scale, (px, py)


def decode(raw, scale, pad, shape_hw, conf, iou, classes=None):
    """YOLOv8 head output (1, C, N): C = 84 for COCO detection, 56 for pose."""
    p = raw[0]
    if p.shape[0] > p.shape[1]:
        p = p.T
    p = p.T
    pose = p.shape[1] == 56
    if pose:
        scores, cls, kpts = p[:, 4], np.zeros(len(p), int), p[:, 5:].reshape(-1, 17, 3)
    else:
        cls = p[:, 4:].argmax(1)
        scores = p[np.arange(len(p)), 4 + cls]
        kpts = None
    keep = scores >= conf
    if classes is not None:
        keep &= np.isin(cls, list(classes))
    if not keep.any():
        return []
    b, scores, cls = p[keep, :4], scores[keep], cls[keep]
    kpts = kpts[keep] if kpts is not None else None
    px, py = pad
    H, W = shape_hw
    xyxy = np.stack([(b[:, 0] - b[:, 2] / 2 - px) / scale, (b[:, 1] - b[:, 3] / 2 - py) / scale,
                     (b[:, 0] + b[:, 2] / 2 - px) / scale, (b[:, 1] + b[:, 3] / 2 - py) / scale], 1)
    xyxy[:, [0, 2]] = xyxy[:, [0, 2]].clip(0, W)
    xyxy[:, [1, 3]] = xyxy[:, [1, 3]].clip(0, H)
    shift = cls[:, None].astype(np.float32) * 4096.0
    rects = np.concatenate([xyxy[:, :2] + shift, xyxy[:, 2:] - xyxy[:, :2]], 1)
    idx = cv2.dnn.NMSBoxes(rects.tolist(), scores.astype(float).tolist(), conf, iou)
    out = []
    for i in np.array(idx).ravel() if len(idx) else []:
        k = None
        if kpts is not None:
            k = kpts[i].copy()
            k[:, 0] = (k[:, 0] - px) / scale
            k[:, 1] = (k[:, 1] - py) / scale
        out.append(Det(xyxy[i], float(scores[i]), int(cls[i]), k))
    return out
