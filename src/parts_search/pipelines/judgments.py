"""GT policy v1 applied to every saved query/product pair, in bounded memory."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from parts_search.errors import FoundationError
from parts_search.logs import logger
from parts_search.pipelines.synthetic import (
    DIMENSIONS,
    POLICY,
    check_records,
    digest,
    normalize_product,
    normalize_query,
    validate_dataset,
)
from parts_search.records.io import read_json, read_records
from parts_search.runstore import file_checksum, verify_run

GT_POLICY = "parts_gt_v1"


def _matches(key: str, expected, actual) -> bool:
    if expected is None or actual is None:
        return False
    if key in DIMENSIONS:
        return expected[0] - 1e-9 <= actual <= expected[1] + 1e-9
    return expected == actual


def judge(query: dict, product: dict) -> tuple[str, int | None, str]:
    """Evaluate normalized inputs; mandatory constraints precede model equality."""
    required, optional = query["required"], query["optional"]
    conditions = [*required.items(), *optional.items()]
    if query["contradictory"]:
        return "unrateable", None, "contradictory_constraints"
    if any(value is None or product.get(key) is None for key, value in conditions):
        return "unrateable", None, "missing_evidence"
    if any(not _matches(key, value, product.get(key)) for key, value in required.items()):
        return "judged", 0, "mandatory_violation"
    category = query["category"] or required.get("category") or optional.get("category")
    if category is not None and product["category"] != category:
        return "judged", 0, "category_mismatch"
    requested = {**optional, **required}
    if requested.get("model_number") == product["model_number"]:
        return "judged", 4, "exact_model"
    dimensions = [(key, requested[key]) for key in DIMENSIONS if key in requested]
    same_category = category is not None and category == product["category"]
    if same_category and dimensions and all(_matches(k, v, product[k]) for k, v in dimensions):
        return "judged", 3, "dimensions_match"
    if same_category and all(
        key in requested and _matches(key, requested[key], product[key])
        for key in ("usage", "material")
    ):
        return "judged", 2, "usage_material_match"
    if same_category:
        return "judged", 1, "semantic_relation"
    return "judged", 0, "unrelated"


def judgment_rows(
    products: list[dict], queries: list[dict], gt_id: str, stats: dict
) -> Iterator[dict]:
    normalized_products = [(p["product_id"], normalize_product(p)) for p in products]
    normalized_products.sort(key=lambda pair: pair[0])
    # Cache only one family. Translation pairs share semantics, never a product/query label column.
    last_signature, decisions = None, None
    relevance_counts = Counter()
    for index, query in enumerate(sorted(queries, key=lambda row: row["query_id"])):
        normalized_query = normalize_query(query)
        signature = digest(normalized_query)
        if signature != last_signature:
            decisions = [judge(normalized_query, product) for _, product in normalized_products]
            last_signature = signature
        rows = [
            {
                "gt_id": gt_id,
                "query_id": query["query_id"],
                "product_id": product_id,
                "status": status,
                "relevance": relevance,
                "source": "rule",
                "reason": reason,
                "rule_version": GT_POLICY,
                "evidence_ids": [],
            }
            for (product_id, _), (status, relevance, reason) in zip(
                normalized_products, decisions, strict=True
            )
        ]
        check_records("Judgment", rows)
        judged = sum(row["status"] == "judged" for row in rows)
        stats["judged"] += judged
        stats["unrateable"] += len(rows) - judged
        stats["rows"] += len(rows)
        stats["queries"] += 1
        stats["complete_queries"] += judged == len(rows)
        stats["no_relevant_queries"] += judged == len(rows) and not any(
            row["relevance"] >= 2 for row in rows
        )
        relevance_counts.update(str(row["relevance"]) for row in rows if row["status"] == "judged")
        yield from rows
        if (index + 1) % 100 == 0:
            logger().info("judgments queries=%d/%d rows=%d", index + 1, len(queries), stats["rows"])
    if stats["rows"] != stats["expected_rows"]:
        raise FoundationError("Incomplete query-product coverage")
    stats["relevance_counts"] = dict(sorted(relevance_counts.items()))
    stats["status"] = (
        "complete" if stats["unrateable"] == 0 and queries and products else "inconclusive"
    )


def build_judgments(config: dict, dataset: Path) -> tuple[dict, dict]:
    if config["judgments"]["policyId"] != GT_POLICY:
        raise FoundationError("Unsupported GT policy")
    manifest = read_json(dataset / "manifest.json")
    verify_run(dataset)
    metadata = manifest.get("metadata", {})
    if metadata.get("stage") != "catalog" or metadata.get("implemented") is not True:
        raise FoundationError("Judgments require an implemented catalog artifact")
    if metadata.get("policy") != POLICY:
        raise FoundationError("Dataset attribute policy does not match supported policy")
    products = read_records("Product", dataset / "catalog.jsonl")
    queries = read_records("Query", dataset / "queries.jsonl")
    split = read_json(dataset / "splits.json")
    split.pop("schema_version")
    validate_dataset(products, queries, split)
    content = {"catalog": digest(products), "queryset": digest(queries), "split": digest(split)}
    if content != metadata.get("set_digests"):
        raise FoundationError("Dataset set digests disagree with input records")
    expected_ids = {
        "dataset_id": "dataset-" + digest(content)[:24],
        "queryset_id": "queryset-" + content["queryset"][:24],
        "split_id": split["split_id"],
    }
    if any(metadata.get(key) != value for key, value in expected_ids.items()):
        raise FoundationError("Dataset content identifiers disagree with input records")
    gt_id = "gt-" + digest([content, GT_POLICY, POLICY])[:24]
    stats = {
        "schema_version": 1,
        "gt_id": gt_id,
        "status": "not_run",
        "rows": 0,
        "expected_rows": len(products) * len(queries),
        "queries": 0,
        "products": len(products),
        "judged": 0,
        "unrateable": 0,
        "complete_queries": 0,
        "no_relevant_queries": 0,
    }
    output = {
        "judgments.jsonl.gz": judgment_rows(products, queries, gt_id, stats),
        "summary.json": stats,
    }
    provenance = {
        "gt_id": gt_id,
        "policy_id": GT_POLICY,
        "policy": POLICY,
        "dataset_id": metadata["dataset_id"],
        "queryset_id": metadata["queryset_id"],
        "split_id": split["split_id"],
        "input": {
            "artifact": str(dataset.resolve()),
            "run_id": manifest["run_id"],
            "manifest_checksum": file_checksum(dataset / "manifest.json"),
            "outputs": manifest["outputs"],
        },
        "counts": stats,
    }
    return output, provenance
