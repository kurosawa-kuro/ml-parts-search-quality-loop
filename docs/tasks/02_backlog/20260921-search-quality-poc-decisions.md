# 検索品質PoCの残る選定・設定

## Goal

[参照実装レビュー](../../reference-implementation-review.md)後の未決事項を確定し、01〜08へ反映する。ID・保存形式・GT優先順位・分割・指標・event・採否状態は設計契約v1として具体化済み。以前の一覧をそのまま未決扱いしない。

## 残る判断

| 項目 | 決めること | 決定時期 |
|---|---|---|
| 商材 | 初期FA部品に設定済み。カテゴリ構成の具体化 | 生成器実装前 |
| 初期規模・言語 | 10,000 SKU・JA/EN・1,000 family・split比率は設定済み。言語別query分布の具体化 | 生成器実装前 |
| 商材別GT | 必須属性、正規単位、数値許容差、代替条件、自然文の制約抽出 | GT実装前 |
| Retrieval | 初期Qdrantローカルに設定済み。Embedding model/revision、filter / boostの追加方式 | 検索実装前 |
| Hybrid | BM25 / Hybrid / RRFの採否とprefetch・fusion設定 | 拡張実装前 |
| 品質ゲート | 最小NDCG改善量、guardrail許容回帰、最低Slice件数、反復seed数 | candidate比較前 |
| SimulationPolicy | 観測窓、位置バイアス、click / conversion / reformulation確率、分布shift条件 | simulation実装前 |
| 実行環境 | 依存version・lock、ir_measures provider、model数値許容差、CLI名・実コマンド | 各工程実装時 |
| OSSの導入 | ライセンス・依存互換・コード流用の採否。静的な参照と導入は別 | 導入前 |

## Acceptance Criteria

- 対応する契約の正本へ決定を反映する。
- 未設定の必須条件で実行・品質合格を通さない。
- 商材・技術候補の決定と、設計契約v1の実装確認を区別する。
