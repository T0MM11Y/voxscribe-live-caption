import unittest

import numpy as np

from app.audio.capture import AudioManager
from app.audio.spool import AUDIO_SPOOL_DISK_LOW_ERROR


class FakeConfig:
    def get(self, key, default=None):
        values = {"sample_rate": 16000, "chunk_size": 16}
        return values.get(key, default)


class FakeLogger:
    def info(self, _message):
        pass

    def error(self, _message):
        pass

    def warning(self, _message):
        pass


class FakeRecorder:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def record(self, numframes):
        return np.zeros((numframes, 1), dtype=np.float32)


class FakeMicrophone:
    def recorder(self, samplerate, channels):
        return FakeRecorder()


class FailingAudioQueue:
    def put_nowait(self, _data):
        raise RuntimeError(AUDIO_SPOOL_DISK_LOW_ERROR)


class AudioCaptureTest(unittest.TestCase):
    def test_record_worker_stores_last_error_when_audio_queue_write_fails(self):
        manager = AudioManager(FakeConfig(), FakeLogger())
        manager.loopback_microphone = FakeMicrophone()
        manager.is_recording = True

        manager._record_worker(FailingAudioQueue())

        self.assertFalse(manager.is_recording)
        self.assertEqual(manager.last_error, AUDIO_SPOOL_DISK_LOW_ERROR)


if __name__ == "__main__":
    unittest.main()
