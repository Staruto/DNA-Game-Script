from __future__ import annotations

from typing import Optional

from dna.vision.capture import ScreenCapture
from dna.vision.templates import (
    DEFAULT_SKILL_SCALES,
    build_skill_variants,
    max_template_score,
    max_template_score_multiscale,
)


class SkillService:
    def __init__(self, config: dict, capture: ScreenCapture, templates):
        self.config = config
        self.capture = capture
        self.templates = templates

    def is_skill_zero_detected(self) -> bool:
        gray = self.capture.grab_gray(self.config["skill_region"])
        template = self.templates.load_gray("skill_zero_template.png")
        if template is None:
            return False

        if template.shape[0] > gray.shape[0] or template.shape[1] > gray.shape[1]:
            print("[WARN] skill_zero_template.png is larger than skill_region; skip this frame.")
            return False

        screen_variants = build_skill_variants(gray)
        template_variants = build_skill_variants(template)

        best_score = -1.0
        best_pair = ""
        for s_name, s_img in screen_variants:
            for t_name, t_img in template_variants:
                score = max_template_score_multiscale(s_img, t_img, DEFAULT_SKILL_SCALES)
                if score is None:
                    continue
                if score > best_score:
                    best_score = score
                    best_pair = f"{s_name}/{t_name}"

        threshold = float(self.config.get("skill_zero_threshold", 0.72))
        if bool(self.config.get("debug_skill_scores", False)):
            print(f"[DEBUG] skill_zero best_score={best_score:.3f} pair={best_pair} threshold={threshold:.3f}")
        return best_score >= threshold

    def detect_skill_active_state(self) -> Optional[bool]:
        mode = str(self.config.get("skill_detect_mode", "auto")).lower()
        if mode == "zero":
            return self.is_skill_zero_detected()

        gray = self.capture.grab_gray(self.config["skill_region"])
        glow_on = self.templates.resolve_path("skill_glow_on_template.png")
        glow_off = self.templates.resolve_path("skill_glow_off_template.png")

        def detect_by_glow() -> Optional[bool]:
            on_score = max_template_score(gray, str(glow_on), center_crop_size=85) if glow_on else None
            off_score = max_template_score(gray, str(glow_off), center_crop_size=85) if glow_off else None
            threshold = float(self.config.get("skill_glow_threshold", 0.72))
            margin = float(self.config.get("skill_glow_score_margin", 0.02))

            if on_score is None and off_score is None:
                return None
            if on_score is not None and off_score is not None:
                if on_score >= threshold and on_score >= (off_score + margin):
                    return True
                if off_score >= threshold and off_score >= (on_score + margin):
                    return False
                if on_score >= threshold and off_score < threshold:
                    return True
                if off_score >= threshold and on_score < threshold:
                    return False
                return None
            if on_score is not None:
                return bool(on_score >= threshold)
            if off_score is not None:
                return not bool(off_score >= threshold)
            return None

        by_glow = detect_by_glow()
        if mode == "glow":
            return by_glow
        if by_glow is not None:
            return by_glow
        return self.is_skill_zero_detected()
