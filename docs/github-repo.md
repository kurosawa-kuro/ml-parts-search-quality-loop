結論として、今回の `parts-search-quality-loop` は、**1つのGitHubリポを真似するより、5〜7個を役割別に組み合わせるのが正解**です。

特に参考価値が高いのは、**Metarank / Amazon ESCI / Qdrant demo / Quepid / OpenSearch Search Relevance / Elasticsearch LTR** の6系統です。

| 優先     | GitHub                                           | 今回どこを参考にするか                                              |
| ------ | ------------------------------------------------ | -------------------------------------------------------- |
| **S**  | `metarank/metarank`                              | **Online event → judgement → retrain → rerank の継続改善ループ** |
| **S**  | `amazon-science/esci-data`                       | **商品検索GT・多言語・relevance設計**                               |
| **S**  | `opensearch-project/dashboards-search-relevance` | **Query Set / Judgment / 比較評価 / 改善実験**                   |
| **A**  | `qdrant/qdrant_demo`                             | Dense / BM25 / Hybrid Retrieval                          |
| **A**  | `o19s/quepid`                                    | **検索品質を継続的に改善するワークフロー思想**                                |
| **A**  | `o19s/elasticsearch-learning-to-rank`            | Feature生成 → 学習データ → LTR → rerank                         |
| **B+** | `wufanyou/KDD-Cup-2022-Amazon`                   | 商品検索 + LightGBMによるランキング                                  |
| **B+** | `tanmay0401/code-mixed-search-benchmark`         | 多言語・failure analysis・nDCG/MRR                            |
| **B**  | `terrierteam/ir_measures`                        | 評価指標ライブラリ                                                |
| **B**  | `DylanJoo/runs-and-qrels`                        | qrels / run / CI評価の構成                                    |

### 1. 一番重要: `metarank/metarank`

今回の設計思想に**最も近い**です。

Metarankは検索や推薦のranking eventと、click / purchaseなどのinteractionを取り込み、その履歴からclick-throughデータを作って、最終的にLTRモデルの学習データへ変換します。つまり、

`Online ranking → interaction → training data → retraining → rerank`

というループを既にかなり明確に実装しています。 ([github.com][1])

特に今回パクるべきなのはモデルそのものではなく、

```text
events/
  ranking
  interaction
      ↓
clickthrough
      ↓
implicit judgement
      ↓
feature dataset
      ↓
train
      ↓
model
      ↓
rerank
```

この境界設計です。

今回なら、

```text
search_impression
search_click
conversion
reformulation
zero_result
```

をイベントとして扱えばかなり近くなります。

**今回の中核参考リポはこれでいいです。**

