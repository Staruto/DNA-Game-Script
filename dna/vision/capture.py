from __future__ import annotations

import cv2
import mss
import numpy as np


class ScreenCapture:
    def __init__(self):
        self._sct = mss.mss()

    def grab_gray(self, region: dict):
        img = np.array(self._sct.grab(region))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

    def grab_bgr(self, region: dict):
        img = np.array(self._sct.grab(region))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
