from __future__ import annotations

import time

import cv2
import numpy as np

from dna.profiles import DungeonProfile
from dna.vision.capture import ScreenCapture


class ResultUIService:
    def __init__(self, config: dict, capture: ScreenCapture, templates, controller):
        self.config = config
        self.capture = capture
        self.templates = templates
        self.controller = controller
        self.awaiting_start_until = 0.0

    def check_and_click_result_ui(self, profile: DungeonProfile, session: object = None):
        gray = self.capture.grab_gray(self.config["result_region"])

        if profile.use_challenge_again:
            template_ca = self.templates.load_gray(profile.challenge_template)
            if template_ca is not None:
                res_ca = cv2.matchTemplate(gray, template_ca, cv2.TM_CCOEFF_NORMED)
                if len(np.where(res_ca >= 0.8)[0]) > 0:
                    print(f"[INFO] Match ended ({profile.display_name}). Pressing 'R' for Challenge Again.")
                    self.controller.press_key("r", delay=0.15)
                    self.awaiting_start_until = time.time() + float(self.config.get("start_search_window_after_r", 12.0))
                    time.sleep(2)
                    return "challenge_again"

        if not profile.use_start_click:
            return None

        template_start = self.templates.load_gray(profile.start_template)
        if template_start is None:
            return None

        w, h = template_start.shape[::-1]
        threshold = 0.82
        res_start = cv2.matchTemplate(gray, template_start, cv2.TM_CCOEFF_NORMED)
        loc_start = np.where(res_start >= threshold)

        should_retry_after_reset = (
            len(loc_start[0]) == 0
            and self.config.get("start_redetect_after_cursor_reset", True)
            and (time.time() <= self.awaiting_start_until)
        )
        if should_retry_after_reset:
            self.controller.move_cursor_absolute(
                int(self.config.get("click_reset_x", 2)),
                int(self.config.get("click_reset_y", 2)),
            )
            time.sleep(float(self.config.get("start_redetect_delay", 0.08)))
            gray = self.capture.grab_gray(self.config["result_region"])
            res_start = cv2.matchTemplate(gray, template_start, cv2.TM_CCOEFF_NORMED)
            loc_start = np.where(res_start >= threshold)

        for pt in zip(*loc_start[::-1]):
            click_x = pt[0] + int(w / 2) + self.config["result_region"]["left"]
            click_y = pt[1] + int(h / 2) + self.config["result_region"]["top"]

            # Handle bonus selection
            bonus_tier = self.config.get("bonus_tier", "none")
            if session and hasattr(session, "bonus_remaining") and session.bonus_remaining > 0 and bonus_tier != "none":
                coords = self.config.get("bonus_coordinates", {}).get(bonus_tier)
                if coords:
                    bx = click_x + coords["x_offset"]
                    by = click_y + coords["y_offset"]
                    print(f"[INFO] Selecting bonus: {bonus_tier}, remaining: {session.bonus_remaining - 1}")
                    self.controller.move_and_click(bx, by, delay=0.15)
                    session.bonus_remaining -= 1
                    time.sleep(0.2)

            print(f"[INFO] Start button detected ({profile.display_name}). Clicking at ({click_x}, {click_y}).")
            self.controller.move_and_click(click_x, click_y, delay=0.15)
            self.awaiting_start_until = 0.0
            time.sleep(5)
            return "start_clicked"

        return None
