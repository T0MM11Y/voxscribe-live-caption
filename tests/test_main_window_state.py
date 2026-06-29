import subprocess
import sys
import time
import unittest
from types import SimpleNamespace

from app.core.languages import INPUT_LANGUAGE_REGISTRY
from app.core.locale import _L, get_ui_language, set_ui_language
from app.ui.main_window import VoxScribeApp


class FakeConfig:
    def __init__(self):
        self.values = {
            "stable_translation_max_chars": 96,
            "stable_translation_short_delay_ms": 450,
            "stable_translation_flush_delay_ms": 650,
            "stable_translation_max_delay_ms": 2200,
            "translation_latency_profile": "responsive",
            "zh_en_accuracy_mode": False,
        }

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save_config(self):
        pass


class FakeStateManager:
    def __init__(self, status="ready", message=""):
        self.status = status
        self.message = message
        self.values = {}

    def get(self, key, default=None):
        if key == "status":
            return self.status
        if key == "status_message":
            return self.message
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def update(self, **kwargs):
        self.values.update(kwargs)


class FakeModelManager:
    def __init__(self, config):
        self.config = config

    def get_input_language(self, language_code=None):
        code = language_code or self.config.get("input_language", "en")
        return INPUT_LANGUAGE_REGISTRY[code]


class FakeTextWidget:
    def __init__(self, text=""):
        self.text = text
        self.delete_calls = 0
        self.insert_calls = []

    def get(self, *_args):
        return self.text

    def delete(self, *_args):
        self.delete_calls += 1
        self.text = ""

    def insert(self, _index, text):
        self.insert_calls.append(text)
        self.text = text


class FakeLayoutWidget:
    def __init__(self):
        self.column_calls = []
        self.row_calls = []
        self.propagate_calls = []

    def grid_columnconfigure(self, *args, **kwargs):
        self.column_calls.append((args, kwargs))

    def grid_rowconfigure(self, *args, **kwargs):
        self.row_calls.append((args, kwargs))

    def grid_propagate(self, value):
        self.propagate_calls.append(value)


class FakeMenu:
    def __init__(self):
        self.configures = []

    def configure(self, **kwargs):
        self.configures.append(kwargs)


def make_app():
    app = VoxScribeApp.__new__(VoxScribeApp)
    app.config = FakeConfig()
    app.state_manager = FakeStateManager()
    app.model_manager = FakeModelManager(app.config)
    app.logger = SimpleNamespace(info=lambda *_args: None, error=lambda *_args: None)
    app.model_download_in_progress = False
    app.model_prewarm_in_progress = False
    app.audio_warmup_in_progress = False
    app.recognition_start_in_progress = False
    app.language_switch_in_progress = False
    app.pending_start_after_prewarm = False
    app.offline_translation_prepare_in_progress = False
    app.pending_start_after_offline_translation = False
    app.stable_translation_segments = []
    app.stable_translation_source_language = "en"
    app.stable_translation_started_at = 0.0
    app.stable_translation_last_update_at = 0.0
    app.stable_translation_flush_job = None
    app.translation_pending_request_id = 0
    app.translation_pending_source = ""
    app.latest_preview_translation_id = 0
    app.current_translation_source = ""
    app.current_translation_source_language = ""
    app.current_translation_value = ""
    app.current_translation_target = ""
    app.source_preview_text = ""
    return app


