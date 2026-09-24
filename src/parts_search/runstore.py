"""Immutable local foundation runs, staged before atomic directory publication."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
import tempfile
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from parts_search.errors import FoundationError, io_error


def new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_checksum(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


# JSONL は `.gz` 付きでも同じ 1 行 1 レコード。完全な GT を全行残したまま
# 容量を落とすための表現差でしかないので、読み書きの契約は変えない。
JSONL_SUFFIXES = (".jsonl", ".jsonl.gz")


class _Digested:
    """書いたバイト列そのものの checksum を取る中継。

    書き終えたファイルを読み直して checksum を作ると、`verify_run` の照合が
    同じバイト列同士の比較になり、**書き込み途中の切断を検出できなくなる**。
    """

    def __init__(self, handle) -> None:
        self._handle = handle
        self.digest = hashlib.sha256()

    def write(self, data: bytes) -> int:
        self.digest.update(data)
        return self._handle.write(data)

    def flush(self) -> None:
        self._handle.flush()


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
        if not name.endswith((".json", *JSONL_SUFFIXES)):
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
        # JSONL を先に書く。generator 出力は消費し終えるまで集計が確定しないため、
        # 集計の受け皿である `.json` は必ずその後で直列化する
        # （呼び出し側の dict の並び順に正しさを依存させない）。
        for name in sorted(outputs, key=lambda item: not item.endswith(JSONL_SUFFIXES)):
            data = outputs[name]
            if name.endswith(JSONL_SUFFIXES):
                if not isinstance(data, Iterable) or isinstance(data, (str, bytes, dict)):
                    raise FoundationError("JSONL output requires an iterable of records")
                with (stage / name).open("wb") as handle:
                    sink = _Digested(handle)
                    # mtime=0 — 同じ内容なら同じ checksum にする（run 間で比較可能）。
                    stream = (
                        gzip.GzipFile(fileobj=sink, mode="wb", compresslevel=6, mtime=0)
                        if name.endswith(".gz")
                        else sink
                    )
                    try:
                        for row in data:
                            if not isinstance(row, dict):
                                raise FoundationError("JSONL record must be an object")
                            stream.write(
                                (
                                    json.dumps(
                                        row, ensure_ascii=False, sort_keys=True, allow_nan=False
                                    )
                                    + "\n"
                                ).encode("utf-8")
                            )
                    finally:
                        if stream is not sink:
                            stream.close()
                hashes[name] = sink.digest.hexdigest()
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
    except OSError as error:
        raise io_error("Cannot publish run; no completed run was replaced", error) from error
    except (ValueError, TypeError) as error:
        raise FoundationError(
            "Cannot publish run; a record could not be serialized and no completed run was replaced"
        ) from error
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        if acquired and lock is not None:
            lock.rmdir()


def verify_run(path: Path) -> dict:
    try:
        manifest_path = path / "manifest.json"
        if manifest_path.is_symlink():
            raise FoundationError(
                "Manifest must be a regular local file", code="INCOMPATIBLE_ARTIFACT"
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or manifest.get("status") != "succeeded"
        ):
            raise FoundationError(
                "Unsupported or incomplete run manifest", code="INCOMPATIBLE_ARTIFACT"
            )
        _name(manifest["run_id"])
        outputs = manifest["outputs"]
        if not isinstance(outputs, dict) or not outputs or "manifest.json" in outputs:
            raise FoundationError("Invalid run output inventory", code="INCOMPATIBLE_ARTIFACT")
        if {p.name for p in path.iterdir()} != set(outputs) | {"manifest.json"}:
            raise FoundationError(
                "Run inventory does not match files", code="INCOMPATIBLE_ARTIFACT"
            )
        for name, expected in outputs.items():
            _name(name)
            target = path / name
            if target.is_symlink() or not target.is_file():
                raise FoundationError(
                    "Artifact must be a regular local file", code="INCOMPATIBLE_ARTIFACT"
                )
            if not isinstance(expected, str) or not re.fullmatch("[a-f0-9]{64}", expected):
                raise FoundationError("Invalid artifact checksum", code="INCOMPATIBLE_ARTIFACT")
            if file_checksum(target) != expected:
                raise FoundationError("Artifact checksum mismatch", code="INCOMPATIBLE_ARTIFACT")
        return manifest
    except OSError as error:
        raise io_error("Cannot verify run artifact", error) from error
    except (ValueError, KeyError, TypeError) as error:
        raise FoundationError(
            "Cannot verify run artifact; the manifest is unreadable or inconsistent",
            code="INCOMPATIBLE_ARTIFACT",
        ) from error
