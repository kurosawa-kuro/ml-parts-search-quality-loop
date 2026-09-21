# 検索品質PoCの仕様・設計整理

## Goal

設計メモとOSS参考メモを、要件・基礎設計・素材・未決事項に分離する。

## Context

ユーザー指定の3文書を `.claude/skills/distill-spec/SKILL.md` に従って整理する。01/02 は未記入テンプレート、プロダクト実装は未着手。

## Scope

指定3文書、素材のarchive、索引、未決事項と実装追跡用backlog。アプリ実装・技術候補の採用・外部リポの検証は含まない。

## Plan

1. 元メモ・添付全文をarchiveへ保存する。
2. WHATとHOWを分離し、Golden Pathと受入条件を対応させる。
3. 未決事項をbacklogに移し、元メモを入口にする。
4. 素材保存、リンク、差分と既存品質ゲートを検証する。

## Acceptance Criteria

- 元素材が欠落せず保存される。
- 01/02にテンプレートのTODOが残らず、未決事項と未実装状態が明示される。
- OSS参照は採用済み依存や検証済み機能と混同しない。
- 要件と設計のGolden Pathが対応し、定義の正本が一意になる。

## Verification

作業完了時に追記する。

- 元メモ（Git HEAD）と添付のバイト列がarchive本文末尾と一致することをPythonで確認。
- 01/02に未記入TODOがないこと、Golden Pathの6段階対応を確認。
- `make test fmt`: 終了コード0。ただし両targetともTODO出力のみであり、実テスト・整形は未実行。
- `git diff --check`: 通過。
- Markdownの相対リンク存在確認を実施（下記完了記録を含む）。
- 外部OSSの現況・機能、PoCの実行と品質効果は未検証。未決事項・実装作業はbacklogで追跡する。
