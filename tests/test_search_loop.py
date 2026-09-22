"""Small independent oracles; heavy/service execution is explicitly integration marked."""

import copy
from pathlib import Path

import pytest
import yaml

from parts_search.config.loader import Settings
from parts_search.errors import FoundationError
from parts_search.pipelines.evaluation import measure_query
from parts_search.pipelines.gate import compare
from parts_search.pipelines.release import SMOKE_STAGES, activate
from parts_search.pipelines.retrieval import preprocess, ranked_points
from parts_search.pipelines.skeleton import run_stage
from parts_search.pipelines.training import feature_schema, features, load_model
from parts_search.records.io import iter_jsonl, read_json, read_records

ROOT = Path(__file__).resolve().parents[1]


def test_independent_metric_oracle_and_gain_not_squared():
    result = measure_query({"a": 4, "b": 3, "c": 0}, ["b", "c", "a"], ["a", "b", "c"])
    assert result["ndcgAt10"] == pytest.approx(0.7309292742059024, abs=1e-9)
    assert result["recallAt100"] == 1 and result["mrrAt100"] == 1
    assert measure_query({"a": 4, "b": 3, "c": 0}, ["c", "a", "b"], ["a"])["mrrAt100"] == 0.5
    assert measure_query({"a": 4}, [], []) == {"ndcgAt10": 0, "recallAt100": 0, "mrrAt100": 0}


def test_preprocessing_normalizes_model_and_prefix():
    assert preprocess(" 型番 ＳＨＦ−２０ ", "query") == "query: 型番 SHF-20"


def test_features_do_not_accept_or_use_label():
    q = {
        "category": "shaft",
        "constraints": {
            "required": {"diameter": {"value": 1, "unit": "cm"}},
            "optional": {"material": "steel"},
        },
    }
    p = {
        "category": "shaft",
        "model_number": "ABC-10",
        "attributes": {"diameter": {"value": 10, "unit": "mm"}, "material": "steel"},
    }
    values, mask = features(q, p, 0.5)
    assert values == [0.5, None, 1, 0, None, 1, None, None]
    assert mask == [False, True, False, False, True, False, True, True]
    q["relevance"] = 4
    assert features(q, p, 0.5) == (values, mask)
    schema = feature_schema("parts_features_v1")
    assert [c["name"] for c in schema["columns"]][0] == "vector_score"


def test_offline_gate_small_slice_and_signature_are_inconclusive():
    config = yaml.safe_load((ROOT / "env/config.yaml").read_text())
    row = {
        "query_id": "q",
        "split": "tuning",
        "status": "complete",
        "language": "en",
        "query_type": "natural_language",
        "category": "shaft",
        "ndcgAt10": 0.5,
        "recallAt100": 1,
        "mrrAt100": 1,
    }
    result = compare(
        {"comparison_signature": "a"},
        {"comparison_signature": "b"},
        [row],
        [row],
        config["qualityGate"],
    )
    assert result["verdict"] == "inconclusive"
    assert "comparison_signature_mismatch" in result["reasons"]


def test_real_local_qdrant_tie_boundary():
    from qdrant_client import QdrantClient, models

    client = QdrantClient(":memory:")
    client.create_collection(
        "tie", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE)
    )
    client.upsert(
        "tie",
        points=[
            models.PointStruct(id=i, vector=[1.0, 0.0], payload={"product_id": pid})
            for i, pid in enumerate(["z", "a", "m", "b"])
        ],
    )
    assert [p.payload["product_id"] for p in ranked_points(client, "tie", [1.0, 0.0], 2, 4)] == [
        "a",
        "b",
    ]
    client.close()


def test_missing_search_inputs_block_without_side_effects(tmp_path):
    config = yaml.safe_load((ROOT / "env/config.yaml").read_text())
    settings = Settings({}, config, tmp_path, tmp_path / "artifacts")
    for stage in ("retrieval", "evaluation", "training", "gate"):
        result = run_stage(settings, stage)
        assert result["status"] == "blocked" and result["artifact"] is None
    assert not settings.artifacts_root.exists()


