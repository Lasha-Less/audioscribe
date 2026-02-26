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
        debug = {"message": "yt-dlp not found during playlist expansion"}
        return [], debug
    except Exception as e:
        debug = {"message": "playlist expansion error", "error": str(e)}
        return [], debug

    ids = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    # Convert to canonical watch URLs
    video_urls = [f"https://www.youtube.com/watch?v={vid}" for vid in ids]
    return video_urls, None


def process_job(job_id: str, allow_playlist: bool = False) -> dict:
    """
    Process a job end-to-end.
    Downloads MP3s for all URLs sequentially via yt-dlp,
    then verifies produced audio via ffprobe (JSON-serializable result).
    Continues on errors and returns an aggregated summary.
    """
    job = _JOBS.get(job_id)

    # Always return same top-level keys
    if not job:
        return {
            "ok": False,
            "message": "job not found",
            "job_id": job_id,
            "input_urls_count": 0,
            "expanded_urls_count": 0,
            "requires_confirmation": False,
            "next_command": None,
            "errors": ["job not found"],
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "items": [],
        }

    if not job.urls:
        return {
            "ok": False,
            "message": "no urls in job",
            "job_id": job_id,
            "input_urls_count": 0,
            "expanded_urls_count": 0,
            "requires_confirmation": False,
            "next_command": None,
            "errors": ["no urls in job"],
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "items": [],
        }

    settings = get_settings()

    input_urls_count = len(job.urls)

    work_urls: list[str] = []
    expanded_urls_count = 0

    for u in job.urls:
        if _is_playlist_url(u):
            expanded, debug = _expand_playlist_to_video_urls(u, settings)

            # If expansion fails or yields nothing, just treat as single URL (yt-dlp will decide)
            if not expanded:
                work_urls.append(u)
                continue

            # If it expands to multiple items, enforce guard
            if len(expanded) > 1 and not allow_playlist:
                return {
                    "ok": False,
                    "message": "playlist detected; confirmation required",
                    "job_id": job_id,
                    "input_urls_count": input_urls_count,
                    "expanded_urls_count": len(expanded),
                    "requires_confirmation": True,
                    "next_command": f'audioscribe ingest "{u}" --allow-playlist',
                    "errors": [],
                    "total": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "items": [],
                }

            work_urls.extend(expanded)
        else:
            work_urls.append(u)

    expanded_urls_count = len(work_urls)

    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_template = str(out_dir / "%(title)s [%(id)s].%(ext)s")

    def _process_one(url: str, index: int) -> dict:
        # Always same per-item keys
        item = {
            "ok": False,
            "message": "",
            "job_id": job_id,
            "index": index,
            "url": url,
            "mp3_path": None,
            "mp3_exists": False,
            "verification": normalize_verification(
                status="failed",
                path=None,
                metrics=None,
                warnings=[],
                errors=["not processed"],
            ),
            "debug": None,
        }

        cmd = [
            "yt-dlp",
            "--windows-filenames",
            *(["--extractor-args", "youtube:player_client=android"] if not settings.cookies_from_browser else []),
            "-x",
            "--audio-format", "mp3",
            "--print", "after_move:filepath",
            "-o", out_template,
            *(["--cookies-from-browser", settings.cookies_from_browser] if settings.cookies_from_browser else []),
            url,
        ]

        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except FileNotFoundError:
            item["ok"] = False
            item["message"] = "yt-dlp not found. Is it installed in this venv?"
            item["verification"] = normalize_verification(
                status="failed",
                path=None,
                metrics=None,
                warnings=[],
                errors=["yt-dlp not found"],
            )
            return item
        except subprocess.CalledProcessError as e:
            item["ok"] = False
            item["message"] = "yt-dlp failed"
            item["debug"] = {
                "stdout_tail": (e.stdout or "")[-400:],
                "stderr_tail": (e.stderr or "")[-400:],
            }
            item["verification"] = normalize_verification(
                status="failed",
                path=None,
                metrics=None,
                warnings=[],
                errors=["yt-dlp failed"],
            )
            return item
        except Exception as e:
            item["ok"] = False
            item["message"] = "download failed"
            item["debug"] = {"error": str(e)}
            item["verification"] = normalize_verification(
                status="failed",
                path=None,
                metrics=None,
                warnings=[],
                errors=[str(e)],
            )
            return item

        # yt-dlp prints the final filepath via after_move:filepath
        raw_out = (completed.stdout or "").strip()
        mp3_path = raw_out.splitlines()[-1].strip() if raw_out else ""

        # yt-dlp sometimes prints quotes around the filepath on Windows
        if mp3_path.startswith('"') and mp3_path.endswith('"'):
            mp3_path = mp3_path[1:-1].strip()

        mp3_exists = False
        mp3_path_obj = None

        if mp3_path:
            mp3_path_obj = Path(mp3_path)

            if not mp3_path_obj.is_absolute():
                mp3_path_obj = (Path.cwd() / mp3_path_obj).resolve()
                mp3_path = str(mp3_path_obj)

            mp3_exists = mp3_path_obj.exists()

        # Fallback: locate the real file by video id in filename
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
                    mp3_path = str(mp3_path_obj)
                    mp3_exists = True

        debug = None
        if not mp3_exists:
            debug = {
                "stdout_tail": (completed.stdout or "")[-400:],
                "stderr_tail": (completed.stderr or "")[-400:],
            }

        item["mp3_path"] = mp3_path or None
        item["mp3_exists"] = mp3_exists
        item["debug"] = debug

        # Canonical verification object (same keys everywhere)
        verification_payload = normalize_verification(
            status="failed",
            path=mp3_path if mp3_path else None,
            metrics=None,
            warnings=[],
            errors=[] if mp3_exists else ["mp3 not found after download"],
        )

        if mp3_exists:
            from audioscribe.core.verify_audio import verify_audio  # local import keeps startup simple
            verification = verify_audio(mp3_path)

            if isinstance(verification, dict):
                verification_payload = normalize_verification(
                    status=verification.get("status"),
                    path=verification.get("path") or mp3_path,
                    metrics=verification.get("metrics"),
                    warnings=verification.get("warnings"),
                    errors=verification.get("errors"),
                )
            else:
                metrics = getattr(verification, "metrics", None)
                verification_payload = normalize_verification(
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

        item["verification"] = verification_payload

        # Item ok = verified success, not merely "yt-dlp succeeded"
        # (If you want different semantics later, we change it explicitly.)
        item["ok"] = (verification_payload.get("status") == "ok")
        item["message"] = "processed" if item["ok"] else "processed with issues"

        return item

    items = [_process_one(url, index) for index, url in enumerate(work_urls)]

    total = len(items)
    succeeded = sum(1 for it in items if it["ok"])
    failed = total - succeeded

    return {
        "ok": True,
        "message": "job processed",
        "job_id": job_id,
        "input_urls_count": input_urls_count,
        "expanded_urls_count": expanded_urls_count,
        "requires_confirmation": False,
        "next_command": None,
        "errors": [],
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "items": items,
    }



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
