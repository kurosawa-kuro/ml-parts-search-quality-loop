# 参照実装に基づく01〜08の設計改善

## Goal / Scope

ローカル参照リポの固定commitを読み、01〜08の仕様・設計・運用契約を整合させる。参照コードは変更・実行しない。アプリ実装、ライブラリ導入、商材の確定は対象外。

## Plan

1. イベント・GT・特徴量・実験・指標のコードとテストを読む。
2. 観測事実と本PoCでの設計判断を分け、出典を固定する。
3. 01〜08と既存backlogを更新し、相互参照と契約を確認する。
4. 文書チェックと既存makeゲートを実行する。

## Acceptance Criteria

- 8文書のテンプレートを埋め、未実装と未決事項を明示する。
- 失敗を0件や指標0に変換しない。未判定を不適合と混同しない。
- split、Feature / model互換、metric policy、GT版、実行成果物を追跡できる。
- 採用・rollback・smokeがGolden Pathと対応する。

## Verification

完了時に追記。

- 12リポから19箇所のコード・schema・公式リポ内資料を静的確認し、固定commitリンクを `docs/reference-implementation-review.md` に保存。
- 01〜08、索引、未決事項・実装backlogを更新。参照repoとアプリコードは変更していない。
- 初回リンク検証で削除済み設計メモへの既存参照を検出。元メモのarchiveへのリンクへ修正（削除ファイルは復元しない）。
- `make test fmt`: 終了0だがTODO表示のみ。実テスト・整形は未実行。
- `git diff --check`: 通過。文書リンク・fence・19出典の固定commitとローカルファイルの一致を検証。
- 契約の手動確認: QuerySet全件評価、null/0、candidateと最終順位、GT/Feature/metric版、bootstrap/rollback、独立集合の更新を確認。
- 未検証: upstream実行、アプリE2E、性能・モデル品質、provider実導入。品質閾値・商材・engine等はbacklogに残す。
