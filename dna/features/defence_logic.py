from __future__ import annotations

import cv2
import time
from typing import Optional

from dna.platform.windows import ROUTE_RECORD_KEYS
from dna.runtime.state import DefenceState, RouteRecordingState
from dna.vision.capture import ScreenCapture
from dna.vision.templates import DEFAULT_DEFENCE_SCALES, DEFAULT_HP_SCALES, locate_best_template_multiscale, max_template_score_multiscale


class DefenceService:
    def __init__(self, config: dict, capture: ScreenCapture, templates, controller, route_manager):
        self.config = config
        self.capture = capture
        self.templates = templates
        self.controller = controller
        self.route_manager = route_manager
        self._marker_warned = False
        self._hp_warned = False

    def prompt_route_mode(self) -> str:
        configured = str(self.config.get("defence_route_mode", "prompt")).strip().lower()
        if configured in ("record", "playback"):
            return configured

        prompt = "[INPUT] Defence route mode: [R]ecord / [P]layback (default P): "
        try:
            while True:
                answer = input(prompt).strip().lower()
                if answer in ("", "p", "playback", "2"):
                    return "playback"
                if answer in ("r", "record", "1"):
                    return "record"
                print("[WARN] Invalid choice. Enter R or P.")
        except EOFError:
            return "playback"

    def _get_defence_entry_template_gray(self):
        template_name = str(self.config.get("defence_entry_template", "")).strip()
        return self.templates.load_gray(template_name) if template_name else None

    def detect_entry_ready(self) -> bool:
        template = self._get_defence_entry_template_gray()
        region = self.config.get("defence_entry_region")
        if template is None or region is None:
            return False

        gray = self.capture.grab_gray(region)
        if gray is None or gray.size == 0:
            return False

        if template.shape[:2] != gray.shape[:2]:
            resized_template = cv2.resize(template, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)
        else:
            resized_template = template

        result = cv2.matchTemplate(gray, resized_template, cv2.TM_CCOEFF_NORMED)
        _, max_score, _, _ = cv2.minMaxLoc(result)
        threshold = float(self.config.get("defence_entry_threshold", 0.22))
        if bool(self.config.get("debug_defence", False)):
            print(f"[DEBUG] defence entry score={float(max_score):.3f}, threshold={threshold:.3f}")
        return bool(float(max_score) >= threshold)

    def _arm_auto_replay_if_ready(self, now: float, state: DefenceState):
        if not state.auto_replay_armed or state.replay_active or state.replay_pending_until > 0.0:
            return

        if not state.waiting_for_entry_logged:
            print("[INFO] Waiting for defence entry detection before auto replay.")
            state.waiting_for_entry_logged = True

        if self.detect_entry_ready():
            state.entry_match_streak += 1
        else:
            state.entry_match_streak = 0

        confirm_frames = max(1, int(self.config.get("defence_entry_confirm_frames", 3)))
        if state.entry_match_streak >= confirm_frames:
            delay = float(self.config.get("defence_route_replay_after_load_delay_sec", 3.0))
            state.replay_pending_until = now + max(0.0, delay)
            state.auto_replay_armed = False
            state.entry_match_streak = 0
            if not state.entry_detected_logged:
                print(f"[INFO] Defence entry detected. Route replay will start in {delay:.1f}s.")
                state.entry_detected_logged = True

    def is_prephase_active(self, state: DefenceState) -> bool:
        if state.ready_for_skill:
            return False
        if state.replay_active or state.replay_pending_until > 0.0 or state.auto_replay_armed or state.w_holding:
            return True
        return False

    def _turn_camera_towards_x(self, target_x: int, region: dict, deadzone: int, gain: float, max_step: int):
        center_x = region["left"] + region["width"] // 2
        error_x = int(target_x - center_x)
        if abs(error_x) <= deadzone:
            return
        step = int(error_x * gain)
        if step == 0:
            step = 1 if error_x > 0 else -1
        step = max(-max_step, min(max_step, step))
        self.controller.move_mouse_relative(dx=step, dy=0)

    def _run_route_replay(self, now: float, state: DefenceState):
        if not self.config.get("defence_route_replay_enabled", True):
            return None

        route_name = str(self.config.get("defence_route_name", "defence_default"))
        if state.replay_route_name != route_name:
            state.replay_route_name = route_name
            state.replay_events = None
            state.replay_index = 0
            state.replay_active = False
            state.replay_held_keys.clear()
            state.missing_route_warned = False

        if state.replay_events is None:
            state.replay_events = self.route_manager.load_route(route_name)

        replay_events = state.replay_events
        if not replay_events:
            if state.route_mode == "playback":
                if not state.missing_route_warned:
                    path = self.route_manager.route_file_path(route_name)
                    print(f"[WARN] Defence route file missing or empty: {path}. Playback paused in pre-phase.")
                    state.missing_route_warned = True
                return True
            return None

        pending_until = float(state.replay_pending_until)
        if state.auto_replay_armed and not state.replay_active and pending_until <= 0.0:
            return True
        if not state.replay_active and pending_until <= 0.0:
            return None
        if not state.replay_active and now < pending_until:
            return True

        if not state.replay_active:
            state.replay_active = True
            state.replay_start_ts = now
            state.replay_index = 0
            state.replay_held_keys.clear()
            state.replay_pending_until = 0.0
            print(f"[INFO] Defence route replay started: {route_name}")

        elapsed = max(0.0, now - state.replay_start_ts)
        idx = state.replay_index
        held_keys = state.replay_held_keys

        while idx < len(replay_events):
            evt = replay_events[idx]
            evt_t = float(evt.get("t", 0.0))
            if evt_t > elapsed:
                break
            evt_type = evt.get("type")
            if evt_type == "key":
                key = str(evt.get("key", "")).lower()
                action = str(evt.get("action", "")).lower()
                if action == "down":
                    if self.controller.key_down(key):
                        held_keys.add(key)
                elif action == "up":
                    self.controller.key_up(key)
                    held_keys.discard(key)
            elif evt_type == "mouse":
                self.controller.move_mouse_relative(int(evt.get("dx", 0)), int(evt.get("dy", 0)))
            idx += 1

        state.replay_index = idx
        if idx >= len(replay_events):
            self.controller.release_keys(list(held_keys) + ROUTE_RECORD_KEYS)
            held_keys.clear()
            state.replay_active = False
            state.ready_for_skill = True
            print("[INFO] Defence route replay finished. Entering skill-only phase.")
            return False
        return True

    def _process_marker_fallback(self, now: float, state: DefenceState) -> bool:
        if self.config.get("defence_use_hp_bar_stop", False) and self.detect_protect_hp_bar():
            if state.w_holding:
                self.controller.key_up("w")
                state.w_holding = False
            state.ready_for_skill = True
            print("[INFO] Defence protect-target HP bar detected. Entering skill-only phase.")
            return False

        marker = self.detect_marker()
        if marker is not None:
            region = self.config.get("defence_marker_region")
            self._turn_camera_towards_x(
                marker["x"],
                region,
                int(self.config.get("defence_turn_deadzone_px", 36)),
                float(self.config.get("defence_turn_gain", 0.085)),
                int(self.config.get("defence_turn_max_step_px", 28)),
            )

        if not state.started:
            state.started = True
            print("[INFO] Defence run started. Moving to protect point.")
        if not state.w_holding and self.controller.key_down("w"):
            state.w_holding = True
        state.last_update_ts = now
        return True

    def update(self, now: float, state: DefenceState) -> bool:
        if not self.config.get("defence_enabled", True):
            return False
        if state.ready_for_skill:
            if state.w_holding:
                self.controller.key_up("w")
                state.w_holding = False
            return False

        self._arm_auto_replay_if_ready(now, state)
        replay_status = self._run_route_replay(now, state)
        if replay_status is not None:
            state.last_update_ts = now
            return replay_status

        if state.route_mode == "playback" and not self.config.get("defence_route_replay_fallback_to_cv", False):
            if state.w_holding:
                self.controller.key_up("w")
                state.w_holding = False
            state.last_update_ts = now
            return True

        return self._process_marker_fallback(now, state)

    def process_hotkeys(self, record_state: RouteRecordingState, defence_state: DefenceState, route_mode: str):
        start_key = str(self.config.get("defence_route_record_hotkey_start", "p")).lower()
        stop_key = str(self.config.get("defence_route_record_hotkey_stop", "o")).lower()
        replay_key = str(self.config.get("defence_route_replay_hotkey", "i")).lower()

        def just_pressed(key: str) -> bool:
            now_down = self.controller.is_physical_key_down(key)
            previous_down = bool(record_state.hotkey_state.get(key, False))
            record_state.hotkey_state[key] = now_down
            return now_down and not previous_down

        if route_mode == "record":
            if just_pressed(start_key):
                if record_state.active:
                    print("[INFO] Recording is already active.")
                else:
                    self.route_manager.start_recording(record_state, defence_state)
            if just_pressed(stop_key) and record_state.active:
                self.route_manager.stop_recording(record_state, save=True)
                record_state.exit_requested = True
            just_pressed(replay_key)
            return

        just_pressed(start_key)
        just_pressed(stop_key)
        if just_pressed(replay_key):
            self.controller.release_keys(ROUTE_RECORD_KEYS)
            self.route_manager.reset_defence_state(defence_state, pending_replay_after_delay=False)
            defence_state.replay_pending_until = time.time()
            defence_state.auto_replay_armed = False
            print("[INFO] Defence route replay manually triggered.")

    def detect_marker(self):
        region = self.config.get("defence_marker_region")
        template = self.templates.load_gray("Defence 1.png")
        if region is None or template is None:
            if not self._marker_warned:
                print("[WARN] Defence marker template not found: Defence 1.png (checked assets and workspace root).")
                self._marker_warned = True
            return None

        gray = self.capture.grab_gray(region)
        result = locate_best_template_multiscale(gray, template, DEFAULT_DEFENCE_SCALES)
        if result is None:
            return None
        threshold = float(self.config.get("defence_marker_threshold", 0.55))
        if result["score"] < threshold:
            return None
        x0, y0 = result["loc"]
        scaled_w, scaled_h = result["shape"]
        marker_center_x = region["left"] + x0 + scaled_w // 2
        marker_center_y = region["top"] + y0 + scaled_h // 2
        if bool(self.config.get("debug_defence", False)):
            print(f"[DEBUG] defence marker score={result['score']:.3f} center=({marker_center_x}, {marker_center_y})")
        return {"x": marker_center_x, "y": marker_center_y, "score": float(result["score"])}

    def detect_protect_hp_bar(self) -> bool:
        region = self.config.get("defence_hp_bar_region")
        template = self.templates.load_gray("Defence 2.png")
        if region is None or template is None:
            if not self._hp_warned:
                print("[WARN] Defence HP-bar template not found: Defence 2.png (checked assets and workspace root).")
                self._hp_warned = True
            return False
        gray = self.capture.grab_gray(region)
        score = max_template_score_multiscale(gray, template, DEFAULT_HP_SCALES)
        if score is None:
            return False
        threshold = float(self.config.get("defence_hp_bar_threshold", 0.72))
        if bool(self.config.get("debug_defence", False)):
            print(f"[DEBUG] defence hp_bar score={score:.3f}, threshold={threshold:.3f}")
        return bool(score >= threshold)
