import json
import unittest
from urllib.request import urlopen

from app.integration.openapi import VoxScribeOpenApiServer, build_openapi_spec


class Logger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))


class OpenApiIntegrationTest(unittest.TestCase):
    def test_openapi_spec_uses_local_server_url(self):
        spec = build_openapi_spec(
            "VoxScribe Local API",
            "1.0.0",
            "127.0.0.1",
            8765,
            docs_enabled=True,
        )

        self.assertEqual(spec["openapi"], "3.1.0")
        self.assertEqual(spec["servers"][0]["url"], "http://127.0.0.1:8765")
        self.assertIn("/runtime/snapshot", spec["paths"])
        self.assertIn("/docs", spec["paths"])

    def test_local_server_exposes_snapshot_and_spec(self):
        logger = Logger()
        server = VoxScribeOpenApiServer(
            host="127.0.0.1",
            port=0,
            docs_enabled=True,
            logger=logger,
        )
        server.publish_snapshot(
            {
                "runtime": {
                    "status": "ready",
                    "status_message": "Ready",
                    "is_recognizing": False,
                    "recognition_ready": True,
                    "stats": "Words: 0",
                    "compute_backend_label": "CPU",
                    "device_profile": "mid",
                    "input_language": {"code": "en", "label": "English"},
                    "output_language": {"code": "zh-cn", "label": "Mandarin Simplified (ZH-CN)"},
                    "availability": {"system_busy": False},
                },
                "caption": {
                    "source_text": "hello team",
                    "translated_text": "ni hao team",
                    "source_preview_text": "",
                    "translation_pending": False,
                    "translation_pending_source": "",
                    "current_translation_source": "hello team",
                    "current_translation_source_language": "en",
                    "current_translation_target": "zh-cn",
                },
                "transcript": {
                    "entry_count": 1,
                    "entries": [
                        {
                            "id": 1,
                            "timestamp": "09:00:00",
                            "text": "hello team",
                            "target_language": "zh-cn",
                            "target_label": "ZH-CN",
                            "pending_text": "Translating...",
                            "translation": "ni hao team",
                            "translation_pending": False,
                        }
                    ],
                    "rendered": "[09:00:00] hello team\nZH-CN: ni hao team\n\n",
                },
            }
        )
        server.start()

        try:
            base_url = server.server_url
            with urlopen(f"{base_url}/health") as response:
                health = json.loads(response.read().decode("utf-8"))
            with urlopen(f"{base_url}/openapi.json") as response:
                spec = json.loads(response.read().decode("utf-8"))
            with urlopen(f"{base_url}/runtime/state") as response:
                state = json.loads(response.read().decode("utf-8"))
            with urlopen(f"{base_url}/runtime/transcript") as response:
                transcript = json.loads(response.read().decode("utf-8"))
            with urlopen(f"{base_url}/docs") as response:
                docs_html = response.read().decode("utf-8")
        finally:
            server.stop()

        self.assertEqual(health["status"], "ok")
        self.assertEqual(spec["servers"][0]["url"], base_url)
        self.assertEqual(state["status"], "ready")
        self.assertEqual(transcript["entry_count"], 1)
        self.assertIn("VoxScribe Local API", docs_html)


if __name__ == "__main__":
    unittest.main()
