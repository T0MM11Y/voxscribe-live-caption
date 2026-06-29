"""Transcript service."""

class TranscriptService:
    """Owns transcript entries and renders stable meeting-friendly text blocks."""

    def __init__(self):
        self.entries = []

    def clear(self):
        self.entries = []

    def add_entry(
        self,
        entry_id: int,
        timestamp: str,
        text: str,
        target_language: str,
        target_label: str,
        pending_text: str,
    ) -> dict:
        entry = {
            "id": entry_id,
            "timestamp": timestamp,
            "text": text,
            "target_language": target_language,
            "target_label": target_label,
            "pending_text": pending_text,
            "translation": None,
            "translation_pending": False,
        }
        self.entries.append(entry)
        return entry

    def update_translation(self, entry_id: int, translation: str):
        for entry in self.entries:
            if entry["id"] == entry_id:
                entry["translation_pending"] = False
                entry["translation"] = (translation or "").strip() or None
                return entry
        return None

    def snapshot(self) -> list[dict]:
        return [dict(entry) for entry in self.entries]

    def render(self) -> str:
        blocks = []
        for entry in self.entries:
            lines = [f"[{entry['timestamp']}] {entry['text']}"]
            target_label = entry.get("target_label", "OUT")
            if entry.get("translation"):
                lines.append(f"{target_label}: {entry['translation']}")
            elif entry.get("translation_pending"):
                lines.append(
                    f"{target_label}: {entry.get('pending_text', 'Translating...')}"
                )
            blocks.append("\n".join(lines))
        content = "\n\n".join(blocks)
        return f"{content}\n\n" if content else ""
