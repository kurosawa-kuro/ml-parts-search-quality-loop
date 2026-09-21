# 02 アーキテクチャ

> 最終更新: 2026-09-21。[要件](./01_requirements.md) を実現する設計方針の正本。以下のプロダクト構成・パスは実装予定であり、実装済みではない。選定前の技術と追加提案は明記する。

## 概要

ローカルで再現可能な改善ループを構築する。候補取得と再ランキング、GT更新と評価を分離し、Experimentを軸に入力・処理・結果を関連づける。

```text
Product Master → Embedding / Index → Candidate Retrieval
                                           ↓
                                    Feature Generation
                                           ↓
                                    LightGBM LambdaRank
                                           ↓
                                      SearchRun
                                           ↓
QuerySet + GroundTruth ───────────→ EvaluationRun
                                           ↓
                                     Metrics / Slices
                                           ↓
                                      FailureCase
                                           ↓
                        GT更新 / Retrieval・Feature改善 / 再学習
                                           ↓
                            Holdout → Production-like validation
                                           ↓
                                採否記録 → Online simulation
                                              ↓
                                Events → FailureCase → 次のExperiment
```

PoCのDeployは疑似オンライン実験で使う構成・モデルの切り替えとして扱う。実サービスへの配備は範囲外。

## 構成要素と責務

プロダクトコードは `src/` 配下に置く。下記は責務の分割案であり、個別APIやファイル形式は実装タスクで具体化する。

| 構成要素 | 役割 | 担当パス（プロダクト部分は予定） |
|---|---|---|
| Catalog / Query生成 | 商品属性、多言語テキスト、クエリと分割データの生成 | `src/catalog/` |
| Retrieval | Embedding、Index、候補取得と検索スコアの出力 | `src/retrieval/` |
| Features | query-productの構造化一致と検索スコアを特徴量化 | `src/features/` |
| Ranker | 学習データからモデルを作り候補を再ランキング | `src/ranker/` |
| Judgments | GTの生成・更新・版管理、判定根拠の保持 | `src/judgments/` |
| Evaluation | SearchRunとGTから指標・Sliceを生成 | `src/evaluation/` |
| Failure analysis | 評価・イベントから失敗クエリと原因候補を抽出 | `src/failure_analysis/` |
| Feedback loop | イベント生成・集約、改善実験への接続 | `src/feedback_loop/` |
| Experiment | 設定・入力版・モデル・実行結果を関連づける | 保存場所・実行インターフェースは未決 |
| エージェントガイド | Codex / 他エージェント向けrepoガイド | `AGENTS.md` |
| Claudeガイド | Claude Codeの司令ルール | `CLAUDE.md` |
| タスク文書 | 一回性の作業計画・実装タスク | `docs/tasks/` |
| Claude skills | Claude Code用の繰り返し手順 | `.claude/skills/` |

## データとGTの境界

### 商品・クエリ

商品は識別情報（`product_id`, `category`, `manufacturer`, `model_number`）、多言語テキスト、構造化スペック、商用属性に分ける。

- テキスト例: `title_ja`, `title_en`, `description_ja`, `description_en`。
- スペック例: `diameter`, `length`, `material`, `thread_size`, `voltage`, `pressure`, `precision_grade`。
- 商用属性例: `price`, `stock`, `popularity`。
- クエリ例: `6204 ベアリング`、`M6 30mm SUS ボルト`、`24V proximity sensor`。

必要属性は商材確定後に絞る。単位・欠損・正規化、多言語間のクエリ対応とID、ファイル形式は未決であり、データ契約を実装する前に確定する。

### Ground Truth

query-productに対する段階的relevanceを0〜4で表す。元メモのルール案を以下に集約する。

| relevance | 判定条件案 |
|---|---|
| 4 | 型番完全一致 |
| 3 | カテゴリ + 寸法完全一致 |
| 2 | カテゴリ + 用途 + 材質一致 |
| 1 | 意味的には近いが仕様不一致 |
| 0 | 別カテゴリ |

