"""Single-window overlay UI for VoxScribe."""

import textwrap
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable, Optional

from app.core.locale import _L


CAPTION_FONT_FAMILY = "Segoe UI"
CAPTION_FONT_DEFAULT_SIZE = 16
CAPTION_FONT_MIN_SIZE = 10
CAPTION_FONT_MAX_SIZE = 28
CAPTION_FONT_PROFILE = "subtitle_v3"


class SubtitleOverlay:
    """Draggable always-on-top overlay with subtitle, menu, and transcript views."""

    def __init__(self, root, config, toggle_recognition: Callable[[], None], actions):
        self.root = root
        self.config = config
        self.toggle_recognition = toggle_recognition
        self.actions = dict(actions or {})
        self.window = None
        self.caption_label = None
        self.loading_label = None
        self.loading_bar = None
        self.status_label = None
        self.info_label = None
        self.compact_label = None
        self.toggle_button = None
        self._menu_variables = []
        self.font_size = self._config_int(
            "overlay_font_size",
            CAPTION_FONT_DEFAULT_SIZE,
            CAPTION_FONT_MIN_SIZE,
            CAPTION_FONT_MAX_SIZE,
        )
        self._migrate_caption_font_profile()
        if self.font_size > CAPTION_FONT_MAX_SIZE:
            self.font_size = CAPTION_FONT_DEFAULT_SIZE
            self.config.set("overlay_font_size", self.font_size)
        self.caption_text = ""
        self.loading_text = ""
        self.loading_progress = None
        self.loading_animation_canvas = None
        self.loading_animation_job = None
        self.loading_animation_phase = 0
        self.status_pulse_job = None
        self.status_pulse_on = True
        self.status_text = "Ready"
        self.status_state = "ready"
        self.is_running = False
        self.is_compact = self._config_bool("overlay_compact", True)
        self.overlay_transcript_widget = None
        self.placement = "default"
        self.drag_anchor = None
        self._last_geometry = None
        self._position_job = None
        self._position_debounce_ms = 45

    def show(
        self,
        caption: Optional[str] = None,
        compact: Optional[bool] = None,
        placement: str = "default",
    ):
        self.placement = placement or "default"
        if compact is not None:
            self.is_compact = bool(compact)
        if caption is not None:
            self.caption_text = caption

        self._ensure_window()
        self._render()
        self._position_window()
        self.window.deiconify()
        self.window.lift()
        self._set_topmost()

    def hide(self):
        if self.window:
            self.window.withdraw()

    def destroy(self):
        self._cancel_pending_position()
        self._stop_status_pulse()
        self._stop_loading_animation()
        self._save_position()
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass
        self.window = None

    def refresh(self):
        if not self.window or not self.window.winfo_exists():
            return
        state = self._state()
        if self.overlay_transcript_widget:
            entries = state.get("transcript_entries")
            if entries:
                self._write_transcript_entries(entries)
            else:
                content = state.get("transcript", "").strip() or _L("No transcript yet.")
                self._write_transcript_text(content)
        self._update_static_labels()
        if self.toggle_button:
            self._configure_toggle_button(self.toggle_button)

    def set_transcript(self, content):
        if not self.overlay_transcript_widget:
            return
        if isinstance(content, list):
            self._write_transcript_entries(content)
        else:
            self._write_transcript_text(content or _L("No transcript yet."))

    def _write_transcript_text(self, text):
        try:
            self.overlay_transcript_widget.configure(state="normal")
            self.overlay_transcript_widget.delete("1.0", "end")
            self.overlay_transcript_widget.insert("1.0", text)
            self.overlay_transcript_widget.configure(state="disabled")
            self.overlay_transcript_widget.see("end")
        except Exception:
            pass

    def _write_transcript_entries(self, entries):
        try:
            self.overlay_transcript_widget.configure(state="normal")
            self.overlay_transcript_widget.delete("1.0", "end")
            total = len(entries)
            for i, entry in enumerate(entries):
                tag = "entry_new" if i == total - 1 else "entry_old"
                lines = [f"[{entry['timestamp']}] {entry['text']}"]
                target_label = entry.get("target_label", "OUT")
                if entry.get("translation"):
                    lines.append(f"{target_label}: {entry['translation']}")
                elif entry.get("translation_pending"):
                    lines.append(f"{target_label}: {entry.get('pending_text', 'Translating...')}")
                block = "\n".join(lines) + "\n\n"
                self.overlay_transcript_widget.insert("end", block, tag)
            self.overlay_transcript_widget.configure(state="disabled")
            self.overlay_transcript_widget.see("end")
        except Exception:
            pass

    def set_caption(self, text: str):
        self.caption_text = (text or "").strip()
        if self.overlay_transcript_widget:
            try:
                self.overlay_transcript_widget.see("end")
            except Exception:
                pass

    def set_status(self, state: str, message: Optional[str] = None):
        was_loading_visible = self._is_loading_visible()
        self.status_state = state or "ready"
        self.status_text = message or self._status_label_for_state(self.status_state)
        if self.status_state not in {"busy", "switching"}:
            self.loading_text = ""
            self.loading_progress = None

        loading_visibility_changed = was_loading_visible != self._is_loading_visible()
        self._update_static_labels()
        self._sync_existing_loading_widgets()
        if self._should_rebuild_for_state_change(loading_visibility_changed):
            self._render()
            self._position_window()

    def _refresh_subtitle_layout(self):
        pass

    def set_loading(self, message: str, progress: Optional[float] = None):
        was_loading_visible = self._is_loading_visible()
        self.status_state = "busy"
        self.status_text = message or "Preparing"
        self.loading_text = self.status_text
        if progress is None:
            self.loading_progress = None
        else:
            try:
                self.loading_progress = max(0.0, min(1.0, float(progress)))
            except Exception:
                self.loading_progress = None

        loading_visibility_changed = was_loading_visible != self._is_loading_visible()
        self._update_static_labels()
        if self._should_rebuild_for_state_change(
            loading_visibility_changed or self._loading_widget_missing()
        ):
            self._render()
            self._position_window()
        else:
            self._sync_existing_loading_widgets()
        self._start_loading_animation()

    def clear_loading(self):
        was_loading_visible = self._is_loading_visible()
        self.loading_text = ""
        self.loading_progress = None
        self._stop_loading_animation()
        loading_visibility_changed = was_loading_visible != self._is_loading_visible()
        self._update_static_labels()
        if self._should_rebuild_for_state_change(loading_visibility_changed):
            self._render()
            self._position_window()

    def _update_static_labels(self):
        if self.status_label:
            self.status_label.configure(
                text=self._header_dot_text(),
                fg=self._status_dot_color(),
            )
        if self.info_label:
            self.info_label.configure(text=self._overlay_info_text(self._state()))
        if self.compact_label:
            self.compact_label.configure(text=self._compact_text())
        if self.toggle_button:
            self._configure_toggle_button(self.toggle_button)

    def _status_dot_color(self):
        if not self.is_running:
            return "#b7c0cc"
        return "#ff4d4f" if self.status_pulse_on else "#7f1d1d"

    def _start_status_pulse(self):
        if self.status_pulse_job:
            return
        self.status_pulse_on = True
        self._tick_status_pulse()

    def _tick_status_pulse(self):
        if not self.is_running:
            self.status_pulse_job = None
            self.status_pulse_on = True
            self._update_static_labels()
            return
        self.status_pulse_on = not self.status_pulse_on
        self._update_static_labels()
        self.status_pulse_job = self.root.after(520, self._tick_status_pulse)

    def _stop_status_pulse(self):
        job = self.status_pulse_job
        self.status_pulse_job = None
        self.status_pulse_on = True
        if job and self.root and hasattr(self.root, "after_cancel"):
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._update_static_labels()

    def _sync_existing_loading_widgets(self):
        if self.loading_label:
            try:
                self.loading_label.configure(text=self._loading_label_text())
            except Exception:
                pass
        self._draw_loading_animation()

    def _loading_widget_missing(self) -> bool:
        return bool(self._is_loading_visible() and not self.loading_label)

    def _should_rebuild_for_state_change(self, structure_changed: bool) -> bool:
        if not self.window or not self.window.winfo_exists():
            return False
        return bool(structure_changed)

    def set_running(self, is_running: bool):
        was_running = self.is_running
        self.is_running = bool(is_running)
        if self.is_running:
            self._start_status_pulse()
        else:
            self._stop_status_pulse()
        if self.window and self.window.winfo_exists():
            if was_running != self.is_running:
                self._render()
                self._position_window()
            else:
                self._update_static_labels()
                if self.toggle_button:
                    self._configure_toggle_button(self.toggle_button)

    def toggle_compact(self):
        if not self.window or not self.window.winfo_exists():
            return
        try:
            self.is_compact = not self.is_compact
            self.config.set("overlay_compact", self.is_compact)
            self._render()
            self._position_window()
        except Exception:
            pass

    def increase_font(self):
        self.font_size = min(CAPTION_FONT_MAX_SIZE, self.font_size + 2)
        self.config.set("overlay_font_size", self.font_size)
        self.config.set("overlay_font_profile", CAPTION_FONT_PROFILE)
        self._render()
        self._position_window()

    def decrease_font(self):
        self.font_size = max(CAPTION_FONT_MIN_SIZE, self.font_size - 2)
        self.config.set("overlay_font_size", self.font_size)
        self.config.set("overlay_font_profile", CAPTION_FONT_PROFILE)
        self._render()
        self._position_window()

    def reset_position(self):
        self.config.set("overlay_x", None)
        self.config.set("overlay_y", None)
        self._position_window()

    def _ensure_window(self):
        if self.window and self.window.winfo_exists():
            return

        self.window = tk.Toplevel(self.root)
        self.window.title("VoxScribe")
        self.window.configure(bg="#111111")
        self.window.overrideredirect(True)
        self.window.protocol("WM_DELETE_WINDOW", self.hide)
        self.window.bind("<ButtonPress-1>", self._begin_drag)
        self.window.bind("<B1-Motion>", self._drag)
        self.window.bind("<ButtonRelease-1>", self._end_drag)
        self._last_geometry = None
        self._set_topmost()
        try:
            self.window.attributes("-alpha", 0.92)
        except Exception:
            pass

    def _render(self):
        if not self.window:
            return

        for child in self.window.winfo_children():
            child.destroy()

        self.caption_label = None
        self.loading_label = None
        self.loading_bar = None
        self.loading_animation_canvas = None
        self.status_label = None
        self.compact_label = None
        self.toggle_button = None
        self.overlay_transcript_widget = None

        if self.placement == "startup":
            self._render_startup()
        else:
            self._render_main()

    def _render_startup(self):
        bg = "#111111"
        frame = tk.Frame(self.window, bg=bg, padx=12, pady=10)
        frame.pack(fill="both", expand=True)
        self._bind_drag(frame)

        header = tk.Frame(frame, bg=bg)
        header.pack(fill="x", pady=(0, 8))
        self._bind_drag(header)

        self.status_label = tk.Label(
            header,
            text=self._header_dot_text(),
            bg=bg,
            fg=self._status_dot_color(),
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.status_label.pack(side="left")
        self._bind_drag(self.status_label)

        self.info_label = tk.Label(
            header,
            text="VoxScribe",
            bg=bg,
            fg="#e6edf3",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        )
        self.info_label.pack(side="left", padx=(8, 0))
        self._bind_drag(self.info_label)

        self.caption_label = tk.Label(
            frame,
            text=self._caption_display_text(),
            bg=bg,
            fg="#d1d5db",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=self._text_wraplength(),
        )
        self.caption_label.pack(fill="x", pady=(0, 8))
        self._bind_drag(self.caption_label)

        self._render_loading_bar(frame)

    def _render_main(self):
        state = self._state()
        controls = self._control_flags(state)
        bg = "#111111"

        frame = tk.Frame(self.window, bg=bg, padx=10, pady=8)
        frame.pack(fill="both", expand=True)
        self._bind_drag(frame)

        # Header row: status dot + buttons
        header = tk.Frame(frame, bg=bg)
        header.pack(fill="x", pady=(0, 4))
        self._bind_drag(header)

        self.status_label = tk.Label(
            header,
            text=self._header_dot_text(),
            bg=bg,
            fg=self._status_dot_color(),
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.status_label.pack(side="left")
        self._bind_drag(self.status_label)

        # Pack buttons to the right first so they're never clipped by long info text
        self.toggle_button = self._button(
            header,
            self._toggle_button_text(state),
            self.toggle_recognition,
            bg=self._toggle_button_bg(state),
            active=self._toggle_button_active_bg(state),
            enabled=not controls["recognition_action_disabled"],
            side="right",
        )
        self._button(header, "A-", self.decrease_font, side="right")
        self._button(header, "A+", self.increase_font, side="right")
        self._button(header, "✕", self._exit_app, bg="#6b1f1f", active="#7f2424", side="right")

        self.info_label = tk.Label(
            header,
            text=self._overlay_info_text(state),
            bg=bg,
            fg="#6b7280",
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.info_label.pack(side="left", padx=(8, 0), fill="x", expand=True)
        self._bind_drag(self.info_label)

        # Loading bar (appears when running or model loading)
        self._render_loading_bar(frame)

        # Language selectors — compact inline
        lang_row = tk.Frame(frame, bg=bg)
        lang_row.pack(fill="x", pady=(2, 6))
        self._bind_drag(lang_row)
        self._compact_language_row(lang_row, state, controls)

        # Transcript area
        text_frame = tk.Frame(frame, bg=bg)
        text_frame.pack(fill="both", expand=True, pady=(0, 6))

        transcript_font_size = max(9, self.font_size - 3)
        self.overlay_transcript_widget = tk.Text(
            text_frame,
            bg="#0d1117",
            fg="#e6edf3",
            insertbackground="#e6edf3",
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#30363d",
            font=("Segoe UI", transcript_font_size),
            padx=8,
            pady=6,
            height=7,
        )
        scrollbar = tk.Scrollbar(text_frame, command=self.overlay_transcript_widget.yview)
        self.overlay_transcript_widget.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.overlay_transcript_widget.pack(side="left", fill="both", expand=True)
        self.overlay_transcript_widget.tag_config("entry_old", foreground="#8b949e")
        self.overlay_transcript_widget.tag_config("entry_new", foreground="#e6edf3",
                                                   font=("Segoe UI", transcript_font_size, "bold"))

        transcript_content = state.get("transcript", "").strip() or _L("No transcript yet.")
        entries = state.get("transcript_entries")
        if entries:
            total = len(entries)
            for i, entry in enumerate(entries):
                tag = "entry_new" if i == total - 1 else "entry_old"
                lines = [f"[{entry['timestamp']}] {entry['text']}"]
                target_label = entry.get("target_label", "OUT")
                if entry.get("translation"):
                    lines.append(f"{target_label}: {entry['translation']}")
                elif entry.get("translation_pending"):
                    lines.append(f"{target_label}: {entry.get('pending_text', 'Translating...')}")
                block = "\n".join(lines) + "\n\n"
                self.overlay_transcript_widget.insert("end", block, tag)
        else:
            self.overlay_transcript_widget.insert("1.0", transcript_content)
        self.overlay_transcript_widget.configure(state="disabled")
        self.overlay_transcript_widget.see("end")

        # Footer: Save / Clear / Font info
        footer = tk.Frame(frame, bg=bg)
        footer.pack(fill="x")
        self._button(
            footer, "Save", self._save_transcript,
            enabled=not controls["transcript_actions_disabled"],
        )
        self._button(
            footer, "Clear", self._clear_transcript,
            enabled=not controls["transcript_actions_disabled"],
        )
        tk.Label(
            footer,
            text=f"F{self.font_size}",
            bg=bg,
            fg="#6b7280",
            font=("Segoe UI", 8),
        ).pack(side="right", padx=(4, 2))
        self._button(footer, "Reset", self.reset_position)

    def _overlay_info_text(self, state):
        input_label = state.get("input_label") or "Auto"
        output_label = state.get("output_label") or "Output"
        if input_label == output_label:
            return f"VoxScribe | {output_label}"
        if input_label == "Auto":
            return f"VoxScribe | Auto → {output_label}"
        return f"VoxScribe | {input_label} → {output_label}"

    def _compact_language_row(self, parent, state, controls):
        bg = "#111111"
        menu_cfg = dict(
            bg="#1e2530", fg="#ffffff", activebackground="#1f6feb",
            activeforeground="#ffffff", highlightthickness=0, relief="flat",
            borderwidth=0, font=("Segoe UI", 8),
        )
        menu_dropdown_cfg = dict(bg="#1e2530", fg="#ffffff", activebackground="#1f6feb", activeforeground="#ffffff")

        # Input language selector
        tk.Label(
            parent, text="In:", bg=bg, fg="#9ca3af", font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=(0, 2))

        in_values = list(state.get("input_labels", ()))
        in_selected = state.get("input_label", "")
        if not in_values:
            in_values = [in_selected or "-"]
        in_var = tk.StringVar(value=in_selected or in_values[0])
        self._menu_variables.append(in_var)
        in_menu = tk.OptionMenu(parent, in_var, *in_values, command=self._change_input_language)
        in_menu.configure(
            **menu_cfg,
            state="normal" if not controls["input_language_disabled"] else "disabled",
            width=8,
        )
        in_menu["menu"].configure(**menu_dropdown_cfg)
        in_menu.pack(side="left")

        # Separator
        tk.Label(parent, text="→", bg=bg, fg="#4b5563", font=("Segoe UI", 8)).pack(side="left", padx=(4, 4))

        # Output language selector
        tk.Label(
            parent, text="Out:", bg=bg, fg="#9ca3af", font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=(0, 2))

        out_values = list(state.get("output_labels", ()))
        out_selected = state.get("output_label", "")
        if not out_values:
            out_values = [out_selected or "-"]
        out_var = tk.StringVar(value=out_selected or out_values[0])
        self._menu_variables.append(out_var)
        out_menu = tk.OptionMenu(parent, out_var, *out_values, command=self._change_output_language)
        out_menu.configure(
            **menu_cfg,
            state="normal" if not controls["output_language_disabled"] else "disabled",
            width=8,
        )
        out_menu["menu"].configure(**menu_dropdown_cfg)
        out_menu.pack(side="left")

    def _language_row(
        self, parent, label_text: str, values, selected: str, command, enabled: bool = True
    ):
        row = tk.Frame(parent, bg="#111111")
        row.pack(fill="x", pady=(3, 3))
        self._bind_drag(row)

        label = tk.Label(
            row,
            text=label_text,
            bg="#111111",
            fg="#d1d5db",
            font=("Segoe UI", 10, "bold"),
            width=6,
            anchor="w",
        )
        label.pack(side="left")
        self._bind_drag(label)

        options = list(values or ())
        if not options:
            options = [selected or "-"]
        variable = tk.StringVar(value=selected or options[0])
        self._menu_variables.append(variable)
        menu = tk.OptionMenu(row, variable, *options, command=command)
        menu.configure(
            bg="#222222",
            fg="#ffffff",
            activebackground="#2f3338",
            activeforeground="#ffffff",
            highlightthickness=0,
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 10),
            state="normal" if enabled else "disabled",
            width=30,
        )
        menu["menu"].configure(
            bg="#222222",
            fg="#ffffff",
            activebackground="#1f6feb",
            activeforeground="#ffffff",
            relief="flat",
        )
        menu.pack(side="left", fill="x", expand=True)

    def _render_loading_bar(self, parent):
        if not self._is_loading_visible():
            return

        loading_frame = tk.Frame(parent, bg=parent.cget("bg"))
        loading_frame.pack(fill="x", pady=(6, 0))
        self._bind_drag(loading_frame)

        self.loading_label = tk.Label(
            loading_frame,
            text=self._loading_label_text(),
            bg=parent.cget("bg"),
            fg="#9fb4c7",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=self._text_wraplength(),
        )
        self.loading_label.pack(fill="x", pady=(0, 4))
        self._bind_drag(self.loading_label)

        width = max(180, min(540, self._target_size()[0] - 34))
        self.loading_animation_canvas = tk.Canvas(
            loading_frame,
            width=width,
            height=5,
            bg="#20252b",
            highlightthickness=0,
            bd=0,
        )
        self.loading_animation_canvas.pack(fill="x")
        self.loading_bar = self.loading_animation_canvas
        self._draw_loading_animation()
        self._start_loading_animation()

    def _loading_label_text(self):
        text = self.loading_text or self.status_text or "Preparing"
        progress = self.loading_progress
        if progress is not None:
            return f"{text} {int(progress * 100)}%"
        dot_count = ((self.loading_animation_phase // 4) % 3) + 1
        return f"{text}{'.' * dot_count}"

    def _draw_loading_animation(self):
        canvas = self.loading_animation_canvas
        if not canvas:
            return

        try:
            width = int(float(canvas.cget("width")))
        except Exception:
            width = 220
        height = 5
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#20252b", width=0)

        progress = self.loading_progress
        if progress is None:
            segment = max(46, int(width * 0.28))
            travel = width + segment
            x = int((travel * ((self.loading_animation_phase % 36) / 35.0)) - segment)
            canvas.create_rectangle(
                max(0, x),
                0,
                min(width, x + segment),
                height,
                fill="#4ea1ff",
                width=0,
            )
            glow_x = min(width, max(0, x + segment - 10))
            canvas.create_rectangle(
                glow_x,
                0,
                min(width, glow_x + 10),
                height,
                fill="#95e6c8",
                width=0,
            )
            return

        filled = int(width * max(0.0, min(1.0, float(progress))))
        if filled > 0:
            canvas.create_rectangle(0, 0, filled, height, fill="#4ea1ff", width=0)
            if 0 < filled < width:
                pulse = 8 + (self.loading_animation_phase % 8)
                canvas.create_rectangle(
                    max(0, filled - pulse),
                    0,
                    min(width, filled + 4),
                    height,
                    fill="#95e6c8",
                    width=0,
                )

    def _start_loading_animation(self):
        if self.loading_animation_job or not self._is_loading_visible():
            return
        self._schedule_loading_animation()

    def _schedule_loading_animation(self):
        try:
            self.loading_animation_job = self.root.after(90, self._tick_loading_animation)
        except Exception:
            self.loading_animation_job = None

    def _stop_loading_animation(self):
        job = self.loading_animation_job
        self.loading_animation_job = None
        if job and self.root:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

    def _tick_loading_animation(self):
        self.loading_animation_job = None
        if not self._is_loading_visible():
            return

        self.loading_animation_phase += 1
        if self.loading_label:
            try:
                self.loading_label.configure(text=self._loading_label_text())
            except Exception:
                pass
        self._draw_loading_animation()
        self._schedule_loading_animation()

    def _is_loading_visible(self):
        return bool(
            self.status_state in {"busy", "switching"}
            or self.is_running
            or self.loading_text
            or self.loading_progress is not None
        )

    def _control_flags(self, state: Optional[dict] = None):
        state = dict(state or self._state() or {})
        loading_keys = (
            "model_download_in_progress",
            "model_prewarm_in_progress",
            "audio_warmup_in_progress",
            "recognition_start_in_progress",
            "pending_start_after_prewarm",
            "offline_translation_prepare_in_progress",
            "pending_start_after_offline_translation",
        )
        engine_busy = any(bool(state.get(key)) for key in loading_keys)
        language_switching = bool(
            state.get("language_switch_in_progress")
            or state.get("status") == "switching"
            or self.status_state == "switching"
        )
        loading_indicator_active = bool(
            self.loading_text
            or self.loading_progress is not None
            or self.status_state in {"busy", "switching"}
        )
        system_busy = bool(
            state.get("system_busy", False)
            or engine_busy
            or language_switching
            or loading_indicator_active
        )

        recognition_disabled = state.get("recognition_action_disabled")
        if recognition_disabled is None:
            recognition_disabled = bool(
                engine_busy
                or language_switching
                or (not self.is_running and self._is_loading_visible())
            )

        input_disabled = state.get("input_language_disabled")
        if input_disabled is None:
            input_disabled = system_busy

        output_disabled = state.get("output_language_disabled")
        if output_disabled is None:
            output_disabled = system_busy

        transcript_disabled = state.get("transcript_actions_disabled")
        if transcript_disabled is None:
            transcript_disabled = bool(engine_busy or language_switching)

        return {
            "system_busy": bool(system_busy),
            "recognition_action_disabled": bool(recognition_disabled),
            "input_language_disabled": bool(input_disabled),
            "output_language_disabled": bool(output_disabled),
            "transcript_actions_disabled": bool(transcript_disabled),
        }

    def _toggle_button_text(self, state: Optional[dict] = None, long: bool = False):
        if self.is_running:
            return _L("Stop Transcription") if long else _L("Stop")
        if self._control_flags(state)["recognition_action_disabled"]:
            return _L("Preparing...") if long else _L("Wait")
        return _L("Start Transcription") if long else _L("Start")

    def _toggle_button_bg(self, state: Optional[dict] = None):
        return "#d23b3b" if self.is_running else "#1f6feb"

    def _toggle_button_active_bg(self, state: Optional[dict] = None):
        return "#b83232" if self.is_running else "#1a5fc8"

    def _configure_toggle_button(self, button, state: Optional[dict] = None):
        enabled = not self._control_flags(state)["recognition_action_disabled"]
        button.configure(
            text=self._toggle_button_text(state),
            bg=self._toggle_button_bg(state) if enabled else "#252a30",
            fg="#ffffff" if enabled else "#7f8792",
            activebackground=self._toggle_button_active_bg(state) if enabled else "#252a30",
            activeforeground="#ffffff" if enabled else "#7f8792",
            disabledforeground="#7f8792",
            cursor="hand2" if enabled else "arrow",
            state="normal" if enabled else "disabled",
        )

    def _button(
        self,
        parent,
        text: str,
        command: Callable[[], None],
        bg="#2f3338",
        active="#3f444a",
        enabled: bool = True,
        width: Optional[int] = None,
        side: str = "left",
    ):
        effective_bg = bg if enabled else "#252a30"
        effective_fg = "#ffffff" if enabled else "#7f8792"
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=effective_bg,
            fg=effective_fg,
            activebackground=active if enabled else effective_bg,
            activeforeground="#ffffff" if enabled else effective_fg,
            disabledforeground="#7f8792",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 8, "bold"),
            padx=7,
            pady=3,
            cursor="hand2" if enabled else "arrow",
            state="normal" if enabled else "disabled",
        )
        if width is not None:
            button.configure(width=width)
        pad = (0, 5) if side == "right" else (5, 0)
        button.pack(side=side, padx=pad)
        return button

    def flash_language_change(self, direction: str, lang_label: str):
        if not self.info_label:
            return
        prefix = "IN" if direction == "input" else "OUT"
        try:
            self.info_label.configure(
                text=f"VoxScribe | {prefix}: {lang_label}",
                fg="#4ea1ff",
            )
        except Exception:
            return

        def revert():
            try:
                state = self._state()
                self.info_label.configure(
                    text=self._overlay_info_text(state),
                    fg="#6b7280",
                )
            except Exception:
                pass

        if self.root:
            self.root.after(1800, revert)

    def _change_input_language(self, selected_label: str):
        if self._control_flags()["input_language_disabled"]:
            self.refresh()
            return
        self._call("set_input_language", selected_label)
        self.refresh()

    def _change_output_language(self, selected_label: str):
        if self._control_flags()["output_language_disabled"]:
            self.refresh()
            return
        self._call("set_output_language", selected_label)
        self.refresh()

    def _save_transcript(self):
        if self._control_flags()["transcript_actions_disabled"]:
            self.refresh()
            return
        self._call("save_transcript")
        self.refresh()

    def _clear_transcript(self):
        if self._control_flags()["transcript_actions_disabled"]:
            self.refresh()
            return
        self._call("clear_transcript")
        self.refresh()

    def _exit_app(self):
        self._call("exit_app")

    def _bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self._begin_drag)
        widget.bind("<B1-Motion>", self._drag)
        widget.bind("<ButtonRelease-1>", self._end_drag)

    def _begin_drag(self, event):
        if not self.window:
            return
        self._cancel_pending_position()
        self.drag_anchor = (
            event.x_root,
            event.y_root,
            self.window.winfo_x(),
            self.window.winfo_y(),
        )

    def _drag(self, event):
        if not self.window or not self.drag_anchor:
            return
        start_x, start_y, window_x, window_y = self.drag_anchor
        new_x = window_x + (event.x_root - start_x)
        new_y = window_y + (event.y_root - start_y)
        self.window.geometry(f"+{new_x}+{new_y}")
        self._last_geometry = None

    def _end_drag(self, _event):
        self._save_position()
        self.drag_anchor = None

    def _request_position_window(self):
        if not self.window:
            return
        if self.drag_anchor:
            return
        if self._position_job:
            return

        if self.root and hasattr(self.root, "after"):
            try:
                self._position_job = self.root.after(
                    self._position_debounce_ms, self._run_pending_position
                )
                return
            except Exception:
                self._position_job = None

        self._position_window()

    def _run_pending_position(self):
        self._position_job = None
        self._position_window()

    def _cancel_pending_position(self):
        job = self._position_job
        self._position_job = None
        if job and self.root and hasattr(self.root, "after_cancel"):
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

    def _position_window(self):
        if not self.window:
            return
        self._cancel_pending_position()

        width, height = self._target_size()
        x, y = self._saved_or_default_position(width, height)
        geometry = (width, height, x, y)
        if geometry == self._last_geometry:
            return
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self._last_geometry = geometry
        try:
            self.window.update_idletasks()
        except Exception:
            pass

    def _saved_or_default_position(self, width: int, height: int):
        screen_width = max(1, self.root.winfo_screenwidth())
        screen_height = max(1, self.root.winfo_screenheight())
        saved_x = self.config.get("overlay_x", None)
        saved_y = self.config.get("overlay_y", None)
        padding = 12
        max_x = max(padding, screen_width - width - padding)
        max_y = max(padding, screen_height - height - padding)

        if self.placement == "startup":
            x = max(padding, screen_width - width - 28)
            y = min(max_y, max(padding, 42))
            return self._clamp_to_visible_area(x, y, width, height)

        try:
            x = int(saved_x)
            y = int(saved_y)
            if x >= -width + 80 and x <= screen_width - 80 and y >= 0 and y <= screen_height - 40:
                return self._clamp_to_visible_area(x, y, width, height)
        except Exception:
            pass

        x = max(padding, min((screen_width - width) // 2, max_x))
        y = max(padding, min(screen_height - height - 124, max_y))
        return self._clamp_to_visible_area(x, y, width, height)

    def _target_size(self):
        if self.placement == "startup":
            return self._bounded_size(580, 172)
        return self._bounded_size(460, 310)

    def _text_wraplength(self):
        return max(180, self._target_size()[0] - 34)

    def _full_width(self):
        screen_width = max(640, self.root.winfo_screenwidth())
        text_length = len(self._caption_display_text())
        scale = 0.44
        max_width = 680
        if text_length > 90:
            scale = 0.60
            max_width = 920
        if text_length > 160:
            scale = 0.72
            max_width = 1080
        if text_length > 260:
            scale = 0.84
            max_width = 1280

        usable_width = max(300, screen_width - 24)
        return min(max_width, usable_width, max(360, int(screen_width * scale)))

    def _subtitle_height(self):
        caption_size = self._effective_caption_font_size()
        height = self._subtitle_content_height(caption_size)
        loading_extra = self._loading_height()
        min_height = 86 + loading_extra
        max_height = self._max_subtitle_height()
        return max(min_height, min(max_height, height))

    def _max_subtitle_height(self):
        screen_height = max(480, self.root.winfo_screenheight())
        return max(220, min(screen_height - 56, int(screen_height * 0.74)))

    def _caption_wraplength(self):
        return max(260, self._full_width() - 48)

    def _caption_display_text(self):
        return self.caption_text or self._idle_caption()

    def _effective_caption_font_size(self):
        base_size = self.font_size
        if self._subtitle_content_height(base_size) <= self._max_subtitle_height():
            return base_size

        for size in range(base_size - 1, CAPTION_FONT_MIN_SIZE - 1, -1):
            if self._subtitle_content_height(size) <= self._max_subtitle_height():
                return size
        return CAPTION_FONT_MIN_SIZE

    def _subtitle_content_height(self, caption_size: int):
        caption_font = self._caption_font(caption_size)
        caption_lines = self._wrapped_lines(self._caption_display_text(), caption_font, caption_size)
        caption_line_height = self._line_height(caption_font, caption_size)
        return 42 + caption_lines * caption_line_height + self._loading_height()

    def _loading_height(self):
        return 30 if self._is_loading_visible() else 0

    def _caption_font(self, size: int):
        return (CAPTION_FONT_FAMILY, size)

    def _line_height(self, font_spec, fallback_size: int):
        try:
            font = tkfont.Font(root=self.root, font=font_spec)
            return max(14, int(font.metrics("linespace") * 1.08))
        except Exception:
            return max(14, int(fallback_size * 1.28))

    def _wrapped_lines(self, text: str, font_spec, fallback_size: int):
        clean_text = (text or "").strip()
        if not clean_text:
            return 0

        try:
            font = tkfont.Font(root=self.root, font=font_spec)
            return self._measured_wrapped_lines(clean_text, font)
        except Exception:
            return self._estimated_wrapped_lines(clean_text, fallback_size)

    def _measured_wrapped_lines(self, text: str, font):
        max_width = self._caption_wraplength()
        total_lines = 0
        for paragraph in text.splitlines() or [text]:
            paragraph = paragraph.strip()
            if not paragraph:
                total_lines += 1
                continue
            total_lines += self._measured_paragraph_lines(paragraph, font, max_width)
        return max(1, total_lines)

    def _measured_paragraph_lines(self, paragraph: str, font, max_width: int):
        chunks = self._wrap_chunks(paragraph)
        lines = 0
        current = ""
        for chunk in chunks:
            candidate = f"{current}{chunk}" if current else chunk.lstrip()
            if font.measure(candidate) <= max_width:
                current = candidate
                continue

            if current:
                lines += 1
                current = ""

            remaining = chunk.lstrip()
            while remaining and font.measure(remaining) > max_width:
                split_at = self._fit_prefix_length(remaining, font, max_width)
                lines += 1
                remaining = remaining[split_at:].lstrip()
            current = remaining

        if current:
            lines += 1
        return max(1, lines)

    def _wrap_chunks(self, paragraph: str):
        chunks = []
        current = ""
        for char in paragraph:
            current += char
            if char.isspace():
                chunks.append(current)
                current = ""
            elif self._has_wide_text(char):
                if current[:-1]:
                    chunks.append(current[:-1])
                chunks.append(char)
                current = ""
        if current:
            chunks.append(current)
        return chunks or [paragraph]

    def _fit_prefix_length(self, text: str, font, max_width: int):
        if len(text) <= 1:
            return 1

        low, high = 1, len(text)
        best = 1
        while low <= high:
            mid = (low + high) // 2
            if font.measure(text[:mid]) <= max_width:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return max(1, best)

    def _estimated_wrapped_lines(self, text: str, font_size: int):
        clean_text = (text or "").strip()
        if not clean_text:
            return 0

        chars_per_line = self._chars_per_line(font_size, clean_text)
        lines = 0
        for paragraph in clean_text.splitlines() or [clean_text]:
            paragraph = paragraph.strip()
            if not paragraph:
                lines += 1
                continue
            lines += max(
                1,
                len(
                    textwrap.wrap(
                        paragraph,
                        width=chars_per_line,
                        break_long_words=True,
                        replace_whitespace=False,
                    )
                ),
            )
        return lines

    def _chars_per_line(self, font_size: int, text: str):
        avg_char_width = font_size * (0.94 if self._has_wide_text(text) else 0.53)
        return max(16, int(self._caption_wraplength() / max(7, avg_char_width)))

    def _has_wide_text(self, text: str):
        return any(
            "\u2e80" <= char <= "\u9fff"
            or "\uf900" <= char <= "\ufaff"
            or "\uff00" <= char <= "\uffef"
            for char in text
        )

    def _bounded_size(self, width: int, height: int):
        screen_width = max(360, self.root.winfo_screenwidth())
        screen_height = max(240, self.root.winfo_screenheight())
        return min(width, screen_width - 24), min(height, screen_height - 48)

    def _clamp_to_visible_area(self, x: int, y: int, width: int, height: int):
        screen_width = max(1, self.root.winfo_screenwidth())
        screen_height = max(1, self.root.winfo_screenheight())
        padding = 12
        max_x = max(padding, screen_width - width - padding)
        max_y = max(padding, screen_height - height - padding)
        return max(padding, min(int(x), max_x)), max(padding, min(int(y), max_y))

    def _save_position(self):
        if not self.window or not self.window.winfo_exists():
            return
        if self.placement == "startup":
            return
        try:
            self.config.set("overlay_x", int(self.window.winfo_x()))
            self.config.set("overlay_y", int(self.window.winfo_y()))
        except Exception:
            pass

    def _set_topmost(self):
        if not self.window:
            return
        try:
            self.window.attributes("-topmost", True)
        except Exception:
            pass

    def _idle_caption(self):
        return _L("Press Start to begin transcription.")

    def _header_text(self):
        return self._status_label_for_state(self.status_state)

    def _header_dot_text(self):
        dot = "●" if self.is_running else "○"
        return f"{dot} {self._status_label_for_state(self.status_state)}"

    def _status_label_for_state(self, state: str):
        return {
            "busy": _L("Preparing"),
            "ready": _L("Ready"),
            "live": _L("Processing"),
            "switching": _L("Switching"),
            "error": _L("Needs attention"),
            "stopped": _L("Stopped"),
        }.get(state, _L("Ready"))

    def _state(self):
        get_state = self.actions.get("get_state")
        if not get_state:
            return {}
        try:
            return dict(get_state() or {})
        except Exception:
            return {}

    def _call(self, name: str, *args):
        action = self.actions.get(name)
        if not action:
            return None
        try:
            return action(*args)
        except Exception:
            return None

    def _config_int(self, key: str, default: int, low: int, high: int):
        try:
            value = int(self.config.get(key, default))
        except Exception:
            value = default
        return max(low, min(high, value))

    def _config_bool(self, key: str, default: bool):
        try:
            value = self.config.get(key, default)
        except Exception:
            return default
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _migrate_caption_font_profile(self):
        try:
            profile = self.config.get("overlay_font_profile", "")
        except Exception:
            profile = ""

        if profile == CAPTION_FONT_PROFILE:
            return

        if self.font_size > CAPTION_FONT_DEFAULT_SIZE:
            self.font_size = CAPTION_FONT_DEFAULT_SIZE
            self.config.set("overlay_font_size", self.font_size)
        self.config.set("overlay_font_profile", CAPTION_FONT_PROFILE)
