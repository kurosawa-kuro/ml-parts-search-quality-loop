"""レコード契約とその検査。T2〜T8 が共通で使う入口。

- `contracts`: 05 の最小レコード契約（宣言）
- `validate`:  集合を受け取って違反を理由付きで返す
- `io`:        JSON / JSONL 読込。未対応 schema_version を拒否する

各工程は `json.load` を直接使わず `read_records` を通す。
自前読込を作ると version 検査が抜けた経路が必ず 1 本できる。
"""

from parts_search.records.contracts import (
    RECORD_NAMES,
    RECORDS,
    SCHEMA_VERSION,
    Issue,
    Record,
    record,
)
from parts_search.records.io import iter_jsonl, read_json, read_records
from parts_search.records.validate import (
    validate,
    validate_query_coverage,
    validate_split_disjoint,
)

__all__ = [
    "RECORDS",
    "RECORD_NAMES",
    "SCHEMA_VERSION",
    "Issue",
    "Record",
    "iter_jsonl",
    "read_json",
    "read_records",
    "record",
    "validate",
    "validate_query_coverage",
    "validate_split_disjoint",
]
