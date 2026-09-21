# 構造化FeatureとLambdaRankを実装する

## Goal

検索候補へ部品固有の一致Featureを付与し、LightGBM LambdaRankの学習・推論を同じFeatureSchemaで再現できるようにする。

## Value

integrity / failure detection

## Weight Class

- Class: **Standard**
- Reason: Feature生成、モデル学習、bundle、互換テストを追加するがローカル成果物に限定
- Limits: max attempts 2 / max changed files 8 / protected path changes 0 / protected capability changes 0
- Owner approval: 不要

## Context

Feature候補とlabel_gain `[0,0,1,3,7]` は02・05に定義済み。`parts_features_v1`のIDとLightGBM依存は設定済み。列順・型・default/null・変換版・checksum・数値許容差は本タスクで具体化して凍結する。依存の単体学習実測は、Feature生成・ModelBundle実装の完了を意味しない。

## 着手前の確認（2026-09-22整理）

- 実処理は未実装。CLIの段階宣言・placeholderと依存ライブラリの導入は完了扱いに含めない。
- 依存: T1・T2は完了。T3のCandidateSet待ち。
- 入力: [T2の完了記録](../05_done/2026-09-22-合成カタログQueryGTとfamily分割.md)。GTは2,000万行のため、利用時は`records.io.iter_judgments`を使い全件list化を避ける。
- T1からの引継ぎ: **FeatureRow・FeatureSchema・ModelBundleの独立した正常fixture**を本タスクで追加する。

## Scope

- 型番、寸法、材質、カテゴリ等の一致Feature
- 順序・型・欠損・変換版を固定するFeatureSchema
- query group境界を守る学習dataset
- LightGBM LambdaRank学習とModelBundle
- 同一CandidateSetに対する`vector_only`と`vector_ltr_v1`比較用run
- 学習・推論Feature互換、未来情報・label漏洩テスト

## Non-scope

- BM25、Hybrid、RRF
- candidate取得方式の変更
- 深層ranker、オンライン学習

## Plan

1. FeatureSchemaと欠損規約を確定する。
2. 学習・推論共通のFeature生成器を実装する。
3. query groupとlabel結合を検査して学習する。
4. ModelBundleへschema checksum、設定、label_gainを保存する。
5. 同一CandidateSetをrerankして互換・漏洩・再現性を検証する。

## Acceptance Criteria

- T1から引き継いだFeatureRow・FeatureSchema・ModelBundleの正常fixtureが契約検査を通る（生成器と独立した手書き例）。

- Feature順序・型・欠損規約が学習と推論で一致する。
- group size合計が行数と一致し、family splitを跨がない。
- GT rule_id、評価label、未来interactionが推論Featureへ入らない。
- schema checksum不一致を黙って補正せず拒否する。
- モデルとFeatureSchemaを再読込して同じ候補順位を再現できる。

## Stop / Ask Owner If

- Feature追加に業務上の優先順位やGT規則そのものを埋め込む必要があるとき。
- 有効な順位差のある学習集合を作れないとき。
