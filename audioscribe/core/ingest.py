from __future__ import annotations
from audioscribe.core import jobs as core_jobs

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from audioscribe.storage.memory_job_store import InMemoryJobStore
from audioscribe.storage.job_store import JobStore
import re


EventCallback = Callable[[Dict[str, Any]], None]


def _emit(on_event: Optional[EventCallback], event: Dict[str, Any]) -> None:
    if on_event is not None:
        on_event(event)


def _split_inputs(inputs: List[str]) -> List[str]:
    """
    UI will likely pass raw lines. Normalize by trimming and dropping empties.
    """
    out: List[str] = []
    for s in inputs:
        s2 = (s or "").strip()
        if s2:
            out.append(s2)
    return out


def _sanitize_filename(name: str) -> str:
    # Windows-illegal: \ / : * ? " < > |
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

def _ensure_mp3_ext(name: str) -> str:
    return name if name.lower().endswith(".mp3") else name + ".mp3"


def ingest(
    inputs: List[str],
    output_dir: str,
    allow_playlist: bool = False,
    save_as: Optional[str] = None,
    on_event: Optional[EventCallback] = None,
    store: Optional[JobStore] = None,
) -> Dict[str, Any]:
    """
    Core/UI contract entry point.

    - Accepts user inputs (urls or playlist url)
    - Creates a job in a store (in-memory for now)
    - Runs download+verify sequentially (existing jobs pipeline)
    - Emits progress events (coarse-grained for now)
    - Returns stable JSON keys
    """
    urls = _split_inputs(inputs)
    _ = str(Path(output_dir).expanduser().resolve())  # reserved for later (UI uses it)

    if store is None:
        store = InMemoryJobStore()

    # Create job + items (our seam; later can be SQLite)
    job_id = store.create_job(urls)

    # Base response skeleton (stable keys)
    if not urls:
        return {
            "ok": False,
            "message": "no urls provided",
            "job_id": job_id,
            "items": [],
        }

    # save_as rule: only allowed when exactly 1 user-provided url is given
    warnings_top: List[str] = []
    if save_as and len(urls) != 1:
        warnings_top.append("save_as ignored: only allowed for single-url ingest")
        save_as = None

    store.update_job(job_id, {"status": "running"})

    _emit(
        on_event,
        {
            "type": "progress",
            "job_id": job_id,
            "url": None,
            "stage": "starting",
            "percent": 0,
            "message": "Starting ingest...",
        },
    )

    # Use existing job pipeline (source of truth for download+verify)
    created = core_jobs.create_job(urls)  # returns dict
    real_job_id = created.get("job_id") or job_id

    job_summary = core_jobs.process_job(real_job_id, allow_playlist=allow_playlist)
    src_items = job_summary.get("items") or []

    # Authoritative overall success: all items ok OR warning (and at least one item exists)
    def _item_is_ok_or_warning(it: dict) -> bool:
        verification = it.get("verification") or {}
        v_status = verification.get("status")
        if v_status in ("ok", "warning"):
            return True
        return bool(it.get("ok"))

    all_ok = bool(src_items) and all(_item_is_ok_or_warning(it) for it in src_items)
    requires_confirmation = bool(job_summary.get("requires_confirmation"))

    response: Dict[str, Any] = {
        "ok": all_ok,
        "message": (
            job_summary.get("message")
            if requires_confirmation
            else ("ingest completed" if all_ok else "ingest completed with errors")
        ),
        "job_id": real_job_id,
        "items": [],
    }

    if requires_confirmation:
        response["input_urls_count"] = job_summary.get("input_urls_count")
        response["expanded_urls_count"] = job_summary.get("expanded_urls_count")
        response["requires_confirmation"] = True
        response["next_command"] = job_summary.get("next_command")
        response["errors"] = job_summary.get("errors") or []

    if warnings_top:
        response["warnings"] = warnings_top

    for it in src_items:
        url = it.get("url")
        verification = it.get("verification") or {}
        v_status = verification.get("status")  # "ok" | "warning" | "failed"
        v_warnings = verification.get("warnings") or []

        download_succeeded = bool(it.get("mp3_exists")) or bool(it.get("mp3_path"))

        if v_status == "warning" and download_succeeded:
            item_ok = True
            status = "warning"
        elif bool(it.get("ok")) and download_succeeded:
            item_ok = True
            status = "done"
        else:
            item_ok = False
            status = "failed"

        item_result = {
            "ok": item_ok,
            "url": url,
            "status": status,
            "stage": "finished" if item_ok else "failed",
            "mp3_path": it.get("mp3_path"),
            "title": it.get("title"),
            "channel": it.get("channel"),
            "duration_seconds": it.get("duration_seconds"),
            "warnings": v_warnings,
            "error": None
            if item_ok
            else {
                "code": "INGEST_FAILED",
                "message": it.get("message") or "failed",
                "details": it.get("debug"),
            },
        }
        response["items"].append(item_result)

        _emit(
            on_event,
            {
                "type": "progress",
                "job_id": real_job_id,
                "url": url,
                "stage": "finished" if item_ok else "failed",
                "percent": 100 if item_ok else None,
                "message": "Finished." if item_ok else "Failed.",
            },
        )

    # Apply save_as rename (single item only)
    if save_as and len(response["items"]) == 1:
        item0 = response["items"][0]
        old_path = item0.get("mp3_path")

        if old_path:
            old = Path(old_path)
            safe_name = _ensure_mp3_ext(_sanitize_filename(save_as))

            new = old.with_name(safe_name)

            # Avoid clobbering an existing file
            if new.exists():
                stem = new.stem
                suffix = new.suffix
                i = 1
                while True:
                    candidate = new.with_name(f"{stem} ({i}){suffix}")
                    if not candidate.exists():
                        new = candidate
                        break
                    i += 1

            try:
                old.rename(new)
                item0["mp3_path"] = str(new)
            except Exception as e:
                item0.setdefault("warnings", [])
                item0["warnings"].append(f"Could not rename file: {e}")

    _emit(
        on_event,
        {
            "type": "progress",
            "job_id": real_job_id,
            "url": None,
            "stage": "finished" if all_ok else "failed",
            "percent": 100 if all_ok else None,
            "message": "Ingest finished." if all_ok else "Ingest finished with errors.",
        },
    )

    # Keep our seam store consistent at a coarse level (optional, but nice)
    store.update_job(
        job_id,
        {
            "status": "done" if all_ok else "failed",
            "succeeded": sum(1 for it in src_items if bool(it.get("ok"))),
            "failed": sum(1 for it in src_items if not bool(it.get("ok"))),
        },
    )

    return response