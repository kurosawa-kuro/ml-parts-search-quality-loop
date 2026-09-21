# 07 テスト戦略

> foundation・T1契約・T2生成/GT/分割/ストリームのテストを実装済み。検索・学習・品質指標テストは後続工程。

## 現在の品質ゲート

```bash
make fmt lint test build
git diff --check
```

runnerは**pytest**。既存のテストは`unittest.TestCase`のままpytestが実行する（期待値は変えていない）。

pytestを選ぶ理由は様式ではなく契約である。本文書は「選定した検索engineのローカル実体で結合テストを行う」と定め、[テストルール](../.claude/rules/tests.md)は「実接続テストは明示マークで分け、既定の`make test`から外す」と定める。**unittestにmarker機構は無く、この分離を実装できない。**

| コマンド | 対象 |
|---|---|
| `make test` | 単体・CLI結合のみ（`-m 'not integration'`） |
| `make test-all` | `integration` markerを含む全件（ローカルサービスが必要） |

`--strict-markers`により綴り違いのmarkerは静かに無視されず失敗する。marker分離が実際に効いていること自体を`tests/test_tooling.py`が検査する（設定を書いただけでは保証にならない）。

検証範囲: YAML未知キー/重複・比率・cutoff・gain不整合・パス逸脱・秘密非漏洩・JSON/JSONL保存・原子的公開・上書き拒否・改変検出・CLI実行・Golden Path骨組みの段階定義と終了コード・パッケージレイアウトの退行。Ruffで整形とlint、uv buildで配布物を検証する。**実Qdrant・学習・指標・ReleaseBundleのテストを通したという意味ではない**（`make test-all`は現在T3未実装で失敗する。これが正しい状態）。

## 実装時のテスト契約

| 層 | 検証する失敗・性質 | 対応要件 |
|---|---|---|
| schema / GT | 必須寸法違反が型番一致より優先、欠損は判定不能、0とnullの区別、単位変換、重複ID拒否 | AC-001, 008 |
| 分割 / 時点 | 同じfamilyの翻訳・派生が分割を跨がない、未来interactionをFeatureへ入れない | AC-005, 009 |
| Retrieval | 実adapterでindex作成・検索、取得漏れとrerank不良の切り分け、0件とtimeout | AC-002, 006, 008 |
| Feature / model | 学習と推論のFeature一致、順序入替・欠損・schema変更の拒否、query group境界 | AC-009 |
| 指標 | 手計算fixtureとir_measuresの一致、gain二重適用防止、未判定・no_relevant・空run | AC-002, 011 |
| event | 重複の無害化、同一ID競合、遅着、提示外click、0件の二重計数防止 | AC-004, 008 |
| 比較 | signature不一致拒否、全QuerySet起点、Slice分母、null・coverageの扱い | AC-003, 008, 011 |
| 成果物 / release | 一時書込中断、checksum不一致、旧bundle復帰、schema不一致rollback拒否 | AC-001, 010 |
| E2E | prepareから失敗検知・学習・独立評価・採否・次の実験まで1周 | AC-001〜011 |

mockだけでadapterが動くとは扱わない。選定した検索engineのローカル実体で結合テストを行う。小さな手書きfixtureは合成生成器と独立に作り、生成ルールのバグを同じルールで検証しない。

## 指標の手計算fixture

GTをA=4、B=3、C=0、結果をB,C,Aとする。05のgainは7,3,0なので:

- DCG@10 = 3 + 7/log2(4) = 6.5。
- IDCG@10 = 7 + 3/log2(3)。NDCG@10はその比。
- Recall@100 = 1、RR@100 = 1。
- 追加ケースとして結果C,A,BではRR@100=1/2。
- 正解があるのに正常0件なら全指標0。実行失敗なら値nullでinconclusive。
- 全商品0の完全GTならno_relevant。未判定があるケースとは別に扱う。

数値許容誤差は固定環境で絶対誤差1e-9を基準とし、provider変更時は同fixtureで検証する。モデルの浮動小数再現性は別途許容差を宣言し、同点時の順位規約は固定する。

## 品質の採否ゲート

実行成功とモデル採用を分ける。比較前にGatePolicyを凍結し、baseline/candidate両者へ適用する。

必須条件:

1. schema・checksum・split・Feature互換・比較signatureがすべて一致する。
2. 全queryのoutcomeがあり、failed / not_runが0。評価GTは完全判定かつ指標を計算できるqueryが1件以上ある。イベント結合と観測窓も完了している。
3. NDCG@10を主指標とし、Recall@100・MRR@100・言語/Query Type Sliceをguardrailとする。疑似オンラインではSearch Success RateとWrong Fitment Rateを確認し、CTR等も報告する。
4. `min_ndcg_delta`、各guardrailの`max_regression`、`min_slice_queries`、必要な反復seed数を実験前に設定する。値は商材・初期分布とBaseline確認後に決め、candidateを見て変更しない。
5. 最小改善量を満たしguardrailに違反しなければaccepted。完全な比較で違反したらrejected。設定不足・件数不足・未判定・実行障害はinconclusive。

query単位の差分、平均、Slice件数、反復seedごとの値を保存する。平均の改善だけから統計的有意差・実オンライン効果は主張しない。小さい固定fixtureで動作を確かめるテストと、10,000〜50,000 SKUのPoC効果検証は別に記録する。

## 完了証跡

taskには実コマンド、入力manifest、結果、失敗理由、未検証範囲を残す。E2Eの最終成果物は比較結果・採否・ReleaseBundle・smoke・次のexperimentへの関係。モデル改善しなかった事実も保持する。品質改善を示すPoCの完了には、独立検証でacceptedとなった改善例が必要。

関連: [01](./01_requirements.md) / [05](./05_data_model.md) / [08](./08_release_runbook.md) / [実装計画](./tasks/02_backlog/20260921-search-quality-poc-implementation.md)。

T2は`tests/test_synthetic.py`で独立GT例、family漏洩、単位、保存済み全直積、ストリームの中断/重複/版拒否を検査する。既定規模の2,000万行生成と読戻しは通常テストから分離し、T2 taskへ実測を記録する。
