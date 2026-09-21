> 退避元: `docs/検索品質-継続改善ループ-PoC設計メモ.md`（2026-09-21）。以下は整理前の全文。蒸留先は [要件](../01_requirements.md) / [基礎設計](../02_architecture.md)。権威順位は archive 最下位。候補・架空値・当時の表現を含み、現行仕様ではない。

# 検索品質 継続改善ループ PoC — 設計メモ

> 元メモ（チャットログ）を設計メモとして再構成したもの。最終更新: 2026-09-21

---

## 0. 結論

このPoCのゴールは **「評価基盤を作ること」ではなく「オンライン検索精度を継続的に上げる仕組みを作ること」**。
評価基盤はそのための手段に過ぎない。

プロジェクト名も `Search Evaluation Platform` ではなく **`Continuous Search Quality Improvement`** が実態に合う。

面接での説明はこう:

> オンライン検索精度を継続的に改善するため、失敗検知 → Ground Truth更新 → 再学習 → Slice評価 → 本番相当分布での検証まで、一連の改善ループを構築しました。

（「オフライン評価基盤を作りました」より一段上。MLエンジニアより MLOps / ML Platform / Tech Lead 寄りの話にできる。）

### なぜこれが正しいか

現場ではモデルは一度作って終わりではない。実際に回るのは以下のループで、検索は Ground Truth・検索候補・特徴量・ランキング・言語差・クエリ分布・オンラインKPI のどこか1つがズレるだけで本番精度が落ちる。
オフラインで NDCG +5% でも、オンラインでCTRや成功率が上がらなければ意味がない。

つまり現場で本当に必要なのは「NDCGを上げられる人」ではなく **「オンライン精度が悪い原因を切り分け、改善ループを回せる人」**。

---

## 1. 主役となる改善ループ

```
Online Monitoring
   ↓
失敗Query抽出
   ↓
Ground Truth 追加・更新
   ↓
Offline評価
   ↓
Failure分析
   ↓
Retrieval / Feature / Ranker 改善
   ↓
再学習
   ↓
Holdoutで再評価
   ↓
疑似Online分布で確認
   ↓
Deploy
   ↓
再Monitoring
```

| 位置づけ | 内容 |
|---|---|
| ゴール | Online Search Quality ↑ |
| 手段 | Monitoring / Ground Truth / Evaluation / Failure Analysis / Retraining / Validation |

---

## 2. 未決事項（要決定）

**商材を「自動車部品」と「FA部品総合EC」のどちらにするか。** 元メモでは両方が併走している。

- 冒頭の起点テーマ = 車の部品検索
- 推奨として出た結論 = 架空FA部品総合EC（現案件＝ミスミ系に最も近い）
- 後半の失敗シナリオ例 = 再び自動車部品（年式・型式・前後）

構造（型番・寸法・適合・多言語・意味検索）はどちらでも同じループが成立するため、**どちらを選んでも設計は流用可能**。以下は推奨のFA部品を主、自動車部品を従として併記する。

---

## 3. テーマ / 商材

### 推奨: 架空「FA部品総合EC」

現案件に最も近い。普通の商品ECと違い **型番・寸法・材質・規格・用途・同義語** が効くため、ベクトル検索＋ランキング改善の題材として強い。

単一カテゴリではなく総合ECにすることで、カテゴリ跨ぎ / 多言語 / 型番 / 自然文 / 寸法 / 属性 / 意味検索 / ランキング を全部入れられる。

**カテゴリ例**

```
Bearing
Bolt / Screw
Nut
Pneumatic Fitting
Linear Guide
Sensor
Motor
Cutting Tool
Cable / Connector
```

**規模**: 10,000〜50,000 SKU。完全に架空生成でよい。

### 商材候補の比較

| 商材 | 評価 |
|---|---|
| FA・機械部品（総合） | 現案件に最も近い ← 推奨 |
| ベアリング | 型番・寸法・用途が明確 |
| ボルト / ねじ | 構造化属性が非常に豊富 |
| 空圧継手 | 型式・径・用途が複雑 |
| 切削工具 | 材質・径・刃数・用途が多い |
| 電子部品 | 面白いが少し別領域に寄る |

