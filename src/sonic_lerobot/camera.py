"""Explicit camera provider boundary; output RGB uint8 plus local monotonic time."""
import importlib
import time
import numpy as np


def load_provider(spec):
    module, name = spec.split(":", 1)
    return getattr(importlib.import_module(module), name)()


def validate_frame(sample, max_age=0.25):
    image = np.asarray(sample["rgb"])
    age = time.monotonic() - float(sample["monotonic"])
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Camera must return HWC RGB uint8")
    if not 0 <= age <= max_age:
        raise ValueError("Camera stale or timestamp in wrong clock domain")
    return image


class OpenCVCamera:
    """Example local RGB camera. Not the Gear-SONIC composed-camera wire protocol."""
    def __init__(self, device=0):
        import cv2
        self.cv2 = cv2
        self.capture = cv2.VideoCapture(device)
        if not self.capture.isOpened():
            raise RuntimeError("Camera could not be opened")

    def read(self):
        ok, image = self.capture.read()
        if not ok:
            raise RuntimeError("Camera read failed")
        return {"rgb": self.cv2.cvtColor(image, self.cv2.COLOR_BGR2RGB), "monotonic": time.monotonic()}

    def close(self):
        self.capture.release()
