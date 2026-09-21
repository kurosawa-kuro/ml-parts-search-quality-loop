"""骨組みが「緑に見えない」ことを検査する。

ここで守るのは機能ではなく**誤読の防止**。
未実装や設定未確定が、成功・0 件・完了として読めてしまう経路を塞ぐ。
"""

from __future__ import annotations

import copy
import json
import logging
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from parts_search.config.loader import load_settings
from parts_search.errors import FoundationError
from parts_search.pipelines.skeleton import BLOCKED, SKELETON, run_pipeline, run_stage
from parts_search.pipelines.stages import STAGE_NAMES, STAGES, stage_by_name
from parts_search.records import RECORD_NAMES

REPO = Path(__file__).resolve().parents[1]


class SkeletonTest(unittest.TestCase):
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
        # ライブラリ側のログは stderr へ出る。テスト出力を汚さないよう黙らせる。
        logging.getLogger("parts_search").addHandler(logging.NullHandler())
        logging.getLogger("parts_search").setLevel(logging.CRITICAL)
        self.addCleanup(logging.getLogger("parts_search").handlers.clear)

    def write(self):
        for name, data in [("config", self.config), ("project", self.project)]:
            (self.root / f"env/{name}.yaml").write_text(yaml.safe_dump(data))

    def settings(self):
        self.write()
        return load_settings(self.root / "env/project.yaml", self.root / "env/config.yaml")

    # --- 段階定義 ---

    def test_stage_names_are_unique_and_ordered_by_task(self):
        self.assertEqual(len(set(STAGE_NAMES)), len(STAGE_NAMES))
        tasks = [int(stage.task[1:]) for stage in STAGES]
        self.assertEqual(tasks, sorted(tasks), "段階は T1→T8 の依存順に並ぶ")

    def test_unknown_stage_is_rejected(self):
        with self.assertRaises(FoundationError):
            stage_by_name("no_such_stage")

    def test_every_output_is_json_or_jsonl(self):
        for stage in STAGES:
            self.assertTrue(stage.outputs, f"{stage.name} は成果物を宣言する")
            for name in stage.outputs:
                self.assertTrue(name.endswith((".json", ".jsonl")), name)

    def test_placeholder_reflects_declared_implementation(self):
        """未実装の段階が implemented=True を主張しないこと。

        実装済み段階（現在は contracts）だけが True。ここが緩むと、
        骨組みの成果物が実装済みに見える。
        """
        unimplemented = [s for s in STAGES if not s.implemented]
        self.assertTrue(unimplemented, "全段階が実装済みならこの test は不要になる")
        for stage in unimplemented:
            self.assertIs(stage.placeholder()["implemented"], False, stage.name)
        for stage in STAGES:
            self.assertIs(stage.placeholder()["implemented"], stage.implemented, stage.name)

    # --- blocked の扱い ---

    def test_blocked_stage_writes_no_artifact(self):
        """設定未確定の段階が成果物を publish すると manifest の成功表示が嘘になる。

        現在の config は埋まっているので、**この test が未設定を作って**検査する。
        """
        self.config["retrieval"]["embedding"]["modelId"] = None
        result = run_stage(self.settings(), "retrieval")
        self.assertEqual(result["status"], BLOCKED)
        self.assertIsNone(result["artifact"])
        self.assertIn("retrieval.embedding.modelId", result["blockers"])
        self.assertFalse((self.root / "artifacts/runs").exists())

    def test_stage_runs_once_configuration_is_filled(self):
        result = run_stage(self.settings(), "catalog")
        self.assertEqual(result["status"], SKELETON)
        published = Path(str(result["artifact"]))
        self.assertTrue((published / "manifest.json").is_file())
        manifest = json.loads((published / "manifest.json").read_text())
        self.assertIs(manifest["metadata"]["implemented"], False)
        self.assertEqual(manifest["metadata"]["evidence_level"], 1)

    def test_empty_jsonl_is_not_presented_as_a_result(self):
        """0 件の JSONL だけを見て「結果が空だった」と読めてはいけない。"""
        result = run_stage(self.settings(), "catalog")
        published = Path(str(result["artifact"]))
        self.assertEqual((published / "catalog.jsonl").read_bytes(), b"")
        payload = json.loads((published / "splits.json").read_text())
        self.assertIs(payload["implemented"], False)

    # --- pipeline 全体 ---

    def test_pipeline_is_not_complete_while_stages_are_unimplemented(self):
        """未実装が 1 つでも残るあいだ golden_path_complete は False。

        「全段階が走った」ことを達成と読み替えさせない。
        """
        result = run_pipeline(self.settings())
        self.assertEqual(len(result["stages"]), len(STAGES))
        self.assertIs(result["golden_path_complete"], False)
        declared = [s.name for s in STAGES if s.implemented]
        self.assertEqual(result["implemented_stages"], declared)
        self.assertLess(len(declared), len(STAGES), "まだ未実装の段階が残っている")

    def test_implemented_stage_reports_completed_with_real_output(self):
        """実装済み段階は placeholder ではなく実処理の成果物を出す。"""
        result = run_stage(self.settings(), "contracts")
        self.assertEqual(result["status"], "completed")
        self.assertIs(result["implemented"], True)
        payload = json.loads((Path(str(result["artifact"])) / "contracts.json").read_text())
        self.assertIs(payload["implemented"], True)
        self.assertEqual(payload["record_count"], len(RECORD_NAMES))
        self.assertIn("identity uniqueness", payload["set_level_checks"])

    def test_pipeline_reports_unresolved_configuration(self):
        """未設定を作れば該当段階が blocked として並ぶ。"""
        self.config["qualityGate"]["policyId"] = None
        result = run_pipeline(self.settings())
        self.assertIn("gate", result["blocked_stages"])
        self.assertIn("release", result["blocked_stages"], "release も qualityGate に依存する")

    def test_simulation_is_blocked_until_enabled(self):
        """simulation は enabled=false のあいだ blocked。設定で有効化できる。"""
        self.assertIn("simulation", run_pipeline(self.settings())["blocked_stages"])
        self.config["simulation"]["enabled"] = True
        self.assertNotIn("simulation", run_pipeline(self.settings())["blocked_stages"])

    def test_stop_on_block_halts_at_first_blocker(self):
        self.config["catalog"]["attributePolicyId"] = None
        result = run_pipeline(self.settings(), stop_on_block=True)
        self.assertLess(len(result["stages"]), len(STAGES))
        self.assertEqual(result["stages"][-1]["status"], BLOCKED)

    # --- CLI 終了コード ---

    def cli(self, *argv):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "parts_search",
                "--project",
                str(self.root / "env/project.yaml"),
                "--config",
                str(self.root / "env/config.yaml"),
                *argv,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=REPO,
        )

    def test_cli_pipeline_does_not_exit_zero(self):
        """骨組みの完走が 0 を返すと CI と人間が「通った」と誤読する。

        simulation が enabled=false のため blocked（=2）。仮に全段階が ready でも
        実装が無いので 3 が返り、どちらにしても 0 にはならない。
        """
        completed = self.cli("pipeline")
        self.assertIn(completed.returncode, (2, 3), completed.stderr)
        self.assertNotEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertIs(payload["golden_path_complete"], False)

    def test_cli_stage_exit_three_when_only_skeleton(self):
        completed = self.cli("stage", "contracts")
        self.assertEqual(completed.returncode, 3, "実装が無いので skeleton=3")

    def test_cli_stages_inventory_is_honest(self):
        completed = self.cli("stages")
        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["implemented_count"], 0)
        self.assertTrue(all(s["implemented"] is False for s in payload["stages"]))

    def test_cli_logs_go_to_stderr_so_stdout_stays_json(self):
        completed = self.cli("stage", "contracts")
        json.loads(completed.stdout)  # 混在していれば例外になる
        self.assertIn("stage=contracts", completed.stderr)

    def test_config_snapshot_is_not_mutated_by_stage_run(self):
        settings = self.settings()
        before = copy.deepcopy(settings.public_snapshot())
        run_stage(settings, "contracts")
        self.assertEqual(settings.public_snapshot(), before)


if __name__ == "__main__":
    unittest.main()
