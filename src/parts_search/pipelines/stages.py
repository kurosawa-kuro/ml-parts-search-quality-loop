"""Golden Path の段階定義（骨組みのみ。ML は未実装）。

各段階は「どの設定段階に依存し、どこへ何を書くか」だけを宣言する。
成果物の配置は `docs/05_data_model.md` の artifacts レイアウトに対応させる。

**未実装を成功として記録しない。** 段階が未実装なら成果物の payload に
`implemented: false` を明示し、設定が未確定（blockers あり）なら成果物を
publish せず `blocked` として報告する。骨組みが緑に見えることを禁じる。
"""

from __future__ import annotations

from dataclasses import dataclass

from parts_search.errors import FoundationError


@dataclass(frozen=True)
class Stage:
    """1 段階の宣言。`implemented=False` のあいだ payload は placeholder。"""

    name: str
    task: str
    config_stage: str
    group: str
    outputs: tuple[str, ...]
    summary: str
    implemented: bool = False

    def placeholder(self) -> dict[str, object]:
        """未実装であることを明示する payload。

        判定結果や指標を「0」で埋めない。0 と未実装は別物であり、
        `docs/06_error_policy.md` の null/0 区別に従う。
        """
        return {
            "schema_version": 1,
            "stage": self.name,
            "implemented": self.implemented,
            "task": self.task,
            "summary": self.summary,
            "note": "skeleton only; no retrieval, training, metrics or release performed",
        }


# 依存順。docs/tasks/02_backlog/20260921-search-quality-poc-implementation.md の T1〜T8。
STAGES: tuple[Stage, ...] = (
    Stage(
        name="contracts",
        task="T1",
        config_stage="foundation",
        group="reports",
        outputs=("contracts.json",),
        summary="レコード契約 validator と手書き fixture",
        implemented=True,
    ),
    Stage(
        name="catalog",
        task="T2",
        config_stage="catalog",
        group="datasets",
        outputs=("catalog.jsonl", "queries.jsonl", "splits.json"),
        summary="合成カタログ・Query・GT と family 分割",
        implemented=True,
    ),
    Stage(
        name="judgments",
        task="T2",
        config_stage="catalog",
        group="judgments",
        outputs=("judgments.jsonl", "summary.json"),
        summary="GT policy v1 による完全判定 GT",
        implemented=True,
    ),
    Stage(
        name="retrieval",
        task="T3",
        config_stage="retrieval",
        group="runs",
        outputs=("candidates.jsonl", "results.jsonl", "outcomes.jsonl", "index.json"),
        summary="Vector Baseline 検索と SearchRun",
        implemented=True,
    ),
    Stage(
        name="evaluation",
        task="T4",
        config_stage="evaluation",
        group="runs",
        outputs=("metrics.json", "per_query.jsonl", "slices.jsonl", "failures.jsonl"),
        summary="評価・Slice・FailureCase",
        implemented=True,
    ),
    Stage(
        name="training",
        task="T5",
        config_stage="training",
        group="models",
        outputs=(
            "feature_schema.json",
            "model.json",
            "bundle.json",
            "features.jsonl",
            "candidates.jsonl",
            "results.jsonl",
            "outcomes.jsonl",
        ),
        summary="構造化 Feature と LambdaRank",
        implemented=True,
    ),
    Stage(
        name="gate",
        task="T6",
        config_stage="gate",
        group="experiments",
        outputs=("experiment.json", "decision.json"),
        summary="Experiment 比較と品質 Gate",
        implemented=True,
    ),
    Stage(
        name="simulation",
        task="T7",
        config_stage="simulation",
        group="runs",
        outputs=(
            "events.jsonl",
            "impressions.jsonl",
            "kpis.json",
            "failures.jsonl",
            "gt_candidates.jsonl",
            "quarantine.jsonl",
        ),
        summary="疑似オンライン Feedback Loop",
        implemented=True,
    ),
    Stage(
        name="release",
        task="T8",
        config_stage="gate",
        group="releases",
        # bundle.json は promote のときだけ書く（昇格しない決定で bundle を作らない）。
        outputs=("decision.json", "smoke.json"),
        summary="独立評価・Release・Golden Path",
        implemented=True,
    ),
)

STAGE_NAMES = tuple(stage.name for stage in STAGES)
_BY_NAME = {stage.name: stage for stage in STAGES}


def stage_by_name(name: str) -> Stage:
    try:
        return _BY_NAME[name]
    except KeyError:
        raise FoundationError("Unknown pipeline stage") from None
