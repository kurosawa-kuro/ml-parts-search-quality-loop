"""Fixed-revision E5 + isolated exact Qdrant indexes; every query has an outcome."""

from __future__ import annotations

import math
import re
import time
import unicodedata
import uuid
from pathlib import Path

from parts_search.errors import FoundationError
from parts_search.logs import logger
from parts_search.pipelines.inputs import dataset_rows, reference
from parts_search.pipelines.synthetic import check_records, digest


def error_code(error: Exception, fallback: str) -> str:
    """Classify exceptions without publishing service responses or credentials."""
    import httpx

    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (TimeoutError, httpx.TimeoutException)):
            return "timeout"
        if isinstance(current, (ConnectionError, httpx.ConnectError)):
            return "dependency_unavailable"
        current = getattr(current, "source", None) or current.__cause__ or current.__context__
    return fallback


def preprocess(text: str, kind: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(str.maketrans("‐‑‒–—−", "------"))
    text = re.sub(r"[A-Za-z]+(?:-[A-Za-z0-9]+)+", lambda m: m[0].upper(), text)
    return ("query: " if kind == "query" else "passage: ") + " ".join(text.split())


class E5Encoder:
    """Persistent subprocess avoids the torch/libomp + LightGBM runtime deadlock."""

    def __init__(self, embedding: dict):
        import subprocess
        import sys

        if embedding["preprocessingVersion"] != "parts_e5_v1":
            raise FoundationError("Unsupported embedding preprocessing policy")
        if not re.fullmatch(r"[a-f0-9]{40}", embedding["revision"]):
            raise FoundationError("Embedding revision must be a commit SHA")
        self.worker = subprocess.Popen(
            [sys.executable, "-m", "parts_search.embedding_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            if self._exchange(embedding) != {"ready": True}:
                raise FoundationError("Embedding worker did not start")
        except BaseException:
            self.close()
            raise

    def _exchange(self, value):
        import json
        import selectors

        self.worker.stdin.write(json.dumps(value) + "\n")
        self.worker.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(self.worker.stdout, selectors.EVENT_READ)
            if not selector.select(timeout=180):
                raise TimeoutError("Embedding worker timed out")
        line = self.worker.stdout.readline()
        if not line:
            raise FoundationError("Embedding worker exited")
        return json.loads(line)

    def encode(self, texts, kind):
        return self._exchange({"texts": texts, "kind": kind})

    def close(self):
        import subprocess

        if self.worker.poll() is None:
            self.worker.terminate()
            try:
                self.worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.worker.kill()
                self.worker.wait()
        self.worker.stdin.close()
        self.worker.stdout.close()


def ranked_points(client, collection, vector, limit, total):
    from qdrant_client import models

    take = min(total, limit + 1)
    if not take:
        return []
    while True:
        points = client.query_points(
            collection,
            query=vector,
            limit=take,
            search_params=models.SearchParams(exact=True),
            with_payload=True,
            with_vectors=False,
        ).points
        if any(not math.isfinite(p.score) for p in points):
            raise FoundationError("Qdrant returned a nonfinite score")
        ordered = sorted(points, key=lambda p: (-p.score, p.payload["product_id"]))
        if (
            take >= total
            or len(points) < take
            or len(points) <= limit
            or ordered[limit - 1].score != ordered[-1].score
        ):
            return ordered[:limit]
        take = min(total, take * 2)


def build_retrieval(config: dict, dataset: Path, run_id: str, *, encoder=None, client=None):
    from qdrant_client import QdrantClient, models

    manifest, products, queries, _ = dataset_rows(dataset)
    retrieval = config["retrieval"]
    if retrieval["hybrid"]["enabled"] or retrieval["structuredFilter"]["enabled"]:
        raise FoundationError("Vector baseline does not implement hybrid or structured filtering")
    embedding = retrieval["embedding"]
    index_id = "index-" + digest([manifest["outputs"]["catalog.jsonl"], embedding])[:24]
    collection = f"{retrieval['qdrant']['collectionPrefix']}_{index_id}_{run_id}"
    config_id = "retrieval-" + digest(retrieval)[:24]
    owned = client is None
    candidates, results, outcomes = [], [], []
    dimension = None
    failure = None
    try:
        client = client or QdrantClient(
            url=retrieval["qdrant"]["url"], timeout=retrieval["qdrant"]["timeoutSeconds"]
        )
        client.get_collections()  # Fail before downloading/encoding if the service is unavailable.
        encoder = encoder or E5Encoder(embedding)
        texts = [
            " ".join(f"{v['title']} {v['description']}" for _, v in sorted(p["texts"].items()))
            for p in products
        ]
        vectors = encoder.encode(texts, "passage")
        if not vectors or len(vectors) != len(products):
            raise FoundationError("Embedding did not cover catalog")
        dimension = len(vectors[0])
        client.create_collection(
            collection,
            vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
        )
        for start in range(0, len(products), 128):
            points = [
                models.PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, index_id + p["product_id"])),
                    vector=v,
                    payload={"product_id": p["product_id"]},
                )
                for p, v in zip(
                    products[start : start + 128], vectors[start : start + 128], strict=True
                )
            ]
            client.upsert(collection, points=points, wait=True)
        if client.count(collection, exact=True).count != len(products):
            raise FoundationError("Qdrant index count mismatch")
    except Exception as exc:
        failure = error_code(exc, "index_unavailable")
        logger().error("retrieval index setup failed (details withheld from public artifact)")
    try:
        for index, query in enumerate(queries):
            started = time.monotonic()
            attempt, error = 1, failure
            points = []
            if failure is None:
                for attempt in range(1, config["retry"]["retrievalMaxAttempts"] + 1):
                    try:
                        vector = encoder.encode([query["text"]], "query")[0]
                        points = ranked_points(
                            client, collection, vector, retrieval["candidateLimit"], len(products)
                        )
                        error = None
                        break
                    except Exception as exc:
                        error = error_code(exc, "retrieval_failed")
                        if attempt < config["retry"]["retrievalMaxAttempts"]:
                            time.sleep(config["retry"]["backoffSeconds"][attempt - 1])
            for rank, point in enumerate(points, 1):
                common = {
                    "run_id": run_id,
                    "query_id": query["query_id"],
                    "product_id": point.payload["product_id"],
                }
                candidates.append(
                    {
                        **common,
                        "source": "vector",
                        "source_rank": rank,
                        "score_type": "similarity",
                        "raw_score": float(point.score),
                        "retrieval_config_id": config_id,
                    }
                )
                if rank <= retrieval["resultLimit"]:
                    results.append(
                        {
                            **common,
                            "rank": rank,
                            "score": float(point.score),
                            "score_type": "similarity",
                            "model_id": None,
                        }
                    )
            outcomes.append(
                {
                    "run_id": run_id,
                    "query_id": query["query_id"],
                    "status": "failed" if error else "succeeded",
                    "returned_count": min(len(points), retrieval["resultLimit"]),
                    "error_code": error,
                    "attempt": attempt,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
            if (index + 1) % 100 == 0:
                logger().info("retrieval queries=%d/%d", index + 1, len(queries))
    finally:
        if isinstance(encoder, E5Encoder):
            encoder.close()
        if owned and client is not None:
            client.close()
    for name, rows in (
        ("Candidate", candidates),
        ("SearchResult", results),
        ("QueryOutcome", outcomes),
    ):
        check_records(name, rows)
    index_manifest = {
        "schema_version": 1,
        "index_id": index_id,
        "collection": collection,
        "embedding": embedding,
        "catalog_checksum": manifest["outputs"]["catalog.jsonl"],
        "dimension": dimension,
        "count": len(products),
        "status": "failed" if failure else "ready",
        "exact": True,
        "tie_break": "product_id_asc",
    }
    return {
        "candidates.jsonl": candidates,
        "results.jsonl": results,
        "outcomes.jsonl": outcomes,
        "index.json": index_manifest,
    }, {
        "dataset_digests": manifest["metadata"]["set_digests"],
        "dataset": reference(dataset),
        "retrieval_config": retrieval,
        "candidate_run_id": run_id,
        "index": index_manifest,
        "failed_queries": sum(o["status"] != "succeeded" for o in outcomes),
    }
