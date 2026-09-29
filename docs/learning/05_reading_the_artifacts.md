# 成果物の読み方

実行のやり方は [04 ワークフロー](../04_workflows.md)。ここは、終わったあとに学習のために開く順番である。

```bash
uv run --locked parts-search pipeline
```

小規模だと slice の件数が足りず exit 4 になる。実行失敗（exit 1）とは別である。
4 は「オンラインを上げる材料がまだ揃っていない」なので、閾値を下げて 0 にしない。

`promote` まで進んだ release は次で切り替える。失敗したら戻す。

```bash
uv run --locked parts-search activate artifacts/releases/<run_id>
uv run --locked parts-search rollback
```

## 開く順

ステージの成果物は `artifacts/<group>/<run_id>/` にある。run の対応は各 `manifest.json` の `metadata.stage` で見る。

| 順 | ファイル | 学習上の質問 |
|---|---|---|
| 1 | 評価 run の `metrics.json` | 並び全体の NDCG / Recall / MRR は baseline と candidate でどう違うか |
| 2 | 同じ run の `failures.jsonl` | `category` の件数。取りこぼしか、順位か |
| 3 | `slices.jsonl` | 言語・クエリ種別・カテゴリのどこに失敗が残っているか |
| 4 | `per_query.jsonl` の 1 位 | NDCG が良いクエリの 1 位は、本当に適合か |
| 5 | simulation run の `kpis.json` | 検索成功率と誤適合率は、baseline と candidate で同じ方向か |
| 6 | simulation の `failures.jsonl` | `simulation_miss` はどのクエリか。オフラインの `rerank_miss` と一致するか |
| 7 | release の `decision.json` | オフライン、holdout、二つのガードレールのどれで止まったか |
| 8 | release の `smoke.json` の `next_experiment` | 次に開く実験が、親と失敗 ID を持っているか |

`kpis.json` には分母がある。分母 0 の率は null であり、0 ではない。null を合格にしない。

## 失敗種別とディレクトリ

| stage | group | 学習で使う出力 |
|---|---|---|
| evaluation | `artifacts/runs/` | `metrics.json` `per_query.jsonl` `slices.jsonl` `failures.jsonl` |
| training | `artifacts/models/` | `feature_schema.json`（列の意味）`bundle.json`（どの分割でフィットしたか） |
| gate | `artifacts/experiments/` | `experiment.json` `decision.json`。ここはオフライン比較まで |
| simulation | `artifacts/runs/` | `kpis.json` `failures.jsonl` `impressions.jsonl` |
| release | `artifacts/releases/` | `decision.json` `smoke.json`。promote のときだけ `bundle.json` |

評価の `failures.jsonl` と simulation の `failures.jsonl` は別 run である。
前者は並びと候補の失敗、後者は提示の 1 位の失敗。両方を開いて、同じ `query_id` がどっちにいるかを見る。

## 読まないもの

- クリックを集計して、評価用の正解が自動で良くなったとは読まない。`promoted_to_evaluation_gt` は false のままである
- `active.json` が指している release を、実サービスの本番トラフィックとは読まない
- seed 三つが同じ点数であることを、分散が小さい証拠とは読まない。`repetition_signal` を見る
- 古い run を `prune` で消したあとも、active とその入力、rollback 先 1 本は残る。学習用に「前の失敗」を見るなら、消す前に失敗 ID と親実験を控える

## 契約を開くとき

手順の意味が成果物だけでは足りないときは、次だけ戻る。

| 詰まり | 正本 |
|---|---|
| 指標の定義、relevance、分母 | [05](../05_data_model.md) |
| なぜその関門で不採用か | [07](../07_test_strategy.md) |
| 切替と戻し | [08](../08_release_runbook.md) |
| なぜこの実験をしているか | [元メモ](../archive/search-quality-loop-brainstorm.md) の 0 章と 9 章 |
