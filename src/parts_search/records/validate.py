"""レコード契約の検査。**違反は理由付きで返し、黙って通さない。**

設計上の約束（`docs/05_data_model.md` / `docs/06_error_policy.md`）:

- **unknown は null。0 とは別物。** `relevance: 0`（不適合と判定した）と
  `relevance: null`（判定していない）を同じ扱いにしない。
- **正常 0 件・failed・not_run・unrateable・no_relevant を区別する。**
  どれも「結果が無い」に見えるが意味が違う。
- 集合全体の性質（ID 一意、rank 連続、query 網羅）は行単位では検査できないため、
  集合を受け取る関数で検査する。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

from parts_search.records.contracts import Issue, Record, record

_KINDS: dict[str, type | tuple[type, ...]] = {
    "str": str,
    "int": int,
    "float": (int, float),
    "bool": bool,
    "dict": dict,
    "list": list,
}


def _check_value(spec, value: Any, name: str, index: int, rec: str) -> list[Issue]:
    if value is None:
        if spec.nullable:
            return []
        return [
            Issue(rec, index, name, "null は許されない（unknown なら nullable な項目で表現する）")
        ]

    expected = _KINDS[spec.kind]
    # bool は int の subclass なので、int 期待の項目に True が入るのを弾く
    if spec.kind in ("int", "float") and isinstance(value, bool):
        return [Issue(rec, index, name, f"{spec.kind} を期待したが bool")]
    if not isinstance(value, expected):
        return [Issue(rec, index, name, f"{spec.kind} を期待したが {type(value).__name__}")]

    issues: list[Issue] = []
    if spec.kind == "str" and not value.strip():
        issues.append(Issue(rec, index, name, "空文字・空白のみは許されない"))
    if spec.enum and value not in spec.enum:
        issues.append(Issue(rec, index, name, "enum 外の値", {"allowed": list(spec.enum)}))
    if spec.finite and isinstance(value, float) and not math.isfinite(value):
        issues.append(Issue(rec, index, name, "有限値でない（NaN / inf）"))
    if spec.minimum is not None and value < spec.minimum:
        issues.append(Issue(rec, index, name, f"{spec.minimum} 未満"))
    if spec.maximum is not None and value > spec.maximum:
        issues.append(Issue(rec, index, name, f"{spec.maximum} 超過"))
    return issues


def _check_fields(rec: Record, row: Any, index: int) -> list[Issue]:
    if not isinstance(row, dict):
        return [Issue(rec.name, index, "", f"レコードは dict であること（{type(row).__name__}）")]
    issues: list[Issue] = []
    missing = [n for n in rec.field_names if n not in row]
    for name in missing:
        issues.append(Issue(rec.name, index, name, "必須項目が無い"))
    extra = [k for k in row if k not in rec.field_names]
    for name in sorted(extra):
        # 未知項目を黙って無視すると、綴り違いが「値が無い」として通る
        issues.append(Issue(rec.name, index, name, "契約に無い項目"))
    for spec in rec.fields:
        if spec.name in row:
            issues.extend(_check_value(spec, row[spec.name], spec.name, index, rec.name))
    return issues


def _check_identity(rec: Record, rows: Sequence[Any]) -> list[Issue]:
    seen: dict[tuple, int] = {}
    issues: list[Issue] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or any(k not in row for k in rec.identity):
            continue
        key = tuple(row[k] for k in rec.identity)
        if key in seen:
            issues.append(
                Issue(
                    rec.name,
                    index,
                    "+".join(rec.identity),
                    "同一性キーが重複",
                    {"first_index": seen[key]},
                )
            )
        else:
            seen[key] = index
    return issues


def _check_ranks(rec: Record, rows: Sequence[Any]) -> list[Issue]:
    """group 単位で rank が 1 始まり連続であること。

    欠番・重複・0 始まりは、上位 N 件の意味を壊すので通さない。
    """
    if not rec.rank_field:
        return []
    groups: dict[tuple, list[int]] = {}
    for row in rows:
        if not isinstance(row, dict) or rec.rank_field not in row:
            continue
        if any(k not in row for k in rec.group):
            continue
        value = row[rec.rank_field]
        if isinstance(value, int) and not isinstance(value, bool):
            groups.setdefault(tuple(row[k] for k in rec.group), []).append(value)

    issues: list[Issue] = []
    for key, ranks in groups.items():
        expected = list(range(1, len(ranks) + 1))
        if sorted(ranks) != expected:
            issues.append(
                Issue(
                    rec.name,
                    None,
                    rec.rank_field,
                    "rank が 1 始まりの連続でない",
                    {"group": list(key), "got": sorted(ranks), "expected": expected},
                )
            )
    return issues


# --- レコード固有の相関規則 -------------------------------------------------
# 単項目の型検査では通ってしまう「意味の矛盾」をここで落とす。


def _judgment_rules(rows: Sequence[Any]) -> list[Issue]:
    issues: list[Issue] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        status, relevance = row.get("status"), row.get("relevance")
        if status == "judged" and relevance is None:
            issues.append(Issue("Judgment", index, "relevance", "status=judged なら 0〜4 が必要"))
        if status in ("unrateable", "not_run") and relevance is not None:
            issues.append(
                Issue(
                    "Judgment",
                    index,
                    "relevance",
                    f"status={status} に relevance を入れない（未判定と 0 を混同させない）",
                )
            )
    return issues


def _outcome_rules(rows: Sequence[Any]) -> list[Issue]:
    issues: list[Issue] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        status = row.get("status")
        error, count = row.get("error_code"), row.get("returned_count")
        latency = row.get("latency_ms")
        if status == "failed" and not error:
            issues.append(Issue("QueryOutcome", index, "error_code", "status=failed なら必須"))
        if status == "succeeded" and error is not None:
            issues.append(
                Issue(
                    "QueryOutcome",
                    index,
                    "error_code",
                    "status=succeeded に error_code を持たせない",
                )
            )
        if status == "not_run":
            if count not in (0, None):
                issues.append(
                    Issue("QueryOutcome", index, "returned_count", "status=not_run は 0 件")
                )
            if latency is not None:
                issues.append(
                    Issue("QueryOutcome", index, "latency_ms", "実行していないので latency は null")
                )
        if status == "failed" and count not in (0, None):
            issues.append(
                Issue(
                    "QueryOutcome",
                    index,
                    "returned_count",
                    "失敗時の件数を成果として数えない（正常 0 件と区別する）",
                )
            )
    return issues


def _feature_row_rules(rows: Sequence[Any]) -> list[Issue]:
    issues: list[Issue] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        values, mask = row.get("values"), row.get("missing_mask")
        if isinstance(values, list) and isinstance(mask, list) and len(values) != len(mask):
            issues.append(
                Issue(
                    "FeatureRow",
                    index,
                    "missing_mask",
                    "values と長さが違う（欠損と 0 の区別が壊れる）",
                    {"values": len(values), "mask": len(mask)},
                )
            )
        for key in ("label", "label_source", "gt_id"):
            if key in row:
                issues.append(
                    Issue("FeatureRow", index, key, "label 系は別列で結合する（漏洩防止）")
                )
    return issues


def _decision_rules(rows: Sequence[Any]) -> list[Issue]:
    issues: list[Issue] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        decision, release = row.get("decision"), row.get("release_id")
        if decision == "promote" and not release:
            issues.append(
                Issue("PromotionDecision", index, "release_id", "decision=promote なら必須")
            )
        if decision != "promote" and release is not None:
            issues.append(
                Issue(
                    "PromotionDecision",
                    index,
                    "release_id",
                    "採用していないのに release_id を持たせない",
                )
            )
    return issues


_RULES = {
    "Judgment": _judgment_rules,
    "QueryOutcome": _outcome_rules,
    "FeatureRow": _feature_row_rules,
    "PromotionDecision": _decision_rules,
}


def validate(name: str, rows: Iterable[Any]) -> list[Issue]:
    """1 レコード型の集合を検査し、違反を全部返す。

    最初の違反で止めない。**1 回の実行で直せる情報を全部出す**ため。
    """
    rec = record(name)
    materialized = list(rows)
    issues: list[Issue] = []
    for index, row in enumerate(materialized):
        issues.extend(_check_fields(rec, row, index))
    issues.extend(_check_identity(rec, materialized))
    issues.extend(_check_ranks(rec, materialized))
    rule = _RULES.get(name)
    if rule:
        issues.extend(rule(materialized))
    return issues


def validate_query_coverage(queries: Sequence[dict], outcomes: Sequence[dict]) -> list[Issue]:
    """QuerySet の全 query に QueryOutcome がちょうど 1 件あること。

    「失敗した query を黙って落とす」と、分母が縮んで指標が良く見える。
    05「QuerySet の全 query につき 1 件」はそれを防ぐための契約。
    """
    wanted = [q["query_id"] for q in queries if isinstance(q, dict) and "query_id" in q]
    counts: dict[str, int] = {}
    for row in outcomes:
        if isinstance(row, dict) and isinstance(row.get("query_id"), str):
            counts[row["query_id"]] = counts.get(row["query_id"], 0) + 1

    issues: list[Issue] = []
    for query_id in wanted:
        found = counts.get(query_id, 0)
        if found != 1:
            issues.append(
                Issue(
                    "QueryOutcome",
                    None,
                    "query_id",
                    "QuerySet の query に対する outcome が 1 件でない",
                    {"query_id": query_id, "found": found},
                )
            )
    for query_id in sorted(set(counts) - set(wanted)):
        issues.append(
            Issue(
                "QueryOutcome",
                None,
                "query_id",
                "QuerySet に無い query の outcome",
                {"query_id": query_id},
            )
        )
    return issues


def validate_split_disjoint(manifest: dict) -> list[Issue]:
    """family が複数 split に跨らないこと（05「family 集合の交差は空」）。

    跨ると train の情報が holdout へ漏れ、評価が甘くなる。
    """
    assignments = manifest.get("assignments")
    if not isinstance(assignments, dict):
        return [Issue("SplitManifest", None, "assignments", "dict であること")]
    issues: list[Issue] = []
    for family, split in assignments.items():
        if not isinstance(split, str):
            issues.append(Issue("SplitManifest", None, f"assignments.{family}", "split 名は文字列"))
    return issues
