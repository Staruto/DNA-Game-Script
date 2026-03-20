from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Dict, Optional

from dna.config import defence_route_path, get_default_config, template_path
from dna.defence.variant_store import load_variants, save_variants
from dna.gui.runner import AppRunner
from dna.settings import ALLOWED_MANUAL_DUNGEONS, normalize_runtime_settings, save_settings_overrides

MAX_LOG_LINES = 2000


class PersistentLauncher:
    def __init__(self, initial_config: Dict[str, Any]):
        self._initial = dict(initial_config)
        self._runner = AppRunner()
        self._closing = False
        self._log_lines = 0
        self._last_detected_variant = ""

        self._variants = load_variants(initial_config)
        initial_variant = str(initial_config.get("manual_defence_variant", "")).strip()
        if initial_variant not in self._variants and self._variants:
            initial_variant = next(iter(self._variants))
        self._active_variant_key = initial_variant

        self.root = tk.Tk()
        self.root.title("DNA Launcher")
        self.root.geometry("980x700")
        self.root.minsize(900, 580)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.mode_var = tk.StringVar(value=str(initial_config.get("dungeon_mode", "auto")))
        self.manual_var = tk.StringVar(value=str(initial_config.get("manual_dungeon", "defence")))
        self.target_runs_var = tk.StringVar(value=str(initial_config.get("target_runs", 0)))
        self.compact_log_var = tk.BooleanVar(value=bool(initial_config.get("compact_log_enabled", True)))
        self.status_var = tk.StringVar(value="Idle")

        self.variant_name_var = tk.StringVar(value="")
        self.auto_detect_defence_var = tk.BooleanVar(value=bool(initial_config.get("auto_detect_defence", True)))
        self.manual_variant_var = tk.StringVar(value=self._active_variant_key)
        self.route_mode_var = tk.StringVar(value=str(initial_config.get("defence_route_mode_override", "auto")))

        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)

        style = ttk.Style(self.root)
        style.configure("Launcher.TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 11, "bold"))
        self.notebook = ttk.Notebook(container, style="Launcher.TNotebook")
        self.notebook.pack(fill="x")

        general_tab = ttk.Frame(self.notebook, padding=10)
        expulsion_tab = ttk.Frame(self.notebook, padding=10)
        defence_tab = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(general_tab, text="General")
        self.notebook.add(expulsion_tab, text="Expulsion")
        self.notebook.add(defence_tab, text="Defence")

        ttk.Label(general_tab, text="Dungeon Mode").grid(row=0, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
        self.mode_combo = ttk.Combobox(general_tab, textvariable=self.mode_var, state="readonly", values=("auto", "manual"), width=16)
        self.mode_combo.grid(row=0, column=1, sticky="w", pady=(0, 6))
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)

        ttk.Label(general_tab, text="Manual Dungeon").grid(row=1, column=0, sticky="w", pady=(0, 6), padx=(0, 10))
        self.manual_combo = ttk.Combobox(
            general_tab,
            textvariable=self.manual_var,
            state="readonly",
            values=tuple(sorted(ALLOWED_MANUAL_DUNGEONS)),
            width=16,
        )
        self.manual_combo.grid(row=1, column=1, sticky="w", pady=(0, 6))
        self.manual_combo.bind("<<ComboboxSelected>>", self._on_manual_dungeon_changed)

        ttk.Label(general_tab, text="Target Runs (0 = infinite)").grid(row=2, column=0, sticky="w", padx=(0, 10))
        self.target_entry = ttk.Entry(general_tab, textvariable=self.target_runs_var, width=18)
        self.target_entry.grid(row=2, column=1, sticky="w")

        self.compact_log_check = ttk.Checkbutton(general_tab, text="Compact log mode", variable=self.compact_log_var)
        self.compact_log_check.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Label(expulsion_tab, text="No extra settings for expulsion yet.").pack(anchor="w")

        defence_top = ttk.Frame(defence_tab)
        defence_mode_frame = ttk.LabelFrame(defence_tab, text="Defence Mode", padding=8)
        defence_mode_frame.pack(fill="x", pady=(0, 8))

        self.auto_detect_check = ttk.Checkbutton(
            defence_mode_frame,
            text="Auto detect variant by entry screen",
            variable=self.auto_detect_defence_var,
            command=self._on_auto_detect_changed,
        )
        self.auto_detect_check.pack(anchor="w")

        self.defence_mode_hint_label = ttk.Label(defence_mode_frame, text="")
        self.defence_mode_hint_label.pack(anchor="w", pady=(4, 0))

        defence_top.pack(fill="x")

        list_frame = ttk.LabelFrame(defence_top, text="Defence Variants", padding=8)
        list_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.variant_list = tk.Listbox(list_frame, height=8)
        self.variant_list.pack(side="left", fill="both", expand=True)
        self.variant_list.bind("<<ListboxSelect>>", self._on_variant_selected)
        variant_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.variant_list.yview)
        variant_scroll.pack(side="right", fill="y")
        self.variant_list.configure(yscrollcommand=variant_scroll.set)

        form_frame = ttk.LabelFrame(defence_top, text="Variant Details", padding=8)
        form_frame.pack(side="left", fill="both", expand=True)

        ttk.Label(form_frame, text="Variant Name").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 6))
        ttk.Entry(form_frame, textvariable=self.variant_name_var, width=30).grid(row=0, column=1, sticky="w", pady=(0, 6))

        ttk.Label(form_frame, text="Route Mode").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.route_mode_combo = ttk.Combobox(
            form_frame,
            textvariable=self.route_mode_var,
            state="readonly",
            values=("auto", "playback", "record"),
            width=30,
        )
        self.route_mode_combo.grid(row=1, column=1, sticky="w")
        self.route_mode_combo.bind("<<ComboboxSelected>>", self._on_route_mode_changed)

        buttons_frame = ttk.Frame(form_frame)
        buttons_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Button(buttons_frame, text="Save Variant", command=self._save_variant).pack(side="left")
        ttk.Button(buttons_frame, text="Delete", command=self._delete_variant).pack(side="left", padx=(6, 0))
        self.set_active_btn = ttk.Button(buttons_frame, text="Set Active", command=self._set_active_variant)
        self.set_active_btn.pack(side="left", padx=(6, 0))
        ttk.Button(buttons_frame, text="Refresh Checks", command=self._refresh_checks).pack(side="left", padx=(6, 0))

        self.variant_hint_label = ttk.Label(defence_tab, text="")
        self.variant_hint_label.pack(anchor="w", pady=(6, 0))

        control_frame = ttk.Frame(container)
        control_frame.pack(fill="x", pady=(10, 8))

        self.start_stop_btn = ttk.Button(control_frame, text="Start", width=10, command=self._on_start_stop)
        self.start_stop_btn.pack(side="left")

        self.clear_logs_btn = ttk.Button(control_frame, text="Clear Logs", command=self._clear_logs)
        self.clear_logs_btn.pack(side="left", padx=(8, 0))

        self.status_label = ttk.Label(control_frame, textvariable=self.status_var, width=30, anchor="w")
        self.status_label.pack(side="left", padx=(12, 0))

        logs_frame = ttk.LabelFrame(container, text="Logs", padding=8)
        logs_frame.pack(fill="both", expand=True)

        self.log_text = scrolledtext.ScrolledText(logs_frame, wrap="word", state="disabled", font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(background="#ffffff", foreground="#111111", insertbackground="#111111")
        self.log_text.tag_configure("info", foreground="#111111")
        self.log_text.tag_configure("warn", foreground="#8a5a00")
        self.log_text.tag_configure("error", foreground="#9f1239")
        self.log_text.tag_configure("summary", foreground="#0f5132")

        self._last_selected_dungeon = str(initial_config.get("manual_dungeon", "defence"))
        self._last_defence_success = 0

        self._refresh_variant_list(select_key=self._active_variant_key)
        self._append_log("[INFO] Launcher ready. Configure and click Start.", tag="info")
        self._on_mode_changed()
        self._on_manual_dungeon_changed()
        self._on_auto_detect_changed()
        self._poll_events()

    def _append_log(self, line: str, tag: str = "info"):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{line}\n", tag)
        self.log_text.see("end")
        self._log_lines += 1
        if self._log_lines > MAX_LOG_LINES:
            self.log_text.delete("1.0", "2.0")
            self._log_lines -= 1
        self.log_text.configure(state="disabled")

    def _clear_logs(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._log_lines = 0

    def _normalize_variant_key(self, text: str) -> str:
        safe = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in text.strip().lower())
        return safe.strip("_")

    def _selected_variant_key_from_list(self) -> Optional[str]:
        selected = self.variant_list.curselection()
        if not selected:
            return None
        keys = sorted(self._variants.keys())
        index = int(selected[0])
        if index < 0 or index >= len(keys):
            return None
        return keys[index]

    def _refresh_variant_list(self, select_key: Optional[str] = None):
        self.variant_list.delete(0, "end")
        keys = sorted(self._variants.keys())
        auto_mode = self.auto_detect_defence_var.get()

        for index, key in enumerate(keys):
            display_name = str(self._variants.get(key, {}).get("display_name", key))
            marker = ">>" if (not auto_mode and key == self._active_variant_key) else "  "
            self.variant_list.insert("end", f"{marker} {key} - {display_name}")
            if not auto_mode and key == self._active_variant_key:
                try:
                    self.variant_list.itemconfig(index, foreground="#0b5ed7", background="#e8f1ff", font=("Segoe UI", 10, "bold"))
                except tk.TclError:
                    pass

        if not keys:
            self.variant_name_var.set("")
            self.variant_hint_label.configure(text="No variants configured yet.")
            return

        if not select_key or select_key not in self._variants:
            select_key = keys[0]

        index = keys.index(select_key)
        self.variant_list.selection_clear(0, "end")
        self.variant_list.selection_set(index)
        self.variant_list.activate(index)
        self._fill_variant_form(select_key)

    def _fill_variant_form(self, key: Optional[str]):
        if not key or key not in self._variants:
            self.variant_name_var.set("")
            self.variant_hint_label.configure(text="")
            return

        item = self._variants[key]
        self.variant_name_var.set(str(item.get("display_name", key)))
        self._refresh_checks()

    def _refresh_checks(self):
        key = self._selected_variant_key_from_list() or self._active_variant_key
        if not key or key not in self._variants:
            self.variant_hint_label.configure(text="")
            return

        item = self._variants[key]
        template_name = str(item.get("entry_template", "")).strip()
        route_name = str(item.get("route_name", key)).strip() or key

        template_exists = bool(template_name and template_path(template_name) is not None)
        route_path = defence_route_path(route_name)
        route_exists = route_path.exists()

        selected_mode = self.route_mode_var.get().strip().lower() or "auto"
        if selected_mode == "auto":
            effective_mode = "playback" if route_exists else "record"
        else:
            effective_mode = selected_mode

        self.variant_hint_label.configure(
            text=(
                f"Variant={key} | Template: {'OK' if template_exists else 'Missing'} ({template_name or 'n/a'})"
                f" | Route: {'OK' if route_exists else 'Missing'} ({route_path.name})"
                f" | Effective mode: {effective_mode}"
            )
        )

    def _save_variant(self):
        raw_name = self.variant_name_var.get().strip()
        key = self._normalize_variant_key(raw_name)
        if not key:
            messagebox.showerror("Invalid Variant", "Variant name is required.")
            return

        entry_template = f"{key}.png"
        route_name = key

        if template_path(entry_template) is None:
            proceed = messagebox.askyesno(
                "Template Missing",
                f"Expected template '{entry_template}' was not found. Save anyway?",
            )
            if not proceed:
                return

        self._variants[key] = {
            "display_name": raw_name or key,
            "entry_template": entry_template,
            "route_name": route_name,
        }
        if not self._active_variant_key:
            self._active_variant_key = key
        save_variants(self._variants)
        self._append_log(f"[INFO] Defence variant saved: {key}", tag="info")
        self._refresh_variant_list(select_key=key)

    def _delete_variant(self):
        key = self._selected_variant_key_from_list() or self.manual_variant_var.get().strip()
        if not key or key not in self._variants:
            messagebox.showerror("Delete Variant", "Please select a valid variant first.")
            return

        if not messagebox.askyesno("Delete Variant", f"Delete defence variant '{key}'?"):
            return

        del self._variants[key]
        if self._active_variant_key == key:
            self._active_variant_key = next(iter(self._variants), "")
        save_variants(self._variants)
        self._append_log(f"[WARN] Defence variant deleted: {key}", tag="warn")
        self._refresh_variant_list(select_key=self._active_variant_key)

    def _set_active_variant(self):
        if self.auto_detect_defence_var.get():
            messagebox.showinfo("Auto Detect Enabled", "Set Active is disabled while auto detect mode is enabled.")
            return

        key = self._selected_variant_key_from_list()
        if not key or key not in self._variants:
            messagebox.showerror("Set Active Variant", "Please select a valid variant first.")
            return

        self._active_variant_key = key
        self._append_log(f"[INFO] Active defence variant: {key}", tag="info")
        self._refresh_variant_list(select_key=key)

    def _on_variant_selected(self, _event=None):
        key = self._selected_variant_key_from_list()
        self._fill_variant_form(key)

    def _on_auto_detect_changed(self):
        if self.auto_detect_defence_var.get():
            self.set_active_btn.configure(state="disabled")
            self.defence_mode_hint_label.configure(
                text="Auto mode: variant is detected from entry screen. Set Active is disabled."
            )
        else:
            self.set_active_btn.configure(state="normal")
            self.defence_mode_hint_label.configure(
                text="Manual mode: select a variant on the left, then click Set Active."
            )
        self._refresh_variant_list(select_key=self._selected_variant_key_from_list() or self._active_variant_key)
        self._refresh_checks()

    def _on_manual_variant_changed(self, _event=None):
        selected = self.manual_variant_var.get().strip()
        if selected in self._variants:
            self._active_variant_key = selected
            self._refresh_variant_list(select_key=selected)
            self._refresh_checks()

    def _on_route_mode_changed(self, _event=None):
        self._refresh_checks()

    def _on_mode_changed(self, _event=None):
        mode = self.mode_var.get().strip().lower()
        if mode == "manual":
            self.manual_combo.configure(state="readonly")
        else:
            self.manual_combo.configure(state="disabled")

    def _on_manual_dungeon_changed(self, _event=None):
        manual = self.manual_var.get().strip().lower()
        if manual == "defence":
            self.notebook.select(2)
        elif manual == "expulsion":
            self.notebook.select(1)

    def _collect_settings(self) -> Optional[Dict[str, Any]]:
        candidate = {
            "dungeon_mode": self.mode_var.get().strip().lower(),
            "manual_dungeon": self.manual_var.get().strip().lower(),
            "target_runs": self.target_runs_var.get().strip(),
            "compact_log_enabled": self.compact_log_var.get(),
            "auto_detect_defence": self.auto_detect_defence_var.get(),
            "manual_defence_variant": self._active_variant_key,
            "defence_route_mode_override": self.route_mode_var.get().strip().lower(),
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
        if not normalized["auto_detect_defence"] and not self._active_variant_key:
            messagebox.showerror("Invalid Defence Setting", "Please select a manual defence variant.")
            return None
        return normalized

    def _on_start_stop(self):
        if self._runner.is_running():
            self.status_var.set("Stopping")
            self._append_log("[INFO] Stop requested. Waiting for safe shutdown...")
            self._runner.request_stop()
            return

        selected = self._collect_settings()
        if selected is None:
            return

        if selected["manual_dungeon"] == "defence" and not self._variants:
            messagebox.showerror("Missing Defence Variant", "Please create at least one defence variant before starting defence mode.")
            return

        runtime_config = get_default_config()
        runtime_config.update(selected)
        runtime_config["defence_variants"] = dict(self._variants)
        runtime_config["manual_defence_variant"] = self._active_variant_key
        runtime_config["auto_detect_defence"] = bool(selected["auto_detect_defence"])
        runtime_config["defence_route_mode_override"] = selected["defence_route_mode_override"]

        save_settings_overrides(selected, get_default_config())

        if not self._runner.start(runtime_config):
            self._append_log("[WARN] Run is already active.", tag="warn")
            return

        self._last_selected_dungeon = selected["manual_dungeon"]
        self._last_defence_success = 0
        self._last_detected_variant = ""
        if not self.compact_log_var.get():
            self._append_log("[INFO] Run started.", tag="info")
            if selected["dungeon_mode"] == "manual":
                self._append_log(f"[INFO] Target dungeon: {selected['manual_dungeon']} (manual mode)", tag="info")
            else:
                self._append_log("[INFO] Target dungeon: auto detect mode", tag="info")
        self.status_var.set("Running")
        self.start_stop_btn.configure(text="Stop")

    def _compact_tag_for_message(self, message: str) -> str:
        if "[ERROR]" in message:
            return "error"
        if "[WARN]" in message:
            return "warn"
        return "info"

    def _maybe_render_compact_log(self, message: str) -> bool:
        if "Defence entry detected" in message:
            self._append_log("[EVENT] Entered defence dungeon.", tag="info")
            return True
        if "Start button detected" in message or "Pressing 'R' for Challenge Again" in message:
            self._append_log("[EVENT] Dungeon restart triggered.", tag="info")
            return True
        if "[WARN]" in message or "[ERROR]" in message:
            self._append_log(message, tag=self._compact_tag_for_message(message))
            return True
        return False

    def _render_session_summary(self, payload: Dict[str, Any]):
        runs = int(payload.get("runs_completed", 0))
        elapsed = float(payload.get("elapsed_sec", 0.0))
        defence_success = int(payload.get("defence_success_runs", self._last_defence_success))
        elapsed_text = f"{int(elapsed)}s"
        is_defence = self._last_selected_dungeon == "defence"

        if is_defence:
            rate = (defence_success / runs * 100.0) if runs > 0 else 0.0
            avg_success = (elapsed / defence_success) if defence_success > 0 else None
            avg_success_text = f"{avg_success:.1f}s" if avg_success is not None else "N/A"
            self._append_log(
                f"[SUMMARY] Defence: success={defence_success} total={runs} success_rate={rate:.1f}% total_time={elapsed_text} avg_success={avg_success_text}",
                tag="summary",
            )
            return

        avg = (elapsed / runs) if runs > 0 else 0.0
        self._append_log(f"[SUMMARY] Runs={runs} total_time={elapsed_text} avg_per_run={avg:.1f}s", tag="summary")

    def _target_object_text(self, mode: str, manual: str) -> str:
        if mode != "manual":
            return "auto"
        if manual == "defence":
            if self.auto_detect_defence_var.get():
                return "defence/auto"
            variant = self._active_variant_key.strip()
            return f"defence/{variant}" if variant else "defence"
        return manual

    def _handle_event(self, event: dict):
        event_type = event.get("type")
        if event_type == "log":
            message = str(event.get("message", "")).rstrip()
            if message:
                if self.compact_log_var.get():
                    self._maybe_render_compact_log(message)
                else:
                    self._append_log(message, tag=self._compact_tag_for_message(message))
            return

        if event_type == "event":
            name = event.get("name")
            payload = event.get("payload") or {}
            if name == "session_started":
                mode = str(payload.get("mode", "manual"))
                manual = str(payload.get("manual_dungeon", self._last_selected_dungeon))
                target = int(payload.get("target_runs", 0))
                self._last_selected_dungeon = manual
                if self.compact_log_var.get():
                    mode_desc = f"manual:{manual}" if mode == "manual" else "auto"
                    target_desc = "unlimited" if target == 0 else str(target)
                    target_obj = self._target_object_text(mode, manual)
                    self._append_log(f"[START] target={target_obj} mode={mode_desc} target_runs={target_desc}", tag="info")
                else:
                    self._append_log(f"[INFO] Session started. mode={mode} manual={manual} target_runs={target}", tag="info")
            elif name == "run_completed":
                if self.compact_log_var.get():
                    run_index = int(payload.get("runs_completed", 0))
                    self._append_log(f"[EVENT] Run #{run_index} completed. Restarting dungeon.", tag="info")
            elif name == "run_restarted":
                if self.compact_log_var.get():
                    self._append_log("[EVENT] Dungeon restart triggered.", tag="info")
            elif name == "dungeon_entered":
                if self.compact_log_var.get():
                    dungeon = str(payload.get("dungeon_type", "unknown"))
                    variant = str(payload.get("variant", "")).strip()
                    if dungeon == "defence" and not variant:
                        variant = self._active_variant_key.strip()
                    if variant:
                        self._last_detected_variant = variant
                        self._append_log(f"[EVENT] Entered {dungeon} ({variant}).", tag="info")
                    else:
                        self._append_log(f"[EVENT] Entered {dungeon}.", tag="info")
            elif name == "session_finished":
                self._render_session_summary(payload)
            elif name == "defence_success":
                self._last_defence_success = int(payload.get("defence_success_runs", 0))
                if not self.compact_log_var.get():
                    self._append_log(f"[STATS] Defence success runs: {self._last_defence_success}", tag="info")
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
            self.status_var.set("Stopping")
            self._append_log("[INFO] Window close requested. Stopping current run first...", tag="warn")
            self._runner.request_stop()
            return
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def run_persistent_launcher(initial_config: Dict[str, Any]):
    app = PersistentLauncher(initial_config)
    app.run()
