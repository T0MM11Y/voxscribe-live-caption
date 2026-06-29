import unittest
from types import SimpleNamespace

from app.ui.main_window import VoxScribeApp


class FakeConfig:
    def __init__(self):
        self.values = {"startup_prepared_model_keys": {}}
        self.saved = False

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save_config(self):
        self.saved = True


class FakeModelManager:
    def __init__(self, model_available=True):
        self.model_available = model_available

    def get_input_language(self):
        return SimpleNamespace(label="English")

    def get_recognition_language_codes(self, language_code=None):
        return (language_code or "en",)

    def get_model_spec(self, _language_code=None):
        return SimpleNamespace(key="whisper")

    def get_model_path(self, _language_code=None):
        return r"C:\Users\t0mm11y\.cache\huggingface\hub"

    def is_model_available(self):
        return self.model_available


def make_app():
    app = VoxScribeApp.__new__(VoxScribeApp)
    app.root = SimpleNamespace(after=lambda _delay, callback: callback())
    app.config = FakeConfig()
    app.model_manager = FakeModelManager()
    return app


class StartupModelMarkerTest(unittest.TestCase):
    def test_startup_model_marker_is_stable_per_language_and_model(self):
        app = make_app()

        key = app._startup_model_ready_key()

        self.assertEqual(key, "en:whisper:hub")

    def test_mark_startup_model_prepared_persists_key(self):
        app = make_app()

        self.assertFalse(app._has_startup_model_prepared())
        app._mark_startup_model_prepared()

        self.assertTrue(app._has_startup_model_prepared())
        self.assertTrue(app.config.saved)

    def test_startup_prewarms_model_even_when_model_was_prepared_before(self):
        app = make_app()
        app._mark_startup_model_prepared()
        calls = []
        app._set_recognition_waiting = lambda *args, **kwargs: calls.append(
            ("waiting", args, kwargs)
        )
        app._schedule_model_prewarm = lambda *args, **kwargs: calls.append(
            ("prewarm", args, kwargs)
        )

        app._run_startup_model_check()

        self.assertEqual(calls[-1][0], "prewarm")
        self.assertEqual(
            calls[-1][1][0], "Preparing English model for startup..."
        )
        self.assertTrue(calls[-1][2]["show_startup_loading"])

    def test_startup_auto_downloads_when_model_is_missing(self):
        app = make_app()
        app.model_manager = FakeModelManager(model_available=False)
        calls = []
        app._current_input_language_code = lambda: "en"
        app._set_recognition_waiting = lambda *args, **kwargs: calls.append(
            ("waiting", args, kwargs)
        )
        app._download_model = lambda *args, **kwargs: calls.append(
            ("download", args, kwargs)
        )

        app._run_startup_model_check()

        self.assertEqual(calls[-1][0], "download")
        self.assertEqual(calls[-1][1][0], "en")
        self.assertTrue(calls[-1][2]["auto"])
        self.assertTrue(calls[-1][2]["startup_layout"])


if __name__ == "__main__":
    unittest.main()
