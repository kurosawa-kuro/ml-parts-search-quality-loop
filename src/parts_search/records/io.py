"""JSON / JSONL の読込入口。**未対応 schema_version を拒否する。**

後続 CLI（T2〜T8）はここを共通で使う。各工程が自前で `json.load` すると、
version 検査が抜けた経路が必ず 1 本できる。

`docs/05_data_model.md`「全成果物に schema_version を付ける」に対応。
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from itertools import islice
from pathlib import Path
from typing import Any

from parts_search.errors import FoundationError, io_error
from parts_search.records.contracts import SCHEMA_VERSION
from parts_search.records.validate import validate
from parts_search.runstore import verify_run

MAX_BYTES = 256 * 1024 * 1024


def _check_version(value: Any, where: str) -> None:
    if value != SCHEMA_VERSION:
        # 値をそのまま出さない（外部由来の文字列を公開エラーへ載せない）
        raise FoundationError(f"Unsupported schema_version in {where}")


def read_json(path: Path) -> dict:
    """メタデータ JSON を読む。`schema_version` を必ず検査する。"""
    try:
        if path.stat().st_size > MAX_BYTES:
            raise FoundationError("JSON document exceeds size limit")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise FoundationError("Cannot read a valid JSON document") from error
    if not isinstance(data, dict):
        raise FoundationError("JSON document must be an object")
    _check_version(data.get("schema_version"), "document")
    return data


def iter_jsonl(path: Path, *, max_bytes: int | None = MAX_BYTES) -> Iterator[dict]:
    """JSONL を 1 行ずつ返す。

    **空ファイルは 0 件として正常に返す**（0 件は結果であり、失敗ではない）。
    行に `schema_version` があれば検査する。無い行は許す — レコード契約は
    行ごとに version を要求せず、同梱 manifest 側で持つ形もあるため。

    `.jsonl.gz` は透過的に展開する。圧縮は保存形の差であって契約の差ではない。
    `max_bytes` は**ディスク上のサイズ**に対する上限（展開後ではない）。
    """
    try:
        if max_bytes is not None and path.stat().st_size > max_bytes:
            raise FoundationError("JSONL document exceeds size limit")
        opener = gzip.open if path.name.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError as error:
                    raise FoundationError(f"Invalid JSONL at line {number}") from error
                if not isinstance(row, dict):
                    raise FoundationError(f"JSONL line {number} must be an object")
                if "schema_version" in row:
                    _check_version(row["schema_version"], f"line {number}")
                yield row
    except OSError as error:
        raise io_error("Cannot read a valid JSONL document", error) from error


def read_records(name: str, path: Path) -> list[dict]:
    """JSONL を読み、契約違反があれば**読込の段で**失敗させる。

    「読めたが中身が壊れている」データを下流へ流さない。
    後段で気付くと、どこで壊れたかの切り分けに時間がかかる。
    """
    rows = list(iter_jsonl(path))
    issues = validate(name, rows)
    if issues:
        raise FoundationError(
            f"{name} records violate the contract ({len(issues)} issue(s); first: {issues[0]})"
        )
    return rows


def iter_judgments(artifact: Path, *, batch_size: int = 10000) -> Iterator[dict]:
    """Read a verified GT artifact without materializing its Cartesian product.

    The consumer must exhaust the iterator to check the final row count. T2 writes
    strictly increasing (gt_id, query_id, product_id), permitting global duplicate
    detection across batch boundaries with constant memory.
    """
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise FoundationError("Judgment batch size must be a positive integer")
    manifest = read_json(artifact / "manifest.json")
    verify_run(artifact)
    metadata = manifest.get("metadata", {})
    if metadata.get("stage") != "judgments" or metadata.get("implemented") is not True:
        raise FoundationError("Expected an implemented judgments artifact")
    summary = read_json(artifact / "summary.json")
    rows = iter_jsonl(artifact / "judgments.jsonl.gz", max_bytes=None)
    previous = None
    count = 0
    while batch := list(islice(rows, batch_size)):
        issues = validate("Judgment", batch)
        if issues:
            raise FoundationError(f"Judgment contract violation: {issues[0]}")
        for row in batch:
            key = (row["gt_id"], row["query_id"], row["product_id"])
            if row["gt_id"] != metadata.get("gt_id") or (previous is not None and key <= previous):
                raise FoundationError(
                    "Judgment identity is duplicated, unordered or uses wrong gt_id"
                )
            previous = key
            count += 1
            yield row
    if count != summary.get("rows") or count != summary.get("expected_rows"):
        raise FoundationError("Judgment row count does not match complete Cartesian coverage")
