"""Integration tests for the full subtitle pipeline: download -> transcribe -> translate -> merge -> serialize."""

import json
import subprocess as _subprocess_mod
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from bilingualsub.core.downloader import VideoMetadata, download_youtube_video
from bilingualsub.core.merger import merge_subtitles
from bilingualsub.core.subtitle import Subtitle
from bilingualsub.core.transcriber import transcribe_audio
from bilingualsub.core.translator import translate_subtitle
from bilingualsub.formats.ass import serialize_bilingual_ass
from bilingualsub.formats.srt import serialize_srt

YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

CHINESE_TRANSLATIONS = [
    "你好，這是一個測試。",
    "這是第二個字幕。",
    "這是第三個。",
]


def _make_ffprobe_json(
    *, width: int = 1920, height: int = 1080, fps: str = "30/1", duration: str = "60.0"
) -> str:
    """Build a ffprobe JSON string with the given video parameters."""
    return json.dumps(
        {
            "format": {"duration": duration, "tags": {"title": "Test Video"}},
            "streams": [
                {
                    "codec_type": "video",
                    "width": width,
                    "height": height,
                    "r_frame_rate": fps,
                }
            ],
        }
    )


def _make_info_dict(*, width: int = 1920, height: int = 1080) -> dict:
    """Build a yt-dlp info_dict with the given dimensions."""
    return {
        "title": "Test Video",
        "duration": 60.0,
        "width": width,
        "height": height,
        "fps": 30.0,
    }


def _patch_downloader(output_path: Path, *, width: int = 1920, height: int = 1080):
    """Return a combined context manager that patches all downloader dependencies.

    Patches: yt_dlp.YoutubeDL, subprocess.run (ffprobe), shutil.which.
    The fake extract_info creates *output_path* on disk so the rename logic succeeds.
    """
    info_dict = _make_info_dict(width=width, height=height)

    def _fake_extract_info(_url: str, download: bool = True):
        output_path.write_bytes(b"fake video content")
        return info_dict

    mock_ydl = MagicMock()
    mock_ydl.__enter__ = Mock(return_value=mock_ydl)
    mock_ydl.__exit__ = Mock(return_value=False)
    mock_ydl.extract_info.side_effect = _fake_extract_info

    mock_ffprobe_result = Mock()
    mock_ffprobe_result.stdout = _make_ffprobe_json(width=width, height=height)

    class _FakeSubprocess:
        CalledProcessError = _subprocess_mod.CalledProcessError

        @staticmethod
        def run(*args, **kwargs):
            return mock_ffprobe_result

    return (
        patch("bilingualsub.core.downloader.yt_dlp.YoutubeDL", return_value=mock_ydl),
        patch("bilingualsub.core.downloader.subprocess", _FakeSubprocess),
        patch(
            "bilingualsub.core.downloader.shutil.which", return_value="/usr/bin/ffmpeg"
        ),
    )


def _patch_transcriber(whisper_response):
    """Return a context manager that patches the Groq client in the transcriber."""
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = whisper_response
    return patch("bilingualsub.core.transcriber.Groq", return_value=mock_client)


def _patch_translator(translations: list[str]):
    """Return a context manager that patches the Agent in the translator."""
    mock_translator = Mock()
    batch_content = "\n".join(f"{i}. {text}" for i, text in enumerate(translations, 1))
    resp = Mock()
    resp.content = batch_content
    mock_translator.run.return_value = resp
    return patch("bilingualsub.core.translator.Agent", return_value=mock_translator)


