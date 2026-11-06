"""Face detection (YuNet) and 128-d face embeddings (SFace) - OpenCV ONNX models, CPU real time."""
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class DetectedFace:
    box: tuple                     # x, y, w, h
    score: float
    landmarks: np.ndarray          # raw YuNet row (15 floats) used for alignment
    vector: np.ndarray = field(default=None, repr=False)   # unit-length embedding or None

    @property
    def centre(self):
        x, y, w, h = self.box
        return x + w / 2, y + h / 2


def normalise(v):
    v = np.asarray(v, np.float32).ravel()
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


class FaceEngine:
    def __init__(self, detector_path, recognizer_path, min_score=0.6, min_size=26, upscale=1.0):
        self.det = cv2.FaceDetectorYN.create(detector_path, "", (320, 320), min_score, 0.3, 5000)
        self.rec = cv2.FaceRecognizerSF.create(recognizer_path, "")
        self.min_size = min_size
        self.upscale = max(0.5, float(upscale))

    def _detect_rows(self, image):
        img = image
        if abs(self.upscale - 1) > 1e-3:
            img = cv2.resize(image, None, fx=self.upscale, fy=self.upscale)
        h, w = img.shape[:2]
        self.det.setInputSize((w, h))
        _, rows = self.det.detect(img)
        if rows is None:
            return np.zeros((0, 15), np.float32)
        rows = rows.copy()
        if abs(self.upscale - 1) > 1e-3:
            rows[:, :14] /= self.upscale
        return rows

    def embed(self, image, row):
        return normalise(self.rec.feature(self.rec.alignCrop(image, row)))

    def detect(self, image, with_vectors=True):
        faces = []
        for row in self._detect_rows(image):
            x, y, w, h = (int(round(v)) for v in row[:4])
            f = DetectedFace((x, y, w, h), float(row[14]), row)
            if with_vectors and min(w, h) >= self.min_size:
                try:
                    f.vector = self.embed(image, row)
                except cv2.error:
                    pass
            faces.append(f)
        return faces

    def main_face(self, image):
        """Largest face row in a photo (for enrolment), or None."""
        rows = self._detect_rows(image)
        if len(rows) == 0:
            return None
        return rows[int(np.argmax(rows[:, 2] * rows[:, 3]))]


def mirror_row(row, width):
    """YuNet row of the horizontally flipped image (left/right landmarks swapped)."""
    r = row.copy()
    r[0] = width - (row[0] + row[2])
    pts = row[4:14].reshape(5, 2).copy()
    pts[:, 0] = width - pts[:, 0]
    r[4:14] = pts[[1, 0, 2, 4, 3]].ravel()
    return r
