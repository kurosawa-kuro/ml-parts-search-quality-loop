# T2: 合成Catalog / Query / family分割 / 完全判定GT

## Goal / Scope

10,000 SKU、1,000 family、JA/EN 2,000 Query、2,000万query-product判定を
再現可能に生成する。family割当を翻訳より先に固定し、GTは公開済みdatasetを読み直す。
GTの未判定・不適合を分離し、入力へ正解ID/rule/未来情報を入れない。

## 実装箇所

- `pipelines/synthetic.py`: 仮置き属性policy、単位正規化、family分割、生成、入力検査。
- `pipelines/judgments.py`: GT policy v1、全直積の順序付きストリーム、集計。
- `runstore.py`: JSONL iterable書出しとファイルchecksumのストリーム化。
- `records/io.py`: manifest版検査付き・順序一意性付きJudgmentストリーム読込。
- `pipelines/skeleton.py`, `stages.py`, `cli.py`: 実処理接続、明示dataset入力。
- `tests/test_synthetic.py`, `test_skeleton.py`: 独立fixture、異常系、CLI。
- 05/04、AGENTS/CLAUDE、task台帳を現在地に同期。

旧taskの8ファイル上限は、完全GTの大規模処理に必要なstore/reader/CLIと
連動docsを含まないため、この明示スコープに更新する。外部サービス、依存変更、
検索・学習・評価指標・simulationは対象外。

## 方式

架空shaft/bearing/boltをほぼ均等に生成。diameter/lengthはmm、元値とunitも保存。
寸法許容差0.01mm、material/standard/usageは完全一致。
constraintsはrequired/optional辞書。未知条件は拒否、矛盾・必要属性欠損はunrateable。
生成器は構造化条件とJA/EN文を同時生成し、任意自然文の抽出は行わない。
1 familyごとに1 query type、各言語1 Query。寸法組が一意な商品から重複なしで
familyの意図を選ぶ。QueryFamily数がSKU数を超える設定は拒否する。
manifestにseed/設定/件数/集合digest、入力checksumと版、source checksumを保存。
GTは全直積をquery_id/product_id順で生成し、query単位で検査、固定メモリで保存。

## 検証

小規模で全rank 0〜4、欠損、矛盾、単位、必須違反優先、family交差、seed決定性、
途中失敗の非公開、改ざん・版拒否、GT順序一意性、CLI exitとdataset引継ぎを検査。
`make fmt lint test build`、既定設定の `stage catalog` →
`stage judgments --dataset <path>` → `verify-artifact <path>`、
GTストリーム読込で2,000万行・全query/product網羅とcountsを確認する。
