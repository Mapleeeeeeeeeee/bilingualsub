"""E2E tests for BilingualSub complete workflow.

This module tests the complete bilingual subtitle generation workflow:
    YouTube URL → Download → Transcribe → Translate → Merge → Output (SRT/ASS/Burn-in)

Note:
    These tests require:
    - GROQ_API_KEY environment variable set
    - FFmpeg installed ONLY for burn-in tests (other tests use yt-dlp fallback)
    - Internet connection for YouTube download and API calls

    Tests are marked with @pytest.mark.e2e and skipped if requirements are not met.
    Subtitle-only tests are marked with @pytest.mark.subtitle_only
    Burn-in tests are marked with @pytest.mark.burn_in
"""

import os
import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from bilingualsub.core.downloader import DownloadError, download_youtube_video
from bilingualsub.core.merger import merge_subtitles
from bilingualsub.core.subtitle import Subtitle, SubtitleEntry
from bilingualsub.core.transcriber import transcribe_audio
from bilingualsub.core.translator import translate_subtitle
from bilingualsub.formats.ass import serialize_bilingual_ass
from bilingualsub.formats.srt import serialize_srt
from bilingualsub.utils.config import get_settings
from bilingualsub.utils.ffmpeg import burn_subtitles

# Test video: Short public video with clear English speech
# Using YouTube's first video "Me at the zoo" (19 seconds) for reliable E2E testing
TEST_YOUTUBE_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # 19 sec test video


def has_groq_api_key() -> bool:
    """Check if GROQ_API_KEY is available."""
    get_settings.cache_clear()
    settings = get_settings()
    return bool(settings.groq_api_key)


def has_ffmpeg() -> bool:
    """Check if FFmpeg is installed."""
    return shutil.which("ffmpeg") is not None


def has_ffprobe() -> bool:
    """Check if FFprobe is installed."""
    return shutil.which("ffprobe") is not None


requires_api_key = pytest.mark.skipif(
    not has_groq_api_key(),
    reason="GROQ_API_KEY environment variable not set",
)

requires_ffmpeg = pytest.mark.skipif(
    not has_ffmpeg() or not has_ffprobe(),
    reason="FFmpeg/FFprobe not installed",
)

requires_youtube_e2e = pytest.mark.skipif(
    os.getenv("ENABLE_YOUTUBE_E2E", "").lower() not in {"1", "true", "yes"},
    reason="ENABLE_YOUTUBE_E2E not set; skipping live YouTube E2E download tests",
)


