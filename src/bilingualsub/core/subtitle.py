"""Subtitle domain models."""

from dataclasses import dataclass
from datetime import timedelta


@dataclass
class SubtitleEntry:
    """Single subtitle entry with timing and text."""

    index: int
    start: timedelta
    end: timedelta
    text: str

    def __post_init__(self):
        """Validate subtitle entry constraints."""
        if self.start >= self.end:
            raise ValueError(
                f"Start time {self.start} must be before end time {self.end}"
            )
        if self.index < 1:
            raise ValueError(f"Index must be positive, got {self.index}")
        if not self.text.strip():
            raise ValueError("Text cannot be empty or whitespace-only")


@dataclass
class Subtitle:
    """Collection of subtitle entries."""

    entries: list[SubtitleEntry]

    def __post_init__(self):
        """Validate subtitle collection constraints."""
        if not self.entries:
            raise ValueError("Subtitle must contain at least one entry")

        # Validate indices are sequential
        for i, entry in enumerate(self.entries, start=1):
            if entry.index != i:
                raise ValueError(
                    f"Entry indices must be sequential starting from 1, "
                    f"expected {i} but got {entry.index}"
                )

        # Validate no overlapping time ranges
        for i in range(len(self.entries) - 1):
            current = self.entries[i]
            next_entry = self.entries[i + 1]
            if current.end > next_entry.start:
                raise ValueError(
                    f"Overlapping time ranges detected: "
                    f"entry {current.index} ends at {current.end}, "
                    f"but entry {next_entry.index} starts at {next_entry.start}"
                )

    def __len__(self) -> int:
        """Return number of entries."""
        return len(self.entries)

    def __iter__(self):
        """Iterate over entries."""
        return iter(self.entries)

    def __getitem__(self, index: int) -> SubtitleEntry:
        """Get entry by index (0-based)."""
        return self.entries[index]
