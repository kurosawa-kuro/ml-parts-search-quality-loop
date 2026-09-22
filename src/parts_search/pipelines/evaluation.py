"""Query-complete evaluation with bounded-memory GT and explicit missing states."""

from __future__ import annotations

from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path

from parts_search.errors import FoundationError
from parts_search.pipelines.inputs import artifact, dataset_rows, gt_groups, reference, search_rows
from parts_search.pipelines.synthetic import check_records, digest

METRICS = ("ndcgAt10", "recallAt100", "mrrAt100")


def measure_query(labels: dict[str, int], ranked: list[str], candidates: list[str]) -> dict:
    import ir_measures as ir

    gains = (0, 0, 1, 3, 7)
    qrels = [ir.Qrel("q", pid, gains[label]) for pid, label in labels.items()]
    ranked_run = [ir.ScoredDoc("q", pid, float(len(ranked) - i)) for i, pid in enumerate(ranked)]
    candidate_run = [
        ir.ScoredDoc("q", pid, float(len(candidates) - i)) for i, pid in enumerate(candidates)
    ]
    metrics = ir.calc_aggregate([ir.nDCG @ 10, ir.RR(rel=1) @ 100], qrels, ranked_run)
    recall = ir.calc_aggregate([ir.Recall(rel=1) @ 100], qrels, candidate_run)
    return {
        "ndcgAt10": metrics[ir.nDCG @ 10],
        "mrrAt100": metrics[ir.RR(rel=1) @ 100],
        "recallAt100": recall[ir.Recall(rel=1) @ 100],
    }


def aggregate(rows: list[dict]) -> dict:
    counts = Counter(r["status"] for r in rows)
    values = {}
    for metric in METRICS:
        available = [r[metric] for r in rows if r[metric] is not None]
        values[metric] = sum(available) / len(available) if available else None
    return {
        "metrics": values,
        "target_queries": len(rows),
        "evaluable_queries": counts["complete"],
        "missing_queries": sum(counts[k] for k in ("failed", "not_run", "unrateable")),
        "no_relevant_queries": counts["no_relevant"],
        "statuses": dict(counts),
    }


def build_evaluation(config: dict, dataset: Path, judgments: Path, search: Path, run_id: str):
    policy = config["evaluation"]
    expected = {
        "ndcgCutoff": 10,
        "recallCutoff": 100,
        "mrrCutoff": 100,
        "relevanceThreshold": 2,
        "gainByRelevance": [0, 0, 1, 3, 7],
        "dcgFormula": "gain_over_log2_rank_plus_one",
        "aggregation": "query_macro",
        "noRelevantPolicy": "exclude_and_report",
        "incompletePolicy": "inconclusive",
    }
    if (
        policy["policyId"] != "parts_metrics_v1"
        or policy["version"] != version("ir_measures")
        or policy["provider"] != "ir_measures"
        or any(policy.get(key) != value for key, value in expected.items())
    ):
        raise FoundationError("Unsupported metric policy/provider version")
    dm, products, queries, split = dataset_rows(dataset)
    sm, candidates, results, outcomes = search_rows(search, dm, queries, products)
    gm = artifact(judgments, "judgments")
    query_map = {q["query_id"]: q for q in queries}
    per_query, failures = [], []
    for qid, gt in gt_groups(judgments, dm, queries, products):
        query, outcome = query_map[qid], outcomes[qid]
        ranked = [r["product_id"] for r in sorted(results.get(qid, []), key=lambda r: r["rank"])]
        candidate = [
            r["product_id"] for r in sorted(candidates.get(qid, []), key=lambda r: r["source_rank"])
        ][:100]
        complete = all(r["status"] == "judged" for r in gt.values())
        labels = {pid: r["relevance"] for pid, r in gt.items() if r["status"] == "judged"}
        positive = {pid for pid, label in labels.items() if label >= 2}
        status = (
            outcome["status"]
            if outcome["status"] != "succeeded"
            else ("unrateable" if not complete else "complete" if positive else "no_relevant")
        )
        values = (
            measure_query(labels, ranked[:100], candidate)
            if status == "complete"
            else dict.fromkeys(METRICS)
        )
        row = {
            "query_id": qid,
            "status": status,
            **values,
            "split": split["assignments"][query["family_id"]],
            "family_id": query["family_id"],
            "language": query["language"],
            "query_type": query["query_type"],
            "category": query["category"],
            "judgment_coverage": sum(pid in labels for pid in ranked[:100]) / len(ranked[:100])
            if ranked
            else None,
            "gt_complete": complete,
            "relevant_products": len(positive),
        }
        per_query.append(row)
        category = None
        if status in ("failed", "not_run"):
            category = "execution_failure"
        elif not complete:
            category = "gt_defect"
        elif positive and positive - set(candidate):
            category = "retrieval_miss"
        elif positive and (not ranked or ranked[0] not in positive):
            category = "rerank_miss"
        if category:
            failures.append(
                {
                    "failure_id": f"{run_id}-{qid}",
                    "query_id": qid,
                    "run_id": sm["run_id"],
                    "evidence_ids": [sm["run_id"], gm["metadata"]["gt_id"]],
                    "category": category,
                    "description": category,
                    "next_experiment_id": None,
                }
            )
    summary = aggregate(per_query)
    status = (
        "inconclusive"
        if summary["missing_queries"] or not per_query
        else ("complete" if summary["evaluable_queries"] else "no_relevant")
    )
    slices = []
    for dimension in ("split", *policy["slices"]):
        groups = defaultdict(list)
        for row in per_query:
            groups[row[dimension]].append(row)
        for key, rows in sorted(groups.items(), key=lambda item: str(item[0])):
            slices.append({"dimension": dimension, "value": key, **aggregate(rows)})
    signature = digest(
        {
            "dataset": dm["outputs"],
            "gt": gm["outputs"],
            "metric": policy,
            "simulation": config["simulation"],
        }
    )
    evaluation = {
        "evaluation_id": run_id,
        "search_run_id": sm["run_id"],
        "candidate_run_id": sm["metadata"]["candidate_run_id"],
        "gt_id": gm["metadata"]["gt_id"],
        "metric_policy_id": policy["policyId"],
        "comparison_signature": signature,
        "status": status,
        "per_query": per_query,
        "aggregate": summary["metrics"],
        "denominators": {k: v for k, v in summary.items() if k != "metrics"},
        "coverage": {
            "complete_queries": sum(r["gt_complete"] for r in per_query),
            "queries": len(per_query),
        },
    }
    check_records("Evaluation", [evaluation])
    check_records("FailureCase", failures)
    return {
        "metrics.json": {"schema_version": 1, **evaluation},
        "per_query.jsonl": per_query,
        "slices.jsonl": slices,
        "failures.jsonl": failures,
    }, {
        "dataset_digests": dm["metadata"]["set_digests"],
        "dataset": reference(dataset),
        "judgments": reference(judgments),
        "search": reference(search),
        "policy": policy,
        "comparison_signature": signature,
        "candidate_checksum": sm["outputs"]["candidates.jsonl"],
        "evaluation_status": status,
    }
