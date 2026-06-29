import unittest

from app.core.languages import INPUT_LANGUAGE_REGISTRY
from app.recognition.whisper_engine import WhisperRecognizer


class FakeConfig:
    def get(self, key, default=None):
        return default


class FakeLogger:
    def info(self, _message):
        pass

    def error(self, _message):
        pass

    def debug(self, _message):
        pass


class ImmediateRoot:
    def after(self, _delay, callback):
        callback()


class DeadThread:
    def is_alive(self):
        return False


class DeadAudioManager:
    def __init__(self):
        self.is_recording = True
        self.record_thread = DeadThread()
        self.stop_timeout = None

    def stop_stream(self, timeout=2.0):
        self.stop_timeout = timeout
        self.is_recording = False


class FakeModelManager:
    def __init__(self, auto=False):
        self._auto = auto

    def get_input_language(self, language_code=None):
        return INPUT_LANGUAGE_REGISTRY[language_code or "en"]

    def is_auto_input_language(self, language_code=None):
        return self._auto


class WhisperEngineTest(unittest.TestCase):
    def test_engine_language_code_returns_none_in_auto_mode(self):
        recognizer = WhisperRecognizer(FakeConfig(), FakeModelManager(auto=True), FakeLogger())

        for app_code in ("en", "zh-cn", "zh-tw", "id"):
            with self.subTest(app_code=app_code):
                recognizer.active_language_code = app_code
                self.assertIsNone(recognizer._engine_language_code())

    def test_engine_language_code_returns_whisper_code_in_specific_mode(self):
        recognizer = WhisperRecognizer(FakeConfig(), FakeModelManager(auto=False), FakeLogger())

        cases = {"en": "en", "zh-cn": "zh", "zh-tw": "zh", "id": "id"}
        for app_code, expected in cases.items():
            with self.subTest(app_code=app_code):
                recognizer.active_language_code = app_code
                self.assertEqual(recognizer._engine_language_code(), expected)

    def test_detected_language_is_normalized_for_app_pipeline(self):
        recognizer = WhisperRecognizer(FakeConfig(), FakeModelManager(), FakeLogger())

        expected = {
            "en": "en",
            "zh": "zh-cn",
            "zh-cn": "zh-cn",
            "zh-tw": "zh-cn",
            "id": "id",
        }
        for detected_code, app_code in expected.items():
            with self.subTest(detected_code=detected_code):
                self.assertEqual(recognizer._detected_language_code(detected_code), app_code)

    def test_dead_capture_thread_emits_error_and_stops_worker(self):
        recognizer = WhisperRecognizer(FakeConfig(), FakeModelManager(), FakeLogger())
        audio_manager = DeadAudioManager()
        errors = []

        recognizer.root = ImmediateRoot()
        recognizer.set_callbacks(error_callback=errors.append)
        recognizer.audio_manager = audio_manager
        recognizer.is_running = True

        recognizer._recognition_worker()

        self.assertFalse(recognizer.is_running)
        self.assertEqual(audio_manager.stop_timeout, 0.0)
        self.assertEqual(len(errors), 1)
        self.assertIn("Audio capture stopped unexpectedly", errors[0])


if __name__ == "__main__":
    unittest.main()
