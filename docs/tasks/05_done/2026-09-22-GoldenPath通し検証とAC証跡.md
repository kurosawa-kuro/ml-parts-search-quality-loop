# Golden Path 通し検証と AC-001〜011 の証跡

## Goal

実データで Golden Path を1周し、[要件](../../01_requirements.md) の AC-001〜011 に**実成果物の証跡**を付ける。
「全段階が走った」ことを達成と読み替えない。

## 実行条件

| 項目 | 値 |
|---|---|
| 規模 | 1,500 SKU / 700 QueryFamily / 1,400 Query / 完全GT 2,100,000行 |
| 検索 | 実 E5 `intfloat/multilingual-e5-small`（commit SHA 固定）＋ ローカル Qdrant |
| 学習 | LightGBM LambdaRank・seed [11, 22, 33] |
| コマンド | `parts-search pipeline` → `activate` → `rollback` |
| 結果 | **exit 0 / `golden_path_complete: true` / `decision: promote`** |

実行された run は 15 本（per-seed の training / evaluation を含めて報告する）。

## AC 証跡

| AC | 観測（実成果物の値） |
|---|---|
| AC-001 再現性 | `experiment.json` に dataset `dataset-9b1256…` / queryset `queryset-4a36ec…` / gt `gt-0c34dd…` / split `split-0c026e…` / metric policy `parts_metrics_v1` / seed 11 と variant 3件。各 variant は manifest checksum つき |
| AC-002 オフライン | baseline NDCG@10 0.7479 / Recall@100 0.8302 / MRR@100 0.7913。3 seed とも NDCG@10 **+0.2429**、Recall 差 0 |
| AC-003 Slice | `slices.jsonl` に language(ja 700 / en 700)・query_type(3種 466〜468)・category(3種 454〜490)・split(train 840 / tuning 210 / holdout 210 / production 140) |
| AC-004 疑似オンライン | KPI 6種を baseline/candidate で比較。searchSuccess 0.757→**0.971**、CTR 0.566→0.718、conversion 0.150→0.195、reformulation 0.227→0.171、wrongFitment 0.243→**0.029**、zeroResult 0.0。event 内訳 impression 560 / click 402 / conversion 109 / reformulation 97 |
| AC-005 データ分離 | family 単位で train 420 / tuning 105 / holdout 105 / production 70。**全ペアの family 重複 0**。simulation は `production` split、学習は `fit_split: train`（`bundle.json` の trainer_config） |
| AC-006 失敗改善 | FailureCase: retrieval_miss 488 / rerank_miss 336 / simulation_miss 4。独立 holdout で NDCG@10 **+0.2762**・verdict accepted |
| AC-007 継続性 | `smoke.json` の `next_experiment` が親 experiment・FailureCase 4件・release_id を保持。smoke 6段階すべて pass |
| AC-008 評価の完全性 | per_query 1,400件すべて `complete`、null metric 0件、evaluation status `complete`、分母（target/evaluable/missing/no_relevant）を併記 |
| AC-009 学習の整合性 | FeatureSchema 8列（vector_score / model_exact / category_exact / diameter_delta / length_delta / material_exact / standard_exact / usage_exact）、FeatureRow に `label` が無いこと、schema checksum `1e9f99b4…`。学習時と推論時のスコア一致は integration test が検査 |
| AC-010 可逆性 | ReleaseBundle が search_config / dataset / index / embedding_revision / model / feature_schema_id / policies / checksums を固定。activate → activate → **rollback で前 release へ復帰**、`active-history.jsonl` 3行、旧 bundle は保持 |
| AC-011 比較可能性 | comparison_signature 一致、baseline/candidate とも評価可能 210 query（holdout）、slice 不足理由は 0件。分母は decision に記録 |

## 実測で見つけた誤読面（修正済み）

**3 seed 反復は「頑健性」の証拠になっていなかった。** model の checksum は seed ごとに
異なる（`1ff58345…` / `1a228e72…` / `fd90d754…`）のに、NDCG@10 は小数9桁まで同一だった。
trainer が `deterministic: true`・bagging/feature subsample 無しのため、**seed が指標へ
影響しない**。「3 seed 通った」を分散の小ささと読むと誤る。

→ gate が `seed_metric_spread`（seed 間の指標幅）と `repetition_signal` を出力するようにした。
現在の trainer 構成では `no_metric_variance_across_seeds` が正しい表示になる。
**閾値や trainer 構成は変えていない**（変えれば品質そのものが動くため、別判断）。

## 小規模実行との対比

120 SKU / 40 family では `minSliceQueries=30` を満たさず **exit 4 / inconclusive**。
実行は成功しているので exit 1 と区別する。**採用を得るために閾値を下げない。**

## Evidence

- `pytest -m ''` 146 passed（実 E5 / Qdrant 込み）
- `ruff check` / `ruff format --check` clean、`uv build` 成功
- 上表の数値は通し実行の成果物（`artifacts/runs/*`・`artifacts/releases/*`・`artifacts/active.json`）から機械抽出