@pytest.mark.e2e
@requires_youtube_e2e
class TestBilingualSubWorkflow:
    """E2E tests for the complete bilingual subtitle workflow."""

    @pytest.fixture
    def e2e_output_dir(self, tmp_path: Path) -> Path:
        """Create a temporary directory for E2E test outputs."""
        output_dir = tmp_path / "e2e_output"
        output_dir.mkdir()
        return output_dir

    @pytest.mark.subtitle_only
    def test_download_youtube_video(self, e2e_output_dir: Path) -> None:
        """Test downloading a YouTube video.

        Given a valid YouTube URL,
        When downloading the video,
        Then video file is created with correct metadata.

        Note: Uses yt-dlp info_dict fallback if FFprobe unavailable.
        """
        output_path = e2e_output_dir / "test_video.mp4"

        metadata = download_youtube_video(TEST_YOUTUBE_URL, output_path)

        assert output_path.exists()
        assert output_path.stat().st_size > 0
        assert metadata.duration > 0
        assert metadata.width > 0
        assert metadata.height > 0
        assert metadata.fps > 0
        assert metadata.title

    @requires_api_key
    @pytest.mark.subtitle_only
    def test_transcribe_audio(self, e2e_output_dir: Path) -> None:
        """Test transcribing audio using Groq Whisper API.

        Given a downloaded video file,
        When transcribing with Whisper,
        Then subtitle entries are created with timing.
        """
        # Download video first
        video_path = e2e_output_dir / "test_video.mp4"
        download_youtube_video(TEST_YOUTUBE_URL, video_path)

        # Transcribe
        subtitle = transcribe_audio(video_path, language="en")

        assert len(subtitle.entries) > 0
        assert all(entry.text.strip() for entry in subtitle.entries)
        assert all(entry.start < entry.end for entry in subtitle.entries)

    @requires_api_key
    @pytest.mark.subtitle_only
    def test_translate_subtitles(self, e2e_output_dir: Path) -> None:
        """Test translating subtitles using Agno + Groq.

        Given transcribed subtitle entries,
        When translating to Traditional Chinese,
        Then translated entries are created.
        """
        # Download and transcribe
        video_path = e2e_output_dir / "test_video.mp4"
        download_youtube_video(TEST_YOUTUBE_URL, video_path)
        original = transcribe_audio(video_path, language="en")

        # Translate
        translated = translate_subtitle(original, source_lang="en", target_lang="zh-TW")

        assert len(translated.entries) == len(original.entries)
        # Translated text should be different from original
        assert any(
            t.text != o.text
            for t, o in zip(translated.entries, original.entries, strict=True)
        )

    @requires_api_key
    @pytest.mark.subtitle_only
    def test_merge_bilingual_subtitles(self, e2e_output_dir: Path) -> None:
        """Test merging original and translated subtitles.

        Given original and translated subtitle entries,
        When merging into bilingual format,
        Then merged entries contain both languages.
        """
        # Full pipeline up to merge
        video_path = e2e_output_dir / "test_video.mp4"
        download_youtube_video(TEST_YOUTUBE_URL, video_path)
        original = transcribe_audio(video_path, language="en")
        translated = translate_subtitle(original, source_lang="en", target_lang="zh-TW")

        # Merge
        merged = merge_subtitles(original.entries, translated.entries)

        assert len(merged) == len(original.entries)
        # Each merged entry should contain newline (bilingual format)
        assert all("\n" in entry.text for entry in merged)

    @requires_api_key
    @pytest.mark.subtitle_only
    def test_full_workflow_youtube_to_bilingual_srt(self, e2e_output_dir: Path) -> None:
        """Test complete workflow: YouTube URL to bilingual SRT.

        Given a YouTube URL,
        When running complete workflow,
        Then bilingual SRT file is created.
        """
        video_path = e2e_output_dir / "video.mp4"
        srt_path = e2e_output_dir / "bilingual.srt"

        # Step 1: Download
        download_youtube_video(TEST_YOUTUBE_URL, video_path)
        assert video_path.exists()

        # Step 2: Transcribe
        original = transcribe_audio(video_path, language="en")
        assert len(original.entries) > 0

        # Step 3: Translate
        translated = translate_subtitle(original, source_lang="en", target_lang="zh-TW")
        assert len(translated.entries) == len(original.entries)

        # Step 4: Merge
        merged = merge_subtitles(original.entries, translated.entries)

        # Step 5: Output SRT
        bilingual_subtitle = Subtitle(entries=merged)
        srt_content = serialize_srt(bilingual_subtitle)
        srt_path.write_text(srt_content, encoding="utf-8")

        # Verify output
        assert srt_path.exists()
        content = srt_path.read_text(encoding="utf-8")
        assert "00:00:" in content  # Has timing
        assert "\n" in content  # Has content

    @requires_api_key
    @pytest.mark.subtitle_only
    def test_full_workflow_youtube_to_bilingual_ass(self, e2e_output_dir: Path) -> None:
        """Test complete workflow: YouTube URL to bilingual ASS.

        Given a YouTube URL,
        When running complete workflow,
        Then bilingual ASS file is created with yellow text styling.
        """
        video_path = e2e_output_dir / "video.mp4"
        ass_path = e2e_output_dir / "bilingual.ass"

        # Full pipeline
        metadata = download_youtube_video(TEST_YOUTUBE_URL, video_path)
        original = transcribe_audio(video_path, language="en")
        translated = translate_subtitle(original, source_lang="en", target_lang="zh-TW")

        # Output ASS with video dimensions
        ass_content = serialize_bilingual_ass(
            original,
            translated,
            video_width=metadata.width,
            video_height=metadata.height,
        )
        ass_path.write_text(ass_content, encoding="utf-8")

        # Verify output
        assert ass_path.exists()
        content = ass_path.read_text(encoding="utf-8")
        assert "[Script Info]" in content
        assert "[V4+ Styles]" in content
        assert "[Events]" in content
        assert "Dialogue:" in content
        # Verify yellow color styling
        assert "&H0000FFFF" in content  # Yellow in ASS BGR format

    @requires_api_key
    @requires_ffmpeg
    @pytest.mark.burn_in
    def test_full_workflow_with_video_burn_in(self, e2e_output_dir: Path) -> None:
        """Test complete workflow with subtitle burn-in to video.

        Given complete bilingual subtitles,
        When burning subtitles into video,
        Then output video is created with embedded subtitles.

        Note: This test REQUIRES FFmpeg for subtitle burn-in.
        """
        video_path = e2e_output_dir / "video.mp4"
        ass_path = e2e_output_dir / "bilingual.ass"
        output_video_path = e2e_output_dir / "output_with_subs.mp4"

        # Full pipeline
        metadata = download_youtube_video(TEST_YOUTUBE_URL, video_path)
        original = transcribe_audio(video_path, language="en")
        translated = translate_subtitle(original, source_lang="en", target_lang="zh-TW")

        # Create ASS file
        ass_content = serialize_bilingual_ass(
            original,
            translated,
            video_width=metadata.width,
            video_height=metadata.height,
        )
        ass_path.write_text(ass_content, encoding="utf-8")

        # Burn subtitles into video
        burn_subtitles(video_path, ass_path, output_video_path)

        # Verify output
        assert output_video_path.exists()
        assert output_video_path.stat().st_size > 0
        # Output should be similar size or larger than input (subtitles add data)
        assert output_video_path.stat().st_size >= video_path.stat().st_size * 0.5


@pytest.mark.e2e
class TestWorkflowEdgeCases:
    """E2E tests for edge cases and error handling."""

    def test_invalid_youtube_url_raises_error(self, tmp_path: Path) -> None:
        """Test that invalid YouTube URL raises appropriate error.

        Note: Uses yt-dlp info_dict fallback if FFprobe unavailable.
        """
        output_path = tmp_path / "video.mp4"

        with pytest.raises((ValueError, DownloadError)):
            download_youtube_video("https://invalid-url.com/video", output_path)

    def test_missing_api_key_raises_error(self, tmp_path: Path, monkeypatch) -> None:
        """Test that missing API key raises appropriate error."""
        get_settings.cache_clear()
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        get_settings.cache_clear()

        sample = Subtitle(
            entries=[
                SubtitleEntry(
                    index=1,
                    start=timedelta(0),
                    end=timedelta(seconds=2),
                    text="Test",
                )
            ]
        )

        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            translate_subtitle(sample)
