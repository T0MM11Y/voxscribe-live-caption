"""Language hot-swap service."""

from app.core.logging import SimpleLogger
from app.recognition.model_manager import ModelManager
from app.recognition.whisper_engine import WhisperRecognizer

class LanguageSwitcher:
    """Controller-friendly facade for recognizer hot-swap operations."""

    def __init__(
        self,
        model_manager: ModelManager,
        recognizer: WhisperRecognizer,
        logger: SimpleLogger,
    ):
        self.model_manager = model_manager
        self.recognizer = recognizer
        self.logger = logger

    def switch(self, language_code: str) -> bool:
        language = self.model_manager.get_input_language(language_code)
        self.logger.info(f"LanguageSwitcher switching to {language.label}")
        return self.recognizer.switch_language(language_code)
