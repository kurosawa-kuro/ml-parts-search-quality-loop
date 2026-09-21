# 疑似オンラインFeedback Loopを実装する

## Goal

固定SimulationPolicyからeventとKPIを生成し、失敗例をGT・Feature改善候補へ接続して次のExperimentを開始できるようにする。

## Value

failure detection / integrity

## Weight Class

- Class: **Standard**
- Reason: ローカルsimulation、event結合、KPI成果物を追加する可逆な変更
- Limits: max attempts 2 / max changed files 8 / protected path changes 0 / protected capability changes 0
- Owner approval: 不要。ただしSimulationPolicy確定後に実行

## Context

eventとKPI契約は05が正本。観測窓、位置バイアス、click/conversion/reformulation確率、distribution shiftは[未決事項](./20260921-search-quality-poc-decisions.md)に残る。

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

1. SimulationPolicyを確定しversion付きで保存する。
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

- SimulationPolicyの確率・観測窓・分布shift条件が未確定のとき。
- 実サービス効果と読める主張を成果物へ追加する必要が出たとき。
