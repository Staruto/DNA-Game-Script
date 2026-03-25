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
    current_variant: Optional[str] = None
    active_route_name: Optional[str] = None
    entry_candidate_variant: Optional[str] = None
    replay_active: bool = False
    replay_start_ts: float = 0.0
    replay_index: int = 0
    replay_events: Optional[List[dict]] = None
    replay_route_name: Optional[str] = None
    replay_held_keys: Set[str] = field(default_factory=set)
    replay_held_mouse_buttons: Set[str] = field(default_factory=set)
    replay_pending_until: float = 0.0
    replay_finished_at: float = 0.0
    auto_replay_armed: bool = False
    entry_detected_logged: bool = False
    waiting_for_entry_logged: bool = False
    entry_match_streak: int = 0
    route_mode: str = "disabled"
    missing_route_warned: bool = False
    unresolved_variant_logged: bool = False
    validation_attempted: bool = False
    recovery_active: bool = False
    recovery_step: str = "idle"
    recovery_step_since: float = 0.0
    recovery_retry_count: int = 0
    recovery_notice_count: int = 0
    popup_detected_logged: bool = False
    replay_locked_until_restart: bool = False
    replay_exec_events: List[dict] = field(default_factory=list)
    replay_exec_emitted: int = 0


@dataclass
class RouteRecordingState:
    active: bool = False
    start_ts: float = 0.0
    events: List[dict] = field(default_factory=list)
    route_name: Optional[str] = None
    key_state: Dict[str, bool] = field(default_factory=dict)
    mouse_button_state: Dict[str, bool] = field(default_factory=dict)
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
