import unittest

from app.core.languages import INPUT_LANGUAGE_REGISTRY
from app.audio.spool import DiskBackedAudioQueue
from app.recognition.whisper_engine import WhisperRecognizer


class FakeConfig:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeLogger:
    def info(self, _message):
        pass

    def error(self, _message):
        pass

    def warning(self, _message):
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


class AliveThread:
    def __init__(self):
        self.alive = True

    def is_alive(self):
        return self.alive


class RecordingAudioManager:
    def __init__(self):
        self.audio_queue = None
        self.is_recording = False
        self.record_thread = AliveThread()
        self.stop_timeout = None

    def start_stream(self, audio_queue):
        self.audio_queue = audio_queue
        self.is_recording = True
        self.record_thread.alive = True
        return True

    def stop_stream(self, timeout=2.0):
        self.stop_timeout = timeout
        self.is_recording = False
        self.record_thread.alive = False


class FakeModelManager:
    def __init__(self, auto=False):
        self._auto = auto

    def get_input_language(self, language_code=None):
        return INPUT_LANGUAGE_REGISTRY[language_code or "en"]

    def get_input_language_code(self):
        return "en"

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

    def test_start_recognition_uses_disk_spool_when_enabled(self):
        recognizer = WhisperRecognizer(
            FakeConfig(
                {
                    "audio_spool_enabled": True,
                    "audio_spool_min_free_mb": 0,
                    "audio_spool_stale_cleanup_hours": 24,
                }
            ),
            FakeModelManager(),
            FakeLogger(),
        )
        recognizer.model_loaded = True
        audio_manager = RecordingAudioManager()

        started = recognizer.start_recognition(audio_manager)
        captured_queue = audio_manager.audio_queue
        try:
            self.assertTrue(started)
            self.assertIsInstance(captured_queue, DiskBackedAudioQueue)
            self.assertTrue(captured_queue.session_dir.exists())
        finally:
            recognizer.stop_recognition(timeout=1.0)

        self.assertFalse(captured_queue.session_dir.exists())


if __name__ == "__main__":
    unittest.main()
