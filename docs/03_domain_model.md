# 03 ドメインモデル

> 設計契約v1。**T1〜T8まで実装済み（2026-09-22）**で、検索・学習・評価・疑似オンライン・Releaseのドメインは実処理が通っている。参照実装の観測と採否理由は [レビュー](./reference-implementation-review.md)。物理項目は [05](./05_data_model.md) を正本とする。

## 用語と関係

| 用語 | 意味・境界 |
|---|---|
| Product / CatalogSnapshot | 架空部品と、その属性・多言語表現を固定した集合 |
| Query / QueryFamily | 言語別の検索要求と、同じ意図から派生した翻訳・言い換えの集合 |
| QuerySet / SplitManifest | 評価対象集合と、familyをどの分割に割り当てたかの記録 |
| Judgment / GroundTruthSnapshot | query-productの判定と、採用した判定を固定した集合。クリックそのものではない |
| SearchConfiguration | 候補取得・filter・fusion・返却数等の版付き設定 |
| CandidateSet | 再ランキング前の候補と取得スコア。候補漏れを評価する境界 |
| FeatureSchema / FeatureDataset | 順序・型・欠損規約付き特徴量定義と学習・推論の入力 |
| ModelBundle | 学習済みモデル、FeatureSchema、学習入力・gain定義を固定した単位 |
| Experiment / Run | 比較仮説・固定入力・variantの宣言と、実行の試行。再試行は別run |
| SearchRun / EvaluationRun | 順位付き結果と、固定GT・MetricPolicyに対する評価成果物 |
| Impression / Interaction | 実際に提示した順位と、それに結合するクリック・購入等 |
| FailureCase | 失敗Query、観測根拠、原因分類、次の改善案 |
| PromotionDecision | baselineとcandidateの比較に対する採用・保留・棄却の判断 |
| ReleaseBundle | 疑似オンラインで使用する検索構成・index・モデルを固定した単位 |

```text
QueryFamily → QuerySet → Experiment → Run
CatalogSnapshot ───────────┘           ├─ CandidateSet → SearchRun → Impression → Interaction
GroundTruthSnapshot + MetricPolicy ───└─ EvaluationRun → FailureCase → 次のExperiment
FeatureDataset → ModelBundle → SearchRun
EvaluationRun → PromotionDecision → ReleaseBundle
```

## ライフサイクル

実行状態は `pending → running → succeeded / failed`。失敗runは上書きせず、`retry_of`で新しいrunへ接続する。成功は成果物とchecksumの検証後に確定する。Experimentの設定は実行開始時に凍結し、変更は新しいexperiment_idとする。

検索outcomeはクエリごとに `success / zero_results / failed / not_run`。0件は正常応答であり、通信失敗とは異なる。実行成功は品質改善の合格を意味しない。

判定状態は `unjudged / judged / unrateable`。judgedのみrelevanceを持つ。根拠不足はunrateable、未実施はunjudgedとし、0へ変換しない。競合判定は根拠を確認してから次版GTへ解決する。

採否は `accepted / rejected / inconclusive`。条件不足・不完全評価はinconclusive。ReleaseBundleは `staged → active → retired`、smoke失敗時は旧activeへ戻し失敗bundleをquarantinedとして保持する。

## 不変条件

- 同一QueryFamilyはtrain / tuning / holdout / productionの複数分割へ跨がない。商品カタログ共有は許すが、未知SKUへの汎化を実証したとは扱わない。
- GT、検索結果、指標は同じquery_id / product_idへ結合する。文字列や並び順だけで結合しない。
- explicitな必須仕様への不適合は型番一致より優先する。条件不足や矛盾したQueryは判定保留にする。
- 学習ラベル・未来のinteraction・評価結果をFeatureへ混ぜない。時点依存Featureはimpression時点以前の値を使う。
- Holdoutと最終production検証を改善材料にした場合、その集合を独立評価として再利用しない。開発側へ移し、別familyの未使用集合を確保する。
- 検索候補にない正解商品をrerank評価時だけ追加しない。候補取得の改善と候補内の順位改善を分ける。

## 関連タスク

[未決事項](./tasks/02_backlog/20260921-search-quality-poc-decisions.md) / [実装計画](./tasks/03_active/20260921-search-quality-poc-implementation.md)。用語・状態変更時は05〜08への影響をtaskへ記録する。
