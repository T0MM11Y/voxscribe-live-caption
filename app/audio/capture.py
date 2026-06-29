"""Audio capture service — loopback or microphone."""

import queue
import sys
import threading

from app.core.config import SimpleConfig
from app.core.logging import SimpleLogger

class AudioManager:
    """Manages audio input — loopback (speaker output) or microphone."""

    def __init__(self, config: SimpleConfig, logger: SimpleLogger):
        self.config = config
        self.logger = logger
        self.is_recording = False
        self.record_thread = None
        self.initialize_lock = threading.Lock()
        self.loopback_microphone = None
        self.loopback_speaker_name = ""
        self.initialized = False
        self.recorder_probe_ok = False
        self._source_type = "loopback"

    @property
    def source_type(self) -> str:
        return self._source_type

    @source_type.setter
    def source_type(self, value: str):
        if value not in ("loopback", "microphone"):
            raise ValueError(f"Invalid audio source: {value}")
        self._source_type = value

    def initialize(
        self, force_refresh: bool = False, probe_recorder: bool = False
    ) -> bool:
        if "soundcard" not in sys.modules:
            return False

        with self.initialize_lock:
            if (
                self.initialized
                and self.loopback_microphone
                and not force_refresh
                and (not probe_recorder or self.recorder_probe_ok)
            ):
                return True

            try:
                import soundcard as sc

                source_type = str(self.config.get("audio_source_type", "loopback") or "loopback")
                self._source_type = source_type

                if source_type == "microphone":
                    microphone = sc.default_microphone()
                    device_name = str(microphone.name)
                    self.logger.info(f"Using microphone: {device_name}")
                else:
                    speaker = sc.default_speaker()
                    microphone = sc.get_microphone(
                        id=str(speaker.name), include_loopback=True
                    )
                    device_name = str(speaker.name)
                    self.logger.info(f"Using loopback device: {device_name}")

                self.loopback_microphone = microphone
                self.loopback_speaker_name = device_name
                if probe_recorder:
                    self._probe_recorder(microphone)
                    self.recorder_probe_ok = True
                self.initialized = True
                self.logger.info(
                    f"Audio device ready ({source_type}): {device_name}"
                )
                return True
            except Exception as e:
                self.loopback_microphone = None
                self.loopback_speaker_name = ""
                self.initialized = False
                self.recorder_probe_ok = False
                self.logger.error(f"Audio initialization error: {e}")
                return False

    def is_initialized(self) -> bool:
        return self.initialized and self.loopback_microphone is not None

    def _probe_recorder(self, microphone):
        sample_rate = self.config.get("sample_rate", 16000)
        with microphone.recorder(samplerate=sample_rate, channels=1) as recorder:
            recorder.record(numframes=1)

    def get_device_list(self):
        return []

    def start_stream(self, audio_queue) -> bool:
        if not self.initialize():
            return False
        if self.is_recording:
            return True

        self.is_recording = True
        self.record_thread = threading.Thread(
            target=self._record_worker, args=(audio_queue,), daemon=True
        )
        self.record_thread.start()
        self.logger.info(f"Audio stream started successfully ({self._source_type})")
        return True

    def _record_worker(self, audio_queue):
        try:
            import numpy as np

            sample_rate = self.config.get("sample_rate", 16000)
            chunk_size = self.config.get("chunk_size", 4096)
            mic = self.loopback_microphone
            if mic is None:
                raise RuntimeError("Audio device is not initialized")

            with mic.recorder(samplerate=sample_rate, channels=1) as recorder:
                while self.is_recording:
                    data = recorder.record(numframes=chunk_size)
                    data_int16 = (data * 32767).astype(np.int16).tobytes()

                    try:
                        audio_queue.put_nowait(data_int16)
                    except queue.Full:
                        self.logger.warning("Audio queue full — frame dropped")
        except Exception as e:
            self.logger.error(f"Recording error: {e}")
            self.is_recording = False
            self.initialized = False
            self.recorder_probe_ok = False

    def stop_stream(self, timeout: float = 2.0):
        self.is_recording = False
        if self.record_thread and self.record_thread.is_alive():
            self.record_thread.join(timeout=max(0.0, timeout))
        self.record_thread = None
        self.logger.info("Audio stream stopped")

    def cleanup(self, timeout: float = 2.0):
        self.stop_stream(timeout=timeout)

AudioCaptureService = AudioManager
