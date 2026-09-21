"""Exercise local config → snapshot → manifest → verification without ML or network."""

from __future__ import annotations

import platform
import subprocess
from importlib.metadata import version
from pathlib import Path

from parts_search_quality_loop.artifacts.store import checksum, new_run_id, publish_run
from parts_search_quality_loop.config.loader import STAGES, Settings


def provenance(root: Path) -> dict:
    def git(*args):
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    try:
        revision = git("rev-parse", "HEAD")
        status = git("status", "--porcelain")
    except (OSError, subprocess.TimeoutExpired):
        revision, status = None, None
    paths = sorted((root / "src").rglob("*.py")) + [root / "pyproject.toml", root / "uv.lock"]
    files = {str(p.relative_to(root)): checksum(p.read_bytes()) for p in paths if p.is_file()}
    return {
        "code_revision": revision,
        "dirty": bool(status) if status is not None else None,
        "source_checksums": files,
        "python_version": platform.python_version(),
        "dependencies": {name: version(name) for name in ("PyYAML", "jsonschema")},
        "scope": "foundation_only; source checksums do not archive uncommitted code",
    }


def run_bootstrap(settings: Settings, run_id: str | None = None) -> Path:
    report = {
        "kind": "foundation_bootstrap",
        "ml_executed": False,
        "blockers": {stage: settings.blockers(stage) for stage in STAGES},
    }
    return publish_run(
        settings.artifacts_root / "runs",
        run_id or new_run_id(),
        {"config.json": settings.public_snapshot(), "readiness.json": report},
        {"kind": "foundation_bootstrap", "provenance": provenance(settings.root)},
    )
