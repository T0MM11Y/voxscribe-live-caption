"""Asynchronous translation service."""

from collections import OrderedDict
import queue
import threading
from typing import Optional

from app.core.languages import *
from app.core.logging import SimpleLogger
from app.dependencies import GoogleTranslator
from app.services.glossary import apply_source_glossary, apply_translation_glossary

class TranslationManager:
    """Handles asynchronous translation requests for the selected output language."""

    def __init__(self, logger: SimpleLogger):
        self.logger = logger
        self.root = None
        self.result_callback = None
        self.request_queue = queue.PriorityQueue()
        self.worker_thread = None
        self.is_running = False
        self.request_sequence = 0
        self.queue_lock = threading.Lock()
        self.cache_lock = threading.Lock()
        self.latest_partial_request_ids = {}
        self.translation_cache = OrderedDict()
        self.max_translation_cache_size = 256

    @property
    def is_available(self) -> bool:
        return GoogleTranslator is not None

    def can_resolve(self, source_language: str, target_language: str) -> bool:
        """Return True when output can be produced locally or via Google Translate."""
        source_code = canonical_language_code(
            source_language, INPUT_LANGUAGE_REGISTRY, DEFAULT_INPUT_LANGUAGE
        )
        target_code = canonical_language_code(
            target_language, OUTPUT_LANGUAGE_REGISTRY, DEFAULT_OUTPUT_LANGUAGE
        )

        if source_code == AUTO_INPUT_LANGUAGE:
            return any(
                self.can_resolve(code, target_code)
                for code in AUTO_DETECT_INPUT_LANGUAGES
            )

        if source_code == target_code:
            return OUTPUT_LANGUAGE_REGISTRY[target_code].output_strategy.is_available

        direct_strategy = DIRECT_TRANSLATION_STRATEGIES.get((source_code, target_code))
        if direct_strategy:
            return direct_strategy.is_available

        return self.is_available and OUTPUT_LANGUAGE_REGISTRY[target_code].output_strategy.is_available

    def supports_offline_pair(self, source_language: str, target_language: str) -> bool:
        return False

    def is_offline_pair_ready(self, source_language: str, target_language: str) -> bool:
        return False

    def prepare_offline_pair(
        self,
        source_language: str,
        target_language: str,
        progress_callback=None,
    ) -> bool:
        return True

    def start(self, root, result_callback):
        """Start background translation worker."""
        self.root = root
        self.result_callback = result_callback

        if self.is_running:
            return

        self.is_running = True
        self.worker_thread = threading.Thread(
            target=self._translation_worker, daemon=True, name="translation-worker"
        )
        self.worker_thread.start()

    def submit(
        self,
        kind: str,
        text: str,
        request_id: int,
        source_language: str,
        target_language: str,
    ) -> bool:
        """Queue a translation request or resolve script-only output immediately."""
        clean_text = (text or "").strip()
        if not self.is_running or not clean_text:
            return False

        source_code = canonical_language_code(
            source_language, INPUT_LANGUAGE_REGISTRY, DEFAULT_INPUT_LANGUAGE
        )
        target_code = canonical_language_code(
            target_language, OUTPUT_LANGUAGE_REGISTRY, DEFAULT_OUTPUT_LANGUAGE
        )
        if source_code == AUTO_INPUT_LANGUAGE:
            source_code = DEFAULT_INPUT_LANGUAGE
        clean_text = apply_source_glossary(clean_text, source_code)

        direct_result = self._resolve_direct(
            kind, clean_text, request_id, source_code, target_code
        )
        if direct_result is not None:
            self._emit_result(direct_result)
            return True

        cache_key = (source_code, target_code, clean_text)
        cached_translation = self._cached_translation(cache_key)
        if cached_translation is not None:
            result = self._base_result(
                kind, clean_text, request_id, source_code, target_code
            )
            result["translation"] = cached_translation
            self._emit_result(result)
            return True

        if not self.is_available:
            return False

        with self.queue_lock:
            self.request_sequence += 1
            sequence = self.request_sequence
            if kind == "partial":
                self.latest_partial_request_ids[(source_code, target_code)] = request_id

        priority = 0 if kind == "final" else 10
        self.request_queue.put(
            (
                priority,
                sequence,
                {
                    "kind": kind,
                    "text": clean_text,
                    "request_id": request_id,
                    "source_language": source_code,
                    "target_language": target_code,
                    "cache_key": cache_key,
                },
            )
        )
        return True

    def stop(self, timeout: float = 2.0):
        """Stop translation worker cleanly."""
        self.is_running = False

        try:
            self.request_queue.put_nowait((100, 0, None))
        except Exception:
            pass

        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=max(0.0, timeout))

    def _base_result(
        self,
        kind: str,
        text: str,
        request_id: int,
        source_language: str,
        target_language: str,
    ) -> dict:
        return {
            "kind": kind,
            "text": text,
            "request_id": request_id,
            "source_language": source_language,
            "target_language": target_language,
            "translation": "",
            "error": None,
        }

    def _resolve_direct(
        self,
        kind: str,
        text: str,
        request_id: int,
        source_language: str,
        target_language: str,
    ) -> Optional[dict]:
        result = self._base_result(
            kind, text, request_id, source_language, target_language
        )

        strategy = None
        if source_language == target_language:
            strategy = OUTPUT_LANGUAGE_REGISTRY[target_language].output_strategy
        else:
            strategy = DIRECT_TRANSLATION_STRATEGIES.get(
                (source_language, target_language)
            )

        if strategy is None:
            return None

        try:
            result["translation"] = strategy.transform(text)
        except Exception as e:
            result["error"] = str(e)
            self.logger.warning(
                f"Direct output failed for request {request_id}: {e}"
            )
        return result

    def _emit_result(self, result: dict):
        if self.root and self.result_callback and hasattr(self.root, "after"):
            self.root.after(0, lambda r=result: self.result_callback(r))

    def _cached_translation(self, cache_key):
        with self.cache_lock:
            cached = self.translation_cache.get(cache_key)
            if cached is None:
                return None
            self.translation_cache.move_to_end(cache_key)
            return cached

    def _remember_translation(self, cache_key, translation: str):
        clean_translation = (translation or "").strip()
        if not clean_translation:
            return
        with self.cache_lock:
            self.translation_cache[cache_key] = clean_translation
            self.translation_cache.move_to_end(cache_key)
            while len(self.translation_cache) > self.max_translation_cache_size:
                self.translation_cache.popitem(last=False)

    def _is_stale_partial(self, request: dict) -> bool:
        if request.get("kind") != "partial":
            return False
        latest_request_id = self.latest_partial_request_ids.get(
            (request["source_language"], request["target_language"])
        )
        return latest_request_id != request["request_id"]

    def _translation_worker(self):
        translators = {}

        while self.is_running:
            try:
                _, _, request = self.request_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if request is None:
                break

            if self._is_stale_partial(request):
                continue

            source_language = request["source_language"]
            target_language = request["target_language"]
            source_spec = INPUT_LANGUAGE_REGISTRY[source_language]
            target_spec = OUTPUT_LANGUAGE_REGISTRY[target_language]
            result = self._base_result(
                request["kind"],
                request["text"],
                request["request_id"],
                source_language,
                target_language,
            )

            try:
                cached_translation = self._cached_translation(request["cache_key"])
                if cached_translation is not None:
                    result["translation"] = cached_translation
                    self._emit_result(result)
                    continue

                if not self.is_available:
                    raise RuntimeError("Online translator is not available")

                translator_key = (source_language, target_language)
                translator = translators.get(translator_key)
                if translator is None:
                    translator = GoogleTranslator(
                        source=source_spec.translator_code,
                        target=target_spec.translator_code,
                    )
                    translators[translator_key] = translator

                translated_text = translator.translate(request["text"])
                translated_text = target_spec.output_strategy.transform(
                    translated_text or ""
                )
                result["translation"] = apply_translation_glossary(
                    translated_text, target_language
                )
                self._remember_translation(request["cache_key"], result["translation"])
            except Exception as e:
                result["error"] = str(e)
                self.logger.warning(
                    f"Translation failed for request {request['request_id']}: {e}"
                )

            if self._is_stale_partial(request):
                continue
            self._emit_result(result)

        self.is_running = False

TranslationService = TranslationManager
