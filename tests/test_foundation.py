from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from parts_search_quality_loop.artifacts.store import publish_run, verify_run
from parts_search_quality_loop.config.loader import load_secret, load_settings
from parts_search_quality_loop.errors import FoundationError

REPO = Path(__file__).resolve().parents[1]


class FoundationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / "env").mkdir()
        self.config = yaml.safe_load((REPO / "env/config.yaml").read_text())
        self.project = dict(
            schemaVersion=1,
            projectName=self.config["projectName"],
            repoRoot=str(self.root),
            workspaceRoot=str(self.root.parent),
            homeDir=str(self.root.parent),
        )
        self.write()

    def write(self):
        for name, data in [("config", self.config), ("project", self.project)]:
            (self.root / f"env/{name}.yaml").write_text(yaml.safe_dump(data))

    def settings(self):
        return load_settings(self.root / "env/project.yaml", self.root / "env/config.yaml")

    def test_config_paths_and_readiness(self):
        s = self.settings()
        self.assertEqual(s.artifacts_root, self.root / "artifacts")
        self.assertIn("retrieval.embedding.revision", s.blockers("retrieval"))
        self.assertEqual(s.blockers("foundation"), [])

    def test_rejects_invalid_config(self):
        original = copy.deepcopy(self.config)
        for path, value in [
            ("split.ratios.train", 0.9),
            ("ranker.labelGain", [0, 1, 2]),
            ("retrieval.candidateLimit", 10),
            ("paths.artifacts", "../outside"),
            ("catalog.typo", 1),
            ("catalog.skuCount", True),
        ]:
            with self.subTest(path=path):
                self.config = copy.deepcopy(original)
                target = self.config
                parts = path.split(".")
                for part in parts[:-1]:
                    target = target[part]
                target[parts[-1]] = value
                self.write()
                with self.assertRaises(FoundationError):
                    self.settings()

    def test_duplicate_keys_and_safe_error(self):
        (self.root / "env/config.yaml").write_text("schemaVersion: 1\nschemaVersion: CANARY\n")
        with self.assertRaises(FoundationError) as error:
            self.settings()
        self.assertNotIn("CANARY", str(error.exception))

    def test_secret_is_separate_and_redacted(self):
        secret = self.root / "env/secret.yaml"
        secret.write_text("schemaVersion: 1\nDB_QDRANT_API_KEY: CANARY_SECRET\n")
        self.assertEqual(load_secret(secret).qdrant_api_key, "CANARY_SECRET")
        self.assertNotIn("CANARY_SECRET", repr(load_secret(secret)))
        self.assertNotIn("CANARY_SECRET", json.dumps(self.settings().public_snapshot()))
        secret.write_text("schemaVersion: 1\nDB_QDRANT_API_KEY: [CANARY_SECRET]\n")
        with self.assertRaises(FoundationError) as error:
            load_secret(secret)
        self.assertNotIn("CANARY_SECRET", str(error.exception))

    def test_paths_reject_symlink_escape(self):
        outside = self.root.parent / (self.root.name + "-outside")
        (self.root / "artifacts").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(FoundationError):
            self.settings()

    def test_jsonl_and_unexpected_file(self):
        path = publish_run(
            self.root / "runs", "jsonl-run", {"events.jsonl": [{"id": "a"}, {"id": "b"}]}, {}
        )
        rows = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
        self.assertEqual(rows, [{"id": "a"}, {"id": "b"}])
        verify_run(path)
        (path / "unexpected.json").write_text("{}")
        with self.assertRaises(FoundationError):
            verify_run(path)

    def test_missing_optional_secret(self):
        self.assertIsNone(load_secret(self.root / "absent.yaml").qdrant_api_key)

    def test_publish_verify_and_tamper(self):
        runs = self.root / "runs"
        path = publish_run(runs, "run-1", {"report.json": {"ok": True}}, {"kind": "test"})
        self.assertEqual(verify_run(path)["run_id"], "run-1")
        with self.assertRaises(FoundationError):
            publish_run(runs, "run-1", {"report.json": {}}, {})
        (path / "report.json").write_text("{}")
        with self.assertRaises(FoundationError):
            verify_run(path)

    def test_failed_serialization_is_not_published(self):
        runs = self.root / "runs"
        with self.assertRaises(FoundationError):
            publish_run(runs, "broken", {"bad.json": {"x": float("nan")}}, {})
        self.assertFalse((runs / "broken").exists())
        self.assertEqual(list(runs.iterdir()), [])

    def test_rejects_paths_and_manifest_override(self):
        for name in ["../escape", "nested/name", ".hidden"]:
            with self.subTest(name=name), self.assertRaises(FoundationError):
                publish_run(self.root / "runs", name, {"x.json": {}}, {})
        with self.assertRaises(FoundationError):
            publish_run(self.root / "runs", "safe", {"manifest.json": {}}, {})

    def test_cli_bootstrap_and_unready_stage(self):
        cmd = [
            sys.executable,
            "-m",
            "parts_search_quality_loop",
            "--project",
            str(self.root / "env/project.yaml"),
            "--config",
            str(self.root / "env/config.yaml"),
        ]
        env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
        (self.root / "env/secret.yaml").write_text(
            "schemaVersion: 1\nDB_QDRANT_API_KEY: CANARY_SECRET\n"
        )
        result = subprocess.run(cmd + ["bootstrap"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        manifest = verify_run(Path(report["run_dir"]))
        self.assertEqual(manifest["metadata"]["kind"], "foundation_bootstrap")
        self.assertNotIn("metrics.json", manifest["outputs"])
        for artifact in Path(report["run_dir"]).iterdir():
            self.assertNotIn("CANARY_SECRET", artifact.read_text())
        result = subprocess.run(
            cmd + ["config-check", "--stage", "retrieval"], env=env, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ready"])


if __name__ == "__main__":
    unittest.main()
