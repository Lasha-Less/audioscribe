from __future__ import annotations
from pathlib import Path
import typer
import json

from audioscribe.core.ingest import ingest as core_ingest
from audioscribe.core.verification_schema import normalize_verification
from audioscribe.core.verify_audio import verify_audio
from dataclasses import asdict, is_dataclass
from enum import Enum

app = typer.Typer()
app.info.help = "AudioScribe CLI."


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
    output_dir: str = typer.Option(
        "outputs",
        "--output-dir",
        help="Directory where audio files are saved.",
    ),
):
    """Ingest URLs."""
    result = core_ingest(
        inputs=urls,
        output_dir=output_dir,
        allow_playlist=allow_playlist,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result.get("job_id"):
        print(f"job_id={result['job_id']}")
    raise typer.Exit(code=0 if result.get("ok") else 1)


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



