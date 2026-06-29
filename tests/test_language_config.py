import unittest

from app.core.config import SimpleConfig
from app.core.languages import (
    DEFAULT_INPUT_LANGUAGE,
    DEFAULT_OUTPUT_LANGUAGE,
    INPUT_LANGUAGE_BY_LABEL,
    INPUT_LANGUAGE_REGISTRY,
    OUTPUT_LANGUAGE_BY_LABEL,
    OUTPUT_LANGUAGE_REGISTRY,
    canonical_language_code,
)


class LanguageConfigTest(unittest.TestCase):
    def test_input_language_choices_are_manual_only(self):
        self.assertEqual(set(INPUT_LANGUAGE_REGISTRY), {"en", "zh-cn", "zh-tw", "id"})
        self.assertEqual(INPUT_LANGUAGE_BY_LABEL["English"], "en")
        self.assertEqual(INPUT_LANGUAGE_BY_LABEL["Mandarin Simplified (ZH-CN)"], "zh-cn")
        self.assertEqual(INPUT_LANGUAGE_BY_LABEL["Mandarin Traditional (ZH-TW)"], "zh-tw")
        self.assertEqual(INPUT_LANGUAGE_BY_LABEL["Indonesian"], "id")

    def test_legacy_auto_detect_falls_back_to_english(self):
        self.assertEqual(
            canonical_language_code("auto", INPUT_LANGUAGE_REGISTRY, DEFAULT_INPUT_LANGUAGE),
            "en",
        )

    def test_traditional_input_is_preserved_as_separate_choice(self):
        self.assertEqual(
            canonical_language_code("zh-tw", INPUT_LANGUAGE_REGISTRY, DEFAULT_INPUT_LANGUAGE),
            "zh-tw",
        )
        traditional = INPUT_LANGUAGE_REGISTRY["zh-tw"]
        self.assertEqual(traditional.model_key, "whisper")
        self.assertEqual(traditional.translator_code, "zh-TW")
        self.assertEqual(traditional.engine_code, "zh")
        self.assertEqual(traditional.recognition_strategy_key, "s2tw")

    def test_mandarin_input_languages_use_whisper_chinese_code(self):
        self.assertEqual(INPUT_LANGUAGE_REGISTRY["zh-cn"].engine_code, "zh")
        self.assertEqual(INPUT_LANGUAGE_REGISTRY["zh-tw"].engine_code, "zh")
        self.assertEqual(INPUT_LANGUAGE_REGISTRY["en"].engine_code, "en")
        self.assertEqual(INPUT_LANGUAGE_REGISTRY["id"].engine_code, "id")

    def test_indonesian_is_a_supported_language(self):
        self.assertEqual(DEFAULT_OUTPUT_LANGUAGE, "en")
        self.assertIn("id", OUTPUT_LANGUAGE_REGISTRY)
        self.assertIn("Indonesian", OUTPUT_LANGUAGE_BY_LABEL)
        self.assertIn("Mandarin Simplified (ZH-CN)", OUTPUT_LANGUAGE_BY_LABEL)
        self.assertIn("Mandarin Traditional (ZH-TW)", OUTPUT_LANGUAGE_BY_LABEL)
        self.assertEqual(
            canonical_language_code("id", OUTPUT_LANGUAGE_REGISTRY, DEFAULT_OUTPUT_LANGUAGE),
            "id",
        )
        self.assertIn("id", INPUT_LANGUAGE_REGISTRY)
        self.assertEqual(
            canonical_language_code("id", INPUT_LANGUAGE_REGISTRY, DEFAULT_INPUT_LANGUAGE),
            "id",
        )

    def test_responsive_latency_profile_caps_legacy_slow_values(self):
        config = SimpleConfig.__new__(SimpleConfig)
        config.config = {
            "translation_latency_profile": "responsive",
            "partial_translation_delay_ms": 650,
            "stable_translation_flush_delay_ms": 1100,
            "stable_translation_short_delay_ms": 850,
            "stable_translation_max_delay_ms": 3500,
            "stable_translation_max_chars": 120,
            "zh_en_accuracy_mode": True,
        }

        config._normalize_latency_config()

        self.assertEqual(config.config["partial_translation_delay_ms"], 500)
        self.assertEqual(config.config["stable_translation_flush_delay_ms"], 650)
        self.assertEqual(config.config["stable_translation_short_delay_ms"], 450)
        self.assertEqual(config.config["stable_translation_max_delay_ms"], 2200)
        self.assertEqual(config.config["stable_translation_max_chars"], 96)
        self.assertFalse(config.config["zh_en_accuracy_mode"])

    def test_integration_api_config_is_normalized(self):
        config = SimpleConfig.__new__(SimpleConfig)
        config.config = {
            "integration_api_enabled": "yes",
            "integration_api_host": " ",
            "integration_api_port": "99999",
            "integration_api_docs_enabled": "off",
        }

        config._normalize_integration_api_config()

        self.assertTrue(config.config["integration_api_enabled"])
        self.assertEqual(config.config["integration_api_host"], "127.0.0.1")
        self.assertEqual(config.config["integration_api_port"], 8765)
        self.assertFalse(config.config["integration_api_docs_enabled"])


if __name__ == "__main__":
    unittest.main()