@pytest.mark.integration
def test_e5_qdrant_evaluation_training_and_comparison(tmp_path):
    """Actual server and cached pinned model; one integrated run, no fake embeddings."""
    import numpy as np
    from qdrant_client import QdrantClient

    config = yaml.safe_load((ROOT / "env/config.yaml").read_text())
    config["catalog"]["skuCount"] = 120
    config["queries"]["familyCount"] = 40
    settings = Settings({}, config, tmp_path, tmp_path / "artifacts")
    ds = Path(run_stage(settings, "catalog")["artifact"])
    gt = Path(run_stage(settings, "judgments", dataset=ds)["artifact"])
    retrieval = run_stage(settings, "retrieval", dataset=ds)
    assert retrieval["status"] == "completed", retrieval
    search = Path(retrieval["artifact"])
    candidates = read_records("Candidate", search / "candidates.jsonl")
    assert len(candidates) == 80 * 100
    baseline = Path(
        run_stage(settings, "evaluation", dataset=ds, judgments=gt, search=search)["artifact"]
    )
    assert read_json(baseline / "metrics.json")["status"] == "complete"
    evaluated = []
    for seed in config["qualityGate"]["repetitionSeeds"]:
        config["ranker"]["seed"] = seed
        trained = Path(
            run_stage(settings, "training", dataset=ds, judgments=gt, search=search)["artifact"]
        )
        schema = read_json(trained / "feature_schema.json")
        schema.pop("schema_version")
        payload = read_json(trained / "model.json")
        model = load_model(payload, schema)
        feature_rows = read_records("FeatureRow", trained / "features.jsonl")
        predicted = model.predict(
            np.asarray([r["values"] for r in feature_rows], dtype=float), num_threads=2
        )
        expected = {
            (r["query_id"], r["product_id"]): float(v)
            for r, v in zip(feature_rows, predicted, strict=True)
        }
        for r in read_records("SearchResult", trained / "results.jsonl"):
            assert r["score"] == pytest.approx(expected[r["query_id"], r["product_id"]])
        broken = copy.deepcopy(schema)
        broken["columns"].reverse()
        with pytest.raises(FoundationError, match="checksum"):
            load_model(payload, broken)
        evaluated.append(
            Path(
                run_stage(settings, "evaluation", dataset=ds, judgments=gt, search=trained)[
                    "artifact"
                ]
            )
        )
    gate = Path(run_stage(settings, "gate", baseline=baseline, evaluations=evaluated)["artifact"])
    decision = read_json(gate / "decision.json")
    assert decision["repetition_complete"]
    assert (
        decision["decision"] == "inconclusive"
    )  # Small slices and no independent online evidence.
    assert all(c["split"] == "tuning" for c in decision["comparisons"])
    # --- T7: 疑似オンライン。baseline と candidate は同じ split・同じ乱数 stream ---
    validation = config["simulation"]["validationSplit"]
    sim_baseline = Path(
        run_stage(
            settings, "simulation", dataset=ds, judgments=gt, search=search, split=validation
        )["artifact"]
    )
    sim_candidate = Path(
        run_stage(
            settings, "simulation", dataset=ds, judgments=gt, search=trained, split=validation
        )["artifact"]
    )
    left = read_json(sim_baseline / "kpis.json")
    right = read_json(sim_candidate / "kpis.json")
    assert left["denominators"]["joined_impressions"] > 0
    assert left["split"] == validation and right["split"] == validation
    # 同じ query・session 割当で比較していること（impression の集合が一致）。
    sessions = {
        path: {row["session_id"] for row in read_records("Event", path / "events.jsonl")}
        for path in (sim_baseline, sim_candidate)
    }
    assert sessions[sim_baseline] == sessions[sim_candidate]
    # 0 件 impression も 1 回記録し、分母 0 の KPI は null で保持する。
    impressions = [
        row
        for row in read_records("Event", sim_baseline / "events.jsonl")
        if row["event_type"] == "impression"
    ]
    assert len(impressions) == left["denominators"]["impressions"]
    assert all(value is None or 0.0 <= value <= 1.0 for value in left["kpis"].values())
    # implicit click は GT 候補どまり。独立評価 GT へ自動反映しない。
    candidates_for_gt = list(iter_jsonl(sim_candidate / "gt_candidates.jsonl"))
    assert all(not row["promoted_to_evaluation_gt"] for row in candidates_for_gt)

    # --- T8: 独立評価（holdout）＋ guardrail → decision → bundle → 切替 ---
    released = run_stage(settings, "release", gate=gate, simulations=[sim_baseline, sim_candidate])
    assert released["status"] == "completed", released
    release_dir = Path(released["artifact"])
    decision_record = read_json(release_dir / "decision.json")
    smoke = read_json(release_dir / "smoke.json")
    assert decision_record["decision"] in ("promote", "reject", "inconclusive")
    assert decision_record["gate_results"]["holdout"] in ("accepted", "rejected", "inconclusive")
    assert [stage["stage"] for stage in smoke["stages"]] == list(SMOKE_STAGES)
    assert (
        smoke["next_experiment"]["parent_experiment_id"]
        == read_json(gate / "experiment.json")["experiment_id"]
    )
    active = settings.root / config["paths"]["activeRelease"]
    if decision_record["decision"] == "promote":
        assert (release_dir / "bundle.json").exists()
        activate(active, release_dir)
        assert read_json(active)["release_id"] == decision_record["release_id"]
    else:
        # accepted でない候補を active へ昇格できない。
        assert not (release_dir / "bundle.json").exists()
        with pytest.raises(FoundationError, match="promoted"):
            activate(active, release_dir)

    index = read_json(search / "index.json")
    client = QdrantClient(url=config["retrieval"]["qdrant"]["url"])
    client.delete_collection(index["collection"])
    client.close()


