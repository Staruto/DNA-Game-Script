from __future__ import annotations

import json
import time
from typing import Optional

from dna.config import defence_route_path
from dna.platform.windows import ROUTE_RECORD_KEYS, WindowsController
from dna.runtime.state import DefenceState, RouteRecordingState


class DefenceRouteManager:
    def __init__(self, config: dict, controller: WindowsController):
        self.config = config
        self.controller = controller

    def route_file_path(self, route_name: Optional[str] = None):
        if route_name is None:
            route_name = str(self.config.get("defence_route_name", "defence_default"))
        return defence_route_path(route_name)

    def save_route(self, events, route_name: Optional[str] = None) -> str:
        file_path = self.route_file_path(route_name)
        payload = {
            "route_name": route_name or str(self.config.get("defence_route_name", "defence_default")),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "events": events,
        }
        with open(file_path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        return str(file_path)

    def load_route(self, route_name: Optional[str] = None):
        file_path = self.route_file_path(route_name)
        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)

        events = payload.get("events", []) if isinstance(payload, dict) else []
        if not isinstance(events, list):
            return None
        events.sort(key=lambda item: float(item.get("t", 0.0)))
        return events

    def reset_defence_state(self, state: DefenceState, pending_replay_after_delay: bool = False):
        state.started = False
        state.ready_for_skill = False
        state.w_holding = False
        state.last_update_ts = 0.0
        state.replay_active = False
        state.replay_start_ts = 0.0
        state.replay_index = 0
        state.replay_events = None
        state.replay_route_name = None
        state.replay_held_keys.clear()
        state.replay_pending_until = 0.0
        state.auto_replay_armed = pending_replay_after_delay
        state.entry_detected_logged = False
        state.waiting_for_entry_logged = False
        state.entry_match_streak = 0
        state.missing_route_warned = False

    def start_recording(self, record_state: RouteRecordingState, defence_state: DefenceState):
        self.controller.release_keys(ROUTE_RECORD_KEYS)
        self.reset_defence_state(defence_state, pending_replay_after_delay=False)
        record_state.active = True
        record_state.start_ts = time.time()
        record_state.events = []
        record_state.last_cursor = self.controller.get_cursor_position()
        for key in ROUTE_RECORD_KEYS:
            record_state.key_state[key] = self.controller.is_physical_key_down(key)
        print(f"[INFO] Defence route recording started. Route={self.config.get('defence_route_name')}")

    def stop_recording(self, record_state: RouteRecordingState, save: bool = True):
        if not record_state.active:
            return

        now = time.time()
        elapsed = max(0.0, now - record_state.start_ts)
        for key in ROUTE_RECORD_KEYS:
            if record_state.key_state.get(key, False):
                record_state.events.append({"t": round(elapsed, 4), "type": "key", "key": key, "action": "up"})

        if save:
            path = self.save_route(record_state.events, str(self.config.get("defence_route_name", "defence_default")))
            print(f"[INFO] Defence route recording saved: {path} (events={len(record_state.events)})")
        else:
            print("[INFO] Defence route recording cancelled.")

        record_state.active = False
        record_state.events = []
        record_state.last_cursor = None
        for key in ROUTE_RECORD_KEYS:
            record_state.key_state[key] = False

    def poll_recording(self, now: float, record_state: RouteRecordingState):
        if not record_state.active:
            return
        if not self.controller.is_game_window_foreground():
            return

        elapsed = max(0.0, now - record_state.start_ts)
        for key in ROUTE_RECORD_KEYS:
            current = self.controller.is_physical_key_down(key)
            previous = record_state.key_state.get(key, False)
            if current != previous:
                record_state.events.append(
                    {
                        "t": round(elapsed, 4),
                        "type": "key",
                        "key": key,
                        "action": "down" if current else "up",
                    }
                )
                record_state.key_state[key] = current

        cursor = self.controller.get_cursor_position()
        if cursor is not None and record_state.last_cursor is not None:
            dx = int(cursor.x - record_state.last_cursor.x)
            dy = int(cursor.y - record_state.last_cursor.y)
            if dx != 0 or dy != 0:
                record_state.events.append({"t": round(elapsed, 4), "type": "mouse", "dx": dx, "dy": dy})
        if cursor is not None:
            record_state.last_cursor = cursor
