from __future__ import annotations

import json
import shutil
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from typing import Any, Dict, Optional

from dna.config import ASSETS_DIR, ROUTES_DIR, defence_route_path, get_default_config, template_path
from dna.defence.route_stats import get_rate, load_route_stats, record_attempt, record_success, save_route_stats
from dna.defence.variant_store import load_variants, save_variants
from dna.gui.runner import AppRunner
from dna.settings import ALLOWED_MANUAL_DUNGEONS, normalize_runtime_settings, save_settings_overrides

MAX_LOG_LINES = 2000
PREVIEW_MAX_W = 360
PREVIEW_MAX_H = 210


class PersistentLauncher:
    def __init__(self, initial_config: Dict[str, Any]):
        self._initial = dict(initial_config)
        self._runner = AppRunner()
        self._closing = False
        self._log_lines = 0
        self._last_detected_variant = ""
        self._image_preview_handle = None
        self._route_stats = load_route_stats()
        self._suppress_variant_name_trace = False

        self._variants = load_variants(initial_config)
        initial_variant = str(initial_config.get("manual_defence_variant", "")).strip()
        if initial_variant not in self._variants and self._variants:
            initial_variant = next(iter(self._variants))
        self._active_variant_key = initial_variant

        self.root = tk.Tk()
        self.root.title("DNA Launcher")
        self.root.geometry("1080x820")
        self.root.minsize(1080, 820)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._scroll_canvas = tk.Canvas(self.root, highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side="right", fill="y")
        self._scroll_canvas.pack(side="left", fill="both", expand=True)

        self.mode_var = tk.StringVar(value=str(initial_config.get("dungeon_mode", "auto")))
        self.manual_var = tk.StringVar(value=str(initial_config.get("manual_dungeon", "defence")))
        self.target_runs_var = tk.StringVar(value=str(initial_config.get("target_runs", 0)))
        self.compact_log_var = tk.BooleanVar(value=bool(initial_config.get("compact_log_enabled", True)))
        self.status_var = tk.StringVar(value="Idle")

        self.variant_name_var = tk.StringVar(value="")
        self.variant_name_var.trace_add("write", self._on_variant_name_changed)
        self.auto_detect_defence_var = tk.BooleanVar(value=bool(initial_config.get("auto_detect_defence", True)))
        self.preview_enabled_var = tk.BooleanVar(value=bool(initial_config.get("defence_preview_enabled", True)))
        self.route_mode_var = tk.StringVar(value=str(initial_config.get("defence_route_mode_override", "auto")))

        self.resource_status_var = tk.StringVar(value="No variant selected.")

        container = ttk.Frame(self._scroll_canvas, padding=12)
        self._canvas_window_id = self._scroll_canvas.create_window((0, 0), window=container, anchor="nw")
        container.bind("<Configure>", self._on_container_configure)
        self._scroll_canvas.bind("<Configure>", self._on_canvas_configure)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

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

        defence_mode_frame = ttk.LabelFrame(defence_tab, text="Defence Mode", padding=8)
        defence_mode_frame.pack(fill="x", pady=(0, 8))

        self.auto_detect_check = ttk.Checkbutton(
            defence_mode_frame,
            text="Auto detect variant by entry screen",
            variable=self.auto_detect_defence_var,
            command=self._on_auto_detect_changed,
        )
        self.auto_detect_check.pack(anchor="w")

        self.preview_toggle_check = ttk.Checkbutton(
            defence_mode_frame,
            text="Enable resource preview",
            variable=self.preview_enabled_var,
            command=self._on_preview_toggle_changed,
        )
        self.preview_toggle_check.pack(anchor="w", pady=(4, 0))

        self.defence_mode_hint_label = ttk.Label(defence_mode_frame, text="")
        self.defence_mode_hint_label.pack(anchor="w", pady=(4, 0))

        defence_top = ttk.Frame(defence_tab)
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
        ttk.Entry(form_frame, textvariable=self.variant_name_var, width=32).grid(row=0, column=1, sticky="w", pady=(0, 6))
        self.save_name_btn = ttk.Button(form_frame, text="Save Changes", command=self._save_variant)
        self.save_name_btn.grid(row=0, column=2, sticky="w", padx=(8, 0), pady=(0, 6))
        self.save_name_btn.grid_remove()

        ttk.Label(form_frame, text="Route Mode").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.route_mode_combo = ttk.Combobox(
            form_frame,
            textvariable=self.route_mode_var,
            state="readonly",
            values=("auto", "playback", "record"),
            width=32,
        )
        self.route_mode_combo.grid(row=1, column=1, sticky="w")
        self.route_mode_combo.bind("<<ComboboxSelected>>", self._on_route_mode_changed)

        buttons_frame = ttk.Frame(form_frame)
        buttons_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.set_active_btn = ttk.Button(buttons_frame, text="Set Active", command=self._set_active_variant)
        self.set_active_btn.pack(side="left")
        ttk.Button(buttons_frame, text="Refresh Checks", command=self._refresh_checks).pack(side="left", padx=(6, 0))

        variant_actions = ttk.Frame(defence_tab)
        variant_actions.pack(fill="x", pady=(8, 0))
        ttk.Button(variant_actions, text="Add", command=self._add_variant).pack(side="left")
        ttk.Button(variant_actions, text="Delete", command=self._delete_variant).pack(side="left", padx=(6, 0))

        self.variant_hint_label = ttk.Label(defence_tab, text="")
        self.variant_hint_label.pack(anchor="w", pady=(6, 0))

        resource_frame = ttk.LabelFrame(defence_tab, text="Resource Management", padding=8)
        resource_frame.pack(fill="x", pady=(8, 0))

        row1 = ttk.Frame(resource_frame)
        row1.pack(fill="x")
        ttk.Button(row1, text="Replace Image", command=self._replace_image).pack(side="left")
        ttk.Button(row1, text="Delete Image", command=self._delete_image).pack(side="left", padx=(6, 0))
        ttk.Button(row1, text="Open Assets Folder", command=self._open_assets_folder).pack(side="left", padx=(12, 0))

        row2 = ttk.Frame(resource_frame)
        row2.pack(fill="x", pady=(6, 0))
        ttk.Button(row2, text="Replace Route", command=self._replace_route).pack(side="left")
        ttk.Button(row2, text="Delete Route", command=self._delete_route).pack(side="left", padx=(6, 0))
        ttk.Button(row2, text="Open Routes Folder", command=self._open_routes_folder).pack(side="left", padx=(12, 0))

        ttk.Label(resource_frame, textvariable=self.resource_status_var).pack(anchor="w", pady=(8, 0))

        preview_frame = ttk.Frame(resource_frame)
        preview_frame.pack(fill="x", pady=(6, 0))

        image_box = ttk.LabelFrame(preview_frame, text="Image Preview", padding=6)
        image_box.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.image_preview_label = ttk.Label(image_box, text="No image loaded.")
        self.image_preview_label.pack(fill="both", expand=True)

        route_box = ttk.LabelFrame(preview_frame, text="Route Preview", padding=6)
        route_box.pack(side="left", fill="both", expand=True)
        self.route_preview_text = scrolledtext.ScrolledText(route_box, height=8, wrap="word", state="disabled", font=("Consolas", 9))
        self.route_preview_text.pack(fill="both", expand=True)

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

        self.log_text = scrolledtext.ScrolledText(logs_frame, height=12, wrap="word", state="disabled", font=("Consolas", 10))
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

    def _on_container_configure(self, _event=None):
        bbox = self._scroll_canvas.bbox("all")
        if bbox is not None:
            self._scroll_canvas.configure(scrollregion=bbox)

    def _on_canvas_configure(self, event):
        self._scroll_canvas.itemconfigure(self._canvas_window_id, width=event.width)

    def _on_mousewheel(self, event):
        if not self._scroll_canvas.winfo_exists():
            return
        delta = int(-event.delta / 120) if event.delta else 0
        if delta != 0:
            self._scroll_canvas.yview_scroll(delta, "units")

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

    def _set_route_preview_text(self, content: str):
        self.route_preview_text.configure(state="normal")
        self.route_preview_text.delete("1.0", "end")
        self.route_preview_text.insert("1.0", content)
        self.route_preview_text.configure(state="disabled")

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

    def _current_variant_key(self) -> Optional[str]:
        return self._selected_variant_key_from_list() or (self._active_variant_key if self._active_variant_key in self._variants else None)

    def _variant_paths(self, key: str) -> tuple[str, Path, Optional[Path]]:
        item = self._variants.get(key, {})
        template_name = str(item.get("entry_template", "")).strip() or f"{key}.png"
        route_name = str(item.get("route_name", key)).strip() or key
        route_path = defence_route_path(route_name)
        template_file = template_path(template_name)
        return template_name, route_path, template_file

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
            self.resource_status_var.set("No variant selected.")
            self.image_preview_label.configure(text="No image loaded.", image="")
            self._set_route_preview_text("")
            self.save_name_btn.grid_remove()
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
        self._suppress_variant_name_trace = True
        self.variant_name_var.set(str(item.get("display_name", key)))
        self._suppress_variant_name_trace = False
        self._refresh_checks()
        self._refresh_previews()
        self._update_save_name_visibility()

    def _on_variant_name_changed(self, *_args):
        if self._suppress_variant_name_trace:
            return
        self._update_save_name_visibility()

    def _update_save_name_visibility(self):
        key = self._current_variant_key()
        if not key or key not in self._variants:
            self.save_name_btn.grid_remove()
            return
        current = str(self._variants[key].get("display_name", key)).strip()
        entered = self.variant_name_var.get().strip()
        if entered and entered != current:
            self.save_name_btn.grid()
        else:
            self.save_name_btn.grid_remove()

    def _refresh_previews(self):
        if not self.preview_enabled_var.get():
            self.image_preview_label.configure(text="Preview disabled.", image="")
            self._image_preview_handle = None
            self._set_route_preview_text("Preview disabled.")
            return
        self._preview_image()
        self._preview_route()

    def _refresh_checks(self):
        key = self._current_variant_key()
        if not key or key not in self._variants:
            self.variant_hint_label.configure(text="")
            self.resource_status_var.set("No variant selected.")
            return

        template_name, route_path, template_file = self._variant_paths(key)
        template_exists = template_file is not None
        route_exists = route_path.exists()

        selected_mode = self.route_mode_var.get().strip().lower() or "auto"
        effective_mode = "playback" if (selected_mode == "auto" and route_exists) else ("record" if selected_mode == "auto" else selected_mode)

        self.variant_hint_label.configure(
            text=(
                f"Variant={key} | Template: {'OK' if template_exists else 'Missing'} ({template_name})"
                f" | Route: {'OK' if route_exists else 'Missing'} ({route_path.name})"
                f" | Effective mode: {effective_mode}"
            )
        )
        self.resource_status_var.set(
            f"Template file: {template_name} | Route file: {route_path.name}"
        )

    def _add_variant(self):
        raw_name = simpledialog.askstring("Add Defence Variant", "Enter new variant name:", parent=self.root)
        if raw_name is None:
            return
        raw_name = raw_name.strip()
        key = self._normalize_variant_key(raw_name)
        if not key:
            messagebox.showerror("Invalid Variant", "Variant name is required.")
            return
        if key in self._variants:
            messagebox.showerror("Duplicate Variant", f"Variant '{key}' already exists.")
            self._refresh_variant_list(select_key=key)
            return

        self._variants[key] = {
            "display_name": raw_name,
            "entry_template": f"{key}.png",
            "route_name": key,
        }
        if not self._active_variant_key:
            self._active_variant_key = key
        save_variants(self._variants)
        self._append_log(f"[INFO] Defence variant added: {key}", tag="info")
        self._refresh_variant_list(select_key=key)

    def _save_variant(self):
        key = self._current_variant_key()
        if not key or key not in self._variants:
            messagebox.showerror("Save Name", "Please select a defence variant first.")
            return
        new_name = self.variant_name_var.get().strip()
        if not new_name:
            messagebox.showerror("Save Name", "Variant name cannot be empty.")
            return
        self._variants[key]["display_name"] = new_name
        save_variants(self._variants)
        self._append_log(f"[INFO] Updated display name: {key} -> {new_name}", tag="info")
        self._refresh_variant_list(select_key=key)
        self._update_save_name_visibility()

    def _delete_variant_resources(self, key: str):
        template_name, route_path, template_file = self._variant_paths(key)
        route_stats_key = route_path.stem
        removed = []
        if template_file is not None and template_file.exists():
            template_file.unlink(missing_ok=True)
            removed.append(template_name)
        if route_path.exists():
            route_path.unlink(missing_ok=True)
            removed.append(route_path.name)
            if route_stats_key in self._route_stats:
                self._route_stats.pop(route_stats_key, None)
                save_route_stats(self._route_stats)
        if removed:
            self._append_log(f"[WARN] Deleted resources for {key}: {', '.join(removed)}", tag="warn")

    def _delete_variant(self):
        key = self._current_variant_key()
        if not key or key not in self._variants:
            messagebox.showerror("Delete Variant", "Please select a valid variant first.")
            return

        if not messagebox.askyesno("Delete Variant", f"Delete defence variant '{key}'?"):
            return

        if not messagebox.askyesno(
            "Confirm Resource Deletion",
            "This will also delete the variant's image and route files. Continue?",
        ):
            return

        self._delete_variant_resources(key)

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

    def _on_preview_toggle_changed(self):
        self._refresh_previews()
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

    def _preview_image(self):
        key = self._current_variant_key()
        if not key:
            self.image_preview_label.configure(text="No variant selected.", image="")
            self._image_preview_handle = None
            return

        template_name, _route_path, template_file = self._variant_paths(key)
        if template_file is None or not template_file.exists():
            self.image_preview_label.configure(text=f"Template missing: {template_name}", image="")
            self._image_preview_handle = None
            return

        try:
            image = tk.PhotoImage(file=str(template_file))
        except Exception as exc:
            self.image_preview_label.configure(text=f"Image load failed: {exc}", image="")
            self._image_preview_handle = None
            return

        width = max(1, int(image.width()))
        height = max(1, int(image.height()))
        factor = max((width + PREVIEW_MAX_W - 1) // PREVIEW_MAX_W, (height + PREVIEW_MAX_H - 1) // PREVIEW_MAX_H, 1)
        if factor > 1:
            image = image.subsample(factor, factor)

        self._image_preview_handle = image
        self.image_preview_label.configure(image=image, text="")

    def _preview_route(self):
        key = self._current_variant_key()
        if not key:
            self._set_route_preview_text("No variant selected.")
            return

        _template_name, route_path, _template_file = self._variant_paths(key)
        if not route_path.exists():
            attempts, successes, rate = get_rate(self._route_stats, key)
            self._set_route_preview_text(
                f"Route: {route_path.name}\nStatus: Missing\nSuccess: {successes}/{attempts} ({rate:.1f}%)\n"
            )
            return

        try:
            payload = json.loads(route_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._set_route_preview_text(f"Route: {route_path.name}\nJSON read failed: {exc}")
            return

        if not isinstance(payload, dict):
            self._set_route_preview_text(f"Route: {route_path.name}\nInvalid JSON payload: object required.")
            return

        events = payload.get("events", [])
        if not isinstance(events, list):
            self._set_route_preview_text(f"Route: {route_path.name}\nInvalid JSON payload: events[] required.")
            return

        first_t = float(events[0].get("t", 0.0)) if events else 0.0
        last_t = float(events[-1].get("t", 0.0)) if events else 0.0
        attempts, successes, rate = get_rate(self._route_stats, key)
        summary = (
            f"Route: {route_path.name}\n"
            f"Events: {len(events)}\n"
            f"First event t: {first_t:.4f}s\n"
            f"Last event t: {last_t:.4f}s\n"
            f"Success: {successes}/{attempts} ({rate:.1f}%)\n"
        )
        self._set_route_preview_text(summary)

    def _replace_image(self):
        key = self._current_variant_key()
        if not key:
            messagebox.showerror("Replace Image", "Please select a defence variant first.")
            return

        source = filedialog.askopenfilename(
            title="Select entry template image",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not source:
            return

        destination = ASSETS_DIR / f"{key}.png"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        except Exception as exc:
            messagebox.showerror("Replace Image", f"Failed to copy image: {exc}")
            return

        self._variants[key]["entry_template"] = destination.name
        save_variants(self._variants)
        self._append_log(f"[INFO] Replaced image for {key}: {destination.name}", tag="info")
        self._refresh_variant_list(select_key=key)
        self._refresh_previews()

    def _validate_route_payload(self, payload: Any) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("events"), list)

    def _replace_route(self):
        key = self._current_variant_key()
        if not key:
            messagebox.showerror("Replace Route", "Please select a defence variant first.")
            return

        source = filedialog.askopenfilename(
            title="Select route json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not source:
            return

        source_path = Path(source)
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror("Replace Route", f"Invalid JSON: {exc}")
            return

        if not self._validate_route_payload(payload):
            messagebox.showerror("Replace Route", "Route JSON must include an 'events' array.")
            return

        destination = defence_route_path(key)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
        except Exception as exc:
            messagebox.showerror("Replace Route", f"Failed to copy route file: {exc}")
            return

        self._variants[key]["route_name"] = key
        # Replacing a route starts a new baseline for this route's success rate.
        self._route_stats.pop(destination.stem, None)
        save_route_stats(self._route_stats)
        save_variants(self._variants)
        self._append_log(f"[INFO] Replaced route for {key}: {destination.name}", tag="info")
        self._refresh_variant_list(select_key=key)
        self._refresh_previews()

    def _delete_image(self):
        key = self._current_variant_key()
        if not key:
            messagebox.showerror("Delete Image", "Please select a defence variant first.")
            return

        template_name, _route_path, template_file = self._variant_paths(key)
        if template_file is None or not template_file.exists():
            messagebox.showinfo("Delete Image", f"Template does not exist: {template_name}")
            return

        if not messagebox.askyesno("Delete Image", f"Delete template '{template_name}'?"):
            return

        template_file.unlink(missing_ok=True)
        self._append_log(f"[WARN] Deleted image resource: {template_name}", tag="warn")
        self._refresh_checks()
        self._refresh_previews()

    def _delete_route(self):
        key = self._current_variant_key()
        if not key:
            messagebox.showerror("Delete Route", "Please select a defence variant first.")
            return

        _template_name, route_path, _template_file = self._variant_paths(key)
        if not route_path.exists():
            messagebox.showinfo("Delete Route", f"Route does not exist: {route_path.name}")
            return

        if not messagebox.askyesno("Delete Route", f"Delete route '{route_path.name}'?"):
            return

        route_path.unlink(missing_ok=True)
        self._route_stats.pop(route_path.stem, None)
        save_route_stats(self._route_stats)
        self._append_log(f"[WARN] Deleted route resource: {route_path.name}", tag="warn")
        self._refresh_checks()
        self._refresh_previews()

    def _open_assets_folder(self):
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(ASSETS_DIR)])

    def _open_routes_folder(self):
        ROUTES_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(ROUTES_DIR)])

    def _collect_settings(self) -> Optional[Dict[str, Any]]:
        candidate = {
            "dungeon_mode": self.mode_var.get().strip().lower(),
            "manual_dungeon": self.manual_var.get().strip().lower(),
            "target_runs": self.target_runs_var.get().strip(),
            "compact_log_enabled": self.compact_log_var.get(),
            "defence_preview_enabled": self.preview_enabled_var.get(),
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

        if selected["defence_route_mode_override"] == "playback":
            check_key = self._current_variant_key() or self._active_variant_key
            if check_key:
                _template_name, route_path, _template_file = self._variant_paths(check_key)
                if not route_path.exists():
                    messagebox.showerror("Invalid Route Mode", "Playback mode requires an existing route file for the selected variant.")
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
                dungeon_type = str(payload.get("dungeon_type", ""))
                route_name = str(payload.get("route_name", "") or "").strip()
                if dungeon_type == "defence" and route_name:
                    record_attempt(self._route_stats, route_name)
                    save_route_stats(self._route_stats)
                    self._refresh_previews()
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
                route_name = str(payload.get("route_name", "") or "").strip()
                if route_name:
                    record_success(self._route_stats, route_name)
                    save_route_stats(self._route_stats)
                    self._refresh_previews()
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
