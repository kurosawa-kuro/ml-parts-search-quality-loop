# 08 リリース Runbook

## リリース前

```bash
make test
git status --short
```

- `docs/tasks/03_active/` と `docs/tasks/04_verifying/` にリリース前の未完了 blocker が残っていないことを確認する。
- リリース対象 task の `Verification` に検証結果が残っていることを確認する。
- 未解決事項がある場合は、release blocker か follow-up かを task に明記する。

## デプロイ

TODO

## デプロイ後 smoke（Golden Path）

要件の Critical User Journey / Golden Path（[01_requirements.md](./01_requirements.md)）を、本番相当の環境で端から端まで実際に1回通す。個別ヘルスチェックが緑でも、この一本が切れていたらリリース失敗として扱う（＝ロールバック判定）。

| # | Golden Path ステップ | 確認方法（実行するコマンド / 操作） | 期待する観測結果 |
|---|---|---|---|
| 1 | TODO | TODO | TODO |
| 2 | TODO | TODO | TODO |
| 3 | TODO | TODO | TODO |
| 4 | TODO | TODO | TODO |

> 例（ショッピングアプリ・比喩）: 商品を見る → カートに入れる → 購入する → 購入履歴を確認する、を実データで1周させ、履歴に購入が反映されるところまで確認する。

- 中間段（ビルド緑・ヘルスチェック 200）だけで完了にしない。最終成果物（Golden Path の完了状態）を実際に観測して初めてリリース完了とする。

## ロールバック

- **トリガー**: デプロイ後 smoke で Golden Path のいずれかのステップが期待結果に到達しない場合。
- TODO: ロールバック手順（前バージョンへの戻し方、データ整合性の扱い）。

## リリース後タスク

- リリース後の確認事項は `docs/tasks/03_active/` または `docs/tasks/02_backlog/` に残す。
- 恒久的な運用手順になったものは `docs/runbooks/` へ昇格する。
