from pathlib import Path
import subprocess
import json


def extract_source_info(url: str, settings) -> dict:
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--skip-download",
        *(["--cookies-from-browser", settings.cookies_from_browser] if settings.cookies_from_browser else []),
        url,
    ]

    completed = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return json.loads(completed.stdout)


def normalize_source_metadata(info: dict, source_url: str, mp3_path: str | None = None) -> dict:
    """
    Normalize metadata from yt-dlp info dict into our internal format.
    """

    title = (
        info.get("track")
        or info.get("title")
    )

    channel = (
        info.get("channel")
        or info.get("uploader")
        or info.get("creator")
    )

    duration = info.get("duration")

    source_id = info.get("id")

    # Fallback: derive title from filename if needed
    if not title and mp3_path:
        title = Path(mp3_path).stem

    if not title:
        title = "unknown title"

    if not channel:
        channel = "unknown channel"

    return {
        "title": title,
        "channel": channel,
        "duration_seconds": duration,
        "source_url": source_url,
        "source_id": source_id,
    }