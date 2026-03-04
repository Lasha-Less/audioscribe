from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from audioscribe.storage.job_store import Job, JobItem, JobStore


class InMemoryJobStore(JobStore):
    """
    Minimal in-memory store that mirrors current behavior.
    Later we can swap this with a SqliteJobStore without changing core/UI.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._items_by_job: Dict[str, List[JobItem]] = {}

    def create_job(self, urls: List[str]) -> str:
        job_id = str(uuid4())
        now = datetime.utcnow()

        job = Job(
            job_id=job_id,
            status="created",
            created_at=now,
            total=len(urls),
            succeeded=0,
            failed=0,
        )
        self._jobs[job_id] = job

        items: List[JobItem] = []
        for url in urls:
            items.append(
                JobItem(
                    item_id=str(uuid4()),
                    job_id=job_id,
                    url=url,
                    status="pending",
                    warnings=[],
                    extra={},
                )
            )
        self._items_by_job[job_id] = items
        return job_id

    def get_job(self, job_id: str) -> Job:
        if job_id not in self._jobs:
            raise KeyError(f"job not found: {job_id}")
        return self._jobs[job_id]

    def list_items(self, job_id: str) -> List[JobItem]:
        if job_id not in self._items_by_job:
            raise KeyError(f"job not found: {job_id}")
        return list(self._items_by_job[job_id])

    def update_job(self, job_id: str, patch: Dict[str, Any]) -> None:
        job = self.get_job(job_id)
        updated = job
        for k, v in patch.items():
            if not hasattr(updated, k):
                raise KeyError(f"unknown job field: {k}")
            updated = replace(updated, **{k: v})
        self._jobs[job_id] = updated

    def update_item(self, job_id: str, url: str, patch: Dict[str, Any]) -> None:
        items = self.list_items(job_id)
        found = False

        new_items: List[JobItem] = []
        for it in items:
            if it.url == url and not found:
                updated = it
                for k, v in patch.items():
                    if not hasattr(updated, k):
                        raise KeyError(f"unknown job item field: {k}")
                    updated = replace(updated, **{k: v})
                new_items.append(updated)
                found = True
            else:
                new_items.append(it)

        if not found:
            raise KeyError(f"item not found for job_id={job_id}, url={url}")

        self._items_by_job[job_id] = new_items