from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Sequence

import cv2

from dna.config import template_path

DEFAULT_SKILL_SCALES = [0.85, 0.92, 1.0, 1.08, 1.15]
DEFAULT_DEFENCE_SCALES = [0.85, 0.92, 1.0, 1.08, 1.15]
DEFAULT_HP_SCALES = [0.88, 0.95, 1.0, 1.05, 1.12]


class TemplateStore:
    def __init__(self):
        self._gray_cache: dict[str, object] = {}

    def load_gray(self, file_name: str):
        if file_name in self._gray_cache:
            return self._gray_cache[file_name]

        path = template_path(file_name)
        if not path:
            return None

        template = cv2.imread(str(path), 0)
        if template is None:
            return None

        self._gray_cache[file_name] = template
        return template

    def resolve_path(self, file_name: str) -> Optional[Path]:
        return template_path(file_name)


def max_template_score(gray_img, template_path_str: str, center_crop_size: Optional[int] = None) -> Optional[float]:
    if not os.path.exists(template_path_str):
        return None
    template = cv2.imread(template_path_str, 0)
    if template is None:
        return None

    if center_crop_size:
        h, w = template.shape[:2]
        size = center_crop_size
        r, c = min(h, size), min(w, size)
        y, x = (h - r) // 2, (w - c) // 2
        template = template[y:y + r, x:x + c]

    if template.shape[0] > gray_img.shape[0] or template.shape[1] > gray_img.shape[1]:
        print(f"[WARN] Template {os.path.basename(template_path_str)} is larger than the search region. Skipping.")
        return None

    result = cv2.matchTemplate(gray_img, template, cv2.TM_CCOEFF_NORMED)
    _, max_score, _, _ = cv2.minMaxLoc(result)
    return float(max_score)


def max_template_score_multiscale(gray_img, template_img, scales: Sequence[float]) -> Optional[float]:
    if gray_img is None or template_img is None:
        return None
    if gray_img.size == 0 or template_img.size == 0:
        return None

    best_score = None
    base_h, base_w = template_img.shape[:2]

    for scale in scales:
        scaled_w = max(1, int(base_w * scale))
        scaled_h = max(1, int(base_h * scale))
        if scaled_w > gray_img.shape[1] or scaled_h > gray_img.shape[0]:
            continue

        if scaled_w == base_w and scaled_h == base_h:
            scaled_template = template_img
        else:
            scaled_template = cv2.resize(template_img, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)

        result = cv2.matchTemplate(gray_img, scaled_template, cv2.TM_CCOEFF_NORMED)
        _, max_score, _, _ = cv2.minMaxLoc(result)
        max_score = float(max_score)
        if best_score is None or max_score > best_score:
            best_score = max_score

    return best_score


def locate_best_template_multiscale(gray_img, template_img, scales: Sequence[float]):
    if gray_img is None or template_img is None:
        return None
    if gray_img.size == 0 or template_img.size == 0:
        return None

    best_loc = None
    best_shape = None
    best_score = None
    base_h, base_w = template_img.shape[:2]

    for scale in scales:
        scaled_w = max(1, int(base_w * scale))
        scaled_h = max(1, int(base_h * scale))
        if scaled_w > gray_img.shape[1] or scaled_h > gray_img.shape[0]:
            continue
        if scaled_w == base_w and scaled_h == base_h:
            scaled_template = template_img
        else:
            scaled_template = cv2.resize(template_img, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)

        result = cv2.matchTemplate(gray_img, scaled_template, cv2.TM_CCOEFF_NORMED)
        _, max_score, _, max_loc = cv2.minMaxLoc(result)
        max_score = float(max_score)
        if best_score is None or max_score > best_score:
            best_score = max_score
            best_loc = max_loc
            best_shape = (scaled_w, scaled_h)

    if best_score is None or best_loc is None or best_shape is None:
        return None

    return {
        "score": float(best_score),
        "loc": best_loc,
        "shape": best_shape,
    }


def build_skill_variants(gray_img):
    variants = [("gray", gray_img)]

    eq = cv2.equalizeHist(gray_img)
    variants.append(("eq", eq))

    _, bin_180 = cv2.threshold(gray_img, 180, 255, cv2.THRESH_BINARY)
    _, bin_200 = cv2.threshold(gray_img, 200, 255, cv2.THRESH_BINARY)
    variants.append(("bin180", bin_180))
    variants.append(("bin200", bin_200))

    edge = cv2.Canny(gray_img, 60, 150)
    variants.append(("edge", edge))
    return variants
