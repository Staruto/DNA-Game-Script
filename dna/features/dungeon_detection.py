from __future__ import annotations

import cv2
import time
from typing import Optional

from dna.profiles import DUNGEON_PROFILES, DungeonProfile
from dna.vision.capture import ScreenCapture
from dna.vision.templates import max_template_score_multiscale


class DungeonDetector:
    def __init__(self, config: dict, templates):
        self.config = config
        self.templates = templates
        self.last_dungeon_detect_ts = 0.0
        self.cached_profile_key = config.get("manual_dungeon", "expulsion")

    def detect_auto(self, capture: ScreenCapture) -> Optional[str]:
        gray = capture.grab_gray(self.config["dungeon_name_region"])
        threshold = float(self.config.get("dungeon_detect_threshold", 0.78))
        scales = self.config.get("dungeon_detect_scales", [1.0])
        if not isinstance(scales, (list, tuple)) or not scales:
            scales = [1.0]
        scales = [float(item) for item in scales]
        debug_enabled = bool(self.config.get("debug_dungeon_detection", False))

        best_key = None
        best_score = -1.0
        for key, profile in DUNGEON_PROFILES.items():
            if key not in ("defence", "expulsion"):
                continue
            if not profile.name_template:
                continue
            template = self.templates.load_gray(profile.name_template)
            if template is None:
                continue
            max_score = max_template_score_multiscale(gray, template, scales)
            if max_score is None:
                continue
            if debug_enabled:
                print(f"[DEBUG] dungeon detect {key} score={float(max_score):.3f} threshold={threshold:.3f}")
            if max_score > best_score:
                best_score = max_score
                best_key = key

        if debug_enabled:
            print(f"[DEBUG] dungeon detect best={best_key} score={best_score:.3f} threshold={threshold:.3f}")

        if best_key and best_score >= threshold:
            return best_key
        return None

    def get_active_profile_key(self, capture: ScreenCapture, force: bool = False) -> str:
        manual_key = self.config.get("manual_dungeon", "expulsion")
        if manual_key not in DUNGEON_PROFILES:
            manual_key = "expulsion"

        mode = self.config.get("dungeon_mode", "manual").lower()
        if mode != "auto":
            self.cached_profile_key = manual_key
            return self.cached_profile_key

        now = time.time()
        detect_interval = float(self.config.get("dungeon_detect_interval", 2.0))
        if not force and (now - self.last_dungeon_detect_ts) < detect_interval:
            return self.cached_profile_key

        detected = self.detect_auto(capture)
        self.last_dungeon_detect_ts = now
        if detected:
            if detected != self.cached_profile_key:
                print(f"[INFO] Dungeon auto-detected: {DUNGEON_PROFILES[detected].display_name}")
            self.cached_profile_key = detected
        else:
            if self.cached_profile_key != manual_key:
                print(f"[INFO] Auto-detect fallback to manual dungeon: {DUNGEON_PROFILES[manual_key].display_name}")
            self.cached_profile_key = manual_key

        return self.cached_profile_key

    def get_active_profile(self, capture: ScreenCapture) -> DungeonProfile:
        return DUNGEON_PROFILES[self.get_active_profile_key(capture)]
