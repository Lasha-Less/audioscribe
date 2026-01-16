"""
AudioScribe - Fake Core (prototype)

Goal:
- Accept URLs
- Return a fake job_id
- Print progress messages
- No downloading, no audio, no YouTube logic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List
import time
import uuid


@dataclass
class Job:
    job_id: str
    urls: List[str]
    created_at: str
    status: str = "created"  # created | running | done
    progress: Dict[str, str] = field(default_factory=dict)  # url -> status


# In-memory "job store" (temporary for this fake version)
_JOBS: Dict[str, Job] = {}


def create_job(urls: List[str]) -> str:
    """
    Accepts a list of URLs and returns a fake job_id.
    Stores the job in memory so we can "process" it later.
    """
    if not isinstance(urls, list) or not urls:
        raise ValueError("create_job(urls): urls must be a non-empty list of strings.")

    cleaned: List[str] = []
    for u in urls:
        if not isinstance(u, str) or not u.strip():
            raise ValueError("All URLs must be non-empty strings.")
        cleaned.append(u.strip())

    job_id = f"job_{uuid.uuid4().hex[:10]}"
    job = Job(
        job_id=job_id,
        urls=cleaned,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        progress={u: "queued" for u in cleaned},
    )
    _JOBS[job_id] = job

    print(f"[core] Created job: {job_id}")
    print(f"[core] URLs received: {len(cleaned)}")
    return job_id


def process_job(job_id: str, *, step_delay_seconds: float = 0.3) -> None:
    """
    Prints progress messages as if we are processing each URL.
    """
    job = _JOBS.get(job_id)
    if not job:
        raise KeyError(f"No such job_id: {job_id}")

    print(f"[core] Starting job: {job.job_id}")
    job.status = "running"

    for i, url in enumerate(job.urls, start=1):
        print(f"[core] ({i}/{len(job.urls)}) Working on: {url}")
        job.progress[url] = "processing"

        time.sleep(step_delay_seconds)
        print("[core]   - validate URL: ok")
        time.sleep(step_delay_seconds)
        print("[core]   - extract metadata: ok (fake)")
        time.sleep(step_delay_seconds)
        print("[core]   - finalize: ok (fake)")

        job.progress[url] = "done"
        print(f"[core] Completed: {url}")

    job.status = "done"
    print(f"[core] Job done: {job.job_id}")


def get_job_summary(job_id: str) -> dict:
    """
    Returns a simple summary dict (useful later for CLI/API/UI).
    """
    job = _JOBS.get(job_id)
    if not job:
        raise KeyError(f"No such job_id: {job_id}")

    done_count = sum(1 for s in job.progress.values() if s == "done")
    return {
        "job_id": job.job_id,
        "created_at": job.created_at,
        "status": job.status,
        "total_urls": len(job.urls),
        "done_urls": done_count,
        "progress": dict(job.progress),
    }


if __name__ == "__main__":
    demo_urls = [
        "https://example.com/video1",
        "https://example.com/video2",
        "https://example.com/video3",
    ]
    jid = create_job(demo_urls)
    process_job(jid)
    print(get_job_summary(jid))


# ---- C2S3 placeholder API (CLI wiring only) ----

def get_job_status(job_id: str) -> dict:
    return {"ok": True, "message": "not implemented", "job_id": job_id}


def list_tracks(limit: int = 25) -> dict:
    return {"ok": True, "message": "not implemented", "limit": limit}


def search_tracks(query: str) -> dict:
    return {"ok": True, "message": "not implemented", "query": query}


def update_track(track_id: str, fields: dict) -> dict:
    return {
        "ok": True,
        "message": "not implemented",
        "track_id": track_id,
        "fields": fields,
    }


def delete_track(track_id: str, soft: bool = True) -> dict:
    return {"ok": True, "message": "not implemented", "track_id": track_id, "soft": soft}


def purge_tracks(older_than_days: int | None = None, confirm: bool = False) -> dict:
    return {
        "ok": True,
        "message": "not implemented",
        "older_than_days": older_than_days,
        "confirm": confirm,
    }


def upload_track(track_id: str) -> dict:
    return {"ok": True, "message": "not implemented", "track_id": track_id}


def upload_job(job_id: str) -> dict:
    return {"ok": True, "message": "not implemented", "job_id": job_id}