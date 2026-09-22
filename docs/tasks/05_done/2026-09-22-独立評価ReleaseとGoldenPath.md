# 独立評価・Release・Golden Pathを通す

## Goal

Holdoutとproduction-like集合で改善候補を比較し、ReleaseBundleの切替・smoke・rollbackを含めてGolden Pathを1周する。

## Value

safety / integrity

## Weight Class

- Class: **Standard**
- Reason: ローカルPoCのbundle参照切替とE2E検証。商用deploy、secret、外部通知は含まない
- Limits: max attempts 2 / max changed files 8 / protected path changes 0 / protected capability changes 0
- Owner approval: 不要

## Context

[リリースRunbook](../../08_release_runbook.md)は手順契約だけでCLI未実装。PoC完了には独立評価でacceptedとなった改善例と、次のExperimentへ戻る証跡が必要。

## 実装（2026-09-22）

`src/parts_search/pipelines/release.py`。`parts-search stage release --gate <実験> --simulation <baseline> --simulation <candidate>` → `parts-search activate <release>` / `parts-search rollback`。

- **独立評価**: 同じ評価成果物の`holdout` splitで再比較する（tuningのoffline比較とは別のsplit）。gateに記録した入力参照が変わっていたら失敗させる。
- **online guardrail**: `searchSuccessRate`と`wrongFitmentRate`を`qualityGate.maxRegression`で判定。**分母0（null）は合格にせず`denominator_zero`で落とす**。
- decision: offline / holdout / simulation comparison_ready / guardrail が全て通ったときだけ`promote`。inconclusiveとrejectを区別して`PromotionDecision`へ保存する。**promoteのときだけ`bundle.json`を書く**。
- ReleaseBundle: 検索構成・dataset・index・embedding revision・model・FeatureSchema・policy参照・checksumを固定。
- 切替: `active.json`を同一filesystemの`os.replace`で原子的に差し替え、旧参照を`previous`と`active-history.jsonl`へ残す。`rollback`は旧参照へ戻すだけで成果物は消さない。**旧bundleのmanifest checksumが変わっていたら強制変換せず停止**する。
- smoke 6段階を`smoke.json`へ保存し、1つでもfalseなら`activate`を拒否する。

証跡は本文末尾の検証節。

## Scope

- Holdoutとproduction-likeの独立比較
- PromotionDecisionからReleaseBundleを構築
- staged検証、`active.json`の原子的切替、履歴保存
- 切替前後smokeと旧bundleへのrollback
- Golden Path 6段階とAC-001〜011の証跡
- 次Experimentへの接続

## Non-scope

- 商用環境deploy、実トラフィックA/B、外部通知
- acceptedを得るための閾値変更
- Hybrid等の追加改善方式

## Plan

1. 08のReleaseBundleとactive参照を実装する。
2. acceptedなcandidateをstagedでsmokeする。
3. 原子的に切り替え、切替後smokeを実行する。
4. 故障fixtureで旧bundleへrollbackする。
5. prepareから次ExperimentまでをE2Eで1周する。

## Acceptance Criteria

- Holdoutとproduction-likeが学習・tuning・development simulationから分離されている。
- accepted decisionなしにcandidateをactiveへ昇格できない。
- 切替失敗時にmodelだけでなくindex・Feature・設定・schemaの組を旧版へ戻せる。
- smoke 6段階とAC-001〜011に実成果物の証跡がある。
- 改善前後、採否、release、rollback、次ExperimentをIDで追跡できる。

## Stop / Ask Owner If

- 独立評価集合を改善作業へ流用する必要が出たとき。
- acceptedな改善例が得られず、PoCの範囲または成功条件を変更する必要があるとき。

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