---

## 4. データ設計

### 商品マスタ スキーマ

| 区分 | フィールド |
|---|---|
| 識別 | `product_id` / `category` / `manufacturer` / `model_number` |
| テキスト | `title_ja` / `title_en` / `description_ja` / `description_en` |
| 構造化スペック | `diameter` / `length` / `material` / `thread_size` / `voltage` / `pressure` / `precision_grade` |
| 商用 | `price` / `stock` / `popularity` |

### 属性のランダム生成レンジ（例: Bearing）

```
inner_diameter = 5〜100mm
outer_diameter = 15〜200mm
material       = steel / stainless / ceramic
type           = deep-groove / angular / thrust
```

---

## 5. クエリ設計（多言語）

現実的なバリエーションを作れるのがこの商材の強み。

```
"6204 ベアリング"
"M6 30mm SUS ボルト"
"耐熱 ベアリング 20mm"
"SMC 6mm ワンタッチ継手"
"24V proximity sensor"
"アルミ加工用 エンドミル 6mm"
```

同じ検索でも重要度の内訳が全部違う: **完全型番一致 / 寸法一致 / カテゴリ一致 / 材質一致 / 意味的類似**。
つまり **Embeddingだけでは勝てない検索問題** を自然に作れる。

### 言語ごとのデータ特性（意図的に作り分ける）

| 言語 | 特性 |
|---|---|
| JA | 型番・規格語が多い |
| EN | natural language query 多め |
| DE | compound noun 多め |
| ZH | 商品説明が短め |

→ 「言語によって Ground Truth の定義やデータ特性が違う」という論点をそのまま再現できる。

---

## 6. Ground Truth 設計

この商材はGTルールが非常に作りやすい。

| 条件 | relevance |
|---|---|
| 型番 完全一致 | 4 |
| カテゴリ + 寸法 完全一致 | 3 |
| カテゴリ + 用途 + 材質 一致 | 2 |
| 意味的には近いが仕様不一致 | 1 |
| 別カテゴリ | 0 |

---

## 7. アーキテクチャ

```
Product Master
   ↓
Embedding
   ↓
Vector DB
   ↓
Candidate Retrieval
   ↓
Feature Generation
   ↓
LightGBM LambdaRank
   ↓
Ranked Results
```

**Vector DB 候補（ローカル）**: Qdrant / pgvector / FAISS
WSLなら Qdrant Docker、さらに軽くするなら FAISS 単体でも成立する。必要になれば Elastic Cloud も検討。

**Ranker**: LightGBM（scikit-learn）の LambdaRank。

---

## 8. 評価設計

オフライン指標は **「オンラインKPIの改善を予測できるか」** という観点で設計する。

| レイヤ | 指標 |
|---|---|
| オフライン | Recall@100 / NDCG@10 / MRR |
| スライス | 言語別NDCG / Query Type別NDCG |
| 疑似オンラインKPI | Search Success Rate / CTR / Zero Result Rate / Reformulation Rate / Conversion |

---

## 9. 意図的な失敗シナリオ

このテーマの最大の強みは **わざと失敗を仕込める** こと。

### ケースA: FA部品（寸法違い）

Baseline を vector similarity のみにすると `"M6 SUS bolt"` と `"M8 SUS bolt"` がかなり近くなる。意味的には近いが、工業部品検索では寸法違いは致命的。

`"M6 30mm SUS bolt"` に対する Vector-only の結果:

| 順位 | 商品 |
|---|---|
| 1 | M8 30mm SUS bolt |
| 2 | M6 40mm SUS bolt |
| 3 | M6 30mm steel bolt |
| 4 | **M6 30mm SUS bolt** ← 本来これが1位であるべき |

**追加するFeature**: `diameter_exact_match` / `thread_exact_match` / `model_number_match` / `material_match`

