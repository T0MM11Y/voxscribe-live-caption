import time
import unittest

from app.core.languages import INPUT_LANGUAGE_REGISTRY, OUTPUT_LANGUAGE_REGISTRY
import app.translation.service as translation_module
from app.translation.service import TranslationManager


class Logger:
    def warning(self, message):
        pass


class ImmediateRoot:
    def after(self, delay_ms, callback):
        callback()


class FakeGoogleTranslator:
    calls = []

    def __init__(self, source, target):
        self.source = source
        self.target = target
        self.calls.append((source, target))

    def translate(self, text):
        return f"{self.source}->{self.target}:{text}"


class TranslationServiceTest(unittest.TestCase):
    def setUp(self):
        self.original_translator = translation_module.GoogleTranslator
        translation_module.GoogleTranslator = object

    def tearDown(self):
        translation_module.GoogleTranslator = self.original_translator

    def test_final_requests_are_prioritized_over_partial_queue(self):
        manager = TranslationManager(Logger())
        manager.is_running = True

        manager.submit("partial", "hello", 1, "en", "zh-cn")
        manager.submit("final", "hello team", 2, "en", "zh-cn")

        _, _, first_request = manager.request_queue.get_nowait()
        _, _, second_request = manager.request_queue.get_nowait()

        self.assertEqual(first_request["kind"], "final")
        self.assertEqual(second_request["kind"], "partial")

    def test_stale_partials_are_detected_before_network_work(self):
        manager = TranslationManager(Logger())
        manager.is_running = True

        manager.submit("partial", "hello", 1, "en", "zh-cn")
        manager.submit("partial", "hello team", 2, "en", "zh-cn")

        _, _, stale_request = manager.request_queue.get_nowait()
        _, _, fresh_request = manager.request_queue.get_nowait()

        self.assertTrue(manager._is_stale_partial(stale_request))
        self.assertFalse(manager._is_stale_partial(fresh_request))

    def test_exact_cache_hit_emits_without_queueing(self):
        manager = TranslationManager(Logger())
        manager.is_running = True
        results = []
        manager.root = ImmediateRoot()
        manager.result_callback = results.append
        manager._remember_translation(("en", "zh-cn", "hello"), "translated hello")

        submitted = manager.submit("final", "hello", 1, "en", "zh-cn")

        self.assertTrue(submitted)
        self.assertEqual(results[0]["translation"], "translated hello")
        self.assertTrue(manager.request_queue.empty())

    def test_submit_requires_online_translator(self):
        translation_module.GoogleTranslator = None
        manager = TranslationManager(Logger())
        manager.is_running = True

        self.assertFalse(manager.can_resolve("zh-cn", "en"))
        submitted = manager.submit("final", "\u4f60\u597d", 1, "zh-cn", "en")

        self.assertFalse(submitted)
        self.assertTrue(manager.request_queue.empty())

    def test_offline_pair_api_is_disabled_in_online_mode(self):
        manager = TranslationManager(Logger())

        self.assertFalse(manager.is_offline_pair_ready("zh-cn", "en"))
        prepared = manager.prepare_offline_pair(
            "zh-cn", "en", None
        )

        self.assertTrue(prepared)
        self.assertFalse(manager.is_offline_pair_ready("zh-cn", "en"))

    def test_same_language_pairs_resolve_without_online_translator(self):
        translation_module.GoogleTranslator = None
        samples = {
            "en": "hello team",
            "zh-cn": "\u8f6f\u4ef6\u6d4b\u8bd5",
            "zh-tw": "\u8edf\u9ad4\u6e2c\u8a66",
            "id": "halo tim",
        }
        manager = TranslationManager(Logger())
        manager.is_running = True
        results = []
        manager.root = ImmediateRoot()
        manager.result_callback = results.append

        for request_id, code in enumerate(samples, start=1):
            submitted = manager.submit("final", samples[code], request_id, code, code)

            self.assertTrue(submitted)

        self.assertTrue(manager.request_queue.empty())
        self.assertEqual(len(results), len(samples))
        for result in results:
            self.assertEqual(result["translation"], samples[result["source_language"]])
            self.assertIsNone(result["error"])

    def test_chinese_script_pairs_resolve_without_online_translator(self):
        translation_module.GoogleTranslator = None
        manager = TranslationManager(Logger())
        manager.is_running = True
        results = []
        manager.root = ImmediateRoot()
        manager.result_callback = results.append

        self.assertTrue(
            manager.submit("final", "\u8f6f\u4ef6\u6d4b\u8bd5", 1, "zh-cn", "zh-tw")
        )
        self.assertTrue(
            manager.submit("final", "\u8edf\u9ad4\u6e2c\u8a66", 2, "zh-tw", "zh-cn")
        )

        self.assertTrue(manager.request_queue.empty())
        self.assertEqual(results[0]["translation"], "\u8edf\u4ef6\u6e2c\u8a66")
        self.assertEqual(results[1]["translation"], "\u8f6f\u4f53\u6d4b\u8bd5")
        self.assertTrue(all(result["error"] is None for result in results))

    def test_supported_cross_language_pairs_use_registry_translator_codes(self):
        FakeGoogleTranslator.calls = []
        translation_module.GoogleTranslator = FakeGoogleTranslator
        manager = TranslationManager(Logger())
        results = []
        manager.start(ImmediateRoot(), results.append)
        samples = {
            "en": "hello team",
            "zh-cn": "\u4f60\u597d",
            "zh-tw": "\u4f60\u597d",
            "id": "halo tim",
        }
        request_id = 0

        for source_code in samples:
            for target_code in samples:
                request_id += 1
                self.assertTrue(
                    manager.submit(
                        "final",
                        samples[source_code],
                        request_id,
                        source_code,
                        target_code,
                    )
                )

        deadline = time.time() + 2.0
        while len(results) < 16 and time.time() < deadline:
            time.sleep(0.01)
        manager.stop()

        expected_online_calls = []
        for source_code in samples:
            for target_code in samples:
                is_same_language = source_code == target_code
                is_direct_chinese = (source_code, target_code) in {
                    ("zh-cn", "zh-tw"),
                    ("zh-tw", "zh-cn"),
                }
                if is_same_language or is_direct_chinese:
                    continue
                expected_online_calls.append(
                    (
                        INPUT_LANGUAGE_REGISTRY[source_code].translator_code,
                        OUTPUT_LANGUAGE_REGISTRY[target_code].translator_code,
                    )
                )

        self.assertCountEqual(FakeGoogleTranslator.calls, expected_online_calls)
        self.assertEqual(len(results), 16)


if __name__ == "__main__":
    unittest.main()
