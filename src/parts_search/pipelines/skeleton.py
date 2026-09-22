"""Execute implemented stages and preserve explicit placeholders for the remainder."""

from __future__ import annotations

from pathlib import Path

from parts_search.config.loader import Settings
from parts_search.errors import FoundationError
from parts_search.logs import logger
from parts_search.pipelines.bootstrap import provenance
from parts_search.pipelines.contracts_report import build_contracts_report
from parts_search.pipelines.evaluation import build_evaluation
from parts_search.pipelines.gate import build_gate
from parts_search.pipelines.judgments import build_judgments
from parts_search.pipelines.release import build_release
from parts_search.pipelines.retrieval import build_retrieval
from parts_search.pipelines.simulation import build_simulation
from parts_search.pipelines.stages import STAGES, Stage, stage_by_name
from parts_search.pipelines.synthetic import build_dataset
from parts_search.pipelines.training import build_training
from parts_search.runstore import new_run_id, publish_run

# 段階の結果。blocked と skeleton を区別する（前者は設定待ち、後者は実装待ち）。
BLOCKED = "blocked"
SKELETON = "skeleton"
COMPLETED = "completed"

# 実装済み段階の実処理。ここに載っていない段階は placeholder のまま。
_IMPLEMENTED = {"contracts": build_contracts_report}


def _outputs(stage: Stage) -> dict[str, object]:
    """宣言された成果物を空で作る。

    JSONL は空リスト（0 件）で、JSON は placeholder。
    **0 件と未実装を混同させない**ため、payload 側に implemented=False を持たせ、
    JSONL の 0 件だけで「結果が空だった」と読めないようにする。
    """
    payload = stage.placeholder()
    return {name: ([] if name.endswith(".jsonl") else payload) for name in stage.outputs}


def run_stage(
    settings: Settings,
    name: str,
    run_id: str | None = None,
    *,
    dataset: Path | None = None,
    judgments: Path | None = None,
    search: Path | None = None,
    baseline: Path | None = None,
    evaluations: list[Path] | None = None,
    gate: Path | None = None,
    simulations: list[Path] | None = None,
    release_id: str | None = None,
    split: str | None = None,
    parent_experiment_id: str | None = None,
    retry_of: str | None = None,
) -> dict[str, object]:
    """1 段階を実行する。設定が未確定なら成果物を作らず blocked を返す。"""
    stage = stage_by_name(name)
    log = logger()
    blockers = settings.blockers(stage.config_stage)
    needs = {
        "judgments": {"dataset": dataset},
        "retrieval": {"dataset": dataset},
        "evaluation": {"dataset": dataset, "judgments": judgments, "search": search},
        "training": {"dataset": dataset, "judgments": judgments, "search": search},
        "gate": {"baseline": baseline, "evaluations": evaluations},
        "simulation": {"dataset": dataset, "judgments": judgments, "search": search},
        "release": {"gate": gate, "simulations": simulations},
    }
    for key, value in needs.get(name, {}).items():
        if not value:
            blockers.append("input." + key)
    supplied = {
        "dataset": dataset,
        "judgments": judgments,
        "search": search,
        "baseline": baseline,
        "evaluations": evaluations,
        "gate": gate,
        "simulations": simulations,
    }
    if any(value is not None and key not in needs.get(name, {}) for key, value in supplied.items()):
        raise FoundationError("Unsupported input for this stage")

    if blockers:
        # 設定が埋まっていない段階で成果物を publish すると、manifest の
        # status='succeeded' が嘘になる。publish せずに理由を返す。
        log.warning(
            "stage=%s task=%s status=%s blockers=%d", stage.name, stage.task, BLOCKED, len(blockers)
        )
        for path in blockers:
            log.info("stage=%s blocker=%s", stage.name, path)
        return {
            "stage": stage.name,
            "task": stage.task,
            "status": BLOCKED,
            "config_stage": stage.config_stage,
            "blockers": blockers,
            "artifact": None,
            "implemented": False,
        }

    identifier = run_id or new_run_id()
    destination = settings.artifacts_root / stage.group
    builder = _IMPLEMENTED.get(stage.name)
    implemented = stage.implemented
    status = COMPLETED if implemented else SKELETON
    log.info("stage=%s task=%s starting id=%s", stage.name, stage.task, identifier)
    metadata = {}
    if name == "catalog":
        outputs, metadata = build_dataset(settings.config)
    elif name == "judgments":
        outputs, metadata = build_judgments(settings.config, dataset)
    elif name == "retrieval":
        outputs, metadata = build_retrieval(settings.config, dataset, identifier)
    elif name == "evaluation":
        outputs, metadata = build_evaluation(
            settings.config, dataset, judgments, search, identifier
        )
    elif name == "training":
        outputs, metadata = build_training(settings.config, dataset, judgments, search, identifier)
    elif name == "gate":
        outputs, metadata = build_gate(
            settings.config,
            baseline,
            evaluations,
            identifier,
            parent_experiment_id=parent_experiment_id,
            retry_of=retry_of,
        )
    elif name == "simulation":
        outputs, metadata = build_simulation(
            settings.config,
            dataset,
            judgments,
            search,
            identifier,
            release_id=release_id,
            split=split,
        )
    elif name == "release":
        outputs, metadata = build_release(settings.config, gate, simulations, identifier)
    else:
        outputs = builder() if builder else _outputs(stage)
    path = publish_run(
        destination,
        identifier,
        outputs,
        {
            **metadata,
            "kind": f"{status}_{stage.name}",
            "stage": stage.name,
            "task": stage.task,
            "implemented": implemented,
            "evidence_level": 2 if implemented else 1,
            "provenance": provenance(settings.root),
        },
    )
    if metadata.get("failed_queries"):
        status = "failed"
    # 品質不採用は実行失敗ではない。CLI の終了コードを分けるため状態で持つ。
    for key in ("offline_verdict", "decision"):
        if metadata.get(key) in ("rejected", "reject", "inconclusive"):
            status = COMPLETED
    for output in stage.outputs:
        log.debug("stage=%s wrote=%s", stage.name, output)
    log.info("stage=%s status=%s id=%s", stage.name, status, identifier)
    return {
        "stage": stage.name,
        "task": stage.task,
        "status": status,
        "config_stage": stage.config_stage,
        "blockers": [],
        "artifact": str(path),
        "implemented": implemented,
        # 品質判定は実行状態と別軸。呼び出し側が終了コードを分けられるようにする。
        "quality": metadata.get("decision") or metadata.get("offline_verdict"),
    }


