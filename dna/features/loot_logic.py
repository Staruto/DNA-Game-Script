from __future__ import annotations

import time

import cv2
import numpy as np

from dna.runtime.state import LootState
from dna.vision.capture import ScreenCapture


class LootService:
    def __init__(self, config: dict, capture: ScreenCapture, templates, controller):
        self.config = config
        self.capture = capture
        self.templates = templates
        self.controller = controller
        self._loot_template_icon_edge = None

    def _get_loot_template_icon_edge(self):
        if self._loot_template_icon_edge is not None:
            return self._loot_template_icon_edge

        tmpl = self.templates.load_gray(str(self.config.get("loot_marker_template", "wedge.png")))
        if tmpl is None:
            return None

        crop_ratio = float(self.config.get("loot_template_icon_crop_ratio", 0.58))
        crop_ratio = max(0.2, min(crop_ratio, 1.0))
        crop_h = max(1, int(tmpl.shape[0] * crop_ratio))
        icon = tmpl[:crop_h, :]
        self._loot_template_icon_edge = cv2.Canny(icon, 70, 150)
        return self._loot_template_icon_edge

    def detect_loot_marker(self):
        if not self.config.get("loot_enabled", True):
            return None

        region = self.config.get("loot_marker_region")
        frame = self.capture.grab_bgr(region)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edge = cv2.Canny(gray, 70, 150)

        template_edge = self._get_loot_template_icon_edge()
        if template_edge is None:
            return None

        th, tw = template_edge.shape[:2]
        if th > edge.shape[0] or tw > edge.shape[1]:
            return None

        result = cv2.matchTemplate(edge, template_edge, cv2.TM_CCOEFF_NORMED)
        _, max_score, _, max_loc = cv2.minMaxLoc(result)

        x0, y0 = max_loc
        x1 = min(x0 + tw, frame.shape[1])
        y1 = min(y0 + th, frame.shape[0])
        if x1 <= x0 or y1 <= y0:
            return None

        roi = frame[y0:y1, x0:x1]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lower_blue = np.array([85, 80, 80], dtype=np.uint8)
        upper_blue = np.array([130, 255, 255], dtype=np.uint8)
        blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
        blue_ratio = float(cv2.countNonZero(blue_mask)) / float(blue_mask.size)

        score_threshold = float(self.config.get("loot_template_threshold", 0.42))
        blue_ratio_threshold = float(self.config.get("loot_blue_ratio_threshold", 0.08))
        if bool(self.config.get("debug_loot", False)):
            print(f"[DEBUG] loot marker score={max_score:.3f}, blue_ratio={blue_ratio:.3f}")

        if max_score < score_threshold or blue_ratio < blue_ratio_threshold:
            return None

        marker_center_x = region["left"] + x0 + (x1 - x0) // 2
        marker_center_y = region["top"] + y0 + (y1 - y0) // 2
        return {
            "x": marker_center_x,
            "y": marker_center_y,
            "score": float(max_score),
            "blue_ratio": blue_ratio,
        }

    def _turn_camera_towards_x(self, target_x: int):
        region = self.config.get("loot_marker_region")
        center_x = region["left"] + region["width"] // 2
        error_x = int(target_x - center_x)

        deadzone = int(self.config.get("loot_turn_deadzone_px", 40))
        if abs(error_x) <= deadzone:
            return
        gain = float(self.config.get("loot_turn_gain", 0.08))
        max_step = int(self.config.get("loot_turn_max_step_px", 45))
        step = int(error_x * gain)
        if step == 0:
            step = 1 if error_x > 0 else -1
        step = max(-max_step, min(max_step, step))
        self.controller.move_mouse_relative(dx=step, dy=0)

    def _forward_pulse(self):
        hold_sec = float(self.config.get("loot_forward_hold_sec", 0.22))
        pause_sec = float(self.config.get("loot_forward_pause_sec", 0.04))
        if hold_sec <= 0:
            return
        if self.controller.key_down("w"):
            time.sleep(hold_sec)
            self.controller.key_up("w")
        if pause_sec > 0:
            time.sleep(pause_sec)

    def update_loot_approach_state(self, now: float, state: LootState) -> bool:
        if not self.config.get("loot_enabled", True):
            return False

        marker = self.detect_loot_marker()
        if marker is not None:
            state.last_seen_ts = now
            state.last_marker_x = marker["x"]
            if not state.active:
                state.active = True
                state.start_ts = now
                print("[INFO] Loot marker detected. Approaching to trigger pickup.")

        if not state.active:
            return False

        if (now - state.start_ts) >= float(self.config.get("loot_approach_timeout_sec", 9.0)):
            state.active = False
            print("[INFO] Loot approach timeout reached. Back to combat logic.")
            return False

        if (now - state.last_seen_ts) >= float(self.config.get("loot_lost_timeout_sec", 1.0)):
            state.active = False
            print("[INFO] Loot marker lost. Assume pickup completed.")
            return False

        if state.last_marker_x is not None:
            self._turn_camera_towards_x(state.last_marker_x)
        self._forward_pulse()
        return True
