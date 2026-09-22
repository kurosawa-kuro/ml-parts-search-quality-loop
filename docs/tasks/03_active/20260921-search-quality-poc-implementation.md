# 検索品質PoCのGolden Pathを段階的に実装する

## Goal

[要件](../../01_requirements.md) のGolden Pathを1周し、受入条件AC-001〜011の証跡を残す。

## Context

T1〜T5完了、T6はoffline比較まで実装。完了タスク単純比は5/8=62.5%（工数比ではない）。9段階の実処理実装は7/9=77.8%だが、正式昇格とGolden Path完走は未完了。

120 SKU・40 family・80 Queryの実E5/Qdrant検索、完全GT評価、3 seed LambdaRankと比較を一括検証。証跡は `artifacts/loop-verification.json`。既定10,000 SKU・2,000万行のT2証跡は保持し、大規模ML通し実行は保留。`make pipeline`は既定でGTを生成するため、再利用には`--dataset` / `--judgments`を指定する。

## Scope / Plan

以下の個別taskを依存順に進める。

| # | task | 主な要件 | 依存・現在地 |
|---|---|---|---|
| T1 | [データ契約validatorと手書きfixture](../05_done/2026-09-22-データ契約validatorと手書きfixture.md) | AC-001, 008, 009 | 完了・正常fixture全14種 |
| T2 | [合成カタログ・Query・GTとfamily分割](../05_done/2026-09-22-合成カタログQueryGTとfamily分割.md) | AC-001, 005, 008 | T1 / 完了 |
| T3 | [Vector Baseline検索とSearchRun](../05_done/2026-09-22-VectorBaseline検索とSearchRun.md) | AC-001, 002, 008 | 完了・実E5/Qdrant検証済み |
| T4 | [評価・Slice・FailureCase](../05_done/2026-09-22-評価SliceとFailureCase.md) | AC-002, 003, 006, 008, 011 | 完了 |
| T5 | [構造化FeatureとLambdaRank](../05_done/2026-09-22-構造化FeatureとLambdaRank.md) | AC-006, 009 | 完了 |
| T6 | [Experiment比較と品質Gate](../03_active/2026-09-22-Experiment比較と品質Gate.md) | AC-001, 002, 003, 011 | offline比較実装済み・系譜/終了コードが残る |
| T7 | [疑似オンラインFeedback Loop](../02_backlog/2026-09-22-疑似オンラインFeedbackLoop.md) | AC-004, 006, 007, 008 | 次工程・policy詳細を具体化 |
| T8 | [独立評価・Release・Golden Path](../02_backlog/2026-09-22-独立評価ReleaseとGoldenPath.md) | AC-001〜011 | T1〜T7 |

- [x] 設定schema、foundation runのJSON/JSONL・manifest保存と改変検証。
- [x] Golden Path 9段階の骨組み（段階定義・成果物配置・blocker報告・ログ・終了コード 0/1/2/3）。未実装段階は`implemented: false`を明示。`make stages` / `make pipeline`で実行できる。
- [x] T1 基盤実装・作成済みfixture検証。正常fixture全14種まで追加済み。
- [x] T2 合成Catalog/Query/完全GT・family分割（既定2,000万行生成・全行読戻し検証）。
- [ ] T1〜T8全体を完了する（次はT6残件→T7→T8）。
- [x] foundation CLIとMakefile、設定・成果物の実テストを接続。
- [ ] 各taskで対応するML工程CLI、07の品質テスト、08のsmokeコマンドを実装。
- [ ] 01〜08の設計契約v1に対する実装確認と差分反映。

## Acceptance Criteria

01の受入条件と02の責務・境界を満たし、実行条件・結果を第三者が確認できる。BM25 / Hybrid等の拡張は採否決定後に別taskで追加する。
