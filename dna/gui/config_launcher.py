from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Dict, Optional

from dna.config import get_default_config
from dna.gui.runner import AppRunner
from dna.settings import ALLOWED_MANUAL_DUNGEONS, normalize_runtime_settings, save_settings_overrides


class PersistentLauncher:
    def __init__(self, initial_config: Dict[str, Any]):
        self._initial = dict(initial_config)
        self._runner = AppRunner()
        self._closing = False

        self.root = tk.Tk()
        self.root.title("DNA Launcher")
        self.root.geometry("760x520")
        self.root.minsize(700, 460)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.mode_var = tk.StringVar(value=str(initial_config.get("dungeon_mode", "auto")))
        self.manual_var = tk.StringVar(value=str(initial_config.get("manual_dungeon", "defence")))
        self.target_runs_var = tk.StringVar(value=str(initial_config.get("target_runs", 0)))
        self.status_var = tk.StringVar(value="Idle")

        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)

        settings_frame = ttk.LabelFrame(container, text="Runtime Settings", padding=10)
        settings_frame.pack(fill="x")

        ttk.Label(settings_frame, text="Dungeon Mode").grid(row=0, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
        self.mode_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.mode_var,
            state="readonly",
            values=("auto", "manual"),
            width=16,
        )
        self.mode_combo.grid(row=0, column=1, sticky="w", pady=(0, 6))
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)

        ttk.Label(settings_frame, text="Manual Dungeon").grid(row=1, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
        self.manual_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.manual_var,
            state="readonly",
            values=tuple(sorted(ALLOWED_MANUAL_DUNGEONS)),
            width=16,
        )
        self.manual_combo.grid(row=1, column=1, sticky="w", pady=(0, 6))

        ttk.Label(settings_frame, text="Target Runs (0 = infinite)").grid(row=2, column=0, sticky="w", padx=(0, 10))
        self.target_entry = ttk.Entry(settings_frame, textvariable=self.target_runs_var, width=18)
        self.target_entry.grid(row=2, column=1, sticky="w")

        control_frame = ttk.Frame(container)
        control_frame.pack(fill="x", pady=(10, 8))

        self.start_stop_btn = ttk.Button(control_frame, text="Start", command=self._on_start_stop)
        self.start_stop_btn.pack(side="left")

        self.status_label = ttk.Label(control_frame, textvariable=self.status_var)
        self.status_label.pack(side="left", padx=(12, 0))

        logs_frame = ttk.LabelFrame(container, text="Logs", padding=8)
        logs_frame.pack(fill="both", expand=True)

        self.log_text = scrolledtext.ScrolledText(logs_frame, wrap="word", state="disabled", font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)

        self._append_log("[INFO] Launcher ready. Configure and click Start.")
        self._on_mode_changed()
        self._poll_events()

    def _append_log(self, line: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{line}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_mode_changed(self, _event=None):
        mode = self.mode_var.get().strip().lower()
        if mode == "manual":
            self.manual_combo.configure(state="readonly")
        else:
            self.manual_combo.configure(state="disabled")

    def _collect_settings(self) -> Optional[Dict[str, Any]]:
        candidate = {
            "dungeon_mode": self.mode_var.get().strip().lower(),
            "manual_dungeon": self.manual_var.get().strip().lower(),
            "target_runs": self.target_runs_var.get().strip(),
        }

        try:
            int(candidate["target_runs"])
        except ValueError:
            messagebox.showerror("Invalid Setting", "target_runs must be a non-negative integer.")
            return None

        normalized = normalize_runtime_settings(candidate, self._initial)
        if candidate["dungeon_mode"] == "manual" and normalized["manual_dungeon"] not in ALLOWED_MANUAL_DUNGEONS:
            messagebox.showerror("Invalid Setting", "manual_dungeon must be defence or expulsion.")
            return None
        return normalized

    def _on_start_stop(self):
        if self._runner.is_running():
            self.status_var.set("Stopping safely...")
            self._append_log("[INFO] Stop requested. Waiting for safe shutdown...")
            self._runner.request_stop()
            return

        selected = self._collect_settings()
        if selected is None:
            return

        runtime_config = get_default_config()
        runtime_config.update(selected)
        save_settings_overrides(selected, get_default_config())

        if not self._runner.start(runtime_config):
            self._append_log("[WARN] Run is already active.")
            return

        self._append_log("[INFO] Run started.")
        if selected["dungeon_mode"] == "manual":
            self._append_log(f"[INFO] Target dungeon: {selected['manual_dungeon']} (manual mode)")
        else:
            self._append_log("[INFO] Target dungeon: auto detect mode")
        self.status_var.set("Running")
        self.start_stop_btn.configure(text="Stop")

    def _handle_event(self, event: dict):
        event_type = event.get("type")
        if event_type == "log":
            message = str(event.get("message", "")).rstrip()
            if message:
                self._append_log(message)
            return

        if event_type == "event":
            name = event.get("name")
            payload = event.get("payload") or {}
            if name == "defence_success":
                value = int(payload.get("defence_success_runs", 0))
                self._append_log(f"[STATS] Defence success runs: {value}")
            elif name == "session_finished":
                runs = int(payload.get("runs_completed", 0))
                elapsed = float(payload.get("elapsed_sec", 0.0))
                defence_success = int(payload.get("defence_success_runs", 0))
                self._append_log(f"[SUMMARY] Total runs: {runs} | Elapsed: {int(elapsed)}s")
                if defence_success > 0:
                    self._append_log(f"[SUMMARY] Defence success runs: {defence_success}")
            return

        if event_type == "state":
            state = event.get("state")
            if state == "running":
                self.status_var.set("Running")
                self.start_stop_btn.configure(text="Stop")
            elif state == "stopped":
                self.status_var.set("Idle")
                self.start_stop_btn.configure(text="Start")
                if self._closing:
                    self.root.destroy()

    def _poll_events(self):
        for event in self._runner.drain_events():
            self._handle_event(event)
        self.root.after(120, self._poll_events)

    def _on_close(self):
        if self._runner.is_running():
            self._closing = True
            self.status_var.set("Stopping safely before exit...")
            self._append_log("[INFO] Window close requested. Stopping current run first...")
            self._runner.request_stop()
            return
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def run_persistent_launcher(initial_config: Dict[str, Any]):
    app = PersistentLauncher(initial_config)
    app.run()
