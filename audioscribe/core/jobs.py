"""
jobs.py — job lifecycle + end-to-end processing (current single-module implementation).

Owns:
- in-memory job store (temporary)
- create_job/process_job/get_job_status
- sequential download + verification pipeline

Non-goals:
- CLI parsing (belongs in cli.py)
- persistence (will move to storage layer later)
"""


from __future__ import annotations
import subprocess
#from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
#from uuid import uuid4
from urllib.parse import urlparse, parse_qs
from audioscribe.core.verification_schema import normalize_verification
from audioscribe.core.config import get_settings
from audioscribe.core.metadata import extract_source_info, normalize_source_metadata
from audioscribe.storage.job_store import JobStore
from audioscribe.storage.memory_job_store import InMemoryJobStore


_DEFAULT_STORE = InMemoryJobStore()


def create_job(
    urls: Iterable[str],
    *,
    store: JobStore | None = None,
) -> dict:
    active_store = store if store is not None else _DEFAULT_STORE
    url_list = [url.strip() for url in urls if url.strip()]
    job_id = active_store.create_job(url_list)

    return {
        "ok": True,
        "message": "job created",
        "job_id": job_id,
        "count": len(url_list),
    }


def _extract_youtube_id(url: str) -> str | None:
    """
    Best-effort extraction of YouTube video id from common URL formats.
    """
    try:
        u = urlparse(url)
        qs = parse_qs(u.query)
        if "v" in qs and qs["v"]:
            return qs["v"][0]
        # youtu.be/<id>
        if u.netloc.endswith("youtu.be"):
            vid = u.path.strip("/").split("/")[0]
            return vid or None
    except Exception:
        return None
    return None


def _is_playlist_url(url: str) -> bool:
    # Minimal heuristic: playlist context in query params
    return "list=" in (url or "")


def _expand_playlist_to_video_urls(url: str, settings) -> tuple[list[str], dict | None]:
    """
    Returns (video_urls, debug)
    - video_urls: list of canonical watch URLs
    - debug: optional debug info if expansion fails
    """
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print", "id",
        *(["--cookies-from-browser", settings.cookies_from_browser] if settings.cookies_from_browser else []),
        url,
    ]

    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        debug = {
            "message": "playlist expansion failed",
            "stdout_tail": (e.stdout or "")[-400:],
            "stderr_tail": (e.stderr or "")[-400:],
        }
        return [], debug
    except FileNotFoundError:
        debug = {"message": "yt-dlp not found. Is it installed in this venv?"}
        return [], debug
    except Exception as e:
        debug = {"message": "playlist expansion error", "error": str(e)}
        return [], debug

    ids = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    # Convert to canonical watch URLs
    video_urls = [f"https://www.youtube.com/watch?v={vid}" for vid in ids]
    return video_urls, None


def _job_error_response(job_id: str, message: str, errors: list[str]) -> dict:
    """Build a canonical job-level error response (stable top-level keys)."""
    return {
        "ok": False,
        "message": message,
        "job_id": job_id,
        "input_urls_count": 0,
        "expanded_urls_count": 0,
        "requires_confirmation": False,
        "next_command": None,
        "errors": errors,
        "total": 0,
        "succeeded": 0,
        "failed": 0,
        "items": [],
    }


def _resolve_work_urls(
    urls: list[str],
    settings,
    allow_playlist: bool,
) -> tuple[list[str], list[str], dict | None]:
    """
    Resolve input URLs into a list of concrete video URLs to process.

    Returns:
      work_urls: URLs that will actually be processed (expanded if playlist)
      errors: non-fatal diagnostics encountered during resolution
      blocked_response: if playlist detected but allow_playlist is False, return this response (no downloads)
    """
    errors: list[str] = []
    work_urls: list[str] = []

    for u in urls:
        if _is_playlist_url(u):
            # Why: --flat-playlist avoids downloading media during expansion; we only need IDs.
            expanded, debug = _expand_playlist_to_video_urls(u, settings)

            # Stop before downloading if the playlist cannot be resolved.
            if not expanded:
                reason = (
                    debug.get("message")
                    if debug
                    else "playlist is empty or has no accessible videos"
                )
                errors.append(f"Could not read playlist {u}: {reason}")

                blocked = _job_error_response(
                    job_id="",
                    message="could not read playlist; no downloads started",
                    errors=errors,
                )
                blocked["input_urls_count"] = len(urls)
                blocked["expanded_urls_count"] = len(work_urls)

                return [], errors, blocked

            # Guard: avoid accidental bulk downloads unless user explicitly opts in.
            if len(expanded) > 1 and not allow_playlist:
                blocked = {
                    "ok": False,
                    "message": "playlist detected; confirmation required",
                    "job_id": "",  # filled by caller
                    "input_urls_count": len(urls),
                    "expanded_urls_count": len(expanded),
                    "requires_confirmation": True,
                    "next_command": f'audioscribe ingest "{u}" --allow-playlist',
                    "errors": errors,
                    "total": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "items": [],
                }
                return [], errors, blocked

            work_urls.extend(expanded)
        else:
            work_urls.append(u)

    return work_urls, errors, None


