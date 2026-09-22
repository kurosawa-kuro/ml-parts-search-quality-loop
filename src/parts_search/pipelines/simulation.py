"""Pseudo-online simulation: paired event streams, joined KPIs, explicit nulls.

版付き SimulationPolicy が無ければ開始しない（`docs/05_data_model.md`）。
baseline と candidate は**同じ query・session 割当・乱数 stream**で比較する。
分母 0 は null で保持し、失敗を KPI 0 へ変換しない。
"""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from parts_search.errors import FoundationError
from parts_search.pipelines.inputs import artifact, dataset_rows, gt_groups, reference, search_rows
from parts_search.pipelines.synthetic import check_records, digest

IMPRESSION_SIZE = 10
# 05: relevance>=2 が正解。click model は relevant(>=3) / marginal(==2) / irrelevant に分ける。
RELEVANT, MARGINAL = 3, 2


class DuplicateEventError(FoundationError):
    """同一 event_id で payload が異なる（05: 無害な重複と区別する）。"""


def policy_of(config: dict) -> dict:
    policy = config["simulation"]
    required = (
        "policyId",
        "policyVersion",
        "observationWindowSeconds",
        "behaviorModel",
        "sessionsPerQuery",
        "conversionProbabilityGivenClick",
        "lateInteractionSeconds",
        "seed",
    )
    if not policy.get("enabled"):
        raise FoundationError("Simulation is disabled in configuration")
    if any(policy.get(key) is None for key in required):
        raise FoundationError("Simulation policy is not fully versioned")
    if policy["behaviorModel"] != "position_biased_cascade_v1":
        raise FoundationError("Unsupported simulation behavior model")
    if policy["positionBias"]["model"] != "inverse_rank_power":
        raise FoundationError("Unsupported position bias model")
    if any(value is None for value in policy["clickProbability"].values()):
        raise FoundationError("Simulation click probabilities are not set")
    if any(value is None for value in policy["reformulationProbability"].values()):
        raise FoundationError("Simulation reformulation probabilities are not set")
    return policy


def stream(policy: dict, query_id: str, session_index: int) -> list[float]:
    """Deterministic paired stream. 同じ query/session なら variant 間で同一。

    variant（baseline / candidate）を種に入れない。入れると「同じ乱数 stream で
    比較する」条件が壊れ、KPI 差が behaviour ではなく乱数差になる。
    """
    material = f"{policy['policyVersion']}|{policy['seed']}|{query_id}|{session_index}"
    values: list[float] = []
    counter = 0
    while len(values) < 4 * IMPRESSION_SIZE + 8:
        block = hashlib.sha256(f"{material}|{counter}".encode()).digest()
        values.extend(int.from_bytes(block[i : i + 8], "big") / 2**64 for i in range(0, 32, 8))
        counter += 1
    return values


def add_event(events: dict[str, dict], event: dict) -> None:
    """同一 payload の重複は無害、異なる payload は誤り（05）。"""
    existing = events.get(event["event_id"])
    if existing is None:
        events[event["event_id"]] = event
        return
    if existing != event:
        raise DuplicateEventError("Conflicting payload for an existing event_id")


def _rate(numerator: int, denominator: int) -> float | None:
    """分母 0 は null。**0 に丸めない**（06 の 0/null 区別）。"""
    return numerator / denominator if denominator else None


