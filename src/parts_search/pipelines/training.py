"""Explicit label-free features; train-only LambdaRank, portable JSON model bundle."""

from __future__ import annotations

import math
from importlib.metadata import version
from pathlib import Path

from parts_search.errors import FoundationError
from parts_search.pipelines.inputs import dataset_rows, gt_groups, reference, search_rows
from parts_search.pipelines.synthetic import (
    DIMENSIONS,
    check_records,
    digest,
    normalize_product,
    normalize_query,
)

FEATURE_NAMES = (
    "vector_score",
    "model_exact",
    "category_exact",
    "diameter_delta",
    "length_delta",
    "material_exact",
    "standard_exact",
    "usage_exact",
)


def feature_schema(schema_id: str) -> dict:
    if schema_id != "parts_features_v1":
        raise FoundationError("Unsupported feature schema")
    schema = {
        "schema_id": schema_id,
        "columns": [
            {"name": n, "type": "float64", "default": None, "null": "nan_with_mask"}
            for n in FEATURE_NAMES
        ],
        "transform_version": "parts_features_v1",
        "normalization": {"dimensions": "absolute_mm", "categorical": "exact"},
    }
    return {**schema, "checksum": digest(schema)}


def features(query: dict, product: dict, score: float) -> tuple[list, list]:
    q, p = normalize_query(query), normalize_product(product)
    requested = {**q["optional"], **q["required"]}
    values = [float(score)]
    for key in ("model_number", "category", *DIMENSIONS, "material", "standard", "usage"):
        expected = q["category"] if key == "category" else requested.get(key)
        actual = p.get(key)
        if expected is None or actual is None:
            values.append(None)
        elif key in DIMENSIONS:
            values.append(abs(actual - (expected[0] + expected[1]) / 2))
        else:
            values.append(float(expected == actual))
    return values, [v is None for v in values]


def load_model(payload: dict, schema: dict):
    import lightgbm as lgb

    stored = dict(schema)
    checksum = stored.pop("checksum")
    if digest(stored) != checksum or payload["feature_schema_checksum"] != checksum:
        raise FoundationError("Feature schema checksum mismatch")
    if payload["label_gain"] != [0, 0, 1, 3, 7]:
        raise FoundationError("Model gain policy mismatch")
    model = lgb.Booster(model_str=payload["model_text"])
    if model.feature_name() != [c["name"] for c in schema["columns"]]:
        raise FoundationError("Model feature order mismatch")
    return model


