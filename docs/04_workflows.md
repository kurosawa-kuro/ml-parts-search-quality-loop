# 04 ワークフロー

> 設定検証・foundation bootstrap・成果物検証・**レコード契約validator（T1）**は実装済み。T2も実装済み。9段階のうち`contracts`・`catalog`・`judgments`が実処理。検索・学習・評価・gate・releaseは未実装。

## 実行できるコマンド

リポジトリ直下、Python 3.11以上とuvを使用する。

```bash
make setup
make config-check
make run
make stages
make pipeline
make fmt lint test build
```

`setup`はlockから.venvへ依存を導入する。`run` / `dev`はfoundation bootstrapを実行し、`artifacts/runs/<run_id>/`へconfig.json・readiness.json・manifest.jsonを保存する。ML処理は実行しない。

## Golden Path の段階実行

`stages`は9段階（T1〜T8）の依存順・依存する設定段階・書き出す成果物を一覧する。`pipeline`はそれを順に実行する。catalog成果物をjudgmentsへ渡し、既定設定では完全判定GTを2,000万行生成する。実行時間・ディスク容量はこの規模に応じて必要になる。

```bash
uv run --locked parts-search stages
uv run --locked parts-search pipeline [--stop-on-block]
uv run --locked parts-search stage retrieval
```

各段階は依存する設定段階のblockerを検査し、未確定なら**成果物を書かずに`blocked`**として報告する。未確定の設定で`status: succeeded`のmanifestを作らないため。

段階の状態は3つ。

| status | 意味 |
|---|---|
| `completed` | 実処理が走った（現在は`contracts`・`catalog`・`judgments`） |
| `skeleton` | 設定は揃っているが実装が無い。`implemented: false`のplaceholderを公開する |
| `blocked` | 依存する設定または入力datasetが不足。**成果物を作らない** |

`golden_path_complete`が`true`になるのは**全段階が`completed`かつblockerゼロ**のときだけ。骨組みの完走を達成と読み替えない。

### 終了コード

| code | 意味 |
|---:|---|
| 0 | 完了（一覧、bootstrap、検証、実装済み単一段階） |
| 1 | 入力・実行エラー、または`config-check`で未設定あり |
| 2 | **設定・入力不足で段階が止まった**（blocked） |
| 3 | **未実装段階が残る**（一部完了していても全体は未完了） |

`pipeline`が0を返すのは全段階の実装が入ったときだけ。**2と3を成功と読み替えない。** ログはstderr、JSONはstdoutへ出るので`parts-search pipeline | jq`が使える。

```bash
uv run --locked parts-search verify-artifact artifacts/runs/<run_id>
uv run --locked parts-search config-check --stage retrieval
```

後者は設定が揃っていれば終了0、未設定があれば終了1となる。工程検査は設定の充足のみを確認する。`foundation`（既定）以外はcatalog / retrieval / training / evaluation / gate / simulationを指定できる。通常CLIはsecretを読まない。`--project` / `--config`はサブコマンドより前に指定する。`make help`で一覧を確認できる。

## 作業開始と終了

1. [タスク一覧](./tasks/README.md)から対象を選び、Scope・Plan・受入条件を記録する。
2. [未決事項](./tasks/02_backlog/20260921-search-quality-poc-decisions.md)のうち、その工程に必要な設定を決める。
3. 変更した契約の正本（01〜08）を更新し、対応するvalidator・テストを実装する。
4. 実行コマンド、結果、未検証範囲をtaskへ記録する。設計文書の検証とアプリ動作確認を区別する。

## 初回Baseline（実装予定手順）

| 順 | 操作 | 入力 / 生成物 | 完了条件 |
|---|---|---|---|
| 1 | prepare | 生成設定 → catalog・queries・split・GT snapshot | ID・family分離・判定完了を検証 |
| 2 | freeze | snapshot + MetricPolicy + baseline設定 → Experiment | 入力checksumと実行環境を固定 |
| 3 | index / retrieve | catalog + QuerySet → index・CandidateSet・outcomes | QuerySet全件にoutcomeがある |
| 4 | rank | 候補 → SearchRun（Baselineは取得順位） | 一意で連続した順位、0件と失敗を区別 |
| 5 | evaluate | SearchRun + CandidateSet + GT → metrics・per-query・Slices | 05の分母・coverage・policyを満たす |
| 6 | simulate / analyze | development集合 → events・KPI・FailureCases | 失敗例に実際の結果・根拠が結合される |

## 改善と独立評価（実装予定手順）

1. developmentのFailureCaseから変更仮説を1つ作る。GT更新、Retrieval変更、Feature変更のどれかを記録する。
2. 新GTを作る場合は旧版を保持する。未判定・暗黙feedbackを評価用GTに黙って混ぜない。
3. trainだけで学習し、tuningで設定を選ぶ。Feature順序とmodel manifestを検証する。
4. 新Experimentで候補を実行する。rerankだけの比較ならbaselineと同じCandidateSetを使う。
5. 両構成を同じGT / MetricPolicyで再評価する。検索結果を再利用できる条件は05に従う。
6. 凍結したholdoutとproduction集合で評価する。採否を [07](./07_test_strategy.md) のゲートに従って記録する。
7. acceptedのみ [08](./08_release_runbook.md) のstaging・smoke・切替へ進む。inconclusiveは原因を残して保留する。
8. 次の失敗から新Experimentへ接続する。独立評価集合を改善へ使う際は開発集合へ移し、次の独立集合を新設する。

## 再試行・再現

失敗は [06](./06_error_policy.md) で分類する。永続成果物は上書きせず、新run_idとretry_ofを使う。再現はmanifestから同じ入力・設定・依存を復元する。seed一致だけでなく出力ID・順位・metricの許容差を [07](./07_test_strategy.md) で検証する。

関連: [05 データ契約](./05_data_model.md) / [実装backlog](./tasks/03_active/20260921-search-quality-poc-implementation.md)。実コマンドの導入時はこの表とテスト・smokeを同じtaskで更新する。

## T2 の単独実行

```bash
uv run --locked parts-search stage catalog
# 上記JSONのartifactを指定する。最新ディレクトリの自動推測はしない。
uv run --locked parts-search stage judgments --dataset artifacts/datasets/<run_id>
uv run --locked parts-search verify-artifact artifacts/judgments/<run_id>
```

両stageは正常完了時exit 0。dataset未指定のjudgmentsは成果物を作らずblocked / exit 2。
入力の改変・未対応版・未知policyはexit 1。GTの判定完了状況はsummary.jsonで確認する。
再実行は新しい公開IDへ保存し、以前の成果物は保持する。Pythonで大きなGTを読む場合は
`parts_search.records.io.iter_judgments(Path(...))`を最後まで消費する。
