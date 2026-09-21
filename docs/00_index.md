# プロジェクトドキュメント索引

このディレクトリは、プロジェクトの要件・設計・ワークフロー・テスト・リリース運用の正本。`AGENTS.md` は Codex / 他エージェント向けの repo ガイド、`CLAUDE.md` は Claude Code の司令塔、`docs/tasks/` は毎日の作業計画・実装タスク・調査ログの実行ハブ、`.claude/skills/` は Claude Code で繰り返し使う作業手順。

## 権威順位

```text
コード / Makefile / config / manifests
> docs
> docs/tasks
> README / CLAUDE / AGENTS
> archive
```

## 毎日使う入口

| 入口 | 用途 |
|---|---|
| [tasks/README.md](./tasks/README.md) | 今日やること、次にやること、完了したことを管理する |
| [tasks/03_active/refactoring-candidates.md](./tasks/03_active/refactoring-candidates.md) | 常時見る cleanup / refactoring 候補 |
| [04_workflows.md](./04_workflows.md) | 作業開始、検証、リリース前確認のコマンド |
| [07_test_strategy.md](./07_test_strategy.md) | タスク完了前に通す品質ゲート |

`docs/tasks/` は仕様の正本ではないが、日々の実行順・証跡・未決事項の正本として扱う。確定した仕様は `docs/specs/` や 01〜08 文書へ、判断理由は `docs/adr/` へ昇格する。

## ドキュメント一覧

| ドキュメント | 役割 |
|---|---|
| [01_requirements.md](./01_requirements.md) | 目的・範囲・ユーザー・ユースケース・Critical User Journey / Golden Path |
| [02_architecture.md](./02_architecture.md) | 構成要素・境界・実行モデル |
| [03_domain_model.md](./03_domain_model.md) | 用語・状態・ビジネス概念 |
| [04_workflows.md](./04_workflows.md) | ローカルコマンドと運用フロー |
| [05_data_model.md](./05_data_model.md) | データ・スキーマ・設定・永続化 |
| [06_error_policy.md](./06_error_policy.md) | エラー処理・リトライ・ログ |
| [07_test_strategy.md](./07_test_strategy.md) | テスト方針と品質ゲート |
| [08_release_runbook.md](./08_release_runbook.md) | リリース・マイグレーション・復旧 |
| [tasks/README.md](./tasks/README.md) | 日次運用の実行ハブ、作業計画、実装タスク |

## PoC設計の素材

- [設計メモ](./検索品質-継続改善ループ-PoC設計メモ.md): 整理済み仕様・設計と保存素材の入口。
- `archive/`: 元メモ・添付全文を保存する参考素材。権威順位は最下位。

## ハーネス（AI 制御）

AI エージェント制御の全体像は `.claude/README.md`。アーキ本体とその repo 固有 instantiation は `docs/specs/` に置く。

| ドキュメント | 役割 |
|---|---|
| [specs/kurosawa-thin-harness-architecture.md](./specs/kurosawa-thin-harness-architecture.md) | Thin Harness アーキ本体（tool-agnostic マスター） |
| [specs/runtime-protocol.md](./specs/runtime-protocol.md) | 実行手順と停止条件（repo 固有） |
| [specs/capability-boundary.md](./specs/capability-boundary.md) | 保護 capability と permissions 写像（脅威モデル） |
| [specs/change-boundary.md](./specs/change-boundary.md) | 保護パスと変更境界 |
| [specs/evidence-policy.md](./specs/evidence-policy.md) | Evidence Level と done の下限 |
| [specs/judgment-memory.md](./specs/judgment-memory.md) | 判断記憶のパイプライン |
| [templates/](./templates/) | 各 Layer のテンプレ（contract / weight-class / reality-check 等） |
| [decisions/decision-log.md](./decisions/decision-log.md) | 判断日誌（trade journal、append-only） |
| [memory/](./memory/) | 蒸留済み判断記憶 |
