# Parts Search Quality Loop

多言語の部品検索で、失敗検知・GT更新・再学習・独立評価をつなぐPoC。
現在は **Python foundation・T1データ契約・T2合成Catalog/Query/GTとfamily分割** を実装済み。厳密な設定検証、JSON/JSONL成果物、checksum、原子的なrun公開、CLI、実テスト、wheel/sdist buildが動く。検索・学習・品質評価・疑似オンライン・ReleaseBundleは未実装であり、foundationの成功をML工程の成功とは扱わない。

## 現在地と実装順序

要件のGolden PathとAC-001〜011を、次の8タスクで段階的に実装する。詳細な依存関係は[実装マスタータスク](docs/tasks/03_active/20260921-search-quality-poc-implementation.md)を参照する。

| # | 実装単位 | 状態 |
|---|---|---|
| Foundation | 設定、成果物store、bootstrap CLI、テスト、build | 実装済み |
| T1 | データ契約validatorと独立した手書きfixture | 実装済み（一部レコードfixtureは後続工程で追加） |
| T2 | 合成Catalog、Query、GT、family分割 | 実装済み |
| T3 | Qdrant Vector BaselineとSearchRun | 次の実装候補 |
| T4 | オフライン評価、Slice、FailureCase | backlog |
| T5 | 構造化FeatureとLightGBM LambdaRank | backlog |
| T6 | Experiment比較と品質Gate | backlog |
| T7 | 疑似オンラインFeedback Loop | backlog |
| T8 | 独立評価、Release、rollback、Golden Path E2E | backlog |

商材別GTは05のT2契約、Embedding・FeatureSchema・品質閾値・SimulationPolicyの仮置き値はconfigと判断記録を参照する。設定が揃ったことを正式評価の合格とは扱わない。

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

現在利用できるCLIは次のとおり。

- `config-check`: 公開設定と工程別blockerを検査する。秘密値は読まない。
- `bootstrap`: foundation runを作る。`ml_executed=false`を記録する。
- `verify-artifact`: 完了runのinventoryとchecksumを検査する。
- `stages`: 全9段階と実装状況を一覧する。
- `stage catalog`: Catalog/Query/splitを生成する。
- `stage judgments --dataset <artifact>`: 明示したdatasetの完全判定GTを生成する。
- `pipeline`: 依存順に実行する。未実装工程が残るためGolden Path全体は未完了。

既定GTは2,000万行。実行手順と大規模読込APIは[ワークフロー](docs/04_workflows.md)を参照。

## 構成

```text
src/parts_search/
  cli.py                 argparseの入口
  config/                厳密なYAML・schema・パス・工程別検証
  artifacts/             JSON/JSONL・checksum・原子的run公開
  pipelines/bootstrap.py 設定から成果物までの最小実行経路
tests/                   単体・CLI結合テスト
env/                     非機密設定・パス・Git管理外の秘密情報
docs/tasks/              T1〜T8、未決事項、完了証跡
```

`env/project.yaml`のrepoRootはclone・移動後に実パスへ更新する。`config.yaml`のパスはrepoRoot基準。秘密ファイルは通常CLIで読み込まず、将来の接続adapterから明示的に使う。API keyを設定snapshotへ混ぜない。

依存は`pyproject.toml`と`uv.lock`で管理する。ML依存は各工程の実装時に追加する。既存runを消す汎用cleanコマンドは用意しない。

## スターターとの関係

`private-ops/tooling/starter-kit/assets/starters/python/ml` のsrc layout、argparse CLI、pipeline、manifestの分離を参考にした。住宅価格回帰やGCS/BigQuery連携は持ち込まず、設定検証と不変run保存を部品検索用に実装した。

設計と残件は [文書索引](docs/00_index.md)、[要件](docs/01_requirements.md)、[アーキテクチャ](docs/02_architecture.md)、[ワークフロー](docs/04_workflows.md)、[タスク一覧](docs/tasks/README.md) を参照。
