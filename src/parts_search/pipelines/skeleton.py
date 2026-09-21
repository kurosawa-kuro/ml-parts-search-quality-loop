"""段階を「実行してログを出して終わる」だけの骨組み。

意図的に何も計算しない。目的は次の 2 つだけ。

1. Golden Path の段数・依存順・成果物配置を**実行可能な形で**固定する。
2. **どの段階が設定未確定で止まるか**を実測で出す（未決事項への写像）。

`docs/specs/evidence-policy.md` の下限に従い、骨組みの実行は
Evidence Level 1（成果物が実在する）どまりであることを payload に明示する。
"""

from __future__ import annotations

from pathlib import Path

from parts_search.config.loader import Settings
from parts_search.errors import FoundationError
from parts_search.logs import logger
from parts_search.pipelines.bootstrap import provenance
from parts_search.pipelines.contracts_report import build_contracts_report
from parts_search.pipelines.stages import STAGES, Stage, stage_by_name
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


def run_stage(settings: Settings, name: str, run_id: str | None = None) -> dict[str, object]:
    """1 段階を実行する。設定が未確定なら成果物を作らず blocked を返す。"""
    stage = stage_by_name(name)
    log = logger()
    blockers = settings.blockers(stage.config_stage)

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
    status = COMPLETED if builder else SKELETON
    log.info("stage=%s task=%s status=%s id=%s", stage.name, stage.task, status, identifier)
    outputs = builder() if builder else _outputs(stage)
    path = publish_run(
        destination,
        identifier,
        outputs,
        {
            "kind": f"{status}_{stage.name}",
            "stage": stage.name,
            "task": stage.task,
            "implemented": bool(builder),
            "evidence_level": 2 if builder else 1,
            "provenance": provenance(settings.root),
        },
    )
    for output in stage.outputs:
        log.debug("stage=%s wrote=%s", stage.name, output)
    return {
        "stage": stage.name,
        "task": stage.task,
        "status": status,
        "config_stage": stage.config_stage,
        "blockers": [],
        "artifact": str(path),
        "implemented": bool(builder),
    }


def run_pipeline(settings: Settings, stop_on_block: bool = False) -> dict[str, object]:
    """全段階を依存順に実行する。

    `golden_path_complete` は**常に False** になる（実装が無いため）。
    ここが True になるのは各段階の実装が入ったときだけで、
    骨組みの完走を Golden Path の達成と読み替えさせない。
    """
    log = logger()
    results: list[dict[str, object]] = []
    for stage in STAGES:
        result = run_stage(settings, stage.name)
        results.append(result)
        if stop_on_block and result["status"] == BLOCKED:
            log.error("pipeline stopped at stage=%s (blocked)", stage.name)
            break

    blocked = [r["stage"] for r in results if r["status"] == BLOCKED]
    done = [r["stage"] for r in results if r["implemented"]]
    log.info(
        "pipeline stages=%d completed=%d skeleton=%d blocked=%d",
        len(results),
        len(done),
        sum(1 for r in results if r["status"] == SKELETON),
        len(blocked),
    )
    return {
        "stages": results,
        "blocked_stages": blocked,
        "implemented_stages": done,
        # 全段階が実装済みかつ blocker 無しのときだけ True。骨組みの完走を達成と読み替えない。
        "golden_path_complete": bool(results) and len(done) == len(STAGES) and not blocked,
        "note": f"{len(done)}/{len(STAGES)} stages implemented",
    }


def resolve_artifacts(settings: Settings) -> Path:
    """成果物 root を返す（CLI の表示用）。"""
    root = settings.artifacts_root
    if not root.is_relative_to(settings.root):
        raise FoundationError("Artifacts root escapes repoRoot")
    return root
