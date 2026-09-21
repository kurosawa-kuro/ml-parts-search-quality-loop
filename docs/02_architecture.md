# 02 アーキテクチャ

## 概要

```text
入力
  -> アプリケーション
  -> 出力
```

## 構成要素

| 構成要素 | 役割 | 担当パス |
|---|---|---|
| TODO | TODO | TODO |
| エージェントガイド | Codex / 他エージェント向けの repo ガイド | `AGENTS.md` |
| Claude ガイド | Claude Code の司令ルール | `CLAUDE.md` |
| タスク文書 | 一回性の作業計画・実装タスク | `docs/tasks/` |
| Claude skills | Claude Code で繰り返し使う作業手順 | `.claude/skills/` |

## Golden Path とアーキテクチャ

要件で定義した Critical User Journey / Golden Path（[01_requirements.md](./01_requirements.md)）が、どの構成要素・境界を通るかを写像する。設計判断（責務配置・境界・依存）は、まずこの一本道を壊さない・遅くしないことを優先条件にする。

| Golden Path ステップ | 通る構成要素 | 通る境界 / データ | 単一障害点（切れると journey が止まる） |
|---|---|---|---|
| 1. TODO | TODO | TODO | TODO |
| 2. TODO | TODO | TODO | TODO |
| 3. TODO | TODO | TODO | TODO |
| 4. TODO | TODO | TODO | TODO |

> 例（ショッピングアプリ・比喩）: 「商品を見る」→ 一覧/検索 + 商品DB、「カートに入れる」→ カート状態、「購入する」→ 決済 + 在庫、「購入履歴を確認する」→ 注文DB。決済が単一障害点なら、そこを最優先で堅牢化・監視する。

- 新しい構成要素・adapter・依存を足すときは、この表の Golden Path 上に不要な単一障害点を増やしていないかを確認する。
- Golden Path 上の構成要素の変更は、リリース Runbook の smoke 対象（[08_release_runbook.md](./08_release_runbook.md)）と整合させる。

## 境界

- ソースコードは、別の境界を定義しない限り `src/` 配下に置く。
- 非機密の設定は `env/config.yaml` に置く。
- ローカル秘密情報は ignore したまま。共有・本番の秘密情報は Doppler などの secret manager に置く。
- Codex が `.claude/rules/` や `.claude/skills/` を読む前提にしない。Codex / 他エージェント向けに永続させたい指針は `AGENTS.md` に置く。

## 関連タスク

- 構造変更、責務移動、adapter 追加、共通化は、実装前に `docs/tasks/03_active/` へ task を作る。
- 中規模以上の変更では、task に Skeleton / Plan / Acceptance Criteria を書いてから実装する。
- 確定した設計判断は task から `docs/adr/` またはこの文書へ昇格する。
