# 検索品質PoCの残る選定・設定

## Goal

[参照実装レビュー](../../reference-implementation-review.md)後の未決事項を確定し、01〜08へ反映する。ID・保存形式・GT優先順位・分割・指標・event・採否状態は設計契約v1として具体化済み。以前の一覧をそのまま未決扱いしない。

## 残る判断

| 項目 | 決めること | 決定時期 |
|---|---|---|
| 商材 | 初期FA部品に設定済み。カテゴリ構成の具体化 | 生成器実装前 |
| 初期規模・言語 | 10,000 SKU・JA/EN・1,000 family・split比率は設定済み。言語別query分布の具体化 | 生成器実装前 |
| 商材別GT | 必須属性、正規単位、数値許容差、代替条件、自然文の制約抽出 | GT実装前 |
| Retrieval | 初期Qdrantローカルに設定済み。**Embedding model/revisionは下記の実測を踏まえて決める**。filter / boostの追加方式 | 検索実装前 |
| Hybrid | BM25 / Hybrid / RRFの採否とprefetch・fusion設定 | 拡張実装前 |
| 品質ゲート | 最小NDCG改善量、guardrail許容回帰、最低Slice件数、反復seed数 | candidate比較前 |
| SimulationPolicy | 観測窓、位置バイアス、click / conversion / reformulation確率、分布shift条件 | simulation実装前 |
| 実行環境 | 依存version・lock、ir_measures provider、model数値許容差、CLI名・実コマンド | 各工程実装時 |
| OSSの導入 | ライセンス・依存互換・コード流用の採否。静的な参照と導入は別 | 導入前 |

## Embedding 実行ライブラリの実測（2026-09-22）

決定前に両候補を実際に導入して API を確認した。**結論: 05 の契約を満たせるのは sentence-transformers のみ。**

| | fastembed 0.8.0 | sentence-transformers 3.0.1 |
|---|---|---|
| `revision` 指定 | **不可**（`TextEmbedding.__init__` に param が無い） | **可**（`revision: Optional[str]`） |
| `local_files_only` | — | 可（再現実行でネットワークを切れる） |
| `multilingual-e5-small` | **非対応**（レジストリに無い） | 利用可（HF から直接） |
| 多言語モデル | `multilingual-e5-large`(1024dim/2.24GB)、`paraphrase-multilingual-MiniLM-L12-v2`(384dim/0.22GB) ほか | HF にあるもの全般 |
| 依存 | ONNX Runtime（軽い） | torch（重い） |
| モデルの出所 | Qdrant 再配布 ONNX（`qdrant/multilingual-e5-large-onnx`）または GCS tarball | upstream HF repo |

**05 は「index は catalog・embedding revision・前処理設定の checksum から識別し、再構築できる派生成果物とする」と定める。** fastembed は revision を持てないため、この識別契約を実装できない。モデル実体も Qdrant の再配布版で upstream の revision とは別物になる。

したがって **sentence-transformers を採用する**。torch 依存は問題にしない — T5 で LightGBM を使う前提であり ML 依存は前提。プロジェクトが優先すると宣言しているのは再現性であって導入容量ではない。

（fastembed を採るには 05 の revision 契約を緩める改訂が要る。契約を黙って破らないため、それは採らない。）

### 決定（2026-09-22）

| 項目 | 値 |
|---|---|
| ライブラリ | `sentence-transformers>=3.0,<3.1`（同一 minor 固定。rules/python.md） |
| `retrieval.embedding.modelId` | `intfloat/multilingual-e5-small`（384dim, MIT, JA/EN） |
| `retrieval.embedding.revision` | `614241f622f53c4eeff9890bdc4f31cfecc418b3`（2026-09-22 に HF API で取得した実 SHA） |
| `retrieval.embedding.preprocessingVersion` | `parts_e5_v1` = NFKC + 型番正規化（全角→半角・ハイフン統一・大文字化）+ E5 の `query: ` / `passage: ` prefix |

代替（E5 の prefix 規約を避けたい場合）: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（384dim, Apache-2.0, SHA `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`）。

### 🚨 環境制約: このMacは x86_64 のため numpy<2 が強制される

実測で `RuntimeError: Numpy is not available` を踏んだ。原因は**インストール容量ではなくバージョン組合せ**。

```text
numpy 2.4.6 + torch 2.2.2  -> RuntimeError: Numpy is not available
numpy 1.26.4 + torch 2.2.2 -> OK
```

- このマシンは **x86_64（Intel）**。PyTorch の macOS x86_64 wheel は **2.2.2 が最後**で、それ以降は arm64 のみ。
- torch 2.2.2 は numpy 1.x に対してビルドされており、**numpy 2.x とは ABI 非互換**。
- よって **`numpy>=1.26,<2` を全体の制約として固定する**。後続の LightGBM・ir_measures もこの制約下で選ぶ。

