from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class Job:
    job_id: str
    status: str  # "created" | "running" | "done" | "failed"
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    total: int = 0
    succeeded: int = 0
    failed: int = 0


@dataclass(frozen=True)
class JobItem:
    item_id: str
    job_id: str
    url: str
    status: str  # "pending" | "running" | "done" | "failed"

    # fields we already know we'll want (optional for now)
    mp3_path: Optional[str] = None
    title: Optional[str] = None
    channel: Optional[str] = None
    duration_seconds: Optional[int] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None

    warnings: Optional[List[str]] = None
    extra: Optional[Dict[str, Any]] = None


class JobStore(Protocol):
    def create_job(self, urls: List[str]) -> str:
        ...

    def get_job(self, job_id: str) -> Job:
        ...

    def list_items(self, job_id: str) -> List[JobItem]:
        ...

    def update_job(self, job_id: str, patch: Dict[str, Any]) -> None:
        ...

    def update_item(self, job_id: str, url: str, patch: Dict[str, Any]) -> None:
        ...