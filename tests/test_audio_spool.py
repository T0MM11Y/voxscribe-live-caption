import queue
import tempfile
import unittest
from pathlib import Path

from app.audio.spool import (
    AUDIO_SPOOL_DISK_LOW_ERROR,
    AudioSpoolDiskSpaceError,
    DiskBackedAudioQueue,
)


class AudioSpoolTest(unittest.TestCase):
    def test_write_read_preserves_frame_order_and_deletes_segments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            spool = DiskBackedAudioQueue(
                sample_rate=4,
                base_dir=temp_dir,
                min_free_mb=0,
                stale_cleanup_hours=24,
            )
            try:
                spool.put_nowait(b"first")
                spool.put_nowait(b"second")

                self.assertEqual(spool.qsize(), 2)
                self.assertEqual(spool.get(timeout=0), b"first")
                self.assertEqual(spool.get(timeout=0), b"second")
                self.assertTrue(spool.empty())
                self.assertEqual(list(spool.session_dir.glob("*.pcm")), [])
            finally:
                spool.close()

    def test_get_timeout_raises_queue_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            spool = DiskBackedAudioQueue(base_dir=temp_dir, min_free_mb=0)
            try:
                with self.assertRaises(queue.Empty):
                    spool.get(timeout=0.01)
            finally:
                spool.close()

    def test_backlog_seconds_decreases_after_read(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            spool = DiskBackedAudioQueue(
                sample_rate=4,
                bytes_per_sample=2,
                channels=1,
                base_dir=temp_dir,
                min_free_mb=0,
            )
            try:
                spool.put_nowait(b"12345678")

                self.assertEqual(spool.backlog_bytes, 8)
                self.assertEqual(spool.backlog_seconds, 1.0)

                spool.get(timeout=0)

                self.assertEqual(spool.backlog_bytes, 0)
                self.assertEqual(spool.backlog_seconds, 0.0)
            finally:
                spool.close()

    def test_close_removes_session_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            spool = DiskBackedAudioQueue(base_dir=temp_dir, min_free_mb=0)
            session_dir = spool.session_dir

            self.assertTrue(session_dir.exists())

            spool.close()

            self.assertFalse(session_dir.exists())
            self.assertTrue(Path(temp_dir).exists())

    def test_low_disk_raises_error_without_enqueuing_frame(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            spool = DiskBackedAudioQueue(
                base_dir=temp_dir,
                min_free_mb=1024 * 1024 * 1024,
            )
            try:
                with self.assertRaises(AudioSpoolDiskSpaceError):
                    spool.put_nowait(b"audio")

                self.assertEqual(spool.qsize(), 0)
                self.assertEqual(spool.last_error, AUDIO_SPOOL_DISK_LOW_ERROR)
            finally:
                spool.close()


if __name__ == "__main__":
    unittest.main()