def _make_output_dir_and_template(
    output_dir: str | Path = "outputs",
) -> tuple[Path, str]:
    """Create the chosen output directory and build the filename template."""
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / "%(title)s [%(id)s].%(ext)s")
    return out_dir, out_template


def _make_initial_item(*, job_id: str, index: int, url: str) -> dict:
    return {
        "ok": False,
        "message": "",
        "job_id": job_id,
        "index": index,
        "url": url,

        "mp3_path": None,
        "mp3_exists": False,

        # metadata (C3_SL12)
        "title": None,
        "channel": None,
        "duration_seconds": None,
        "metadata": None,

        "verification": normalize_verification(
            status="failed",
            path=None,
            metrics=None,
            warnings=[],
            errors=["not processed"],
        ),
        "debug": None,
    }


def _build_download_command(
    *,
    url: str,
    settings,
    out_template: str,
    media_type: str = "audio",
) -> list[str]:
    if media_type == "audio":
        format_options = [
            "-x",
            "--audio-format", "mp3",
        ]
    elif media_type == "video":
        format_options = [
            "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
            "--merge-output-format", "mp4",
        ]
    else:
        raise ValueError(f"Unsupported media type: {media_type}")

    return [
        "yt-dlp",
        "--encoding", "utf-8",
        "--no-playlist",
        "--windows-filenames",
        *(
            ["--extractor-args", "youtube:player_client=android"]
            if not settings.cookies_from_browser
            else []
        ),
        *format_options,
        "--print", "before_dl:url",
        "--print", "after_move:filepath",
        "-o", out_template,
        *(
            ["--cookies-from-browser", settings.cookies_from_browser]
            if settings.cookies_from_browser
            else []
        ),
        url,
    ]


