# データ契約validatorと手書きfixtureを実装する

## Goal

[データモデル](../../05_data_model.md)の最小レコード契約をコード化し、後続工程が不正入力や不完全評価を成功扱いできない土台を作る。

## Value

integrity / dev speed

## Weight Class

- Class: **Standard**
- Reason: 複数のレコード型、validator、テストを追加する可逆なローカル変更
- Limits: max attempts 2 / max changed files 8 / protected path changes 0 / protected capability changes 0
- Owner approval: 不要

## Context

設定schemaとfoundation成果物検証は実装済みだが、ProductからPromotionDecisionまでの検索・学習レコードvalidatorは未実装。合成生成器と同じロジックでテストすると誤りを自己検証するため、手書きfixtureを独立して用意する。

## Scope

- Product、Query、SplitManifest、Judgment、Candidate、SearchResult、QueryOutcomeのvalidator
- FeatureSchema、FeatureRow、ModelBundle、Experiment、Evaluation、FailureCase、PromotionDecisionのvalidator
- ID、重複、有限値、rank連続、0/null、schema_versionの検査
- [テスト戦略](../../07_test_strategy.md)の指標手計算fixtureと異常fixture
- JSON/JSONLの読込時に未対応versionを拒否する入口

## Non-scope

- 合成カタログ生成、検索engine接続、学習、指標provider導入
- 商材固有の必須属性・許容差の決定

## Plan

1. 05のレコード契約を小さいPython型と境界validatorへ写像する。
2. 生成器から独立した正常・異常fixtureを作る。
3. 欠落、重複、非有限score、rank不連続、null/0混同をテストする。
4. 後続CLIが共通利用できる読込APIを固定する。

## Acceptance Criteria

- 05の最小レコード契約を正常fixtureが通り、契約違反fixtureが理由付きで失敗する。
- 正常0件、failed、not_run、unrateable、no_relevantを区別できる。
- 指標fixtureの期待値が07の手計算値として固定される。
- `make fmt lint test build`が成功する。

## Stop / Ask Owner If

- 05と07で同じ項目の意味またはnull規約が一致しないとき。
- validator実装のために商材固有のGT意味を決める必要があるとき。
