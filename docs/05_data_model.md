# 05 データモデル

## 設定

| 種別 | 方針 |
|---|---|
| 一般設定 | `env/config.yaml` または環境変数 |
| ローカル秘密情報 | ignore するローカルファイル |
| 共有 / 本番の秘密情報 | Doppler などの secret manager |

## 永続化

TODO

## 関連タスク

- schema、migration、設定、永続化方式の変更は task に目的・移行手順・検証方法を残す。
- 破壊的変更や後方互換が絡む変更は、実装前に `docs/tasks/03_active/` で作業計画を固定する。
- 確定した migration 手順は `docs/runbooks/` または `08_release_runbook.md` へ昇格する。
