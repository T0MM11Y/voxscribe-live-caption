"""Language, model, and text transform registry."""

from dataclasses import dataclass
from typing import Dict

from app.dependencies import opencc

class TextTransformStrategy:
    """Base text transform strategy for language-specific output handling."""

    requires_opencc = False

    def transform(self, text: str) -> str:
        return (text or "").strip()

    @property
    def is_available(self) -> bool:
        return True

    @property
    def dependency_message(self) -> str:
        return ""


class OpenCCTransformStrategy(TextTransformStrategy):
    """OpenCC-backed script conversion strategy."""

    requires_opencc = True
    _converters = {}

    def __init__(self, config_name: str):
        self.config_name = config_name

    @property
    def is_available(self) -> bool:
        return opencc is not None

    @property
    def dependency_message(self) -> str:
        return "Install 'opencc-python-reimplemented' for Mandarin Traditional."

    def transform(self, text: str) -> str:
        clean_text = (text or "").strip()
        if not clean_text:
            return ""

        if opencc is None:
            raise RuntimeError(self.dependency_message)

        converter = self._converters.get(self.config_name)
        if converter is None:
            converter = opencc.OpenCC(self.config_name)
            self._converters[self.config_name] = converter

        return converter.convert(clean_text).strip()


TEXT_STRATEGIES = {
    "identity": TextTransformStrategy(),
    "s2tw": OpenCCTransformStrategy("s2tw"),
    "t2s": OpenCCTransformStrategy("t2s"),
}


@dataclass(frozen=True)
class ModelSpec:
    key: str
    display_name: str
    model_name: str
    model_url: str
    size_label: str


@dataclass(frozen=True)
class InputLanguageSpec:
    code: str
    label: str
    model_key: str
    translator_code: str
    recognizer_code: str = ""
    recognition_strategy_key: str = "identity"

    @property
    def recognition_strategy(self) -> TextTransformStrategy:
        return TEXT_STRATEGIES[self.recognition_strategy_key]

    @property
    def engine_code(self) -> str:
        return self.recognizer_code or self.code


@dataclass(frozen=True)
class OutputLanguageSpec:
    code: str
    label: str
    transcript_label: str
    translator_code: str
    output_strategy_key: str = "identity"

    @property
    def output_strategy(self) -> TextTransformStrategy:
        return TEXT_STRATEGIES[self.output_strategy_key]


MODEL_REGISTRY: Dict[str, ModelSpec] = {
    "whisper": ModelSpec(
        key="whisper",
        display_name="Whisper",
        model_name="medium",
        model_url="",
        size_label="about 1.5GB",
    ),
}


AUTO_INPUT_LANGUAGE = "auto"
AUTO_INPUT_LANGUAGE_LABEL = "Auto Detect"
AUTO_DETECT_INPUT_LANGUAGES = ("en", "zh-cn", "id")
SUPPORTED_INPUT_LANGUAGE_CODES = ("en", "zh-cn", "zh-tw", "id")


INPUT_LANGUAGE_REGISTRY: Dict[str, InputLanguageSpec] = {
    "en": InputLanguageSpec(
        code="en", label="English", model_key="whisper", translator_code="en"
    ),
    "zh-cn": InputLanguageSpec(
        code="zh-cn",
        label="Mandarin Simplified (ZH-CN)",
        model_key="whisper",
        translator_code="zh-CN",
        recognizer_code="zh",
    ),
    "zh-tw": InputLanguageSpec(
        code="zh-tw",
        label="Mandarin Traditional (ZH-TW)",
        model_key="whisper",
        translator_code="zh-TW",
        recognizer_code="zh",
        recognition_strategy_key="s2tw",
    ),
    "id": InputLanguageSpec(
        code="id",
        label="Indonesian",
        model_key="whisper",
        translator_code="id",
    ),
}


OUTPUT_LANGUAGE_REGISTRY: Dict[str, OutputLanguageSpec] = {
    "en": OutputLanguageSpec(
        code="en",
        label="English",
        transcript_label="EN",
        translator_code="en",
    ),
    "zh-cn": OutputLanguageSpec(
        code="zh-cn",
        label="Mandarin Simplified (ZH-CN)",
        transcript_label="ZH-CN",
        translator_code="zh-CN",
    ),
    "zh-tw": OutputLanguageSpec(
        code="zh-tw",
        label="Mandarin Traditional (ZH-TW)",
        transcript_label="ZH-TW",
        translator_code="zh-TW",
        output_strategy_key="s2tw",
    ),
    "id": OutputLanguageSpec(
        code="id",
        label="Indonesian",
        transcript_label="ID",
        translator_code="id",
    ),
}


DIRECT_TRANSLATION_STRATEGIES = {
    ("zh-cn", "zh-tw"): TEXT_STRATEGIES["s2tw"],
    ("zh-tw", "zh-cn"): TEXT_STRATEGIES["t2s"],
}


LANGUAGE_ALIASES = {
    "auto": AUTO_INPUT_LANGUAGE,
    "automatic": AUTO_INPUT_LANGUAGE,
    "detect": AUTO_INPUT_LANGUAGE,
    "auto-detect": AUTO_INPUT_LANGUAGE,
    "cn": "zh-cn",
    "zh": "zh-cn",
    "zh_cn": "zh-cn",
    "zh-cn": "zh-cn",
    "zh-hans": "zh-cn",
    "tw": "zh-tw",
    "zh_tw": "zh-tw",
    "zh-tw": "zh-tw",
    "zh-hant": "zh-tw",
    "id": "id",
    "ind": "id",
    "indonesian": "id",
}


DEFAULT_INPUT_LANGUAGE = "en"
DEFAULT_INPUT_LANGUAGE_SETTING = DEFAULT_INPUT_LANGUAGE
DEFAULT_OUTPUT_LANGUAGE = "en"

def canonical_language_code(
    value: str, registry: Dict[str, object], default_code: str
) -> str:
    """Normalize persisted/user language codes without language-specific branching."""
    key = str(value or default_code).strip().lower().replace("_", "-")
    canonical = LANGUAGE_ALIASES.get(key, key)
    if canonical == AUTO_INPUT_LANGUAGE and AUTO_INPUT_LANGUAGE not in registry:
        return default_code
    if canonical == "zh-tw" and canonical not in registry and "zh-cn" in registry:
        return "zh-cn"
    return canonical if canonical in registry else default_code


def input_language_labels():
    return [spec.label for spec in INPUT_LANGUAGE_REGISTRY.values()]


def output_language_labels():
    return [spec.label for spec in OUTPUT_LANGUAGE_REGISTRY.values()]


INPUT_LANGUAGE_BY_LABEL = {
    spec.label: code for code, spec in INPUT_LANGUAGE_REGISTRY.items()
}
OUTPUT_LANGUAGE_BY_LABEL = {
    spec.label: code for code, spec in OUTPUT_LANGUAGE_REGISTRY.items()
}
