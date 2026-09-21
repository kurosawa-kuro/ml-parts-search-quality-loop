# 検索品質PoCのGolden Pathを段階的に実装する

## Goal

[要件](../../01_requirements.md) のGolden Pathを1周し、受入条件AC-001〜007の証跡を残す。

## Context

プロダクト実装は未着手。Makefileのtest / fmtはTODO出力のみ。先に [未決事項](./20260921-search-quality-poc-decisions.md) の該当契約を確定する。

## Scope / Plan

以下を実装単位ごとのtaskへ分割して進める。

- [ ] 商品マスタ・クエリ・GT生成、独立したデータ分割。
- [ ] Vector-only検索とSearchRun記録。
- [ ] 全体指標・Slice・FailureCaseの生成。
- [ ] 構造化FeatureとLightGBM LambdaRankの学習・推論。
- [ ] Experimentと入力・設定・モデル・成果物の関連づけ。
- [ ] 疑似オンラインイベントとKPI、失敗抽出からGT更新への接続。
- [ ] Holdout / Production-like比較、採否と次の実験の記録。
- [ ] 実行コマンド、テスト、smokeと関連する03〜08文書の具体化。

## Acceptance Criteria

01の受入条件と02の責務・境界を満たし、実行条件・結果を第三者が確認できる。BM25 / Hybrid等の拡張は採否決定後に別taskで追加する。
