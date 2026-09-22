"""Frozen offline comparison with signature, coverage, slice and repetition guards."""

from __future__ import annotations

from pathlib import Path

from parts_search.errors import FoundationError
from parts_search.pipelines.evaluation import METRICS, aggregate
from parts_search.pipelines.inputs import artifact, reference
from parts_search.pipelines.synthetic import digest
from parts_search.records.io import iter_jsonl, read_json


def compare(
    baseline: dict, candidate: dict, left: list, right: list, policy: dict, *, split="tuning"
):
    reasons = []
    if baseline["comparison_signature"] != candidate["comparison_signature"]:
        reasons.append("comparison_signature_mismatch")
    left_rows = {r["query_id"]: r for r in left if r["split"] == split}
    r = {row["query_id"]: row for row in right if row["split"] == split}
    if not left_rows or set(left_rows) != set(r):
        reasons.append("query_set_mismatch_or_empty")
    if any(row["status"] not in ("complete", "no_relevant") for row in [*left_rows.values(), *r.values()]):
        reasons.append("incomplete_evaluation")
    a, b = aggregate(list(left_rows.values())), aggregate(list(r.values()))
    if a["evaluable_queries"] != b["evaluable_queries"] or not a["evaluable_queries"]:
        reasons.append("evaluable_denominator_mismatch_or_zero")
    deltas = {
        k: b["metrics"][k] - a["metrics"][k]
        if a["metrics"][k] is not None and b["metrics"][k] is not None
        else None
        for k in METRICS
    }
    guards = []
    if deltas["ndcgAt10"] is not None:
        guards.append(
            {"name": "ndcg_improvement", "passed": deltas["ndcgAt10"] >= policy["minNdcgDelta"]}
        )
    for metric in ("recallAt100", "mrrAt100"):
        if deltas[metric] is not None:
            guards.append(
                {"name": metric, "passed": deltas[metric] >= -policy["maxRegression"][metric]}
            )
    for dimension in ("language", "query_type", "category"):
        keys = {row[dimension] for row in [*left_rows.values(), *r.values()]}
        for key in sorted(keys, key=str):
            aa = aggregate([row for row in left_rows.values() if row[dimension] == key])
            bb = aggregate([row for row in r.values() if row[dimension] == key])
            if min(aa["evaluable_queries"], bb["evaluable_queries"]) < policy["minSliceQueries"]:
                reasons.append(f"slice_too_small:{dimension}:{key}")
            elif aa["metrics"]["ndcgAt10"] is not None and bb["metrics"]["ndcgAt10"] is not None:
                guards.append(
                    {
                        "name": f"slice:{dimension}:{key}",
                        "passed": bb["metrics"]["ndcgAt10"] - aa["metrics"]["ndcgAt10"]
                        >= -policy["maxRegression"]["sliceNdcgAt10"],
                    }
                )
    verdict = (
        "inconclusive"
        if reasons
        else "accepted"
        if guards and all(g["passed"] for g in guards)
        else "rejected"
    )
    return {
        "verdict": verdict,
        "reasons": reasons,
        "delta": deltas,
        "guards": guards,
        "split": split,
        "baseline": a,
        "candidate": b,
    }


def build_gate(config: dict, baseline: Path, evaluations: list[Path], run_id: str):
    policy = config["qualityGate"]
    bm = artifact(baseline, "evaluation")
    b = read_json(baseline / "metrics.json")
    left = list(iter_jsonl(baseline / "per_query.jsonl"))
    comparisons = []
    seeds = []
    refs = []
    for path in evaluations:
        cm = artifact(path, "evaluation")
        c = read_json(path / "metrics.json")
        training_path = Path(cm["metadata"]["search"]["path"])
        tm = artifact(training_path, "training")
        if reference(training_path) != cm["metadata"]["search"]:
            raise FoundationError("Candidate evaluation references changed model artifact")
        if tm["metadata"].get("quality_gate_checksum") != digest(policy):
            raise FoundationError("Quality gate policy changed after candidate training")
        seed = tm["metadata"]["seed"]
        seeds.append(seed)
        comparison = compare(b, c, left, list(iter_jsonl(path / "per_query.jsonl")), policy)
        if bm["metadata"]["candidate_checksum"] != cm["metadata"]["candidate_checksum"]:
            comparison["verdict"] = "inconclusive"
            comparison["reasons"].append("candidate_set_mismatch")
        comparisons.append({"seed": seed, "evaluation_id": c["evaluation_id"], **comparison})
        refs.append(reference(path))
    complete = sorted(seeds) == sorted(policy["repetitionSeeds"]) and len(seeds) == len(set(seeds))
    offline = (
        "inconclusive"
        if not complete or any(c["verdict"] == "inconclusive" for c in comparisons)
        else (
            "accepted"
            if comparisons and all(c["verdict"] == "accepted" for c in comparisons)
            else "rejected"
        )
    )
    # Online guardrails and independent holdout remain required; never issue a promotion here.
    result = {
        "schema_version": 1,
        "experiment_id": run_id,
        "policy": policy,
        "policy_checksum": digest(policy),
        "baseline": reference(baseline),
        "candidates": refs,
        "comparisons": comparisons,
        "repetition_complete": complete,
        "offline_verdict": offline,
        "decision": "inconclusive",
        "reasons": ["independent_holdout_and_simulation_required"],
        "release_id": None,
    }
    return {"experiment.json": result, "decision.json": result}, {
        "policy": policy,
        "baseline": reference(baseline),
        "candidates": refs,
        "offline_verdict": offline,
        "decision": "inconclusive",
    }
