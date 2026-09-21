# Parts Search Quality Loop

多言語の部品検索で、失敗検知・GT更新・再学習・独立評価をつなぐPoC。
現在は **Pythonの土台（設定検証、ローカル成果物、CLI）** を実装済み。検索・GT生成・学習・品質評価はこれから実装する。

## セットアップと起動

Python 3.11以上とuvを使用する。リポジトリ直下で実行する。

```bash
make setup
make config-check
make run
```

`make run`は設定snapshotと未設定レポートを `artifacts/runs/<run_id>/` へ保存する。外部サービスへの通信・検索・学習は行わない。

```bash
uv run --locked parts-search verify-artifact artifacts/runs/<run_id>
uv run --locked parts-search config-check --stage retrieval
make fmt lint test build
```

未設定の工程は`config-check`が不足項目を返して終了1となる。これは設定の充足判定であり、モデルやengineの存在・接続を検証するものではない。任意の設定を使う場合、`--project` / `--config`はサブコマンドの前に指定する。

## 構成

```text
src/parts_search_quality_loop/
  cli.py                 argparseの入口
  config/                厳密なYAML・schema・パス・工程別検証
  artifacts/             JSON/JSONL・checksum・原子的run公開
  pipelines/bootstrap.py 設定から成果物までの最小実行経路
tests/                   単体・CLI結合テスト
env/                     非機密設定・パス・Git管理外の秘密情報
```

`env/project.yaml`のrepoRootはclone・移動後に実パスへ更新する。`config.yaml`のパスはrepoRoot基準。秘密ファイルは通常CLIで読み込まず、将来の接続adapterから明示的に使う。API keyを設定snapshotへ混ぜない。

依存は`pyproject.toml`と`uv.lock`で管理する。ML依存は各工程の実装時に追加する。既存runを消す汎用cleanコマンドは用意しない。

## スターターとの関係

`private-ops/tooling/starter-kit/assets/starters/python/ml` のsrc layout、argparse CLI、pipeline、manifestの分離を参考にした。住宅価格回帰やGCS/BigQuery連携は持ち込まず、設定検証と不変run保存を部品検索用に実装した。

設計と残件は [文書索引](docs/00_index.md)、[ワークフロー](docs/04_workflows.md)、[実装backlog](docs/tasks/02_backlog/20260921-search-quality-poc-implementation.md) を参照。
