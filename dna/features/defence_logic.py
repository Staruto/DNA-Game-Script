from __future__ import annotations

import cv2
import time
from typing import Optional

from dna.platform.windows import ROUTE_RECORD_KEYS, ROUTE_RECORD_MOUSE_BUTTONS
from dna.runtime.state import DefenceState, RouteRecordingState
from dna.vision.capture import ScreenCapture
from dna.vision.templates import DEFAULT_HP_SCALES, locate_best_template_multiscale


class DefenceService:
    def __init__(self, config: dict, capture: ScreenCapture, templates, controller, route_manager):
        self.config = config
        self.capture = capture
        self.templates = templates
        self.controller = controller
        self.route_manager = route_manager

    def _get_defence_variants(self) -> dict:
        variants = self.config.get("defence_variants", {})
        return variants if isinstance(variants, dict) else {}

    def _get_variant_display_name(self, variant_key: str) -> str:
        variants = self._get_defence_variants()
        variant = variants.get(variant_key, {}) if isinstance(variants, dict) else {}
        display_name = variant.get("display_name") if isinstance(variant, dict) else None
        return str(display_name or variant_key)

    def _scale_mouse_delta(self, value: int) -> int:
        scale = float(self.config.get("defence_route_mouse_scale", 1.0))
        scaled = int(round(int(value) * scale))
        if value != 0 and scaled == 0:
            return 1 if value > 0 else -1
        return scaled

    def _match_template_in_region(self, template_name: str, region: dict, threshold: float) -> Optional[dict]:
        template = self.templates.load_gray(template_name)
        if template is None or region is None:
            return None

        gray = self.capture.grab_gray(region)
        if gray is None or gray.size == 0:
            return None
        if template.shape[0] > gray.shape[0] or template.shape[1] > gray.shape[1]:
            return None

        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_score, _, max_loc = cv2.minMaxLoc(result)
        score = float(max_score)
        if score < float(threshold):
            return None

        width = int(template.shape[1])
        height = int(template.shape[0])
        return {
            "score": score,
            "loc": max_loc,
            "width": width,
            "height": height,
            "center_x": int(region["left"] + max_loc[0] + width / 2),
            "center_y": int(region["top"] + max_loc[1] + height / 2),
        }

    def _is_target_hp_visible(self) -> bool:
        region = self.config.get("defence_target_hp_region")
        template_name = str(self.config.get("defence_target_hp_template", "defence_hp.png"))
        threshold = float(self.config.get("defence_target_hp_threshold", 0.88))
        template = self.templates.load_gray(template_name)
        match = None
        best_score = None
        if template is not None and region is not None:
            gray = self.capture.grab_gray(region)
            if gray is not None and gray.size > 0:
                result = locate_best_template_multiscale(gray, template, DEFAULT_HP_SCALES)
                if result is not None:
                    best_score = float(result["score"])
                    if best_score >= threshold:
                        x0, y0 = result["loc"]
                        width, height = result["shape"]
                        match = {
                            "score": best_score,
                            "center_x": int(region["left"] + x0 + width / 2),
                            "center_y": int(region["top"] + y0 + height / 2),
                        }
        if bool(self.config.get("debug_defence", False)):
            if match is None:
                score_text = "n/a" if best_score is None else f"{best_score:.3f}"
                print(f"[DEBUG] defence target hp not matched in region={region} score={score_text} threshold={threshold:.3f}")
            else:
                print(f"[DEBUG] defence target hp matched score={match['score']:.3f} center=({match['center_x']}, {match['center_y']})")
        return match is not None

    def _detect_exit_popup_visible(self) -> bool:
        template_name = str(self.config.get("defence_exit_popup_template", "exit_pop_up.png"))
        path = self.templates.resolve_path(template_name)
        if path is None:
            return False
        template = self.templates.load_gray(template_name)
        region = self.config.get("defence_exit_popup_region")
        if template is None or region is None:
            return False

        gray = self.capture.grab_gray(region)
        if gray is None or gray.size == 0:
            return False
        if template.shape != gray.shape:
            template = cv2.resize(template, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)

        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_score, _, _ = cv2.minMaxLoc(result)
        score = float(max_score)
        threshold = float(self.config.get("defence_exit_popup_threshold", 0.93))
        if bool(self.config.get("debug_defence", False)):
            print(f"[DEBUG] defence exit popup score={score:.3f} threshold={threshold:.3f}")
        return score >= threshold

    def _find_quit_button(self) -> Optional[dict]:
        return self._match_template_in_region(
            str(self.config.get("defence_quit_template", "quit_challenge.png")),
            self.config.get("defence_quit_region"),
            float(self.config.get("defence_quit_threshold", 0.8)),
        )

    def _find_confirm_button(self) -> Optional[dict]:
        return self._match_template_in_region(
            str(self.config.get("defence_confirm_template", "confirm.png")),
            self.config.get("defence_confirm_region"),
            float(self.config.get("defence_confirm_threshold", 0.9)),
        )

    def _begin_recovery(self, now: float, state: DefenceState):
        state.ready_for_skill = False
        state.validation_attempted = True
        state.recovery_active = True
        state.recovery_step = "press_esc"
        state.recovery_step_since = now
        state.recovery_retry_count += 1
        state.recovery_notice_count = 0
        state.popup_detected_logged = False
        print(f"[FALLBACK] Defence target validation failed. Restart attempt #{state.recovery_retry_count}.")

    def _process_recovery(self, now: float, state: DefenceState) -> bool:
        if not state.recovery_active:
            return False

        step = state.recovery_step
        if step == "press_esc":
            self.controller.release_keys(ROUTE_RECORD_KEYS)
            self.controller.release_mouse_buttons(ROUTE_RECORD_MOUSE_BUTTONS)
            self.controller.press_key("esc", delay=0.12)
            state.recovery_step = "wait_for_quit"
            state.recovery_step_since = now
            print("[FALLBACK] Opening pause menu with ESC.")
            return True

        if step == "wait_for_quit":
            open_menu_delay = float(self.config.get("defence_quit_open_menu_delay_sec", 0.5))
            if now - state.recovery_step_since < open_menu_delay:
                return True

            quit_match = self._find_quit_button()
            if quit_match is not None:
                print(f"[FALLBACK] Quit Challenge detected. Clicking at ({quit_match['center_x']}, {quit_match['center_y']}).")
                self.controller.move_and_click(quit_match["center_x"], quit_match["center_y"], delay=0.12)
                state.recovery_step = "wait_for_confirm"
                state.recovery_step_since = now
                state.popup_detected_logged = False
                return True

            retry_interval = float(self.config.get("defence_quit_retry_interval_sec", 1.0))
            if now - state.recovery_step_since >= retry_interval:
                print("[FALLBACK] Quit Challenge not found yet. Re-opening pause menu.")
                state.recovery_step = "press_esc"
                state.recovery_step_since = now
            return True

        if step == "wait_for_confirm":
            popup_visible = self._detect_exit_popup_visible()
            if popup_visible and not state.popup_detected_logged:
                print("[FALLBACK] Exit confirmation popup detected.")
                state.popup_detected_logged = True

            confirm_match = self._find_confirm_button()
            if confirm_match is not None:
                print(f"[FALLBACK] Confirm button detected. Clicking at ({confirm_match['center_x']}, {confirm_match['center_y']}).")
                self.controller.move_and_click(confirm_match["center_x"], confirm_match["center_y"], delay=0.12)
                state.recovery_step = "await_restart"
                state.recovery_step_since = now
                repeat_limit = max(1, int(self.config.get("defence_restart_notice_repeat", 3)))
                if state.recovery_notice_count < repeat_limit:
                    print("[FALLBACK] Waiting for existing Challenge Again / Start logic to restart the run.")
                    state.recovery_notice_count += 1
                return True

            retry_interval = float(self.config.get("defence_confirm_retry_interval_sec", 0.8))
            if now - state.recovery_step_since >= retry_interval:
                print("[FALLBACK] Confirm button not found yet. Waiting for exit popup UI.")
                state.recovery_step_since = now
            return True

        if step == "await_restart":
            repeat_limit = max(1, int(self.config.get("defence_restart_notice_repeat", 3)))
            if state.recovery_notice_count < repeat_limit and now - state.recovery_step_since >= 3.0:
                print("[FALLBACK] Still waiting for restart UI after exit. Existing result/start logic remains active.")
                state.recovery_notice_count += 1
                state.recovery_step_since = now
            return True

        return True

    def _validate_arrival_or_recover(self, now: float, state: DefenceState) -> bool:
        if state.ready_for_skill:
            return False
        if state.route_mode != "playback":
            return False
        if state.recovery_active:
            return self._process_recovery(now, state)
        if state.replay_active:
            return False
        if state.replay_finished_at <= 0.0:
            return False

        validate_delay = float(self.config.get("defence_post_replay_validate_delay_sec", 0.8))
        elapsed = now - state.replay_finished_at
        if elapsed < validate_delay:
            return True

        if self._is_target_hp_visible():
            state.ready_for_skill = True
            state.replay_finished_at = 0.0
            state.validation_attempted = False
            print("[INFO] Defence target point confirmed by protect HP bar. Entering skill-only phase.")
            return False

        validate_timeout = float(self.config.get("defence_post_replay_validate_timeout_sec", 6.0))
        deadline = validate_delay + max(0.0, validate_timeout)

        if not state.validation_attempted:
            state.validation_attempted = True
            print("[INFO] Replay finished. Waiting for protect HP bar confirmation before deciding fallback.")
            return True

        if elapsed < deadline:
            return True

        self._begin_recovery(now, state)
        state.replay_finished_at = 0.0
        return self._process_recovery(now, state)

    def _resolve_route_mode(self, route_name: str) -> str:
        override = str(self.config.get("defence_route_mode_override", "auto")).strip().lower()
        if override in ("record", "playback"):
            return override
        path = self.route_manager.route_file_path(route_name)
        return "playback" if path.exists() else "record"

    def _detect_best_entry_variant(self):
        region = self.config.get("defence_entry_region")
        variants = self._get_defence_variants()
        if region is None or not variants:
            return None, None

        gray = self.capture.grab_gray(region)
        if gray is None or gray.size == 0:
            return None, None

        best_variant = None
        best_score = -1.0
        debug_enabled = bool(self.config.get("debug_defence", False))
        for variant_key, variant in variants.items():
            if not isinstance(variant, dict):
                continue
            template_name = str(variant.get("entry_template", "")).strip()
            if not template_name:
                continue
            template = self.templates.load_gray(template_name)
            if template is None:
                continue
            if template.shape[:2] != gray.shape[:2]:
                resized_template = cv2.resize(template, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)
            else:
                resized_template = template

            result = cv2.matchTemplate(gray, resized_template, cv2.TM_CCOEFF_NORMED)
            _, max_score, _, _ = cv2.minMaxLoc(result)
            if debug_enabled:
                print(f"[DEBUG] defence entry variant={variant_key} score={float(max_score):.3f}")
            if max_score > best_score:
                best_score = float(max_score)
                best_variant = str(variant_key)

        threshold = float(self.config.get("defence_entry_threshold", 0.22))
        if debug_enabled:
            print(f"[DEBUG] defence entry best_variant={best_variant} score={best_score:.3f} threshold={threshold:.3f}")
        if best_variant is None or best_score < threshold:
            return None, best_score
        return best_variant, best_score

    def _detect_entry_ready_for_variant(self, variant_key: str) -> bool:
        region = self.config.get("defence_entry_region")
        variants = self._get_defence_variants()
        variant = variants.get(variant_key, {}) if isinstance(variants, dict) else {}
        template_name = str(variant.get("entry_template", "")).strip() if isinstance(variant, dict) else ""
        if region is None or not template_name:
            return False

        template = self.templates.load_gray(template_name)
        if template is None:
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
            print(f"[DEBUG] defence entry confirm variant={variant_key} score={float(max_score):.3f} threshold={threshold:.3f}")
        return bool(float(max_score) >= threshold)

    def _arm_auto_replay_if_ready(self, now: float, state: DefenceState):
        if state.route_mode != "playback" or state.current_variant is None:
            return
        if state.replay_finished_at > 0.0 or state.validation_attempted or state.recovery_active:
            return
        if state.ready_for_skill or state.replay_active or state.replay_pending_until > 0.0:
            return

        if not state.waiting_for_entry_logged:
            print("[INFO] Waiting for defence entry detection before auto replay.")
            state.waiting_for_entry_logged = True

        if self._detect_entry_ready_for_variant(state.current_variant):
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

    def _apply_variant_resolution(self, now: float, state: DefenceState, variant_key: str):
        variants = self._get_defence_variants()
        variant = variants.get(variant_key, {}) if isinstance(variants, dict) else {}
        route_name = str(variant.get("route_name") or variant_key)
        route_mode = self._resolve_route_mode(route_name)
        variant_changed = state.current_variant != variant_key
        route_changed = state.active_route_name != route_name or state.route_mode != route_mode

        state.current_variant = variant_key
        state.active_route_name = route_name
        state.entry_candidate_variant = None
        state.entry_match_streak = 0
        state.unresolved_variant_logged = False
        state.waiting_for_entry_logged = False

        if route_changed:
            state.route_mode = route_mode
            state.replay_route_name = None
            state.replay_events = None
            state.replay_index = 0
            state.replay_pending_until = 0.0
            state.replay_active = False
            state.replay_held_keys.clear()
            self.controller.release_mouse_buttons(state.replay_held_mouse_buttons)
            state.replay_held_mouse_buttons.clear()
            state.missing_route_warned = False

        state.auto_replay_armed = route_mode == "playback" and not state.ready_for_skill
        state.entry_detected_logged = False

        if variant_changed or route_changed:
            display_name = self._get_variant_display_name(variant_key)
            print(f"[INFO] Defence variant resolved: {display_name} ({variant_key})")
            if route_mode == "playback":
                path = self.route_manager.route_file_path(route_name)
                print(f"[INFO] Defence route mode: PLAYBACK ({path.name})")
                print("[INFO] Playback mode ready. Route replay will auto-start after dungeon entry is confirmed, or press I to replay manually.")
            else:
                print(f"[INFO] Defence route mode: RECORD ({route_name}.json not found)")
                print("[INFO] Record mode ready. Press P to start recording and O to stop/save/exit.")

    def resolve_variant(self, now: float, state: DefenceState) -> Optional[str]:
        if state.current_variant:
            return state.current_variant

        variants = self._get_defence_variants()
        if not variants:
            if not state.unresolved_variant_logged:
                print("[WARN] No defence variants are configured. Waiting for a valid defence variant configuration.")
                state.unresolved_variant_logged = True
            return None

        auto_detect = bool(self.config.get("auto_detect_defence", True))
        if not auto_detect:
            manual_variant = str(self.config.get("manual_defence_variant", "")).strip()
            if manual_variant not in variants:
                if not state.unresolved_variant_logged:
                    print(f"[WARN] Unknown manual defence variant '{manual_variant}'. Waiting for a valid manual_defence_variant.")
                    state.unresolved_variant_logged = True
                return None
            self._apply_variant_resolution(now, state, manual_variant)
            return state.current_variant

        matched_variant, _ = self._detect_best_entry_variant()
        if matched_variant is None:
            state.entry_candidate_variant = None
            state.entry_match_streak = 0
            if not state.unresolved_variant_logged:
                print("[INFO] Waiting for defence variant detection before record/playback selection.")
                state.unresolved_variant_logged = True
            return None

        if state.entry_candidate_variant == matched_variant:
            state.entry_match_streak += 1
        else:
            state.entry_candidate_variant = matched_variant
            state.entry_match_streak = 1

        confirm_frames = max(1, int(self.config.get("defence_entry_confirm_frames", 3)))
        if state.entry_match_streak < confirm_frames:
            return None

        self._apply_variant_resolution(now, state, matched_variant)
        return state.current_variant

    def is_prephase_active(self, state: DefenceState) -> bool:
        if state.ready_for_skill:
            return False
        if state.current_variant is None:
            return True
        if state.route_mode == "record":
            return True
        if state.recovery_active:
            return True
        if state.replay_active or state.replay_pending_until > 0.0 or state.auto_replay_armed:
            return True
        if state.replay_finished_at > 0.0 and not state.ready_for_skill:
            return True
        return False

    def _run_route_replay(self, now: float, state: DefenceState):
        if not self.config.get("defence_route_replay_enabled", True):
            return None

        route_name = state.active_route_name
        if not route_name:
            return None
        if state.replay_route_name != route_name:
            state.replay_route_name = route_name
            state.replay_events = None
            state.replay_index = 0
            state.replay_active = False
            state.replay_held_keys.clear()
            self.controller.release_mouse_buttons(state.replay_held_mouse_buttons)
            state.replay_held_mouse_buttons.clear()
            state.replay_finished_at = 0.0
            state.validation_attempted = False
            state.missing_route_warned = False

        if state.replay_events is None:
            state.replay_events = self.route_manager.load_route(route_name)

        replay_events = state.replay_events
        if not replay_events:
            return None

        pending_until = float(state.replay_pending_until)
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
            state.replay_finished_at = 0.0
            state.validation_attempted = False
            print(f"[INFO] Defence route replay started: {route_name}")

        elapsed = max(0.0, now - state.replay_start_ts)
        idx = state.replay_index
        held_keys = state.replay_held_keys
        held_mouse_buttons = state.replay_held_mouse_buttons

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
                dx = self._scale_mouse_delta(int(evt.get("dx", 0)))
                dy = self._scale_mouse_delta(int(evt.get("dy", 0)))
                if dx != 0 or dy != 0:
                    self.controller.move_mouse_relative(dx, dy)
            elif evt_type == "mouse_button":
                button = str(evt.get("button", "")).lower()
                action = str(evt.get("action", "")).lower()
                if action == "down":
                    if self.controller.mouse_button_down(button):
                        held_mouse_buttons.add(button)
                elif action == "up":
                    self.controller.mouse_button_up(button)
                    held_mouse_buttons.discard(button)
            idx += 1

        state.replay_index = idx
        if idx >= len(replay_events):
            self.controller.release_keys(list(held_keys) + ROUTE_RECORD_KEYS)
            self.controller.release_mouse_buttons(list(held_mouse_buttons) + ROUTE_RECORD_MOUSE_BUTTONS)
            held_keys.clear()
            held_mouse_buttons.clear()
            state.replay_active = False
            state.replay_finished_at = now
            state.validation_attempted = False
            print("[INFO] Defence route replay finished. Validating arrival at protect point.")
            return False
        return True

    def update(self, now: float, state: DefenceState) -> bool:
        if self.resolve_variant(now, state) is None:
            state.last_update_ts = now
            return True

        if state.replay_finished_at > 0.0 or state.recovery_active:
            validation_or_recovery = self._validate_arrival_or_recover(now, state)
            if validation_or_recovery:
                state.last_update_ts = now
                return True

        self._arm_auto_replay_if_ready(now, state)

        replay_status = self._run_route_replay(now, state)
        if replay_status is not None:
            state.last_update_ts = now
            return replay_status

        validation_or_recovery = self._validate_arrival_or_recover(now, state)
        if validation_or_recovery:
            state.last_update_ts = now
            return True

        if state.route_mode == "record":
            if state.w_holding:
                self.controller.key_up("w")
                state.w_holding = False
            state.last_update_ts = now
            return True

        if state.w_holding:
            self.controller.key_up("w")
            state.w_holding = False
        state.last_update_ts = now
        return True

    def process_hotkeys(self, record_state: RouteRecordingState, defence_state: DefenceState):
        start_key = str(self.config.get("defence_route_record_hotkey_start", "p")).lower()
        stop_key = str(self.config.get("defence_route_record_hotkey_stop", "o")).lower()
        replay_key = str(self.config.get("defence_route_replay_hotkey", "i")).lower()

        def just_pressed(key: str) -> bool:
            now_down = self.controller.is_physical_key_down(key)
            previous_down = bool(record_state.hotkey_state.get(key, False))
            record_state.hotkey_state[key] = now_down
            return now_down and not previous_down

        route_mode = defence_state.route_mode
        if route_mode == "disabled":
            just_pressed(start_key)
            just_pressed(stop_key)
            just_pressed(replay_key)
            return

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
            self.route_manager.reset_defence_state(defence_state, pending_replay_after_delay=False, clear_variant=False)
            defence_state.replay_pending_until = time.time()
            defence_state.auto_replay_armed = False
            print("[INFO] Defence route replay manually triggered.")
