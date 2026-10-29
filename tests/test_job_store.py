import unittest

from audioscribe.storage.memory_job_store import InMemoryJobStore


class JobStoreTests(unittest.TestCase):
    def test_duplicate_urls_can_be_updated_independently(self):
        store = InMemoryJobStore()
        url = "https://www.youtube.com/watch?v=example"
        job_id = store.create_job([url, url])

        first, second = store.list_items(job_id)
        self.assertNotEqual(first.item_id, second.item_id)

        store.update_item(
            job_id,
            second.item_id,
            {
                "status": "failed",
                "error_message": "simulated failure",
            },
        )

        first, second = store.list_items(job_id)
        self.assertEqual(first.status, "pending")
        self.assertIsNone(first.error_message)
        self.assertEqual(second.status, "failed")
        self.assertEqual(second.error_message, "simulated failure")

    def test_playlist_replacement_updates_items_and_totals(self):
        store = InMemoryJobStore()
        job_id = store.create_job(
            ["https://www.youtube.com/playlist?list=example"]
        )
        store.update_job(job_id, {"succeeded": 1, "failed": 1})

        urls = [
            "https://www.youtube.com/watch?v=one",
            "https://www.youtube.com/watch?v=two",
        ]
        store.replace_items(job_id, urls)

        items = store.list_items(job_id)
        job = store.get_job(job_id)

        self.assertEqual([item.url for item in items], urls)
        self.assertEqual(len({item.item_id for item in items}), 2)
        self.assertTrue(all(item.job_id == job_id for item in items))
        self.assertTrue(all(item.status == "pending" for item in items))
        self.assertEqual(
            (job.total, job.succeeded, job.failed),
            (2, 0, 0),
        )