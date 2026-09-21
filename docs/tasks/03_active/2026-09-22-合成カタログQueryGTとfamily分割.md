# 合成カタログ・Query・GTとfamily分割を生成する

## Goal

FA部品の架空データからCatalog、QuerySet、GroundTruthSnapshot、SplitManifestを再現可能に生成し、Golden Pathの入力を固定する。

## Value

integrity / collection accuracy

## Weight Class

- Class: **Standard**
- Reason: データ生成と分割の挙動を複数ファイルで追加するが、ローカルの再生成可能な成果物に限定
- Limits: max attempts 2 / max changed files 8 / protected path changes 0 / protected capability changes 0
- Owner approval: 不要。ただし下記の商材契約確定後に実行

## Context

初期規模、JA/EN、family分割比率は05にある。カテゴリ構成、必須属性、単位、許容差、代替条件、言語別query分布は[未決事項](./20260921-search-quality-poc-decisions.md)に残っている。

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
- 商材 policy の内容は、[仮置き判断](./20260921-search-quality-poc-decisions.md)の
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
