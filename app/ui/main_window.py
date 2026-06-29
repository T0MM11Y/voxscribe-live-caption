import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, scrolledtext
from app.ui.dialogs import ask_yes_no, ask_yes_no_cancel, show_error, show_info, show_warning
from typing import Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    import opencc
except ImportError:
    opencc = None

from app.audio.capture import AudioManager
from app.core.config import SimpleConfig
from app.core.languages import (
    AUTO_INPUT_LANGUAGE,
    DEFAULT_INPUT_LANGUAGE,
    DEFAULT_INPUT_LANGUAGE_SETTING,
    DEFAULT_OUTPUT_LANGUAGE,
    DIRECT_TRANSLATION_STRATEGIES,
    INPUT_LANGUAGE_BY_LABEL,
    INPUT_LANGUAGE_REGISTRY,
    OUTPUT_LANGUAGE_BY_LABEL,
    InputLanguageSpec,
    OutputLanguageSpec,
    canonical_language_code,
    input_language_labels,
    output_language_labels,
)
from app.core.locale import _L
from app.core.logging import SimpleLogger
from app.core.state import StateManager
from app.dependencies import (
    DEPENDENCIES_OK,
    MISSING_DEPS,
    dependency_install_command,
    dependency_install_target,
)
from app.integration.openapi import VoxScribeOpenApiServer
from app.recognition.model_manager import ModelManager
from app.recognition.whisper_engine import WhisperRecognizer
from app.services.export import ExportService
from app.services.language_switcher import LanguageSwitcher
from app.services.transcript import TranscriptService
from app.system.profiler import (
    AutoTuner,
    ComputeModeDetector,
    HardwareProbe,
    SystemSpecChecker,
)
from app.translation.service import TranslationManager
from app.ui.subtitle_overlay import SubtitleOverlay


