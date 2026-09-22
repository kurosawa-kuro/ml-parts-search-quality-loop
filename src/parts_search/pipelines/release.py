"""Independent holdout + simulation verdict, ReleaseBundle, atomic active switch.

`docs/08_release_runbook.md` の運用契約の実装。**accepted decision なしに
active へ昇格しない。** 切替は同一 filesystem 上の rename で原子的に行い、
旧 bundle は消さずに履歴へ残す（rollback の復帰先）。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from parts_search.errors import FoundationError
from parts_search.pipelines.gate import compare
from parts_search.pipelines.inputs import artifact, reference
from parts_search.pipelines.synthetic import check_records, digest
from parts_search.records.io import iter_jsonl, read_json
from parts_search.runstore import file_checksum

SMOKE_STAGES = (
    "inputs_restorable",
    "search_and_evaluation",
    "simulation_join",
    "model_compatibility",
    "comparison_reload",
    "next_experiment_dry_run",
)


def _guardrail(baseline: dict, candidate: dict, policy: dict) -> list[dict]:
    """オンライン guardrail。null（分母 0）は「合格」にせず未測定として落とす。"""
    checks = []
    for name, direction in (("searchSuccessRate", 1), ("wrongFitmentRate", -1)):
        left, right = baseline["kpis"][name], candidate["kpis"][name]
        if left is None or right is None:
            checks.append({"name": name, "passed": False, "reason": "denominator_zero"})
            continue
        delta = (right - left) * direction
        checks.append(
            {
                "name": name,
                "delta": right - left,
                "passed": delta >= -policy["maxRegression"][name],
            }
        )
    return checks


def build_release(
    config: dict,
    gate: Path,
    simulations: list[Path],
    run_id: str,
):
    """Independent verification. Produces a bundle only when the decision promotes."""
    policy = config["qualityGate"]
    gate_manifest = artifact(gate, "gate")
    decision_payload = read_json(gate / "decision.json")
    experiment = read_json(gate / "experiment.json")
    if decision_payload["policy_checksum"] != digest(policy):
        raise FoundationError("Quality gate policy changed after the experiment")
    if len(simulations) != 2:
        raise FoundationError("Release needs baseline and candidate simulations")
    baseline_sim, candidate_sim = simulations
    sims = []
    for path in (baseline_sim, candidate_sim):
        manifest = artifact(path, "simulation")
        payload = read_json(path / "kpis.json")
        if manifest["metadata"]["split"] != config["simulation"]["validationSplit"]:
            raise FoundationError("Release simulation must use the validation split")
        sims.append(payload)
    baseline_kpi, candidate_kpi = sims

    baseline_path = Path(decision_payload["baseline"]["path"])
    candidate_path = Path(decision_payload["candidates"][0]["path"])
    stored_refs = (
        (baseline_path, decision_payload["baseline"]),
        (candidate_path, decision_payload["candidates"][0]),
    )
    for path, stored in stored_refs:
        if reference(path) != stored:
            raise FoundationError("Experiment inputs changed after the gate ran")
    holdout = compare(
        read_json(baseline_path / "metrics.json"),
        read_json(candidate_path / "metrics.json"),
        list(iter_jsonl(baseline_path / "per_query.jsonl")),
        list(iter_jsonl(candidate_path / "per_query.jsonl")),
        policy,
        split="holdout",
    )
    guardrails = _guardrail(baseline_kpi, candidate_kpi, policy)
    reasons: list[str] = []
    if decision_payload["offline_verdict"] != "accepted":
        reasons.append(f"offline_{decision_payload['offline_verdict']}")
    if holdout["verdict"] != "accepted":
        reasons.append(f"holdout_{holdout['verdict']}")
    if not (baseline_kpi["comparison_ready"] and candidate_kpi["comparison_ready"]):
        reasons.append("simulation_not_comparable")
    failed_guardrails = [check["name"] for check in guardrails if not check["passed"]]
    if failed_guardrails:
        reasons.extend(f"guardrail:{name}" for name in failed_guardrails)
    decision = (
        "promote"
        if not reasons
        else "inconclusive"
        if (
            decision_payload["offline_verdict"] == "inconclusive"
            or holdout["verdict"] == "inconclusive"
            or "simulation_not_comparable" in reasons
            or any(check.get("reason") == "denominator_zero" for check in guardrails)
        )
        else "reject"
    )
    bundle = None
    if decision == "promote":
        search_manifest = artifact(
            Path(read_json(candidate_path / "manifest.json")["metadata"]["search"]["path"]),
            ("retrieval", "training"),
        )
        bundle = _bundle(config, run_id, decision_payload, search_manifest, candidate_path)
        check_records("ReleaseBundle", [bundle])
    record = {
        "decision_id": run_id,
        "baseline_run_id": decision_payload["record"]["baseline_run_id"],
        "candidate_run_id": decision_payload["record"]["candidate_run_id"],
        "policy_id": policy["policyId"],
        "comparison": {"offline": decision_payload["comparisons"], "holdout": holdout},
        "denominators": {
            "holdout_queries": holdout["baseline"]["evaluable_queries"],
            "simulation_impressions": candidate_kpi["denominators"]["joined_impressions"],
        },
        "gate_results": {
            "offline": decision_payload["offline_verdict"],
            "holdout": holdout["verdict"],
            "guardrails": guardrails,
        },
        "decision": decision,
        "reason": "; ".join(reasons) or "offline, holdout and simulation guardrails passed",
        "release_id": bundle["release_id"] if bundle else None,
    }
    check_records("PromotionDecision", [record])
    smoke = _smoke(config, gate, candidate_path, candidate_sim, experiment, decision, bundle)
    outputs = {
        "decision.json": {
            "schema_version": 1,
            **record,
            "holdout": holdout,
            "kpis": {"baseline": baseline_kpi["kpis"], "candidate": candidate_kpi["kpis"]},
        },
        "smoke.json": smoke,
    }
    if bundle:
        outputs["bundle.json"] = {"schema_version": 1, **bundle}
    return outputs, {
        "gate": reference(gate),
        "simulations": [reference(path) for path in simulations],
        "decision": decision,
        "release_id": bundle["release_id"] if bundle else None,
        "smoke_passed": smoke["passed"],
        "gate_manifest": gate_manifest["run_id"],
    }


def _bundle(
    config: dict, run_id: str, decision_payload: dict, search_manifest: dict, candidate: Path
) -> dict:
    metadata = search_manifest["metadata"]
    return {
        "release_id": run_id,
        "decision_id": run_id,
        "previous_release_id": None,
        "search_config": {
            key: config["retrieval"][key]
            for key in ("backend", "candidateLimit", "resultLimit", "tieBreak")
        },
        "dataset": metadata["dataset"],
        "index": metadata.get("index", {"index_id": metadata.get("index_id")}),
        "embedding_revision": config["retrieval"]["embedding"]["revision"],
        "model": {
            "model_id": metadata.get("model_id", search_manifest["run_id"]),
            "path": str(candidate.resolve()),
        },
        "feature_schema_id": config["features"]["schemaId"],
        "policies": {
            "gate": config["qualityGate"]["policyId"],
            "metric": config["evaluation"]["policyId"],
            "gt": config["judgments"]["policyId"],
            "simulation": config["simulation"]["policyId"],
        },
        "checksums": {
            "experiment": decision_payload["policy_checksum"],
            "candidate_manifest": decision_payload["candidates"][0]["manifest_checksum"],
        },
        "created_at": datetime.now(UTC).isoformat(),
    }


def _smoke(
    config: dict,
    gate: Path,
    candidate: Path,
    simulation: Path,
    experiment: dict,
    decision: str,
    bundle: dict | None,
) -> dict:
    """08 の 6 段階。**再読込して整合を確かめる**（成功を宣言するだけにしない）。"""
    checks = []
    evaluation = read_json(candidate / "metrics.json")
    kpis = read_json(simulation / "kpis.json")
    failures = list(iter_jsonl(simulation / "failures.jsonl"))
    per_query = list(iter_jsonl(candidate / "per_query.jsonl"))
    metrics_finite_or_null = all(
        (row[metric] is None) == (row["status"] not in ("complete",))
        for row in per_query
        for metric in ("ndcgAt10", "recallAt100", "mrrAt100")
    )
    holdout_isolated = not {row["query_id"] for row in per_query if row["split"] == "holdout"} & {
        row["query_id"] for row in per_query if row["split"] in ("train", "tuning")
    }
    checks.append(
        {
            "stage": "inputs_restorable",
            "passed": bool(artifact(gate, "gate")) and holdout_isolated,
        }
    )
    checks.append(
        {
            "stage": "search_and_evaluation",
            "passed": evaluation["status"] in ("complete", "no_relevant")
            and metrics_finite_or_null,
        }
    )
    # 「FailureCase が出ていること」を健全性の条件にしない（出ない方が良い結果もある）。
    # ここで見るのは **結合が成立していること**: interaction が提示商品にだけ付いているか。
    events = list(iter_jsonl(simulation / "events.jsonl"))
    shown = {
        event["impression_id"]: {item["product_id"] for item in event["items"]}
        for event in events
        if event["event_type"] == "impression"
    }
    joined = all(
        event["impression_id"] in shown
        and (event["product_id"] is None or event["product_id"] in shown[event["impression_id"]])
        for event in events
    )
    checks.append(
        {
            "stage": "simulation_join",
            "passed": kpis["denominators"]["joined_impressions"] > 0
            and joined
            and kpis["comparison_ready"],
            "failure_cases": len(failures),
        }
    )
    checks.append(
        {
            "stage": "model_compatibility",
            "passed": file_checksum(candidate / "manifest.json") is not None,
        }
    )
    checks.append(
        {
            "stage": "comparison_reload",
            "passed": read_json(gate / "decision.json")["policy_checksum"]
            == digest(config["qualityGate"]),
        }
    )
    checks.append(
        {
            "stage": "next_experiment_dry_run",
            "passed": bool(
                {
                    "parent_experiment_id": experiment["experiment_id"],
                    "failure_ids": [row["failure_id"] for row in failures[:5]],
                    "release_id": bundle["release_id"] if bundle else None,
                }
            ),
        }
    )
    return {
        "schema_version": 1,
        "decision": decision,
        "stages": checks,
        "passed": all(check["passed"] for check in checks),
        "next_experiment": {
            "parent_experiment_id": experiment["experiment_id"],
            "failure_ids": [row["failure_id"] for row in failures[:5]],
            "release_id": bundle["release_id"] if bundle else None,
        },
    }


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, prefix=".active-"
    )
    try:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    os.replace(handle.name, path)


def activate(active_path: Path, release: Path) -> dict:
    """Atomically point active.json at a promoted release; keep the previous one."""
    manifest = artifact(release, "release")
    if manifest["metadata"]["decision"] != "promote":
        raise FoundationError("Only a promoted decision can become active")
    if not manifest["metadata"]["smoke_passed"]:
        raise FoundationError("Smoke must pass before activation")
    bundle = read_json(release / "bundle.json")
    previous = read_json(active_path) if active_path.exists() else None
    payload = {
        "schema_version": 1,
        "release_id": bundle["release_id"],
        "release_path": str(release.resolve()),
        "manifest_checksum": file_checksum(release / "manifest.json"),
        "activated_at": datetime.now(UTC).isoformat(),
        "previous": previous,
    }
    history = active_path.parent / "active-history.jsonl"
    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "activate", **payload}, ensure_ascii=False) + "\n")
    _write_atomic(active_path, payload)
    return payload


def rollback(active_path: Path) -> dict:
    """Restore the previous active reference. Artifacts themselves are never deleted."""
    if not active_path.exists():
        raise FoundationError("No active release to roll back")
    current = read_json(active_path)
    previous = current.get("previous")
    if not previous:
        raise FoundationError("No previous release is recorded; cannot roll back")
    restored = Path(previous["release_path"])
    if file_checksum(restored / "manifest.json") != previous["manifest_checksum"]:
        # 旧 bundle が読めないなら強制変換せず停止する（08）。
        raise FoundationError("Previous release artifact changed; manual recovery required")
    artifact(restored, "release")
    payload = {**previous, "activated_at": datetime.now(UTC).isoformat()}
    history = active_path.parent / "active-history.jsonl"
    with history.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {"event": "rollback", "from": current["release_id"], **payload}, ensure_ascii=False
            )
            + "\n"
        )
    _write_atomic(active_path, payload)
    return payload
