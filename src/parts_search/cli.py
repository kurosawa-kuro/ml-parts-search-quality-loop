"""Small argparse CLI adapted from the Python ML starter's entrypoint pattern."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from parts_search.config.loader import STAGES, load_settings
from parts_search.errors import FoundationError
from parts_search.logs import configure
from parts_search.pipelines.bootstrap import run_bootstrap
from parts_search.pipelines.release import activate as activate_release
from parts_search.pipelines.release import rollback as rollback_release
from parts_search.pipelines.skeleton import run_pipeline, run_stage
from parts_search.pipelines.stages import STAGE_NAMES
from parts_search.pipelines.stages import STAGES as PIPELINE_STAGES
from parts_search.runstore import verify_run

# 終了コード: 0=完了 / 1=入力・実行エラー / 2=設定未確定で段階が止まった /
# 3=骨組みのみ実行（実装が無い） / 4=実行は成功したが品質判定が採用にならなかった。
# **3 を成功と読み替えない。4 と 1 を混同しない**（前者は品質、後者は実行の失敗）。
EXIT_OK, EXIT_ERROR, EXIT_BLOCKED, EXIT_SKELETON, EXIT_NOT_ACCEPTED = 0, 1, 2, 3, 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local parts search quality loop")
    parser.add_argument("--project", type=Path, default=Path("env/project.yaml"))
    parser.add_argument("--config", type=Path, default=Path("env/config.yaml"))
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("config-check", help="Validate public config; never loads secrets")
    check.add_argument("--stage", choices=STAGES, default="foundation")
    bootstrap = commands.add_parser("bootstrap", help="Write a local foundation run, without ML")
    bootstrap.add_argument("--run-id")
    verify = commands.add_parser("verify-artifact", help="Verify a completed run and its checksums")
    verify.add_argument("run_dir", type=Path)
    commands.add_parser("stages", help="List Golden Path stages and their config dependencies")
    stage = commands.add_parser(
        "stage", help="Run one stage; report unimplemented stages as skeleton"
    )
    stage.add_argument("name", choices=STAGE_NAMES)
    stage.add_argument("--run-id")
    stage.add_argument("--dataset", type=Path, help="Explicit immutable catalog/query artifact")
    stage.add_argument("--judgments", type=Path)
    stage.add_argument("--search", type=Path)
    stage.add_argument("--baseline", type=Path)
    stage.add_argument("--candidate-evaluation", type=Path, action="append", dest="evaluations")
    stage.add_argument("--gate", type=Path, help="Frozen experiment artifact for release")
    stage.add_argument("--simulation", type=Path, action="append", dest="simulations")
    stage.add_argument("--release-id", help="Release whose bundle served the simulation")
    stage.add_argument("--split", help="Override the simulation split")
    stage.add_argument("--parent-experiment", dest="parent_experiment_id")
    stage.add_argument("--retry-of", dest="retry_of", help="Experiment this run retries")
    activate = commands.add_parser("activate", help="Point active.json at a promoted release")
    activate.add_argument("release", type=Path)
    commands.add_parser("rollback", help="Restore the previous active release reference")
    pipeline = commands.add_parser("pipeline", help="Run every stage in dependency order")
    pipeline.add_argument("--dataset", type=Path)
    pipeline.add_argument("--judgments", type=Path)
    pipeline.add_argument(
        "--stop-on-block", action="store_true", help="Stop at the first stage blocked by config"
    )
    return parser


def _stage_inventory() -> dict:
    return {
        "stages": [
            {
                "stage": stage.name,
                "task": stage.task,
                "config_stage": stage.config_stage,
                "artifact_group": stage.group,
                "outputs": list(stage.outputs),
                "summary": stage.summary,
                "implemented": stage.implemented,
            }
            for stage in PIPELINE_STAGES
        ],
        "implemented_count": sum(stage.implemented for stage in PIPELINE_STAGES),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "verify-artifact":
            manifest = verify_run(args.run_dir)
            output = {"verified": True, "run_id": manifest["run_id"]}
        elif args.command == "stages":
            output = _stage_inventory()
        else:
            settings = load_settings(args.project, args.config)
            if args.command == "config-check":
                blockers = settings.blockers(args.stage)
                output = {
                    "valid": True,
                    "stage": args.stage,
                    "ready": not blockers,
                    "blockers": blockers,
                    "scope": "configuration_only",
                }
                print(json.dumps(output, ensure_ascii=False, indent=2))
                return EXIT_ERROR if blockers else EXIT_OK
            if args.command in ("stage", "pipeline"):
                configure(settings.config["logLevel"])
                if args.command == "stage":
                    output = run_stage(
                        settings,
                        args.name,
                        args.run_id,
                        dataset=args.dataset,
                        judgments=args.judgments,
                        search=args.search,
                        baseline=args.baseline,
                        evaluations=args.evaluations,
                        gate=args.gate,
                        simulations=args.simulations,
                        release_id=args.release_id,
                        split=args.split,
                        parent_experiment_id=args.parent_experiment_id,
                        retry_of=args.retry_of,
                    )
                    failed = output["status"] == "failed"
                    blocked = output["status"] == "blocked"
                    completed = output["status"] == "completed"
                    not_accepted = output.get("quality") in (
                        "rejected",
                        "reject",
                        "inconclusive",
                    )
                else:
                    output = run_pipeline(
                        settings, args.stop_on_block, dataset=args.dataset, judgments=args.judgments
                    )
                    failed = bool(output["failed_stages"])
                    blocked = bool(output["blocked_stages"])
                    completed = output["golden_path_complete"]
                    not_accepted = output.get("quality") in (
                        "rejected",
                        "reject",
                        "inconclusive",
                    )
                print(json.dumps(output, ensure_ascii=False, indent=2))
                if failed:
                    return EXIT_ERROR
                if blocked:
                    return EXIT_BLOCKED
                if not_accepted:
                    # 実行は成功している。品質で採用にならなかったことを別コードで返す。
                    return EXIT_NOT_ACCEPTED
                return EXIT_OK if completed else EXIT_SKELETON
            if args.command in ("activate", "rollback"):
                active = settings.root / settings.config["paths"]["activeRelease"]
                output = (
                    activate_release(active, args.release)
                    if args.command == "activate"
                    else rollback_release(active)
                )
                print(json.dumps(output, ensure_ascii=False, indent=2))
                return EXIT_OK
            path = run_bootstrap(settings, args.run_id)
            output = {"run_dir": str(path), "ml_executed": False}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return EXIT_OK
    except FoundationError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return EXIT_ERROR
    except OSError:
        print(json.dumps({"error": "Filesystem operation failed"}), file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
