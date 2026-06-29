"""Transcript export service."""

from pathlib import Path

class ExportService:
    """Writes transcript exports through one bounded service API."""

    def save_text(self, filename: str, content: str):
        path = Path(filename)
        path.write_text(content, encoding="utf-8")
        return path
