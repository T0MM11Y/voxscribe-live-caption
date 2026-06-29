"""Disk-backed FIFO for captured PCM audio frames."""

import os
import queue
import shutil
import threading
import time
from collections import deque
from pathlib import Path


AUDIO_SPOOL_DISK_LOW_ERROR = (
    "Audio spool disk space is low. Free disk space, then click Retry Start."
)


class AudioSpoolError(RuntimeError):
    """Base error for disk-backed audio spool failures."""


class AudioSpoolDiskSpaceError(AudioSpoolError):
    """Raised when the spool cannot safely accept more audio."""


class DiskBackedAudioQueue:
    """FIFO queue that stores audio frames on disk instead of in memory."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        bytes_per_sample: int = 2,
        base_dir=None,
        min_free_mb: int = 1024,
        stale_cleanup_hours: int = 24,
        logger=None,
        cleanup_on_close: bool = True,
    ):
        self.sample_rate = max(1, int(sample_rate))
        self.channels = max(1, int(channels))
        self.bytes_per_sample = max(1, int(bytes_per_sample))
        self.min_free_bytes = max(0, int(min_free_mb)) * 1024 * 1024
        self.stale_cleanup_seconds = max(1, int(stale_cleanup_hours)) * 3600
        self.logger = logger
        self.cleanup_on_close = cleanup_on_close

        self.base_dir = Path(base_dir) if base_dir else Path.home() / ".voxscribe" / "audio_spool"
        self.base_dir = self.base_dir.expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale_sessions()

        stamp = time.strftime("%Y%m%d-%H%M%S")
        unique = f"{stamp}-{os.getpid()}-{time.monotonic_ns()}"
        self.session_dir = (self.base_dir / f"session-{unique}").resolve()
        self._ensure_inside_base(self.session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=False)

        self._condition = threading.Condition()
        self._segments = deque()
        self._next_index = 0
        self._closed = False
        self.backlog_bytes = 0
        self.last_error = ""

    @property
    def bytes_per_second(self) -> int:
        return self.sample_rate * self.channels * self.bytes_per_sample

    @property
    def backlog_seconds(self) -> float:
        with self._condition:
            return self.backlog_bytes / float(self.bytes_per_second)

    def put_nowait(self, data):
        frame = bytes(data)
        self._ensure_can_write(len(frame))

        with self._condition:
            if self._closed:
                raise AudioSpoolError("Audio spool is closed")
            index = self._next_index
            self._next_index += 1

        tmp_path = self.session_dir / f"{index:012d}.tmp"
        final_path = self.session_dir / f"{index:012d}.pcm"

        try:
            with open(tmp_path, "wb") as handle:
                handle.write(frame)
            os.replace(tmp_path, final_path)
        except Exception as e:
            self._delete_file(tmp_path)
            self.last_error = f"Audio spool write failed: {e}"
            raise AudioSpoolError(self.last_error) from e

        with self._condition:
            if self._closed:
                self._delete_file(final_path)
                raise AudioSpoolError("Audio spool is closed")
            self._segments.append((final_path, len(frame)))
            self.backlog_bytes += len(frame)
            self._condition.notify()

    def get(self, timeout=None):
        path, size = self._pop_segment(timeout)

        try:
            data = path.read_bytes()
        except Exception as e:
            self.last_error = f"Audio spool read failed: {e}"
            raise AudioSpoolError(self.last_error) from e
        finally:
            self._delete_file(path)

        return data

    def get_nowait(self):
        return self.get(timeout=0)

    def qsize(self) -> int:
        with self._condition:
            return len(self._segments)

    def empty(self) -> bool:
        return self.qsize() == 0

    def clear(self):
        with self._condition:
            segments = list(self._segments)
            self._segments.clear()
            self.backlog_bytes = 0

        for path, _size in segments:
            self._delete_file(path)
        for path in self.session_dir.glob("*.tmp"):
            self._delete_file(path)

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()

        self.clear()
        if self.cleanup_on_close:
            self._delete_session_dir()

    def _pop_segment(self, timeout):
        deadline = None
        if timeout is not None:
            timeout = max(0.0, float(timeout))
            deadline = time.monotonic() + timeout

        with self._condition:
            while not self._segments:
                if self._closed:
                    raise queue.Empty
                if timeout is None:
                    self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty
                self._condition.wait(remaining)

            path, size = self._segments.popleft()
            self.backlog_bytes = max(0, self.backlog_bytes - size)
            return path, size

    def _ensure_can_write(self, frame_size: int):
        try:
            free_bytes = shutil.disk_usage(self.base_dir).free
        except Exception as e:
            self.last_error = f"Audio spool disk check failed: {e}"
            raise AudioSpoolError(self.last_error) from e

        if free_bytes < self.min_free_bytes + max(0, frame_size):
            self.last_error = AUDIO_SPOOL_DISK_LOW_ERROR
            raise AudioSpoolDiskSpaceError(self.last_error)

    def _cleanup_stale_sessions(self):
        now = time.time()
        for path in self.base_dir.glob("session-*"):
            try:
                resolved = path.resolve()
                self._ensure_inside_base(resolved)
                if not resolved.is_dir():
                    continue
                age_seconds = now - resolved.stat().st_mtime
                if age_seconds >= self.stale_cleanup_seconds:
                    shutil.rmtree(resolved, ignore_errors=True)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to clean stale audio spool {path}: {e}")

    def _delete_session_dir(self):
        try:
            self._ensure_inside_base(self.session_dir)
            shutil.rmtree(self.session_dir, ignore_errors=True)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to remove audio spool session: {e}")

    def _ensure_inside_base(self, path: Path):
        try:
            path.relative_to(self.base_dir)
        except ValueError as e:
            raise AudioSpoolError(f"Refusing to access path outside spool dir: {path}") from e

    def _delete_file(self, path: Path):
        try:
            self._ensure_inside_base(path.resolve())
            path.unlink(missing_ok=True)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to remove audio spool file {path}: {e}")
