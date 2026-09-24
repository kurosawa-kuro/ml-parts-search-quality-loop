"""Verified artifact boundaries shared by search, evaluation and training."""

from __future__ import annotations

from itertools import groupby
from pathlib import Path

from parts_search.errors import FoundationError
from parts_search.pipelines.synthetic import digest, validate_dataset
from parts_search.records.io import iter_judgments, read_json, read_records
from parts_search.records.validate import validate_query_coverage
from parts_search.runstore import file_checksum, verify_run


def artifact(path: Path, stage: str | tuple[str, ...]) -> dict:
    manifest = read_json(path / "manifest.json")
    verify_run(path)
    stages = (stage,) if isinstance(stage, str) else stage
    if manifest.get("metadata", {}).get("stage") not in stages or not manifest["metadata"].get(
        "implemented"
    ):
        raise FoundationError("Unexpected or unimplemented input artifact")
    return manifest


def reference(path: Path) -> dict:
    return {"path": str(path.resolve()), "manifest_checksum": file_checksum(path / "manifest.json")}


def dataset_rows(path: Path):
    manifest = artifact(path, "catalog")
    products = read_records("Product", path / "catalog.jsonl")
    queries = read_records("Query", path / "queries.jsonl")
    splits = read_json(path / "splits.json")
    splits.pop("schema_version")
    validate_dataset(products, queries, splits)
    content = {"catalog": digest(products), "queryset": digest(queries), "split": digest(splits)}
    if content != manifest["metadata"].get("set_digests"):
        raise FoundationError("Dataset content mismatch")
    return manifest, products, queries, splits


def search_rows(path: Path, dataset: dict, queries: list[dict], products: list[dict]):
    manifest = artifact(path, ("retrieval", "training"))
    if manifest["metadata"].get("dataset_digests") != dataset["metadata"]["set_digests"]:
        raise FoundationError("SearchRun uses a different dataset")
    candidates = read_records("Candidate", path / "candidates.jsonl.gz")
    results = read_records("SearchResult", path / "results.jsonl.gz")
    outcomes = read_records("QueryOutcome", path / "outcomes.jsonl")
    if validate_query_coverage(queries, outcomes):
        raise FoundationError("SearchRun does not cover QuerySet")
    qids, pids = {q["query_id"] for q in queries}, {p["product_id"] for p in products}
    for rows in (candidates, results, outcomes):
        for row in rows:
            if row["query_id"] not in qids or (
                "product_id" in row and row["product_id"] not in pids
            ):
                raise FoundationError("SearchRun contains unknown query or product")
    cgroup, rgroup = {}, {}
    for row in candidates:
        cgroup.setdefault(row["query_id"], []).append(row)
    for row in results:
        rgroup.setdefault(row["query_id"], []).append(row)
    for rows in cgroup.values():
        if sorted(r["source_rank"] for r in rows) != list(range(1, len(rows) + 1)):
            raise FoundationError("Candidate ranks are not contiguous")
        if len({r["product_id"] for r in rows}) != len(rows):
            raise FoundationError("CandidateSet is not deduplicated")
    for outcome in outcomes:
        qid = outcome["query_id"]
        returned = rgroup.get(qid, [])
        if len(returned) != outcome["returned_count"]:
            raise FoundationError("Outcome count differs from results")
        if outcome["status"] != "succeeded" and (returned or cgroup.get(qid)):
            raise FoundationError("Failed query contains search results")
        if not {r["product_id"] for r in returned} <= {
            r["product_id"] for r in cgroup.get(qid, [])
        }:
            raise FoundationError("Result is outside CandidateSet")
    if any(r["run_id"] != manifest["run_id"] for r in results + outcomes):
        raise FoundationError("SearchRun identity mismatch")
    return manifest, cgroup, rgroup, {r["query_id"]: r for r in outcomes}


def gt_groups(path: Path, dataset: dict, queries: list[dict], products: list[dict]):
    manifest = artifact(path, "judgments")
    if manifest["metadata"].get("input", {}).get("outputs") != dataset["outputs"]:
        raise FoundationError("Ground truth uses a different dataset")
    expected_queries = sorted(q["query_id"] for q in queries)
    expected_products = {p["product_id"] for p in products}
    observed = []
    for qid, rows in groupby(iter_judgments(path), key=lambda r: r["query_id"]):
        group = {r["product_id"]: r for r in rows}
        if set(group) != expected_products:
            raise FoundationError("Ground truth does not cover the full catalog")
        observed.append(qid)
        yield qid, group
    if observed != expected_queries:
        raise FoundationError("Ground truth does not cover QuerySet")
