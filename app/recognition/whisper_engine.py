"""Whisper-based speech recognition engine via faster-whisper."""

import queue
import threading
import time

import numpy as np

from app.core.languages import INPUT_LANGUAGE_REGISTRY
from app.core.logging import SimpleLogger
from app.dependencies import faster_whisper
from app.services.glossary import apply_source_glossary


CAPTURE_STOPPED_ERROR = (
    "Audio capture stopped unexpectedly. Check the selected audio device, "
    "then click Retry Start."
)


class WhisperRecognizer:
    """Handles speech recognition using Whisper via faster-whisper.

    One model handles all languages (en, zh-cn, zh-tw, id).
    Language switching is instant — just change the `language` parameter.
    """

    def __init__(self, config, model_manager, logger):
        self.config = config
        self.model_manager = model_manager
        self.logger = logger

        self.model = None
        self.model_size = str(config.get("whisper_model_size", "large-v3")).strip() or "large-v3"
        self.model_device = str(config.get("compute_device", "cpu")).strip().lower()
        if self.model_device == "cuda":
            self.model_compute_type = "int8_float16"
        else:
            self.model_compute_type = "int8"
        self.model_loaded = False

        self.audio_queue = queue.Queue(
            maxsize=int(config.get("audio_queue_size", 50))
        )
        self.is_running = False
        self.recognition_thread = None
        self.audio_manager = None
        self.active_language_code = "en"

        self.partial_callback = None
        self.final_callback = None
        self.error_callback = None
        self.backlog_callback = None
        self.root = None

        self.sample_rate = int(config.get("sample_rate", 16000))
        self.chunk_duration = float(config.get("whisper_chunk_duration", 10.0))
        self.overlap_duration = float(config.get("whisper_overlap_duration", 1.5))
        self.silence_rms_threshold = float(config.get("whisper_silence_threshold", 0.0005))
        self.no_speech_threshold = float(config.get("whisper_no_speech_threshold", 0.6))
        self.logprob_threshold = float(config.get("whisper_logprob_threshold", -1.0))
        self.compression_ratio_threshold = float(config.get("whisper_compression_ratio_threshold", 2.4))

        self.audio_buffer = bytearray()
        self._chunk_bytes = int(self.sample_rate * 2 * self.chunk_duration)
        self._overlap_bytes = int(self.sample_rate * 2 * self.overlap_duration)

        self._backlog_seconds = 0.0
        self._last_transcribe_ms = 0.0

    def load_model(self, language_code=None):
        if self.model_loaded:
            return True

        try:
            self.model = faster_whisper.WhisperModel(
                self.model_size,
                device=self.model_device,
                compute_type=self.model_compute_type,
            )
            self.model_loaded = True
            self.logger.info(
                f"Whisper model loaded: {self.model_size} on {self.model_device} "
                f"({self.model_compute_type})"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to load Whisper model: {e}")
            return False

    def unload_model(self):
        self.model = None
        self.model_loaded = False

    def set_callbacks(self, partial_callback=None, final_callback=None,
                      error_callback=None, backlog_callback=None):
        self.partial_callback = partial_callback
        self.final_callback = final_callback
        self.error_callback = error_callback
        self.backlog_callback = backlog_callback

    def start_recognition(self, audio_manager):
        if self.is_running:
            self.stop_recognition()

        if not self.model_loaded:
            if not self.load_model():
                return False

        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        self.audio_buffer = bytearray()
        self.is_running = True
        self._backlog_seconds = 0.0
        self.active_language_code = self.model_manager.get_input_language_code()

        if not audio_manager.start_stream(self.audio_queue):
            self.is_running = False
            self.audio_manager = None
            return False

        self.audio_manager = audio_manager
        self.recognition_thread = threading.Thread(
            target=self._recognition_worker, daemon=True
        )
        self.recognition_thread.start()
        self.logger.info(
            f"Whisper recognition started (language={self.active_language_code})"
        )
        return True

    def stop_recognition(self, timeout=2.0):
        self.is_running = False
        if (
            self.recognition_thread
            and self.recognition_thread.is_alive()
            and threading.current_thread() is not self.recognition_thread
        ):
            self.recognition_thread.join(timeout=max(0.0, timeout))
        self.audio_manager = None
        self._backlog_seconds = 0.0
        self.logger.info("Whisper recognition stopped")

    def switch_language(self, language_code):
        self.active_language_code = language_code
        self.logger.info(f"Whisper language switched to {language_code}")
        return True

    def _engine_language_code(self):
        if self.model_manager.is_auto_input_language():
            return None
        code = self.active_language_code or ""
        if code in {"zh-cn", "zh-tw"}:
            return "zh"
        if code in {"en", "id"}:
            return code
        return None

    def _detected_language_code(self, detected_code):
        normalized = str(detected_code or "").strip().lower().replace("_", "-")
        if normalized.startswith("zh"):
            return "zh-cn"
        if normalized in {"en", "id"}:
            return normalized
        return self.active_language_code if self.active_language_code in {"en", "zh-cn", "zh-tw", "id"} else "id"

    def _format_text(self, text):
        corrected = apply_source_glossary(text, self.active_language_code)
        language_spec = self.model_manager.get_input_language(self.active_language_code)
        return language_spec.recognition_strategy.transform(corrected)

    def _emit_final_result(self, text, confidence=0.9):
        if not self.final_callback or not self.root or not hasattr(self.root, "after"):
            return

        payload = {
            "text": text,
            "language_code": self.active_language_code,
            "language_label": self.model_manager.get_input_language(
                self.active_language_code
            ).label,
            "score": confidence,
        }
        self.root.after(0, lambda p=payload: self.final_callback(p))
        self.logger.info(
            f"Whisper: {payload['language_label']} — {text[:80]}"
        )

    def _emit_backlog(self, queue_size, transcribe_ms):
        if not self.backlog_callback or not self.root or not hasattr(self.root, "after"):
            return
        payload = {
            "backlog_seconds": round(self._backlog_seconds, 1),
            "queue_size": queue_size,
            "last_transcribe_ms": round(transcribe_ms, 0),
        }
        self.root.after(0, lambda p=payload: self.backlog_callback(p))

    def _emit_error(self, error):
        if not self.error_callback:
            return

        error_text = str(error)
        if self.root and hasattr(self.root, "after"):
            self.root.after(0, lambda err=error_text: self.error_callback(err))
        else:
            self.error_callback(error_text)

    def _is_capture_stream_alive(self):
        audio_manager = self.audio_manager
        if audio_manager is None:
            return True

        if hasattr(audio_manager, "record_thread"):
            record_thread = getattr(audio_manager, "record_thread", None)
            if record_thread is None or not record_thread.is_alive():
                return False

        if hasattr(audio_manager, "is_recording"):
            return bool(getattr(audio_manager, "is_recording"))

        return True

    def _stop_after_capture_failure(self):
        self.logger.error(CAPTURE_STOPPED_ERROR)
        self.is_running = False
        self._backlog_seconds = 0.0

        audio_manager = self.audio_manager
        if audio_manager and hasattr(audio_manager, "stop_stream"):
            try:
                audio_manager.stop_stream(timeout=0.0)
            except Exception as e:
                self.logger.error(f"Failed to stop audio capture after failure: {e}")

        self._emit_error(CAPTURE_STOPPED_ERROR)

    def _is_hallucination(self, seg):
        if hasattr(seg, "no_speech_prob") and seg.no_speech_prob > self.no_speech_threshold:
            return True
        if hasattr(seg, "avg_logprob") and seg.avg_logprob < self.logprob_threshold:
            return True
        if hasattr(seg, "compression_ratio") and seg.compression_ratio > self.compression_ratio_threshold:
            return True
        return False

    def _recognition_worker(self):
        self.logger.info("Whisper worker thread started")
        last_full_text = ""
        last_emit_time = 0.0
        _last_rms_log = 0.0
        _last_empty_log = 0.0
        _last_backlog_emit = 0.0
        _last_capture_check = 0.0

        while self.is_running:
            now = time.time()
            if now - _last_capture_check > 1.0:
                _last_capture_check = now
                if not self._is_capture_stream_alive():
                    self._stop_after_capture_failure()
                    break

            try:
                data = self.audio_queue.get(timeout=0.15)
                self.audio_buffer.extend(data)
            except queue.Empty:
                continue

            if len(self.audio_buffer) < self._chunk_bytes:
                continue

            audio_bytes = bytes(self.audio_buffer)
            self.audio_buffer = bytearray(
                audio_bytes[-self._overlap_bytes:] if self._overlap_bytes > 0 else b""
            )

            if self.model is None:
                continue

            try:
                audio_np = (
                    np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
                    / 32768.0
                )

                rms = float(np.sqrt(np.mean(audio_np ** 2)))
                if rms < self.silence_rms_threshold:
                    now = time.time()
                    if now - _last_rms_log > 15.0:
                        self.logger.debug(
                            f"Whisper: skipping chunk (RMS {rms:.5f} < threshold {self.silence_rms_threshold})"
                        )
                        _last_rms_log = now
                    continue

                t_start = time.time()

                segments, info = self.model.transcribe(
                    audio_np,
                    language=self._engine_language_code(),
                    beam_size=5,
                    vad_filter=True,
                    condition_on_previous_text=False,
                )
                if self.model_manager.is_auto_input_language():
                    detected_language = self._detected_language_code(getattr(info, "language", None))
                    self.active_language_code = detected_language

                accepted_texts = []
                logprob_sum = 0.0
                logprob_count = 0
                skipped = 0

                for seg in segments:
                    if not seg.text.strip():
                        continue
                    if seg.start < self.overlap_duration:
                        continue
                    if self._is_hallucination(seg):
                        skipped += 1
                        continue
                    accepted_texts.append(seg.text.strip())
                    if hasattr(seg, "avg_logprob"):
                        logprob_sum += seg.avg_logprob
                        logprob_count += 1

                full_text = " ".join(accepted_texts)

                t_end = time.time()
                transcribe_ms = (t_end - t_start) * 1000
                self._last_transcribe_ms = transcribe_ms

                queue_size = self.audio_queue.qsize()
                bytes_per_second = self.sample_rate * 2
                queued_audio_seconds = 0.0
                if queue_size > 0:
                    chunk_size = int(self.config.get("chunk_size", 4096))
                    queued_audio_seconds = (queue_size * chunk_size * 2) / bytes_per_second
                self._backlog_seconds = queued_audio_seconds + len(self.audio_buffer) / bytes_per_second

                now = time.time()
                if now - _last_backlog_emit > 2.0:
                    self._emit_backlog(queue_size, transcribe_ms)
                    _last_backlog_emit = now

                if skipped > 0:
                    self.logger.debug(
                        f"Whisper: filtered {skipped} hallucinated segment(s), "
                        f"transcribe {transcribe_ms:.0f}ms, queue {queue_size}"
                    )

                if not full_text:
                    if now - _last_empty_log > 15.0:
                        self.logger.debug("Whisper: chunk produced no speech (VAD/filter)")
                        _last_empty_log = now
                    continue

                if now - last_emit_time > 10.0:
                    last_full_text = ""

                if full_text != last_full_text:
                    last_full_text = full_text
                    last_emit_time = now
                    display_text = self._format_text(full_text)
                    confidence = 0.9
                    if logprob_count > 0:
                        avg_lp = logprob_sum / logprob_count
                        confidence = max(0.1, min(1.0, 1.0 + avg_lp))
                    self._emit_final_result(display_text, confidence)

            except Exception as e:
                self.logger.error(f"Whisper transcription error: {e}")
                self._emit_error(e)

        self.logger.info("Whisper worker thread ended")

    def cleanup(self, timeout=2.0):
        self.stop_recognition(timeout=timeout)
        self.unload_model()
