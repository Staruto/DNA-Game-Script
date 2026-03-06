from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class LootState:
    active: bool = False
    start_ts: float = 0.0
    last_seen_ts: float = 0.0
    last_marker_x: Optional[int] = None


@dataclass
class DefenceState:
    started: bool = False
    ready_for_skill: bool = False
    w_holding: bool = False
    last_update_ts: float = 0.0
    replay_active: bool = False
    replay_start_ts: float = 0.0
    replay_index: int = 0
    replay_events: Optional[List[dict]] = None
    replay_route_name: Optional[str] = None
    replay_held_keys: Set[str] = field(default_factory=set)
    replay_pending_until: float = 0.0
    auto_replay_armed: bool = False
    entry_detected_logged: bool = False
    waiting_for_entry_logged: bool = False
    entry_match_streak: int = 0
    route_mode: str = "playback"
    missing_route_warned: bool = False


@dataclass
class RouteRecordingState:
    active: bool = False
    start_ts: float = 0.0
    events: List[dict] = field(default_factory=list)
    key_state: Dict[str, bool] = field(default_factory=dict)
    hotkey_state: Dict[str, bool] = field(default_factory=dict)
    last_cursor: Optional[object] = None
    exit_requested: bool = False


@dataclass
class SessionState:
    last_skill_check: float = 0.0
    last_result_check: float = 0.0
    last_loot_check: float = 0.0
    skill_zero_streak: int = 0
    skill_nonzero_streak: int = 0
    skill_active: bool = False
    q_pressed_for_cycle: bool = False
    last_q_press_time: float = 0.0
    runs_completed: int = 0
    session_start_ts: float = 0.0