これは初期案であり全入力を網羅していない。型番一致と必須仕様不一致の競合、同一カテゴリ内の不適合、属性欠損、複数条件成立時の優先順位は未決。`EXACT / COMPATIBLE / SUBSTITUTE / RELATED / IRRELEVANT` の名前付けは追加提案として保持し、数値ルールやESCIラベルと自動的に同一視しない。

GTと検索特徴量は別の責務に置く。イベント由来の暗黙的な判定とルール生成GTを区別し、どの根拠からGTを更新したか追跡する。クリック等をGTへ反映する重み・判定ルールは今後定義する。

## Retrieval / Feature / Ranker

基本経路はVector検索 → 特徴量生成 → LightGBM LambdaRankによる再ランキング。Vector DBはQdrant / pgvector / FAISSから選定する。ローカル実行を想定し、特定エンジンへの依存はRetrieval内に閉じる。

| 比較構成 | 位置づけ |
|---|---|
| `vector_only` | 意味的類似のみのBaseline |
| `vector_structured` | 構造化条件を加えた比較候補。filter / boostの方式は未決 |
| `vector_ltr_v1` / `vector_ltr_v2` | 特徴量と学習モデルの改善比較 |
| BM25 / Hybrid / RRF | 添付からの拡張候補。PoC必須構成への採否は未決 |

特徴量候補は `semantic_score`, `bm25_score`（BM25採用時）、`model_number_exact_match`, `diameter_exact_match`, `thread_exact_match`, `material_match`, `category_match`, `manufacturer_match`, `stock`, `popularity`。自動車部品を選ぶ場合は年式・型式・位置の一致を検討する。

Feature定義 → Feature生成 → 学習データ → モデル → 再ランキングを分ける。候補取得の漏れはRecall、候補内の並びの問題はランキング指標・失敗例で切り分ける。Cross Encoder、外部LTRプラグイン、独立したFeature Storeの採用は必須にしない。

## Experimentと評価成果物

添付の提案を設計方針として取り込み、Experimentを第一級の管理単位とする。実行API・保存形式・ID体系は未決。

| 概念 | 責務・関連 |
|---|---|
| QuerySet | クエリ集合とSlice属性を識別する |
| GroundTruth | query-productの判定とその版・根拠を識別する |
| Experiment | Retrieval設定、Feature構成、Ranker版、GT版、データ分割・seedを束ねる |
| SearchRun | Experimentで得た順位付き検索結果を保持する |
| EvaluationRun | SearchRunとGTに対するMetrics / Slicesを保持する |
| FailureCase | 元Query・結果・評価またはイベントと失敗原因を関連づける |

```text
Experiment → SearchRun → EvaluationRun → Metrics / Slices
                                               ↓
                                          FailureCases
                                               ↓
                                        Next Experiment
```

例示設定（採用技術・版を確定するものではない）:

```yaml
experiment_id: exp_20260921_001
retrieval:
  dense: bge-m3
  sparse: bm25
  fusion: rrf
features:
  model_number_exact_match: true
  diameter_exact_match: true
  material_match: true
ranker:
  type: lightgbm_lambdarank
  version: v3
ground_truth:
  version: gt_20260921
dataset:
  train_seed: 42
  holdout_seed: 137
  production_seed: 999
```

この例に加え、実装時には実際のデータ版・分割対象を特定できる契約を定義する。版とseedだけで再現性を保証したとは扱わない。

## Feedbackと独立検証

イベント候補は `search_impression`, `search_click`, `conversion`, `reformulation`, `zero_result`。検索結果とinteractionを関連づけ、失敗抽出・GT更新・学習データ生成へつなぐ。イベントの識別子・時刻・検索実行との結合方法、欠落・重複時の扱いは実装前の未決事項とする。

```text
ranking / interaction events
  → 集約・判定候補
  → GT更新 / feature dataset
  → train → model → rerank
```

Training / tuning、Holdout、Production-like simulationを分離し、seedも変更する。分割単位と同一商品の派生・翻訳クエリ等の重複防止方法は未決。seed変更だけを漏洩防止の証拠にしない。Holdoutを繰り返し改善に利用する場合の更新方針も決める。

Baselineと改善候補の比較では、評価QuerySet・GT・データ条件を揃える。GT自体を更新した際の旧実験の再評価方法、採用基準・許容回帰はbacklogで決定する。判定条件が未確定の間は、自動採用・品質合格を行わず結果の比較までとする。

