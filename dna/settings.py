from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping

from dna.config import ROOT_DIR

SETTINGS_FILE = ROOT_DIR / "settings.json"
ALLOWED_DUNGEON_MODES = {"auto", "manual"}
ALLOWED_MANUAL_DUNGEONS = {"defence", "expulsion"}
ALLOWED_DEFENCE_ROUTE_MODES = {"auto", "record", "playback"}


def _normalize_mode(value: Any, fallback: str) -> str:
    mode = str(value).strip().lower()
    if mode in ALLOWED_DUNGEON_MODES:
        return mode
    return fallback


def _normalize_manual_dungeon(value: Any, fallback: str) -> str:
    dungeon = str(value).strip().lower()
    if dungeon in ALLOWED_MANUAL_DUNGEONS:
        return dungeon
    return fallback


def _normalize_target_runs(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    if parsed < 0:
        return 0
    return parsed


def _normalize_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return fallback


def _normalize_route_mode(value: Any, fallback: str) -> str:
    mode = str(value).strip().lower()
    if mode in ALLOWED_DEFENCE_ROUTE_MODES:
        return mode
    return fallback


def normalize_runtime_settings(raw: Mapping[str, Any], base: Mapping[str, Any]) -> Dict[str, Any]:
    fallback_mode = _normalize_mode(base.get("dungeon_mode", "auto"), "auto")
    fallback_manual = _normalize_manual_dungeon(base.get("manual_dungeon", "defence"), "defence")
    fallback_runs = _normalize_target_runs(base.get("target_runs", 0), 0)
    fallback_compact_log = _normalize_bool(base.get("compact_log_enabled", True), True)
    fallback_defence_preview = _normalize_bool(base.get("defence_preview_enabled", True), True)
    fallback_auto_detect_defence = _normalize_bool(base.get("auto_detect_defence", True), True)
    fallback_manual_variant = str(base.get("manual_defence_variant", "")).strip()
    fallback_route_mode = _normalize_route_mode(base.get("defence_route_mode_override", "auto"), "auto")

    mode = _normalize_mode(raw.get("dungeon_mode", fallback_mode), fallback_mode)
    manual = _normalize_manual_dungeon(raw.get("manual_dungeon", fallback_manual), fallback_manual)
    target_runs = _normalize_target_runs(raw.get("target_runs", fallback_runs), fallback_runs)
    compact_log_enabled = _normalize_bool(raw.get("compact_log_enabled", fallback_compact_log), fallback_compact_log)
    defence_preview_enabled = _normalize_bool(raw.get("defence_preview_enabled", fallback_defence_preview), fallback_defence_preview)
    auto_detect_defence = _normalize_bool(raw.get("auto_detect_defence", fallback_auto_detect_defence), fallback_auto_detect_defence)
    manual_defence_variant = str(raw.get("manual_defence_variant", fallback_manual_variant)).strip()
    defence_route_mode_override = _normalize_route_mode(
        raw.get("defence_route_mode_override", fallback_route_mode),
        fallback_route_mode,
    )

    return {
        "dungeon_mode": mode,
        "manual_dungeon": manual,
        "target_runs": target_runs,
        "compact_log_enabled": compact_log_enabled,
        "defence_preview_enabled": defence_preview_enabled,
        "auto_detect_defence": auto_detect_defence,
        "manual_defence_variant": manual_defence_variant,
        "defence_route_mode_override": defence_route_mode_override,
    }


def load_settings_overrides(base: Mapping[str, Any]) -> Dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return normalize_runtime_settings({}, base)

    try:
        payload = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] Failed to read settings file '{SETTINGS_FILE.name}': {exc}")
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    return normalize_runtime_settings(payload, base)


def save_settings_overrides(values: Mapping[str, Any], base: Mapping[str, Any]) -> Path:
    normalized = normalize_runtime_settings(values, base)
    SETTINGS_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return SETTINGS_FILE
