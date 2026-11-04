import unittest

from audioscribe.core.jobs import _store_item_result
from audioscribe.storage.memory_job_store import InMemoryJobStore


class MediaStorageTests(unittest.TestCase):
    def store_result(self, result):
        store = InMemoryJobStore()
        job_id = store.create_job(["https://example.com/video"])
        item = store.list_items(job_id)[0]

        _store_item_result(store, job_id, item.item_id, result)

        return store.list_items(job_id)[0]

    def test_existing_audio_result_populates_both_paths(self):
        item = self.store_result({
            "ok": True,
            "mp3_path": "outputs/audio.mp3",
        })

        self.assertEqual(item.media_type, "audio")
        self.assertEqual(item.file_path, "outputs/audio.mp3")
        self.assertEqual(item.mp3_path, "outputs/audio.mp3")
        self.assertEqual(item.status, "done")

    def test_video_path_is_stored_without_mp3_path(self):
        item = self.store_result({
            "ok": True,
            "media_type": "video",
            "file_path": "outputs/video.mp4",
        })

        self.assertEqual(item.media_type, "video")
        self.assertEqual(item.file_path, "outputs/video.mp4")
        self.assertIsNone(item.mp3_path)
        self.assertEqual(item.status, "done")


if __name__ == "__main__":
    unittest.main()