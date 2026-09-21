# 疑似オンラインFeedback Loopを実装する

## Goal

固定SimulationPolicyからeventとKPIを生成し、失敗例をGT・Feature改善候補へ接続して次のExperimentを開始できるようにする。

## Value

failure detection / integrity

## Weight Class

- Class: **Standard**
- Reason: ローカルsimulation、event結合、KPI成果物を追加する可逆な変更
- Limits: max attempts 2 / max changed files 8 / protected path changes 0 / protected capability changes 0
- Owner approval: 不要。既存仮置き方針に沿ってpolicyの詳細を固定する

## Context

eventとKPI契約は05が正本。`parts_sim_v1`、観測窓1800秒、`position_biased_cascade_v1`、paired streamは設定済み。位置バイアス関数、click/conversion/reformulation確率、分布shift条件は本タスクで仮置きを具体化して版付きpolicyへ固定する。event生成・集計は未実装。

## 着手前の確認（2026-09-22整理）

- 実処理は未実装。CLIの段階宣言・placeholderと依存ライブラリの導入は完了扱いに含めない。
- 依存: T4・T6待ち。simulation.enabled=falseは未実装による意図的な停止。
- 入力: [T2の完了記録](../05_done/2026-09-22-合成カタログQueryGTとfamily分割.md)。GTは2,000万行のため、利用時は`records.io.iter_judgments`を使い全件list化を避ける。

## Scope

- impression、click、conversion、reformulation event
- event_id冪等性、競合、遅着、提示外interactionの検査
- Search Success、CTR、Zero Result、Reformulation、Conversion、Wrong Fitment KPI
- development simulationからFailureCaseとGT候補を作る経路
- 次Experimentとの関連づけ

## Non-scope

- 実ユーザー・実トラフィック・実オンライン効果の主張
- implicit eventの独立評価GTへの自動昇格
- ReleaseBundle切替

## Plan

1. 設定済みpolicy ID・観測窓・方式を使い、確率と分布shift条件を具体化してversion付きで保存する。
2. baseline/candidateで同じquery/session/乱数streamを使う。
3. event生成・結合・観測窓確定を実装する。
4. KPIとFailureCaseを生成する。
5. GT更新候補と次Experimentを関連づける。

## Acceptance Criteria

- 同一event_id同一payloadは無害な重複、異なるpayloadはエラーになる。
- 0件impressionを保持し、zero resultを二重計数しない。
- 提示外click、未結合、観測窓未完了が正式比較を止める。
- 分母0をnullとして保持し、失敗をKPI 0へ変換しない。
- implicit feedbackが独立評価GTへ自動反映されない。

## Stop / Ask Owner If

- 仮置き方針の範囲を越えて、実ユーザーの行動データや実サービスの校正が必要になったとき。
- 実サービス効果と読める主張を成果物へ追加する必要が出たとき。
