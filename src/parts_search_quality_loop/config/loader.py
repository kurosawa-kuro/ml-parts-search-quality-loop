"""Load public settings without loading secrets or contacting services."""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from jsonschema import Draft202012Validator

from parts_search_quality_loop.config.schema import CONFIG_SCHEMA, PROJECT_SCHEMA, SECRET_SCHEMA
from parts_search_quality_loop.errors import FoundationError

STAGES = ("foundation", "catalog", "retrieval", "training", "evaluation", "gate", "simulation")


class StrictLoader(yaml.SafeLoader):
    """Reject duplicate mapping keys instead of silently overriding them."""


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise FoundationError("YAML mapping contains duplicate or non-string keys")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def read_yaml(path: Path, schema: dict) -> dict:
    try:
        if path.stat().st_size > 1024 * 1024:
            raise FoundationError("YAML configuration exceeds size limit")
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=StrictLoader)
        # Restrict YAML to finite JSON values, rejecting dates, NaN and cyclic aliases.
        json.dumps(data, allow_nan=False)
        error = next(Draft202012Validator(schema).iter_errors(data), None)
        if error:
            # Use schema path, not error.message (which may contain a secret value).
            location = ".".join(str(p) for p in error.absolute_schema_path)
            raise FoundationError(f"Configuration violates schema at {location}")
        return data
    except (OSError, ValueError, TypeError, RecursionError, yaml.YAMLError):
        raise FoundationError("Cannot read a valid YAML configuration") from None


def resolve_relative(root: Path, value: str) -> Path:
    relative = Path(value)
    resolved = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or resolved == root:
        raise FoundationError("Configured path must be a child of repoRoot")
    if not resolved.is_relative_to(root):
        raise FoundationError("Configured path escapes repoRoot")
    return resolved


@dataclass(frozen=True)
class Settings:
    project: dict = field(repr=False)
    config: dict = field(repr=False)
    root: Path
    artifacts_root: Path

    def public_snapshot(self) -> dict:
        return copy.deepcopy(self.config)

    def blockers(self, stage: str) -> list[str]:
        if stage not in STAGES:
            raise FoundationError("Unknown configuration stage")
        required = {
            "foundation": [],
            "catalog": ["catalog.attributePolicyId"],
            "retrieval": [
                "catalog.attributePolicyId",
                "retrieval.embedding.modelId",
                "retrieval.embedding.revision",
                "retrieval.embedding.preprocessingVersion",
            ],
            "training": ["catalog.attributePolicyId", "features.schemaId"],
            "evaluation": ["evaluation.version", "evaluation.provider"],
            "gate": [
                "qualityGate.policyId",
                "qualityGate.minNdcgDelta",
                "qualityGate.minSliceQueries",
                "qualityGate.repetitionSeeds",
            ]
            + [
                f"qualityGate.maxRegression.{key}"
                for key in self.config["qualityGate"]["maxRegression"]
            ],
            "simulation": [
                "simulation.policyId",
                "simulation.observationWindowSeconds",
                "simulation.behaviorModel",
            ],
        }
        missing = []
        for path in required[stage]:
            value = self.config
            for part in path.split("."):
                value = value[part]
            if value is None:
                missing.append(path)
        if stage == "simulation" and not self.config["simulation"]["enabled"]:
            missing.append("simulation.enabled")
        return missing


def load_settings(project_path: Path, config_path: Path) -> Settings:
    project = read_yaml(project_path, PROJECT_SCHEMA)
    config = read_yaml(config_path, CONFIG_SCHEMA)
    root = Path(project["repoRoot"])
    if not root.is_absolute() or not root.is_dir():
        raise FoundationError("project.repoRoot must be an existing absolute directory")
    root = root.resolve()
    if project["projectName"] != config["projectName"]:
        raise FoundationError("Project names do not match")
    ratios = config["split"]["ratios"]
    if not math.isclose(sum(ratios.values()), 1.0, rel_tol=0, abs_tol=1e-9):
        raise FoundationError("Split ratios must sum to one")
    if config["queries"]["familyCount"] < len(ratios):
        raise FoundationError("Query families cannot populate every split")
    if any(int(config["queries"]["familyCount"] * ratio) < 1 for ratio in ratios.values()):
        raise FoundationError("Each split needs at least one query family")
    retrieval, evaluation = config["retrieval"], config["evaluation"]
    if (
        retrieval["candidateLimit"] < evaluation["recallCutoff"]
        or retrieval["resultLimit"] < evaluation["mrrCutoff"]
        or retrieval["resultLimit"] > retrieval["candidateLimit"]
    ):
        raise FoundationError("Retrieval limits do not cover metric cutoffs")
    if not {"language", "query_type"}.issubset(evaluation["slices"]):
        raise FoundationError("Mandatory evaluation slices are missing")
    if len(config["retry"]["backoffSeconds"]) != config["retry"]["retrievalMaxAttempts"] - 1:
        raise FoundationError("Retry attempts and backoff count disagree")
    try:
        url = urlsplit(retrieval["qdrant"]["url"])
        valid = url.scheme in ("http", "https") and url.hostname and url.port != 0
        if not valid or url.username or url.password or url.query or url.fragment:
            raise ValueError
    except ValueError:
        raise FoundationError("Qdrant URL must be HTTP(S) without embedded credentials") from None
    paths = {key: resolve_relative(root, value) for key, value in config["paths"].items()}
    if not paths["activeRelease"].is_relative_to(paths["artifacts"]):
        raise FoundationError("Active release path must be inside artifacts")
    return Settings(project, config, root, paths["artifacts"])


@dataclass(frozen=True)
class Secrets:
    qdrant_api_key: str | None = field(default=None, repr=False)


def load_secret(path: Path) -> Secrets:
    """Explicit opt-in for future adapters; absent file means local unauthenticated access."""
    if not path.exists():
        return Secrets()
    data = read_yaml(path, SECRET_SCHEMA)
    return Secrets(data["DB_QDRANT_API_KEY"])