def _run_download(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _parse_download_stdout(stdout: str) -> str:
    raw_out = (stdout or "").strip()
    lines = [line.strip() for line in raw_out.splitlines() if line.strip()]

    mp3_path = lines[-1] if lines else ""

    if mp3_path.startswith('"') and mp3_path.endswith('"'):
        mp3_path = mp3_path[1:-1].strip()

    return mp3_path


def _resolve_mp3_path(mp3_path: str, url: str, out_dir: Path) -> tuple[str, bool]:
    mp3_exists = False
    mp3_path_obj: Path | None = None

    if mp3_path:
        mp3_path_obj = Path(mp3_path)
        if not mp3_path_obj.is_absolute():
            mp3_path_obj = (Path.cwd() / mp3_path_obj).resolve()
            mp3_path = str(mp3_path_obj)
        mp3_exists = mp3_path_obj.exists()

    # Why: yt-dlp output can be noisy; we fall back to locating by video id in filename.
    if not mp3_exists:
        video_id = _extract_youtube_id(url)
        if video_id:
            needle = f"[{video_id}]"
            candidates = sorted(
                (p for p in out_dir.glob("*.mp3") if needle in p.name),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                mp3_path_obj = candidates[0]
                mp3_path = str(mp3_path_obj.resolve())
                mp3_exists = True

    return mp3_path, mp3_exists


def _build_download_failure_item(
    *,
    item: dict,
    message: str,
    errors: list[str],
    debug: dict | None = None,
) -> dict:
    item["message"] = message
    item["debug"] = debug
    item["verification"] = normalize_verification(
        status="failed",
        path=None,
        metrics=None,
        warnings=[],
        errors=errors,
    )
    return item


def _run_and_normalize_verification(
    mp3_path: str,
    *,
    media_type: str = "audio",
) -> dict:
    from audioscribe.core.verify_audio import verify_audio, verify_media

    try:
        if media_type == "audio":
            verification = verify_audio(mp3_path)
        else:
            verification = verify_media(mp3_path, media_type=media_type)
    except Exception as e:
        return normalize_verification(
            status="failed",
            path=mp3_path,
            metrics=None,
            warnings=[],
            errors=[str(e)],
        )

    if isinstance(verification, dict):
        return normalize_verification(
            status=verification.get("status"),
            path=verification.get("path") or mp3_path,
            metrics=verification.get("metrics"),
            warnings=verification.get("warnings"),
            errors=verification.get("errors"),
        )

    metrics = getattr(verification, "metrics", None)
    return normalize_verification(
        status=getattr(getattr(verification, "status", None), "value", None),
        path=mp3_path,
        metrics={
            "duration_s": getattr(metrics, "duration_s", None) if metrics else None,
            "sample_rate_hz": getattr(metrics, "sample_rate_hz", None) if metrics else None,
            "bitrate_kbps": getattr(metrics, "bitrate_kbps", None) if metrics else None,
            "channels": getattr(metrics, "channels", None) if metrics else None,
            "file_size_bytes": getattr(metrics, "file_size_bytes", None) if metrics else None,
        },
        warnings=getattr(verification, "warnings", None),
        errors=getattr(verification, "errors", None),
    )


def _finalize_processed_item(
    *,
    item: dict,
    mp3_path: str,
    mp3_exists: bool,
    debug: dict | None,
    title: str | None,
    channel: str | None,
    duration_seconds: int | None,
    metadata: dict,
    verification_payload: dict,
) -> dict:
    item["mp3_path"] = str(Path(mp3_path).resolve()) if mp3_exists else mp3_path
    item["mp3_exists"] = mp3_exists
    item["debug"] = debug

    item["title"] = title
    item["channel"] = channel
    item["duration_seconds"] = duration_seconds
    item["metadata"] = metadata

    item["verification"] = verification_payload
    item["ok"] = mp3_exists and verification_payload["status"] != "failed"
    item["message"] = "downloaded mp3 (minimal)"
    return item



def _resolve_download_path(
    file_path: str,
    url: str,
    out_dir: Path,
    *,
    media_type: str,
) -> tuple[str, bool]:
    if media_type == "audio":
        return _resolve_mp3_path(file_path, url, out_dir)

    if not file_path:
        return "", False

    path = Path(file_path).resolve()
    return str(path), path.is_file()



def _process_one_url(
    *,
    job_id: str,
    url: str,
    index: int,
    settings,
    out_dir: Path,
    out_template: str,
    media_type: str = "audio",
) -> dict:
    """
    Download and verify one audio or video item.
    """
    item = _make_initial_item(job_id=job_id, index=index, url=url)
    item.update({
        "media_type": media_type,
        "file_path": None,
        "file_exists": False,
    })

    source_info = {}
    try:
        source_info = extract_source_info(url, settings)
    except Exception:
        source_info = {}

    cmd = _build_download_command(
        url=url,
        settings=settings,
        out_template=out_template,
        media_type=media_type,
    )

    try:
        completed = _run_download(cmd)
    except FileNotFoundError:
        return _build_download_failure_item(
            item=item,
            message="yt-dlp not found. Is it installed in this venv?",
            errors=["yt-dlp not found"],
        )
    except subprocess.CalledProcessError as e:
        return _build_download_failure_item(
            item=item,
            message="yt-dlp failed",
            errors=["yt-dlp failed"],
            debug={
                "stdout_tail": (e.stdout or "")[-400:],
                "stderr_tail": (e.stderr or "")[-400:],
            },
        )
    except Exception as e:
        return _build_download_failure_item(
            item=item,
            message="download failed",
            errors=[str(e)],
            debug={"error": str(e)},
        )

    file_path = _parse_download_stdout(completed.stdout)
    file_path, file_exists = _resolve_download_path(
        file_path,
        url,
        out_dir,
        media_type=media_type,
    )

    debug = None
    if not file_exists:
        debug = {
            "stdout_tail": (completed.stdout or "")[-400:],
            "stderr_tail": (completed.stderr or "")[-400:],
        }

    metadata = normalize_source_metadata(
        source_info,
        source_url=url,
        mp3_path=file_path if file_exists else None,
    )

    verification_payload = normalize_verification(
        status="failed",
        path=file_path or None,
        metrics=None,
        warnings=[],
        errors=[] if file_exists else ["file not found after download"],
    )

    if file_exists:
        verification_payload = _run_and_normalize_verification(
            file_path,
            media_type=media_type,
        )

    item.update({
        "file_path": file_path,
        "file_exists": file_exists,
        "mp3_path": file_path if media_type == "audio" else None,
        "mp3_exists": file_exists if media_type == "audio" else False,
        "debug": debug,
        "title": metadata["title"],
        "channel": metadata["channel"],
        "duration_seconds": metadata["duration_seconds"],
        "metadata": metadata,
        "verification": verification_payload,
        "ok": file_exists and verification_payload["status"] != "failed",
    })
    item["message"] = (
        f"downloaded {media_type}"
        if item["ok"]
        else f"{media_type} download or verification failed"
    )
    return item


def _summarize_job(
    *,
    job_id: str,
    input_urls_count: int,
    expanded_urls_count: int,
    errors: list[str],
    items: list[dict],
) -> dict:
    """Build canonical job summary response."""
    total = len(items)
    succeeded = sum(1 for it in items if it.get("ok"))
    failed = total - succeeded
    all_ok = total > 0 and failed == 0 and not errors

    return {
        "ok": all_ok,
        "message": (
            "job processed successfully"
            if all_ok
            else "job processed with errors"
        ),
        "job_id": job_id,
        "input_urls_count": input_urls_count,
        "expanded_urls_count": expanded_urls_count,
        "requires_confirmation": False,
        "next_command": None,
        "errors": errors,
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "items": items,
    }

def _store_item_result(
    store: JobStore,
    job_id: str,
    item_id: str,
    result: dict,
) -> None:
    verification = result.get("verification") or {}
    succeeded = bool(result.get("ok"))
    errors = verification.get("errors") or []

    error_message = None
    if not succeeded:
        error_message = (
            "; ".join(str(error) for error in errors)
            or result.get("message")
            or "processing failed"
        )

    store.update_item(
        job_id,
        item_id,
        {
            "status": "done" if succeeded else "failed",
                        "mp3_path": result.get("mp3_path"),
            "file_path": result.get("file_path") or result.get("mp3_path"),
            "media_type": result.get("media_type", "audio"),
            "title": result.get("title"),
            "channel": result.get("channel"),
            "duration_seconds": result.get("duration_seconds"),
            "warnings": list(verification.get("warnings") or []),
            "error_code": None if succeeded else "INGEST_FAILED",
            "error_message": error_message,
            "extra": {
                "verification": verification,
                "metadata": result.get("metadata"),
                "debug": result.get("debug"),
            },
        },
    )

def process_job(
    job_id: str,
    allow_playlist: bool = False,
    *,
    store: JobStore | None = None,
    output_dir: str | Path = "outputs",
    media_type: str = "audio",
) -> dict:
    """Download and verify the URLs belonging to an existing job."""
    if media_type not in {"audio", "video"}:
        raise ValueError(f"Unsupported media type: {media_type}")
    active_store = store if store is not None else _DEFAULT_STORE

    try:
        active_store.get_job(job_id)
        urls = [item.url for item in active_store.list_items(job_id)]
    except KeyError:
        return _job_error_response(
            job_id, "job not found", ["job not found"]
        )

    if not urls:
        return _job_error_response(
            job_id, "no urls in job", ["no urls in job"]
        )

    settings = get_settings()
    input_urls_count = len(urls)

    work_urls, resolution_errors, blocked = _resolve_work_urls(
        urls, settings, allow_playlist
    )

    if blocked is not None:
        blocked["job_id"] = job_id
        if media_type == "video" and blocked.get("next_command"):
            blocked["next_command"] = blocked["next_command"].replace(
                "audioscribe ingest ",
                "python -m audioscribe video ",
                1,
            )
        return blocked

    out_dir, out_template = _make_output_dir_and_template(output_dir)

    active_store.replace_items(job_id, work_urls)
    stored_items = active_store.list_items(job_id)
    items = []

    for index, stored_item in enumerate(stored_items):
        active_store.update_item(
            job_id,
            stored_item.item_id,
            {"status": "running"},
        )

        result = _process_one_url(
            job_id=job_id,
            url=stored_item.url,
            index=index,
            settings=settings,
            out_dir=out_dir,
            out_template=out_template,
            media_type=media_type,
        )
        result["item_id"] = stored_item.item_id

        _store_item_result(
            active_store,
            job_id,
            stored_item.item_id,
            result,
        )
        items.append(result)

    return _summarize_job(
        job_id=job_id,
        input_urls_count=input_urls_count,
        expanded_urls_count=len(work_urls),
        errors=resolution_errors,
        items=items,
    )



def get_job_status(
    job_id: str,
    *,
    store: JobStore | None = None,
) -> dict:
    active_store = store if store is not None else _DEFAULT_STORE

    try:
        job = active_store.get_job(job_id)
    except KeyError:
        return {
            "ok": False,
            "message": "job not found",
            "job_id": job_id,
            "exists": False,
        }

    return {
        "ok": True,
        "message": "job found",
        "job_id": job_id,
        "exists": True,
        "status": job.status,
    }