def build_training(config: dict, dataset: Path, judgments: Path, search: Path, run_id: str):
    import lightgbm as lgb
    import numpy as np

    dm, products, queries, split = dataset_rows(dataset)
    sm, candidates, results, outcomes = search_rows(search, dm, queries, products)
    if any(o["status"] != "succeeded" for o in outcomes.values()):
        raise FoundationError("Cannot train from failed or unexecuted query outcomes")
    schema = feature_schema(config["features"]["schemaId"])
    pmap, qmap = {p["product_id"]: p for p in products}, {q["query_id"]: q for q in queries}
    feature_rows, grouped, x, y, groups = [], {}, [], [], []
    for qid in sorted(qmap):
        group = []
        for c in sorted(candidates.get(qid, []), key=lambda c: c["source_rank"]):
            values, mask = features(qmap[qid], pmap[c["product_id"]], c["raw_score"])
            row = {
                "query_id": qid,
                "product_id": c["product_id"],
                "schema_id": schema["schema_id"],
                "values": values,
                "missing_mask": mask,
                "as_of": dm["created_at"],
            }
            feature_rows.append(row)
            group.append(row)
        grouped[qid] = group
    train_queries = []
    for qid, gt in gt_groups(judgments, dm, queries, products):
        if split["assignments"][qmap[qid]["family_id"]] != "train":
            continue
        if not grouped[qid]:
            continue
        if any(r["status"] != "judged" for r in gt.values()):
            raise FoundationError("Training query has incomplete ground truth")
        rows = grouped[qid]
        x.extend(r["values"] for r in rows)
        y.extend(gt[r["product_id"]]["relevance"] for r in rows)
        groups.append(len(rows))
        train_queries.append(qid)
    if not groups or len(set(y)) < 2:
        raise FoundationError("Training requires ranked label variation in the train split")
    parameters = {
        "objective": "lambdarank",
        "metric": "ndcg",
        "label_gain": [0, 0, 1, 3, 7],
        "verbosity": -1,
        "num_threads": 2,
        "seed": config["ranker"]["seed"],
        "deterministic": True,
        "force_col_wise": True,
        "min_data_in_leaf": 5,
        "num_leaves": 15,
        "learning_rate": 0.05,
        "feature_pre_filter": False,
    }
    training = lgb.Dataset(
        np.asarray(x, dtype=float), label=y, group=groups, feature_name=list(FEATURE_NAMES)
    )
    model = lgb.train(parameters, training, num_boost_round=60)
    model_text = model.model_to_string()
    payload = {
        "schema_version": 1,
        "model_id": run_id,
        "feature_schema_checksum": schema["checksum"],
        "label_gain": [0, 0, 1, 3, 7],
        "model_text": model_text,
    }
    model = load_model(payload, schema)
    reranked = []
    for qid, rows in grouped.items():
        if not rows:
            continue
        predictions = model.predict(
            np.asarray([r["values"] for r in rows], dtype=float), num_threads=2
        )
        if not all(math.isfinite(float(v)) for v in predictions):
            raise FoundationError("Ranker returned nonfinite predictions")
        ordered = sorted(
            zip(rows, predictions, strict=True), key=lambda pair: (-pair[1], pair[0]["product_id"])
        )
        for rank, (row, score) in enumerate(ordered[: config["retrieval"]["resultLimit"]], 1):
            reranked.append(
                {
                    "run_id": run_id,
                    "query_id": qid,
                    "product_id": row["product_id"],
                    "rank": rank,
                    "score": float(score),
                    "score_type": "model_score",
                    "model_id": run_id,
                }
            )
    new_outcomes = [{**o, "run_id": run_id} for o in outcomes.values()]
    all_candidates = [c for rows in candidates.values() for c in rows]
    all_candidates.sort(key=lambda c: (c["query_id"], c["source_rank"]))
    bundle = {
        "model_id": run_id,
        "dataset_id": dm["metadata"]["dataset_id"],
        "feature_schema_checksum": schema["checksum"],
        "trainer_version": version("lightgbm"),
        "trainer_config": {
            **parameters,
            "num_boost_round": 60,
            "fit_split": "train",
            "train_queries": train_queries,
        },
        "label_gain": [0, 0, 1, 3, 7],
        "split_id": split["split_id"],
        "artifact_checksum": digest(model_text),
    }
    for name, rows in (
        ("FeatureRow", feature_rows),
        ("FeatureSchema", [schema]),
        ("ModelBundle", [bundle]),
        ("SearchResult", reranked),
        ("QueryOutcome", new_outcomes),
    ):
        check_records(name, rows)
    return {
        "feature_schema.json": {"schema_version": 1, **schema},
        "model.json": payload,
        "bundle.json": {"schema_version": 1, **bundle},
        "features.jsonl": feature_rows,
        "candidates.jsonl": all_candidates,
        "results.jsonl": reranked,
        "outcomes.jsonl": new_outcomes,
    }, {
        "dataset_digests": dm["metadata"]["set_digests"],
        "dataset": reference(dataset),
        "judgments": reference(judgments),
        "baseline": reference(search),
        "candidate_run_id": sm["metadata"]["candidate_run_id"],
        "feature_schema_checksum": schema["checksum"],
        "seed": config["ranker"]["seed"],
        "fit_split": "train",
        "quality_gate_checksum": digest(config["qualityGate"]),
        "training_queries": len(groups),
        "training_rows": len(y),
        "failed_queries": 0,
    }
