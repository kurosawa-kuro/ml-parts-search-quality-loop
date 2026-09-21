# 08 リリース Runbook

> 対象はローカル疑似オンラインで使うReleaseBundleの切替。商用環境への配備は対象外。処理・CLIは未実装のため、以下は実装後の運用契約。現状ではリリースを実行できない。

## リリース前

1. [07](./07_test_strategy.md)の実テストと品質ゲートが完了し、decision=acceptedであることを確認する。foundationテストの成功だけをモデル品質の合格証跡にしない。
2. baseline/candidateの入力・GT・MetricPolicy・split・結果・採否をmanifestで確認する。
3. 新ReleaseBundleへ検索構成、catalog/index参照、embedding revision、model、FeatureSchema、policy参照とchecksumを固定する。
4. 直前activeのmanifest・必要ファイル・indexが残っていて、現runtimeで読み込み可能なことを確認する。
5. 未決の商材契約・必須設定、failed query、未判定GT、未完了blockerがあれば切替を止める。

初回Baselineの登録は比較改善のacceptedとは別に、schema・完全評価・smokeの通過を条件とするbootstrap操作として記録する。このBaseline bundleを以後の復帰先とする。Baselineがない初回stagingの失敗時はsimulationを停止し、activeを作らない。

## stagingと切替

1. 新bundleをstagedとして検証する。成果物は原子的公開済みのものだけを参照する。
2. activeを変えず、固定smoke QuerySetで検索・event結合・評価まで実行する。
3. smokeが通ったら、ローカル単一writerの下で旧active参照を履歴へ保存する。
4. 一時active.jsonへ新release_id・checksumを書き、同一filesystem上のrenameで切り替える。
5. 切替後smokeを実施し、runが新release_idを使っていることと最終成果物を確認する。

同時実行のsimulationは開始時にbundleを固定し、途中でactiveが変わっても混在させない。更新・rollbackの履歴を残し、旧bundleは削除しない。

## Golden Pathのsmoke

| # | 確認操作（実コマンドは実装時に追加） | 期待する観測 |
|---|---|---|
| 1 | 入力manifestと固定smokeデータを検査 | catalog・GT・split・policyが復元できる |
| 2 | 正常query・正常0件queryを検索し評価 | 新bundleの結果、全outcome、有限metricと規定のnull |
| 3 | developmentのimpression・click・失敗例を生成 | event結合が成立しFailureCaseを取得 |
| 4 | 同梱の小規模学習fixtureでFeature・model互換を確認 | labelを推論へ漏らさず、再学習成果物を別runへ保存 |
| 5 | baselineとの比較・採否成果物を再読込 | signature・指標・decisionが整合する |
| 6 | 次experimentを作るdry-run | 親実験・FailureCase・新releaseの関係を保存できる |

リリース前のE2Eは6段階を実行する。切替後は1〜3と5〜6を実行し、4はモデルschema・checksum確認を行う。smokeが学習用に使う小規模fixtureをholdoutへ混ぜない。smoke結果と正式品質評価は別runとして扱う。

## rollback

トリガーは切替後smoke失敗、bundle混在、checksum・互換性不整合、または採用後に発見した重大な回帰。

1. 新規simulationの受付を止め、失敗runと現在のactive参照を保存する。
2. 旧bundleを検査する。モデルだけでなくindex・Feature・検索設定・schemaの組を復元する。
3. 旧参照を一時ファイル経由でactive.jsonへ原子的に戻す。
4. 旧bundleで切替後smokeを実行し、release_idと成果物を確認してから再開する。
5. 新bundleをquarantinedにし、原因・失敗run・復旧run・時刻を記録する。

旧bundleが現runtimeで読めない場合は強制変換せず停止し、旧runtimeも含めて復元する。復旧不能のままsuccessを記録しない。GT・model・event・評価履歴は削除・巻き戻しをせず、active参照だけを戻す。

## リリース後

実行証跡と復旧確認をtaskへ残し、恒久修正は対応する01〜08へ反映する。schema移行は新成果物へ行い、旧版からの復帰テストを追加する。

関連: [04 手順](./04_workflows.md) / [05 保存契約](./05_data_model.md) / [06 エラー](./06_error_policy.md) / [実装計画](./tasks/03_active/20260921-search-quality-poc-implementation.md)。
