# 02 アーキテクチャ

> 設計契約v1。ローカル参照実装を確認して改訂。アプリは未実装であり、以下のパス・インターフェースは予定。観測事実・固定commit・採否理由は [参照実装レビュー](./reference-implementation-review.md)。

## 概要と実行モデル

ローカルのバッチ処理を成果物境界で接続する。検索・学習・評価を独立に再実行できる形とし、PoC段階では常駐API、外部Feature Store、分散queueを必須にしない。

```text
Catalog + QuerySet + SplitManifest + GT snapshot
                      ↓
                  Experiment
                      ↓
Retrieval → CandidateSet → Feature Generation → Ranker → SearchRun
                  │                                 │
                  └────────── Evaluation ← GT + MetricPolicy
                                      ↓
                               Metrics / Slices / FailureCase
                                      ↓
                      GT更新・Feature改善・Train → 新Experiment
                                      ↓
                       Holdout + Production-like validation
                                      ↓
                     PromotionDecision → ReleaseBundle → simulation
                                                               ↓
                                                    Events → FailureCase
```

正本の分担: [01](./01_requirements.md)は要求、[03](./03_domain_model.md)は概念・状態、[05](./05_data_model.md)はデータ・GT・指標契約、[04](./04_workflows.md)は手順、[06](./06_error_policy.md)は異常、[07](./07_test_strategy.md)は検証、[08](./08_release_runbook.md)は疑似オンライン切替。

## 構成要素と境界

| 構成要素 | 入力 → 出力 / 責務 | 予定パス |
|---|---|---|
| Catalog | 生成設定 → CatalogSnapshot・QuerySet・SplitManifest。GT用の潜在正解情報を検索入力へ露出しない | `src/catalog/` |
| Judgments | 属性・明示条件・判定根拠 → GroundTruthSnapshot。未判定・不適合を分離 | `src/judgments/` |
| Retrieval | catalog/index + Query + SearchConfiguration → CandidateSet・QueryOutcome | `src/retrieval/` |
| Features | query-product・取得score・時点属性 → FeatureDataset。学習/推論で共通生成 | `src/features/` |
| Ranker | FeatureDataset + train labels → ModelBundle、候補 + ModelBundle → SearchRun | `src/ranker/` |
| Evaluation | CandidateSet / SearchRun + GT + MetricPolicy → EvaluationRun。検索engineを呼ばない | `src/evaluation/` |
| Failure analysis | query別評価・Slice・event → FailureCase。原因分類と証拠を保持 | `src/failure_analysis/` |
| Feedback loop | 固定simulation条件 + SearchRun → Events・暗黙判定候補。評価GTを直接更新しない | `src/feedback_loop/` |
| Experiments | 設定凍結、run実行・入力照合、成果物公開、比較・採否 | `src/experiments/` |
| Artifacts | manifest・checksum・JSON/JSONL・TREC adapter、版互換検査 | `src/artifacts/` |
| エージェントガイド | Codex / 他エージェント共通方針 | `AGENTS.md` |
| Claudeガイド / skills | Claude Codeの指示と繰り返し手順 | `CLAUDE.md` / `.claude/skills/` |
| タスク文書 | 作業計画・証跡・残件 | `docs/tasks/` |

各処理はmanifest参照で入力を受け、成功成果物の参照を返す。run中の一時出力を後続へ渡さない。学習・評価が必要とするGTは明示引数とし、Retrieval / 推論には渡さない。

## Retrievalと再ランキング

初期比較は `vector_only` と `vector_ltr_v1`。構造化条件のみの効果を調べる `vector_structured` をablationとして追加する。BM25 / Hybrid / RRFは次段階候補。初期Vector DBはQdrantローカル。pgvector / FAISSは代替候補。Embeddingモデルは未決、構造化filterは初期無効とし、boost方式はablation実装時に決める。

- 候補取得は100件以上を要求できる契約とし、取得件数・filter条件・返却件数を保存する。catalogが小さい場合等の実件数も残す。
- `source_score`と`score_type`を保持する。dense cosine、BM25、RRF、モデルscoreは同じ尺度ではない。RRFの結果をsemantic_scoreへ入れない。
- Hybridを採用する場合はdense/sparse双方のprefetch件数、fusionパラメータ、重複排除を記録する。元scoreが得られない場合は欠損として扱い、0で捏造しない。
- 初期runは候補100件を最終順位まで保持し、上位10件だけの保存でRecall@100やMRR@100を失わないようにする。
- rerankのみの効果測定は同一CandidateSetで比較する。Retrievalの変更は別実験で候補Recallも比較する。
- Retrieval失敗時に別engineへ黙ってfallbackしない。fallbackを実験するなら別variantとして識別する。