@pytest.mark.parametrize(
    "name",
    [
        "Candidate",
        "FeatureRow",
        "FeatureSchema",
        "ModelBundle",
        "Experiment",
        "Evaluation",
        "FailureCase",
        "PromotionDecision",
        "Event",
        "ReleaseBundle",
    ],
)
def test_independent_normal_record_fixtures(name):
    assert read_records(name, ROOT / "tests/fixtures/valid" / f"{name}.jsonl")


@pytest.mark.parametrize("mode", ["empty", "timeout", "unavailable"])
def test_retrieval_failure_is_not_successful_empty(tmp_path, mode):
    from types import SimpleNamespace

    from parts_search.pipelines.retrieval import build_retrieval

    config = yaml.safe_load((ROOT / "env/config.yaml").read_text())
    config["catalog"]["skuCount"] = 30
    config["queries"]["familyCount"] = 20
    config["retry"]["backoffSeconds"] = [0, 0]
    settings = Settings({}, config, tmp_path, tmp_path / "artifacts")
    ds = Path(run_stage(settings, "catalog")["artifact"])

    class Encoder:
        def encode(self, texts, kind):
            return [[1.0, 0.0] for _ in texts]

    class Client:
        def get_collections(self):
            if mode == "unavailable":
                raise ConnectionError("private endpoint must not leak")

        def create_collection(self, *args, **kwargs):
            pass

        def upsert(self, *args, **kwargs):
            pass

        def count(self, *args, **kwargs):
            return SimpleNamespace(count=30)

        def query_points(self, *args, **kwargs):
            if mode == "timeout":
                raise TimeoutError("private endpoint must not leak")
            return SimpleNamespace(points=[])

    outputs, metadata = build_retrieval(
        config, ds, "failure-oracle", encoder=Encoder(), client=Client()
    )
    assert not outputs["candidates.jsonl"] and not outputs["results.jsonl"]
    assert len(outputs["outcomes.jsonl"]) == 40
    for row in outputs["outcomes.jsonl"]:
        assert row["returned_count"] == 0
        assert row["status"] == ("succeeded" if mode == "empty" else "failed")
        assert (
            row["error_code"]
            == {"empty": None, "timeout": "timeout", "unavailable": "dependency_unavailable"}[mode]
        )
        assert row["attempt"] == (3 if mode == "timeout" else 1)
    assert metadata["failed_queries"] == (0 if mode == "empty" else 40)
