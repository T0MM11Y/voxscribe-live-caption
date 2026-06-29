import unittest

from app.services.transcript import TranscriptService


class TranscriptServiceTest(unittest.TestCase):
    def test_render_pending_and_translated_entries(self):
        service = TranscriptService()
        entry = service.add_entry(
            entry_id=1,
            timestamp="09:00:00",
            text="hello team",
            target_language="zh-cn",
            target_label="ZH-CN",
            pending_text="Translating...",
        )
        entry["translation_pending"] = True

        self.assertIn("ZH-CN: Translating...", service.render())

        service.update_translation(1, "translated hello team")

        rendered = service.render()
        self.assertIn("[09:00:00] hello team", rendered)
        self.assertIn("ZH-CN: translated hello team", rendered)


if __name__ == "__main__":
    unittest.main()
