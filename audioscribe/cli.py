from __future__ import annotations

import typer

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
)

app = typer.Typer()
app.info.help = "AudioScribe CLI (skeleton)."


@app.command("version")
def version_cmd():
    """Print version info."""
    typer.echo("AudioScribe CLI — v0.0 (skeleton)")


@app.command("ingest")
def ingest_cmd(urls: list[str]):
    """Ingest URLs (placeholder)."""
    job_id = create_job(urls)
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