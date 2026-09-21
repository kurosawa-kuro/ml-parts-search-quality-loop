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

初期engineはQdrantローカル、初期variantは`vector_only`。Embedding model/revisionと前処理は[未決事項](./20260921-search-quality-poc-decisions.md)で検索実装前に確定する。

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

1. Embedding model/revisionを確定して設定schemaへ反映する。
2. index構築と検索のadapter境界を実装する。
3. Candidate、Result、Outcomeを同一runへ保存する。
4. 0件と実行失敗を分離し、全query coverageを検査する。
5. 小規模データで実Qdrant結合テストを行う。

## Acceptance Criteria

- QuerySetの全queryにQueryOutcomeがちょうど1件ある。
- CandidateとSearchResultのrankが1始まりで連続し、scoreが有限である。
- 正常0件は成功outcome、timeout等はfailedとして保存される。
- 同じ入力・設定・indexで順位が決定的に再現する。
- mockだけでなくローカルQdrant実体で検索が成功する。

## Stop / Ask Owner If

- Embedding model/revisionまたは利用条件が確定していないとき。
- Qdrant以外へengine選定を変更する必要が出たとき。
