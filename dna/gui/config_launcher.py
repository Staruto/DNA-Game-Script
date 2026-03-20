from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict, Optional

from dna.settings import ALLOWED_MANUAL_DUNGEONS, normalize_runtime_settings


class _ConfigLauncher:
    def __init__(self, initial_config: Dict[str, Any]):
        self._initial = initial_config
        self.result: Optional[Dict[str, Any]] = None

        self.root = tk.Tk()
        self.root.title("DNA Launcher")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.mode_var = tk.StringVar(value=str(initial_config.get("dungeon_mode", "auto")))
        self.manual_var = tk.StringVar(value=str(initial_config.get("manual_dungeon", "defence")))
        self.target_runs_var = tk.StringVar(value=str(initial_config.get("target_runs", 0)))

        frame = ttk.Frame(self.root, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="Dungeon Mode").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.mode_combo = ttk.Combobox(
            frame,
            textvariable=self.mode_var,
            state="readonly",
            values=("auto", "manual"),
            width=16,
        )
        self.mode_combo.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)

        ttk.Label(frame, text="Manual Dungeon").grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.manual_combo = ttk.Combobox(
            frame,
            textvariable=self.manual_var,
            state="readonly",
            values=tuple(sorted(ALLOWED_MANUAL_DUNGEONS)),
            width=16,
        )
        self.manual_combo.grid(row=1, column=1, sticky="ew", pady=(0, 6))

        ttk.Label(frame, text="Target Runs (0 = infinite)").grid(row=2, column=0, sticky="w", pady=(0, 10))
        self.target_runs_entry = ttk.Entry(frame, textvariable=self.target_runs_var, width=18)
        self.target_runs_entry.grid(row=2, column=1, sticky="ew", pady=(0, 10))

        button_row = ttk.Frame(frame)
        button_row.grid(row=3, column=0, columnspan=2, sticky="e")
        ttk.Button(button_row, text="Cancel", command=self._on_cancel).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_row, text="Start", command=self._on_start).grid(row=0, column=1)

        self._on_mode_changed()

    def _on_mode_changed(self, _event=None):
        mode = self.mode_var.get().strip().lower()
        if mode == "manual":
            self.manual_combo.configure(state="readonly")
        else:
            self.manual_combo.configure(state="disabled")

    def _on_start(self):
        candidate = {
            "dungeon_mode": self.mode_var.get().strip().lower(),
            "manual_dungeon": self.manual_var.get().strip().lower(),
            "target_runs": self.target_runs_var.get().strip(),
        }
        normalized = normalize_runtime_settings(candidate, self._initial)

        # Keep manual dungeon untouched while auto mode is selected; runtime fallback still has a valid value.
        if candidate["dungeon_mode"] == "manual" and normalized["manual_dungeon"] not in ALLOWED_MANUAL_DUNGEONS:
            messagebox.showerror("Invalid Setting", "manual_dungeon must be defence or expulsion.")
            return

        try:
            int(candidate["target_runs"])
        except ValueError:
            messagebox.showerror("Invalid Setting", "target_runs must be a non-negative integer.")
            return

        self.result = normalized
        self.root.destroy()

    def _on_cancel(self):
        self.result = None
        self.root.destroy()


def open_config_launcher(initial_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    launcher = _ConfigLauncher(initial_config)
    launcher.root.mainloop()
    return launcher.result
