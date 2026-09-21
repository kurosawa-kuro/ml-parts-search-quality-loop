# Experiment比較と品質Gateを実装する

## Goal

入力・設定・variantを凍結したExperimentを実行し、baselineとcandidateを同じ比較条件で評価してaccepted/rejected/inconclusiveを保存する。

## Value

integrity / safety

## Weight Class

- Class: **Standard**
- Reason: ローカル実験オーケストレーションと比較成果物を追加する可逆な変更
- Limits: max attempts 2 / max changed files 8 / protected path changes 0 / protected capability changes 0
- Owner approval: 不要。承認済み仮置き値を使い、比較前に凍結する

## Context

品質Gateの意味は07が正本。`parts_gate_v1`、最小NDCG差0.01、許容回帰0.01（誤適合0.005）、最低Slice件数30、seed `[11,22,33]` は設定済みの仮置き。[判断記録](./20260921-search-quality-poc-decisions.md)に従い、candidate比較前にmanifestへ凍結する。Gateの比較処理は未実装。

## 着手前の確認（2026-09-22整理）

- 実処理は未実装。CLIの段階宣言・placeholderと依存ライブラリの導入は完了扱いに含めない。
- 依存: T4のEvaluationとT5のcandidate run待ち。
- 入力: [T2の完了記録](../05_done/2026-09-22-合成カタログQueryGTとfamily分割.md)。GTは2,000万行のため、利用時は`records.io.iter_judgments`を使い全件list化を避ける。
- T1からの引継ぎ: **Experiment・PromotionDecisionの独立した正常fixture**を本タスクで追加する。

## Scope

- Experiment、Run、EvaluationRunの関連づけ
- 入力・設定・seed・依存・成果物checksumの凍結
- baseline/candidate比較signatureの照合
- query差分、Slice、反復seed結果
- PromotionDecisionとgate終了コード
- retry_of、parent_experiment_id、失敗runの保持

## Non-scope

- ReleaseBundle切替
- 疑似オンラインsimulation
- 品質閾値を実装側で決めること

## Plan

1. 設定schemaにあるGatePolicyを読み、比較前にmanifestへ凍結する。
2. 複数variantを同じ入力条件で実行する。
3. signatureとcoverageを照合して比較する。
4. accepted/rejected/inconclusiveを理由・分母とともに保存する。
5. 再試行が既存runを変更しないことを検証する。

## Acceptance Criteria

- T1から引き継いだExperiment・PromotionDecisionの正常fixtureが契約検査を通る（生成器と独立した手書き例）。

- 比較前にGatePolicyが凍結され、candidate結果から変更できない。
- signature不一致、不完全評価、必須Slice不足はinconclusiveになる。
- 完全比較のみacceptedまたはrejectedになる。
- run失敗と品質不採用を別の状態・終了コードで識別できる。
- manifestから入力・設定・結果・decisionを第三者が辿れる。

## Stop / Ask Owner If

- 凍結した品質閾値・guardrail・最低Slice件数・seedをcandidateの結果に応じて変更する必要が出たとき。
- baselineとcandidateで固定すべき入力を一致させられないとき。