class VoxScribeApp:
    """Main application class"""

    def __init__(self):
        self.logger = SimpleLogger(__name__)
        self.config = SimpleConfig()
        self.hardware_snapshot = HardwareProbe().probe()
        self.performance_profile = AutoTuner().tune(self.hardware_snapshot)
        self.compute_profile = ComputeModeDetector(
            self.hardware_snapshot, self.performance_profile
        ).detect()
        self._apply_compute_mode_profile()
        self.root = None
        self.startup_loading_window = None
        self.startup_loading_status = None
        self.startup_loading_bar = None

        self._run_system_spec_check()

        if not DEPENDENCIES_OK:
            self.root = tk.Tk()
            self.root.withdraw()
            self._handle_missing_dependencies()
            return

        try:
            self.root = ctk.CTk()
            self.root.withdraw()
            self._show_startup_loading(
                "Preparing application interface... "
                f"({self.compute_profile.backend_label})"
            )

            self.model_manager = ModelManager(self.config, self.logger)
            self.audio_manager = AudioManager(self.config, self.logger)
            self.speech_recognizer = WhisperRecognizer(
                self.config, self.model_manager, self.logger
            )
            self.translation_manager = TranslationManager(self.logger)
            self.language_switcher = LanguageSwitcher(
                self.model_manager, self.speech_recognizer, self.logger
            )
            self.state_manager = StateManager(
                {"recognition": "starting", "input_language": DEFAULT_INPUT_LANGUAGE}
            )
            self.transcript_service = TranscriptService()
            self.export_service = ExportService()
            self.integration_api = None
            self.subtitle_overlay = None
            self._update_startup_loading(
                "Initializing audio and speech modules... "
                f"({self.compute_profile.backend_label})"
            )

            self.is_recognizing = False
            self.word_count = 0
            self._backlog_seconds = 0.0
            self.detected_input_language_label = "Auto"
            self.start_time = None
            self.translation_request_counter = 0
            self.latest_preview_translation_id = 0
            self.current_translation_source = ""
            self.current_translation_source_language = ""
            self.current_translation_value = ""
            self.current_translation_target = ""
            self.translation_pending_request_id = 0
            self.stable_translation_segments = []
            self.stable_translation_source_language = ""
            self.stable_translation_started_at = 0.0
            self.stable_translation_last_update_at = 0.0
            self.stable_translation_flush_job = None
            self.model_download_in_progress = False
            self.model_prewarm_in_progress = False
            self.language_switch_in_progress = False
            self.language_switch_target_code = ""
            self.model_prewarm_language_codes = tuple()
            self.model_prewarm_completion_callbacks = []
            self.recognition_ready = False
            self.recognition_start_in_progress = False
            self.audio_warmup_in_progress = False
            self.offline_translation_prepare_in_progress = False
            self.pending_start_after_prewarm = False
            self.pending_start_after_offline_translation = False
            self.transcript_entries = self.transcript_service.entries

            self._setup_gui()
            self.subtitle_overlay = SubtitleOverlay(
                self.root,
                self.config,
                self._toggle_recognition,
                {
                    "get_state": self._overlay_state,
                    "set_input_language": self._overlay_set_input_language,
                    "set_output_language": self._overlay_set_output_language,
                    "save_transcript": self._save_transcript,
                    "clear_transcript": self._clear_transcript,
                    "exit_app": self._on_closing,
                },
            )
            self._enter_overlay_mode()
            self._update_startup_loading("Connecting callbacks and workers...")
            self._setup_callbacks()
            self.speech_recognizer.root = self.root
            self.translation_manager.start(self.root, self._on_translation_result)
            self._start_integration_api()
            self._publish_integration_snapshot()
            self.root.after(300, self._run_startup_model_check)
        except Exception as e:
            self.logger.error(f"Startup failed: {e}")
            self._close_startup_loading()
            self._show_startup_error(e)
            raise

    def _apply_compute_mode_profile(self):
        self.config.set("compute_device", self.compute_profile.device)
        self.config.set("compute_type", self.compute_profile.compute_type)
        self.config.set("compute_backend_label", self.compute_profile.backend_label)
        self.config.set("device_profile", self.performance_profile.name)
        self.config.set("sample_rate", self.performance_profile.sample_rate)
        self.config.set("chunk_size", self.performance_profile.chunk_size)
        self.config.set("audio_queue_size", self.performance_profile.audio_queue_size)
        self.config.set(
            "preload_secondary_model",
            self.performance_profile.preload_secondary_model,
        )
        self.config.set("max_cached_models", self.performance_profile.max_cached_models)
        self.config.save_config()
        self.logger.info(
            "Compute mode selected: "
            f"{self.compute_profile.backend_label} | {self.compute_profile.details}"
        )

    def _show_startup_loading(self, message: str):
        if not self.root:
            return

        overlay = getattr(self, "subtitle_overlay", None)
        if overlay:
            overlay.set_running(self.is_recognizing)
            needs_show = True
            try:
                needs_show = bool(
                    not overlay.window
                    or not overlay.window.winfo_exists()
                    or overlay.placement != "startup"
                )
            except Exception:
                needs_show = True

            if needs_show:
                overlay.show(
                    caption=self._current_caption_text(),
                    placement="startup",
                )
            else:
                overlay.set_caption(self._current_caption_text())
            overlay.set_loading(message)
            return

        try:
            if (
                self.startup_loading_window
                and self.startup_loading_window.winfo_exists()
            ):
                self._update_startup_loading(message)
                return

            self.startup_loading_window = ctk.CTkToplevel(self.root)
            self.startup_loading_window.title("VoxScribe")
            self.startup_loading_window.geometry("420x160")
            self.startup_loading_window.resizable(False, False)
            self.startup_loading_window.transient(self.root)
            self.startup_loading_window.protocol("WM_DELETE_WINDOW", lambda: None)
            try:
                self.startup_loading_window.grab_set()
            except Exception:
                pass

            frame = ctk.CTkFrame(self.startup_loading_window, fg_color="transparent")
            frame.pack(fill="both", expand=True, padx=20, pady=20)

            ctk.CTkLabel(
                frame,
                text="VoxScribe",
                font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            ).pack(anchor="w")

            self.startup_loading_status = tk.StringVar(value=message)
            ctk.CTkLabel(
                frame,
                textvariable=self.startup_loading_status,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color="gray",
            ).pack(anchor="w", pady=(6, 14))

            self.startup_loading_bar = ctk.CTkProgressBar(frame, mode="indeterminate")
            self.startup_loading_bar.pack(fill="x")
            self.startup_loading_bar.start()

            self.startup_loading_window.lift()
            self.startup_loading_window.focus_force()
            self.startup_loading_window.update_idletasks()
        except Exception:
            self.startup_loading_window = None
            self.startup_loading_status = None
            self.startup_loading_bar = None

    def _update_startup_loading(self, message: str):
        overlay = getattr(self, "subtitle_overlay", None)
        if overlay:
            overlay.set_loading(message)
            return

        if not self.startup_loading_window:
            return

        try:
            if self.startup_loading_status:
                self.startup_loading_status.set(message)
            self.startup_loading_window.update_idletasks()
        except Exception:
            pass

    def _close_startup_loading(self):
        if not self.startup_loading_window:
            return

        try:
            if self.startup_loading_bar:
                self.startup_loading_bar.stop()
        except Exception:
            pass

        try:
            self.startup_loading_window.grab_release()
        except Exception:
            pass

        try:
            self.startup_loading_window.destroy()
        except Exception:
            pass

        self.startup_loading_window = None
        self.startup_loading_status = None
        self.startup_loading_bar = None

    def _run_system_spec_check(self):
        """Run PC spec validation before dependency and model checks."""
        checker = SystemSpecChecker(self.compute_profile)
        result = checker.run()

        if result.passed:
            for line in result.lines:
                self.logger.info(f"Startup check: {line}")
            return

        check_root = tk.Tk()
        check_root.title("VoxScribe Startup Check")
        check_root.geometry("560x340")
        check_root.resizable(False, False)
        check_root.configure(bg="#f5f5f5")

        frame = tk.Frame(check_root, bg="#f5f5f5")
        frame.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(
            frame,
            text="Checking PC Specifications",
            font=("Segoe UI", 14, "bold"),
            bg="#f5f5f5",
        ).pack(anchor="w", pady=(0, 10))

        status_text = scrolledtext.ScrolledText(
            frame, height=10, wrap="word", font=("Consolas", 9), bg="white"
        )
        status_text.pack(fill="both", expand=True, pady=(0, 12))
        status_text.insert("end", "\n".join(result.lines))
        status_text.configure(state="disabled")

        status_label = tk.Label(
            frame,
            text=(
                "PC specs passed. "
                f"Compute mode: {self.compute_profile.backend_label}. "
                "Checking dependencies next..."
                if result.passed
                else "PC specs failed. Startup stopped."
            ),
            bg="#f5f5f5",
            font=("Segoe UI", 9, "bold"),
        )
        status_label.pack(anchor="w")

        check_root.update()

        if not result.passed:
            show_error(
                "PC Specifications Not Supported",
                "VoxScribe cannot start because this PC does not meet the minimum requirements.\n\n"
                + "\n".join(result.failures),
                parent=check_root,
            )
            check_root.destroy()
            sys.exit(1)

        check_root.after(900, check_root.destroy)
        check_root.mainloop()

    def _show_startup_error(self, error):
        """Show startup failures instead of exiting silently with a hidden window."""
        try:
            if self.root is None:
                self.root = tk.Tk()
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            show_error(
                "Startup Error",
                "VoxScribe failed to initialize.\n\n"
                f"{error}\n\n"
                "Run the app from a terminal to see the full traceback.",
            )
        except Exception:
            pass

    def _handle_missing_dependencies(self):
        missing_list = ", ".join(MISSING_DEPS)
        install_command = dependency_install_command()
        response = ask_yes_no_cancel(
            "Missing Dependencies",
            f"Required packages are missing:\n{missing_list}\n\n"
            "Would you like to install them automatically?\n\n"
            "Click 'Yes' to install automatically\n"
            f"Click 'No' to install manually: pip install {install_command}\n"
            "Click 'Cancel' to exit",
        )

        if response is True:
            self._install_dependencies()
        elif response is False:
            show_info(
                "Manual Installation",
                f"Please install the missing packages manually:\n\n"
                f"pip install {install_command}\n\n"
                "Then restart the application.",
            )
            sys.exit(0)
        else:
            sys.exit(0)

    def _install_dependencies(self):
        """Install missing dependencies automatically"""
        import subprocess

        install_window = tk.Toplevel(self.root)
        install_window.title("Installing Dependencies")
        install_window.geometry("500x300")
        install_window.resizable(False, False)
        install_window.transient(self.root)
        install_window.grab_set()
        install_window.configure(bg="#f5f5f5")

        main_frame = tk.Frame(install_window, bg="#f5f5f5")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(
            main_frame,
            text="Installing Required Dependencies",
            font=("Segoe UI", 14, "bold"),
            bg="#f5f5f5",
        ).pack(pady=(0, 20))

        status_text = scrolledtext.ScrolledText(
            main_frame, height=10, wrap="word", font=("Consolas", 9), bg="white"
        )
        status_text.pack(fill="both", expand=True, pady=(0, 20))

        progress_label = tk.Label(
            main_frame,
            text="Starting installation...",
            bg="#f5f5f5",
            font=("Segoe UI", 9),
        )
        progress_label.pack()

        def install_thread():
            def update_status(text):
                status_text.insert("end", text + "\n")
                status_text.see("end")
                install_window.update()

            def update_progress(text):
                progress_label.config(text=text)
                install_window.update()

            try:
                update_status("Starting dependency installation...")
                update_progress("Upgrading pip...")

                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                for i, dep in enumerate(MISSING_DEPS, 1):
                    install_target = dependency_install_target(dep)
                    update_progress(f"Installing {dep} ({i}/{len(MISSING_DEPS)})...")
                    update_status(f"\nInstalling {dep}...")

                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", install_target],
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )

                    if result.returncode == 0:
                        update_status(f"OK: {dep} installed successfully")
                    else:
                        update_status(f"FAILED: Could not install {dep}")
                        if result.stderr:
                            update_status(result.stderr)

                update_progress("Installation completed!")
                update_status(
                    "\nInstallation process completed.\nPlease restart the application to continue."
                )

                restart_btn = tk.Button(
                    main_frame,
                    text="Restart Application",
                    command=lambda: (
                        install_window.destroy(),
                        self._restart_application(),
                    ),
                    bg="#4a90e2",
                    fg="white",
                    font=("Segoe UI", 10, "bold"),
                )
                restart_btn.pack(pady=10)

            except Exception as e:
                update_status(f"Installation error: {e}")
                update_progress("Installation failed")

        threading.Thread(target=install_thread, daemon=True).start()

    def _restart_application(self):
        """Restart the application"""
        import subprocess

        try:
            self._on_closing()
            subprocess.Popen([sys.executable] + sys.argv)
            sys.exit(0)
        except Exception as e:
            show_error("Error", f"Failed to restart application: {e}", parent=self.root)
            sys.exit(1)

    def _setup_gui(self):
        """Setup main GUI with customtkinter design"""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root.title("VoxScribe - Real-time Transcription")

        min_width = 850
        min_height = 560
        screen_width = max(1, self.root.winfo_screenwidth())
        screen_height = max(1, self.root.winfo_screenheight())
        max_width = max(720, screen_width - 80)
        max_height = max(560, screen_height - 100)
        saved_width = int(self.config.get("window_width") or min_width)
        saved_height = int(self.config.get("window_height") or min_height)
        window_width = min(max(saved_width, min_width), max_width)
        window_height = min(max(saved_height, min_height), max_height)
        self.root.geometry(f"{window_width}x{window_height}")
        self.root.minsize(min(min_width, max_width), min(min_height, max_height))

        self.colors = {
            "button_bg": "#2563eb",
            "button_hover": "#1d4ed8",
            "muted_button": "#27272a",
            "muted_hover": "#3f3f46",
            "ready": "#10b981",
            "busy": "#f59e0b",
            "live": "#ef4444",
            "error": "#dc2626",
            "stopped": "#52525b",
            "sidebar": "#18181b",
            "main_bg": "#09090b",
        }

        try:
            self.root.configure(fg_color=self.colors["main_bg"])
        except Exception:
            pass

        # 1. SIDEBAR (Left)
        sidebar_frame = ctk.CTkFrame(self.root, width=280, corner_radius=0, fg_color=self.colors["sidebar"])
        sidebar_frame.grid(row=0, column=0, sticky="nsew")

        title_label = ctk.CTkLabel(
            sidebar_frame,
            text="VoxScribe",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold")
        )
        title_label.grid(row=0, column=0, padx=20, pady=(32, 28))

        self.start_stop_btn = ctk.CTkButton(
            sidebar_frame,
            text=_L("Start Transcription"),
            command=self._toggle_recognition,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            height=46,
            fg_color=self.colors["button_bg"],
            hover_color=self.colors["button_hover"],
            state="disabled",
            corner_radius=8
        )
        self.start_stop_btn.grid(row=1, column=0, padx=20, pady=(0, 28), sticky="ew")

        input_language = self.model_manager.get_input_language()
        output_language = self.model_manager.get_output_language()

        self.input_language_var = tk.StringVar(value=input_language.label)
        ctk.CTkLabel(
            sidebar_frame,
            text="Input Language",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="gray"
        ).grid(row=2, column=0, padx=20, pady=(0, 6), sticky="w")

        self.input_language_menu = ctk.CTkOptionMenu(
            sidebar_frame,
            values=input_language_labels(),
            variable=self.input_language_var,
            command=self._on_input_language_change,
            height=38,
            font=ctk.CTkFont(size=13),
            corner_radius=6
        )
        self.input_language_menu.grid(row=3, column=0, padx=20, pady=(0, 16), sticky="ew")

        ctk.CTkLabel(
            sidebar_frame,
            text="Output Language",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="gray"
        ).grid(row=4, column=0, padx=20, pady=(0, 6), sticky="w")

        self.output_language_var = tk.StringVar(value=output_language.label)
        self.output_language_menu = ctk.CTkOptionMenu(
            sidebar_frame,
            values=output_language_labels(),
            variable=self.output_language_var,
            command=self._on_output_language_change,
            height=38,
            font=ctk.CTkFont(size=13),
            corner_radius=6
        )
        self.output_language_menu.grid(row=5, column=0, padx=20, pady=(0, 16), sticky="ew")

        ctk.CTkLabel(
            sidebar_frame,
            text="Audio Source",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="gray"
        ).grid(row=6, column=0, padx=20, pady=(0, 6), sticky="w")

        audio_source_value = self.config.get("audio_source_type", "loopback")
        audio_source_labels = {
            "loopback": "Speaker Output (Loopback)",
            "microphone": "Microphone",
        }
        self.audio_source_var = tk.StringVar(
            value=audio_source_labels.get(audio_source_value, "loopback")
        )
        self.audio_source_menu = ctk.CTkOptionMenu(
            sidebar_frame,
            values=list(audio_source_labels.values()),
            variable=self.audio_source_var,
            command=self._on_audio_source_change,
            height=38,
            font=ctk.CTkFont(size=13),
            corner_radius=6
        )
        self.audio_source_menu.grid(row=7, column=0, padx=20, pady=(0, 20), sticky="ew")

        util_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
        util_frame.grid(row=9, column=0, padx=20, pady=24, sticky="ew")
        util_frame.grid_columnconfigure((0, 1), weight=1)

        self.subtitle_btn = ctk.CTkButton(
            util_frame,
            text="Overlay Mode",
            command=self._show_subtitle_overlay,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=self.colors["muted_button"],
            hover_color=self.colors["muted_hover"],
            height=38,
            corner_radius=6
        )
        self.subtitle_btn.grid(row=0, column=0, columnspan=2, pady=(0, 12), sticky="ew")

        self.save_btn = ctk.CTkButton(
            util_frame,
            text="Save",
            command=self._save_transcript,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=self.colors["muted_button"],
            hover_color=self.colors["muted_hover"],
            height=38,
            corner_radius=6
        )
        self.save_btn.grid(row=1, column=0, padx=(0, 6), sticky="ew")

        self.clear_btn = ctk.CTkButton(
            util_frame,
            text="Clear",
            command=self._clear_transcript,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=self.colors["muted_button"],
            hover_color=self.colors["muted_hover"],
            height=38,
            corner_radius=6
        )
        self.clear_btn.grid(row=1, column=1, padx=(6, 0), sticky="ew")

        self.language_state_var = tk.StringVar(value=f"Active: {input_language.label}")
        self.language_state_label = ctk.CTkLabel(sidebar_frame, textvariable=self.language_state_var)

        # 2. MAIN AREA (Right)
        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.grid(row=0, column=1, sticky="nsew", padx=35, pady=35)
        self._configure_main_window_layout(sidebar_frame, main_frame)

        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        header_frame.grid_columnconfigure(1, weight=1)
        header_frame.bind(
            "<Configure>",
            lambda event: self._update_status_wraplength(event.width),
        )

        self.status_badge_var = tk.StringVar(value=_L("PREPARING"))
        self.status_badge = ctk.CTkLabel(
            header_frame,
            textvariable=self.status_badge_var,
            width=100, height=28,
            corner_radius=6,
            fg_color=self.colors["busy"],
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        )
        self.status_badge.grid(row=0, column=0, sticky="w")

        self.status_var = tk.StringVar(value=_L("STATUS: INITIALIZATION IN PROGRESS"))
        self.status_label = ctk.CTkLabel(
            header_frame,
            textvariable=self.status_var,
            text_color="gray",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            wraplength=self._header_status_wraplength(650),
            justify="left",
            width=1,
        )
        self.status_label.grid(row=0, column=1, sticky="ew", padx=(15, 0))

        self.loading_indicator = ctk.CTkProgressBar(header_frame, mode="indeterminate", width=120, height=4)
        self.loading_indicator_visible = False

        self.stats_var = tk.StringVar(value="Words: 0 | Duration: 00:00:00")
        self.stats_label = ctk.CTkLabel(
            header_frame,
            textvariable=self.stats_var,
            text_color="gray",
            font=ctk.CTkFont(family="Segoe UI", size=13)
        )
        self.stats_label.grid(row=0, column=3, sticky="e", padx=(15, 0))

        live_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        live_frame.grid(row=1, column=0, sticky="ew", pady=(0, 25))

        self.translation_label = ctk.CTkLabel(
            live_frame,
            text=f"Transcription ({output_language.label})",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="gray"
        )
        self.translation_label.pack(anchor="w", pady=(0, 8))

        self.translation_text = ctk.CTkTextbox(
            live_frame,
            height=140,
            wrap="word",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            fg_color="transparent",
            text_color="#ffffff",
            border_width=0,
            activate_scrollbars=False
        )
        self.translation_text.pack(fill="x")
        self._set_textbox_content(self.translation_text, self._default_translation_placeholder())

        self.current_frame_label = ctk.CTkLabel(
            live_frame,
            text=f"Source ({input_language.label})",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="gray"
        )
        self.current_frame_label.pack(anchor="w", pady=(15, 8))

        self.current_text = ctk.CTkTextbox(
            live_frame,
            height=65,
            wrap="word",
            font=ctk.CTkFont(family="Segoe UI", size=15),
            fg_color="transparent",
            text_color="#a1a1aa",
            border_width=0,
            activate_scrollbars=False
        )
        self.current_text.pack(fill="x")
        self._update_source_visibility(input_language.code)

        transcript_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        transcript_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 0))

        self.transcript_label = ctk.CTkLabel(
            transcript_frame,
            text="History",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="gray"
        )
        self.transcript_label.pack(anchor="w", pady=(0, 8))

        self.transcript_text = ctk.CTkTextbox(
            transcript_frame,
            wrap="word",
            font=ctk.CTkFont(family="Segoe UI", size=15),
            border_width=0,
            corner_radius=8,
            fg_color="#18181b",
            text_color="#e4e4e7"
        )
        self.transcript_text.pack(fill="both", expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.bind("<F5>", lambda e: self._toggle_recognition())
        self.root.bind("<Control-s>", lambda e: self._save_transcript())
        try:
            self.root.bind("<Control-Shift-KeyPress-C>", lambda e: self._toggle_subtitle_overlay())
            self.root.bind("<Control-Shift-KeyPress-c>", lambda e: self._toggle_subtitle_overlay())
        except Exception:
            pass

    def _configure_main_window_layout(self, sidebar_frame, main_frame):
        self.root.grid_columnconfigure(0, weight=0, minsize=280)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        try:
            sidebar_frame.grid_propagate(False)
        except Exception:
            pass
        sidebar_frame.grid_columnconfigure(0, weight=1)
        sidebar_frame.grid_rowconfigure(8, weight=1)

        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)

    def _header_status_wraplength(self, header_width: int) -> int:
        try:
            width = int(header_width)
        except Exception:
            width = 650
        return max(160, min(520, width - 430))

    def _update_status_wraplength(self, header_width: int):
        label = getattr(self, "status_label", None)
        if not label:
            return
        try:
            label.configure(wraplength=self._header_status_wraplength(header_width))
        except Exception:
            pass

    def _setup_callbacks(self):
        """Setup speech recognition callbacks"""
        self.speech_recognizer.set_callbacks(
            final_callback=self._on_final_result,
            error_callback=self._on_error,
            backlog_callback=self._on_backlog_update,
        )

    def _enter_overlay_mode(self):
        if not self.root:
            return

        self._close_startup_loading()
        try:
            self.root.withdraw()
        except Exception:
            pass

        self._show_subtitle_overlay(compact=True)

    def _show_main_window(self):
        if not self.root:
            return

        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _overlay_state(self) -> dict:
        availability = self._control_availability()
        input_language = self.model_manager.get_input_language()
        output_language = self.model_manager.get_output_language()
        state_status = (
            self.state_manager.get("status", "ready")
            if hasattr(self, "state_manager")
            else "ready"
        )
        status = (
            "switching"
            if availability["language_switch_in_progress"]
            else ("live" if self.is_recognizing else state_status)
        )
        status_message = (
            self.state_manager.get("status_message", "")
            if hasattr(self, "state_manager")
            else ""
        )
        try:
            stats = self.stats_var.get()
        except Exception:
            stats = ""

        return {
            "status": status,
            "status_message": status_message,
            "is_recognizing": self.is_recognizing,
            "input_label": input_language.label,
            "output_label": output_language.label,
            "input_labels": input_language_labels(),
            "output_labels": output_language_labels(),
            "transcript": self.transcript_service.render(),
            "stats": stats,
            **availability,
        }

    def _overlay_set_input_language(self, selected_label: str):
        self._on_input_language_change(selected_label)
        self._refresh_overlay_panel()

    def _overlay_set_output_language(self, selected_label: str):
        self._on_output_language_change(selected_label)
        self._refresh_overlay_panel()

    def _refresh_overlay_panel(self):
        overlay = getattr(self, "subtitle_overlay", None)
        if overlay:
            overlay.refresh()

    def _show_subtitle_overlay(self, compact: Optional[bool] = None):
        overlay = getattr(self, "subtitle_overlay", None)
        if not overlay:
            return

        overlay.set_running(self.is_recognizing)
        overlay.set_status(
            getattr(self, "state_manager", None).get("status", "ready")
            if hasattr(getattr(self, "state_manager", None), "get")
            else ("live" if self.is_recognizing else "ready")
        )
        overlay.show(caption=self._current_caption_text(), compact=compact)

    def _toggle_subtitle_overlay(self):
        overlay = getattr(self, "subtitle_overlay", None)
        if not overlay:
            return

        if overlay.window and overlay.window.winfo_exists():
            overlay.toggle_compact()
            return

        self._show_subtitle_overlay()

    def _current_caption_text(self) -> str:
        try:
            if hasattr(self, "translation_text") and self.translation_text:
                text = self.translation_text.get("1.0", "end-1c").strip()
                if text:
                    return text
        except Exception:
            pass
        return "Processing..." if self.is_recognizing else "Press Start to begin transcription."

    def _sync_subtitle_caption(self, text: str):
        overlay = getattr(self, "subtitle_overlay", None)
        if overlay:
            overlay.set_caption(text)
        self._publish_integration_snapshot()

    def _current_input_language_code(self) -> str:
        return self.model_manager.get_input_language_code()

    def _current_output_language_code(self) -> str:
        return self.model_manager.get_output_language_code()

    def _current_output_language(self) -> OutputLanguageSpec:
        return self.model_manager.get_output_language()

    def _translation_progress_text(self) -> str:
        return f"Menerjemahkan ke {self._current_output_language().label}..."

    def _requires_opencc_for_language_pair(
        self, input_language: InputLanguageSpec, output_language: OutputLanguageSpec
    ) -> bool:
        strategies = [
            input_language.recognition_strategy,
            output_language.output_strategy,
        ]
        direct_strategy = DIRECT_TRANSLATION_STRATEGIES.get(
            (input_language.code, output_language.code)
        )
        if direct_strategy:
            strategies.append(direct_strategy)
        return any(strategy.requires_opencc for strategy in strategies)

    def _can_produce_current_output(
        self, source_language_code: Optional[str] = None
    ) -> bool:
        source_code = source_language_code or self._current_input_language_code()
        return self.translation_manager.can_resolve(
            source_code, self._current_output_language_code()
        )

    def _system_busy_flags(self) -> dict:
        return {
            "model_download_in_progress": bool(
                getattr(self, "model_download_in_progress", False)
            ),
            "model_prewarm_in_progress": bool(
                getattr(self, "model_prewarm_in_progress", False)
            ),
            "audio_warmup_in_progress": bool(
                getattr(self, "audio_warmup_in_progress", False)
            ),
            "recognition_start_in_progress": bool(
                getattr(self, "recognition_start_in_progress", False)
            ),
            "language_switch_in_progress": bool(
                getattr(self, "language_switch_in_progress", False)
            ),
            "pending_start_after_prewarm": bool(
                getattr(self, "pending_start_after_prewarm", False)
            ),
            "offline_translation_prepare_in_progress": bool(
                getattr(self, "offline_translation_prepare_in_progress", False)
            ),
            "pending_start_after_offline_translation": bool(
                getattr(self, "pending_start_after_offline_translation", False)
            ),
        }

    def _control_availability(self) -> dict:
        flags = self._system_busy_flags()
        try:
            current_status = self.state_manager.get("status", "")
        except Exception:
            current_status = ""
        status_busy = current_status in {"busy", "switching"}
        engine_busy = any(flags.values()) or status_busy
        recognition_action_disabled = bool(
            flags["model_download_in_progress"]
            or flags["model_prewarm_in_progress"]
            or flags["audio_warmup_in_progress"]
            or flags["recognition_start_in_progress"]
            or flags["language_switch_in_progress"]
            or flags["pending_start_after_prewarm"]
            or flags["offline_translation_prepare_in_progress"]
            or flags["pending_start_after_offline_translation"]
            or status_busy
        )
        language_disabled = engine_busy
        transcript_actions_disabled = engine_busy

        return {
            **flags,
            "system_busy": engine_busy,
            "recognition_action_disabled": recognition_action_disabled,
            "input_language_disabled": language_disabled,
            "output_language_disabled": language_disabled,
            "transcript_actions_disabled": transcript_actions_disabled,
        }

    def _sync_control_availability(self):
        availability = self._control_availability()

        start_button = getattr(self, "start_stop_btn", None)
        if start_button:
            start_button.configure(
                state=(
                    "disabled"
                    if availability["recognition_action_disabled"]
                    else "normal"
                )
            )

        for button_name in ("clear_btn", "save_btn"):
            button = getattr(self, button_name, None)
            if button:
                button.configure(
                    state=(
                        "disabled"
                        if availability["transcript_actions_disabled"]
                        else "normal"
                    )
                )

        subtitle_button = getattr(self, "subtitle_btn", None)
        if subtitle_button:
            subtitle_button.configure(state="normal")

        self._set_language_controls_state("normal")

    def _busy_action_message(self) -> str:
        try:
            message = self.state_manager.get("status_message", "")
            if message:
                return message
        except Exception:
            pass
        try:
            if hasattr(self, "status_var") and self.status_var.get():
                return self.status_var.get()
        except Exception:
            pass
        return "Please wait until preparation finishes."

    def _show_action_blocked_hint(self):
        message = self._busy_action_message()
        state = (
            "switching"
            if getattr(self, "language_switch_in_progress", False)
            else "busy"
        )
        self._set_status_state(state, message)

    def _set_language_controls_state(self, state: str):
        availability = self._control_availability()
        for menu_name in ("input_language_menu", "output_language_menu"):
            menu = getattr(self, menu_name, None)
            if menu:
                if state == "disabled":
                    target_state = "disabled"
                elif menu_name == "input_language_menu":
                    target_state = (
                        "disabled"
                        if availability["input_language_disabled"]
                        else "normal"
                    )
                else:
                    target_state = (
                        "disabled"
                        if availability["output_language_disabled"]
                        else "normal"
                    )
                menu.configure(state=target_state)

    def _set_start_button_idle(
        self, state: str = "normal", text: str = _L("Start Transcription")
    ):
        button = getattr(self, "start_stop_btn", None)
        if not button:
            return

        button_bg = getattr(self, "colors", {}).get("button_bg", "#1f538d")
        button.configure(
            text=text,
            state=state,
            fg_color=button_bg,
            hover_color=getattr(self, "colors", {}).get("button_hover", "#1a4677"),
        )

    def _set_status_state(self, state: str, message: Optional[str] = None):
        label_map = {
            "busy": _L("PREPARING"),
            "ready": _L("READY"),
            "live": _L("ACTIVE"),
            "switching": _L("SWITCHING"),
            "error": _L("ERROR"),
            "stopped": _L("STOPPED"),
        }
        color_map = {
            "busy": getattr(self, "colors", {}).get("busy", "#946200"),
            "ready": getattr(self, "colors", {}).get("ready", "#2e7d32"),
            "live": getattr(self, "colors", {}).get("live", "#c62828"),
            "switching": "#5b4b8a",
            "error": getattr(self, "colors", {}).get("error", "#b3261e"),
            "stopped": getattr(self, "colors", {}).get("stopped", "#4b5563"),
        }

        if hasattr(self, "status_badge_var"):
            self.status_badge_var.set(label_map.get(state, "STATUS"))
        badge = getattr(self, "status_badge", None)
        if badge:
            badge.configure(fg_color=color_map.get(state, color_map["stopped"]))
        if message and hasattr(self, "status_var"):
            self.status_var.set(message)
        if hasattr(self, "state_manager"):
            self.state_manager.update(status=state, status_message=message or "")
        overlay = getattr(self, "subtitle_overlay", None)
        if overlay:
            overlay.set_status(state, message)
            if state == "live":
                overlay.set_running(True)
            elif state in {"ready", "stopped", "error"}:
                overlay.set_running(False)
        self._sync_control_availability()
        self._publish_integration_snapshot()

    def _show_loading_indicator(self, message: Optional[str] = None):
        self._set_status_state("busy", message)
        overlay = getattr(self, "subtitle_overlay", None)
        if overlay and message:
            overlay.set_loading(message)

        indicator = getattr(self, "loading_indicator", None)
        if not indicator:
            return

        try:
            if not getattr(self, "loading_indicator_visible", False):
                indicator.grid(row=0, column=2, sticky="ew", padx=(12, 0))
                self.loading_indicator_visible = True
            indicator.start()
        except Exception:
            pass

    def _hide_loading_indicator(self):
        overlay = getattr(self, "subtitle_overlay", None)
        if overlay:
            overlay.clear_loading()

        indicator = getattr(self, "loading_indicator", None)
        if not indicator:
            return

        try:
            indicator.stop()
        except Exception:
            pass

        try:
            if getattr(self, "loading_indicator_visible", False):
                indicator.grid_remove()
                self.loading_indicator_visible = False
        except Exception:
            pass

    def _set_recognition_waiting(
        self,
        message: str,
        button_text: str = "Preparing...",
        disable_languages: bool = True,
        show_startup_loading: bool = False,
    ):
        self.recognition_ready = False

        button = getattr(self, "start_stop_btn", None)
        if button and not self.is_recognizing:
            button_bg = getattr(self, "colors", {}).get("button_bg", "#1f538d")
            button.configure(
                text=button_text,
                state="disabled",
                fg_color=button_bg,
                hover_color=getattr(self, "colors", {}).get("button_hover", "#1a4677"),
            )

        if disable_languages and not self.is_recognizing:
            self._set_language_controls_state("disabled")

        self._show_loading_indicator(message)
        if show_startup_loading or self.startup_loading_window:
            self._show_startup_loading(message)
            self._update_startup_loading(message)

    def _set_recognition_ready(self, message: str = "Ready - Click Start Transcription"):
        self.recognition_ready = True
        self.recognition_start_in_progress = False
        self.audio_warmup_in_progress = False
        self.pending_start_after_offline_translation = False
        self._hide_loading_indicator()
        self._close_startup_loading()

        if not self.is_recognizing:
            self._set_start_button_idle("normal")
            self._set_language_controls_state("normal")
            self._set_status_state("ready", message)
            overlay = getattr(self, "subtitle_overlay", None)
            if overlay and getattr(overlay, "placement", "default") == "startup":
                overlay.show(placement="default")

    def _set_recognition_unavailable(self, message: str):
        self.recognition_ready = False
        self.recognition_start_in_progress = False
        self.audio_warmup_in_progress = False
        self.offline_translation_prepare_in_progress = False
        self.pending_start_after_prewarm = False
        self.pending_start_after_offline_translation = False
        self._hide_loading_indicator()
        self._close_startup_loading()

        if not self.is_recognizing:
            self._set_start_button_idle("normal", text="Retry Start")
            self._set_language_controls_state("normal")
            self._set_status_state("error", message)

    def _is_current_model_ready(self) -> bool:
        if not hasattr(self, "speech_recognizer"):
            return False

        return bool(
            getattr(self, "speech_recognizer", None)
            and getattr(self.speech_recognizer, "model_loaded", False)
        )

    def _is_audio_ready(self) -> bool:
        return bool(
            hasattr(self, "audio_manager") and self.audio_manager.is_initialized()
        )

    def _schedule_audio_warmup(
        self,
        status_text: str = "Preparing audio device...",
        show_startup_loading: bool = False,
    ):
        if not hasattr(self, "audio_manager"):
            self._set_recognition_unavailable("Audio system is not available")
            return

        if self._is_audio_ready():
            if self.pending_start_after_prewarm and not self.is_recognizing:
                self.pending_start_after_prewarm = False
                self._hide_loading_indicator()
                self._close_startup_loading()
                self._start_recognition()
                return

            if not self.is_recognizing:
                self._set_recognition_ready()
            return

        if self.audio_warmup_in_progress:
            self._set_recognition_waiting(
                status_text,
                button_text="Preparing...",
                show_startup_loading=show_startup_loading,
            )
            return

        self.audio_warmup_in_progress = True
        self._set_recognition_waiting(
            status_text,
            button_text="Preparing...",
            show_startup_loading=show_startup_loading,
        )

        def audio_warmup_worker():
            success = self.audio_manager.initialize(probe_recorder=True)

            def finalize():
                self.audio_warmup_in_progress = False

                if not success:
                    self._set_recognition_unavailable(
                        "Audio device not ready. Check Windows output device and retry."
                    )
                    return

                if self.pending_start_after_prewarm and not self.is_recognizing:
                    self.pending_start_after_prewarm = False
                    self._hide_loading_indicator()
                    self._close_startup_loading()
                    self._start_recognition()
                    return

                if not self.is_recognizing:
                    self._set_recognition_ready()

            if self.root and hasattr(self.root, "after"):
                self.root.after(0, finalize)

        threading.Thread(target=audio_warmup_worker, daemon=True).start()

    def _run_startup_model_check(self):
        """Check the active speech model after GUI/dependencies are ready."""
        if not self.root or not hasattr(self, "model_manager"):
            self._close_startup_loading()
            return

        input_language = self.model_manager.get_input_language()
        self._set_recognition_waiting(
            f"Checking {input_language.label} model and audio device...",
            button_text="Checking...",
            show_startup_loading=True,
        )

        if self.model_manager.is_model_available():
            status_text = (
                f"Preparing {input_language.label} model for startup..."
                if self._has_startup_model_prepared()
                else f"First-time preparation for {input_language.label} model..."
            )
            self._set_recognition_waiting(
                status_text,
                button_text="Preparing...",
                show_startup_loading=True,
            )
            self._schedule_model_prewarm(
                status_text,
                show_startup_loading=True,
            )
            return

        self._set_recognition_waiting(
            f"{input_language.label} model is missing. Opening download...",
            button_text="Downloading...",
            show_startup_loading=True,
        )
        self.root.after(
            50,
            lambda: self._download_model(
                self._current_input_language_code(), auto=True, startup_layout=True
            ),
        )

    def _startup_model_ready_key(self, language_code: Optional[str] = None) -> str:
        if not hasattr(self, "model_manager"):
            return ""

        try:
            codes = self.model_manager.get_recognition_language_codes(language_code)
            parts = []
            for code in codes:
                spec = self.model_manager.get_model_spec(code)
                model_path = self.model_manager.get_model_path(code)
                if not model_path:
                    return ""
                parts.append(f"{code}:{spec.key}:{Path(model_path).name}")
            return "|".join(parts)
        except Exception:
            return ""

    def _startup_model_markers(self) -> dict:
        markers = self.config.get("startup_prepared_model_keys", {})
        return dict(markers) if isinstance(markers, dict) else {}

    def _has_startup_model_prepared(self, language_code: Optional[str] = None) -> bool:
        key = self._startup_model_ready_key(language_code)
        if not key:
            return False
        return bool(self._startup_model_markers().get(key))

    def _mark_startup_model_prepared(self, language_code: Optional[str] = None):
        key = self._startup_model_ready_key(language_code)
        if not key:
            return
        markers = self._startup_model_markers()
        markers[key] = int(time.time())
        self.config.set("startup_prepared_model_keys", markers)
        self.config.save_config()

    def _ensure_selected_model_available(
        self,
        start_after_ready: bool = False,
        prepare_audio: bool = True,
    ) -> bool:
        """Ensure Whisper model and audio device are ready."""
        if not self.model_manager.is_model_available():
            if self.model_download_in_progress:
                if start_after_ready:
                    self.pending_start_after_prewarm = True
                return False
            if start_after_ready:
                self.pending_start_after_prewarm = True
            self._download_model(self._current_input_language_code(), auto=True)
            return False

        if not self._is_current_model_ready():
            if start_after_ready:
                self.pending_start_after_prewarm = True
            self._schedule_model_prewarm(
                "Preparing Whisper model...",
                prepare_audio_after=prepare_audio,
            )
            return False

        if not self._is_audio_ready() and prepare_audio:
            if start_after_ready:
                self.pending_start_after_prewarm = True
            self._schedule_audio_warmup(
                "Preparing audio device..."
            )
            return False

        if not self.is_recognizing and not self.model_prewarm_in_progress:
            self._set_recognition_ready()
        return True

    def _schedule_model_prewarm(
        self,
        status_text: str = "Preparing speech model...",
        show_startup_loading: bool = False,
        completion_callback=None,
        prepare_audio_after: bool = True,
    ):
        if not hasattr(self, "speech_recognizer"):
            if completion_callback:
                completion_callback(False)
            return

        language_codes = tuple(self.model_manager.get_recognition_language_codes())
        if not language_codes:
            if completion_callback:
                completion_callback(False)
            return

        if completion_callback:
            self.model_prewarm_completion_callbacks.append(completion_callback)

        already_loaded = bool(
            getattr(self.speech_recognizer, "model_loaded", False)
        )
        if already_loaded:
            callbacks = list(self.model_prewarm_completion_callbacks)
            self.model_prewarm_completion_callbacks = []
            for callback in callbacks:
                try:
                    callback(True)
                except Exception as e:
                    self.logger.error(f"Prewarm completion callback failed: {e}")
            if not self.is_recognizing:
                if prepare_audio_after:
                    self._schedule_audio_warmup(
                        "Preparing audio device before starting transcription..."
                        if self.pending_start_after_prewarm
                        else "Preparing audio device...",
                        show_startup_loading=show_startup_loading,
                    )
                else:
                    self._set_recognition_ready()
            return

        if self.model_prewarm_in_progress:
            self._set_recognition_waiting(
                status_text,
                show_startup_loading=show_startup_loading,
            )
            return

        self.model_prewarm_in_progress = True
        self.model_prewarm_language_codes = language_codes

        self._set_recognition_waiting(
            status_text,
            show_startup_loading=show_startup_loading,
        )

        def prewarm_worker():
            success = self.speech_recognizer.load_model()

            def finalize():
                self.model_prewarm_in_progress = False
                self.model_prewarm_language_codes = tuple()
                callbacks = list(self.model_prewarm_completion_callbacks)
                self.model_prewarm_completion_callbacks = []

                if success:
                    self._mark_startup_model_prepared()
                    for callback in callbacks:
                        try:
                            callback(True)
                        except Exception as e:
                            self.logger.error(
                                f"Prewarm completion callback failed: {e}"
                            )
                    if not self.is_recognizing:
                        if prepare_audio_after:
                            self._schedule_audio_warmup(
                                "Preparing audio device before starting transcription..."
                                if self.pending_start_after_prewarm
                                else "Preparing audio device...",
                                show_startup_loading=show_startup_loading,
                            )
                        else:
                            self._set_recognition_ready()
                    return
                else:
                    self._set_recognition_unavailable("Failed to prepare speech model")

                for callback in callbacks:
                    try:
                        callback(success)
                    except Exception as e:
                        self.logger.error(f"Prewarm completion callback failed: {e}")

            if self.root and hasattr(self.root, "after"):
                self.root.after(0, finalize)

        threading.Thread(target=prewarm_worker, daemon=True).start()

    def _reset_translation_state(self, clear_caption: bool = True):
        self.latest_preview_translation_id = 0
        self.translation_pending_request_id = 0
        self.current_translation_source = ""
        self.current_translation_source_language = ""
        self.current_translation_value = ""
        self.current_translation_target = ""
        self._reset_stable_translation_buffer()
        if clear_caption and hasattr(self, "translation_text"):
            self._set_textbox_content(
                self.translation_text, self._default_translation_placeholder()
            )

    def _set_language_state_text(
        self, active_language_label: str, preparing_language_label: Optional[str] = None
    ):
        if not hasattr(self, "language_state_var"):
            return

        if preparing_language_label:
            self.language_state_var.set(
                f"Active: {active_language_label} | Preparing: {preparing_language_label}"
            )
            return

        self.language_state_var.set(f"Active: {active_language_label}")

    def _set_source_label(self, language_code: Optional[str] = None):
        if not hasattr(self, "current_frame_label"):
            return

        try:
            language = self.model_manager.get_input_language(
                language_code or self._current_input_language_code()
            )
            self.current_frame_label.configure(text=f"Source: {language.label}")
            self._update_source_visibility(language.code)
        except Exception:
            pass

    def _update_source_visibility(self, source_language_code: Optional[str] = None):
        if not hasattr(self, "current_frame_label") or not hasattr(self, "current_text"):
            return
        try:
            source_code = source_language_code or self._current_input_language_code()
            output_language = self._current_output_language()
            same_language = source_code == output_language.code
            if same_language:
                self.current_frame_label.pack_forget()
                self.current_text.pack_forget()
                self.translation_label.configure(text=f"Transcription ({output_language.label})")
            else:
                if not self.current_frame_label.winfo_manager():
                    self.current_frame_label.pack(anchor="w", pady=(15, 8))
                if not self.current_text.winfo_manager():
                    self.current_text.pack(fill="x")
                self.translation_label.configure(text=f"Translation: {output_language.label}")
        except Exception:
            pass

    def _on_input_language_change(self, selected_label: str):
        code = INPUT_LANGUAGE_BY_LABEL.get(selected_label, DEFAULT_INPUT_LANGUAGE)
        current_language = self.model_manager.get_input_language()

        if self._control_availability()["input_language_disabled"]:
            self.input_language_var.set(current_language.label)
            self._show_action_blocked_hint()
            self._refresh_overlay_panel()
            return

        if code == current_language.code:
            return

        new_language = self.model_manager.get_input_language(code)
        self.config.set("input_language", code)
        self.config.set("language", code)
        self.config.save_config()
        self.state_manager.set("input_language", code)
        self._reset_translation_state(clear_caption=self.is_recognizing)

        if self.is_recognizing:
            success = self.speech_recognizer.switch_language(code)
            if success:
                self._set_language_state_text(new_language.label)
                self._set_source_label(code)
                self._set_status_state(
                    "live", f"Processing ({new_language.label})... Press F5 to stop"
                )
                self.logger.info(f"Live language switch completed: {new_language.label}")
                overlay = getattr(self, "subtitle_overlay", None)
                if overlay:
                    overlay.flash_language_change("input", new_language.label)
            else:
                self.input_language_var.set(current_language.label)
                self.logger.error(f"Language switch failed for {new_language.label}")
        else:
            self._set_language_state_text(new_language.label)
            self._set_source_label(code)
            self._ensure_selected_model_available(prepare_audio=False)
            overlay = getattr(self, "subtitle_overlay", None)
            if overlay:
                overlay.flash_language_change("input", new_language.label)

        self._refresh_overlay_panel()

    def _on_output_language_change(self, selected_label: str):
        code = OUTPUT_LANGUAGE_BY_LABEL.get(selected_label, DEFAULT_OUTPUT_LANGUAGE)
        current_output_language = self.model_manager.get_output_language()

        if self._control_availability()["output_language_disabled"]:
            self.output_language_var.set(current_output_language.label)
            self._show_action_blocked_hint()
            self._refresh_overlay_panel()
            return

        output_language = self.model_manager.get_output_language(code)

        self.config.set("output_language", code)
        self.config.save_config()
        self._reset_translation_state()
        self.translation_label.configure(text=f"Translation: {output_language.label}")
        status_state = (
            "live"
            if self.is_recognizing
            else ("ready" if self.recognition_ready else "stopped")
        )
        self._set_status_state(
            status_state, f"Output language: {output_language.label}"
        )
        self.logger.info(f"Output language changed to {output_language.label}")
        overlay = getattr(self, "subtitle_overlay", None)
        if overlay:
            overlay.flash_language_change("output", output_language.label)

    def _on_audio_source_change(self, selected_label: str):
        label_to_value = {
            "Speaker Output (Loopback)": "loopback",
            "Microphone": "microphone",
        }
        new_value = label_to_value.get(selected_label, "loopback")
        current_value = str(self.config.get("audio_source_type", "loopback") or "loopback")
        if new_value == current_value:
            return

        was_recognizing = self.is_recognizing
        if was_recognizing:
            self._stop_recognition()

        self.config.set("audio_source_type", new_value)
        self.config.save_config()

        try:
            self.audio_manager.source_type = new_value
        except Exception:
            pass
        self.audio_manager.initialize(force_refresh=True, probe_recorder=True)

        source_label = "Speaker Output" if new_value == "loopback" else "Microphone"
        self.logger.info(f"Audio source changed to {source_label}")
        self._set_status_state(
            "ready" if self.recognition_ready else "stopped",
            f"Audio source: {source_label}",
        )

        if was_recognizing:
            self._start_recognition()

    def _default_translation_placeholder(self) -> str:
        output_language = self._current_output_language()
        input_language = self.model_manager.get_input_language()
        if self.translation_manager.can_resolve(
            input_language.code, output_language.code
        ):
            return f"{output_language.label} transcription will appear here."

        if (
            self._requires_opencc_for_language_pair(input_language, output_language)
            and opencc is None
        ):
            return "Install 'opencc-python-reimplemented' for Mandarin Traditional."

        return (
            "Install 'deep-translator' to enable "
            f"{output_language.label}."
        )

    def _set_textbox_content(self, widget, text: str):
        if not widget:
            return

        safe_text = text or ""
        try:
            if widget.get("1.0", "end-1c") == safe_text:
                if widget is getattr(self, "translation_text", None):
                    self._sync_subtitle_caption(safe_text)
                return
        except Exception:
            pass

        widget.delete("1.0", "end")
        if safe_text:
            widget.insert("1.0", safe_text)
        if widget is getattr(self, "translation_text", None):
            self._sync_subtitle_caption(safe_text)
        self._publish_integration_snapshot()

    def _next_translation_request_id(self) -> int:
        self.translation_request_counter += 1
        return self.translation_request_counter

    def _cancel_stable_translation_flush(self):
        if self.stable_translation_flush_job and self.root:
            try:
                self.root.after_cancel(self.stable_translation_flush_job)
            except Exception:
                pass
        self.stable_translation_flush_job = None

    def _reset_stable_translation_buffer(self):
        self._cancel_stable_translation_flush()
        self.stable_translation_segments = []
        self.stable_translation_source_language = ""
        self.stable_translation_started_at = 0.0
        self.stable_translation_last_update_at = 0.0

    def _append_stable_translation_segment(
        self, text: str, source_language_code: str
    ):
        clean_text = (text or "").strip()
        if not clean_text:
            return

        source_code = source_language_code or self._current_input_language_code()
        if (
            self.stable_translation_segments
            and source_code != self.stable_translation_source_language
        ):
            self._flush_stable_translation_buffer(force=True)

        now = time.time()
        if not self.stable_translation_segments:
            self.stable_translation_started_at = now
            self.stable_translation_source_language = source_code

        self.stable_translation_segments.append(clean_text)
        self.stable_translation_last_update_at = now
        source_text = self._stable_translation_source_text()

        if self._should_flush_stable_translation(source_text, now):
            self._schedule_stable_translation_flush(0)
            return

        self._schedule_stable_translation_flush(
            self._stable_translation_next_delay_ms(source_text)
        )

    def _stable_translation_source_text(self) -> str:
        return " ".join(
            segment.strip()
            for segment in self.stable_translation_segments
            if segment.strip()
        ).strip()

    def _should_flush_stable_translation(self, source_text: str, now: float) -> bool:
        clean_text = (source_text or "").strip()
        if not clean_text:
            return False

        source_code = (
            self.stable_translation_source_language
            or self._current_input_language_code()
        )
        profile = self._chunk_profile(source_code)
        if self._ends_sentence(clean_text):
            return True

        unit_count = self._chunk_unit_count(clean_text, source_code)
        if unit_count >= profile["max_units"]:
            return True

        elapsed_ms = self._stable_translation_elapsed_ms(now)
        if unit_count >= profile["ideal_min_units"]:
            short_delay_ms = self._stable_short_delay_ms(source_code)
            if elapsed_ms >= short_delay_ms:
                return True

        max_delay_ms = self._stable_max_delay_ms(source_code)
        return elapsed_ms >= max_delay_ms

    def _stable_translation_next_delay_ms(self, source_text: str) -> int:
        source_code = (
            self.stable_translation_source_language
            or self._current_input_language_code()
        )
        profile = self._chunk_profile(source_code)
        unit_count = self._chunk_unit_count(source_text, source_code)
        if unit_count >= profile["ideal_min_units"]:
            return self._stable_short_delay_ms(source_code)
        return self._stable_flush_delay_ms(source_code)

    def _stable_translation_elapsed_ms(self, now: Optional[float] = None) -> float:
        if not self.stable_translation_started_at:
            return 0.0
        reference_time = time.time() if now is None else now
        return max(0.0, (reference_time - self.stable_translation_started_at) * 1000)

    def _stable_translation_retry_delay_ms(self) -> int:
        source_code = (
            self.stable_translation_source_language
            or self._current_input_language_code()
        )
        max_delay_ms = self._stable_max_delay_ms(source_code)
        remaining_ms = max_delay_ms - self._stable_translation_elapsed_ms()
        if remaining_ms <= 0:
            return 0
        return max(250, int(remaining_ms))

    def _chunk_profile(self, source_language_code: str) -> dict:
        if self._is_zh_to_en_pair(source_language_code):
            return {
                "min_units": 24,
                "ideal_min_units": 42,
                "max_units": int(
                    self.config.get("zh_en_stable_translation_max_chars", 180)
                ),
            }
        if self._is_cjk_language(source_language_code):
            return {
                "min_units": 12,
                "ideal_min_units": 22,
                "max_units": int(self.config.get("stable_translation_max_chars", 96)),
            }
        return {"min_units": 5, "ideal_min_units": 9, "max_units": 26}

    def _is_zh_to_en_pair(self, source_language_code: str) -> bool:
        latency_profile = str(
            self.config.get("translation_latency_profile", "responsive") or "responsive"
        ).strip().lower()
        if latency_profile != "quality":
            return False
        if not bool(self.config.get("zh_en_accuracy_mode", False)):
            return False
        if not getattr(self, "model_manager", None):
            return False
        source_code = (source_language_code or "").lower()
        target_code = self._current_output_language_code()
        return source_code in {"zh-cn", "zh-tw", "zh"} and target_code == "en"

    def _stable_flush_delay_ms(self, source_language_code: str) -> int:
        if self._is_zh_to_en_pair(source_language_code):
            return int(
                self.config.get("zh_en_stable_translation_flush_delay_ms", 1450)
            )
        return int(self.config.get("stable_translation_flush_delay_ms", 650))

    def _stable_short_delay_ms(self, source_language_code: str) -> int:
        if self._is_zh_to_en_pair(source_language_code):
            return int(
                self.config.get("zh_en_stable_translation_short_delay_ms", 1150)
            )
        return int(self.config.get("stable_translation_short_delay_ms", 450))

    def _stable_max_delay_ms(self, source_language_code: str) -> int:
        if self._is_zh_to_en_pair(source_language_code):
            return int(
                self.config.get("zh_en_stable_translation_max_delay_ms", 5200)
            )
        return int(self.config.get("stable_translation_max_delay_ms", 2200))

    def _chunk_unit_count(self, text: str, source_language_code: str) -> int:
        clean_text = (text or "").strip()
        if not clean_text:
            return 0
        if self._is_cjk_language(source_language_code):
            cjk_count = sum(1 for char in clean_text if self._is_cjk_char(char))
            return cjk_count or len(clean_text)
        return len(clean_text.split())

    def _is_cjk_language(self, source_language_code: str) -> bool:
        return source_language_code in {"zh-cn", "zh-tw", "zh"}

    def _is_cjk_char(self, char: str) -> bool:
        return (
            "\u2e80" <= char <= "\u9fff"
            or "\uf900" <= char <= "\ufaff"
            or "\uff00" <= char <= "\uffef"
        )

    def _ends_sentence(self, text: str) -> bool:
        return (text or "").strip().endswith(
            (".", "?", "!", "\u3002", "\uff1f", "\uff01", "\u2026")
        )

    def _schedule_stable_translation_flush(self, delay_ms: int):
        self._cancel_stable_translation_flush()
        if not self.root:
            return
        self.stable_translation_flush_job = self.root.after(
            max(0, int(delay_ms)), self._flush_stable_translation_buffer
        )

    def _flush_stable_translation_buffer(self, force: bool = False):
        self._cancel_stable_translation_flush()
        source_language_code = (
            self.stable_translation_source_language
            or self._current_input_language_code()
        )
        source_buffer_text = self._stable_translation_source_text()
        if not source_buffer_text:
            return

        max_delay_ms = self._stable_max_delay_ms(source_language_code)
        if not force and self._stable_translation_elapsed_ms() >= max_delay_ms:
            force = True

        source_text, remainder_text = self._take_stable_translation_chunk(
            source_language_code, force=force
        )

        if not source_text:
            if remainder_text:
                self._schedule_stable_translation_flush(
                    self._stable_translation_retry_delay_ms()
                )
            return

        output_language = self._current_output_language()
        timestamp = time.strftime("%H:%M:%S")
        request_id = self._next_translation_request_id()
        self.latest_preview_translation_id = request_id

        entry = self.transcript_service.add_entry(
            request_id,
            timestamp,
            source_text,
            output_language.code,
            output_language.transcript_label,
            self._translation_progress_text(),
        )

        cached_translation = None
        if (
            source_text == self.current_translation_source
            and self.current_translation_value
            and output_language.code == self.current_translation_target
        ):
            cached_translation = self.current_translation_value

        if cached_translation:
            entry["translation"] = cached_translation
            self.translation_pending_request_id = 0
            self._set_textbox_content(self.translation_text, cached_translation)
        elif source_language_code == output_language.code:
            entry["translation"] = source_text
            self.translation_pending_request_id = 0
            self.current_translation_source = source_text
            self.current_translation_source_language = source_language_code
            self.current_translation_value = source_text
            self.current_translation_target = output_language.code
            self._set_textbox_content(self.translation_text, source_text)
        elif self._can_produce_current_output(source_language_code):
            entry["translation_pending"] = True
            self.translation_pending_request_id = request_id
            if not self.current_translation_value:
                self._set_textbox_content(self.translation_text, entry["pending_text"])
            submitted = self.translation_manager.submit(
                "final",
                source_text,
                request_id,
                source_language_code,
                output_language.code,
            )
            if not submitted:
                self.translation_pending_request_id = 0
                entry["translation_pending"] = False
                entry["translation"] = ""
                self._set_textbox_content(
                    self.translation_text, self._default_translation_placeholder()
                )
        else:
            self.translation_pending_request_id = 0
            self._set_textbox_content(
                self.translation_text, self._default_translation_placeholder()
            )

        self._refresh_transcript()

        if remainder_text:
            now = time.time()
            self.stable_translation_segments = [remainder_text]
            self.stable_translation_source_language = source_language_code
            self.stable_translation_started_at = now
            self.stable_translation_last_update_at = now
            self._schedule_stable_translation_flush(
                self._stable_translation_next_delay_ms(remainder_text)
            )
        else:
            self.stable_translation_segments = []
            self.stable_translation_source_language = ""
            self.stable_translation_started_at = 0.0
            self.stable_translation_last_update_at = 0.0

    def _take_stable_translation_chunk(
        self, source_language_code: str, force: bool = False
    ) -> tuple:
        source_text = self._stable_translation_source_text()
        if not source_text:
            return "", ""

        chunk_text, remainder_text = self._split_translation_chunk(
            source_text, source_language_code, force=force
        )
        if not chunk_text and force:
            return source_text, ""
        return chunk_text, remainder_text

    def _split_translation_chunk(
        self, text: str, source_language_code: str, force: bool = False
    ) -> tuple:
        clean_text = (text or "").strip()
        if not clean_text:
            return "", ""

        profile = self._chunk_profile(source_language_code)
        unit_count = self._chunk_unit_count(clean_text, source_language_code)

        if self._ends_sentence(clean_text):
            return clean_text, ""

        if unit_count < profile["min_units"] and not force:
            return "", clean_text

        if unit_count <= profile["max_units"]:
            return clean_text, ""

        split_at = self._best_chunk_split_index(clean_text, source_language_code)
        if split_at <= 0:
            split_at = self._fallback_chunk_split_index(clean_text, source_language_code)

        chunk_text = clean_text[:split_at].strip()
        remainder_text = clean_text[split_at:].strip()
        if not chunk_text:
            return clean_text, ""
        return chunk_text, remainder_text

    def _best_chunk_split_index(self, text: str, source_language_code: str) -> int:
        profile = self._chunk_profile(source_language_code)
        separators = (
            (".", "?", "!", "\u3002", "\uff1f", "\uff01", "\u2026"),
            (",", ";", ":", "\uff0c", "\uff1b", "\u3001"),
        )
        for separator_group in separators:
            best_index = 0
            for index, char in enumerate(text):
                if char not in separator_group:
                    continue
                candidate = text[: index + 1].strip()
                units = self._chunk_unit_count(candidate, source_language_code)
                if profile["min_units"] <= units <= profile["max_units"]:
                    best_index = index + 1
            if best_index:
                return best_index

        if not self._is_cjk_language(source_language_code):
            return self._best_space_split_index(text, source_language_code)
        return 0

    def _best_space_split_index(self, text: str, source_language_code: str) -> int:
        profile = self._chunk_profile(source_language_code)
        best_index = 0
        for index, char in enumerate(text):
            if not char.isspace():
                continue
            candidate = text[:index].strip()
            units = self._chunk_unit_count(candidate, source_language_code)
            if profile["min_units"] <= units <= profile["max_units"]:
                best_index = index
        return best_index

    def _fallback_chunk_split_index(self, text: str, source_language_code: str) -> int:
        profile = self._chunk_profile(source_language_code)
        target_units = profile["max_units"]
        if not self._is_cjk_language(source_language_code):
            words = text.split()
            return len(" ".join(words[:target_units]))

        seen_units = 0
        for index, char in enumerate(text):
            if self._is_cjk_char(char):
                seen_units += 1
            if seen_units >= target_units:
                return index + 1
        return min(len(text), target_units)

    def _refresh_transcript(self):
        if not self.transcript_text:
            return

        content = self.transcript_service.render()
        self.transcript_text.delete("1.0", "end")
        if content:
            self.transcript_text.insert("1.0", content)
            self.transcript_text.see("end")

        overlay = getattr(self, "subtitle_overlay", None)
        if overlay:
            overlay.set_transcript(content or "")

        self._publish_integration_snapshot()

    def _update_transcript_translation(self, request_id: int, translation: str):
        self.transcript_service.update_translation(request_id, translation)
        self._refresh_transcript()

    def _on_translation_result(self, result):
        kind = result.get("kind")
        request_id = result.get("request_id", 0)
        source_text = result.get("text", "")
        target_language = result.get("target_language", "")
        translated_text = (result.get("translation") or "").strip()
        error = result.get("error")

        should_update_caption = translated_text and (
            kind == "final" or request_id == self.latest_preview_translation_id
        )

        if should_update_caption:
            self.current_translation_source = source_text
            self.current_translation_source_language = result.get(
                "source_language", ""
            )
            self.current_translation_value = translated_text
            self.current_translation_target = target_language
            self._set_textbox_content(self.translation_text, translated_text)
            if request_id == self.translation_pending_request_id:
                self.translation_pending_request_id = 0
        elif error and (
            request_id == self.latest_preview_translation_id
            or request_id == self.translation_pending_request_id
        ):
            if request_id == self.translation_pending_request_id:
                self.translation_pending_request_id = 0
            self._set_textbox_content(
                self.translation_text, "Translation temporarily unavailable."
            )

        if kind == "final":
            self._update_transcript_translation(request_id, translated_text)

    def _toggle_recognition(self):
        """Toggle speech recognition"""
        if self._control_availability()["recognition_action_disabled"]:
            self._show_action_blocked_hint()
            return

        if not self.is_recognizing:
            self._start_recognition()
        else:
            self._stop_recognition()

    def _start_recognition(self):
        """Start speech recognition"""
        if self.recognition_start_in_progress:
            self._show_loading_indicator("Transcription is starting...")
            return

        if self.audio_warmup_in_progress:
            self.pending_start_after_prewarm = True
            self._set_recognition_waiting(
                "Preparing audio... transcription will start automatically.",
                button_text="Preparing...",
            )
            return

        if self.model_prewarm_in_progress:
            self.pending_start_after_prewarm = True
            self._set_recognition_waiting(
                "Preparing model... transcription will start automatically.",
                button_text="Preparing...",
            )
            return

        try:
            numpy_major = int(np.__version__.split(".")[0])
        except Exception:
            numpy_major = 1

        if numpy_major >= 2:
            self._set_recognition_unavailable(
                "NumPy 2.x is installed. Install numpy<2, then restart the app."
            )
            show_error(
                "Incompatible Dependencies",
                "Detected NumPy 2.x. The installed soundcard build is not compatible and recording will fail.\n\n"
                "Please run:\n"
                'pip install "numpy<2"\n\n'
                "Then restart the application.",
            )
            return

        input_language = self.model_manager.get_input_language()
        output_language = self.model_manager.get_output_language()
        if (
            self._requires_opencc_for_language_pair(input_language, output_language)
            and opencc is None
        ):
            self._set_recognition_unavailable(
                "OpenCC is missing. Install it, then restart the app."
            )
            show_error(
                "OpenCC Required",
                "Mandarin Traditional requires OpenCC conversion.\n\n"
                "Please run:\n"
                "pip install opencc-python-reimplemented\n\n"
                "Then restart the application.",
            )
            return

        if not self._ensure_selected_model_available(start_after_ready=True):
            return

        try:
            self.recognition_start_in_progress = True
            self._set_recognition_waiting(
                f"Starting transcription ({input_language.label})...",
                button_text="Starting...",
                disable_languages=True,
            )
            if self.root:
                self.root.update_idletasks()

            if not self.audio_manager.initialize():
                self._set_recognition_unavailable(
                    "Audio device not ready. Check Windows output device, then retry."
                )
                show_error(
                    "Audio Device Not Ready",
                    "VoxScribe could not open the audio device.\n\n"
                    "Check that a Windows audio device is available and working, "
                    "play any audio once (for loopback), then click Retry Start.",
                )
                return

            if not self.speech_recognizer.start_recognition(self.audio_manager):
                self._set_recognition_unavailable(
                    "Transcription did not start. Check audio output and retry."
                )
                show_error(
                    "Transcription Did Not Start",
                    "The speech engine is ready, but the audio stream did not start.\n\n"
                    "Check the Windows output device, make sure audio is playing, "
                    "then click Retry Start.",
                )
                return

            self.is_recognizing = True
            self.recognition_start_in_progress = False
            self.recognition_ready = True
            self.start_time = time.time()
            self.word_count = 0
            self._set_language_controls_state("disabled")
            self._set_language_state_text(input_language.label)
            self._set_source_label(input_language.code)
            self._hide_loading_indicator()

            self.start_stop_btn.configure(
                text="Stop Transcription",
                state="normal",
                fg_color="#e53935",
                hover_color="#c62828",
            )
            self._set_status_state(
                "live", f"Processing ({input_language.label})... Press F5 to stop"
            )
            self._show_subtitle_overlay(compact=False)

            self._update_stats()
            self.logger.info("Speech transcription started")

        except Exception as e:
            self._set_recognition_unavailable(
                "Transcription failed to start. Check audio output and retry."
            )
            self.logger.error(f"Failed to start transcription: {e}")
            show_error(
                "Transcription Error",
                f"Transcription failed to start.\n\nDetails: {e}\n\n"
                "Check the Windows output device, make sure audio is playing, "
                "then click Retry Start.",
            )

    def _stop_recognition(self):
        """Stop speech recognition"""
        try:
            self.speech_recognizer.stop_recognition()
            self.audio_manager.stop_stream()
            self._flush_stable_translation_buffer(force=True)

            self.is_recognizing = False
            self.recognition_start_in_progress = False
            self.recognition_ready = self._is_current_model_ready()
            self._hide_loading_indicator()
            self._set_language_controls_state("normal")
            self._set_start_button_idle("normal")
            self._set_status_state(
                "stopped", "Stopped. Click Start Transcription when ready."
            )

            self.logger.info("Speech transcription stopped")
        except Exception as e:
            self.logger.error(f"Failed to stop transcription: {e}")

    def _download_model(
        self,
        language_code: Optional[str] = None,
        auto: bool = False,
        completion_callback=None,
        startup_layout: bool = False,
    ):
        """Install faster-whisper dependency if missing."""
        if self.model_download_in_progress:
            return

        self._close_startup_loading()

        model_spec = self.model_manager.get_model_spec(
            language_code or self._current_input_language_code()
        )

        self.model_download_in_progress = True
        if hasattr(self, "start_stop_btn"):
            self.start_stop_btn.configure(text="Installing...", state="disabled")
        self._set_language_controls_state("disabled")
        self._show_loading_indicator("Installing Whisper engine dependency...")

        overlay = getattr(self, "subtitle_overlay", None)
        use_overlay_progress = bool(overlay)

        if use_overlay_progress:
            overlay.set_loading(
                f"Installing {model_spec.display_name} engine...", 0.0
            )

        def finish_download(success: bool, error: Optional[str] = None):
            self.model_download_in_progress = False

            if use_overlay_progress:
                overlay.clear_loading()

            if success:
                if completion_callback:
                    completion_callback(True)
                    return
                self._ensure_selected_model_available()
                return

            self._set_recognition_unavailable(
                "Failed to install Whisper engine. Check internet and retry."
            )
            if completion_callback:
                completion_callback(False)
                self._hide_loading_indicator()
                return

            self._hide_loading_indicator()
            self._set_language_controls_state("normal")
            if hasattr(self, "start_stop_btn"):
                self.start_stop_btn.configure(text=_L("Start Transcription"), state="normal")

            if error:
                show_error(
                    "Installation Failed",
                    f"Could not install Whisper engine.\n\n"
                    f"Details: {error}\n\n"
                    "Check internet connection, then click Retry Start.",
                )

        def download_thread():
            try:
                ok = self.model_manager.download_model(lambda *_: None, language_code)
                root = self.root
                if root and hasattr(root, "after"):
                    root.after(0, lambda: finish_download(ok))
            except Exception as e:
                root = self.root
                if root and hasattr(root, "after"):
                    root.after(0, lambda err=str(e): finish_download(False, err))

        threading.Thread(target=download_thread, daemon=True).start()

    def _on_backlog_update(self, payload):
        self._backlog_seconds = payload.get("backlog_seconds", 0.0)
        self._update_stats()

    def _on_final_result(self, result):
        """Handle final recognition result from Whisper chunk."""
        try:
            text = result.get("text", "")
            if not text or not self.current_text:
                return

            input_language_code = (
                result.get("language_code") or self._current_input_language_code()
            )
            self.detected_input_language_label = result.get("language_label") or self.model_manager.get_input_language(input_language_code).label
            self._set_source_label(input_language_code)
            self._refresh_overlay_panel()
            self._set_textbox_content(self.current_text, text)
            self._append_stable_translation_segment(text, input_language_code)

            self.word_count += len(text.split())
        except Exception as e:
            self.logger.error(f"Error updating final result: {e}")

    def _on_error(self, error):
        """Handle recognition error"""
        friendly_error = self._friendly_recognition_error(error)
        self.logger.error(f"Transcription error: {error}")
        if self._is_audio_capture_stopped_error(error):
            self._handle_fatal_recognition_error(friendly_error)
            return
        self._set_status_state("error", friendly_error)

    def _is_audio_capture_stopped_error(self, error) -> bool:
        return "audio capture stopped unexpectedly" in str(error or "").lower()

    def _handle_fatal_recognition_error(self, friendly_error: str):
        self.is_recognizing = False
        self.recognition_start_in_progress = False
        self.recognition_ready = self._is_current_model_ready()
        self._backlog_seconds = 0.0
        self._hide_loading_indicator()

        audio_manager = getattr(self, "audio_manager", None)
        if audio_manager and hasattr(audio_manager, "stop_stream"):
            try:
                audio_manager.stop_stream(timeout=0.0)
            except Exception as e:
                self.logger.error(f"Failed to stop audio stream after error: {e}")

        self._set_language_controls_state("normal")
        self._set_start_button_idle("normal", text="Retry Start")
        self._set_status_state("error", friendly_error)

    def _friendly_recognition_error(self, error) -> str:
        raw_error = str(error or "").strip()
        if not raw_error:
            return "Transcription stopped unexpectedly. Click Retry Start."

        lowered = raw_error.lower()
        if self._is_audio_capture_stopped_error(raw_error):
            return (
                "Audio capture stopped unexpectedly. Check the selected audio device, "
                "then click Retry Start."
            )
        if "not a valid language code" in lowered or "accepted language codes" in lowered:
            return (
                "The selected input language is not available in the speech engine. "
                "Click Retry Start or choose another input language."
            )
        if "fromstring is removed" in lowered or "frombuffer" in lowered:
            return (
                "Audio capture dependency is incompatible with the installed NumPy. "
                "Install numpy<2, then restart the app."
            )

        clean_error = " ".join(raw_error.split())
        if len(clean_error) > 180:
            clean_error = f"{clean_error[:177].rstrip()}..."
        return f"Transcription error: {clean_error}. Click Retry Start."

    def _update_stats(self):
        """Update statistics display"""
        if self.is_recognizing and self.start_time:
            duration = int(time.time() - self.start_time)
            hours, remainder = divmod(duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            wpm_str = ""
            if duration > 0 and self.word_count > 0:
                wpm = (self.word_count / duration) * 60
                wpm_str = f" | WPM: {wpm:.1f}"

            backlog_str = ""
            if getattr(self, "_backlog_seconds", 0.0) > 0:
                backlog_str = f" | Behind: {self._backlog_seconds:.1f}s"

            self.stats_var.set(
                f"Words: {self.word_count} | Duration: {time_str}{wpm_str}{backlog_str}"
            )
            if self.root:
                self.root.after(1000, self._update_stats)

    def _clear_transcript(self):
        """Clear transcript"""
        if self._control_availability()["transcript_actions_disabled"]:
            self._show_action_blocked_hint()
            self._refresh_overlay_panel()
            return

        current_text = ""
        translation_text = ""
        transcript_text = ""
        try:
            current_text = self.current_text.get("1.0", "end-1c")
        except Exception:
            pass
        try:
            translation_text = self.translation_text.get("1.0", "end-1c")
        except Exception:
            pass
        try:
            transcript_text = self.transcript_text.get("1.0", "end-1c")
        except Exception:
            pass

        has_content = bool(
            self.transcript_entries
            or current_text.strip()
            or translation_text.strip()
            or transcript_text.strip()
        )
        if has_content and not ask_yes_no(
            "Clear Transcript",
            "Clear the transcription, source text, and full transcript?\n\n"
            "This cannot be undone.",
            parent=self.root,
        ):
            return

        self.transcript_service.clear()
        self.transcript_entries = self.transcript_service.entries
        self._refresh_transcript()
        self._set_textbox_content(self.current_text, "")
        self._set_textbox_content(
            self.translation_text, self._default_translation_placeholder()
        )
        self.latest_preview_translation_id = 0
        self.current_translation_source = ""
        self.current_translation_source_language = ""
        self.current_translation_value = ""
        self.current_translation_target = ""
        self._reset_stable_translation_buffer()
        self.word_count = 0
        status_state = (
            "live"
            if self.is_recognizing
            else ("ready" if self.recognition_ready else "stopped")
        )
        self._set_status_state(status_state, "Transcript cleared.")

    def _save_transcript(self):
        """Save transcript to file"""
        if self._control_availability()["transcript_actions_disabled"]:
            self._show_action_blocked_hint()
            self._refresh_overlay_panel()
            return

        try:
            content = self.transcript_text.get("1.0", "end-1c")
            if not content.strip():
                show_warning("Warning", "No transcript to save")
                return

            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            )

            if filename:
                self.export_service.save_text(filename, content)
                status_state = (
                    "live"
                    if self.is_recognizing
                    else ("ready" if self.recognition_ready else "stopped")
                )
                self._set_status_state(status_state, f"Saved: {Path(filename).name}")
                self.logger.info(f"Transcript saved to: {filename}")
        except Exception as e:
            self.logger.error(f"Failed to save transcript: {e}")
            self._set_status_state("error", "Save failed. Choose another location.")
            show_error(
                "Save Failed",
                f"Transcript could not be saved.\n\nDetails: {e}\n\n"
                "Choose another folder or file name, then try Save again.",
            )

    def _on_closing(self):
        """Handle application closing"""
        try:
            self.logger.info("Application shutdown initiated")
            shutdown_timeout = 0.25
            if getattr(self, "is_recognizing", False):
                self._stop_recognition()
            if hasattr(self, "speech_recognizer"):
                self.speech_recognizer.cleanup(timeout=shutdown_timeout)
            if hasattr(self, "translation_manager"):
                self.translation_manager.stop(timeout=shutdown_timeout)
            if hasattr(self, "audio_manager"):
                self.audio_manager.cleanup(timeout=shutdown_timeout)
            if hasattr(self, "subtitle_overlay") and self.subtitle_overlay:
                self.subtitle_overlay.destroy()
            if getattr(self, "integration_api", None):
                self.integration_api.stop(timeout=shutdown_timeout)
            if hasattr(self, "config"):
                self.config.save_config()
            self.logger.info("Application shutdown complete")
            if self.root:
                self.root.quit()
                self.root.destroy()
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            if self.root:
                try:
                    self.root.quit()
                except:
                    pass
                try:
                    self.root.destroy()
                except:
                    pass

    def run(self):
        """Run the application"""
        try:
            self.logger.info("Starting VoxScribe")
            if self.root and hasattr(self.root, "mainloop"):
                self.root.mainloop()
            else:
                self.logger.error("Root window is not properly initialized")
        except Exception as e:
            self.logger.error(f"Application error: {e}")

    def _safe_text_value(self, widget) -> str:
        if not widget:
            return ""
        try:
            return widget.get("1.0", "end-1c").strip()
        except Exception:
            return ""

    def _safe_var_value(self, variable) -> str:
        if not variable:
            return ""
        try:
            return str(variable.get() or "").strip()
        except Exception:
            return ""

    def _build_integration_snapshot(self) -> dict:
        input_language = (
            self.model_manager.get_input_language()
            if hasattr(self, "model_manager")
            else INPUT_LANGUAGE_REGISTRY[DEFAULT_INPUT_LANGUAGE_SETTING]
        )
        output_language = (
            self.model_manager.get_output_language()
            if hasattr(self, "model_manager")
            else OUTPUT_LANGUAGE_REGISTRY[DEFAULT_OUTPUT_LANGUAGE]
        )
        availability = (
            self._control_availability()
            if hasattr(self, "_control_availability")
            else {}
        )

        return {
            "runtime": {
                "status": self.state_manager.get("status", "starting")
                if hasattr(self, "state_manager")
                else "starting",
                "status_message": self.state_manager.get("status_message", "")
                if hasattr(self, "state_manager")
                else "",
                "is_recognizing": bool(getattr(self, "is_recognizing", False)),
                "recognition_ready": bool(getattr(self, "recognition_ready", False)),
                "stats": self._safe_var_value(getattr(self, "stats_var", None)),
                "compute_backend_label": str(
                    self.config.get("compute_backend_label", "") or ""
                ),
                "device_profile": str(self.config.get("device_profile", "") or ""),
                "input_language": {
                    "code": input_language.code,
                    "label": input_language.label,
                },
                "output_language": {
                    "code": output_language.code,
                    "label": output_language.label,
                },
                "availability": availability,
            },
            "caption": {
                "source_text": self._safe_text_value(getattr(self, "current_text", None)),
                "translated_text": self._safe_text_value(
                    getattr(self, "translation_text", None)
                ),
                "translation_pending": bool(
                    getattr(self, "translation_pending_request_id", 0)
                ),
                "current_translation_source": str(
                    getattr(self, "current_translation_source", "") or ""
                ),
                "current_translation_source_language": str(
                    getattr(self, "current_translation_source_language", "") or ""
                ),
                "current_translation_target": str(
                    getattr(self, "current_translation_target", "") or ""
                ),
            },
            "transcript": {
                "entry_count": len(getattr(self.transcript_service, "entries", [])),
                "entries": self.transcript_service.snapshot()
                if hasattr(self.transcript_service, "snapshot")
                else [],
                "rendered": self.transcript_service.render()
                if hasattr(self.transcript_service, "render")
                else "",
            },
        }

    def _publish_integration_snapshot(self):
        api_server = getattr(self, "integration_api", None)
        if not api_server:
            return
        try:
            api_server.publish_snapshot(self._build_integration_snapshot())
        except Exception as e:
            self.logger.warning(f"Failed to publish integration snapshot: {e}")

    def _start_integration_api(self):
        if not self.config.get("integration_api_enabled", False):
            return
        try:
            self.integration_api = VoxScribeOpenApiServer(
                host=self.config.get("integration_api_host", "127.0.0.1"),
                port=self.config.get("integration_api_port", 8765),
                docs_enabled=self.config.get("integration_api_docs_enabled", True),
                logger=self.logger,
            )
            self.integration_api.start()
        except Exception as e:
            self.integration_api = None
            self.logger.warning(f"Integration API failed to start: {e}")
