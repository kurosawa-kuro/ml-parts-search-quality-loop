"""Retention prune keeps the active release graph and drops only older runs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from parts_search.config.loader import load_settings
from parts_search.errors import FoundationError
from parts_search.pipelines.prune import prune_artifacts
from parts_search.runstore import publish_run

REPO = Path(__file__).resolve().parents[1]


def _publish(root: Path, group: str, run_id: str, metadata: dict, created_at: str) -> Path:
    path = publish_run(root / group, run_id, {"note.json": {"ok": True}}, metadata)
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["created_at"] = created_at
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _ref(path: Path) -> dict:
    return {"path": str(path.resolve()), "manifest_checksum": "unchanged-for-prune"}


def _active(path: Path, release: Path, previous: dict | None = None) -> None:
    payload = {
        "schema_version": 1,
        "release_id": release.name,
        "release_path": str(release.resolve()),
        "manifest_checksum": "unchanged-for-prune",
        "previous": previous,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _ids(report: dict, group: str) -> set[str]:
    return {item["run_id"] for item in report["deleted"] if item["group"] == group}


def test_oldest_runs_are_deleted_and_bytes_are_reported(tmp_path: Path):
    root = tmp_path / "artifacts"
    created = []
    for index, stamp in enumerate(("2026-01-01", "2026-02-01", "2026-03-01")):
        path = _publish(root, "runs", f"2026010{index}T000000Z-aaaaaaaaaaa{index}", {}, stamp)
        created.append(path)
    before = sum(item.stat().st_size for item in created[0].rglob("*") if item.is_file())
    report = prune_artifacts(root, root / "active.json", keep=1)
    assert _ids(report, "runs") == {created[0].name, created[1].name}
    assert report["freed_bytes"] == before * 2
    assert created[2].is_dir()
    assert not created[0].exists()


def test_active_release_inputs_survive_even_when_older_than_retention(tmp_path: Path):
    root = tmp_path / "artifacts"
    dataset = _publish(
        root, "datasets", "20260101T000000Z-aaaaaaaaaaaa", {}, "2026-01-01T00:00:00+00:00"
    )
    other = _publish(
        root, "datasets", "20260201T000000Z-bbbbbbbbbbbb", {}, "2026-02-01T00:00:00+00:00"
    )
    newest = _publish(
        root, "datasets", "20260301T000000Z-cccccccccccc", {}, "2026-03-01T00:00:00+00:00"
    )
    judgments = _publish(
        root,
        "judgments",
        "20260102T000000Z-dddddddddddd",
        {
            "input": {
                "artifact": str(dataset.resolve()),
                "run_id": dataset.name,
                "manifest_checksum": "not-the-file-checksum",
            }
        },
        "2026-01-02T00:00:00+00:00",
    )
    release = _publish(
        root,
        "releases",
        "20260103T000000Z-eeeeeeeeeeee",
        {"gate": _ref(judgments)},
        "2026-01-03T00:00:00+00:00",
    )
    _publish(root, "releases", "20260401T000000Z-ffffffffffff", {}, "2026-04-01T00:00:00+00:00")
    active = root / "active.json"
    _active(active, release)
    report = prune_artifacts(root, active, keep=1)
    assert dataset.is_dir()
    assert judgments.is_dir()
    assert release.is_dir()
    assert newest.is_dir()
    assert not other.exists()
    assert report["freed_bytes"] > 0
    assert {item["run_id"] for item in report["pinned"]} >= {
        dataset.name,
        judgments.name,
        release.name,
    }


def test_rollback_target_is_kept_but_older_history_is_not(tmp_path: Path):
    root = tmp_path / "artifacts"
    ancient_input = _publish(
        root, "datasets", "20260101T000000Z-aaaaaaaaaaaa", {}, "2026-01-01T00:00:00+00:00"
    )
    previous_input = _publish(
        root, "datasets", "20260201T000000Z-bbbbbbbbbbbb", {}, "2026-02-01T00:00:00+00:00"
    )
    ancient = _publish(
        root,
        "releases",
        "20260101T000000Z-111111111111",
        {"dataset": _ref(ancient_input)},
        "2026-01-01T00:00:00+00:00",
    )
    previous = _publish(
        root,
        "releases",
        "20260201T000000Z-222222222222",
        {"dataset": _ref(previous_input)},
        "2026-02-01T00:00:00+00:00",
    )
    current = _publish(
        root, "releases", "20260301T000000Z-333333333333", {}, "2026-03-01T00:00:00+00:00"
    )
    active = root / "active.json"
    _active(
        active,
        current,
        previous={
            "release_id": previous.name,
            "release_path": str(previous.resolve()),
            "manifest_checksum": "x",
            "previous": {
                "release_id": ancient.name,
                "release_path": str(ancient.resolve()),
                "manifest_checksum": "y",
                "previous": None,
            },
        },
    )
    prune_artifacts(root, active, keep=1)
    assert current.is_dir() and previous.is_dir() and previous_input.is_dir()
    assert not ancient.exists()
    assert not ancient_input.exists()


def test_locks_symlinks_and_unreadable_manifests_are_not_deleted(tmp_path: Path):
    root = tmp_path / "artifacts"
    kept = _publish(root, "runs", "20260301T000000Z-aaaaaaaaaaaa", {}, "2026-03-01T00:00:00+00:00")
    lock = root / "runs" / ".20260101T000000Z-bbbbbbbbbbbb.lock"
    lock.mkdir(parents=True)
    (lock / "marker").write_text("lock", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("keep", encoding="utf-8")
    link = root / "runs" / "20260101T000000Z-cccccccccccc"
    link.symlink_to(outside, target_is_directory=True)
    broken = root / "runs" / "20260101T000000Z-dddddddddddd"
    broken.mkdir(parents=True)
    (broken / "manifest.json").write_text("{", encoding="utf-8")
    note = root / "runs" / "note.txt"
    note.write_text("not a run", encoding="utf-8")
    report = prune_artifacts(root, root / "active.json", keep=1)
    assert kept.is_dir()
    assert (lock / "marker").read_text(encoding="utf-8") == "lock"
    assert (outside / "secret").read_text(encoding="utf-8") == "keep"
    assert link.is_symlink()
    assert broken.is_dir()
    assert note.read_text(encoding="utf-8") == "not a run"
    assert report["deleted"] == []
    assert {item["reason"] for item in report["skipped"]} == {"symlink", "unreadable_manifest"}


def test_unreadable_active_release_deletes_nothing(tmp_path: Path):
    root = tmp_path / "artifacts"
    run = _publish(root, "runs", "20260101T000000Z-aaaaaaaaaaaa", {}, "2026-01-01T00:00:00+00:00")
    _publish(root, "runs", "20260301T000000Z-bbbbbbbbbbbb", {}, "2026-03-01T00:00:00+00:00")
    active = root / "active.json"
    active.write_text("not-json", encoding="utf-8")
    try:
        prune_artifacts(root, active, keep=1)
    except FoundationError as error:
        assert error.code == "INVALID_INPUT"
    else:
        raise AssertionError("expected FoundationError")
    assert run.is_dir()


def test_group_override_keeps_more_runs_than_the_default(tmp_path: Path):
    root = tmp_path / "artifacts"
    runs = [
        _publish(
            root, "runs", f"2026010{index}T000000Z-aaaaaaaaaaa{index}", {}, f"2026-01-0{index + 1}"
        )
        for index in range(3)
    ]
    models = [
        _publish(
            root,
            "models",
            f"2026010{index}T000000Z-bbbbbbbbbbb{index}",
            {},
            f"2026-01-0{index + 1}",
        )
        for index in range(3)
    ]
    report = prune_artifacts(root, root / "active.json", keep=1, group_keep={"models": 3})
    assert _ids(report, "runs") == {runs[0].name, runs[1].name}
    assert models[0].is_dir() and models[2].is_dir()
    assert report["keep"]["groups"]["models"] == 3
    assert report["keep"]["groups"]["runs"] == 1


def test_config_rejects_non_positive_retention(tmp_path: Path):
    config = yaml.safe_load((REPO / "env/config.yaml").read_text(encoding="utf-8"))
    project = {
        "schemaVersion": 1,
        "projectName": config["projectName"],
        "repoRoot": str(tmp_path),
        "workspaceRoot": str(tmp_path),
        "homeDir": str(tmp_path),
    }
    env = tmp_path / "env"
    env.mkdir()
    (env / "project.yaml").write_text(yaml.safe_dump(project), encoding="utf-8")
    config["artifacts"]["retention"]["keep"] = 0
    (env / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    try:
        load_settings(env / "project.yaml", env / "config.yaml")
    except FoundationError:
        return
    raise AssertionError("expected FoundationError")


def test_cli_prune_reports_deleted_run_ids(tmp_path: Path):
    config = yaml.safe_load((REPO / "env/config.yaml").read_text(encoding="utf-8"))
    config["artifacts"]["retention"] = {"keep": 1, "groups": {}}
    project = {
        "schemaVersion": 1,
        "projectName": config["projectName"],
        "repoRoot": str(tmp_path),
        "workspaceRoot": str(tmp_path),
        "homeDir": str(tmp_path),
    }
    env = tmp_path / "env"
    env.mkdir()
    (env / "project.yaml").write_text(yaml.safe_dump(project), encoding="utf-8")
    (env / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    old = _publish(
        tmp_path / "artifacts",
        "reports",
        "20260101T000000Z-aaaaaaaaaaaa",
        {},
        "2026-01-01T00:00:00+00:00",
    )
    new = _publish(
        tmp_path / "artifacts",
        "reports",
        "20260201T000000Z-bbbbbbbbbbbb",
        {},
        "2026-02-01T00:00:00+00:00",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "parts_search",
            "--project",
            str(env / "project.yaml"),
            "--config",
            str(env / "config.yaml"),
            "prune",
        ],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert _ids(report, "reports") == {old.name}
    assert new.is_dir()
    assert "error" not in report
