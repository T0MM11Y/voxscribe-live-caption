import unittest

from app.core.locale import _L, get_ui_language, set_ui_language


class LocaleTest(unittest.TestCase):
    def test_ui_language_stays_english_for_supported_caption_languages(self):
        for language_code in ("en", "zh-cn", "zh-tw", "id"):
            with self.subTest(language_code=language_code):
                set_ui_language(language_code)

                self.assertEqual(get_ui_language(), "en")
                self.assertEqual(_L("Start Recognition"), "Start Recognition")
                self.assertEqual(_L("READY"), "READY")


if __name__ == "__main__":
    unittest.main()