def run_pipeline(
    settings: Settings,
    stop_on_block: bool = False,
    *,
    dataset: Path | None = None,
    judgments: Path | None = None,
) -> dict[str, object]:
    """Execute dependency order, optionally reusing immutable T2 input snapshots."""
    results = []
    artifacts = {"catalog": dataset, "judgments": judgments}
    for stage in STAGES:
        if stage.name in ("catalog", "judgments") and artifacts.get(stage.name):
            from parts_search.pipelines.inputs import artifact

            artifact(artifacts[stage.name], stage.name)
            result = {
                "stage": stage.name,
                "status": COMPLETED,
                "implemented": True,
                "artifact": str(artifacts[stage.name]),
                "reused": True,
                "blockers": [],
                "quality": None,
            }
        else:
            inputs = {}
            if stage.name in ("judgments", "retrieval", "evaluation", "training"):
                inputs["dataset"] = artifacts.get("catalog")
            if stage.name in ("evaluation", "training"):
                inputs.update(
                    judgments=artifacts.get("judgments"), search=artifacts.get("retrieval")
                )
            if stage.name == "gate":
                inputs.update(
                    baseline=artifacts.get("evaluation"),
                    evaluations=artifacts.get("candidate_evaluations"),
                )
            if stage.name == "simulation":
                inputs.update(
                    dataset=artifacts.get("catalog"),
                    judgments=artifacts.get("judgments"),
                    search=artifacts.get("retrieval"),
                    split=settings.config["simulation"]["validationSplit"],
                )
            if stage.name == "release":
                inputs.update(gate=artifacts.get("gate"), simulations=artifacts.get("simulations"))
            variant_settings = settings
            if stage.name == "training":
                import copy
                from dataclasses import replace

                config = copy.deepcopy(settings.config)
                config["ranker"]["seed"] = config["qualityGate"]["repetitionSeeds"][0]
                variant_settings = replace(settings, config=config)
            result = run_stage(variant_settings, stage.name, **inputs)
            if result["status"] == COMPLETED:
                artifacts[stage.name] = Path(result["artifact"])
        results.append(result)
        if stage.name == "simulation" and result["status"] == COMPLETED:
            # candidate 側は同じ split・同じ乱数 stream で、model 後の結果に対して回す。
            candidate_sim = run_stage(
                settings,
                "simulation",
                dataset=artifacts["catalog"],
                judgments=artifacts["judgments"],
                search=artifacts["training"],
                split=settings.config["simulation"]["validationSplit"],
            )
            results.append(candidate_sim)
            if candidate_sim["status"] == COMPLETED:
                artifacts["simulations"] = [
                    Path(result["artifact"]),
                    Path(candidate_sim["artifact"]),
                ]
        if stage.name == "training" and result["status"] == COMPLETED:
            import copy
            from dataclasses import replace

            evaluation_paths = []
            for seed in settings.config["qualityGate"]["repetitionSeeds"]:
                config = copy.deepcopy(settings.config)
                config["ranker"]["seed"] = seed
                variant = replace(settings, config=config)
                trained = (
                    result
                    if seed == settings.config["qualityGate"]["repetitionSeeds"][0]
                    else run_stage(
                        variant,
                        "training",
                        dataset=artifacts["catalog"],
                        judgments=artifacts["judgments"],
                        search=artifacts["retrieval"],
                    )
                )
                evaluated = run_stage(
                    variant,
                    "evaluation",
                    dataset=artifacts["catalog"],
                    judgments=artifacts["judgments"],
                    search=Path(trained["artifact"]),
                )
                evaluation_paths.append(Path(evaluated["artifact"]))
                if trained is not result:
                    results.append({**trained, "seed": seed})
                results.append({**evaluated, "seed": seed})
            artifacts["candidate_evaluations"] = evaluation_paths
        if result["status"] == "failed" or (stop_on_block and result["status"] == BLOCKED):
            break
    blocked = [r["stage"] for r in results if r["status"] == BLOCKED]
    failed = [r["stage"] for r in results if r["status"] == "failed"]
    done = [r["stage"] for r in results if r["status"] == COMPLETED]
    release = next((r for r in results if r["stage"] == "release"), None)
    quality = release.get("quality") if release else None
    # Golden Path は release が promote し、切替前 smoke まで通ったときだけ完走とする。
    complete = bool(
        release
        and release["status"] == COMPLETED
        and quality == "promote"
        and not blocked
        and not failed
    )
    return {
        "stages": results,
        "blocked_stages": blocked,
        "failed_stages": failed,
        "implemented_stages": done,
        "quality": quality,
        "golden_path_complete": complete,
        "note": f"{len(done)}/{len(STAGES)} stages completed; quality verdict={quality}",
    }


def resolve_artifacts(settings: Settings) -> Path:
    """成果物 root を返す（CLI の表示用）。"""
    root = settings.artifacts_root
    if not root.is_relative_to(settings.root):
        raise FoundationError("Artifacts root escapes repoRoot")
    return root
