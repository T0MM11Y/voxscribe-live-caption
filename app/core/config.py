"""Configuration persistence."""

import json
import shutil
from pathlib import Path

from app.core.languages import (
    DEFAULT_INPUT_LANGUAGE,
    DEFAULT_INPUT_LANGUAGE_SETTING,
    DEFAULT_OUTPUT_LANGUAGE,
    INPUT_LANGUAGE_REGISTRY,
    OUTPUT_LANGUAGE_REGISTRY,
    canonical_language_code,
)

class SimpleConfig:
    """Simplified configuration manager"""

    def __init__(self):
        self.config = {
            "language": "en",
            "input_language": DEFAULT_INPUT_LANGUAGE_SETTING,
            "output_language": DEFAULT_OUTPUT_LANGUAGE,
            "compute_device": "cpu",
            "compute_type": "default",
            "compute_backend_label": "CPU",
            "device_profile": "mid",
            "audio_queue_size": 2000,
            "partial_translation_delay_ms": 500,
            "stable_translation_flush_delay_ms": 650,
            "stable_translation_short_delay_ms": 450,
            "stable_translation_max_delay_ms": 2200,
            "stable_translation_max_chars": 96,
            "translation_latency_profile": "responsive",
            "zh_en_accuracy_mode": False,
            "zh_en_stable_translation_flush_delay_ms": 1450,
            "zh_en_stable_translation_short_delay_ms": 1150,
            "zh_en_stable_translation_max_delay_ms": 5200,
            "zh_en_stable_translation_max_chars": 180,
            "audio_source_type": "loopback",
            "preload_secondary_model": False,
            "max_cached_models": 1,
            "model_type": "large",
            "whisper_model_size": "large-v3",
            "whisper_chunk_duration": 10.0,
            "whisper_overlap_duration": 1.5,
            "whisper_silence_threshold": 0.0005,
            "whisper_no_speech_threshold": 0.6,
            "whisper_logprob_threshold": -1.0,
            "whisper_compression_ratio_threshold": 2.4,
            "sample_rate": 16000,
            "chunk_size": 4096,
            "window_width": 850,
            "window_height": 600,
            "font_size": 12,
            "overlay_font_size": 16,
            "overlay_font_profile": "subtitle_v3",
            "overlay_compact": True,
            "overlay_x": None,
            "overlay_y": None,
            "startup_prepared_model_keys": {},
            "grammar": None,
            "integration_api_enabled": False,
            "integration_api_host": "127.0.0.1",
            "integration_api_port": 8765,
            "integration_api_docs_enabled": True,
        }
        self.config_file = Path.home() / ".voxscribe" / "config.json"
        self._migrate_legacy_config()
        self.load_config()

    def _migrate_legacy_config(self):
        legacy_dir = Path.home() / ".livec4ption"
        legacy_file = legacy_dir / "config.json"
        if legacy_file.exists() and not self.config_file.exists():
            try:
                self.config_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(legacy_file), str(self.config_file))
            except Exception:
                pass

    def load_config(self):
        """Load configuration from file"""
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                    self.config.update(user_config)
        except Exception:
            pass
        self._normalize_language_config()
        self._normalize_latency_config()
        self._normalize_integration_api_config()

    def _normalize_language_config(self):
        """Keep legacy language config compatible with the new input/output split."""
        legacy_language = self.config.get("language", DEFAULT_INPUT_LANGUAGE)
        input_language = self.config.get(
            "input_language", DEFAULT_INPUT_LANGUAGE_SETTING
        )
        output_language = self.config.get("output_language", DEFAULT_OUTPUT_LANGUAGE)

        normalized_input = canonical_language_code(
            input_language or legacy_language,
            INPUT_LANGUAGE_REGISTRY,
            DEFAULT_INPUT_LANGUAGE_SETTING,
        )
        normalized_output = canonical_language_code(
            output_language, OUTPUT_LANGUAGE_REGISTRY, DEFAULT_OUTPUT_LANGUAGE
        )

        self.config["input_language"] = normalized_input
        self.config["language"] = normalized_input
        self.config["output_language"] = normalized_output

        compute_device = str(self.config.get("compute_device", "cpu")).strip().lower()
        if compute_device not in {"cpu", "cuda"}:
            compute_device = "cpu"
        self.config["compute_device"] = compute_device

        compute_type = str(self.config.get("compute_type", "default")).strip().lower()
        if compute_type not in {"default", "int8"}:
            compute_type = "default"
        self.config["compute_type"] = compute_type

        backend_label = str(self.config.get("compute_backend_label", "")).strip()
        if not backend_label:
            backend_label = "CUDA INT8" if compute_device == "cuda" else "CPU"
        self.config["compute_backend_label"] = backend_label

    def _normalize_latency_config(self):
        """Keep old saved slow-buffer settings from overriding responsive defaults."""
        profile = str(
            self.config.get("translation_latency_profile", "responsive")
            or "responsive"
        ).strip().lower()
        if profile not in {"responsive", "quality"}:
            profile = "responsive"
        self.config["translation_latency_profile"] = profile

        if profile == "quality":
            return

        self.config["zh_en_accuracy_mode"] = False
        self.config["partial_translation_delay_ms"] = self._capped_int(
            "partial_translation_delay_ms", 500, 500
        )
        self.config["stable_translation_flush_delay_ms"] = self._capped_int(
            "stable_translation_flush_delay_ms", 650, 650
        )
        self.config["stable_translation_short_delay_ms"] = self._capped_int(
            "stable_translation_short_delay_ms", 450, 450
        )
        self.config["stable_translation_max_delay_ms"] = self._capped_int(
            "stable_translation_max_delay_ms", 2200, 2200
        )
        self.config["stable_translation_max_chars"] = self._capped_int(
            "stable_translation_max_chars", 96, 96
        )

    def _normalize_integration_api_config(self):
        """Keep the optional local integration API config stable and safe."""
        self.config["integration_api_enabled"] = self._coerce_bool(
            self.config.get("integration_api_enabled", False), False
        )
        self.config["integration_api_docs_enabled"] = self._coerce_bool(
            self.config.get("integration_api_docs_enabled", True), True
        )

        host = str(
            self.config.get("integration_api_host", "127.0.0.1") or "127.0.0.1"
        ).strip()
        self.config["integration_api_host"] = host or "127.0.0.1"

        try:
            port = int(self.config.get("integration_api_port", 8765))
        except Exception:
            port = 8765
        if port < 1 or port > 65535:
            port = 8765
        self.config["integration_api_port"] = port

    def _capped_int(self, key: str, default: int, maximum: int) -> int:
        try:
            value = int(self.config.get(key, default))
        except Exception:
            value = default
        return max(1, min(value, maximum))

    def _coerce_bool(self, value, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)

        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default

    def save_config(self):
        """Save configuration to file"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value):
        self.config[key] = value
