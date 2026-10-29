import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from audioscribe.core import jobs
from audioscribe.core.ingest import ingest
from audioscribe.storage.memory_job_store import InMemoryJobStore


class IngestWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryJobStore()
        self.events = []

        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.output_dir = Path(temp.name) / "chosen folder"

        settings_patch = patch.object(
            jobs,
            "get_settings",
            return_value=SimpleNamespace(cookies_from_browser=None),
        )
        settings_patch.start()
        self.addCleanup(settings_patch.stop)

    @staticmethod
    def simulated_result(ok):
        return {
            "ok": ok,
            "url": "https://www.youtube.com/watch?v=example",
            "mp3_exists": ok,
            "mp3_path": None,
            "message": "simulated success" if ok else "simulated failure",
            "verification": {
                "status": "ok" if ok else "failed",
                "warnings": [],
                "errors": [] if ok else ["simulated failure"],
            },
        }

    def test_success_uses_one_job_and_the_chosen_folder(self):
        with (
            patch.object(
                self.store,
                "create_job",
                wraps=self.store.create_job,
            ) as create,
            patch.object(
                jobs,
                "_process_one_url",
                return_value=self.simulated_result(True),
            ) as process,
        ):
            result = ingest(
                ["https://www.youtube.com/watch?v=example"],
                output_dir=str(self.output_dir),
                store=self.store,
                on_event=self.events.append,
            )

        create.assert_called_once()
        self.assertTrue(result["ok"])
        self.assertTrue(self.output_dir.is_dir())
        self.assertEqual(
            process.call_args.kwargs["out_dir"],
            self.output_dir.resolve(),
        )
        self.assertEqual(
            process.call_args.kwargs["job_id"],
            result["job_id"],
        )

        job = self.store.get_job(result["job_id"])
        self.assertEqual(job.status, "done")
        self.assertEqual((job.total, job.succeeded, job.failed), (1, 1, 0))
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.finished_at)
        self.assertIsNotNone(job.created_at.utcoffset())
        self.assertIsNotNone(job.started_at.utcoffset())
        self.assertIsNotNone(job.finished_at.utcoffset())
        self.assertLessEqual(job.created_at, job.started_at)
        self.assertLessEqual(job.started_at, job.finished_at)

        self.assertTrue(self.events)
        self.assertTrue(
            all(event["job_id"] == job.job_id for event in self.events)
        )
        self.assertEqual(
            self.store.list_items(job.job_id)[0].status,
            "done",
        )

    def test_partial_failure_is_not_reported_as_success(self):
        with patch.object(
            jobs,
            "_process_one_url",
            side_effect=[
                self.simulated_result(True),
                self.simulated_result(False),
            ],
        ):
            result = ingest(
                [
                    "https://www.youtube.com/watch?v=example",
                    "https://www.youtube.com/watch?v=example",
                ],
                output_dir=str(self.output_dir),
                store=self.store,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            [item["status"] for item in result["items"]],
            ["done", "failed"],
        )

        job = self.store.get_job(result["job_id"])
        self.assertEqual(job.status, "failed")
        self.assertEqual((job.total, job.succeeded, job.failed), (2, 1, 1))
        self.assertEqual(
            [item.status for item in self.store.list_items(job.job_id)],
            ["done", "failed"],
        )