"""`docs/05_data_model.md` の最小レコード契約を宣言で持つ。

判定ロジックを散らさず、**必須項目・型・null 規約をここ 1 箇所**に置く。
05 を変えたらここを変える。逆にここだけ変えて 05 を放置しない。

設計上の約束:

- **unknown は null。0 とは別物**（05「unknownはnullであり0と異なる」）。
  よって「欠落」と「値が 0」を同じ扱いにしない。
- `schema_version` は全レコードに付く。未対応 version は読込時に拒否する。
- status 系は enum で固定し、`failed` / `not_run` / `unrateable` / `no_relevant` を
  区別できる形にする（07「正常0件、failed、not_run、unrateable、no_relevantを区別」）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSION = 1

# 05 GT policy v1: judged のときだけ 0〜4。未判定は relevance を持たない。
JUDGMENT_STATUS = ("judged", "unrateable", "not_run")
JUDGMENT_SOURCE = ("rule", "manual", "implicit")
RELEVANCE_RANGE = (0, 4)

# 05 QueryOutcome: 正常 0 件は成功。timeout 等は failed。未実行は not_run。
OUTCOME_STATUS = ("succeeded", "failed", "not_run")

QUERY_TYPES = ("exact_model_number", "natural_language", "dimension_sensitive")
SPLITS = ("train", "tuning", "holdout", "production")
SCORE_TYPES = ("similarity", "distance", "model_score", "fused_score")

# 05 Evaluation: 完全判定でない場合は inconclusive、正解不在は no_relevant。
EVALUATION_STATUS = ("complete", "inconclusive", "no_relevant")
DECISIONS = ("promote", "reject", "inconclusive")
FAILURE_CATEGORIES = ("retrieval_miss", "rerank_miss", "gt_defect", "execution_failure")


@dataclass(frozen=True)
class Field:
    """1 項目の契約。

    `nullable=True` は「値が無い」を正当に表現できる項目のみに付ける。
    ここを緩めると unknown と 0 の区別が壊れる。
    """

    name: str
    kind: str  # "str" | "int" | "float" | "bool" | "dict" | "list"
    nullable: bool = False
    enum: tuple[str, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None
    finite: bool = False  # float のとき NaN / inf を拒否する


@dataclass(frozen=True)
class Record:
    """レコード型の契約。

    `identity` は集合内一意性の検査キー。`rank_field` があれば
    `group` 単位で 1 始まり連続を検査する。
    """

    name: str
    fields: tuple[Field, ...]
    identity: tuple[str, ...]
    group: tuple[str, ...] = ()
    rank_field: str | None = None
    doc: str = ""

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(name)


def _text(name: str, **kw) -> Field:
    return Field(name, "str", **kw)


def _int(name: str, **kw) -> Field:
    return Field(name, "int", **kw)


def _score(name: str, **kw) -> Field:
    return Field(name, "float", finite=True, **kw)


PRODUCT = Record(
    name="Product",
    fields=(
        _text("product_id"),
        _text("category"),
        _text("model_number"),
        Field("texts", "dict"),  # locale -> {title, description}
        Field("attributes", "dict"),  # name -> {value, unit} / null
    ),
    identity=("product_id",),
    doc="catalog 内で product_id 一意。manufacturer・価格・在庫は利用時に追加する。",
)

QUERY = Record(
    name="Query",
    fields=(
        _text("query_id"),
        _text("family_id"),
        _text("text"),
        _text("language"),
        _text("query_type", enum=QUERY_TYPES),
        _text("category", nullable=True),
        Field("constraints", "dict"),  # 必須条件と任意条件を区別して持つ
    ),
    identity=("query_id",),
    doc="必須条件と任意条件を constraints 内で区別する。",
)

SPLIT_MANIFEST = Record(
    name="SplitManifest",
    fields=(
        _text("split_id"),
        Field("assignments", "dict"),  # family_id -> split
        _int("generation_seed", minimum=0),
        _int("split_seed", minimum=0),
        Field("counts", "dict"),
        _text("set_digest"),
    ),
    identity=("split_id",),
    doc="family 集合の交差は空。集合 digest で同一性を確認する。",
)

JUDGMENT = Record(
    name="Judgment",
    fields=(
        _text("gt_id"),
        _text("query_id"),
        _text("product_id"),
        _text("status", enum=JUDGMENT_STATUS),
        _int("relevance", nullable=True, minimum=RELEVANCE_RANGE[0], maximum=RELEVANCE_RANGE[1]),
        _text("source", enum=JUDGMENT_SOURCE),
        _text("reason"),
        _text("rule_version"),
        Field("evidence_ids", "list"),
    ),
    identity=("gt_id", "query_id", "product_id"),
    doc="relevance は status=judged のときのみ 0〜4。未判定で 0 を入れない。",
)

CANDIDATE = Record(
    name="Candidate",
    fields=(
        _text("run_id"),
        _text("query_id"),
        _text("product_id"),
        _text("source"),
        _int("source_rank", minimum=1),
        _text("score_type", enum=SCORE_TYPES),
        _score("raw_score"),
        _text("retrieval_config_id"),
    ),
    identity=("run_id", "query_id", "product_id", "source"),
    doc="query-product-source 一意。統合後の CandidateSet は別途 candidate_rank を持つ。",
)

SEARCH_RESULT = Record(
    name="SearchResult",
    fields=(
        _text("run_id"),
        _text("query_id"),
        _text("product_id"),
        _int("rank", minimum=1),
        _score("score"),
        _text("score_type", enum=SCORE_TYPES),
        _text("model_id", nullable=True),
    ),
    identity=("run_id", "query_id", "product_id"),
    group=("run_id", "query_id"),
    rank_field="rank",
    doc="query 単位で rank が 1 始まり連続。score は有限。",
)

QUERY_OUTCOME = Record(
    name="QueryOutcome",
    fields=(
        _text("run_id"),
        _text("query_id"),
        _text("status", enum=OUTCOME_STATUS),
        _int("returned_count", minimum=0),
        _text("error_code", nullable=True),
        _int("attempt", minimum=1),
        _int("latency_ms", nullable=True, minimum=0),
    ),
    identity=("run_id", "query_id"),
    doc="QuerySet の全 query につき 1 件。正常 0 件は succeeded かつ returned_count=0。",
)

FEATURE_SCHEMA = Record(
    name="FeatureSchema",
    fields=(
        _text("schema_id"),
        Field("columns", "list"),  # 順序付き。name/type/default/null 規約
        _text("transform_version"),
        Field("normalization", "dict"),
        _text("checksum"),
    ),
    identity=("schema_id",),
    doc="列順を含めて checksum 化する。順序が変われば別 schema。",
)

FEATURE_ROW = Record(
    name="FeatureRow",
    fields=(
        _text("query_id"),
        _text("product_id"),
        _text("schema_id"),
        Field("values", "list"),
        Field("missing_mask", "list"),
        _text("as_of"),
    ),
    identity=("schema_id", "query_id", "product_id"),
    doc="label は学習時のみ別列で結合する。ここに label を混ぜない（漏洩防止）。",
)

MODEL_BUNDLE = Record(
    name="ModelBundle",
    fields=(
        _text("model_id"),
        _text("dataset_id"),
        _text("feature_schema_checksum"),
        _text("trainer_version"),
        Field("trainer_config", "dict"),
        Field("label_gain", "list"),
        _text("split_id"),
        _text("artifact_checksum"),
    ),
    identity=("model_id",),
    doc="label_gain は MetricPolicy v1 と一致させる。",
)

EXPERIMENT = Record(
    name="Experiment",
    fields=(
        _text("experiment_id"),
        _text("parent_experiment_id", nullable=True),
        _text("hypothesis"),
        _text("dataset_id"),
        _text("queryset_id"),
        _text("gt_id"),
        _text("split_id"),
        _text("metric_policy_id"),
        Field("variants", "list"),
        _int("seed", minimum=0),
        Field("compared_runs", "dict"),  # baseline / candidate
    ),
    identity=("experiment_id",),
    doc="各 variant が SearchConfiguration と model を固定する。",
)

EVALUATION = Record(
    name="Evaluation",
    fields=(
        _text("evaluation_id"),
        _text("search_run_id"),
        _text("candidate_run_id"),
        _text("gt_id"),
        _text("metric_policy_id"),
        _text("comparison_signature"),
        _text("status", enum=EVALUATION_STATUS),
        Field("per_query", "list"),
        Field("aggregate", "dict"),
        Field("denominators", "dict"),
        Field("coverage", "dict"),
    ),
    identity=("evaluation_id",),
    doc="未判定が残れば inconclusive。正解不在は no_relevant として分ける。",
)

FAILURE_CASE = Record(
    name="FailureCase",
    fields=(
        _text("failure_id"),
        _text("query_id"),
        _text("run_id"),
        Field("evidence_ids", "list"),
        _text("category", enum=FAILURE_CATEGORIES),
        _text("description"),
        _text("next_experiment_id", nullable=True),
    ),
    identity=("failure_id",),
    doc="retrieval 漏れと rerank 不良を category で区別する。",
)

PROMOTION_DECISION = Record(
    name="PromotionDecision",
    fields=(
        _text("decision_id"),
        _text("baseline_run_id"),
        _text("candidate_run_id"),
        _text("policy_id"),
        Field("comparison", "dict"),
        Field("denominators", "dict"),
        Field("gate_results", "dict"),
        _text("decision", enum=DECISIONS),
        _text("reason"),
        _text("release_id", nullable=True),
    ),
    identity=("decision_id",),
    doc="採用時のみ release_id を持つ。",
)

RECORDS: tuple[Record, ...] = (
    PRODUCT,
    QUERY,
    SPLIT_MANIFEST,
    JUDGMENT,
    CANDIDATE,
    SEARCH_RESULT,
    QUERY_OUTCOME,
    FEATURE_SCHEMA,
    FEATURE_ROW,
    MODEL_BUNDLE,
    EXPERIMENT,
    EVALUATION,
    FAILURE_CASE,
    PROMOTION_DECISION,
)

RECORD_NAMES: tuple[str, ...] = tuple(r.name for r in RECORDS)
_BY_NAME: dict[str, Record] = {r.name: r for r in RECORDS}


def record(name: str) -> Record:
    try:
        return _BY_NAME[name]
    except KeyError as error:
        raise KeyError(f"Unknown record contract: {name}") from error


@dataclass(frozen=True)
class Issue:
    """契約違反 1 件。**理由を必ず持つ**（どこが何故駄目かを言わない検査は使えない）。"""

    record: str
    index: int | None
    path: str
    reason: str
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:
        where = f"[{self.index}]" if self.index is not None else ""
        return f"{self.record}{where}.{self.path}: {self.reason}"
