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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import uuid4
from urllib.parse import urlparse, parse_qs
from audioscribe.core.verification_schema import normalize_verification
from audioscribe.core.config import get_settings


@dataclass(frozen=True)
class Job:
    job_id: str
    urls: list[str]


# In-memory placeholder store (slice-safe: no DB yet)
_JOBS: dict[str, Job] = {}


def create_job(urls: Iterable[str]) -> dict:
    """
    Create a job for ingesting a set of URLs.
    Placeholder implementation: stores job in memory only.
    """
    url_list = [u.strip() for u in urls if str(u).strip()]
    job_id = str(uuid4())

    _JOBS[job_id] = Job(job_id=job_id, urls=url_list)

    return {
        "ok": True,
        "message": "job created (placeholder)",
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


def _build_metadata(title, channel, duration_seconds, url):
    return {
        "title": title,
        "channel": channel,
        "duration_seconds": duration_seconds,
        "video_id": _extract_youtube_id(url),
        "source_url": url,
    }


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

            # If expansion fails or yields nothing, fall back to treating URL as a single item.
            # We still record a diagnostic note so future debugging is possible.
            if not expanded:
                if debug:
                    errors.append(f"playlist expansion failed; falling back to single URL: {debug.get('message')}")
                work_urls.append(u)
                continue

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


def _make_output_dir_and_template() -> tuple[Path, str]:
    """Create outputs directory (if needed) and return (out_dir, out_template)."""
    out_dir = Path("outputs")
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


def _build_download_command(*, url: str, settings, out_template: str) -> list[str]:
    return [
        "yt-dlp",
        "--windows-filenames",
        *(["--extractor-args", "youtube:player_client=android"] if not settings.cookies_from_browser else []),
        "-x",
        "--audio-format", "mp3",
        "--print", "before_dl:url",
        "--print", "title",
        "--print", "channel",
        "--print", "uploader",
        "--print", "duration",
        "--print", "after_move:filepath",
        "-o", out_template,
        *(["--cookies-from-browser", settings.cookies_from_browser] if settings.cookies_from_browser else []),
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


def _parse_download_stdout(stdout: str) -> tuple[str | None, str | None, int | None, str]:
    raw_out = (stdout or "").strip()
    lines = [line.strip() for line in raw_out.splitlines() if line.strip()]

    title = None
    channel = None
    duration_seconds = None
    mp3_path = ""

    if len(lines) >= 5:
        title = lines[0] or None

        second = lines[1]
        third = lines[2]
        fourth = lines[3]
        last = lines[-1]

        if second.isdigit():
            # shape:
            # title
            # duration
            # resolved media url
            # filepath
            raw_duration = second
            try:
                duration_seconds = int(raw_duration) if raw_duration else None
            except ValueError:
                duration_seconds = None

            mp3_path = last or ""

        elif third.isdigit():
            # shape:
            # title
            # uploader
            # duration
            # resolved media url
            # filepath
            channel = second or None

            raw_duration = third
            try:
                duration_seconds = int(raw_duration) if raw_duration else None
            except ValueError:
                duration_seconds = None

            mp3_path = last or ""

        else:
            # shape:
            # title
            # channel
            # uploader
            # duration
            # resolved media url
            # filepath
            channel = second or third or None

            raw_duration = fourth
            try:
                duration_seconds = int(raw_duration) if raw_duration else None
            except ValueError:
                duration_seconds = None

            mp3_path = last or ""

    elif lines:
        mp3_path = lines[-1]

    # yt-dlp sometimes prints quotes around the filepath on Windows
    if mp3_path.startswith('"') and mp3_path.endswith('"'):
        mp3_path = mp3_path[1:-1].strip()

    return title, channel, duration_seconds, mp3_path


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


def _run_and_normalize_verification(mp3_path: str) -> dict:
    from audioscribe.core.verify_audio import verify_audio

    try:
        verification = verify_audio(mp3_path)
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
    item["mp3_path"] = str(Path(mp3_path).relative_to(Path.cwd())) if mp3_exists else mp3_path
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


def _process_one_url(
    *,
    job_id: str,
    url: str,
    index: int,
    settings,
    out_dir: Path,
    out_template: str,
) -> dict:
    """
    Download one URL via yt-dlp and verify the produced MP3.
    Returns canonical per-item structure (stable keys).
    """
    item = _make_initial_item(job_id=job_id, index=index, url=url)

    cmd = _build_download_command(
        url=url,
        settings=settings,
        out_template=out_template,
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

    title, channel, duration_seconds, mp3_path = _parse_download_stdout(completed.stdout)
    mp3_path, mp3_exists = _resolve_mp3_path(mp3_path, url, out_dir)

    debug = None
    if not mp3_exists:
        debug = {
            "stdout_tail": (completed.stdout or "")[-400:],
            "stderr_tail": (completed.stderr or "")[-400:],
        }

    metadata = _build_metadata(title, channel, duration_seconds, url)

    verification_payload = normalize_verification(
        status="failed",
        path=mp3_path if mp3_path else None,
        metrics=None,
        warnings=[],
        errors=[] if mp3_exists else ["mp3 not found after download"],
    )

    if mp3_exists:
        verification_payload = _run_and_normalize_verification(mp3_path)

    return _finalize_processed_item(
        item=item,
        mp3_path=mp3_path,
        mp3_exists=mp3_exists,
        debug=debug,
        title=title,
        channel=channel,
        duration_seconds=duration_seconds,
        metadata=metadata,
        verification_payload=verification_payload,
    )


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

    return {
        "ok": True,
        "message": "job processed",
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


def process_job(job_id: str, allow_playlist: bool = False) -> dict:
    """
    Process a job end-to-end (sequential).
    High-level flow:
      1) validate job
      2) resolve URLs (playlist expansion + guard)
      3) download + verify each item
      4) return summary with stable schema
    """
    job = _JOBS.get(job_id)
    if not job:
        return _job_error_response(job_id, "job not found", ["job not found"])

    if not job.urls:
        return _job_error_response(job_id, "no urls in job", ["no urls in job"])

    settings = get_settings()
    input_urls_count = len(job.urls)

    work_urls, resolution_errors, blocked = _resolve_work_urls(job.urls, settings, allow_playlist)

    if blocked is not None:
        blocked["job_id"] = job_id
        return blocked

    out_dir, out_template = _make_output_dir_and_template()

    items = [
        _process_one_url(
            job_id=job_id,
            url=url,
            index=index,
            settings=settings,
            out_dir=out_dir,
            out_template=out_template,
        )
        for index, url in enumerate(work_urls)
    ]

    return _summarize_job(
        job_id=job_id,
        input_urls_count=input_urls_count,
        expanded_urls_count=len(work_urls),
        errors=resolution_errors,
        items=items,
    )



def get_job_status(job_id: str) -> dict:
    """
    Return job status.
    Placeholder implementation: only indicates existence for now.
    """
    exists = job_id in _JOBS
    return {
        "ok": True,
        "message": "status placeholder",
        "job_id": job_id,
        "exists": exists,
    }
