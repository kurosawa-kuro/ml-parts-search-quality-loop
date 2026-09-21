"""Deterministic fictional FA catalog and family-first query generation (T2)."""

from __future__ import annotations

import copy
import json
import math
import random
from collections import Counter

from parts_search.errors import FoundationError
from parts_search.records import validate
from parts_search.records.contracts import QUERY_TYPES, SPLITS
from parts_search.runstore import checksum

ATTRIBUTE_POLICY = "fa_parts_attr_v1"
GENERATOR_VERSION = "parts_synthetic_v1"
CATEGORIES = ("shaft", "bearing", "bolt")
CATEGORY_JA = {"shaft": "軸", "bearing": "軸受", "bolt": "ボルト"}
MATERIALS = ("steel", "stainless", "aluminum")
MATERIAL_JA = {"steel": "鋼", "stainless": "ステンレス", "aluminum": "アルミ"}
USES = {"shaft": "guiding", "bearing": "rotation", "bolt": "mounting"}
USE_JA = {"guiding": "案内", "rotation": "回転", "mounting": "固定"}
DIMENSIONS = ("diameter", "length")
ATTRIBUTES = (*DIMENSIONS, "material", "standard", "usage")
TOLERANCE_MM = 0.01
UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}
POLICY = {
    "attribute_policy_id": ATTRIBUTE_POLICY,
    "generator_version": GENERATOR_VERSION,
    "categories": list(CATEGORIES),
    "attributes": list(ATTRIBUTES),
    "units_to_mm": UNITS,
    "tolerance_mm": TOLERANCE_MM,
    "categorical_match": "exact",
    "semantic_relation": "same_category",
    "substitution": "all_required_constraints_must_match",
    "languages_per_family": "one_query_per_configured_language",
}


def digest(value) -> str:
    return checksum(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())


def check_records(name: str, rows: list[dict]) -> None:
    issues = validate(name, rows)
    if issues:
        raise FoundationError(f"{name} contract violation: {issues[0]}")


def millimeters(value, unit: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
        or value < 0
        or not isinstance(unit, str)
        or unit not in UNITS
    ):
        raise FoundationError("Dimension requires a finite nonnegative value and supported unit")
    result = value * UNITS[unit]
    if not math.isfinite(result):
        raise FoundationError("Converted dimension is not finite")
    return result


def dimension(value: dict, *, condition: bool = False):
    if not isinstance(value, dict):
        raise FoundationError("Dimension must be an object")
    if condition and set(value) == {"min", "max", "unit"}:
        return millimeters(value["min"], value["unit"]), millimeters(value["max"], value["unit"])
    if not {"value", "unit"} <= set(value) or set(value) - {"value", "unit", "original"}:
        raise FoundationError("Invalid dimension fields")
    number = millimeters(value["value"], value["unit"])
    if "original" in value:
        original = dimension(value["original"])
        if not math.isclose(number, original, abs_tol=1e-9, rel_tol=0):
            raise FoundationError("Original dimension disagrees with normalized value")
    return (number - TOLERANCE_MM, number + TOLERANCE_MM) if condition else number


def normalize_product(row: dict) -> dict:
    if row["category"] not in CATEGORIES or set(row["attributes"]) - set(ATTRIBUTES):
        raise FoundationError("Product violates attribute policy")
    result = {"category": row["category"], "model_number": row["model_number"]}
    for key in ATTRIBUTES:
        value = row["attributes"].get(key)
        if value is not None:
            if key in DIMENSIONS:
                value = dimension(value)
            elif not isinstance(value, str) or not value.strip():
                raise FoundationError("Categorical attributes require nonempty strings or null")
        result[key] = value
    return result


