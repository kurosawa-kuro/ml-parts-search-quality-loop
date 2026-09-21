# 06 エラー方針

> 設計契約v1。エラーコード・終了コード・ログ出力は未実装。正常な品質不良と実行障害を別に扱う。

## 分類と対応

| コード | 例 | 対応・再試行 |
|---|---|---|
| INVALID_INPUT | 重複ID、無効label、group数不一致、非有限score、schema未対応 | 停止。入力修正後に新run。自動再試行なし |
| INCOMPATIBLE_ARTIFACT | Feature順序、モデル、embedding / index、checksum不一致 | 停止。互換bundleを再構築。黙った変換なし |
| DATA_LEAKAGE | family交差、評価labelをFeatureへ混入、未来の人気度参照 | 学習・採用停止。splitと入力経路を修正 |
| INCOMPLETE_EVALUATION | missing outcome、未判定GT、必須Slice不足 | 探索用レポートに理由・件数を残す。正式判断はinconclusive |
| DEPENDENCY_UNAVAILABLE | metric provider未導入、モデルファイルなし | 停止。指標を0で代替しない |
| RETRIEVAL_TRANSIENT | timeout、一時的な接続切断 | 同じ固定入力で最大3試行（初回含む）、待機1秒・2秒。尽きたらquery failed |
| EVENT_CONFLICT | 同一event_idに異なるpayload、提示外商品へのclick | 隔離し正式評価を止める。同一payloadの重複は安全に除外 |
| EVENT_UNMATCHED | 観測窓終了後もimpressionへ結合不能 | 隔離・件数記録。修正後に新集計run |
| ARTIFACT_IO | 書込失敗、checksum不一致 | 未完了出力を公開しない。原因解消後に新run |
| QUALITY_REGRESSION | 完全な評価で許容回帰を超えた | 実行は成功、decisionはrejected。モデルを自動再学習して隠さない |
| RELEASE_SMOKE_FAILED | 切替後のID・結果・event・最終成果物が不一致 | 旧bundleへrollback。08の復旧手順へ |

正常0件は`zero_results`でありエラーではない。GTに正解があるなら指標0として計上する。失敗queryや未実行queryはnull、coverageに欠落を表示する。分母0やGT不備を「検索が悪い」と誤分類しない。

## 冪等性と成果物

readのみの検索は固定indexに対して再試行する。eventはevent_id、成果物はrun_idで重複を検査する。学習・公開・切替を自動で丸ごと再実行しない。成功公開済みのrunは変更せず、新runから参照する。部分成功でも正式gateを通さない。

バッチ終了コードは0=処理完了、1=実行失敗を予定する。採否はdecisionに明示し、gateコマンド導入時はaccepted=0、rejected=2、inconclusive=3とする。CLI未実装の現状ではこの値を利用できない。

## ログと診断

構造化ログにtimestamp、level、experiment_id、run_id、query_id、stage、attempt、error_code、duration、artifact参照を持たせる。成功件数・0件・失敗・未実行・判定不能・隔離eventの件数をsummaryに残す。秘密情報は記録しない。GT・生eventをログに重複出力せず成果物IDから追跡する。

関連: [03 状態](./03_domain_model.md) / [05 契約](./05_data_model.md) / [07 回帰テスト](./07_test_strategy.md) / [08 復旧](./08_release_runbook.md)。障害の再現条件・期待する観測・検証をtaskに記録する。
