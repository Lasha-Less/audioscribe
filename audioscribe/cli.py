from __future__ import annotations
from pathlib import Path
import typer
import json

from audioscribe.core import create_job as core_create_job, process_job as core_process_job
from audioscribe.core.verification_schema import normalize_verification
from audioscribe.core.verify_audio import verify_audio
from dataclasses import asdict, is_dataclass
from enum import Enum

from audioscribe_core_fake import (
    create_job,
    delete_track,
    get_job_status,
    list_tracks,
    purge_tracks,
    search_tracks,
    update_track,
    upload_job,
    upload_track,
    process_job,
)

app = typer.Typer()
app.info.help = "AudioScribe CLI (skeleton)."


def _to_jsonable(obj):
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


@app.command("version")
def version_cmd():
    """Print version info."""
    typer.echo("AudioScribe CLI — v0.0 (skeleton)")


@app.command("ingest")
def ingest_cmd(
    urls: list[str],
    allow_playlist: bool = typer.Option(
        False,
        "--allow-playlist",
        help="Allow downloading multiple items when a playlist is detected/expanded.",
    ),
):
    """Ingest URLs (placeholder)."""
    result = core_create_job(urls)
    print(json.dumps(result, indent=2))

    if result.get("ok"):
        job_id = result["job_id"]
        print(json.dumps(core_process_job(job_id, allow_playlist=allow_playlist), indent=2))
        print(f"job_id={job_id}")


@app.command("status")
def status_cmd(job_id: str):
    """Show status for a job (placeholder)"""
    result = get_job_status(job_id)
    typer.echo(str(result))


@app.command("list")
def list_cmd(limit: int = typer.Option(25, "--limit", "-m")):
    """List tracks (placeholder)"""
    result = list_tracks(limit)
    typer.echo(str(result))


@app.command("search")
def search_cmd(query: str):
    """Search for tracks (placeholder)"""
    result = search_tracks(query)
    typer.echo(str(result))


@app.command("delete")
def delete_cmd(
    track_id: str,
    hard: bool = typer.Option(False, "--hard"),
):
    """Delete a track (placeholder)."""
    result = delete_track(track_id, soft=not hard)
    typer.echo(str(result))


@app.command("edit")
def edit_cmd(
    track_id: str,
    title: str | None = typer.Option(None, "--title"),
    artist: str | None = typer.Option(None, "--artist"),
):
    """Edit track metadata (placeholder)."""
    fields: dict[str, str] = {}

    if title is not None:
        fields["title"] = title
    if artist is not None:
        fields["artist"] = artist

    result = update_track(track_id, fields)
    typer.echo(str(result))


@app.command("purge")
def purge_cmd(
    older_than_days: int | None = typer.Option(None, "--older-than-days"),
    confirm: bool = typer.Option(False, "--confirm"),
):
    """Purge tracks (placeholder)."""
    result = purge_tracks(older_than_days=older_than_days, confirm=confirm)
    typer.echo(str(result))


@app.command("upload")
def upload_cmd(
    track_id: str | None = typer.Argument(None),
    job_id: str | None = typer.Option(None, "--job"),
):
    """Upload a track or a whole job (placeholder)."""
    if job_id is not None:
        result = upload_job(job_id)
        typer.echo(str(result))
        return

    if track_id is None:
        typer.echo("Provide TRACK_ID or use --job JOB_ID")
        raise typer.Exit(code=1)

    result = upload_track(track_id)
    typer.echo(str(result))


def run():
    app()


@app.command()
def verify(path: str, strict: bool = False):
    """
    Verify an audio file.
    Prints canonical verification JSON (same keys always).
    Exit code:
      0 = ok
      2 = warning (non-strict)
      1 = failed (or warning in strict)
    """
    file_path = Path(path)

    def _blank_result(p: str, status: str, errors=None, warnings=None):
        return {
            "ok": (status != "failed"),
            "status": status,
            "path": p,
            "metrics": {
                "duration_s": None,
                "sample_rate_hz": None,
                "bitrate_kbps": None,
                "channels": None,
                "file_size_bytes": None,
            },
            "warnings": warnings or [],
            "errors": errors or [],
        }

    # 1️⃣ Exists check (canonical output)
    if not file_path.exists():
        result = _blank_result(
            p=str(file_path),
            status="failed",
            errors=["file does not exist"],
        )
        typer.echo(json.dumps(result, indent=2))
        raise typer.Exit(code=1)

    # 2️⃣ Is file check (canonical output)
    if not file_path.is_file():
        result = _blank_result(
            p=str(file_path),
            status="failed",
            errors=["path is not a file"],
        )
        typer.echo(json.dumps(result, indent=2))
        raise typer.Exit(code=1)

    # 3️⃣ Core verification (assumed to return dict-ish)
    verifier_result = verify_audio(str(file_path))
    data = _to_jsonable(verifier_result) or {}

    result = normalize_verification(
        status=data.get("status"),
        path=str(file_path),
        metrics=data.get("metrics"),
        warnings=data.get("warnings"),
        errors=data.get("errors"),
    )

    # strict mode treats warnings as failures for human-visible JSON
    if strict and result["status"] == "warning":
        result["ok"] = False

    typer.echo(json.dumps(result, indent=2))

    status = result["status"]

    if status == "ok":
        raise typer.Exit(code=0)

    if status == "warning":
        raise typer.Exit(code=1 if strict else 2)

    raise typer.Exit(code=1)



