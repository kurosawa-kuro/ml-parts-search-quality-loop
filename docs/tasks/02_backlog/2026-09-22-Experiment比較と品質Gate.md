# Experiment比較と品質Gateを実装する

## Goal

入力・設定・variantを凍結したExperimentを実行し、baselineとcandidateを同じ比較条件で評価してaccepted/rejected/inconclusiveを保存する。

## Value

integrity / safety

## Weight Class

- Class: **Standard**
- Reason: ローカル実験オーケストレーションと比較成果物を追加する可逆な変更
- Limits: max attempts 2 / max changed files 8 / protected path changes 0 / protected capability changes 0
- Owner approval: 不要。ただし品質閾値はowner判断後に実行

## Context

品質Gateの意味は07が正本。`min_ndcg_delta`、guardrail、最低Slice件数、反復seed数はcandidateを見る前に[未決事項](./20260921-search-quality-poc-decisions.md)で確定する。

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

1. GatePolicyを設定schemaとmanifestへ追加する。
2. 複数variantを同じ入力条件で実行する。
3. signatureとcoverageを照合して比較する。
4. accepted/rejected/inconclusiveを理由・分母とともに保存する。
5. 再試行が既存runを変更しないことを検証する。

## Acceptance Criteria

- 比較前にGatePolicyが凍結され、candidate結果から変更できない。
- signature不一致、不完全評価、必須Slice不足はinconclusiveになる。
- 完全比較のみacceptedまたはrejectedになる。
- run失敗と品質不採用を別の状態・終了コードで識別できる。
- manifestから入力・設定・結果・decisionを第三者が辿れる。

## Stop / Ask Owner If

- 品質閾値、guardrail、最低Slice件数、反復seed数が未確定のとき。
- baselineとcandidateで固定すべき入力を一致させられないとき。
