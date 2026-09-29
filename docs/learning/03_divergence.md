# 食い違ったときにやること

ここが、このプロジェクトで習得する手順である。
前提は「オフラインは良くなった。オンラインは良くなっていない」。またはその逆。

採用しない。`decision` が `promote` になるのは、オフライン判定、holdout、検索成功率、誤適合率が、実験前に凍結した許容をすべて満たしたときだけである。
結果を見てから `minNdcgDelta` やガードレールを緩めて通すのは、検証を捨てることなのでやらない。許容は [env/config.yaml](../../env/config.yaml) の `qualityGate` にある。

## 1. オフラインの合格を、オンラインの合格と別にする

Gate 段階は、繰り返し seed のオフライン比較までで、正式な採否は出さない。
正式な `decision` は Release 段階で、holdout と疑似オンラインのガードレールを足してから付ける。

見るファイル:

- オフラインの並び: 評価 run の `metrics.json`、`per_query.jsonl`、`slices.jsonl`
- オンラインの 1 位: simulation run の `kpis.json`
- 採否: release の `decision.json`

`kpis.json` の検索成功率が baseline より許容を超えて下がり、または誤適合率が許容を超えて上がっていれば、NDCG が良くても切り替えない。

## 2. 失敗を、直す場所に分ける

評価と simulation は、クエリごとに失敗の種類を残す。`failures.jsonl` の `category` を数える。

| category | 意味 | 次に変える場所 | 変えてはいけない読み |
|---|---|---|---|
| `retrieval_miss` | 適合する部品が候補 100 件に入っていない | 埋め込み、前処理、候補の取り方 | 順位モデルを回しても 1 位にはならない |
| `rerank_miss` | 候補にはいるのに、1 位が適合ではない | 特徴と LambdaRank。候補集合は固定したまま比較する | Recall が動かないのは失敗ではない。1 位が動いたかが本題 |
| `simulation_miss` | 提示の最上位が relevance 2 未満 | 1 位が寸法違いか、空か、再検索されたかを `kpis.json` と impression で見る | NDCG の平均で打ち消さない |
| `execution_failure` | 検索や評価が落ちた | 実行。品質の話にしない | 点数 0 と混同しない |
| `gt_defect` | 正解データが不完全 | 正解。モデルの良し悪しではない | 合格にしない |

元メモが仕込んでいる教材は `rerank_miss` と誤適合である。

ベクトル検索だけの 1 位は、例えば次のようになる。

| 順位 | 商品 | 部品としての扱い |
|---|---|---|
| 1 | M8 30mm SUS | 寸法違い。relevance 0 |
| 2 | M6 40mm SUS | 長さ違い |
| 3 | M6 30mm steel | 材質違い |
| 4 | M6 30mm SUS | これが 1 位であるべき |

足す特徴は、意味の近さではない。型番一致、径の差、長さの差、材質・規格・用途の一致である。
実装の列は `vector_score` / `model_exact` / `category_exact` / `diameter_delta` / `length_delta` / `material_exact` / `standard_exact` / `usage_exact`。
正解ラベルそのものは特徴に入れない。入れると、ルールを暗記したモデルになる。

`simulation_miss` が残って `wrongFitmentRate` が下がらないときは、まだ 1 位が必須条件違反である。
NDCG 用に 2〜10 位を整えても、オンラインは動かない。見るのは `per_query.jsonl` で 1 位の商品が、そのクエリの必須寸法と一致しているかである。

全体平均で言語やクエリ種別が隠れる。`slices.jsonl` を、language / query_type / category で見る。
寸法指定のクエリだけが悪いまま、というのはよくある隠れ方である。

## 3. 原因の段だけを変えて、同じ条件で比較する

次の実験は、親実験の ID と、今回の失敗 ID を持ったまま開く。
Release の `smoke.json` にある `next_experiment` が、その三つ（親、失敗 ID、release ID）を残す場所である。

比較が成立する条件:

- カタログ、クエリ、正解データ、指標の定義、シミュレーションの版が同じ
- 順位だけを比べるなら、候補集合も同じ。検索の取り方を変えた実験と混ぜない
- train でフィットし、holdout と production は判定のあとまで改善に使わない
- オンラインのクリックで評価用正解を書き換えない

三つが同じ方向か、を見る。

| 見る場所 | 質問 |
|---|---|
| train 上の学習 | 特徴を足したモデルが、学習データでは 1 位を直せているか。ここだけの改善は採用理由にしない |
| holdout の NDCG と失敗種別 | 学習に使っていないクエリでも、並びと 1 位が同じ方向か |
| production の検索成功率と誤適合率 | 本番相当の family で、疑似ユーザーが見る 1 位が同じ方向か |

seed を変えて点数が動かないことがある。このリポジトリの LightGBM は決定的で、bagging がない。
seed が三つとも同じ NDCG でも、頑健性の証拠ではない。Gate は `repetition_signal` に `no_metric_variance_across_seeds` と出す。その表示を「ばらつきが小さい」と読まない。

## 4. 採用と戻し

四つの関門を同時に満たしたときだけ `promote` する。

1. オフライン比較が accepted
2. holdout が accepted
3. 検索成功率の低下が凍結した許容以内
4. 誤適合率の上昇が凍結した許容以内

そのあと `activate` で `active.json` をその release に向ける。smoke に失敗したら `rollback` で直前の release に戻す。成果物自体は消えない。
戻したあとも、失敗 ID は次の実験の入力として残る。オンラインを上げる作業は、不採用の記録から再開する。
