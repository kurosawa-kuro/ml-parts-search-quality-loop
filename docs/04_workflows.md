# 04 ワークフロー

## セットアップ

```bash
make help
make setup
```

## 作業開始

```bash
git status --short
```

1. [tasks/README.md](./tasks/README.md) を見る。
2. `docs/tasks/03_active/` から今日の task を選ぶ。
3. task に Scope / Plan / Acceptance Criteria があることを確認する。
4. 中規模以上なら Skeleton を固定してから実装する。

## ローカル実行

```bash
make run
```

または:

```bash
make dev
```

## テスト

```bash
make test
```

## 作業終了

```bash
git diff --check
git status --short
```

- 実行した検証を task の `Verification` に残す。
- 未解決事項は task の `Notes` または `backlog/` に移す。
- 確定した仕様・手順・判断は docs 本体、runbook、ADR へ昇格する。
