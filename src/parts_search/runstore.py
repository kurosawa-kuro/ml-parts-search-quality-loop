"""Immutable local foundation runs, staged before atomic directory publication."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from parts_search.errors import FoundationError


def new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _name(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise FoundationError("Invalid artifact identifier")


def _json_bytes(value) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def publish_run(runs: Path, run_id: str, outputs: dict, metadata: dict) -> Path:
    _name(run_id)
    if not outputs or "manifest.json" in outputs:
        raise FoundationError("Run requires outputs and reserves manifest.json")
    for name in outputs:
        _name(name)
        if not name.endswith((".json", ".jsonl")):
            raise FoundationError("Only JSON/JSONL outputs are supported")
    stage = None
    lock = None
    acquired = False
    try:
        runs.mkdir(parents=True, exist_ok=True)
        destination = runs / run_id
        lock = runs / f".{run_id}.lock"
        # Exclusive reservation avoids racing publishers and overwriting completed runs.
        lock.mkdir()
        acquired = True
        if destination.exists():
            raise FoundationError("Run already exists")
        stage = Path(tempfile.mkdtemp(prefix=f".{run_id}-", dir=runs))
        hashes = {}
        for name, data in outputs.items():
            if name.endswith(".jsonl"):
                if not isinstance(data, list):
                    raise FoundationError("JSONL output requires a list of records")
                raw = b"".join(
                    (
                        json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
                    ).encode()
                    for row in data
                )
            else:
                raw = _json_bytes(data)
            (stage / name).write_bytes(raw)
            hashes[name] = checksum(raw)
        manifest = dict(
            schema_version=1,
            run_id=run_id,
            status="succeeded",
            created_at=datetime.now(UTC).isoformat(),
            outputs=hashes,
            metadata=metadata,
        )
        (stage / "manifest.json").write_bytes(_json_bytes(manifest))
        verify_run(stage)
        stage.rename(destination)
        return destination
    except (OSError, ValueError, TypeError):
        raise FoundationError("Cannot publish run; no completed run was replaced") from None
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        if acquired and lock is not None:
            lock.rmdir()


def verify_run(path: Path) -> dict:
    try:
        manifest_path = path / "manifest.json"
        if manifest_path.is_symlink():
            raise FoundationError("Manifest must be a regular local file")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or manifest.get("status") != "succeeded"
        ):
            raise FoundationError("Unsupported or incomplete run manifest")
        _name(manifest["run_id"])
        outputs = manifest["outputs"]
        if not isinstance(outputs, dict) or not outputs or "manifest.json" in outputs:
            raise FoundationError("Invalid run output inventory")
        if {p.name for p in path.iterdir()} != set(outputs) | {"manifest.json"}:
            raise FoundationError("Run inventory does not match files")
        for name, expected in outputs.items():
            _name(name)
            target = path / name
            if target.is_symlink() or not target.is_file():
                raise FoundationError("Artifact must be a regular local file")
            if not isinstance(expected, str) or not re.fullmatch("[a-f0-9]{64}", expected):
                raise FoundationError("Invalid artifact checksum")
            if checksum(target.read_bytes()) != expected:
                raise FoundationError("Artifact checksum mismatch")
        return manifest
    except (OSError, ValueError, KeyError, TypeError):
        raise FoundationError("Cannot verify run artifact") from None
