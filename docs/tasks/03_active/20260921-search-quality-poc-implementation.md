# 検索品質PoCのGolden Pathを段階的に実装する

## Goal

[要件](../../01_requirements.md) のGolden Pathを1周し、受入条件AC-001〜011の証跡を残す。

## Context

設定検証・foundation CLI・ローカルrun保存とMakefileの実テスト/整形/buildを実装済み。Golden Path 9段階のうちcontracts/catalog/judgmentsは実処理を実装済み。検索・学習・評価以降は未実装。設定済みの仮置きと工程内の残作業は [判断・設定台帳](../02_backlog/20260921-search-quality-poc-decisions.md) を参照する。

現在は3段階completed（contracts/catalog/judgments）、5段階skeleton、simulationのみblocked。未実装はsimulationも含め6段階。`make pipeline`は既定で2,000万行GTを生成するため、状況一覧だけなら`make stages`を使う。

## Scope / Plan

以下の個別taskを依存順に進める。

| # | task | 主な要件 | 依存・現在地 |
|---|---|---|---|
| T1 | [データ契約validatorと手書きfixture](../05_done/2026-09-22-データ契約validatorと手書きfixture.md) | AC-001, 008, 009 | foundation / 基盤完了、正常fixtureの残りをT3〜T6へ移管 |
| T2 | [合成カタログ・Query・GTとfamily分割](../05_done/2026-09-22-合成カタログQueryGTとfamily分割.md) | AC-001, 005, 008 | T1 / 完了 |
| T3 | [Vector Baseline検索とSearchRun](../02_backlog/2026-09-22-VectorBaseline検索とSearchRun.md) | AC-001, 002, 008 | T1,T2充足・Embedding選定済み / 次に着手 |
| T4 | [評価・Slice・FailureCase](../02_backlog/2026-09-22-評価SliceとFailureCase.md) | AC-002, 003, 006, 008, 011 | T1,T3 |
| T5 | [構造化FeatureとLambdaRank](../02_backlog/2026-09-22-構造化FeatureとLambdaRank.md) | AC-006, 009 | T1,T2,T3 |
| T6 | [Experiment比較と品質Gate](../02_backlog/2026-09-22-Experiment比較と品質Gate.md) | AC-001, 002, 003, 011 | T4,T5待ち・品質閾値は仮置き済み |
| T7 | [疑似オンラインFeedback Loop](../02_backlog/2026-09-22-疑似オンラインFeedbackLoop.md) | AC-004, 006, 007, 008 | T4,T6待ち・policy詳細はT7で具体化 |
| T8 | [独立評価・Release・Golden Path](../02_backlog/2026-09-22-独立評価ReleaseとGoldenPath.md) | AC-001〜011 | T1〜T7 |

- [x] 設定schema、foundation runのJSON/JSONL・manifest保存と改変検証。
- [x] Golden Path 9段階の骨組み（段階定義・成果物配置・blocker報告・ログ・終了コード 0/1/2/3）。未実装段階は`implemented: false`を明示。`make stages` / `make pipeline`で実行できる。
- [x] T1 基盤実装・作成済みfixture検証。正常fixture残りはT3〜T6の受入条件へ移管。
- [x] T2 合成Catalog/Query/完全GT・family分割（既定2,000万行生成・全行読戻し検証）。
- [ ] T1〜T8全体を完了する（次はT3。T1の残りfixtureは該当後続工程で追加）。
- [x] foundation CLIとMakefile、設定・成果物の実テストを接続。
- [ ] 各taskで対応するML工程CLI、07の品質テスト、08のsmokeコマンドを実装。
- [ ] 01〜08の設計契約v1に対する実装確認と差分反映。

## Acceptance Criteria

01の受入条件と02の責務・境界を満たし、実行条件・結果を第三者が確認できる。BM25 / Hybrid等の拡張は採否決定後に別taskで追加する。
