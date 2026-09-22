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

## 実装（2026-09-22）

`src/parts_search/pipelines/simulation.py`。`parts-search stage simulation --dataset .. --judgments .. --search .. [--split ..] [--release-id ..]`。

- **版付きpolicyを config で固定**（`parts_sim_v1.0.0`）。位置バイアス`1/rank**decay`、click確率（relevant .65 / marginal .30 / irrelevant .03）、conversion .25、reformulation（zero .80 / noClick .45 / afterClick .05）、観測窓1800秒、sessionsPerQuery 4、seed 777。**いずれかがnullなら段階がblockedになる**（loaderのblockersに追加）。
- **paired random stream**: 乱数の種は`policyVersion|seed|query_id|session_index`だけで、variantを含めない。baselineとcandidateで同じquery・session・乱数を使う（integration testでsession集合の一致を検査）。
- event: impression（0件でも空itemsで1回）・click（cascadeで最初のclickで離脱）・conversion・reformulation。`event_id`重複は同payloadなら無害、異payloadは`DuplicateEventError`。
- **観測窓外の遅着は`quarantine.jsonl`へ隔離**しKPIの母集合から外す。これは設計どおりの除外なので比較を止めない。**止めるのは欠陥**（提示外product・孤児interaction・観測窓未完了・failed impression）で、`kpis.json`の`blocking_reasons`に出す。
- KPI 6種を**分母0はnull**で保持（`_rate`）。`searchSuccessRate` / `ctr` / `zeroResultRate` / `reformulationRate` / `conversionRate` / `wrongFitmentRate`。
- FailureCase（`simulation_miss`）とGT候補を生成。GT候補は`promoted_to_evaluation_gt: false`固定で、`judgments.promoteImplicitToEvaluation`がtrueなら段階自体を失敗させる。

証跡は本文末尾の検証節。

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

## 一括検証（2026-09-22、実E5 + ローカルQdrant）

`make test-all` 相当: `uv run --locked pytest -m ''` → **146 passed**。`ruff check` clean。

CLI通し実行（1,500 SKU / 700 family / 1,400 Query / 完全GT 2,100,000行）:

```
parts-search pipeline  → exit 0 / golden_path_complete: true / quality: promote
  contracts catalog judgments retrieval evaluation training gate simulation ×2 release = 全 completed
```

| 観測 | 実測 |
|---|---|
| offline比較（seed 11/22/33） | accepted・repetition_complete |
| 独立holdout比較 | **accepted**・評価可能 210 query・NDCG@10 差 **+0.2762**・Recall@100 差 0 |
| online guardrail | searchSuccessRate **+0.2143** / wrongFitmentRate **−0.2143** → いずれも合格 |
| simulation | joined impression **560**・orphan 0・comparison_ready true |
| KPI（baseline→candidate） | searchSuccess 0.757→**0.971** / CTR 0.566→0.718 / conversion 0.150→0.195 / reformulation 0.227→0.171 / wrongFitment 0.243→**0.029** / zeroResult 0.0 |
| smoke 6段階 | すべて passed（`model_compatibility`はmodelを実際に読み込みFeatureSchema checksumと列順を照合） |
| decision | **promote**・`bundle.json`を生成 |
| active切替 | activate（previous: null）→ activate（previous: 前release）→ rollback で前releaseへ復帰。`active-history.jsonl` 3行。旧bundleは保持 |

小規模（120 SKU / 40 family）では `minSliceQueries=30` を満たさず **exit 4 / inconclusive**。
実行は成功しているので exit 1 と混同しない。**採用を得るために閾値を下げていない。**
