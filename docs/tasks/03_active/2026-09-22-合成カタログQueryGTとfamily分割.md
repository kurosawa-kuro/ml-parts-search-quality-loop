# 合成カタログ・Query・GTとfamily分割を生成する

## Goal

FA部品の架空データからCatalog、QuerySet、GroundTruthSnapshot、SplitManifestを再現可能に生成し、Golden Pathの入力を固定する。

## Value

integrity / collection accuracy

## Weight Class

- Class: **Standard**
- Reason: データ生成と分割の挙動を複数ファイルで追加するが、ローカルの再生成可能な成果物に限定
- Limits: scopeはSPEC.mdの名指し箇所（generator/GT/store/reader/CLI、独立テストと連動docs）。protected path changes 0 / protected capability changes 0
- Owner approval: 不要。2026-09-22の仮置き判断に沿って商材契約を05へ具体化

## Context

初期規模、JA/EN、family分割比率は05にある。カテゴリ構成・属性・単位・許容差・代替条件・言語別分布は、[仮置き判断](../02_backlog/20260921-search-quality-poc-decisions.md)に沿って本タスクで具体化し、05へ記録した。

## Scope

- Product familyを先に分割し、その後で翻訳・派生Queryを生成
- 型番、寸法、材質、規格、用途を含む架空FA部品Catalog
- JA/EN QuerySetとconstraints
- GT policy v1による完全判定GTとunrateableの分離
- seed、件数、集合digest、生成設定を持つmanifest
- family交差、単位変換、必須条件違反を検出するテスト

## Non-scope

- 実商品・実顧客データ、外部カタログ取得
- Retrieval、Embedding、学習、暗黙feedback

## Plan

1. 未決事項のうち生成に必要な商材契約を確定し、正本文書へ反映する。
2. family単位の決定的分割を実装する。
3. CatalogとQueryを分割後に生成する。
4. GTを別工程で生成し、入力への潜在正解情報漏洩を検査する。
5. 小規模fixtureと設定規模の生成を別テストにする。

## Acceptance Criteria

- 同一seedと設定でID・split・digestが一致する。
- train/tuning/holdout/production間でfamilyが交差しない。
- GTはcatalog全体へ適用され、未判定と不適合を区別する。
- Query/Feature入力にGT rule_idや未来情報が混入しない。
- 成果物が05のdataset/judgments配置へ原子的に公開される。

## Stop / Ask Owner If

- カテゴリ構成、必須属性、数値許容差、代替条件が未確定のとき。
- 生成規則だけでは曖昧な自然文を一意に判定できないとき。

## 引き継ぎ時の実装準備（2026-09-22）

- T1 の再検証と CLI 接続漏れ修正を実施。85 passed, 2 deselected、lint/build 成功。
  T2 の生成器はまだ未実装。
- 商材 policy の内容は、[仮置き判断](../02_backlog/20260921-search-quality-poc-decisions.md)の
  「全項目を仮置きで確定した」に沿って T2 で具体化できる。古い owner 判断待ちの記述だけで停止しない。
- `read_records` は集合全体を list にし、JSONL 読込は 256 MiB 上限。
  `publish_run` も JSONL の list と全出力 bytes をメモリへ保持する。
  既定の 10,000 SKU × 1,000 family に JA/EN 各1件を作るだけでも GT は2,000万行になる。
  完全判定を省略せず、ストリーム生成・検査・checksum・原子的公開を含む実装計画にする。
- `validate_split_disjoint` は現在 assignments の値が文字列かを調べるだけ。
  T2 では許可 split、全 family の割当、翻訳・派生 query の同一 family、件数と digest を検証する。
- `schema_version` は I/O で検査する一方、行契約の許可項目には含まれない。
  metadata に version を持つ場合は、それを検査してから `read_records` を呼ぶ。
  GT 大規模読込用 API を足す際も、この検査を抜かない。
