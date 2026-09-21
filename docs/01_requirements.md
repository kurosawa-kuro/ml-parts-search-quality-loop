# 01 要件

## 目的

TODO: このプロジェクトはどんな課題を解決するか?

## 範囲

対象:

- TODO

非対象:

- TODO

## ユーザー

- TODO

## ユースケース

| ID | ユースケース | 成功条件 |
|---|---|---|
| UC-001 | TODO | TODO |

## Critical User Journey / Golden Path

このプロダクトが「使われて価値が出る」中核の一本道。ユーザーが最初から最後まで通す happy path を、順序付きの1シーケンスで定義する。多数のユースケースの中で **これが壊れたらプロダクトが成立しない** 1本を明示する。

- 一次ユーザー: TODO（誰の、どの目的の journey か）
- 完了状態（この journey のゴール）: TODO

| # | ステップ | 成功条件（観測可能な状態） |
|---|---|---|
| 1 | TODO | TODO |
| 2 | TODO | TODO |
| 3 | TODO | TODO |
| 4 | TODO | TODO |

> 例（ショッピングアプリ・比喩）: 商品を見る → カートに入れる → 購入する → 購入履歴を確認する。
> この4ステップが端から端まで通ることが Golden Path。個別機能が動いても、この一本が切れていたら未達とみなす。

- この Golden Path は、基礎設計（[02_architecture.md](./02_architecture.md)）でどの構成要素・境界を通るかに写像する。
- リリース運用（[08_release_runbook.md](./08_release_runbook.md)）では、この一本をデプロイ後 smoke / ロールバック判定の基準にする。

## 関連タスク

- 要件追加・変更は、まず `docs/tasks/03_active/` または `docs/tasks/02_backlog/` に task として記録する。
- 確定した要件だけをこの文書へ反映する。
- 要件変更に伴う未実装作業は `docs/tasks/README.md` から追跡できる状態にする。