@pytest.mark.integration
class TestFullSubtitlePipeline:
    """Full pipeline integration tests: download -> transcribe -> translate -> merge -> serialize."""

    def test_full_pipeline_to_bilingual_srt(
        self,
        tmp_path: Path,
        set_fake_api_key: None,
        sample_whisper_api_response,
    ) -> None:
        """Full pipeline produces a bilingual SRT file with correct format."""
        video_path = tmp_path / "video.mp4"
        srt_output = tmp_path / "output.srt"

        dl_patches = _patch_downloader(video_path)
        with dl_patches[0], dl_patches[1], dl_patches[2]:
            metadata = download_youtube_video(YOUTUBE_URL, video_path)

        assert isinstance(metadata, VideoMetadata)

        # Create a fake audio file for the transcriber
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        with _patch_transcriber(sample_whisper_api_response):
            original = transcribe_audio(audio_path)

        assert isinstance(original, Subtitle)
        assert len(original.entries) == 3

        with _patch_translator(CHINESE_TRANSLATIONS):
            translated = translate_subtitle(original)

        assert len(translated.entries) == 3

        # Merge and serialize
        merged_entries = merge_subtitles(original.entries, translated.entries)
        merged_subtitle = Subtitle(entries=merged_entries)
        srt_content = serialize_srt(merged_subtitle)
        srt_output.write_text(srt_content, encoding="utf-8")

        # Verify SRT file
        assert srt_output.exists()
        written = srt_output.read_text(encoding="utf-8")

        # Each entry should have bilingual format: "translated\noriginal"
        for orig_entry, zh_text in zip(
            original.entries, CHINESE_TRANSLATIONS, strict=True
        ):
            assert zh_text in written
            assert orig_entry.text in written

        # Verify timing is preserved in the output
        assert "00:00:01,000 --> 00:00:04,000" in written
        assert "00:00:05,000 --> 00:00:08,000" in written
        assert "00:00:09,000 --> 00:00:12,000" in written

    def test_full_pipeline_to_bilingual_ass(
        self,
        tmp_path: Path,
        set_fake_api_key: None,
        sample_whisper_api_response,
    ) -> None:
        """Full pipeline produces a bilingual ASS file using VideoMetadata dimensions."""
        video_path = tmp_path / "video.mp4"
        ass_output = tmp_path / "output.ass"

        dl_patches = _patch_downloader(video_path)
        with dl_patches[0], dl_patches[1], dl_patches[2]:
            metadata = download_youtube_video(YOUTUBE_URL, video_path)

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio content")

        with _patch_transcriber(sample_whisper_api_response):
            original = transcribe_audio(audio_path)

        with _patch_translator(CHINESE_TRANSLATIONS):
            translated = translate_subtitle(original)

        # Serialize as ASS using metadata dimensions
        ass_content = serialize_bilingual_ass(
            original,
            translated,
            video_width=metadata.width,
            video_height=metadata.height,
        )
        ass_output.write_text(ass_content, encoding="utf-8")

        assert ass_output.exists()
        written = ass_output.read_text(encoding="utf-8")

        # Verify ASS header uses VideoMetadata dimensions
        assert "PlayResX: 1920" in written
        assert "PlayResY: 1080" in written

        # Verify both styles exist
        assert "Style: Translated" in written
        assert "Style: Original" in written

        # Verify dialogue lines exist for each entry
        for orig_entry in original.entries:
            assert orig_entry.text in written
        for zh_text in CHINESE_TRANSLATIONS:
            assert zh_text in written

        # Verify dialogue line format
        assert "Dialogue: 0," in written

    def test_pipeline_metadata_flows_from_downloader_to_ass_serializer(
        self,
        tmp_path: Path,
        set_fake_api_key: None,
        sample_whisper_api_response,
    ) -> None:
        """VideoMetadata width/height flows correctly to ASS PlayResX/PlayResY across resolutions."""
        resolutions = [
            (1920, 1080, "1080p"),
            (1280, 720, "720p"),
            (3840, 2160, "4K"),
            (854, 480, "480p"),
        ]

        for width, height, label in resolutions:
            video_path = tmp_path / f"video_{label}.mp4"

            dl_patches = _patch_downloader(video_path, width=width, height=height)
            with dl_patches[0], dl_patches[1], dl_patches[2]:
                metadata = download_youtube_video(YOUTUBE_URL, video_path)

            assert metadata.width == width, f"{label}: width mismatch"
            assert metadata.height == height, f"{label}: height mismatch"

            # Use pre-built subtitle fixtures instead of re-mocking transcriber
            audio_path = tmp_path / f"audio_{label}.mp3"
            audio_path.write_bytes(b"fake audio content")

            with _patch_transcriber(sample_whisper_api_response):
                original = transcribe_audio(audio_path)

            with _patch_translator(list(CHINESE_TRANSLATIONS)):
                translated = translate_subtitle(original)

            ass_content = serialize_bilingual_ass(
                original,
                translated,
                video_width=metadata.width,
                video_height=metadata.height,
            )

            assert "PlayResX: 1920" in ass_content, (
                f"{label}: PlayResX should always be 1920"
            )
            assert "PlayResY: 1080" in ass_content, (
                f"{label}: PlayResY should always be 1080"
            )
