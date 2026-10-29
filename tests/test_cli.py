import json
import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from audioscribe.cli import app


class CliTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_success_returns_zero_and_passes_options_to_ingest(self):
        url = "https://www.youtube.com/watch?v=example"
        response = {
            "ok": True,
            "job_id": "test-job",
            "items": [],
        }

        with patch(
            "audioscribe.cli.core_ingest",
            return_value=response,
        ) as ingest:
            result = self.runner.invoke(
                app,
                [
                    "ingest",
                    url,
                    "--allow-playlist",
                    "--output-dir",
                    "chosen folder",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        ingest.assert_called_once_with(
            inputs=[url],
            output_dir="chosen folder",
            allow_playlist=True,
        )
        payload, _ = json.JSONDecoder().raw_decode(result.stdout)
        self.assertEqual(payload, response)
        self.assertIn("job_id=test-job", result.stdout)

    def test_failure_and_confirmation_return_one(self):
        responses = [
            {
                "ok": False,
                "job_id": "failed-job",
                "items": [],
                "errors": ["simulated failure"],
            },
            {
                "ok": False,
                "job_id": "waiting-job",
                "items": [],
                "requires_confirmation": True,
            },
        ]

        for response in responses:
            with self.subTest(job_id=response["job_id"]):
                with patch(
                    "audioscribe.cli.core_ingest",
                    return_value=response,
                ):
                    result = self.runner.invoke(
                        app,
                        ["ingest", "https://example.com/video"],
                    )

                self.assertEqual(result.exit_code, 1, result.output)
                payload, _ = json.JSONDecoder().raw_decode(result.stdout)
                self.assertEqual(payload, response)

    def test_placeholder_commands_are_rejected(self):
        commands = [
            "status",
            "list",
            "search",
            "delete",
            "edit",
            "purge",
            "upload",
        ]

        for command in commands:
            with self.subTest(command=command):
                result = self.runner.invoke(app, [command])

                self.assertEqual(result.exit_code, 2, result.output)
                self.assertIn("No such command", result.output)