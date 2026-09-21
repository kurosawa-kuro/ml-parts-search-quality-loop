# ローカルPoC設定の整備

## Goal / Scope

env/config.yaml・project.yaml・secret.yamlを現在の設計と実パスに合わせる。アプリ実装、依存導入、Qdrant起動、外部秘密登録は対象外。

## Plan / Acceptance Criteria

- 汎用サーバー設定をbatch PoCの初期設定へ置き換える。
- projectNameはparts-search-quality-loopを保持し、repoRootを実ディレクトリへ修正する。
- FA・JA/EN・10,000 SKU・1,000 query family・Qdrantローカルを初期値とする。
- 未確定のEmbedding revision・属性規約・Feature schema・評価依存・品質閾値・simulationをnull/無効で明示する。
- secretの既存値を表示・変更しない。今回は既存YAMLはコメントのみ（null）と確認し、コメントを保持して空キーを追加する。
- YAML・分割比率・gain・パス・secretのGit除外と権限を検証する。

## Verification

完了時に追記。

- Ruby標準YAML parserで3ファイルの構文・マッピングを確認。
- project名と実パス、split合計1、gain一致、cutoff、retry数、相対パスを検証。
- secret参照キーの存在・権限0600・Git ignore・未追跡を値非表示で確認。
- `make test fmt`は終了0だがTODO出力のみ。アプリの設定読込・接続・実テストは未実装。
- `git diff --check`通過。01/02/05と未決事項を初期設定に合わせて更新。
