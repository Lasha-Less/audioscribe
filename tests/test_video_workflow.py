import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from audioscribe.core.ingest import ingest
from audioscribe.storage.memory_job_store import InMemoryJobStore


class VideoWorkflowTests(unittest.TestCase):
    def test_video_is_downloaded_verified_and_stored(self):
        store = InMemoryJobStore()

        with TemporaryDirectory() as folder:
            path = Path(folder) / "example.mp4"

            def download(cmd):
                path.write_bytes(b"simulated video")
                return CompletedProcess(
                    cmd, 0, stdout=str(path), stderr=""
                )

            with (
                patch(
                    "audioscribe.core.jobs.get_settings",
                    return_value=SimpleNamespace(cookies_from_browser=None),
                ),
                patch(
                    "audioscribe.core.jobs.extract_source_info",
                    return_value={"title": "Example"},
                ),
                patch(
                    "audioscribe.core.jobs._run_download",
                    side_effect=download,
                ) as downloader,
                patch(
                    "audioscribe.core.verify_audio.verify_media",
                    return_value={
                        "status": "ok",
                        "metrics": {},
                        "warnings": [],
                        "errors": [],
                    },
                ) as verifier,
            ):
                result = ingest(
                    ["https://www.youtube.com/watch?v=example"],
                    folder,
                    store=store,
                    media_type="video",
                )

            self.assertTrue(result["ok"])
            item = result["items"][0]
            self.assertEqual(item["file_path"], str(path))
            self.assertEqual(item["media_type"], "video")
            self.assertIsNone(item["mp3_path"])

            stored = store.list_items(result["job_id"])[0]
            self.assertEqual(stored.file_path, str(path))
            self.assertEqual(stored.status, "done")
            self.assertEqual(stored.media_type, "video")
            self.assertIsNone(stored.mp3_path)
            self.assertEqual(store.get_job(result["job_id"]).status, "done")

            command = downloader.call_args.args[0]
            self.assertIn("--merge-output-format", command)
            self.assertNotIn("--audio-format", command)
            verifier.assert_called_once_with(str(path), media_type="video")

    def test_video_playlist_requires_confirmation(self):
        store = InMemoryJobStore()

        with (
            patch(
                "audioscribe.core.jobs.get_settings",
                return_value=SimpleNamespace(cookies_from_browser=None),
            ),
            patch(
                "audioscribe.core.jobs._expand_playlist_to_video_urls",
                return_value=(
                    [
                        "https://www.youtube.com/watch?v=first",
                        "https://www.youtube.com/watch?v=second",
                    ],
                    None,
                ),
            ),
            patch("audioscribe.core.jobs._run_download") as downloader,
        ):
            result = ingest(
                ["https://www.youtube.com/playlist?list=example"],
                "outputs",
                store=store,
                media_type="video",
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["requires_confirmation"])
        self.assertIn(
            "python -m audioscribe video",
            result["next_command"],
        )
        self.assertEqual(
            store.get_job(result["job_id"]).status,
            "awaiting_confirmation",
        )
        downloader.assert_not_called()


if __name__ == "__main__":
    unittest.main()