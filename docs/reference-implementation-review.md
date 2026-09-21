# 参照実装レビューと設計反映

> 2026-09-21。`references/github/` のローカルcheckoutを静的に確認。実行・性能検証や最新upstreamの確認ではない。観測事実と本PoCの設計判断を分ける。参照先の設計を一括移植しない。

| 固定commitの出典 | 確認した事実 | 本PoCでの扱い |
|---|---|---|
| [metarank/metarank: src/main/scala/ai/metarank/model/Event.scala](https://github.com/metarank/metarank/blob/e3b8d44b302c98bd7cb2e06bbb6ad06bb3a10293/src/main/scala/ai/metarank/model/Event.scala) | RankingEventのid・itemsとInteractionEventのranking参照。itemsは非空。 | event_idとimpression_idで結合する。PoCの0件impressionは空配列を許し、非空制約は移植しない。 |
| [metarank/metarank: src/main/scala/ai/metarank/flow/ClickthroughQuery.scala](https://github.com/metarank/metarank/blob/e3b8d44b302c98bd7cb2e06bbb6ad06bb3a10293/src/main/scala/ai/metarank/flow/ClickthroughQuery.scala) | interaction種別の重みからlabelを作り、query groupと特徴量offsetを保持。 | 暗黙feedbackと評価GTを分離。Featureの名前・順序・版を固定する。 |
| [metarank/metarank: src/main/scala/ai/metarank/main/command/train/SplitStrategy.scala](https://github.com/metarank/metarank/blob/e3b8d44b302c98bd7cb2e06bbb6ad06bb3a10293/src/main/scala/ai/metarank/main/command/train/SplitStrategy.scala) | time / random / field等の分割がある。1件のTimeSplitはtrain/testへ同じqueryを返す。 | 本PoCではgroup分離を必須とし、学習不足時は停止する。少数時の重複fallbackは移植しない。 |
| [amazon-science/esci-data: README.md](https://github.com/amazon-science/esci-data/blob/7916cdf6ab75a462e77f20ab40428a10923998d5/README.md) | 商品localeとproduct_idで結合。query単位train/test。判定は候補リストに対するもの。 | 商品ID・localeとquery familyを明示。部分qrelsからcatalog全体Recallを主張しない。 |
| [amazon-science/esci-data: ranking/prepare_trec_eval_files.py](https://github.com/amazon-science/esci-data/blob/7916cdf6ab75a462e77f20ab40428a10923998d5/ranking/prepare_trec_eval_files.py) | E/S/C/Iを4/2/3/1へ変換し、末尾のtrec_eval例で別のgain mappingを指定。 | カテゴリlabel・ordinal・評価gainを別契約にする。ESCI値をそのまま部品GTにしない。 |
| [qdrant/qdrant_demo: qdrant_demo/neural_searcher.py](https://github.com/qdrant/qdrant_demo/blob/3d64f12febe6ef3312c406969ca2b1616a67d189/qdrant_demo/neural_searcher.py) | denseとsparseのprefetchをRRFで融合し、score_typeでcosineとrrfを区別。 | Retrieval候補数・返却数・スコア種別を保存。融合scoreをsemantic_scoreに流用しない。 |
| [qdrant/qdrant_demo: qdrant_demo/text_searcher.py](https://github.com/qdrant/qdrant_demo/blob/3d64f12febe6ef3312c406969ca2b1616a67d189/qdrant_demo/text_searcher.py) | sparse vectorを使うBM25検索。payload MatchTextとの違いを記述。 | keyword検索の役割を明示。BM25 / Hybridは段階的拡張のまま保持。 |
| [qdrant/qdrant: lib/api/src/rest/schema.rs](https://github.com/qdrant/qdrant/blob/6ab21cac18ebb6f4ae29102c7f8f5cc11affd5de/lib/api/src/rest/schema.rs) | Fusion列挙にRrf / Dbsf、Rrfにkとweightsの設定がある。 | fusion設定を検索構成の版管理対象にする。Qdrant採用自体は未決。 |
| [opensearch-project/search-relevance: src/main/resources/mappings/experiment.json](https://github.com/opensearch-project/search-relevance/blob/82a10c042aa4d48f36fa8571c6815643fdd3a529/src/main/resources/mappings/experiment.json) | querySetId、searchConfigurationList、judgmentList、inputSignatureがある。 | 実験入力のsignatureと固定snapshotで比較可能性を検査する。 |
| [opensearch-project/dashboards-search-relevance: public/components/experiment/utils/query_evaluation_builder.ts](https://github.com/opensearch-project/dashboards-search-relevance/blob/8d7936fd0264a6d32dff4a88f3f86cd376d1a77b/public/components/experiment/utils/query_evaluation_builder.ts) | success / zero_results / failed / not_runを区別。 | QuerySet全件にoutcomeを残す。時刻順・query文字列結合ではなくID結合にする。 |
| [o19s/quepid: app/models/judgement.rb](https://github.com/o19s/quepid/blob/f77c17d42edc6013b7f40854216b267a4ee4e676/app/models/judgement.rb) | ratingとunrateable / judge_later、explanationを別に保持。 | unjudged / unrateable / judgedと判定理由を分ける。 |
| [o19s/quepid: app/models/snapshot.rb](https://github.com/o19s/quepid/blob/f77c17d42edc6013b7f40854216b267a4ee4e676/app/models/snapshot.rb) | Snapshotがcase・try・scorerと検索結果に関連する。 | 比較時の検索結果・GT・指標契約を固定し再評価を別実行として記録する。 |
| [o19s/elasticsearch-learning-to-rank: docs/training-models.rst](https://github.com/o19s/elasticsearch-learning-to-rank/blob/9409a6c72cc2707ef6b215ef8b81a377abecfcd5/docs/training-models.rst) | 学習はplugin外。ordinalでFeatureを参照し、modelにはFeature定義をコピーする。 | モデルbundleにFeature schemaと学習入力を固定。定義変更時は旧モデルを上書きしない。 |
| [wufanyou/KDD-Cup-2022-Amazon: README.md](https://github.com/wufanyou/KDD-Cup-2022-Amazon/blob/e1601e6bb51e604a6e5149373d12ea66e7483034/README.md) | Task 1はLightGBMの出力から期待gainで並べる説明。Task 2/3にはTask 1由来のpotential data leakageを使う特徴量も記述。 | LambdaRank実装の直接根拠とはしない。リーク依存の特徴量は採用しない。 |
| [tanmay0401/code-mixed-search-benchmark: src/evaluation/metrics.py](https://github.com/tanmay0401/code-mixed-search-benchmark/blob/4ba9ceb646dd1d8302ee77d7fc3efc7ee6bb8bd8/src/evaluation/metrics.py) | NDCGはlinear gain、RRはgain>0。未判定はgain 0扱い。 | PoC独自のgain / relevant閾値を明示して固定する。 |
| [tanmay0401/code-mixed-search-benchmark: src/evaluation/evaluator.py](https://github.com/tanmay0401/code-mixed-search-benchmark/blob/4ba9ceb646dd1d8302ee77d7fc3efc7ee6bb8bd8/src/evaluation/evaluator.py) | runにあるqueryだけを走査し、GTなしをskip。Slice平均と件数を出す。 | Slice件数は採用。query欠落で分母を減らす挙動は採用しない。 |
| [terrierteam/ir_measures: ir_measures/measures/ndcg.py](https://github.com/terrierteam/ir_measures/blob/64b5afd5cd14f7d8323f9b24a1bfd12afdd1e776/ir_measures/measures/ndcg.py) | dcg方式、custom gains、judged_onlyをパラメータ化。 | 指標名だけで比較せずmetric policyを保存する。 |
| [terrierteam/ir_measures: ir_measures/measures/rr.py](https://github.com/terrierteam/ir_measures/blob/64b5afd5cd14f7d8323f9b24a1bfd12afdd1e776/ir_measures/measures/rr.py) | relevantの下限relとcutoffを指定できる。 | MRRをMRR@100・relevance>=2と定義する。 |
| [DylanJoo/runs-and-qrels: scripts/evaluate.py](https://github.com/DylanJoo/runs-and-qrels/blob/bf87db4b07a8474966cce6864a08f6b1e85569c7/scripts/evaluate.py) | TREC run / qrelsで評価を分離。依存がないfallbackは指標を0.0として返す。 | TREC交換形式を採用するが、依存欠落時は失敗とし0埋めは採用しない。 |

## 反映先

- [01 要件](./01_requirements.md): 再現性・不完全評価の検知・独立検証。
- [02 設計](./02_architecture.md): 成果物境界、候補取得と再ランキングの分離。
- [03 ドメイン](./03_domain_model.md) / [05 データ](./05_data_model.md): 状態、ID、schema、GTとmetric policy。
- [04 ワークフロー](./04_workflows.md) / [06 エラー](./06_error_policy.md) / [07 テスト](./07_test_strategy.md) / [08 リリース](./08_release_runbook.md): 実行・異常・検証・切替。

入力snapshot、原子的な成果物公開、具体的なKPI契約、rollback方式は本PoCのための設計判断。上流の実装済み機能としては主張しない。コードの転用・依存導入前には別途ライセンスと互換性を確認する。