def normalize_query(row: dict) -> dict:
    constraints = row["constraints"]
    if set(constraints) != {"required", "optional"}:
        raise FoundationError("Constraints require only required/optional fields")
    result = {"category": row["category"], "contradictory": False}
    if row["category"] is not None and row["category"] not in CATEGORIES:
        raise FoundationError("Unknown query category")
    for group in ("required", "optional"):
        if not isinstance(constraints[group], dict):
            raise FoundationError("Constraint groups must be objects")
        normalized = {}
        for key, value in constraints[group].items():
            if key not in (*ATTRIBUTES, "model_number", "category"):
                raise FoundationError("Unsupported constraint; refusing to ignore it")
            if value is None:
                normalized[key] = None
            elif key in DIMENSIONS:
                normalized[key] = dimension(value, condition=True)
                if normalized[key][0] > normalized[key][1]:
                    result["contradictory"] = True
            elif isinstance(value, str) and value.strip():
                normalized[key] = value
            else:
                raise FoundationError("Categorical constraints require nonempty strings or null")
        result[group] = normalized
    required_category = result["required"].get("category")
    if required_category and row["category"] and required_category != row["category"]:
        result["contradictory"] = True
    return result


def split_families(config: dict) -> dict:
    count = config["queries"]["familyCount"]
    families = [f"family-{index:06d}" for index in range(count)]
    random.Random(config["split"]["seed"]).shuffle(families)
    ratios = config["split"]["ratios"]
    counts = {name: math.floor(count * ratios[name]) for name in SPLITS}
    remainder = count - sum(counts.values())
    order = sorted(SPLITS, key=lambda name: (-(count * ratios[name] - counts[name]), name))
    for name in order[:remainder]:
        counts[name] += 1
    assignments = {}
    offset = 0
    for name in SPLITS:
        for family in families[offset : offset + counts[name]]:
            assignments[family] = name
        offset += counts[name]
    assignments = dict(sorted(assignments.items()))
    return {
        "split_id": "split-" + digest(assignments)[:24],
        "assignments": assignments,
        "generation_seed": config["queries"]["generationSeed"],
        "split_seed": config["split"]["seed"],
        "counts": counts,
        "set_digest": digest(assignments),
    }


def validate_dataset(products: list[dict], queries: list[dict], split: dict) -> None:
    check_records("Product", products)
    check_records("Query", queries)
    check_records("SplitManifest", [split])
    assignments = split["assignments"]
    if not assignments or any(value not in SPLITS for value in assignments.values()):
        raise FoundationError("Invalid split assignment")
    if set(assignments) != {query["family_id"] for query in queries}:
        raise FoundationError("Split assignments must cover exactly the query families")
    counts = {name: sum(value == name for value in assignments.values()) for name in SPLITS}
    if counts != split["counts"] or digest(assignments) != split["set_digest"]:
        raise FoundationError("Split counts or set digest mismatch")
    for product in products:
        normalize_product(product)
    signatures = {}
    families = {}
    locales = set()
    for query in queries:
        signature = digest(normalize_query(query))
        family = query["family_id"]
        if signature in signatures and signatures[signature] != family:
            raise FoundationError("Equivalent query intents cross families")
        signatures[signature] = family
        if family in families and families[family] != signature:
            raise FoundationError("Translations disagree within a family")
        families[family] = signature
        key = (family, query["language"])
        if key in locales:
            raise FoundationError("Duplicate family locale")
        locales.add(key)


def _quantity(number: float, unit: str) -> dict:
    original = {"value": number / UNITS[unit], "unit": unit}
    return {"value": number, "unit": "mm", "original": original}


def _query_text(category: str, kind: str, constraints: dict, language: str, variant: int) -> str:
    ja = language == "ja"
    parts = [CATEGORY_JA[category] if ja else category]
    labels = {
        "diameter": "直径",
        "length": "長さ",
        "material": "材質",
        "standard": "規格",
        "usage": "用途",
        "model_number": "型番",
    }
    for group, values in constraints.items():
        for key, value in values.items():
            if key in DIMENSIONS:
                rendered = f"{value['value']:g} {value['unit']}"
            elif ja and key == "material":
                rendered = MATERIAL_JA[value]
            elif ja and key == "usage":
                rendered = USE_JA[value]
            else:
                rendered = value
            requirement = ("必須" if group == "required" else "希望") if ja else group
            parts.append(f"{requirement} {labels[key] if ja else key}: {rendered}")
    if kind == "natural_language":
        prefix = (
            ("探しています。" if variant else "必要です。")
            if ja
            else ("Looking for " if variant else "I need ")
        )
        return prefix + "; ".join(parts)
    return "; ".join(parts)