## Golden Pathとアーキテクチャ

| 要件のステップ | 通る構成要素 | 通る境界 / データ | 停止要因 |
|---|---|---|---|
| 1. 準備 | Catalog / Judgments / Experiment | Product Master / QuerySet / GT / 分割設定 | 入力・版・分割を特定できない |
| 2. Baseline評価 | Retrieval / Evaluation | SearchRun → EvaluationRun | Index欠落、結果とGTの対応不整合 |
| 3. 失敗抽出 | Feedback loop / Failure analysis | Events・Slices → FailureCase | イベントと検索結果を関連づけられない |
| 4. 更新・再学習 | Judgments / Features / Ranker | GT・Feature dataset → model | 学習入力・Feature定義の不整合 |
| 5. 独立比較 | Retrieval / Ranker / Evaluation | Holdout・Production-like結果 | 分割漏洩、比較条件の不一致 |
| 6. 次の実験 | Experiment / Feedback loop | 採否・次の構成 → Events | 採否根拠や使用モデルを追跡できない |

現時点のMakefileはテンプレートであり、この経路を実行するコマンドは未実装。実装時に [ワークフロー](./04_workflows.md)、[テスト戦略](./07_test_strategy.md)、[リリース運用](./08_release_runbook.md) へ実コマンドとsmoke条件を反映する。

## 成長フェーズ

1. 商材・初期言語・GT・分割・指標契約を確定し、Catalog / QuerySet / GT生成を作る。
2. Vector-onlyのSearchRun・EvaluationRun・Slice分析を通す。
3. 構造化FeatureとLambdaRankを加え、失敗改善を比較する。
4. 疑似オンラインイベント、GT更新、独立検証、採否記録を接続してループを1周する。
5. 必要に応じてBM25 / Hybrid / RRF、判定補助、構成探索を追加する。

## OSSの参照方針

単一リポを模倣せず、主に6系統の責務境界を参考にする。以下は添付から抽出した**調査観点**であり、各リポの現況・機能は今回検証していない。依存の導入やコード流用を決定したものではない。

| 参考候補 | 読み取る設計観点 | 対応先 |
|---|---|---|
| [Metarank](https://github.com/metarank/metarank) | イベントから判定・学習・rerankへ戻す境界 | Feedback loop |
| [Amazon ESCI](https://github.com/amazon-science/esci-data) | 商品検索のrelevance・多言語GT | Judgments |
| [OpenSearch Search Relevance](https://github.com/opensearch-project/dashboards-search-relevance) | Query Set・Judgment・検索構成の比較 | Experiment / Evaluation |
| [Qdrant demo](https://github.com/qdrant/qdrant_demo) | 検索方式の比較構成 | Retrieval |
| [Elasticsearch LTR](https://github.com/o19s/elasticsearch-learning-to-rank) | Feature定義・記録・学習・rerankの分離 | Features / Ranker |
| [Quepid](https://github.com/o19s/quepid) | Query・判定・結果・実験の関係 | 評価ドメイン |

補助候補はAmazon KDD Cup（LightGBMとの統合）、code-mixed-search-benchmark（多言語の失敗分析）、ir_measures（指標計算）、runs-and-qrels（評価データ構成）。出典・候補一覧・元の主張は [添付全文](./archive/search-quality-loop-oss-references.md) に保存する。

## 運用上の境界

非機密設定は `env/config.yaml`、ローカル秘密情報はignore対象の `env/secret.yaml`、共有・本番の秘密情報はDoppler等で管理する。実験別設定と成果物の保存先は実装時に決める。

Codex / 他エージェント共通の永続指針は `AGENTS.md` に置き、`.claude/` の常時読込を前提にしない。

## 関連タスク

構造・責務・adapter変更は実装前にtaskを作り、確定判断を本文またはADRに反映する。

- [未決事項と採否判断](./tasks/02_backlog/20260921-search-quality-poc-decisions.md)
- [Golden Pathの段階的実装](./tasks/02_backlog/20260921-search-quality-poc-implementation.md)
- [タスク一覧](./tasks/README.md)
