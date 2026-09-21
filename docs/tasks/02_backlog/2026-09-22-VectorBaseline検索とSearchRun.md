# Vector Baseline検索とSearchRunを実装する

## Goal

固定CatalogとQuerySetからQdrantローカルでVector-only検索を実行し、全queryのCandidate、SearchResult、QueryOutcomeを追跡可能なrunとして保存する。

## Value

integrity / dev speed

## Weight Class

- Class: **Standard**
- Reason: ローカル検索adapter、CLI、結合テストを追加する可逆な変更
- Limits: max attempts 2 / max changed files 8 / protected path changes 0 / protected capability changes 0
- Owner approval: 不要

## Context

初期engineはQdrantローカル、variantは`vector_only`。Embeddingは`intfloat/multilingual-e5-small`、revisionは`614241f622f53c4eeff9890bdc4f31cfecc418b3`、前処理は`parts_e5_v1`として設定済み。[判断記録](./20260921-search-quality-poc-decisions.md)を参照。選定済みだが検索adapter・前処理本体・実Qdrant検索の実装は未完了。

## 着手前の確認（2026-09-22整理）

- 実処理は未実装。CLIの段階宣言・placeholderと依存ライブラリの導入は完了扱いに含めない。
- 依存: T1・T2は完了。次に着手可能。
- 入力: [T2の完了記録](../05_done/2026-09-22-合成カタログQueryGTとfamily分割.md)。GTは2,000万行のため、利用時は`records.io.iter_judgments`を使い全件list化を避ける。
- T1からの引継ぎ: **Candidateの独立した正常fixture**を本タスクで追加する。

## Scope

- Qdrantローカルadapterとindex manifest
- Embedding revision・前処理・Catalog checksumからのindex識別
- Candidate上位100件以上と最終SearchResultの保存
- QuerySet全件に対するQueryOutcome
- 0件、timeout、依存停止を区別するCLI終了と構造化エラー
- 実Qdrantを使う結合テスト

## Non-scope

- BM25、Hybrid、RRF、構造化boost
- LambdaRank、Feature生成、品質採否
- 外部managed Vector DB

## Plan

1. 設定済みEmbeddingのrevision・前処理契約を使用し、index manifestへ固定する。
2. index構築と検索のadapter境界を実装する。
3. Candidate、Result、Outcomeを同一runへ保存する。
4. 0件と実行失敗を分離し、全query coverageを検査する。
5. 小規模データで実Qdrant結合テストを行う。

## Acceptance Criteria

- T1から引き継いだCandidateの正常fixtureが契約検査を通る（生成器と独立した手書き例）。

- QuerySetの全queryにQueryOutcomeがちょうど1件ある。
- CandidateとSearchResultのrankが1始まりで連続し、scoreが有限である。
- 正常0件は成功outcome、timeout等はfailedとして保存される。
- 同じ入力・設定・indexで順位が決定的に再現する。
- mockだけでなくローカルQdrant実体で検索が成功する。

## Stop / Ask Owner If

- 設定済みEmbeddingのrevisionや利用条件を変更する必要があるとき。
- Qdrant以外へengine選定を変更する必要が出たとき。
