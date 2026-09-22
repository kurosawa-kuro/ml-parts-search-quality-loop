# AGENTS.md

AI コーディングエージェント（Claude Code / Codex / GitHub Copilot 等）共通の作業ガイド。
Codex は作業前にこのファイルを読むため、ここには repo 共通方針のみ記す。
ツール固有の指示は各ツールのファイル（例: Claude Code は `CLAUDE.md`）に置く。

## プロジェクト概要

- 目的: 多言語部品検索の継続改善ループを再現するPoC
- 主要技術: Python 3.11+ / uv / PyYAML / jsonschema。Qdrant / E5 / LightGBM / ir_measures。
- 現在地: T1〜T5完了。contracts/catalog/judgments/retrieval/evaluation/training/gateの7段階に実処理あり。T6はoffline比較まで実装、再試行系譜と品質終了コードが残る。T7 simulation・T8 releaseは未実装。
- 実装順: `docs/tasks/03_active/20260921-search-quality-poc-implementation.md`。次はT6の残件、T7、T8。
- 実行上の注意: Intel MacでPyTorchとLightGBMを同一プロセスへimportするとOpenMPが停止する。E5は`embedding_worker`専用プロセスを維持する。既存2,000万行GTはpipelineの`--dataset` / `--judgments`で再利用可能。

## セットアップ / 主要コマンド

```bash
make setup    # lockから.venvへ依存導入
make config-check # foundation設定検証
make run      # foundation run作成。MLは実行しない
make dev      # foundation bootstrap（検索・学習は未実行）
make test     # テスト
make fmt      # フォーマット
make lint     # lint・format check
make build    # wheel / sdist
```

## コーディング規約

- 作業開始時に`pwd`と`git rev-parse --show-toplevel`を確認する。このリポジトリの正しいルートは`/Users/kurosawa/Dev/ml-parts-search-quality-loop`。以前の会話で扱った別リポジトリを推測で選ばない。
- ユーザーがフルパスを指定した場合はそのパスを最優先し、編集前後に`git status --short`で変更対象を確認する。
- 既存のコード・命名・パターンに合わせる。新規導入より既存の再利用を優先する。
- 変更後はテストとフォーマッタを実行してから完了とする。
- 非機密の設定値は `env/config.yaml`、ローカル秘密情報は `env/secret.yaml`、チーム共有・本番クレデンシャルは Doppler (`doppler.yaml`)。秘密情報をコミットしない。

## ドキュメント

設計・仕様・運用は `docs/` 配下を参照。更新規約と権威順位は `docs/00_index.md` に従う。
仕様レベルの変更は連動するドキュメントを同一 PR でまとめて直す。

## Codex / Claude Code

- `AGENTS.md` は Codex / 他エージェント共通ガイド。
- `CLAUDE.md` は Claude Code の司令塔。
- `.claude/rules/` と `.claude/skills/` は Claude Code 用。Codex が読む前提にしない。
- Codex 向けに永続させたい recurring な指摘やミス防止は、この `AGENTS.md` または nested `AGENTS.md` に小さく追加する。

## Harness（AI 制御一式）

- このリポジトリの AI 制御の全体像は `.claude/README.md`（Kurosawa Thin Harness Architecture の実装）。
- アーキ本体（tool-agnostic マスター）は `docs/specs/kurosawa-thin-harness-architecture.md`、repo 固有の脅威モデルは `docs/specs/{capability-boundary,change-boundary,runtime-protocol,evidence-policy,judgment-memory}.md`。
- permissions の ask/deny と保護パスは脅威モデルで決める。**他プロジェクトの設定をそのまま移植しない**。

## Task / Skill

- 一回性の作業計画・調査メモ・実装タスクは `docs/tasks/` に置く。
- Claude Code で繰り返し使う作業手順は `.claude/skills/` に置く（classify-task → create-task → scan-decisions → plan-skeleton → execute-task → verify-completion → review-task のライフサイクル）。
- Codex repo skills を本格運用する場合は `.agents/skills/` を任意追加する。標準生成物には含めない。
- task note を仕様の正本にしない。確定した仕様は `docs/specs/`、判断理由は `docs/adr/`、運用手順は `docs/runbooks/` に昇格する。
- 現在のbacklogはT1〜T8に分割済み。依存順を守る。`docs/tasks/02_backlog/20260921-search-quality-poc-decisions.md` の2026-09-22の判断により設定値は仮置き済みで、商材policyの内容はT2で具体化済み（docs/05_data_model.md）。実測後に調整する前提を保持し、古い未決記述だけで作業を止めない。
