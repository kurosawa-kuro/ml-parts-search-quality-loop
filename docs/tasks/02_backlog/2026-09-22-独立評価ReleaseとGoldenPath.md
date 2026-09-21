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
