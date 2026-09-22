"""Frozen offline comparison with signature, coverage, slice and repetition guards."""

from __future__ import annotations

from pathlib import Path

from parts_search.errors import FoundationError
from parts_search.pipelines.evaluation import METRICS, aggregate
from parts_search.pipelines.inputs import artifact, reference
from parts_search.pipelines.synthetic import check_records, digest
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
    if any(
        row["status"] not in ("complete", "no_relevant")
        for row in [*left_rows.values(), *r.values()]
    ):
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
        "per_query_delta": [
            {
                "query_id": qid,
                **{
                    metric: r[qid][metric] - left_rows[qid][metric]
                    if r[qid][metric] is not None and left_rows[qid][metric] is not None
                    else None
                    for metric in METRICS
                },
            }
            for qid in sorted(set(left_rows) & set(r))
        ],
    }


def build_gate(
    config: dict,
    baseline: Path,
    evaluations: list[Path],
    run_id: str,
    *,
    parent_experiment_id: str | None = None,
    retry_of: str | None = None,
):
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
        "parent_experiment_id": parent_experiment_id,
        "retry_of": retry_of,
    }
    search_manifest = artifact(Path(bm["metadata"]["search"]["path"]), ("retrieval", "training"))
    dm = artifact(Path(bm["metadata"]["dataset"]["path"]), "catalog")
    if retry_of is not None and parent_experiment_id is None:
        # 再試行は系譜を切らない。元実験を親として残す（既存 run は変更しない）。
        parent_experiment_id = retry_of
    experiment = {
        "experiment_id": run_id,
        "parent_experiment_id": parent_experiment_id,
        "hypothesis": "Structured features improve reranking on fixed vector candidates",
        "dataset_id": dm["metadata"]["dataset_id"],
        "queryset_id": dm["metadata"]["queryset_id"],
        "gt_id": b["gt_id"],
        "split_id": dm["metadata"]["split_id"],
        "metric_policy_id": b["metric_policy_id"],
        "variants": refs,
        "seed": policy["repetitionSeeds"][0],
        "compared_runs": {
            "baseline": b["search_run_id"],
            "candidates": [c["evaluation_id"] for c in comparisons],
        },
    }
    decision = {
        "decision_id": run_id,
        "baseline_run_id": search_manifest["run_id"],
        "candidate_run_id": c["search_run_id"] if comparisons else "not_run",
        "policy_id": policy["policyId"],
        "comparison": {"repetitions": comparisons},
        "denominators": {"repetitions": len(comparisons)},
        "gate_results": {"offline": offline, "repetition_complete": complete},
        "decision": "inconclusive",
        "reason": "Independent holdout and simulation required",
        "release_id": None,
    }
    check_records("Experiment", [experiment])
    check_records("PromotionDecision", [decision])
    return {
        "experiment.json": {"schema_version": 1, **experiment},
        "decision.json": {**result, "record": decision},
    }, {
        "policy": policy,
        "baseline": reference(baseline),
        "candidates": refs,
        "offline_verdict": offline,
        "decision": "inconclusive",
        "parent_experiment_id": parent_experiment_id,
        "retry_of": retry_of,
    }