### ケースB: 自動車部品（適合違い）

Vector Search だけだと「車種は合うが年式違い・型式違い・前後違い」という失敗が出る。

**追加するFeature**: `year_match` / `model_code_match` / `position_match` / `part_number_match`

### 改善の流れ（両ケース共通）

```
Failure detected
   ↓
dimension / fitment mismatch と特定
   ↓
Feature追加
   ↓
Retrain (LambdaRank)
   ↓
NDCG改善
   ↓
疑似オンライン分布でも改善を確認
```

### 到達イメージ（架空の目標値）

**オフライン**

| 構成 | NDCG@10 |
|---|---|
| Vector-only | 0.61 |
| Vector + structured features + LambdaRank | 0.83 |

（自動車部品ケースでは 0.66 → 0.81 想定）

**重要なのは、ここで止めず疑似オンライン分布でも改善を確認すること**

| KPI | Before | After |
|---|---|---|
| Top1 Success | 72% | 84% |
| Wrong Fitment Rate | 11% | 4% |
| Search Reformulation | 18% | 10% |

---

## 10. 破綻条件と対策

**最も避けるべき失敗**: Ground Truth を改善した結果、**そのGround Truthにだけ強いモデル** になること。

**必須の分離**

```
Training / tuning set
      ≠
Holdout set
      ≠
Production-like simulation
```

さらに **seed も変える**。ここまでやって3つが同方向に改善すれば、かなり説得力がある。

---

## 11. 命名

### 判断軸

1. **0章の結論と一致させる** — ゴールは評価基盤でなく継続改善ループ。名前の主語もループ側にする
2. **2章の未決事項を吸収する** — 商材が未確定のため、商材を名前に固定するとrenameが必要になる

### リポジトリ名: `parts-search-quality-loop`（採用）

- ループが主語 → 「改善可能性をシステム化する」という位置づけと一致
- `parts` が中立 → FA部品 / 自動車部品のどちらに決めてもrename不要

| 候補 | 主語 | 商材固定 | 評価 |
|---|---|---|---|
| `parts-search-quality-loop` | ループ | なし | **採用** |
| `industrial-search-quality-loop` | ループ | ややFA寄り | 次点。FA確定ならこれでもよい |
| `search-quality-loop` | ループ | なし | 最短だがドメインの具体性が消える |
| `search-relevance-ops` | 運用 | なし | MLOps / Platform 寄りの印象が最も強い |
| `continuous-search-quality` | 改善 | なし | 0章の名称そのまま。`loop` が無く動きが弱い |
| `ltr-search-improvement-loop` | 技術 | なし | LTRが前面に出て手段が主語になる |

**却下した元案**

- `synthetic-fa-product-search` — 主語が synthetic data / search になりゴールとズレる。かつ `fa` で商材を固定してしまう

### README 一文

> A continuous search-quality improvement loop for multilingual industrial parts search: synthetic catalog and ground-truth generation, vector retrieval, learning-to-rank, slice evaluation, failure analysis, and production-like validation.

主語が loop になり、synthetic生成は手段側に下がる。

現案件を直接コピーせず、**構造だけ再現する** テーマとして相性がよい。

---

## 12. 構成要素チェックリスト

- [ ] 商材の確定（FA部品 / 自動車部品）
- [ ] 商品マスタ生成器（10,000〜50,000 SKU・多言語）
- [ ] クエリ生成器（言語別の特性差を含む）
- [ ] 正解データ作成システム（relevance 0〜4 のルールベース生成）
- [ ] Embedding + Vector DB（Qdrant / pgvector / FAISS）
- [ ] Feature Generation（構造化一致フラグ群）
- [ ] LightGBM LambdaRank による再ランキング
- [ ] 評価システム（オフライン指標 + スライス評価）
- [ ] 評価基盤（Train / Holdout / Production-like の3分離 + seed変更）
- [ ] 疑似オンライン分布シミュレータ + オンラインKPI
- [ ] Failure分析 → Feature追加 → 再学習 のループ自動化