- 最初に小規模の独立 fixture と決定性・漏洩・GT優先順位のテストを作り、
  続いて既定規模の生成を実測する。Catalog/Query 入力へ GT の rule_id や生成時の正解IDを混入させない。

## 実装（2026-09-22）

- `synthetic.py`: 版付き架空FA属性policy、単位正規化、family先行分割、JA/EN生成、入力検査。
- `judgments.py`: 保存済みdatasetを検査・読込後、GT policyの全直積を生成。
  query単位のバッファでT1 validatorを通し、判定不能もnull行で保持する。
- `runstore.py`: iterable JSONLと逐次checksum。公開前検証・rename・既存run不変を維持。
- `records/io.py`: `iter_judgments`。manifest版とchecksum、行契約、batch境界の重複、最終件数を検査。
- stage/CLI: catalogとjudgmentsを実処理へ。`--dataset`明示入力、pipeline内の入力受渡し。
- `test_synthetic.py`: 生成器と独立のGT例、`fixtures/valid/splits.json`、単位/分割漏洩、
  決定性、直積網羅、欠損/不適合/正解なしの区別、版/改変拒否、途中失敗の非公開。

旧taskの8ファイル制限は、大規模処理に不可欠な共通store/readerとCLI接続・連動文書を
含まないため、ユーザーが今回明示した「完全判定GTの大規模処理」を満たす範囲へ更新。
検索・学習・外部サービス・依存変更には広げていない。

## Verification（2026-09-22）

- `make fmt lint test build`: 成功。**114 passed, 2 deselected**。除外2件はT3の実Qdrant接続テスト。
- `git diff --check` / `git diff --cached --check`: 成功。
- 小規模CLI pipeline: contracts/catalog/judgmentsの3段階がcompleted、simulationはblocked、
  他5段階はskeleton、Golden Path全体は未完了。simulation有効時も未実装が残るのでexit 3。
- 小規模GT再生成の出力checksum一致、全query-product直積一致、必須違反が型番一致より優先、
  mm/cm/in換算、family間の同一意図拒否、同family内の翻訳条件一致、
  判定不能と全0のno_relevantを別に集計することをテスト。
- store中断時に公開先とstagingが残らないこと、同じIDの再公開が既存成果物を変えず
  streamを消費する前に拒否されることをテスト。

既定設定の実CLI（exitはすべて0）:

```bash
uv run --locked parts-search stage catalog
uv run --locked parts-search stage judgments --dataset artifacts/datasets/20260921T163519Z-00509a39e003
uv run --locked parts-search verify-artifact artifacts/judgments/20260921T163520Z-c82b50e6a3c3
```

| 項目 | 実測 |
|---|---|
| 商品 / family / Query | 10,000 / 1,000 / 2,000（JA/EN各1,000） |
| family分割 | train 600 / tuning 150 / holdout 150 / production 100 |
| GT ID | `gt-eb7ff6a2a3b017531474b90b` |
| GT行数 / judged / unrateable | 20,000,000 / 20,000,000 / 0 |
| 判定完了Query / no_relevant Query | 2,000 / 0 |
| relevance 0 / 1 / 2 / 3 / 4 | 17,778,676 / 1,480,474 / 738,850 / 1,332 / 668 |
| JSONLサイズ | 4,837,768,562 bytes |
| Catalog→GT→verify所要時間 | 470.97秒 |
| 子プロセス最大RSS（macOS実測） | 119,058,432 bytes（約114 MiB） |

機械可読レポートは`artifacts/t2-verification.json`（Git管理外）。UTCのrun_idと
Asia/Tokyoの作業日は日付が異なる。性能値はこのIntel Macでの単発測定。

未検証・後続範囲: 実商品適合性、任意自然文の解析、検索・学習・指標・品質改善効果。
商材policyは合成PoC向けの仮置きであり、実商品業務に転用する契約ではない。
既存foundation同様、未コミットコードの自動patch保存は未実装。
