"""Delete artifact runs that exceed the configured retention.

`publish_run` は呼ばない。公開は不変のままで、消す判断はこのコマンドだけが行う。
active.json が指す release と、rollback が戻る直前の release、およびそれらの
manifest が参照する入力 run は保持本数に関わらず残す。
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from parts_search.config.schema import ARTIFACT_GROUPS
from parts_search.errors import FoundationError, io_error

# 参照の形は 2 つ。reference() は path、judgments の入力は artifact。
# どちらも manifest_checksum と組のときだけ成果物参照として辿る。
_LOCATION_KEYS = ("path", "artifact")


@dataclass(frozen=True)
class _Run:
    group: str
    run_id: str
    path: Path
    created_at: str


def prune_artifacts(
    artifacts_root: Path,
    active_path: Path,
    keep: int,
    group_keep: dict[str, int] | None = None,
) -> dict:
    """Drop the oldest runs in each group once `keep` newest runs are retained.

    Pinned runs (the active release, its rollback target, and their inputs)
    stay even when they are older than the retention window.
    """
    if keep < 1:
        raise FoundationError("Retention keep must be at least 1")
    overrides = dict(group_keep or {})
    unknown = set(overrides) - set(ARTIFACT_GROUPS)
    if unknown or any(value < 1 for value in overrides.values()):
        raise FoundationError("Retention group override is invalid")
    limits = {group: overrides.get(group, keep) for group in ARTIFACT_GROUPS}
    pinned, missing = _pinned_runs(artifacts_root, active_path)
    deleted: list[dict] = []
    skipped: list[dict] = []
    try:
        for group in ARTIFACT_GROUPS:
            group_dir = artifacts_root / group
            if not group_dir.exists():
                continue
            runs, group_skipped = _runs(group, group_dir)
            skipped.extend(group_skipped)
            newest = sorted(runs, key=lambda run: (run.created_at, run.run_id), reverse=True)
            retained = {run.path for run in newest[: limits[group]]}
            for run in newest:
                if run.path in retained or run.path in pinned:
                    continue
                freed = _byte_size(run.path)
                if run.path.is_symlink() or not run.path.resolve().is_relative_to(artifacts_root):
                    raise FoundationError("Refusing to delete a run outside artifacts")
                shutil.rmtree(run.path)
                deleted.append({"group": group, "run_id": run.run_id, "bytes": freed})
    except OSError as error:
        raise io_error(f"Prune stopped after deleting {len(deleted)} runs", error) from error
    return {
        "schema_version": 1,
        "keep": {"default": keep, "groups": limits},
        "deleted": deleted,
        "freed_bytes": sum(item["bytes"] for item in deleted),
        "pinned": [
            {"group": path.parent.name, "run_id": path.name}
            for path in sorted(pinned, key=lambda item: (item.parent.name, item.name))
        ],
        "missing_pins": missing,
        "skipped": skipped,
    }


def _pinned_runs(artifacts_root: Path, active_path: Path) -> tuple[set[Path], list[str]]:
    """Active release, the single rollback target, and every run those manifests name."""
    if not active_path.exists():
        return set(), []
    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FoundationError("Cannot read active release; nothing was deleted") from error
    if not isinstance(active, dict) or not isinstance(active.get("release_path"), str):
        raise FoundationError("Cannot read active release; nothing was deleted")
    seeds: list[Path] = []
    missing: list[str] = []
    current = active.get("release_path")
    previous = active.get("previous")
    previous_path = previous.get("release_path") if isinstance(previous, dict) else None
    for location in (current, previous_path):
        if not isinstance(location, str):
            continue
        path = Path(location)
        if path.is_dir() and not path.is_symlink():
            seeds.append(path)
        else:
            missing.append(path.name)
    pinned: set[Path] = set()
    queue = list(seeds)
    while queue:
        current_path = queue.pop()
        try:
            resolved = current_path.resolve()
        except OSError as error:
            raise FoundationError("Cannot read a pinned run; nothing was deleted") from error
        if resolved in pinned or not resolved.is_relative_to(artifacts_root):
            continue
        if not resolved.is_dir() or resolved.is_symlink():
            continue
        manifest_path = resolved / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise FoundationError("Cannot read a pinned run; nothing was deleted")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise FoundationError("Cannot read a pinned run; nothing was deleted") from error
        pinned.add(resolved)
        for location in _reference_paths(manifest.get("metadata")):
            queue.append(Path(location))
    return pinned, missing


def _reference_paths(value: object) -> list[str]:
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            checksum = node.get("manifest_checksum")
            location = next(
                (node[key] for key in _LOCATION_KEYS if isinstance(node.get(key), str)),
                None,
            )
            if isinstance(location, str) and isinstance(checksum, str):
                found.append(location)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return found


def _runs(group: str, group_dir: Path) -> tuple[list[_Run], list[dict]]:
    runs: list[_Run] = []
    skipped: list[dict] = []
    try:
        children = list(group_dir.iterdir())
    except OSError as error:
        raise io_error("Cannot list artifact runs", error) from error
    for path in children:
        name = path.name
        # lock / staging は `.` 始まり。公開の残骸なので消さず、報告もしない。
        if name.startswith("."):
            continue
        if path.is_symlink():
            skipped.append({"group": group, "name": name, "reason": "symlink"})
            continue
        if not path.is_dir():
            continue
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            skipped.append({"group": group, "name": name, "reason": "missing_manifest"})
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            created_at = manifest["created_at"]
            run_id = manifest["run_id"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            skipped.append({"group": group, "name": name, "reason": "unreadable_manifest"})
            continue
        if not isinstance(created_at, str) or run_id != name:
            skipped.append({"group": group, "name": name, "reason": "unreadable_manifest"})
            continue
        runs.append(_Run(group, run_id, path.resolve(), created_at))
    return runs, skipped


def _byte_size(path: Path) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
        dirnames[:] = [name for name in dirnames if not (Path(dirpath) / name).is_symlink()]
        for name in filenames:
            target = Path(dirpath) / name
            if target.is_symlink():
                continue
            total += target.stat().st_size
    return total
