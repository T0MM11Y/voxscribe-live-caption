"""Unified model management for Whisper recognition engine."""

from pathlib import Path
from typing import Optional

from app.core.config import SimpleConfig
from app.core.languages import *
from app.core.logging import SimpleLogger


class ModelManager:
    """Language registry access and single Whisper model lifecycle.

    With Whisper, one model handles all input languages.
    Language-specific model downloads are no longer needed.
    """

    def __init__(self, config: SimpleConfig, logger: SimpleLogger):
        self.config = config
        self.logger = logger

    def get_input_language_code(self) -> str:
        language = self.config.get(
            "input_language",
            self.config.get("language", DEFAULT_INPUT_LANGUAGE_SETTING),
        )
        return canonical_language_code(
            language, INPUT_LANGUAGE_REGISTRY, DEFAULT_INPUT_LANGUAGE_SETTING
        )

    def get_output_language_code(self) -> str:
        language = self.config.get("output_language", DEFAULT_OUTPUT_LANGUAGE)
        return canonical_language_code(
            language, OUTPUT_LANGUAGE_REGISTRY, DEFAULT_OUTPUT_LANGUAGE
        )

    def get_input_language(self, language_code: Optional[str] = None) -> InputLanguageSpec:
        code = canonical_language_code(
            language_code or self.get_input_language_code(),
            INPUT_LANGUAGE_REGISTRY,
            DEFAULT_INPUT_LANGUAGE,
        )
        return INPUT_LANGUAGE_REGISTRY[code]

    def get_output_language(
        self, language_code: Optional[str] = None
    ) -> OutputLanguageSpec:
        code = canonical_language_code(
            language_code or self.get_output_language_code(),
            OUTPUT_LANGUAGE_REGISTRY,
            DEFAULT_OUTPUT_LANGUAGE,
        )
        return OUTPUT_LANGUAGE_REGISTRY[code]

    def get_model_spec(self, language_code: Optional[str] = None) -> ModelSpec:
        _input_language = self.get_input_language(language_code)
        if _input_language.code == AUTO_INPUT_LANGUAGE:
            raise ValueError("Auto Detect uses multiple speech models")
        return MODEL_REGISTRY["whisper"]

    def is_auto_input_language(self, language_code: Optional[str] = None) -> bool:
        code = canonical_language_code(
            language_code or self.get_input_language_code(),
            INPUT_LANGUAGE_REGISTRY,
            DEFAULT_INPUT_LANGUAGE_SETTING,
        )
        return code == AUTO_INPUT_LANGUAGE

    def get_recognition_language_codes(
        self, language_code: Optional[str] = None
    ) -> tuple:
        code = canonical_language_code(
            language_code or self.get_input_language_code(),
            INPUT_LANGUAGE_REGISTRY,
            DEFAULT_INPUT_LANGUAGE_SETTING,
        )
        if code == AUTO_INPUT_LANGUAGE:
            return AUTO_DETECT_INPUT_LANGUAGES
        return (code,)

    def get_model_path(self, language_code: Optional[str] = None) -> Optional[str]:
        """Whisper model is managed by faster-whisper internally."""
        from pathlib import Path
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        if cache_dir.exists():
            return str(cache_dir)
        return str(Path.home() / ".cache" / "faster_whisper")

    def is_model_available(self, language_code: Optional[str] = None) -> bool:
        """Whisper model is considered available once faster-whisper is importable."""
        from app.dependencies import faster_whisper as fw
        return fw is not None

    def missing_model_specs(self, language_code: Optional[str] = None) -> tuple:
        """No per-language model specs to download with Whisper."""
        if not self.is_model_available(language_code):
            return (MODEL_REGISTRY["whisper"],)
        return ()

    def download_model(
        self, progress_callback=None, language_code: Optional[str] = None
    ) -> bool:
        """Trigger Whisper model download via faster-whisper preload."""
        if self.is_model_available(language_code):
            return True

        try:
            if progress_callback:
                progress_callback(0, "Installing faster-whisper dependency...")

            import subprocess
            import sys

            subprocess.run(
                [sys.executable, "-m", "pip", "install", "faster-whisper"],
                check=True,
            )

            if progress_callback:
                progress_callback(100, "Whisper model ready.")

            return self.is_model_available(language_code)
        except Exception as e:
            self.logger.error(f"Failed to install faster-whisper: {e}")
            return False

    def download_models(
        self, progress_callback=None, language_code: Optional[str] = None
    ) -> bool:
        """Single model download for Whisper."""
        return self.download_model(progress_callback, language_code)
