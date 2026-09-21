# 検索品質PoCのGolden Pathを段階的に実装する

## Goal

[要件](../../01_requirements.md) のGolden Pathを1周し、受入条件AC-001〜011の証跡を残す。

## Context

設定検証・foundation CLI・ローカルrun保存とMakefileの実テスト/整形/buildを実装済み。検索・GT・学習・評価は未実装。先に [未決事項](./20260921-search-quality-poc-decisions.md) の該当契約を確定する。

## Scope / Plan

以下を実装単位ごとのtaskへ分割して進める。

- [x] 設定schema、foundation runのJSON/JSONL・manifest保存と改変検証。
- [ ] 検索・GT・Feature・modelのレコードvalidatorと07の指標手書きfixture。
- [ ] 商品マスタ・クエリ・GT生成、独立したデータ分割。
- [ ] Vector-only検索とSearchRun記録。
- [ ] 全体指標・Slice・FailureCaseの生成。
- [ ] 構造化FeatureとLightGBM LambdaRankの学習・推論。
- [ ] Experimentと入力・設定・モデル・成果物の関連づけ。
- [ ] 疑似オンラインイベントとKPI、失敗抽出からGT更新への接続。
- [ ] Holdout / Production-like比較、採否と次の実験の記録。
- [ ] 不完全評価の停止、再試行・event隔離、bundle切替・rollback。
- [x] foundation CLIとMakefile、設定・成果物の実テストを接続。
- [ ] ML工程CLI、07の品質テスト、08のsmokeコマンドを実装。
- [ ] 01〜08の設計契約v1に対する実装確認と差分反映。

## Acceptance Criteria

01の受入条件と02の責務・境界を満たし、実行条件・結果を第三者が確認できる。BM25 / Hybrid等の拡張は採否決定後に別taskで追加する。
