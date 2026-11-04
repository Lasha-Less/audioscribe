import json
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from audioscribe.core.verify_audio import verify_media


class VideoVerificationTests(unittest.TestCase):
    def verify_streams(self, streams, duration="2.0"):
        payload = {
            "format": {"duration": duration},
            "streams": streams,
        }
        completed = CompletedProcess(
            args=["ffprobe"],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )
        with (
            patch.object(Path, "exists", return_value=True),
            patch(
                "audioscribe.core.verify_audio.subprocess.run",
                return_value=completed,
            ),
        ):
            return verify_media("example.mp4", media_type="video")

    def test_short_video_with_audio_passes(self):
        result = self.verify_streams([
            {"codec_type": "audio"},
            {"codec_type": "video", "width": 1280, "height": 720},
        ])
        self.assertEqual(result.status.value, "ok")

    def test_audio_only_file_fails(self):
        result = self.verify_streams([{"codec_type": "audio"}])
        self.assertIn("No video stream found", result.errors)

    def test_silent_video_fails(self):
        result = self.verify_streams([
            {"codec_type": "video", "width": 1280, "height": 720},
        ])
        self.assertIn("No audio stream found", result.errors)

    def test_cover_art_does_not_count_as_video(self):
        result = self.verify_streams([
            {"codec_type": "audio"},
            {
                "codec_type": "video",
                "width": 500,
                "height": 500,
                "disposition": {"attached_pic": 1},
            },
        ])
        self.assertIn("No video stream found", result.errors)


if __name__ == "__main__":
    unittest.main()