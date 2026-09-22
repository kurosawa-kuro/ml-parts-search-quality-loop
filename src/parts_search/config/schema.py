"""Strict configuration v1 contract; no implicit defaults or unknown fields."""


def obj(**properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def const(value):
    return {
        "const": value,
        "type": {bool: "boolean", int: "integer", str: "string", list: "array"}[type(value)],
    }


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def array(item):
    return {"type": "array", "items": item, "minItems": 1, "uniqueItems": True}


TEXT = {"type": "string", "minLength": 1, "pattern": r"\S"}
POSITIVE = {"type": "integer", "minimum": 1}
SEED = {"type": "integer", "minimum": 0}
RATIO = {"type": "number", "exclusiveMinimum": 0, "maximum": 1}
NONNEGATIVE = {"type": "number", "minimum": 0}
OPTIONAL_TEXT = nullable(TEXT)
GAINS = const([0, 0, 1, 3, 7])
SPLITS = ("train", "tuning", "holdout", "production")

PROJECT_SCHEMA = obj(
    schemaVersion=const(1), projectName=TEXT, repoRoot=TEXT, workspaceRoot=TEXT, homeDir=TEXT
)
SECRET_SCHEMA = obj(schemaVersion=const(1), DB_QDRANT_API_KEY=OPTIONAL_TEXT)
CONFIG_SCHEMA = obj(
    schemaVersion=const(1),
    projectName=TEXT,
    appEnv=const("local"),
    executionMode=const("batch"),
    logLevel={"enum": ["debug", "info", "warning", "error"]},
    paths=obj(artifacts=TEXT, references=TEXT, activeRelease=TEXT),
    artifacts=obj(
        schemaVersion=const(1),
        metadataFormat=const("json"),
        recordsFormat=const("jsonl"),
        encoding=const("utf-8"),
        checksum=const("sha256"),
        immutableSnapshots=const(True),
        atomicPublish=const(True),
    ),
    catalog=obj(
        domain={"enum": ["fa_parts", "automotive_parts"]},
        skuCount=POSITIVE,
        languages=array({"enum": ["ja", "en", "de", "zh"]}),
        seed=SEED,
        attributePolicyId=OPTIONAL_TEXT,
    ),
    queries=obj(
        familyCount=POSITIVE,
        types=array({"enum": ["exact_model_number", "natural_language", "dimension_sensitive"]}),
        generationSeed=SEED,
    ),
    split=obj(
        unit=const("family_id"),
        seed=SEED,
        ratios=obj(**dict.fromkeys(SPLITS, RATIO)),
        generationSeeds=obj(**dict.fromkeys(SPLITS, SEED)),
        allowFamilyOverlap=const(False),
        sharedCatalog=const(True),
    ),
    retrieval=obj(
        backend=const("qdrant"),
        candidateLimit=POSITIVE,
        resultLimit=POSITIVE,
        tieBreak=const("product_id_asc"),
        qdrant=obj(
            url=TEXT,
            collectionPrefix=TEXT,
            timeoutSeconds=POSITIVE,
            apiKeySecret=const("DB_QDRANT_API_KEY"),
        ),
        embedding=obj(
            modelId=OPTIONAL_TEXT, revision=OPTIONAL_TEXT, preprocessingVersion=OPTIONAL_TEXT
        ),
        hybrid=obj(enabled=const(False)),
        structuredFilter=obj(enabled=const(False)),
    ),
    features=obj(schemaId=OPTIONAL_TEXT),
    ranker=obj(
        implementation=const("lightgbm"),
        objective=const("lambdarank"),
        seed=SEED,
        labelGain=GAINS,
        fitSplit=const("train"),
        tuningSplit=const("tuning"),
    ),
    judgments=obj(
        policyId=const("parts_gt_v1"),
        requireCompleteEvaluation=const(True),
        promoteImplicitToEvaluation=const(False),
    ),
    evaluation=obj(
        policyId=const("parts_metrics_v1"),
        implementation=const("ir_measures"),
        version=OPTIONAL_TEXT,
        provider=OPTIONAL_TEXT,
        ndcgCutoff=const(10),
        recallCutoff=const(100),
        mrrCutoff=const(100),
        relevanceThreshold=const(2),
        gainByRelevance=GAINS,
        dcgFormula=const("gain_over_log2_rank_plus_one"),
        aggregation=const("query_macro"),
        noRelevantPolicy=const("exclude_and_report"),
        incompletePolicy=const("inconclusive"),
        slices=array({"enum": ["language", "query_type", "category"]}),
    ),
    qualityGate=obj(
        policyId=OPTIONAL_TEXT,
        minNdcgDelta=nullable(NONNEGATIVE),
        maxRegression=obj(
            **dict.fromkeys(
                [
                    "recallAt100",
                    "mrrAt100",
                    "sliceNdcgAt10",
                    "searchSuccessRate",
                    "wrongFitmentRate",
                ],
                nullable(NONNEGATIVE),
            )
        ),
        minSliceQueries=nullable(POSITIVE),
        repetitionSeeds=nullable(array(SEED)),
    ),
    simulation=obj(
        # const(False) だと T7 で simulation を有効化できず、段階が永久に実行不能になる。
        # blockers() が enabled=false を未充足として報告する仕組みが既にあるので、
        # ここは boolean にして「まだ有効化していない」を設定で表現する。
        enabled={"type": "boolean"},
        policyId=OPTIONAL_TEXT,
        observationWindowSeconds=nullable(POSITIVE),
        behaviorModel=OPTIONAL_TEXT,
        developmentSplit=const("tuning"),
        validationSplit=const("production"),
        pairedRandomStreams=const(True),
        # T7 で具体化した版付き policy。null のままなら simulation を開始しない
        # （05「未設定ならシミュレーションを開始しない」）。
        policyVersion=OPTIONAL_TEXT,
        sessionsPerQuery=nullable(POSITIVE),
        positionBias=obj(model=OPTIONAL_TEXT, decay=nullable(NONNEGATIVE)),
        clickProbability=obj(
            **dict.fromkeys(["relevant", "marginal", "irrelevant"], nullable(NONNEGATIVE))
        ),
        conversionProbabilityGivenClick=nullable(NONNEGATIVE),
        reformulationProbability=obj(
            **dict.fromkeys(["zeroResult", "noClick", "afterClick"], nullable(NONNEGATIVE))
        ),
        lateInteractionSeconds=nullable(NONNEGATIVE),
        seed=nullable(SEED),
    ),
    retry=obj(
        retrievalMaxAttempts=POSITIVE, backoffSeconds={"type": "array", "items": NONNEGATIVE}
    ),
    release=obj(
        mode=const("local_simulation"),
        requireAcceptedDecision=const(True),
        requireSmoke=const(True),
        preservePreviousBundle=const(True),
    ),
)
