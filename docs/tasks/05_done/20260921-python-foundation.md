# Python MLスターターからPoCの土台を作る

## Goal / Scope

スターターのsrc package・argparse CLI・pipeline・run manifestという構成を適応する。住宅回帰、GCP、検索・学習本体、外部サービス起動は対象外。既存設定と秘密値を保持する。

## Skeleton

- `pyproject.toml` / `uv.lock` / Makefile: src layout、依存固定、実テスト・lint・build。
- `src/parts_search/config/`: 厳密なYAMLとschema検証、パス解決、工程別未設定一覧、秘密値の別読込。
- `artifacts/`: JSON/JSONL、sha256、run manifest、原子的公開と検証。
- `pipelines/bootstrap.py`: 設定snapshotと未設定レポートを1つのrunへ保存する実行経路。
- `cli.py`: config-check / bootstrap / verify-artifact。未実装MLを成功扱いしない。
- `tests/`: 設定不備・秘密非漏洩・原子的保存・改変検出・CLI実行。

## Failing Condition

新packageのimportとCLIが存在せずテストが失敗する。

## Acceptance Criteria

1. 現行configを読める。未知キー・重複YAML・比率・gain不整合・パス逸脱は拒否する。
2. secretは公開snapshotへ混ぜず、エラーにも値を出さない。
3. 未確定の工程設定を報告し、工程指定時は非0終了する。
4. bootstrapは外部通信なしでrunを公開しchecksum検証できる。同一IDを上書きせず中断時は公開しない。
5. 実テスト・fmt・lint・build、CLIの永続成果物を確認（Evidence Level 3）。

## Test Command

`uv run python -m unittest discover -s tests -v`

## Minimal Implementation Plan

テストを先に置きimport失敗を確認 → スターター構成に合わせて設定/成果物/CLIを実装 → Makefileとdocsを更新 → 実行検証。

## Verification Command

`make fmt lint test build` / `make run` / `uv run parts-search verify-artifact <run-dir>` / `git diff --check`

## Rollback Trigger

既存secretの変更、未実装のML成功表示、run上書き。実装を修正し、既存成果物・ユーザー変更は削除しない。

## Verification

- RED: `uv run python -m unittest discover -s tests -v` が未実装storeのimportで失敗。
- 初回テストの実パス比較はmacOSの `/var` → `/private/var` aliasで不一致。fixtureのrootをresolveし、同一実パスを比較するよう修正（期待する検証は維持）。
- GREEN: `make fmt lint test`、11テスト成功。Ruff整形・lint通過。
- `make setup config-check run`成功。run `20260921T142909Z-6d5896b8442b` に公開設定・readiness・manifestを永続化。
- `parts-search verify-artifact`で当該runのchecksum検証成功。`config-check --stage retrieval`は期待どおり未設定を報告し終了1。
- 3つのJSON schemaをDraft202012Validator.check_schemaで検証。
- `make build`成功。wheel/sdist生成、wheelにconfig schemaを含みenv・references・実行成果物を含まないことを確認。
- `git diff --check`、更新文書の内部リンク検査を実施。
- 秘密ファイルは未変更。テストではダミー秘密値がエラー・repr・bootstrap成果物へ出ないことを確認。
- 検証環境: uv管理CPython 3.12.13。Python 3.11以上の全versionでの検証は未実施。
- 未実装: 検索、GT生成、学習、品質指標、ReleaseBundle、完全な実験再現。設定のreadyは外部接続やML完了を意味しない。