[metarank/metarank](https://github.com/metarank/metarank?utm_source=chatgpt.com)

---

### 2. GT設計は `amazon-science/esci-data`

これは今回のPoCにかなり刺さります。

Amazonの商品検索データで、

* Exact
* Substitute
* Complement
* Irrelevant

というquery-product relevanceを持っています。

さらに **英語・日本語・スペイン語**を含む多言語データです。Query Product Rankingそのものがタスクとして存在します。 ([GitHub][2])

つまり今考えている、

```text
4 = 型番完全一致
3 = カテゴリ + 寸法一致
2 = 用途・材質一致
1 = 意味だけ近い
0 = 不一致
```

というGT設計のベースとして非常に使いやすいです。

むしろ少し構造を借りて、

```python
class RelevanceLabel(Enum):
    EXACT = 4
    COMPATIBLE = 3
    SUBSTITUTE = 2
    RELATED = 1
    IRRELEVANT = 0
```

のようにすると商品検索らしさが増します。

[amazon-science/esci-data](https://github.com/amazon-science/esci-data?utm_source=chatgpt.com)

---

### 3. 評価・Judgement管理は `OpenSearch Search Relevance`

ここは**かなり重要な発見**です。

OpenSearchのSearch Relevance Toolsは、

* Query Set
* Judgement
* Search Configuration比較
* NDCG / MAP
* Hybrid Optimizer

まで持っています。つまり、「検索品質改善を繰り返す」という思想自体が今回とかなり近い。 ([GitHub][3])

構造としては、

```text
Query Set
   ↓
Search Config A
Search Config B
   ↓
Judgments
   ↓
NDCG comparison
   ↓
Configuration improvement
```

です。

今回ならConfig比較を、

```text
vector_only
vector_structured
vector_ltr_v1
vector_ltr_v2
```

に置き換えればよい。

さらに最近のOpenSearch側では、LLMによるquery生成・judgement生成・hybrid最適化の自動化まで進めています。 ([GitHub][4])

今回の将来形、

```text
Failure Query
 ↓
GT生成
 ↓
再評価
 ↓
最適構成探索
```

ともかなり近いです。

[OpenSearch Search Relevance Dashboard](https://github.com/opensearch-project/dashboards-search-relevance?utm_source=chatgpt.com)

---

### 4. Retrieval部分は `qdrant/qdrant_demo`

ここは実装をかなりそのまま参考にできます。

同一データに対して、

* Semantic
* Keyword/BM25
* Hybrid
* RRF

を切り替えています。 ([GitHub][5])

Qdrant本体もdense / sparse / payload filter / hybrid searchをサポートしています。 ([GitHub][6])

今回なら、

```text
dense
BM25
hybrid
hybrid + structured filtering
hybrid + LambdaRank
```

を比較するBaseline構築に使えます。

特に、

> EmbeddingだけではM6とM8を区別できない

という失敗を出したい今回には都合がいい。

[qdrant/qdrant_demo](https://github.com/qdrant/qdrant_demo?utm_source=chatgpt.com)

---

### 5. 「検索品質改善」という思想は `o19s/quepid`

これも今回かなり参考になります。

Quepidの思想は、

> 検索変更を繰り返しテストし、品質悪化を防ぎながら継続改善する

というものです。 ([GitHub][7])

今回の名前、

```text
Continuous Search Quality Improvement
```

とほぼ同じ方向です。

ただしQuepidはUIが巨大なので、**コードをコピーする対象ではない**です。

参考にするのは、

```text
Case
Query
Judgement
Search result
Score
Experiment
```

というドメインモデル。

つまり今回、

```text
QuerySet
GroundTruth
SearchRun
EvaluationRun
FailureCase
Experiment
```

のような構造にすると良いです。

[o19s/quepid](https://github.com/o19s/quepid?utm_source=chatgpt.com)

---

### 6. Feature → LTR は `o19s/elasticsearch-learning-to-rank`

ここも重要。

このリポは、

```text
Feature definition
 ↓
Feature logging
 ↓
Training dataset
 ↓
XGBoost / Ranklib
 ↓
Model
 ↓
Reranking
```

を明確に分離しています。 ([GitHub][8])

今回なら完全に、

```python
semantic_score
bm25_score

model_number_exact_match
diameter_exact_match
thread_exact_match
material_match
category_match
manufacturer_match
stock
popularity
```

をfeature vectorにすればいい。

ただし、Elastic Pluginそのものを使う必要はありません。

**Feature Storeの設計思想だけ借りる**のがよいです。

[o19s/elasticsearch-learning-to-rank](https://github.com/o19s/elasticsearch-learning-to-rank?utm_source=chatgpt.com)

---

### 7. `LightGBM + 商品検索`なら Amazon KDD Cup

`wufanyou/KDD-Cup-2022-Amazon` は今回かなり実装寄りです。

Cross Encoderの出力や商品属性由来featureを作り、それをLightGBMで統合しています。 ([GitHub][9])

今回Cross Encoderは不要ですが、

```text
retrieval score
+
structured feature
+
model prediction
↓
LightGBM
```

という考え方はそのまま使えます。

つまり、

```text
Qdrant score
BM25 score
diameter_match
material_match
model_number_match
category_match
```

↓

```text
LightGBM LambdaRank
```

です。

[wufanyou/KDD-Cup-2022-Amazon](https://github.com/wufanyou/KDD-Cup-2022-Amazon?utm_source=chatgpt.com)

---

### 8. 多言語 + Failure Analysis

`tanmay0401/code-mixed-search-benchmark`

これもかなり今回向けです。

BM25 / multilingual dense / rerankingを比較し、

* nDCG
* MRR
* failure analysis

まで行っています。 ([GitHub][10])

今回予定している、

```text
language
query_type
category
exact-model-number
natural-language
dimension-sensitive
```

によるSlice分析を作る参考になります。

特に

```python
failures = results[
    (results.ndcg < threshold)
    & (results.language == "ja")
]
```

のような**failure slice抽出**部分はこちらを参考にするとよいです。

[code-mixed-search-benchmark](https://github.com/tanmay0401/code-mixed-search-benchmark?utm_source=chatgpt.com)

---

## 私ならこう組み合わせます

今回、GitHubからコードを丸ごと持ってくる必要はほぼありません。

```text
parts-search-quality-loop
│
├── catalog/
│   └── Amazon ESCI思想
│
├── retrieval/
│   └── qdrant_demo
│
├── features/
│   └── elasticsearch-learning-to-rank
│
├── ranker/
│   └── Amazon KDD Cup / LightGBM
│
├── judgments/
│   └── ESCI + OpenSearch Search Relevance
│
├── evaluation/
│   └── ir_measures
│
├── failure_analysis/
│   └── code-mixed-search-benchmark
│
└── feedback_loop/
    └── Metarank
```

これがかなり綺麗です。

### さらに設計を1段上げるなら

今の設計に1つだけ追加したいです。

```text
Experiment
```

を第一級オブジェクトにします。

例えば、

```yaml
experiment_id: exp_20260921_001

retrieval:
  dense: bge-m3
  sparse: bm25
  fusion: rrf

features:
  model_number_match: true
  diameter_match: true
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

そして、

```text
Experiment
 ↓
SearchRun
 ↓
Metrics
 ↓
Slices
 ↓
FailureCases
 ↓
Next Experiment
```

にする。

これで単なる「評価コード」ではなく、

**検索品質Experiment Platform**

になります。

今のPoCの狙いにはこちらの方が合っています。

### 最終的な優先順位

最初に読むなら、この順です。

1. **Metarank**
2. **Amazon ESCI**
3. **OpenSearch Search Relevance**
4. **Qdrant demo**
5. **Elasticsearch LTR**
6. **Quepid**
7. Amazon KDD Cup
8. code-mixed-search-benchmark

この6個くらいを押さえれば、**今回のPoCの構成要素の8〜9割は既存OSSの設計思想から持ってこられます**。

そして重要なのは、これを見る限り今回のPoCは「ありものをつなげただけ」にはならないことです。既存OSSはそれぞれ **Retrieval / Evaluation / LTR / Feedback** を持っていますが、

```text
Online failure
→ GT更新
→ Slice analysis
→ Feature改善
→ LambdaRank retrain
→ Holdout
→ Production-like validation
→ Online simulation
```

までを**一つの再現可能なPoCとして束ねるところ**が、今回の `parts-search-quality-loop` の独自部分になります。

[1]: https://github.com/metarank/metarank?utm_source=chatgpt.com "GitHub - metarank/metarank: A low code Machine Learning personalized ranking service for articles, listings, search results, recommendations that boosts user engagement. A friendly Learn-to-Rank engine · GitHub"
[2]: https://github.com/amazon-science/esci-data?utm_source=chatgpt.com "GitHub - amazon-science/esci-data: Shopping Queries Dataset: A Large-Scale ESCI Benchmark for Improving Product Search · GitHub"
[3]: https://github.com/opensearch-project/dashboards-search-relevance?utm_source=chatgpt.com "GitHub - opensearch-project/dashboards-search-relevance: Tools to help search relevance engineers and business users tune search results for their OpenSearch applications. · GitHub"
[4]: https://github.com/opensearch-project/search-relevance/issues/407?utm_source=chatgpt.com "[META] Auto-optimized hybrid search · Issue #407 · opensearch-project/search-relevance · GitHub"
[5]: https://github.com/qdrant/qdrant_demo?utm_source=chatgpt.com "GitHub - qdrant/qdrant_demo: Demo of the neural semantic search built with Qdrant · GitHub"
[6]: https://github.com/qdrant/qdrant?utm_source=chatgpt.com "GitHub - qdrant/qdrant: Qdrant - High-performance, massive-scale Vector Database and Vector Search Engine for the next generation of AI. Also available in the cloud https://cloud.qdrant.io/ · GitHub"
[7]: https://github.com/o19s/quepid?utm_source=chatgpt.com "GitHub - o19s/quepid: Improve your OpenSearch, Elasticsearch, Solr, Vectara, Algolia and Custom Search search quality. · GitHub"
[8]: https://github.com/o19s/elasticsearch-learning-to-rank?utm_source=chatgpt.com "GitHub - o19s/elasticsearch-learning-to-rank: Plugin to integrate Learning to Rank (aka machine learning for better relevance) with Elasticsearch · GitHub"
[9]: https://github.com/wufanyou/KDD-Cup-2022-Amazon?utm_source=chatgpt.com "GitHub - wufanyou/KDD-Cup-2022-Amazon: This repository is the team ETS-Lab's solution towards KDD Cup 2022. · GitHub"
[10]: https://github.com/tanmay0401/code-mixed-search-benchmark?utm_source=chatgpt.com "GitHub - tanmay0401/code-mixed-search-benchmark: Reproducible IR benchmark for Hinglish / code-mixed product search on Amazon ESCI: BM25 vs multilingual dense vs LLM reranking, evaluated with nDCG/MRR + failure analysis. · GitHub"
