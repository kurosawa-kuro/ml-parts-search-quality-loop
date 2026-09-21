"""Independent rule examples plus saved-data/streaming/CLI T2 acceptance tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from parts_search.config.loader import Settings
from parts_search.errors import FoundationError
from parts_search.pipelines.judgments import build_judgments, judge
from parts_search.pipelines.skeleton import run_stage
from parts_search.pipelines.synthetic import (
    build_dataset,
    digest,
    millimeters,
    normalize_product,
    normalize_query,
    validate_dataset,
)
from parts_search.records.io import iter_judgments, read_json, read_records
from parts_search.runstore import file_checksum, publish_run, verify_run

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    value = yaml.safe_load((REPO / "env/config.yaml").read_text())
    value["catalog"]["skuCount"] = 30
    value["queries"]["familyCount"] = 20
    return value


@pytest.fixture
def settings(tmp_path, config):
    return Settings({}, config, tmp_path, tmp_path / "artifacts")


# Handwritten independently of build_dataset, including deliberate near misses.
@pytest.fixture
def product():
    return {
        "product_id": "p",
        "category": "shaft",
        "model_number": "ABC-10",
        "texts": {"en": {"title": "Test shaft", "description": "Independent fixture"}},
        "attributes": {
            "diameter": {"value": 10, "unit": "mm"},
            "length": {"value": 2, "unit": "cm"},
            "material": "steel",
            "usage": "guiding",
            "standard": "SYN-SHAFT-V1",
        },
    }


def query(required=None, optional=None, category="shaft"):
    return {
        "query_id": "q",
        "family_id": "f",
        "text": "Independent query",
        "language": "en",
        "query_type": "natural_language",
        "category": category,
        "constraints": {"required": required or {}, "optional": optional or {}},
    }


def evaluate(q, p):
    return judge(normalize_query(q), normalize_product(p))


@pytest.mark.parametrize(
    ("required", "optional", "expected"),
    [
        ({}, {"model_number": "ABC-10"}, 4),
        ({"diameter": {"value": 1, "unit": "cm"}}, {}, 3),
        ({}, {"usage": "guiding", "material": "steel"}, 2),
        ({}, {"usage": "guiding"}, 1),
        ({"diameter": {"value": 11, "unit": "mm"}}, {"model_number": "ABC-10"}, 0),
        ({"material": "stainless"}, {"model_number": "ABC-10"}, 0),
        ({"standard": "OTHER"}, {"model_number": "ABC-10"}, 0),
        ({"diameter": {"value": 10.01, "unit": "mm"}}, {}, 3),
        ({"diameter": {"value": 10.011, "unit": "mm"}}, {}, 0),
    ],
)
def test_gt_priority_and_grades(product, required, optional, expected):
    assert evaluate(query(required, optional), product)[:2] == ("judged", expected)


def test_other_category_and_no_semantic_evidence_are_zero(product):
    assert evaluate(query(category="bolt"), product)[:2] == ("judged", 0)
    assert evaluate(query(category=None), product)[:2] == ("judged", 0)


def test_missing_is_unrateable_and_zero_is_known(product):
    q = query({"diameter": {"value": 0, "unit": "mm"}})
    product["attributes"]["diameter"] = None
    assert evaluate(q, product)[:2] == ("unrateable", None)
    product["attributes"]["diameter"] = {"value": 0, "unit": "mm"}
    assert evaluate(q, product)[:2] == ("judged", 3)
    del product["attributes"]["diameter"]
    assert evaluate(q, product)[2] == "missing_evidence"


def test_contradiction_is_unrateable(product):
    q = query({"diameter": {"min": 11, "max": 9, "unit": "mm"}})
    assert evaluate(q, product) == ("unrateable", None, "contradictory_constraints")
    assert evaluate(query({"category": "bolt"}), product)[0] == "unrateable"


def test_units_and_unknown_constraints_rejected(product):
    assert millimeters(1, "in") == 25.4
    assert millimeters(1, "m") == 1000
    for bad in [float("nan"), float("inf"), -1, True]:
        with pytest.raises(FoundationError):
            millimeters(bad, "mm")
    with pytest.raises(FoundationError, match="supported unit"):
        millimeters(1, "feet")
    with pytest.raises(FoundationError, match="Unsupported constraint"):
        evaluate(query({"future_label": 4}), product)
    product["attributes"]["diameter"]["original"] = {"value": 3, "unit": "cm"}
    with pytest.raises(FoundationError, match="Original dimension"):
        normalize_product(product)


def test_generation_is_deterministic_and_translations_stay_in_family(config):
    outputs, metadata = build_dataset(config)
    assert (outputs, metadata) == build_dataset(copy.deepcopy(config))
    assert metadata["counts"]["family_splits"] == {
        "train": 12,
        "tuning": 3,
        "holdout": 3,
        "production": 2,
    }
    assert metadata["counts"]["languages"] == {"en": 20, "ja": 20}
    families = {}
    for q in outputs["queries.jsonl"]:
        families.setdefault(q["family_id"], []).append(q)
        assert set(q["constraints"]) == {"required", "optional"}
        serialized = json.dumps(q)
        for forbidden in ("gt_id", "rule_id", "relevance", "target_product_id", "label", "future"):
            assert forbidden not in serialized
    for translations in families.values():
        assert len(translations) == 2
        assert translations[0]["constraints"] == translations[1]["constraints"]
    changed = copy.deepcopy(config)
    changed["split"]["seed"] += 1
    other, _ = build_dataset(changed)
    assert outputs["splits.json"]["assignments"] != other["splits.json"]["assignments"]
    assert outputs["catalog.jsonl"] == other["catalog.jsonl"]
    changed = copy.deepcopy(config)
    changed["catalog"]["seed"] += 1
    assert build_dataset(changed)[1]["set_digests"]["catalog"] != metadata["set_digests"]["catalog"]


def test_split_and_leakage_checks(config):
    outputs, _ = build_dataset(config)
    products, queries = outputs["catalog.jsonl"], outputs["queries.jsonl"]
    split = outputs["splits.json"].copy()
    split.pop("schema_version")
    for mutation in ("unknown", "missing", "count", "digest", "overlap"):
        bad = copy.deepcopy(split)
        if mutation == "unknown":
            bad["assignments"]["family-000000"] = "validation"
        elif mutation == "missing":
            del bad["assignments"]["family-000000"]
        elif mutation == "count":
            bad["counts"]["train"] += 1
        elif mutation == "overlap":
            bad["assignments"]["family-000000"] = ["train", "holdout"]
        else:
            bad["set_digest"] = "invalid"
        with pytest.raises(FoundationError):
            validate_dataset(products, queries, bad)
    bad_queries = copy.deepcopy(queries)
    bad_queries[0]["constraints"]["required"]["gt_rule_id"] = "hidden"
    with pytest.raises(FoundationError, match="Unsupported constraint"):
        validate_dataset(products, bad_queries, split)
    bad_queries = copy.deepcopy(queries)
    bad_queries[0]["constraints"]["required"]["standard"] = "different"
    with pytest.raises(FoundationError, match="Translations disagree"):
        validate_dataset(products, bad_queries, split)


def test_family_intent_cannot_cross_splits(config):
    outputs, _ = build_dataset(config)
    split = outputs["splits.json"].copy()
    split.pop("schema_version")
    queries = outputs["queries.jsonl"]
    # Two complete translation pairs now share one semantic intent but different families.
    for i in (2, 3):
        for field in ("constraints", "query_type", "category"):
            queries[i][field] = copy.deepcopy(queries[0][field])
    with pytest.raises(FoundationError, match="cross families"):
        validate_dataset(outputs["catalog.jsonl"], queries, split)


def test_publish_full_gt_and_read_in_batches(settings):
    dataset = Path(run_stage(settings, "catalog")["artifact"])
    repeated = Path(run_stage(settings, "catalog")["artifact"])
    assert verify_run(dataset)["outputs"] == verify_run(repeated)["outputs"]
    result = run_stage(settings, "judgments", dataset=dataset)
    assert result["status"] == "completed"
    artifact = Path(result["artifact"])
    rows = list(iter_judgments(artifact, batch_size=7))
    products = read_records("Product", dataset / "catalog.jsonl")
    queries = read_records("Query", dataset / "queries.jsonl")
    assert {(r["query_id"], r["product_id"]) for r in rows} == {
        (q["query_id"], p["product_id"]) for q in queries for p in products
    }
    assert len(rows) == 1200
    for row in rows:
        p = next(p for p in products if p["product_id"] == row["product_id"])
        q = next(q for q in queries if q["query_id"] == row["query_id"])
        assert (row["status"], row["relevance"], row["reason"]) == evaluate(q, p)
    summary = read_json(artifact / "summary.json")
    assert summary["rows"] == summary["judged"] == 1200
    assert summary["unrateable"] == 0 and summary["status"] == "complete"
    assert summary["complete_queries"] == 40
    assert summary["no_relevant_queries"] == 0
    again = Path(run_stage(settings, "judgments", dataset=repeated)["artifact"])
    assert verify_run(artifact)["outputs"] == verify_run(again)["outputs"]
    assert verify_run(artifact)["metadata"]["input"]["manifest_checksum"] == file_checksum(
        dataset / "manifest.json"
    )


def test_missing_input_blocks_and_corrupt_or_placeholder_input_fails(settings):
    assert run_stage(settings, "judgments")["blockers"] == ["input.dataset"]
    assert not (settings.artifacts_root / "judgments").exists()
    dataset = Path(run_stage(settings, "catalog")["artifact"])
    (dataset / "queries.jsonl").write_text("{}\n")
    with pytest.raises(FoundationError, match="checksum"):
        run_stage(settings, "judgments", dataset=dataset)
    placeholder = publish_run(
        settings.artifacts_root / "datasets", "placeholder", {"catalog.jsonl": []}, {}
    )
    with pytest.raises(FoundationError, match="implemented catalog"):
        build_judgments(settings.config, placeholder)


def test_interrupted_stream_is_never_published(tmp_path):
    def broken():
        yield {"value": 1}
        raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError, match="interrupted"):
        publish_run(tmp_path, "broken", {"rows.jsonl": broken()}, {})
    assert list(tmp_path.iterdir()) == []


def test_large_reader_checks_version_and_batch_boundary_duplicates(settings):
    dataset = Path(run_stage(settings, "catalog")["artifact"])
    artifact = Path(run_stage(settings, "judgments", dataset=dataset)["artifact"])
    rows = list(iter_judgments(artifact))[:2]
    rows.append(rows[-1])
    summary = {"schema_version": 1, "rows": 3, "expected_rows": 3}
    duplicate = publish_run(
        settings.artifacts_root / "judgments",
        "duplicate",
        {"judgments.jsonl": rows, "summary.json": summary},
        {"stage": "judgments", "implemented": True, "gt_id": rows[0]["gt_id"]},
    )
    with pytest.raises(FoundationError, match="duplicated"):
        list(iter_judgments(duplicate, batch_size=2))
    summary["schema_version"] = 99
    unsupported = publish_run(
        settings.artifacts_root / "judgments",
        "unsupported",
        {"judgments.jsonl": rows[:1], "summary.json": summary},
        {"stage": "judgments", "implemented": True, "gt_id": rows[0]["gt_id"]},
    )
    with pytest.raises(FoundationError, match="schema_version"):
        list(iter_judgments(unsupported))


def test_saved_dataset_with_missing_evidence_produces_inconclusive_gt(settings):
    outputs, metadata = build_dataset(settings.config)
    for p in outputs["catalog.jsonl"]:
        p["attributes"]["material"] = None
    metadata["set_digests"]["catalog"] = digest(outputs["catalog.jsonl"])
    dataset = publish_run(
        settings.artifacts_root / "datasets",
        "missing",
        outputs,
        {**metadata, "stage": "catalog", "implemented": True},
    )
    artifact = Path(run_stage(settings, "judgments", dataset=dataset)["artifact"])
    summary = read_json(artifact / "summary.json")
    assert summary["status"] == "inconclusive"
    assert summary["unrateable"] == 1200 and summary["judged"] == 0
    assert all(row["relevance"] is None for row in iter_judgments(artifact))


def test_handwritten_split_manifest(product):
    split = read_json(REPO / "tests/fixtures/valid/splits.json")
    split.pop("schema_version")
    queries = []
    for index, family in enumerate(("f1", "f2", "f3", "f4")):
        q = query(optional={"model_number": f"MODEL-{index}"})
        q.update(query_id=f"q{index}", family_id=family)
        queries.append(q)
    validate_dataset([product], queries, split)


def test_equivalent_units_and_different_type_do_not_hide_family_leak(product):
    split = read_json(REPO / "tests/fixtures/valid/splits.json")
    split.pop("schema_version")
    queries = []
    for index, family in enumerate(("f1", "f2", "f3", "f4")):
        q = query(required={"diameter": {"value": index + 10, "unit": "mm"}})
        q.update(query_id=f"q{index}", family_id=family)
        queries.append(q)
    queries[1]["constraints"]["required"]["diameter"] = {"value": 1, "unit": "cm"}
    queries[1]["query_type"] = "dimension_sensitive"
    with pytest.raises(FoundationError, match="cross families"):
        validate_dataset([product], queries, split)


def test_unsupported_policy_and_insufficient_skus_fail_without_publication(settings):
    settings.config["catalog"]["attributePolicyId"] = "future_policy"
    with pytest.raises(FoundationError, match="Unsupported attribute"):
        run_stage(settings, "catalog")
    assert not settings.artifacts_root.exists()
    settings.config["catalog"]["attributePolicyId"] = "fa_parts_attr_v1"
    settings.config["queries"]["familyCount"] = 31
    with pytest.raises(FoundationError, match="must not exceed"):
        run_stage(settings, "catalog")
    assert not settings.artifacts_root.exists()


def test_streaming_reader_rejects_truncation_and_wrong_gt(settings):
    dataset = Path(run_stage(settings, "catalog")["artifact"])
    artifact = Path(run_stage(settings, "judgments", dataset=dataset)["artifact"])
    rows = list(iter_judgments(artifact))[:2]
    metadata = {"stage": "judgments", "implemented": True, "gt_id": rows[0]["gt_id"]}
    for name, expected, wrong_id in (("truncated", 3, False), ("wrong-gt", 2, True)):
        if wrong_id:
            rows[0]["gt_id"] = "wrong"
        path = publish_run(
            settings.artifacts_root / "judgments",
            name,
            {
                "judgments.jsonl": rows,
                "summary.json": {"schema_version": 1, "rows": expected, "expected_rows": expected},
            },
            metadata,
        )
        with pytest.raises(FoundationError):
            list(iter_judgments(path, batch_size=1))
