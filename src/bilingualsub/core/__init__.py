"""Core business logic modules."""

from bilingualsub.core.downloader import (
    DownloadError,
    VideoMetadata,
    download_video,
)
from bilingualsub.core.glossary import GlossaryEntry, GlossaryError, GlossaryManager
from bilingualsub.core.merger import merge_subtitles
from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.core.subtitle_fetcher import SubtitleFetchError, fetch_manual_subtitle
from bilingualsub.core.transcriber import TranscriptionError, transcribe_audio
from bilingualsub.core.translator import (
    RetranslateEntry,
    TranslationError,
    retranslate_entries,
    translate_subtitle,
)

__all__ = [
    "DownloadError",
    "GlossaryEntry",
    "GlossaryError",
    "GlossaryManager",
    "RetranslateEntry",
    "Subtitle",
    "SubtitleEntry",
    "SubtitleFetchError",
    "TranscriptionError",
    "TranslationError",
    "VideoMetadata",
    "download_video",
    "fetch_manual_subtitle",
    "merge_subtitles",
    "retranslate_entries",
    "transcribe_audio",
    "translate_subtitle",
]
