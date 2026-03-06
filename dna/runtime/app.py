from __future__ import annotations

import time
from typing import Optional

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
        self.route_mode: Optional[str] = None
        self._route_mode_ready_logged = False
        self.dungeon_detector = DungeonDetector(self.config, self.templates)
        self.skill_service = SkillService(self.config, self.capture, self.templates)
        self.result_ui = ResultUIService(self.config, self.capture, self.templates, self.controller)
        self.loot_service = LootService(self.config, self.capture, self.templates, self.controller)
        self.defence_service = DefenceService(self.config, self.capture, self.templates, self.controller, self.route_manager)

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

    def _defence_routes_relevant_at_startup(self) -> bool:
        mode = self.config.get("dungeon_mode", "manual").lower()
        if mode == "manual":
            return self.config.get("manual_dungeon", "expulsion") == "defence"
        return False

    def _ensure_route_mode_for_profile(self, profile_key: str, defence_state: DefenceState):
        if profile_key != "defence":
            return
        if self.route_mode is None:
            self.route_mode = self.defence_service.prompt_route_mode()
            defence_state.route_mode = self.route_mode
            defence_state.auto_replay_armed = self.route_mode == "playback"
            print(f"[INFO] Defence route mode: {self.route_mode.upper()}")

        if not self._route_mode_ready_logged:
            if self.route_mode == "record":
                print("[INFO] Record mode ready. Press P to start recording and O to stop/save/exit.")
            else:
                print("[INFO] Playback mode ready. Route replay will auto-start after dungeon entry is detected, or press I to replay manually.")
            self._route_mode_ready_logged = True

    def run(self):
        self._validate_runtime_config()

        print("[INFO] Duet Night Abyss helper started.")
        print("[INFO] Input backend: Windows SendInput (DirectX-compatible path).")
        if not self.controller.is_running_as_admin():
            print("[WARN] Not running as administrator. Some games may block input events.")

        if self._defence_routes_relevant_at_startup():
            self.route_mode = self.defence_service.prompt_route_mode()
            print(f"[INFO] Defence route mode: {self.route_mode.upper()}")
            self._route_mode_ready_logged = False

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

        print("[INFO] Switch to the game window. Starting in 3 seconds...")
        time.sleep(3)

        if self._defence_routes_relevant_at_startup() and self.route_mode is not None:
            if self.route_mode == "record":
                print("[INFO] Record mode ready. Press P to start recording and O to stop/save/exit.")
            else:
                print("[INFO] Playback mode ready. Route replay will auto-start after dungeon entry is detected, or press I to replay manually.")
            self._route_mode_ready_logged = True

        session = SessionState(session_start_ts=time.time())
        loot_state = LootState()
        defence_state = DefenceState(auto_replay_armed=(self.route_mode == "playback"), route_mode=self.route_mode or "disabled")
        record_state = RouteRecordingState(
            key_state={key: False for key in ROUTE_RECORD_KEYS},
            hotkey_state={
                str(self.config.get("defence_route_record_hotkey_start", "p")).lower(): False,
                str(self.config.get("defence_route_record_hotkey_stop", "o")).lower(): False,
                str(self.config.get("defence_route_replay_hotkey", "i")).lower(): False,
            },
        )

        while True:
            try:
                if self.route_mode is not None:
                    self.defence_service.process_hotkeys(record_state, defence_state, self.route_mode)
                    now = time.time()
                    self.route_manager.poll_recording(now, record_state)
                else:
                    now = time.time()

                if record_state.exit_requested:
                    print("[INFO] Recording finished. Exiting.")
                    break
                if record_state.active:
                    time.sleep(0.01)
                    continue
                if self.route_mode == "record":
                    time.sleep(0.01)
                    continue
                if not self.controller.is_game_window_foreground():
                    time.sleep(0.2)
                    continue

                now = time.time()
                active_profile = self.dungeon_detector.get_active_profile(self.capture)
                self._ensure_route_mode_for_profile(active_profile.key, defence_state)

                if now - session.last_result_check >= self.config["result_check_interval"]:
                    session.last_result_check = now
                    result_action = self.result_ui.check_and_click_result_ui(active_profile)
                    if result_action == "start_clicked":
                        self.controller.release_keys(ROUTE_RECORD_KEYS)
                        self.route_manager.reset_defence_state(
                            defence_state,
                            pending_replay_after_delay=(self.route_mode == "playback" and active_profile.key == "defence"),
                        )
                        session.runs_completed += 1
                        self._print_run_stats(session)
                        if target_runs > 0 and session.runs_completed >= target_runs:
                            self._print_session_summary(session)
                            break
                        continue

                if active_profile.key == "defence":
                    if now - defence_state.last_update_ts >= float(self.config.get("defence_check_interval", 0.22)):
                        defence_active = self.defence_service.update(now, defence_state)
                    else:
                        defence_active = self.defence_service.is_prephase_active(defence_state)
                    if defence_active:
                        time.sleep(0.02)
                        continue
                else:
                    self.controller.release_keys(ROUTE_RECORD_KEYS)
                    self.route_manager.reset_defence_state(defence_state, pending_replay_after_delay=False)

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
                print("[INFO] Script stopped by user.")
                break