実測で動いた組合せ（そのまま pin する）:

| パッケージ | pin |
|---|---|
| `numpy` | `>=1.26,<2` |
| `torch` | `>=2.2,<2.3`（x86_64 macOS の最終版） |
| `transformers` | `>=4.44,<4.45` |
| `sentence-transformers` | `>=3.0,<3.1` |

**この制約を記録しないと、後で誰かが numpy を上げて torch 連携が壊れる。** エラーは import 時ではなく `torch->numpy` 変換時に出るため、気付くのが遅い。

### 併せて記録する見立て

dense embedding は**型番の完全一致に弱い**（`SHF-20` と `SHF-25` を近いと判定する）。`exact_model_number` が query type にあるため vector-only baseline はそこで弱く出るが、**それは T5（構造化 Feature + LambdaRank）が埋める改善余地**であり、baseline を強化するために BM25 / Hybrid を先に入れると改善ループの検証対象が消える。T3 の Non-scope はそう読める。

## 全項目を仮置きで確定した（2026-09-22）

**方針**: 実データで動かすまで最適値は分からない。よって**論理的に妥当な既定を置いて先に進め、実測後に調整する**。未確定を理由に工程を止めない。

| 設定 | 仮置き値 | 根拠 |
|---|---|---|
| `catalog.attributePolicyId` | `fa_parts_attr_v1` | 合成データなので policy ID を先に切り、内容は T2 実装時に定義 |
| `features.schemaId` | `parts_features_v1` | 列順を含む checksum は T5 で確定 |
| `evaluation.version` | `0.4.3` | **実測**した ir_measures の解決版 |
| `evaluation.provider` | `ir_measures` | 05 の `implementation` と一致 |
| `qualityGate.policyId` | `parts_gate_v1` | — |
| `qualityGate.minNdcgDelta` | `0.01` | NDCG@10 で 1pt 改善を最小要求 |
| `qualityGate.maxRegression.*` | `0.01`（wrongFitmentRate は `0.005`） | 誤適合は業務影響が大きいので他より厳しく |
| `qualityGate.minSliceQueries` | `30` | Slice 集計が意味を持つ最小件数 |
| `qualityGate.repetitionSeeds` | `[11, 22, 33]` | 3 反復で seed 感度を見る |
| `simulation.policyId` | `parts_sim_v1` | — |
| `simulation.observationWindowSeconds` | `1800` | 30 分 |
| `simulation.behaviorModel` | `position_biased_cascade_v1` | 位置バイアス付き cascade |
| `simulation.enabled` | `false` | T7 未実装。**有効化できる**ことは確認済み（下記 schema 修正） |

結果: `make pipeline` の blocked が **8/9 → 1/9**（simulation のみ、意図的に無効）。

### schema の設計欠陥を修正

`simulation.enabled` が `const(False)` だったため、**T7 で有効化できず段階が永久に実行不能**だった。`blockers()` 側に「enabled が false なら未充足」と報告する仕組みが既にあるので、schema を boolean へ変更した。`enabled=true` で blocker が消えることを実測で確認済み。

## 依存の実測結果（2026-09-22）

決定に沿って実依存を導入し、lock を解決して**全モジュールの import まで確認**した。

| パッケージ | 解決版 | 備考 |
|---|---|---|
| numpy | 1.26.4 | **1.x 固定が必須** |
| torch | 2.2.2 | x86_64 macOS の最終 wheel |
| transformers | 4.44.2 | |
| sentence-transformers | 3.0.1 | revision 指定ロードを実測確認 |
| qdrant-client | 1.19.1 | |
| ir_measures | 0.4.3 | |
| lightgbm | 4.6.0 | **`brew install libomp` が必要**（未導入だと import 時に dlopen 失敗） |

### 🚨 制約は連鎖する

```text
x86_64 mac -> torch <= 2.2.2 -> numpy < 2 -> Python < 3.13
```

`requires-python = ">=3.11"` のままでは **qdrant-client が Python 3.14 で numpy>=2.3 を要求して依存解決が失敗**する。`>=3.11,<3.13` へ狭めた。この連鎖を知らずに Python や numpy を上げると壊れる。

実測で確認した動作:

- `torch->numpy` 変換（numpy 2.x だと `RuntimeError: Numpy is not available`。**import では落ちず変換時に落ちるので気付きにくい**）
- `sentence-transformers` で `revision` 指定ロード・384dim・決定的なベクトル
- `lightgbm` の LambdaRank 学習（`label_gain=[0,0,1,3,7]`、libomp 導入後）

## Acceptance Criteria

- 対応する契約の正本へ決定を反映する。
- 未設定の必須条件で実行・品質合格を通さない。
- 商材・技術候補の決定と、設計契約v1の実装確認を区別する。
