from __future__ import annotations

import copy
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
ROUTES_DIR = ROOT_DIR / "routes"

DEFAULT_CONFIG = {
    "skill_region": {"left": 1700, "top": 1000, "width": 860, "height": 440},
    "result_region": {"left": 0, "top": 800, "width": 2560, "height": 800},
    "dungeon_name_region": {"left": 0, "top": 250, "width": 900, "height": 300},
    "loot_marker_region": {"left": 420, "top": 120, "width": 1720, "height": 980},
    "defence_target_hp_region": {"left": 0, "top": 500, "width": 700, "height": 220},
    "defence_quit_region": {"left": 2040, "top": 1300, "width": 519, "height": 299},
    "defence_exit_popup_region": {"left": 0, "top": 0, "width": 2560, "height": 1440},
    "defence_confirm_region": {"left": 1080, "top": 700, "width": 780, "height": 260},
    "dungeon_mode": "auto",
    "manual_dungeon": "defence",
    "dungeon_detect_interval": 2.0,
    "dungeon_detect_threshold": 0.72,
    "dungeon_detect_scales": [0.9, 0.95, 1.0, 1.05, 1.1],
    "debug_dungeon_detection": False,
    "target_runs": 0,
    "compact_log_enabled": True,
    "enable_run_stats": True,
    "skill_check_interval": 1.2,
    "skill_state_confirm_frames": 2,
    "skill_press_retry_interval": 8.0,
    "skill_detect_mode": "zero",
    "skill_zero_threshold": 0.72,
    "debug_skill_scores": False,
    "skill_glow_threshold": 0.72,
    "skill_glow_score_margin": 0.02,
    "loot_enabled": True,
    "loot_marker_template": "wedge.png",
    "loot_check_interval": 0.35,
    "loot_template_threshold": 0.42,
    "loot_blue_ratio_threshold": 0.08,
    "loot_template_icon_crop_ratio": 0.58,
    "loot_turn_deadzone_px": 40,
    "loot_turn_gain": 0.08,
    "loot_turn_max_step_px": 45,
    "loot_forward_hold_sec": 0.4,
    "loot_forward_pause_sec": 0.04,
    "loot_lost_timeout_sec": 1.0,
    "loot_approach_timeout_sec": 9.0,
    "debug_loot": False,
    "defence_enabled": True,
    "auto_detect_defence": True,
    "manual_defence_variant": "defence_wings_inspo_volition",
    "defence_variants": {
        "defence_wings_inspo_volition": {
            "display_name": "Defence Wings Inspo Volition",
            "entry_template": "defence_wings_inspo_volition.png",
            "route_name": "defence_wings_inspo_volition",
        },
        "defence_lv65": {
            "display_name": "Defence Lv65",
            "entry_template": "defence_lv65.png",
            "route_name": "defence_lv65",
        },
    },
    "defence_entry_region": {"left": 0, "top": 0, "width": 2560, "height": 1440},
    "defence_entry_threshold": 0.1,
    "defence_entry_confirm_frames": 3,
    "defence_route_mode_override": "auto",
    "defence_route_record_hotkey_start": "p",
    "defence_route_record_hotkey_stop": "o",
    "defence_route_replay_hotkey": "i",
    "defence_route_replay_enabled": True,
    "defence_route_replay_after_load_delay_sec": 1.5,
    "defence_check_interval": 0.22,
    "defence_replay_tick_interval": 0.01,
    "defence_exit_confirm_frames": 12,
    "defence_exit_confirm_frames_locked": 180,
    "defence_route_mouse_scale": 0.71,
    "defence_target_hp_template": "defence_hp.png",
    "defence_target_hp_threshold": 0.78,
    "defence_post_replay_validate_delay_sec": 0.8,
    "defence_post_replay_validate_timeout_sec": 4.0,
    "defence_quit_template": "quit_challenge.png",
    "defence_quit_threshold": 0.92,
    "defence_quit_open_menu_delay_sec": 0.5,
    "defence_quit_retry_interval_sec": 1.0,
    "defence_exit_popup_template": "exit_pop_up.png",
    "defence_exit_popup_threshold": 0.93,
    "defence_confirm_template": "confirm.png",
    "defence_confirm_threshold": 0.9,
    "defence_confirm_retry_interval_sec": 0.8,
    "defence_restart_notice_repeat": 3,
    "debug_defence": True,
    "result_check_interval": 0.3,
    "click_reset_x": 2,
    "click_reset_y": 2,
    "click_reset_delay": 0.12,
    "click_target_settle_delay": 0.08,
    "start_search_window_after_r": 12.0,
    "start_redetect_after_cursor_reset": True,
    "start_redetect_delay": 0.08,
    "game_window_keywords": ["Duet Night Abyss", "Abyss"],
    "only_when_foreground": True,
    "block_keyboard_when_taskbar_visible": True,
}


def get_default_config() -> dict:
    return copy.deepcopy(DEFAULT_CONFIG)


def workspace_path(*parts: str) -> Path:
    return ROOT_DIR.joinpath(*parts)


def asset_path(file_name: str) -> Path:
    return ASSETS_DIR / file_name


def template_path(file_name: str) -> Optional[Path]:
    asset_candidate = asset_path(file_name)
    if asset_candidate.exists():
        return asset_candidate

    root_candidate = workspace_path(file_name)
    if root_candidate.exists():
        return root_candidate

    return None


def defence_route_path(route_name: str) -> Path:
    route_name = (route_name or "defence_default").strip() or "defence_default"
    safe_name = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in route_name)
    ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    return ROUTES_DIR / f"{safe_name}.json"
