from __future__ import annotations

import time
from typing import Callable, Optional

from dna.config import get_default_config
from dna.features.defence_logic import DefenceService
from dna.features.dungeon_detection import DungeonDetector
from dna.features.loot_logic import LootService
from dna.features.result_ui import ResultUIService
from dna.features.skill_logic import SkillService
from dna.platform.windows import ROUTE_RECORD_KEYS, WindowsController
from dna.profiles import DUNGEON_PROFILES
from dna.routes.defence_routes import DefenceRouteManager
from dna.runtime.state import DefenceState, LootState, RouteRecordingState, SessionState
from dna.vision.capture import ScreenCapture
from dna.vision.templates import TemplateStore


class DNAApp:
    def __init__(self, config: dict | None = None):
        self.config = config or get_default_config()
        self.controller = WindowsController(self.config)
        self.capture = ScreenCapture()
        self.templates = TemplateStore()
        self.route_manager = DefenceRouteManager(self.config, self.controller)
        self.dungeon_detector = DungeonDetector(self.config, self.templates)
        self.skill_service = SkillService(self.config, self.capture, self.templates)
        self.result_ui = ResultUIService(self.config, self.capture, self.templates, self.controller)
        self.loot_service = LootService(self.config, self.capture, self.templates, self.controller)
        self.defence_service = DefenceService(self.config, self.capture, self.templates, self.controller, self.route_manager)

    def _emit_event(self, on_event: Optional[Callable[[str, dict], None]], event_name: str, payload: Optional[dict] = None):
        if on_event is None:
            return
        try:
            on_event(event_name, payload or {})
        except Exception:
            return

    def _format_duration(self, seconds: float) -> str:
        seconds = max(0, int(seconds))
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _print_run_stats(self, state: SessionState):
        if not self.config.get("enable_run_stats", True):
            return
        elapsed = time.time() - state.session_start_ts
        avg = elapsed / state.runs_completed if state.runs_completed > 0 else 0.0
        target = int(self.config.get("target_runs", 0))
        if target > 0:
            print(f"[STATS] Runs: {state.runs_completed}/{target} | Elapsed: {self._format_duration(elapsed)} | Avg/run: {avg:.1f}s")
        else:
            print(f"[STATS] Runs: {state.runs_completed} | Elapsed: {self._format_duration(elapsed)} | Avg/run: {avg:.1f}s")

    def _print_session_summary(self, state: SessionState):
        elapsed = time.time() - state.session_start_ts
        avg = elapsed / state.runs_completed if state.runs_completed > 0 else 0.0
        print("[INFO] Session finished.")
        print(f"[INFO] Total runs: {state.runs_completed}")
        print(f"[INFO] Total elapsed: {self._format_duration(elapsed)}")
        print(f"[INFO] Average per run: {avg:.1f}s")

    def _validate_runtime_config(self):
        manual_key = self.config.get("manual_dungeon", "expulsion")
        if manual_key not in DUNGEON_PROFILES:
            print(f"[WARN] Unknown manual_dungeon '{manual_key}', fallback to 'expulsion'.")
            self.config["manual_dungeon"] = "expulsion"
        mode = self.config.get("dungeon_mode", "manual").lower()
        if mode not in ("manual", "auto"):
            print(f"[WARN] Unknown dungeon_mode '{mode}', fallback to 'manual'.")
            self.config["dungeon_mode"] = "manual"

        variants = self.config.get("defence_variants", {})
        if not isinstance(variants, dict) or not variants:
            print("[WARN] defence_variants is empty. Defence route automation will remain idle.")

        manual_variant = str(self.config.get("manual_defence_variant", "")).strip()
        if manual_variant and isinstance(variants, dict) and variants and manual_variant not in variants:
            fallback_variant = next(iter(variants))
            print(f"[WARN] Unknown manual_defence_variant '{manual_variant}', fallback to '{fallback_variant}'.")
            self.config["manual_defence_variant"] = fallback_variant

        route_override = str(self.config.get("defence_route_mode_override", "auto")).strip().lower()
        if route_override not in ("auto", "record", "playback"):
            print(f"[WARN] Unknown defence_route_mode_override '{route_override}', fallback to 'auto'.")
            self.config["defence_route_mode_override"] = "auto"

        keywords = self.config.get("game_window_keywords", [])
        if isinstance(keywords, str):
            self.config["game_window_keywords"] = [keywords]
        elif not isinstance(keywords, list):
            self.config["game_window_keywords"] = ["Duet Night Abyss", "Abyss"]

    def run(
        self,
        should_stop: Optional[Callable[[], bool]] = None,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        self._validate_runtime_config()

        print("[INFO] Duet Night Abyss helper started.")
        print("[INFO] Input backend: Windows SendInput (DirectX-compatible path).")
        if not self.controller.is_running_as_admin():
            print("[WARN] Not running as administrator. Some games may block input events.")

        mode = self.config.get("dungeon_mode", "manual").lower()
        manual_profile = DUNGEON_PROFILES[self.config.get("manual_dungeon", "expulsion")]
        if mode == "auto":
            print("[INFO] Dungeon mode: AUTO (template-based name detection).")
        else:
            print(f"[INFO] Dungeon mode: MANUAL ({manual_profile.display_name}).")

        target_runs = int(self.config.get("target_runs", 0))
        if target_runs > 0:
            print(f"[INFO] Target runs this session: {target_runs}")
        else:
            print("[INFO] Target runs this session: unlimited")

        self._emit_event(
            on_event,
            "session_started",
            {
                "mode": mode,
                "manual_dungeon": manual_profile.key,
                "target_runs": target_runs,
            },
        )

        print("[INFO] Switch to the game window. Starting in 3 seconds...")
        time.sleep(3)

        session = SessionState(session_start_ts=time.time())
        loot_state = LootState()
        defence_state = DefenceState()
        defence_success_runs = 0
        defence_ready_prev = False
        record_state = RouteRecordingState(
            key_state={key: False for key in ROUTE_RECORD_KEYS},
            mouse_button_state={"left": False, "right": False},
            hotkey_state={
                str(self.config.get("defence_route_record_hotkey_start", "p")).lower(): False,
                str(self.config.get("defence_route_record_hotkey_stop", "o")).lower(): False,
                str(self.config.get("defence_route_replay_hotkey", "i")).lower(): False,
            },
        )

        while True:
            try:
                now = time.time()

                if should_stop is not None and should_stop():
                    self.route_manager.stop_recording(record_state, save=False)
                    self.controller.release_keys(ROUTE_RECORD_KEYS)
                    self._print_session_summary(session)
                    if defence_success_runs > 0:
                        print(f"[INFO] Defence success runs: {defence_success_runs}")
                    self._emit_event(
                        on_event,
                        "session_finished",
                        {
                            "runs_completed": session.runs_completed,
                            "elapsed_sec": max(0.0, time.time() - session.session_start_ts),
                            "defence_success_runs": defence_success_runs,
                            "stopped_by_user": True,
                        },
                    )
                    print("[INFO] Script stopped by GUI request.")
                    break

                if record_state.exit_requested:
                    print("[INFO] Recording finished. Exiting.")
                    break
                if not record_state.active and not self.controller.is_game_window_foreground():
                    time.sleep(0.2)
                    continue

                active_profile = self.dungeon_detector.get_active_profile(self.capture)

                if active_profile.key == "defence" or record_state.active or defence_state.route_mode == "record":
                    self.defence_service.process_hotkeys(record_state, defence_state)
                    self.route_manager.poll_recording(now, record_state)

                if record_state.exit_requested:
                    print("[INFO] Recording finished. Exiting.")
                    break
                if record_state.active:
                    time.sleep(0.01)
                    continue

                if now - session.last_result_check >= self.config["result_check_interval"]:
                    session.last_result_check = now
                    result_action = self.result_ui.check_and_click_result_ui(active_profile)
                    if result_action == "start_clicked":
                        self.controller.release_keys(ROUTE_RECORD_KEYS)
                        self.route_manager.reset_defence_state(
                            defence_state,
                            pending_replay_after_delay=False,
                            clear_variant=True,
                        )
                        session.runs_completed += 1
                        self._print_run_stats(session)
                        self._emit_event(
                            on_event,
                            "run_completed",
                            {
                                "runs_completed": session.runs_completed,
                                "target_runs": target_runs,
                            },
                        )
                        if target_runs > 0 and session.runs_completed >= target_runs:
                            self._print_session_summary(session)
                            self._emit_event(
                                on_event,
                                "session_finished",
                                {
                                    "runs_completed": session.runs_completed,
                                    "elapsed_sec": max(0.0, time.time() - session.session_start_ts),
                                    "defence_success_runs": defence_success_runs,
                                    "stopped_by_user": False,
                                },
                            )
                            break
                        continue

                if active_profile.key == "defence":
                    update_interval = float(self.config.get("defence_check_interval", 0.22))
                    if defence_state.replay_active:
                        update_interval = float(self.config.get("defence_replay_tick_interval", 0.01))
                    if now - defence_state.last_update_ts >= update_interval:
                        defence_active = self.defence_service.update(now, defence_state)
                    else:
                        defence_active = self.defence_service.is_prephase_active(defence_state)

                    if defence_state.ready_for_skill and not defence_ready_prev:
                        defence_success_runs += 1
                        self._emit_event(
                            on_event,
                            "defence_success",
                            {"defence_success_runs": defence_success_runs},
                        )
                    defence_ready_prev = defence_state.ready_for_skill

                    if defence_active:
                        sleep_interval = 0.02
                        if defence_state.replay_active:
                            sleep_interval = float(self.config.get("defence_replay_tick_interval", 0.01))
                        time.sleep(sleep_interval)
                        continue
                else:
                    defence_ready_prev = False
                    self.controller.release_keys(ROUTE_RECORD_KEYS)
                    self.route_manager.reset_defence_state(defence_state, pending_replay_after_delay=False, clear_variant=True)

                loot_approaching = False
                if active_profile.key != "defence":
                    if now - session.last_loot_check >= float(self.config.get("loot_check_interval", 0.35)):
                        session.last_loot_check = now
                        loot_approaching = self.loot_service.update_loot_approach_state(now, loot_state)
                    elif loot_state.active:
                        loot_approaching = self.loot_service.update_loot_approach_state(now, loot_state)
                if loot_approaching:
                    time.sleep(0.02)
                    continue

                if active_profile.use_skill_logic and (now - session.last_skill_check >= self.config["skill_check_interval"]):
                    session.last_skill_check = now
                    skill_active_detected = self.skill_service.detect_skill_active_state()
                    if skill_active_detected is None:
                        time.sleep(0.05)
                        continue
                    if skill_active_detected:
                        session.skill_zero_streak += 1
                        session.skill_nonzero_streak = 0
                    else:
                        session.skill_nonzero_streak += 1
                        session.skill_zero_streak = 0

                    confirm_frames = max(1, int(self.config.get("skill_state_confirm_frames", 2)))
                    if session.skill_zero_streak >= confirm_frames:
                        if not session.skill_active:
                            print("[INFO] Skill state changed: ACTIVE (zero detected).")
                        session.skill_active = True
                        session.q_pressed_for_cycle = False

                    if session.skill_nonzero_streak >= confirm_frames:
                        if session.skill_active:
                            print("[INFO] Skill state changed: INACTIVE (zero missing).")
                        session.skill_active = False

                    if not session.skill_active:
                        retry_interval = float(self.config.get("skill_press_retry_interval", 8.0))
                        should_press = (not session.q_pressed_for_cycle) or ((now - session.last_q_press_time) >= retry_interval)
                        if should_press:
                            print(f"[INFO] Skill inactive. Pressing {active_profile.skill_key.upper()}.")
                            self.controller.press_key(active_profile.skill_key, delay=0.15)
                            session.q_pressed_for_cycle = True
                            session.last_q_press_time = now
                            time.sleep(0.35)

                time.sleep(0.05)

            except KeyboardInterrupt:
                self.route_manager.stop_recording(record_state, save=False)
                self.controller.release_keys(ROUTE_RECORD_KEYS)
                self._print_session_summary(session)
                self._emit_event(
                    on_event,
                    "session_finished",
                    {
                        "runs_completed": session.runs_completed,
                        "elapsed_sec": max(0.0, time.time() - session.session_start_ts),
                        "defence_success_runs": defence_success_runs,
                        "stopped_by_user": True,
                    },
                )
                print("[INFO] Script stopped by user.")
                break