## Featureと学習

LightGBM LambdaRankを基本方針とする。モデル名だけで再現性を表さず、ModelBundleへFeature順序・型・欠損・変換・label_gainを固定する。推論時に互換性が一致しなければ停止する。

Feature候補はsemantic / BM25 score、型番・径・ねじ・材質・カテゴリ・メーカー一致、在庫、人気。後二者は時点を固定する。自動車部品なら年式・型式・位置一致を検討する。欠損フラグを保持し、Feature変更は新schema_idとする。

学習データはqueryごとに連続した行とgroup sizeを作り、group size合計と行数の一致を検査する。splitは行単位の乱数ではなくQueryFamily単位。正規化等のfitはtrainのみ、early stoppingや設定探索はtuningのみで行う。空学習・有効な順位差のない学習集合は失敗にする。GTにない候補を自動で負例にしない。

合成GTのルールをFeatureとして直接出力すると答えの再現になるため、通常の商品・クエリ情報から得られる一致特徴量だけを使う。GT rule_id・relevance・future conversion等は推論入力から排除する。合成ルール由来の限界は評価報告に明記する。

## 実験・評価・Feedback

Experimentは入力snapshotと複数variantを固定する。Runは実行試行、EvaluationRunは評価の試行であり、同じ検索結果を新GTで再評価しても元結果を変更しない。

評価はQuerySetの全IDを起点にし、各queryのoutcomeを確認する。GTやrunに存在する行だけを平均して欠落を隠さない。metric policy、比較signature、coverageの規約は05を参照する。

Feedbackはdevelopment simulationで改善材料を集める。最後のproduction分布検証は凍結した別familyとsimulation policyで実行する。その結果から改善を行う場合、当該検証集合を開発側へ移し、独立な最終集合を更新する。実オンライン効果や位置バイアス補正済み効果を主張しない。

## Golden Pathとの対応

| 要件のステップ | 主な境界 | 完了成果物 | 停止条件 |
|---|---|---|---|
| 1. 準備 | Catalog / Judgments / Experiments | 入力snapshot・split・policy manifest | 未決の必須設定、GT不備、family重複 |
| 2. Baseline評価 | Retrieval / Evaluation | candidates・results・outcomes・metrics | 欠落query、依存欠落、schema不整合 |
| 3. 失敗抽出 | Feedback / Failure analysis | Events・FailureCase | 未結合event、根拠のない分類 |
| 4. 更新・学習 | Judgments / Features / Ranker | 新GT・FeatureDataset・ModelBundle | group不整合、リーク、学習不能 |
| 5. 独立比較 | Experiments / Evaluation | Holdout / production比較・採否 | signature不一致、不完全評価 |
| 6. 次へ戻す | Experiments / Feedback | ReleaseBundle・smoke・次の実験 | 切替後smoke失敗、旧版復旧不能 |

## 実装順序と採用しない挙動

1. データ契約validatorと小さな手書きfixture、GT / split / MetricPolicyを作る。
2. Vector-only検索と成果物評価を接続する。
3. FeatureとLambdaRankを接続し、学習・推論の一致を検証する。
4. development simulation、FailureCase、GT更新から再実験へ接続する。
5. 独立検証・採否・bundle切替・rollbackまで通す。
6. 必要に応じHybrid等を追加する。

参照コードの「評価依存がなければ0を返す」「小データでtrain/testを重複させる」「未実行queryが平均から消える」「他タスクの漏洩情報をFeatureに使う」は採用しない。KDD CupのLightGBMは確率統合・期待gain順の参考であり、LambdaRank実装の直接根拠ではない。

## 運用境界と関連タスク

設定・秘密情報・保存先は05に従う。PoCのDeployはローカルsimulationのbundle切替であり商用配備ではない。参照repoは読み取り用で、アプリのruntime依存にしない。

[未決事項](./tasks/02_backlog/20260921-search-quality-poc-decisions.md) / [実装計画](./tasks/02_backlog/20260921-search-quality-poc-implementation.md)。構造・責務変更はtaskで影響と検証を記録し、確定事項を本文へ反映する。
