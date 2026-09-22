"""レコード契約 validator のテスト（T1）。

**手書き fixture を使う。** 合成生成器の出力でテストすると、生成器のバグを
同じバグで検証してしまい常に緑になる（`docs/07_test_strategy.md`）。

異常 fixture は「落ちること」ではなく「**正しい理由で**落ちること」を見る。
理由が違えば、別のバグで偶然落ちているだけかもしれない。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parts_search.errors import FoundationError
from parts_search.records import (
    RECORD_NAMES,
    RECORDS,
    iter_jsonl,
    read_records,
    record,
    validate,
    validate_query_coverage,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VALID, INVALID = FIXTURES / "valid", FIXTURES / "invalid"

VALID_SETS = {
    "Product": "products.jsonl",
    "Query": "queries.jsonl",
    "Judgment": "judgments.jsonl",
    "SearchResult": "results.jsonl",
    "QueryOutcome": "outcomes.jsonl",
}


# --- 契約の宣言そのもの ---


def test_every_record_declares_identity_and_fields():
    for rec in RECORDS:
        assert rec.fields, rec.name
        assert rec.identity, rec.name
        for key in rec.identity:
            assert key in rec.field_names, f"{rec.name}.{key}"
        for key in rec.group:
            assert key in rec.field_names, f"{rec.name}.{key}"


def test_record_lookup_rejects_unknown():
    with pytest.raises(KeyError):
        record("NotARecord")


def test_contract_covers_the_data_model():
    """05 の最小レコード契約表に載っている型が揃っていること。"""
    expected = {
        "Product",
        "Query",
        "SplitManifest",
        "Judgment",
        "Candidate",
        "SearchResult",
        "QueryOutcome",
        "FeatureRow",
        "FeatureSchema",
        "ModelBundle",
        "Experiment",
        "Evaluation",
        "FailureCase",
        "PromotionDecision",
        "Event",
        "ReleaseBundle",
    }
    assert set(RECORD_NAMES) == expected


# --- 正常 fixture ---


@pytest.mark.parametrize(("name", "filename"), sorted(VALID_SETS.items()))
def test_valid_fixtures_pass(name: str, filename: str):
    rows = list(iter_jsonl(VALID / filename))
    assert rows, filename
    assert validate(name, rows) == []


def test_read_records_returns_rows_for_valid_fixture():
    rows = read_records("Product", VALID / "products.jsonl")
    assert [r["product_id"] for r in rows] == ["P-0001", "P-0002"]


def test_empty_jsonl_is_zero_records_not_an_error(tmp_path: Path):
    """0 件は結果であって失敗ではない（06 の 0/null 区別）。"""
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert read_records("Product", empty) == []


def test_query_coverage_is_satisfied_by_valid_fixture():
    queries = list(iter_jsonl(VALID / "queries.jsonl"))
    outcomes = list(iter_jsonl(VALID / "outcomes.jsonl"))
    assert validate_query_coverage(queries, outcomes) == []


# --- 異常 fixture: 理由まで確認する ---

CASES = [
    ("duplicate_product_id.jsonl", "Product", "同一性キーが重複"),
    ("rank_not_contiguous.jsonl", "SearchResult", "rank が 1 始まりの連続でない"),
    ("rank_starts_at_zero.jsonl", "SearchResult", "1 未満"),
    ("score_not_finite.jsonl", "SearchResult", "有限値でない"),
    ("judged_without_relevance.jsonl", "Judgment", "status=judged なら 0〜4 が必要"),
    ("unrateable_with_zero_relevance.jsonl", "Judgment", "relevance を入れない"),
    ("relevance_out_of_range.jsonl", "Judgment", "4 超過"),
    ("failed_outcome_counts_results.jsonl", "QueryOutcome", "成果として数えない"),
    ("failed_outcome_without_error_code.jsonl", "QueryOutcome", "status=failed なら必須"),
    ("not_run_outcome_with_latency.jsonl", "QueryOutcome", "latency は null"),
    ("unknown_field.jsonl", "Product", "契約に無い項目"),
    ("feature_row_with_label.jsonl", "FeatureRow", "label 系は別列で結合する"),
    ("feature_mask_length_mismatch.jsonl", "FeatureRow", "values と長さが違う"),
    ("promote_without_release.jsonl", "PromotionDecision", "decision=promote なら必須"),
]


@pytest.mark.parametrize(("filename", "name", "reason"), CASES)
def test_invalid_fixtures_fail_with_the_right_reason(filename: str, name: str, reason: str):
    rows = list(iter_jsonl(INVALID / filename))
    issues = validate(name, rows)
    assert issues, f"{filename} が通ってしまった"
    assert any(reason in issue.reason for issue in issues), (
        f"{filename}: 期待した理由 '{reason}' が出ていない / 実際: {[i.reason for i in issues]}"
    )


@pytest.mark.parametrize("filename", [c[0] for c in CASES])
def test_read_records_refuses_invalid_fixtures(filename: str):
    """読込の段で落とす。壊れたデータを下流へ流さない。"""
    name = dict((c[0], c[1]) for c in CASES)[filename]
    with pytest.raises(FoundationError):
        read_records(name, INVALID / filename)


def test_unsupported_schema_version_is_rejected():
    with pytest.raises(FoundationError, match="schema_version"):
        list(iter_jsonl(INVALID / "bad_schema_version.jsonl"))


def test_malformed_jsonl_line_is_rejected(tmp_path: Path):
    broken = tmp_path / "broken.jsonl"
    broken.write_text('{"product_id": "P-1"}\nnot json\n', encoding="utf-8")
    with pytest.raises(FoundationError, match="line 2"):
        list(iter_jsonl(broken))


# --- 0 と null、status の区別 ---


def test_zero_and_null_are_not_interchangeable():
    """relevance=0（不適合と判定した）と null（未判定）は別物。"""
    judged_zero = {
        "gt_id": "G",
        "query_id": "Q",
        "product_id": "P",
        "status": "judged",
        "relevance": 0,
        "source": "rule",
        "reason": "mismatch",
        "rule_version": "v1",
        "evidence_ids": [],
    }
    assert validate("Judgment", [judged_zero]) == [], "0 は正当な判定結果"
    not_judged_zero = dict(judged_zero, status="not_run")
    assert validate("Judgment", [not_judged_zero]), "未判定に 0 を入れたら落ちる"


def test_succeeded_zero_results_is_not_a_failure():
    """正常 0 件は成功。failed / not_run と区別する。"""
    base = {"run_id": "R", "query_id": "Q", "attempt": 1}
    zero_ok = {
        **base,
        "status": "succeeded",
        "returned_count": 0,
        "error_code": None,
        "latency_ms": 8,
    }
    assert validate("QueryOutcome", [zero_ok]) == []

    failed = {
        **base,
        "status": "failed",
        "returned_count": 0,
        "error_code": "timeout",
        "latency_ms": 15000,
    }
    assert validate("QueryOutcome", [failed]) == []

    not_run = {
        **base,
        "status": "not_run",
        "returned_count": 0,
        "error_code": None,
        "latency_ms": None,
    }
    assert validate("QueryOutcome", [not_run]) == []

    statuses = {r["status"] for r in (zero_ok, failed, not_run)}
    assert statuses == {"succeeded", "failed", "not_run"}, "3 状態を別に表現できる"


def test_bool_is_not_accepted_where_an_int_is_required():
    """True は int の subclass。件数に True が入るのを通さない。"""
    row = {
        "run_id": "R",
        "query_id": "Q",
        "status": "succeeded",
        "returned_count": True,
        "error_code": None,
        "attempt": 1,
        "latency_ms": 1,
    }
    issues = validate("QueryOutcome", [row])
    assert any("bool" in i.reason for i in issues)


def test_query_coverage_detects_missing_and_extra():
    queries = [{"query_id": "Q-1"}, {"query_id": "Q-2"}]
    outcomes = [
        {"query_id": "Q-1"},
        {"query_id": "Q-1"},  # 重複
        {"query_id": "Q-9"},  # QuerySet に無い
    ]
    issues = validate_query_coverage(queries, outcomes)
    detail = {tuple(i.detail.items()) for i in issues}
    assert ("query_id", "Q-1") in [tuple(d)[0] for d in detail]
    assert any(i.detail.get("query_id") == "Q-2" and i.detail.get("found") == 0 for i in issues)
    assert any(i.detail.get("query_id") == "Q-9" for i in issues)


# --- 指標の手計算 fixture（T4 がこれに一致すること） ---


def test_metric_fixture_matches_the_documented_hand_calculation():
    data = json.loads((FIXTURES / "metrics_expected.json").read_text(encoding="utf-8"))
    assert data["policy"]["gain_by_relevance"] == [0, 0, 1, 3, 7]
    first = next(c for c in data["cases"] if c["name"] == "results_B_C_A")
    assert first["expected"]["dcg_at_10"] == pytest.approx(6.5), "07 の手計算値"
    assert first["expected"]["rr_at_100"] == 1.0
    second = next(c for c in data["cases"] if c["name"] == "results_C_A_B")
    assert second["expected"]["rr_at_100"] == 0.5


def test_metric_fixture_separates_zero_null_and_no_relevant():
    """0 点・null・no_relevant を別のケースとして持っていること。"""
    data = json.loads((FIXTURES / "metrics_expected.json").read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in data["cases"]}
    assert by_name["zero_results_with_relevant_gt"]["expected"]["ndcg_at_10"] == 0.0
    assert by_name["execution_failed"]["expected"]["ndcg_at_10"] is None
    assert by_name["execution_failed"]["status"] == "inconclusive"
    assert by_name["no_relevant_complete_gt"]["status"] == "no_relevant"
