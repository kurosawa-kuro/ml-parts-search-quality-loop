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


## Verification（2026-09-22）

実行コマンドと結果。

```bash
make lint            # ruff check / format --check -> All checks passed
make test            # 82 passed, 2 deselected
uv run --locked parts-search pipeline   # contracts=completed, implemented=['contracts']
uv run --locked parts-search verify-artifact artifacts/reports/<run_id>   # verified
```

実装:

| ファイル | 内容 |
|---|---|
| `src/parts_search/records/contracts.py` | 05 の 14 レコード契約を宣言で保持（Product〜PromotionDecision） |
| `src/parts_search/records/validate.py` | 単項目 + 集合 + 相関規則の検査。違反を理由付きで返す |
| `src/parts_search/records/io.py` | JSON/JSONL 読込。未対応 schema_version を拒否。`read_records` が契約違反を読込段で落とす |
| `src/parts_search/pipelines/contracts_report.py` | contracts 段階の実処理（契約棚卸しを成果物化） |
| `tests/fixtures/valid/` | 手書き正常 fixture 5 種（生成器と独立） |
| `tests/fixtures/invalid/` | 手書き異常 fixture 15 種（**1 ファイル 1 違反**） |
| `tests/fixtures/metrics_expected.json` | 07 の手計算値。DCG@10=6.5 を一致確認 |
| `tests/test_records.py` | 上記の検証。異常 fixture は**理由まで**照合する |

受入条件の充足:

- 正常 fixture が全 validator を違反ゼロで通る。契約違反 fixture が**期待した理由で**落ちる。
- 正常 0 件 / failed / not_run / unrateable / no_relevant を別に表現できることをテストで固定。
  `relevance: 0`（不適合と判定）と `null`（未判定）の混同は落ちる。
- 指標 fixture の期待値を `tests/fixtures/metrics_expected.json` に固定（DCG@10=6.5、
  IDCG@10=8.8927892607、NDCG@10=0.7309292742、RR の 1.0 / 0.5、0 件 / 失敗 / no_relevant の区別）。
- `make fmt lint test build` が成功する。

## 残り（このタスクの外）

- `Candidate` / `SplitManifest` / `FeatureSchema` / `ModelBundle` / `Experiment` / `Evaluation` /
  `FailureCase` の**手書き fixture は未作成**。契約と validator は実装済みで、
  fixture は各レコードを実際に生成する工程（T2・T3・T5・T6）で足すのが自然。
- 指標の**計算実装**は T4。ここでは期待値の fixture を固定しただけ。

## 引き継ぎ時の再検証（2026-09-22、Codex）

- 前任の staged / unstaged 変更を保持して引き継いだ。引き継ぎ直後は `make lint test` が成功（82 passed, 2 deselected）。
- CLI に T1 の接続漏れがあった。`stages` が `implemented_count=0` を固定表示し、
  `stage contracts` は completed でも exit 3 を返していた。既存テストも旧挙動を期待していた。
- `cli.py` の一覧を Stage 宣言へ接続し、完了した単一段階は exit 0、blocked は 2、
  未実装を残す実行は 3 とした。pipeline 全体の exit 0 は `golden_path_complete` の場合のみ。
- `make fmt lint test build` 成功。85 passed, 2 deselected（実サービス接続テストは未実行）。
- 実 CLI: `stages` は実装済み 1、`stage contracts` は completed / exit 0、
  生成成果物の `verify-artifact` は verified / exit 0。
- 実 CLI: `pipeline` は contracts のみ実装済み、simulation のみ blocked、exit 2、
  `golden_path_complete=false`。T2〜T8 の実装完了を示すものではない。
- 確認用成果物: `artifacts/reports/20260921T162239Z-a4100dadfa90`。
  ID の日付は UTC、作業日は Asia/Tokyo。

次工程は [T2](../02_backlog/2026-09-22-合成カタログQueryGTとfamily分割.md)。
上記「残り」の fixture 不足は引き続き未対応であり、本再検証によって充足したとは扱わない。
