"""T1 の成果物: レコード契約と validator の棚卸しを出す。

`contracts` 段階の実処理。**何を検査できるようになったか**を成果物として残す。
後続工程は「この契約が既にあるか」をここで確認できる。
"""

from __future__ import annotations

from typing import Any

from parts_search.records.contracts import RECORDS, SCHEMA_VERSION
from parts_search.records.validate import _RULES  # noqa: PLC2701 - 棚卸し目的の内部参照


def build_contracts_report() -> dict[str, Any]:
    """契約一覧を成果物形式で返す。

    件数ではなく**項目名まで**出す。「14 契約ある」だけでは、
    どの検査が入っているのか後から確認できない。
    """
    records = []
    for rec in RECORDS:
        records.append(
            {
                "record": rec.name,
                "identity": list(rec.identity),
                "rank_checked": bool(rec.rank_field),
                "rank_group": list(rec.group),
                "nullable_fields": [f.name for f in rec.fields if f.nullable],
                "enum_fields": {f.name: list(f.enum) for f in rec.fields if f.enum},
                "finite_fields": [f.name for f in rec.fields if f.finite],
                "cross_field_rules": rec.name in _RULES,
                "fields": list(rec.field_names),
                "doc": rec.doc,
            }
        )
    return {
        "contracts.json": {
            "schema_version": SCHEMA_VERSION,
            "stage": "contracts",
            "implemented": True,
            "task": "T1",
            "record_count": len(records),
            "records": records,
            "set_level_checks": [
                "identity uniqueness",
                "rank contiguity from 1 per group",
                "query coverage (exactly one QueryOutcome per Query)",
                "unsupported schema_version rejected on read",
            ],
            "note": "validators only; no catalog, retrieval, training or metrics performed",
        }
    }
