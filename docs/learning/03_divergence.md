# 食い違ったときにやること

場面は、DS が「NDCG が上がった」と LightGBM の新しいランを持ってきたときである。
プラットフォーム側の仕事は、そのランを VectorSearch の再投入と一緒くたにリリースしないことと、オンラインが動かなかったときに **どのジョブを、どの入力を固定して回し直すか** を成果物から決めることである。

`promote` は四つの関門が同時に通ったときだけである。実験後に [env/config.yaml](../../env/config.yaml) の `qualityGate` を緩めて通さない。コンペで private を見てから検証の切り方を変えないのと同じ制限である。

1. オフライン比較が accepted（NDCG の最小改善と、Recall / MRR / slice の許容回帰）
2. 学習に使っていない holdout が accepted
3. production の検索成功率の低下が `maxRegression.searchSuccessRate`（0.01）以内
4. 誤適合率の上昇が `maxRegression.wrongFitmentRate`（0.005）以内

Gate 段階の `decision` はオフライン比較の途中結果で、正式採用ではない。正式な採否は Release の `decision.json` にある。

## 失敗種別が、回し直すジョブを決める

`failures.jsonl` の `category` を、評価 run と simulation run で別々に数える。

| category | 入力表の状態 | 回すジョブ | 固定するもの |
|---|---|---|---|
| `retrieval_miss` | 適合が候補 100 件に無い | VectorSearch 側。埋め込み revision、前処理、取得件数 | LightGBM を先に回しても 1 位は変わらない |
| `rerank_miss` | 候補にはあるのに 1 位が適合ではない | LightGBM と特徴。候補の run は固定 | Recall が 0 差なのはこの実験では正常。混ぜて VectorSearch も更新しない |
| `simulation_miss` | 提示の 1 位が relevance 2 未満 | 上のどちらか。1 位が relevance 0 なら特徴、候補外なら VectorSearch | NDCG のマクロでこの件数を相殺しない |
| `execution_failure` | ジョブが落ちた | 再実行。品質の採否に入れない | null を 0 で埋めない |
| `gt_defect` | 正解が不完全 | 正解の版。モデルの比較を止める | 不完全なクエリを平均から落とさない |

参画先に Elasticsearch がある場合も、切り方は同じである。キーワード側を変えたなら候補集合が変わるので `retrieval_miss` 側の実験である。このリポジトリはその経路を持たない。ベクトル候補を固定したリランキングの実験として読む。

## 教材になっている失敗

ベクトルだけだと、要求が M6 30mm SUS のときに 1 位が M8 30mm SUS になる。relevance は 0 である。求める商品は候補の 4 位付近にいる。これは `rerank_miss` であり、オンラインでは `wrongFitmentRate` に出る。

足す列は意味類似の作り直しではない。実装の `parts_features_v1` は次である。

`vector_score`、`model_exact`、`category_exact`、`diameter_delta`、`length_delta`、`material_exact`、`standard_exact`、`usage_exact`

relevance や GT の rule id は列に入れない。入れると、ルールを復元するモデルになり、Feature Store に「正解そのもの」を載せるのと同じリークになる。

列を足すときのプラットフォーム側の固定は二つある。

- 候補 run の checksum を変えない。VectorSearch の再エクスポートと同時に列を足すと、NDCG の差がどちらのジョブのものか分からなくなる
- `feature_schema.json` の checksum を学習ジョブとバッチ推論で一致させる。列順が違うと推論を止める。止めたジョブを、欠損を 0 で埋めて通さない

1 位がまだ relevance 0 のクエリは、NDCG が改善していても `simulation_miss` に残る。`per_query.jsonl` でその `query_id` の 1 位と、クエリの必須寸法を突き合わせる。slice（language、query_type、category）で、マクロの裏に寸法クエリだけが残っていないかを見る。

## 次の実験に渡すもの

Release の `smoke.json` の `next_experiment` が、親実験 ID、失敗 ID、release ID を持つ。次のジョブはこの三つを入力にする。

比較が成立する条件は次である。

- カタログ、クエリ、正解、指標ポリシー、シミュレーション版の checksum が baseline と candidate で同じ
- リランキング実験なら候補 run も同じ。VectorSearch を変えた実験は別の `experiment_id` にする
- フィットは train だけ。holdout と production の点数を見て列や閾値を追加しない
- クリックは正解候補のログに留め、評価用正解の版は変えない

seed 三つで NDCG が一致しても、頑健性の確認は終わっていない。この LightGBM は `deterministic` で、bagging も feature subsample も無い。Gate の `repetition_signal` が `no_metric_variance_across_seeds` なら、seed は指標に入っていない。評価基盤に「3 seed の分散」を頑健性チェックとして足すなら、トレーナーが seed を実際に使う構成になってからである。

## 採用と戻し

四関門を満たしたら `activate` で `active.json` をその release に向ける。smoke が落ちたら `rollback` で直前の参照に戻す。モデルディレクトリは消えない。

不採用も成果物として残す。オンラインを動かす次のジョブは、その `decision.json` と `failures.jsonl` から開く。関門を緩めた再実行では開かない。
