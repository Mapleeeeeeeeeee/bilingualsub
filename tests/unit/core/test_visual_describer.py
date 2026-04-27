"""Unit tests for video visual description using Gemini."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from bilingualsub.core.subtitle import Subtitle
from bilingualsub.core.visual_describer import VisualDescriptionError, describe_video


@pytest.mark.unit
class TestDescribeVideo:
    """Test cases for describe_video function."""

    @pytest.fixture
    def mock_genai(self):
        """Mock google.genai module-level reference used by visual_describer."""
        with patch("bilingualsub.core.visual_describer._genai") as mock:
            yield mock

    @pytest.fixture
    def mock_get_gemini_api_key(self):
        """Mock get_gemini_api_key to return a fixed key."""
        with patch(
            "bilingualsub.core.visual_describer.get_gemini_api_key",
            return_value="fake-gemini-key",
        ) as mock:
            yield mock

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _setup_client(self, mock_genai, response_text: str) -> MagicMock:
        """Wire up mock_genai so generate_content returns response_text."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_file = MagicMock()
        mock_file.state = "ACTIVE"
        mock_file.name = "files/test-file"
        mock_client.files.upload.return_value = mock_file

        mock_response = MagicMock()
        mock_response.text = response_text
        mock_client.models.generate_content.return_value = mock_response

        return mock_client

    # ------------------------------------------------------------------
    # Test cases
    # ------------------------------------------------------------------

    def test_valid_response_parses_to_subtitle(
        self, tmp_path, mock_genai, mock_get_gemini_api_key
    ):
        """Three well-formed lines produce a Subtitle with 3 entries."""
        response_text = (
            "00:00 - 00:05 | Opening title card\n"
            "00:05 - 00:15 | Product logo appears on screen\n"
            "00:15 - 00:30 | Presenter walks into frame\n"
        )
        self._setup_client(mock_genai, response_text)

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video content")

        result = describe_video(video_path, source_lang="en")

        assert isinstance(result, Subtitle)
        assert len(result.entries) == 3

        # Indices must start at 1
        assert result.entries[0].index == 1
        assert result.entries[1].index == 2
        assert result.entries[2].index == 3

        # start < end for every entry
        for entry in result.entries:
            assert entry.start < entry.end

        # Text is preserved verbatim (stripped)
        assert result.entries[0].text == "Opening title card"
        assert result.entries[1].text == "Product logo appears on screen"
        assert result.entries[2].text == "Presenter walks into frame"

        # Spot-check timestamps
        assert result.entries[0].start == timedelta(seconds=0)
        assert result.entries[0].end == timedelta(seconds=5)
        assert result.entries[2].start == timedelta(seconds=15)
        assert result.entries[2].end == timedelta(seconds=30)

    def test_no_segments_raises_error(
        self, tmp_path, mock_genai, mock_get_gemini_api_key
    ):
        """Empty response text must raise VisualDescriptionError."""
        self._setup_client(mock_genai, "")

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video content")

        with pytest.raises(
            VisualDescriptionError,
            match="No visual description segments returned",
        ):
            describe_video(video_path, source_lang="en")

    def test_no_segments_unparseable_content_raises_error(
        self, tmp_path, mock_genai, mock_get_gemini_api_key
    ):
        """Response with only unparseable lines must raise VisualDescriptionError."""
        self._setup_client(
            mock_genai, "This video shows nothing interesting.\nNo timestamps here!"
        )

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video content")

        with pytest.raises(
            VisualDescriptionError,
            match="No visual description segments returned",
        ):
            describe_video(video_path, source_lang="en")

    def test_api_error_raises_visual_description_error(
        self, tmp_path, mock_genai, mock_get_gemini_api_key
    ):
        """Exception from generate_content is wrapped into VisualDescriptionError."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_file = MagicMock()
        mock_file.state = "ACTIVE"
        mock_file.name = "files/test-file"
        mock_client.files.upload.return_value = mock_file
        mock_client.models.generate_content.side_effect = Exception("quota exceeded")

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video content")

        with pytest.raises(
            VisualDescriptionError,
            match="Gemini API call failed",
        ):
            describe_video(video_path, source_lang="en")

    def test_missing_api_key_raises_value_error(self, tmp_path, mock_genai):
        """ValueError from get_gemini_api_key propagates unchanged."""
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video content")

        with (
            patch(
                "bilingualsub.core.visual_describer.get_gemini_api_key",
                side_effect=ValueError(
                    "GEMINI_API_KEY environment variable is not set"
                ),
            ),
            pytest.raises(ValueError, match="GEMINI_API_KEY"),
        ):
            describe_video(video_path, source_lang="en")

    def test_file_not_exists_raises_value_error(self, tmp_path):
        """Non-existent video path raises ValueError before any API call."""
        video_path = tmp_path / "missing.mp4"

        with pytest.raises(ValueError, match="Video file not found"):
            describe_video(video_path, source_lang="en")

    def test_malformed_lines_are_skipped(
        self, tmp_path, mock_genai, mock_get_gemini_api_key
    ):
        """Lines that don't match the timestamp pattern are silently ignored."""
        response_text = (
            "00:00 - 00:10 | Valid first entry\n"
            "This line has no timestamp at all\n"
            "01:00 - 01:10 | Valid second entry\n"
            "just some random text\n"
            "NOT A TIMESTAMP | description without time\n"
        )
        self._setup_client(mock_genai, response_text)

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video content")

        result = describe_video(video_path, source_lang="en")

        assert isinstance(result, Subtitle)
        assert len(result.entries) == 2
        assert result.entries[0].text == "Valid first entry"
        assert result.entries[1].text == "Valid second entry"

    def test_mixed_timestamp_formats_parsed_correctly(
        self, tmp_path, mock_genai, mock_get_gemini_api_key
    ):
        """MM:SS and HH:MM:SS formats are both parsed correctly."""
        response_text = (
            "01:00 - 01:30 | Scene with minutes\n"
            "01:00:00 - 01:00:10 | Scene with hours\n"
        )
        self._setup_client(mock_genai, response_text)

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video content")

        result = describe_video(video_path, source_lang="en")

        assert len(result.entries) == 2
        # MM:SS: 01:00 = 60 seconds, 01:30 = 90 seconds
        assert result.entries[0].start == timedelta(minutes=1, seconds=0)
        assert result.entries[0].end == timedelta(minutes=1, seconds=30)
        # HH:MM:SS: 01:00:00 = 1 hour, 01:00:10 = 1 hour 10 seconds
        assert result.entries[1].start == timedelta(hours=1)
        assert result.entries[1].end == timedelta(hours=1, seconds=10)

    def test_reversed_and_equal_timestamps_are_skipped(
        self, tmp_path, mock_genai, mock_get_gemini_api_key
    ):
        """Entries where start >= end are silently skipped."""
        response_text = (
            "00:10 - 00:05 | Reversed timestamps\n"
            "00:05 - 00:05 | Equal timestamps\n"
            "00:00 - 00:10 | Valid entry\n"
        )
        self._setup_client(mock_genai, response_text)

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video content")

        result = describe_video(video_path, source_lang="en")

        assert len(result.entries) == 1
        assert result.entries[0].text == "Valid entry"

    def test_file_state_failed_raises_error(
        self, tmp_path, mock_genai, mock_get_gemini_api_key
    ):
        """Gemini file in FAILED state raises VisualDescriptionError."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_file = MagicMock()
        mock_file.state = "FAILED"
        mock_file.name = "files/test-file"
        mock_client.files.upload.return_value = mock_file

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video content")

        with pytest.raises(
            VisualDescriptionError,
            match="File processing failed on Gemini servers",
        ):
            describe_video(video_path, source_lang="en")

    def test_file_processing_timeout_raises_error(
        self, tmp_path, mock_genai, mock_get_gemini_api_key
    ):
        """File stuck in PROCESSING state past timeout raises error."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_file = MagicMock()
        mock_file.state = "PROCESSING"
        mock_file.name = "files/test-file"
        mock_client.files.upload.return_value = mock_file
        # files.get always returns PROCESSING
        mock_client.files.get.return_value = mock_file

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video content")

        with (
            patch("bilingualsub.core.visual_describer.time") as mock_time,
            pytest.raises(
                VisualDescriptionError,
                match="File processing timed out",
            ),
        ):
            # First call to monotonic() sets deadline, second exceeds it
            mock_time.monotonic.side_effect = [0.0, 601.0]
            mock_time.sleep = MagicMock()
            describe_video(video_path, source_lang="en")
