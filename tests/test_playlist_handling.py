import unittest
from types import SimpleNamespace
from unittest.mock import patch

from audioscribe.core import jobs
from audioscribe.storage.memory_job_store import InMemoryJobStore


class PlaylistHandlingTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryJobStore()
        self.playlist = "https://www.youtube.com/playlist?list=example"
        self.videos = [
            "https://www.youtube.com/watch?v=one",
            "https://www.youtube.com/watch?v=two",
        ]

        settings_patch = patch.object(
            jobs,
            "get_settings",
            return_value=SimpleNamespace(cookies_from_browser=None),
        )
        settings_patch.start()
        self.addCleanup(settings_patch.stop)

        # Any unexpected external command makes the test fail.
        subprocess_patch = patch.object(
            jobs.subprocess,
            "run",
            side_effect=AssertionError("Unexpected external command"),
        )
        subprocess_patch.start()
        self.addCleanup(subprocess_patch.stop)

    def test_playlist_requires_confirmation_before_downloading(self):
        job_id = self.store.create_job([self.playlist])

        with (
            patch.object(
                jobs,
                "_expand_playlist_to_video_urls",
                return_value=(self.videos, None),
            ),
            patch.object(jobs, "_process_one_url") as download,
        ):
            result = jobs.process_job(job_id, store=self.store)

        self.assertFalse(result["ok"])
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["job_id"], job_id)
        self.assertEqual(result["expanded_urls_count"], 2)
        self.assertEqual(result["items"], [])
        download.assert_not_called()

    def test_unreadable_playlist_blocks_the_entire_request(self):
        for allow_playlist in (False, True):
            for debug in (None, {"message": "simulated lookup failure"}):
                with self.subTest(
                    allow_playlist=allow_playlist,
                    debug=debug,
                ):
                    # A valid video comes before the unreadable playlist.
                    job_id = self.store.create_job(
                        [self.videos[0], self.playlist]
                    )

                    with (
                        patch.object(
                            jobs,
                            "_expand_playlist_to_video_urls",
                            return_value=([], debug),
                        ),
                        patch.object(jobs, "_process_one_url") as download,
                    ):
                        result = jobs.process_job(
                            job_id,
                            store=self.store,
                            allow_playlist=allow_playlist,
                        )

                    self.assertFalse(result["ok"])
                    self.assertFalse(result["requires_confirmation"])
                    self.assertEqual(result["items"], [])
                    self.assertTrue(result["errors"])
                    self.assertIn("no downloads started", result["message"])
                    download.assert_not_called()