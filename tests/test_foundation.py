from __future__ import annotations

import copy
import errno
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import yaml

from parts_search.config.loader import load_secret, load_settings
from parts_search.errors import FoundationError
from parts_search.records.io import iter_jsonl
from parts_search.runstore import publish_run, verify_run

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
        self.assertEqual(s.blockers("foundation"), [])

    def test_blockers_report_missing_values_not_current_config(self):
        """blocker 機構そのものを検査する。

        リポジトリの config が埋まった瞬間に壊れる書き方（現在値への依存）をしない。
        未設定を**この test が作って**報告されることを確かめる。
        """
        self.assertEqual(self.settings().blockers("retrieval"), [])
        self.config["retrieval"]["embedding"]["revision"] = None
        self.write()  # settings() は読むだけ。変更は書き出してから読み直す
        self.assertIn("retrieval.embedding.revision", self.settings().blockers("retrieval"))

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

    def test_disk_full_is_reported_as_disk_full(self):
        """失敗の原因を 1 つの文言へ丸めない。

        ENOSPC を "Cannot publish run" だけで返すと、容量不足なのか入力不正なのかを
        運用側で切り分けられない（`docs/06_error_policy.md` の分類）。
        """
        runs = self.root / "runs"
        full = OSError(errno.ENOSPC, "No space left on device")
        with unittest.mock.patch.object(Path, "write_bytes", side_effect=full):
            with self.assertRaises(FoundationError) as error:
                publish_run(runs, "full", {"report.json": {"ok": True}}, {})
        self.assertEqual("ARTIFACT_IO", error.exception.code)
        self.assertIn("ENOSPC", str(error.exception))
        self.assertFalse((runs / "full").exists())

    def test_serialization_failure_is_not_reported_as_io(self):
        """入力不正を I/O 障害と同じコードで返さない。"""
        with self.assertRaises(FoundationError) as error:
            publish_run(self.root / "runs", "broken", {"bad.json": {"x": float("nan")}}, {})
        self.assertEqual("INVALID_INPUT", error.exception.code)

    def test_jsonl_rows_reach_disk_before_the_generator_finishes(self):
        """全件をメモリへ溜めない。generator を逐次消費して書く。

        list へ materialize すると 2,000 万行の GT で数 GB を抱える。
        """
        runs = self.root / "runs"
        sizes = []
        padding = "x" * 200_000

        def rows():
            for index in range(3):
                yield {"id": index, "pad": padding}
                stage = next(iter(runs.glob(".stream-*")), None)
                sizes.append((stage / "events.jsonl").stat().st_size if stage else 0)

        publish_run(runs, "stream", {"events.jsonl": rows()}, {})
        self.assertTrue(all(size > 0 for size in sizes), sizes)

    def test_json_outputs_are_written_after_jsonl_generators(self):
        """generator が埋める集計を、確定前に直列化しない（宣言順に依存させない）。"""
        stats = {"rows": 0}

        def rows():
            for index in range(3):
                stats["rows"] += 1
                yield {"id": index}

        path = publish_run(
            self.root / "runs", "order", {"summary.json": stats, "events.jsonl": rows()}, {}
        )
        self.assertEqual(3, json.loads((path / "summary.json").read_text())["rows"])

    def test_gzip_jsonl_is_stored_compressed_and_reproducible(self):
        """完全判定 GT を全行残したまま容量を落とす。

        gzip header に時刻を入れない — 同じ内容なら同じ checksum になる。
        """
        runs = self.root / "runs"
        rows = [{"id": f"row-{index:06d}", "relevance": 0} for index in range(5000)]
        path = publish_run(runs, "gz", {"events.jsonl.gz": list(rows)}, {})
        stored = path / "events.jsonl.gz"
        self.assertLess(stored.stat().st_size, len(json.dumps(rows)) // 5)
        self.assertEqual(rows, list(iter_jsonl(stored)))
        again = publish_run(runs, "gz-again", {"events.jsonl.gz": list(rows)}, {})
        self.assertEqual(
            verify_run(path)["outputs"]["events.jsonl.gz"],
            verify_run(again)["outputs"]["events.jsonl.gz"],
        )

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
            "parts_search",
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
        # 未設定を作ってから検査する（現在の config が埋まっていても成立させる）
        self.config["retrieval"]["embedding"]["revision"] = None
        self.write()
        result = subprocess.run(
            cmd + ["config-check", "--stage", "retrieval"], env=env, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ready"])
        self.assertIn("retrieval.embedding.revision", payload["blockers"])


if __name__ == "__main__":
    unittest.main()
