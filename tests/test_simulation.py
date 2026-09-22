"""T7/T8 の独立オラクル。実サービスを使わずに規約そのものを検査する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from parts_search.errors import FoundationError
from parts_search.pipelines import release as release_module
from parts_search.pipelines.simulation import (
    DuplicateEventError,
    _rate,
    add_event,
    policy_of,
    stream,
)
from parts_search.records.io import read_json

ROOT = Path(__file__).resolve().parents[1]


def config() -> dict:
    return yaml.safe_load((ROOT / "env/config.yaml").read_text())


# --- SimulationPolicy ---


def test_policy_must_be_versioned_before_simulating():
    unset = config()
    unset["simulation"]["policyVersion"] = None
    with pytest.raises(FoundationError, match="versioned"):
        policy_of(unset)
    disabled = config()
    disabled["simulation"]["enabled"] = False
    with pytest.raises(FoundationError, match="disabled"):
        policy_of(disabled)


def test_probabilities_must_be_set_before_simulating():
    partial = config()
    partial["simulation"]["clickProbability"]["relevant"] = None
    with pytest.raises(FoundationError, match="click probabilities"):
        policy_of(partial)


# --- paired random stream ---


def test_stream_is_deterministic_and_shared_between_variants():
    policy = config()["simulation"]
    assert stream(policy, "q-1", 0) == stream(policy, "q-1", 0)
    assert stream(policy, "q-1", 0) != stream(policy, "q-1", 1)
    assert stream(policy, "q-1", 0) != stream(policy, "q-2", 0)
    # variant を種に入れていないこと（同じ query/session なら baseline と candidate で同一）。
    assert all(0.0 <= value < 1.0 for value in stream(policy, "q-1", 0))


# --- event の冪等性 ---


def test_same_event_id_same_payload_is_harmless_but_conflict_is_an_error():
    events: dict[str, dict] = {}
    event = {"event_id": "e1", "event_type": "click", "product_id": "p1"}
    add_event(events, event)
    add_event(events, dict(event))
    assert len(events) == 1
    with pytest.raises(DuplicateEventError):
        add_event(events, {**event, "product_id": "p2"})


# --- 分母 0 ---


def test_zero_denominator_is_null_not_zero():
    assert _rate(0, 0) is None
    assert _rate(0, 4) == 0.0


# --- online guardrail ---


def test_guardrail_fails_when_a_kpi_is_unmeasured():
    policy = config()["qualityGate"]
    baseline = {"kpis": {"searchSuccessRate": 0.5, "wrongFitmentRate": None}}
    candidate = {"kpis": {"searchSuccessRate": 0.6, "wrongFitmentRate": None}}
    checks = release_module._guardrail(baseline, candidate, policy)
    assert [c["name"] for c in checks] == ["searchSuccessRate", "wrongFitmentRate"]
    assert checks[0]["passed"] is True
    # 未測定を合格にしない。
    assert checks[1] == {"name": "wrongFitmentRate", "passed": False, "reason": "denominator_zero"}


def test_guardrail_rejects_regression_beyond_policy():
    policy = config()["qualityGate"]
    checks = release_module._guardrail(
        {"kpis": {"searchSuccessRate": 0.90, "wrongFitmentRate": 0.010}},
        {"kpis": {"searchSuccessRate": 0.80, "wrongFitmentRate": 0.030}},
        policy,
    )
    assert [c["passed"] for c in checks] == [False, False]


# --- active 切替 ---


def _publish_release(tmp_path: Path, decision: str, *, smoke: bool = True) -> Path:
    from parts_search.runstore import publish_run

    bundle = json.loads((ROOT / "tests/fixtures/valid/ReleaseBundle.jsonl").read_text())
    return publish_run(
        tmp_path / "releases",
        f"rel-{decision}-{int(smoke)}",
        {
            "decision.json": {"schema_version": 1, "decision": decision},
            "smoke.json": {"schema_version": 1, "passed": smoke},
            "bundle.json": {"schema_version": 1, **bundle},
        },
        {
            "stage": "release",
            "implemented": True,
            "decision": decision,
            "smoke_passed": smoke,
        },
    )


def test_only_a_promoted_release_with_passing_smoke_can_become_active(tmp_path):
    active = tmp_path / "active.json"
    with pytest.raises(FoundationError, match="promoted"):
        release_module.activate(active, _publish_release(tmp_path, "reject"))
    with pytest.raises(FoundationError, match="Smoke"):
        release_module.activate(active, _publish_release(tmp_path, "promote", smoke=False))
    assert not active.exists()


def test_activate_then_rollback_restores_the_previous_reference(tmp_path):
    active = tmp_path / "active.json"
    first = _publish_release(tmp_path, "promote")
    payload = release_module.activate(active, first)
    assert read_json(active)["release_id"] == payload["release_id"]
    with pytest.raises(FoundationError, match="previous"):
        release_module.rollback(active)

    second_bundle = json.loads((ROOT / "tests/fixtures/valid/ReleaseBundle.jsonl").read_text())
    second_bundle["release_id"] = "release-hand-2"
    from parts_search.runstore import publish_run

    second = publish_run(
        tmp_path / "releases",
        "rel-promote-second",
        {
            "decision.json": {"schema_version": 1, "decision": "promote"},
            "smoke.json": {"schema_version": 1, "passed": True},
            "bundle.json": {"schema_version": 1, **second_bundle},
        },
        {"stage": "release", "implemented": True, "decision": "promote", "smoke_passed": True},
    )
    release_module.activate(active, second)
    assert read_json(active)["release_id"] == "release-hand-2"
    restored = release_module.rollback(active)
    assert restored["release_id"] == "release-hand"
    assert read_json(active)["release_id"] == "release-hand"
    # 履歴は残す。成果物は削除しない。
    history = [
        json.loads(line) for line in (tmp_path / "active-history.jsonl").read_text().splitlines()
    ]
    assert [row["event"] for row in history] == ["activate", "activate", "rollback"]
    assert first.exists() and second.exists()


def test_rollback_refuses_a_changed_previous_bundle(tmp_path):
    active = tmp_path / "active.json"
    first = _publish_release(tmp_path, "promote")
    release_module.activate(active, first)
    payload = read_json(active)
    payload["previous"] = {
        "release_path": str(first),
        "manifest_checksum": "0" * 64,
        "release_id": "release-hand",
    }
    active.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(FoundationError, match="manual recovery"):
        release_module.rollback(active)
