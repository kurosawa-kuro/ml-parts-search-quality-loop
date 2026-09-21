# オフライン評価・Slice・FailureCaseを実装する

## Goal

SearchRunと固定GTからRecall@100、NDCG@10、MRR@100、Slice、FailureCaseを生成し、不完全な評価を合格扱いしない評価経路を作る。

## Value

failure detection / integrity

## Weight Class

- Class: **Standard**
- Reason: 指標計算、成果物、CLI、テストを追加するローカルで可逆な変更
- Limits: max attempts 2 / max changed files 8 / protected path changes 0 / protected capability changes 0
- Owner approval: 不要

## Context

MetricPolicy v1と手計算値は05・07が正本。評価はQuerySet全件を起点にし、runやGTに現れた行だけで平均してはならない。

## 着手前の確認（2026-09-22整理）

- 実処理は未実装。CLIの段階宣言・placeholderと依存ライブラリの導入は完了扱いに含めない。
- 依存: T1・T2は完了。T3のSearchRun待ち。
- 入力: [T2の完了記録](../05_done/2026-09-22-合成カタログQueryGTとfamily分割.md)。GTは2,000万行のため、利用時は`records.io.iter_judgments`を使い全件list化を避ける。
- T1からの引継ぎ: **Evaluation・FailureCaseの独立した正常fixture**を本タスクで追加する。

`ir_measures 0.4.3`は導入・版設定済み。provider APIでpolicyを再現する実装・一致検証は本タスクに残る。

## Scope

- MetricPolicy v1の指標計算とprovider版固定
- query単位値、全体集計、language/query_type必須Slice
- coverage、no_relevant、unrateable、failed/not_runの分離
- retrieval漏れとrerank不良を区別するFailureCase
- comparison signatureの生成

## Non-scope

- 学習、Feature、モデル比較、PromotionDecision
- 疑似オンラインKPI

## Plan

1. T1の`tests/fixtures/metrics_expected.json`を独立オラクルとして使用し、指標計算を実装する。
2. provider結果との一致とgain二重適用防止を検証する。
3. QuerySet全件からEvaluationを生成する。
4. SliceとFailureCaseへ根拠IDを残す。
5. 不完全条件を`inconclusive`にする。

## Acceptance Criteria

- T1から引き継いだEvaluation・FailureCaseの正常fixtureが契約検査を通る（生成器と独立した手書き例）。

- 07の手計算fixtureと絶対誤差1e-9以内で一致する。
- 正常0件は0、実行失敗・未実行はnullとして区別される。
- 全体と各Sliceに対象数、評価可能数、欠落数がある。
- failed/not_runまたは未判定GTが1件でも残れば正式比較を許可しない。
- FailureCaseからquery、run、根拠成果物を辿れる。

## Stop / Ask Owner If

- 05と利用providerで指標定義が一致しないとき。
- Failure分類に新しい業務上の意味を追加する必要があるとき。
