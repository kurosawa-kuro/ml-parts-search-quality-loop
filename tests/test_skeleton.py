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
from parts_search.pipelines.skeleton import BLOCKED, run_pipeline, run_stage
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
        self.config["retrieval"]["embedding"]["modelId"] = None
        self.config["catalog"]["skuCount"] = 30
        self.config["queries"]["familyCount"] = 20
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
                self.assertTrue(name.endswith((".json", ".jsonl", ".jsonl.gz")), name)

    def test_placeholder_reflects_declared_implementation(self):
        """placeholder が実装状態を偽らないこと。

        全段階が実装済みになった後も、placeholder 経路が implemented=True を
        主張しないことを守る（未実装段階を足したときに緑で通さない）。
        """
        for stage in STAGES:
            self.assertIs(stage.placeholder()["implemented"], stage.implemented, stage.name)
        for stage in STAGES:
            self.assertIn("no retrieval, training, metrics or release", stage.placeholder()["note"])

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

    def test_release_without_inputs_is_blocked_not_published(self):
        """入力が無い release を「実行した」ことにしない。"""
        result = run_stage(self.settings(), "release")
        self.assertEqual(result["status"], BLOCKED)
        self.assertIsNone(result["artifact"])
        self.assertIn("input.gate", result["blockers"])
        self.assertIn("input.simulations", result["blockers"])
        self.assertFalse((self.root / "artifacts/releases").exists())

    # --- pipeline 全体 ---

    def test_pipeline_is_not_complete_while_stages_are_unimplemented(self):
        """未実装が 1 つでも残るあいだ golden_path_complete は False。

        「全段階が走った」ことを達成と読み替えさせない。
        """
        result = run_pipeline(self.settings())
        self.assertGreaterEqual(len(result["stages"]), len(STAGES))
        self.assertIs(result["golden_path_complete"], False)
        # embedding.modelId を外してあるので retrieval 以降は blocked のまま。
        self.assertEqual(result["implemented_stages"], ["contracts", "catalog", "judgments"])
        self.assertIn("retrieval", result["blocked_stages"])

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

    def test_simulation_is_blocked_while_disabled(self):
        """enabled=false は「未実施」であって合格でも 0 でもない。"""
        self.config["simulation"]["enabled"] = False
        blockers = run_stage(self.settings(), "simulation")["blockers"]
        self.assertIn("simulation.enabled", blockers)
        self.config["simulation"]["enabled"] = True
        self.assertNotIn("simulation.enabled", run_stage(self.settings(), "simulation")["blockers"])

    def test_unversioned_simulation_policy_blocks(self):
        """版付き policy が無ければ simulation を開始しない（05）。"""
        self.config["simulation"]["policyVersion"] = None
        self.assertIn(
            "simulation.policyVersion", run_stage(self.settings(), "simulation")["blockers"]
        )

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
        self.assertIn(completed.returncode, (2, 3, 4), completed.stderr)
        self.assertNotEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertIs(payload["golden_path_complete"], False)

    def test_cli_stage_exit_two_when_inputs_are_missing(self):
        completed = self.cli("stage", "release")
        self.assertEqual(completed.returncode, 2, "入力未指定は blocked=2")

    def test_cli_completed_stage_exits_zero(self):
        completed = self.cli("stage", "contracts")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "completed")
        self.assertIs(payload["implemented"], True)

    def test_cli_catalog_to_judgments_uses_explicit_input(self):
        missing = self.cli("stage", "judgments")
        self.assertEqual(missing.returncode, 2)
        catalog = self.cli("stage", "catalog")
        self.assertEqual(catalog.returncode, 0, catalog.stderr)
        dataset = json.loads(catalog.stdout)["artifact"]
        judgments = self.cli("stage", "judgments", "--dataset", dataset)
        self.assertEqual(judgments.returncode, 0, judgments.stderr)
        path = Path(json.loads(judgments.stdout)["artifact"])
        summary = json.loads((path / "summary.json").read_text())
        self.assertEqual(summary["rows"], 1200)
        self.assertEqual(summary["status"], "complete")
        rejected = self.cli("stage", "catalog", "--dataset", dataset)
        self.assertEqual(rejected.returncode, 1)

    def test_cli_blocked_stage_exits_two_without_artifact(self):
        completed = self.cli("stage", "simulation")
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIsNone(json.loads(completed.stdout)["artifact"])

    def test_cli_stages_inventory_is_honest(self):
        completed = self.cli("stages")
        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        expected = {stage.name: stage.implemented for stage in STAGES}
        self.assertEqual(payload["implemented_count"], sum(expected.values()))
        self.assertEqual(
            {stage["stage"]: stage["implemented"] for stage in payload["stages"]}, expected
        )

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
