import unittest

from app.services.glossary import apply_source_glossary, apply_translation_glossary


class GlossaryTest(unittest.TestCase):
    def test_source_glossary_corrects_meeting_technology_homophones(self):
        text = (
            "我们 爱踢 单位 先 测试, 他们 皮炎 还 没 去 找, "
            "再 跟 开开 大 讨论 API gateway"
        )

        corrected = apply_source_glossary(text, "zh-cn")

        self.assertIn("IT 单位", corrected)
        self.assertIn("PM 还", corrected)
        self.assertIn("KKday 讨论 API Gateway", corrected)

    def test_source_glossary_corrects_project_terms(self):
        text = "后面 几 天 先 做 欧 土坯 专案, 然后 进入 优爱踢 和 系统整合测试"

        corrected = apply_source_glossary(text, "zh-cn")

        self.assertIn("O2P project", corrected)
        self.assertIn("UAT", corrected)
        self.assertIn("SIT", corrected)

    def test_translation_glossary_normalizes_spacing(self):
        text = "hello   API   Gateway"

        corrected = apply_translation_glossary(text, "zh-cn")

        self.assertEqual(corrected, "hello API Gateway")


if __name__ == "__main__":
    unittest.main()
