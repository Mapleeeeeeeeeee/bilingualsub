"""Glossary manager for term preservation during translation."""

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger()


class GlossaryError(Exception):
    """Raised when glossary operations fail."""


class GlossaryNotFoundError(GlossaryError):
    """Raised when a glossary term is not found."""


_MAX_ENTRIES = 500
_MAX_TERM_LENGTH = 100


@dataclass
class GlossaryEntry:
    source: str
    target: str


class GlossaryManager:
    """Manages glossary terms with JSON file persistence."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: dict[str, GlossaryEntry] = {}
        self._prompt_cache: str | None = None
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Load glossary from JSON file. Does nothing if file does not exist."""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for e in data.get("entries", []):
                try:
                    self._entries[e["source"]] = GlossaryEntry(
                        source=e["source"], target=e["target"]
                    )
                except (KeyError, TypeError):
                    logger.warning("glossary_entry_skipped", entry=e)
        except json.JSONDecodeError:
            logger.warning("glossary_corrupted", path=str(self._path))
            self._path.rename(self._path.with_suffix(".json.bak"))
            self._entries = {}

    def _save(self) -> None:
        """Persist glossary to JSON file atomically."""
        data = {
            "entries": [
                {"source": e.source, "target": e.target} for e in self._sorted_entries()
            ]
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self._path)
        self._prompt_cache = None

    def _sorted_entries(self) -> list[GlossaryEntry]:
        return sorted(self._entries.values(), key=lambda x: x.source.lower())

    def _validate_terms(self, source: str, target: str) -> tuple[str, str]:
        source, target = source.strip(), target.strip()
        if not source:
            raise GlossaryError("Source term cannot be empty")
        if len(source) > _MAX_TERM_LENGTH or len(target) > _MAX_TERM_LENGTH:
            raise GlossaryError(
                f"Term length cannot exceed {_MAX_TERM_LENGTH} characters"
            )
        return source, target

    def get_all(self) -> list[GlossaryEntry]:
        return self._sorted_entries()

    def add(self, source: str, target: str) -> GlossaryEntry:
        source, target = self._validate_terms(source, target)
        with self._lock:
            if source in self._entries:
                entry = GlossaryEntry(source=source, target=target)
                self._entries[source] = entry
                self._save()
                return entry
            if len(self._entries) >= _MAX_ENTRIES:
                raise GlossaryError(f"Glossary is full (max {_MAX_ENTRIES} entries)")
            entry = GlossaryEntry(source=source, target=target)
            self._entries[source] = entry
            self._save()
            return entry

    def update(self, source: str, target: str) -> GlossaryEntry:
        source, target = self._validate_terms(source, target)
        with self._lock:
            if source not in self._entries:
                raise GlossaryNotFoundError(f"Term '{source}' not found")
            entry = GlossaryEntry(source=source, target=target)
            self._entries[source] = entry
            self._save()
            return entry

    def delete(self, source: str) -> None:
        source = source.strip()
        with self._lock:
            if source not in self._entries:
                raise GlossaryNotFoundError(f"Term '{source}' not found")
            del self._entries[source]
            self._save()

    def format_for_prompt(self) -> str:
        """Format glossary as a string for injection into translation prompt."""
        if not self._entries:
            return ""
        if self._prompt_cache is not None:
            return self._prompt_cache
        lines = [f"{e.source} → {e.target}" for e in self.get_all()]
        self._prompt_cache = (
            "以下是術語表，請嚴格依照此表翻譯對應的專有名詞：\n" + "\n".join(lines)  # noqa: RUF001
        )
        return self._prompt_cache