def build_simulation(
    config: dict,
    dataset: Path,
    judgments: Path,
    search: Path,
    run_id: str,
    *,
    release_id: str | None = None,
    split: str | None = None,
):
    policy = policy_of(config)
    split_name = split or policy["developmentSplit"]
    dm, products, queries, splits = dataset_rows(dataset)
    sm, _candidates, results, outcomes = search_rows(search, dm, queries, products)
    gm = artifact(judgments, "judgments")
    query_map = {q["query_id"]: q for q in queries}
    window = int(policy["observationWindowSeconds"])
    decay = float(policy["positionBias"]["decay"])
    click_probability = policy["clickProbability"]
    reformulation = policy["reformulationProbability"]

    events: dict[str, dict] = {}
    impressions: list[dict] = []
    quarantined: list[dict] = []
    failures: list[dict] = []
    gt_candidates: list[dict] = []
    for qid, gt in gt_groups(judgments, dm, queries, products):
        query = query_map[qid]
        if splits["assignments"][query["family_id"]] != split_name:
            continue
        outcome = outcomes[qid]
        labels = {pid: row["relevance"] for pid, row in gt.items() if row["status"] == "judged"}
        ranked = [r["product_id"] for r in sorted(results.get(qid, []), key=lambda r: r["rank"])]
        shown = ranked[:IMPRESSION_SIZE]
        for session_index in range(int(policy["sessionsPerQuery"])):
            draws = stream(policy, qid, session_index)
            session_id = f"{qid}-s{session_index}"
            impression_id = f"{run_id}-{session_id}"
            base_time = 1_000_000 + session_index * (window + 1)
            impression = {
                "event_id": f"{impression_id}-impression",
                "event_type": "impression",
                "event_time": base_time,
                "session_id": session_id,
                "run_id": run_id,
                "query_id": qid,
                "simulation_policy_id": policy["policyId"],
                "impression_id": impression_id,
                # 0 件でも空 items で 1 回記録する（05）。
                "items": [{"rank": i + 1, "product_id": pid} for i, pid in enumerate(shown)],
                "release_id": release_id,
                "product_id": None,
                "next_query_id": None,
            }
            add_event(events, impression)
            clicked: list[str] = []
            converted = False
            if outcome["status"] == "succeeded":
                for index, pid in enumerate(shown):
                    rank = index + 1
                    examine, click, convert = draws[index * 3 : index * 3 + 3]
                    if examine >= 1.0 / rank**decay:
                        continue
                    label = labels.get(pid)
                    kind = (
                        "relevant"
                        if label is not None and label >= RELEVANT
                        else "marginal"
                        if label == MARGINAL
                        else "irrelevant"
                    )
                    if click >= click_probability[kind]:
                        continue
                    clicked.append(pid)
                    add_event(
                        events,
                        {
                            "event_id": f"{impression_id}-click-{rank}",
                            "event_type": "click",
                            "event_time": base_time + rank,
                            "session_id": session_id,
                            "run_id": run_id,
                            "query_id": qid,
                            "simulation_policy_id": policy["policyId"],
                            "impression_id": impression_id,
                            "items": [],
                            "release_id": None,
                            "product_id": pid,
                            "next_query_id": None,
                        },
                    )
                    if convert < float(policy["conversionProbabilityGivenClick"]):
                        converted = True
                        add_event(
                            events,
                            {
                                "event_id": f"{impression_id}-conversion-{rank}",
                                "event_type": "conversion",
                                "event_time": base_time + rank + 1,
                                "session_id": session_id,
                                "run_id": run_id,
                                "query_id": qid,
                                "simulation_policy_id": policy["policyId"],
                                "impression_id": impression_id,
                                "items": [],
                                "release_id": None,
                                "product_id": pid,
                                "next_query_id": None,
                            },
                        )
                    break  # cascade: 最初の click で離脱する
            kind = "zeroResult" if not shown else ("afterClick" if clicked else "noClick")
            reformulated = draws[-1] < reformulation[kind]
            late = draws[-2] < 0.02
            if reformulated:
                offset = int(policy["lateInteractionSeconds"]) if late else window // 2
                event = {
                    "event_id": f"{impression_id}-reformulation",
                    "event_type": "reformulation",
                    "event_time": base_time + offset,
                    "session_id": session_id,
                    "run_id": run_id,
                    "query_id": qid,
                    "simulation_policy_id": policy["policyId"],
                    "impression_id": impression_id,
                    "items": [],
                    "release_id": None,
                    "product_id": None,
                    "next_query_id": qid,
                }
                add_event(events, event)
                # 観測窓を越えた遅着は結合せず隔離する（05）。KPI の母集合に入れない。
                if offset > window:
                    quarantined.append(event)
                    reformulated = False
            top_label = labels.get(shown[0]) if shown else None
            impressions.append(
                {
                    "impression_id": impression_id,
                    "query_id": qid,
                    "session_id": session_id,
                    "status": outcome["status"],
                    "window_closed": True,
                    "items": len(shown),
                    "top_label": top_label,
                    "clicked": bool(clicked),
                    "converted": converted,
                    "reformulated": reformulated,
                    "language": query["language"],
                    "query_type": query["query_type"],
                    "category": query["category"],
                }
            )
            for pid in clicked:
                label = labels.get(pid)
                if label is None or label < MARGINAL:
                    # implicit feedback は GT 候補どまり。自動昇格しない（05・要件 AC）。
                    gt_candidates.append(
                        {
                            "query_id": qid,
                            "product_id": pid,
                            "observed_label": label,
                            "source": "implicit_click",
                            "promoted_to_evaluation_gt": False,
                            "simulation_run_id": run_id,
                        }
                    )
        if shown and (labels.get(shown[0]) or 0) < MARGINAL:
            failures.append(
                {
                    "failure_id": f"{run_id}-{qid}",
                    "query_id": qid,
                    "run_id": run_id,
                    "evidence_ids": [sm["run_id"], gm["metadata"]["gt_id"]],
                    "category": "simulation_miss",
                    "description": "Top result is not relevant in the simulated impression",
                    "next_experiment_id": None,
                }
            )

    if config["judgments"]["promoteImplicitToEvaluation"]:
        raise FoundationError("Implicit feedback must not be promoted into evaluation GT")
    joined = [row for row in impressions if row["window_closed"] and row["status"] == "succeeded"]
    non_empty = [row for row in joined if row["items"]]
    failed = [row for row in impressions if row["status"] != "succeeded"]
    kpis = {
        "searchSuccessRate": _rate(
            sum(1 for row in joined if (row["top_label"] or 0) >= MARGINAL), len(joined)
        ),
        "ctr": _rate(sum(1 for row in joined if row["clicked"]), len(joined)),
        "zeroResultRate": _rate(sum(1 for row in joined if not row["items"]), len(joined)),
        "reformulationRate": _rate(sum(1 for row in joined if row["reformulated"]), len(joined)),
        "conversionRate": _rate(sum(1 for row in joined if row["converted"]), len(joined)),
        # 補助指標。必須条件違反（relevance 0）が最上位に出た非空 impression の割合。
        "wrongFitmentRate": _rate(
            sum(1 for row in non_empty if row["top_label"] == 0), len(non_empty)
        ),
    }
    check_records("Event", list(events.values()))
    check_records("FailureCase", failures)
    counts = Counter(event["event_type"] for event in events.values())
    complete = not failed and not quarantined
    return {
        "events.jsonl": sorted(events.values(), key=lambda e: (e["event_time"], e["event_id"])),
        "impressions.jsonl": impressions,
        "kpis.json": {
            "schema_version": 1,
            "simulation_run_id": run_id,
            "policy_id": policy["policyId"],
            "policy_version": policy["policyVersion"],
            "split": split_name,
            "search_run_id": sm["run_id"],
            "kpis": kpis,
            "denominators": {
                "impressions": len(impressions),
                "joined_impressions": len(joined),
                "non_empty_impressions": len(non_empty),
                "failed_impressions": len(failed),
                "quarantined_events": len(quarantined),
                "events": dict(counts),
            },
            # 1 件でも失敗・未結合が残れば正式比較は inconclusive（05）。
            "comparison_ready": complete,
            "blocking_reasons": [
                reason
                for reason, present in (
                    ("failed_impressions", bool(failed)),
                    ("unjoined_events", bool(quarantined)),
                )
                if present
            ],
        },
        "failures.jsonl": failures,
        "gt_candidates.jsonl": gt_candidates,
        "quarantine.jsonl": quarantined,
    }, {
        "dataset_digests": dm["metadata"]["set_digests"],
        "dataset": reference(dataset),
        "judgments": reference(judgments),
        "search": reference(search),
        "policy": policy,
        "policy_checksum": digest(policy),
        "split": split_name,
        "release_id": release_id,
        "comparison_ready": complete,
    }