class MainWindowStateTest(unittest.TestCase):
    def test_offline_translation_prepare_disables_related_controls(self):
        app = make_app()
        app.offline_translation_prepare_in_progress = True

        availability = app._control_availability()

        self.assertTrue(availability["system_busy"])
        self.assertTrue(availability["recognition_action_disabled"])
        self.assertTrue(availability["input_language_disabled"])
        self.assertTrue(availability["output_language_disabled"])
        self.assertTrue(availability["transcript_actions_disabled"])

    def test_stable_translation_flushes_on_sentence_end_punctuation(self):
        app = make_app()
        app.stable_translation_started_at = 100.0

        for punctuation in (".", "?", "!", "\u3002", "\uff1f", "\uff01", "\u2026"):
            self.assertTrue(
                app._should_flush_stable_translation(f"ready{punctuation}", 100.1)
            )

    def test_stable_translation_waits_for_more_context_without_boundary(self):
        app = make_app()
        app.stable_translation_started_at = 100.0

        self.assertFalse(app._should_flush_stable_translation("still speaking", 100.2))

    def test_short_mandarin_fragment_waits_for_more_context_until_max_delay(self):
        app = make_app()
        app.stable_translation_source_language = "zh-cn"
        app.stable_translation_started_at = 100.0
        text = "\u7136\u540e\u8fd9\u4e2a"

        self.assertFalse(app._should_flush_stable_translation(text, 100.8))
        self.assertTrue(app._should_flush_stable_translation(text, 104.0))

        chunk, remainder = app._split_translation_chunk(text, "zh-cn")
        self.assertEqual(chunk, "")
        self.assertEqual(remainder, text)

        forced_chunk, forced_remainder = app._split_translation_chunk(
            text, "zh-cn", force=True
        )
        self.assertEqual(forced_chunk, text)
        self.assertEqual(forced_remainder, "")

    def test_ideal_mandarin_chunk_flushes_after_short_delay(self):
        app = make_app()
        app.stable_translation_source_language = "zh-cn"
        app.stable_translation_started_at = 100.0
        text = "\u6211\u4eec\u9700\u8981\u68c0\u67e5\u8fd9\u4e2a\u529f\u80fd\u7684\u90e8\u7f72\u72b6\u6001\u7136\u540e\u786e\u8ba4\u4eca\u5929\u4e0a\u7ebf"

        self.assertFalse(app._should_flush_stable_translation(text, 100.3))
        self.assertTrue(app._should_flush_stable_translation(text, 100.5))

    def test_long_mandarin_chunk_splits_on_comma_boundary(self):
        app = make_app()
        app.stable_translation_source_language = "zh-cn"
        first_clause = "\u6211\u4eec\u9700\u8981\u68c0\u67e5\u8fd9\u4e2a\u529f\u80fd\u7684\u90e8\u7f72\u72b6\u6001" * 5
        second_clause = "\u7136\u540e\u518d\u786e\u8ba4\u524d\u7aef\u7684\u53d1\u5e03\u65f6\u95f4\u548c\u56de\u6eda\u65b9\u6848\u662f\u5426\u5df2\u7ecf\u51c6\u5907\u597d" * 4
        text = f"{first_clause}\uff0c{second_clause}"

        chunk, remainder = app._split_translation_chunk(text, "zh-cn")

        self.assertTrue(chunk.endswith("\uff0c"))
        self.assertTrue(remainder.startswith(second_clause[:4]))

    def test_long_english_chunk_splits_on_space_boundary(self):
        app = make_app()
        text = " ".join(f"word{i}" for i in range(45))

        chunk, remainder = app._split_translation_chunk(text, "en")

        self.assertEqual(len(chunk.split()), 26)
        self.assertEqual(remainder.split()[0], "word26")

    def test_next_delay_uses_short_wait_for_ideal_chunk(self):
        app = make_app()
        app.stable_translation_source_language = "en"
        short_text = "we need"
        ideal_text = "we need to check the deployment status before release"

        self.assertEqual(app._stable_translation_next_delay_ms(short_text), 650)
        self.assertEqual(app._stable_translation_next_delay_ms(ideal_text), 450)

    def test_flush_reschedules_short_fragment_before_max_delay(self):
        app = make_app()
        app.root = None
        app.stable_translation_segments = ["\u7136\u540e\u8fd9\u4e2a"]
        app.stable_translation_source_language = "zh-cn"
        app.stable_translation_started_at = time.time() - 1.0
        app.stable_translation_last_update_at = time.time()
        app.stable_translation_flush_job = None
        scheduled_delays = []
        app._schedule_stable_translation_flush = scheduled_delays.append

        app._flush_stable_translation_buffer()

        self.assertEqual(app.stable_translation_segments, ["\u7136\u540e\u8fd9\u4e2a"])
        self.assertEqual(app.stable_translation_source_language, "zh-cn")
        self.assertTrue(scheduled_delays)
        self.assertGreaterEqual(scheduled_delays[0], 250)

    def test_final_translation_updates_caption_even_when_newer_request_is_pending(self):
        app = make_app()
        app.latest_preview_translation_id = 2
        app.translation_pending_request_id = 2
        app.translation_text = object()
        shown_texts = []
        pending_states = []
        transcript_updates = []
        app._set_textbox_content = lambda _widget, text: shown_texts.append(text)
        app._set_translation_pending = (
            lambda is_pending, source_text="": pending_states.append(is_pending)
        )
        app.transcript_service = SimpleNamespace(
            update_translation=lambda request_id, text: transcript_updates.append(
                (request_id, text)
            )
        )
        app._refresh_transcript = lambda: None

        app._on_translation_result(
            {
                "kind": "final",
                "request_id": 1,
                "text": "first source",
                "source_language": "zh-cn",
                "target_language": "en",
                "translation": "first translation",
            }
        )

        self.assertEqual(shown_texts[-1], "first translation")
        self.assertEqual(app.translation_pending_request_id, 2)
        self.assertEqual(pending_states, [])
        self.assertEqual(transcript_updates, [(1, "first translation")])

    def test_audio_warmup_sets_ready_after_probe(self):
        class FakeAudioManager:
            def is_initialized(self):
                return False

            def initialize(self, probe_recorder=False):
                return probe_recorder

        app = make_app()
        app.root = SimpleNamespace(after=lambda _delay, callback: callback())
        app.audio_manager = FakeAudioManager()
        app.is_recognizing = False
        app._set_recognition_waiting = lambda *args, **kwargs: None
        calls = []
        app._set_recognition_ready = lambda *args, **kwargs: calls.append("ready")

        app._schedule_audio_warmup("Checking audio device...", show_startup_loading=True)

        deadline = time.time() + 2.0
        while "ready" not in calls and time.time() < deadline:
            time.sleep(0.01)

        self.assertIn("ready", calls)

    def test_textbox_content_skips_rewrite_when_text_is_unchanged(self):
        app = make_app()
        widget = FakeTextWidget("same text")
        app.translation_text = object()

        app._set_textbox_content(widget, "same text")

        self.assertEqual(widget.delete_calls, 0)
        self.assertEqual(widget.insert_calls, [])

    def test_translation_text_syncs_overlay_without_rewriting_same_text(self):
        app = make_app()
        widget = FakeTextWidget("same caption")
        app.translation_text = widget
        synced_captions = []
        app._sync_subtitle_caption = synced_captions.append

        app._set_textbox_content(widget, "same caption")

        self.assertEqual(widget.delete_calls, 0)
        self.assertEqual(widget.insert_calls, [])
        self.assertEqual(synced_captions, ["same caption"])

    def test_input_language_change_updates_source_but_keeps_ui_english(self):
        set_ui_language("id")

        for code in ("zh-cn", "zh-tw", "id"):
            app = make_app()
            app.input_language_var = SimpleNamespace(set=lambda _label: None)
            app.is_recognizing = False
            app._reset_translation_state = lambda clear_caption=True: None
            app._set_language_state_text = lambda *_args, **_kwargs: None
            app._set_source_label = lambda *_args, **_kwargs: None
            app._ensure_selected_model_available = lambda **_kwargs: True
            app._refresh_overlay_panel = lambda: None

            app._on_input_language_change(INPUT_LANGUAGE_REGISTRY[code].label)

            self.assertEqual(app.config.get("input_language"), code)
            self.assertEqual(app.config.get("language"), code)
            self.assertEqual(app.state_manager.get("input_language"), code)
            self.assertEqual(get_ui_language(), "en")
            self.assertEqual(_L("Start Recognition"), "Start Recognition")

    def test_recognition_language_code_error_is_user_friendly(self):
        app = make_app()
        captured = []
        app.status_var = None
        app._set_status_state = lambda state, message: captured.append((state, message))
        raw_error = (
            "'zh-tw' is not a valid language code (accepted language codes: "
            "af, am, ar, as, az, ba, be, bg, bn, bo, br, bs, ca, cs, cy, da, de, el, en)"
        )

        app._on_error(raw_error)

        self.assertEqual(captured[0][0], "error")
        self.assertIn("selected input language", captured[0][1])
        self.assertNotIn("accepted language codes", captured[0][1])
        self.assertNotIn("zh-tw", captured[0][1])

    def test_recognition_errors_are_truncated_for_status_display(self):
        app = make_app()
        message = app._friendly_recognition_error("x" * 260)

        self.assertLessEqual(len(message), 225)
        self.assertTrue(message.endswith("Click Retry Start."))

    def test_main_window_layout_configures_expandable_columns(self):
        app = make_app()
        root = FakeLayoutWidget()
        sidebar = FakeLayoutWidget()
        main = FakeLayoutWidget()
        app.root = root

        app._configure_main_window_layout(sidebar, main)

        self.assertIn(((0,), {"weight": 0, "minsize": 280}), root.column_calls)
        self.assertIn(((1,), {"weight": 1}), root.column_calls)
        self.assertIn(((0,), {"weight": 1}), root.row_calls)
        self.assertEqual(sidebar.propagate_calls, [False])
        self.assertIn(((0,), {"weight": 1}), sidebar.column_calls)
        self.assertIn(((8,), {"weight": 1}), sidebar.row_calls)
        self.assertIn(((0,), {"weight": 1}), main.column_calls)
        self.assertIn(((2,), {"weight": 1}), main.row_calls)

    def test_header_status_wraplength_stays_bounded(self):
        app = make_app()

        self.assertEqual(app._header_status_wraplength(320), 160)
        self.assertEqual(app._header_status_wraplength(650), 220)
        self.assertEqual(app._header_status_wraplength(1200), 520)

    def test_language_control_state_updates_input_and_output_menus(self):
        app = make_app()
        app.input_language_menu = FakeMenu()
        app.output_language_menu = FakeMenu()

        app._set_language_controls_state("normal")

        self.assertEqual(app.input_language_menu.configures[-1]["state"], "normal")
        self.assertEqual(app.output_language_menu.configures[-1]["state"], "normal")

        app._set_language_controls_state("disabled")

        self.assertEqual(app.input_language_menu.configures[-1]["state"], "disabled")
        self.assertEqual(app.output_language_menu.configures[-1]["state"], "disabled")

    def test_restart_application_relaunches_current_process(self):
        app = make_app()
        app.root = object()
        closed = []
        popen_calls = []
        exit_codes = []
        original_popen = subprocess.Popen
        original_exit = sys.exit

        def fake_popen(args):
            popen_calls.append(args)
            return object()

        def fake_exit(code=0):
            exit_codes.append(code)
            raise SystemExit(code)

        app._on_closing = lambda: closed.append(True)
        subprocess.Popen = fake_popen
        sys.exit = fake_exit
        try:
            with self.assertRaises(SystemExit) as raised:
                app._restart_application()
        finally:
            subprocess.Popen = original_popen
            sys.exit = original_exit

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(closed, [True])
        self.assertEqual(popen_calls, [[sys.executable] + sys.argv])
        self.assertEqual(exit_codes, [0])


if __name__ == "__main__":
    unittest.main()