def build_dataset(config: dict) -> tuple[dict, dict]:
    if config["catalog"]["attributePolicyId"] != ATTRIBUTE_POLICY:
        raise FoundationError("Unsupported attribute policy")
    languages = config["catalog"]["languages"]
    types = config["queries"]["types"]
    if not languages or set(languages) - {"ja", "en"} or not types or set(types) - set(QUERY_TYPES):
        raise FoundationError("Unsupported synthetic language or query type")
    size, families = config["catalog"]["skuCount"], config["queries"]["familyCount"]
    if families > size:
        raise FoundationError("Synthetic query families must not exceed SKU count")
    split = split_families(config)  # Fixed before any translation or surface variation.
    rng = random.Random(config["catalog"]["seed"])
    products = []
    for index in range(size):
        category = CATEGORIES[index % len(CATEGORIES)]
        material = rng.choice(MATERIALS)
        diameter = float(5 + (index // 3) % 50)
        length = float(20 + 5 * (index // 150))
        model = f"FA-{category.upper()}-{index:06d}"
        attributes = {
            "diameter": _quantity(diameter, rng.choice(("mm", "cm"))),
            "length": _quantity(length, rng.choice(("mm", "cm"))),
            "material": material,
            "standard": f"SYN-{category.upper()}-V1",
            "usage": USES[category],
        }
        texts = {}
        for language in languages:
            title = f"{CATEGORY_JA[category] if language == 'ja' else category} {model}"
            description = (
                f"架空部品。直径 {diameter:g} mm、長さ {length:g} mm。"
                f"材質 {MATERIAL_JA[material]}、用途 {USE_JA[USES[category]]}。"
                if language == "ja"
                else f"Fictional part. Diameter {diameter:g} mm, length {length:g} mm. "
                f"Material {material}, use {USES[category]}."
            )
            texts[language] = {
                "title": title,
                "description": description + " " + attributes["standard"],
            }
        products.append(
            {
                "product_id": f"product-{index:06d}",
                "category": category,
                "model_number": model,
                "texts": texts,
                "attributes": attributes,
            }
        )
    anchors = random.Random(config["queries"]["generationSeed"]).sample(products, families)
    queries = []
    for index, (family, partition) in enumerate(split["assignments"].items()):
        product = anchors[index]
        attrs = product["attributes"]
        rng = random.Random(digest([config["split"]["generationSeeds"][partition], family]))
        kind = types[index % len(types)]
        dims = {}
        for key in DIMENSIONS:
            unit = rng.choice(("mm", "cm"))
            dims[key] = {"value": attrs[key]["value"] / UNITS[unit], "unit": unit}
        required = {"standard": attrs["standard"]}
        optional = {"material": attrs["material"], "usage": attrs["usage"]}
        if kind == "natural_language":
            optional.update(dims)
        else:
            required.update(dims)
        if kind == "exact_model_number":
            optional["model_number"] = product["model_number"]
        constraints = {"required": required, "optional": optional}
        variant = rng.randrange(2)
        for language in languages:
            queries.append(
                {
                    "query_id": f"query-{index:06d}-{language}",
                    "family_id": family,
                    "text": _query_text(product["category"], kind, constraints, language, variant),
                    "language": language,
                    "query_type": kind,
                    "category": product["category"],
                    "constraints": copy.deepcopy(constraints),
                }
            )
    queries.sort(key=lambda query: query["query_id"])
    validate_dataset(products, queries, split)
    generation = {key: copy.deepcopy(config[key]) for key in ("catalog", "queries", "split")}
    content = {"catalog": digest(products), "queryset": digest(queries), "split": digest(split)}
    metadata = {
        "dataset_id": "dataset-" + digest(content)[:24],
        "queryset_id": "queryset-" + content["queryset"][:24],
        "split_id": split["split_id"],
        "set_digests": content,
        "generation_config": generation,
        "policy": POLICY,
        "counts": {
            "products": len(products),
            "queries": len(queries),
            "families": families,
            "family_splits": split["counts"],
            "languages": dict(Counter(q["language"] for q in queries)),
            "query_types": dict(Counter(q["query_type"] for q in queries)),
        },
    }
    return {
        "catalog.jsonl": products,
        "queries.jsonl": queries,
        "splits.json": {"schema_version": 1, **split},
    }, metadata
