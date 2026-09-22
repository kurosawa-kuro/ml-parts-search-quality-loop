# 05 データモデル

> 設計契約v1。**T1〜T8まで実装済み（2026-09-22）**。設定schema、foundation保存・検証、レコードvalidator、合成Catalog/Query/GT、検索・学習・指標・疑似オンラインevent/KPI・ReleaseBundleが実処理で通る。根拠は [参照レビュー](./reference-implementation-review.md)。

## 保存方式と識別

PoCはローカル成果物を正本とする。メタデータはUTF-8 JSON、行データはUTF-8 JSONLとし、大量データのParquet化は互換adapterとして後続対応する。全成果物にschema_versionを付ける。IDは空白を含まない文字列とし、異なるlocaleの外部IDは名前空間を付けて取り込む。

```text
artifacts/
  datasets/<dataset_id>/       catalog.jsonl, queries.jsonl, splits.json, manifest.json
  judgments/<gt_id>/           judgments.jsonl, manifest.json
  models/<model_id>/           model, feature_schema.json, manifest.json
  experiments/<experiment_id>/ experiment.json
  runs/<run_id>/              manifest.json, candidates.jsonl, results.jsonl,
                              outcomes.jsonl, metrics.json, per_query.jsonl,
                              slices.jsonl, events.jsonl, failures.jsonl
  releases/<release_id>/       manifest.json, decision.json, smoke.json
  active.json                 release_idとmanifest checksum
```

`artifacts/`はGit管理外。各manifestにID、schema_version、作成日時、code revision、dirty差分のdigest、依存lockのdigest、設定、seed、入力ID・checksum、出力path・checksum、実行状態を持たせる。未コミット実行の再現には差分patchも保存する。秘密情報はsnapshotへ含めない。indexはcatalog・embedding revision・前処理設定のchecksumから識別し、再構築できる派生成果物とする。

一時ディレクトリへ出力し、検証後に同一filesystem内でrenameして成功manifestを公開する。学習のlabel_gainもMetricPolicy v1の配列 `[0, 0, 1, 3, 7]` と一致させる。異なる目的関数の実験は別policyとして扱う。入力snapshotは不変。変更・再評価・再試行には新IDを払い出す。`retry_of` / `parent_experiment_id`で関係を残す。

## 最小レコード契約

| レコード | 必須項目と検証 |
|---|---|
| Product | product_id、category、model_number、texts（locale→title/description）、attributes。IDはcatalog内一意。manufacturer・価格・在庫等は利用時に追加 |
| Query | query_id、family_id、text、language、query_type、category、constraints。型番・寸法等の必須条件と任意条件を区別 |
| SplitManifest | split_id、family→train/tuning/holdout/production、生成seed、分割seed、件数、集合digest。family集合の交差は空 |
| Judgment | gt_id、query_id、product_id、status、relevance（judged時のみ0〜4）、source（rule/manual/implicit）、reason、rule_version、evidence_ids |
| Candidate | run_id、query_id、product_id、source、source_rank、score_type、raw_score、retrieval_config_id。query-product-source一意。統合後のCandidateSetは商品を重複排除しcandidate_rankを1始まりで付ける |
| SearchResult | run_id、query_id、product_id、rank（1始まり）、score、score_type、model_id（使用時）。query-product一意、rank連続、score有限 |
| QueryOutcome | run_id、query_id、status、returned_count、error_code（失敗時）、attempt、latency_ms。QuerySetの全queryにつき1件 |
| FeatureRow | query_id、product_id、schema_id、values、missing_mask、as_of。学習時のみlabel・label_source・gt_idを別列で結合 |
| FeatureSchema | schema_id、順序付きのname/type/default/null規約、変換版、正規化パラメータ。順序を含めchecksum化 |
| ModelBundle | model_id、学習データID、FeatureSchema checksum、trainer版・設定、label_gain、split_id、artifact checksum |
| Experiment | experiment_id、parent、仮説、dataset/queryset/gt/split/policy各ID、variants、seed、比較対象run。各variantがSearchConfigurationとmodelを固定 |
| Evaluation | evaluation_id、search_run_id、candidate_run_id、gt_id、metric_policy_id、比較signature、query別値・集計値・分母・coverage |
| FailureCase | failure_id、query_id、run_id、evidence_ids、category、説明、次のexperiment_id（着手時） |
| PromotionDecision | decision_id、baseline/candidate run、policy_id、比較値・分母・gate結果、decision、理由、release_id（採用時） |

数値属性は値とunitを分離し、寸法はmm等のカテゴリ別正規単位に揃える。元値も保存する。unknownはnullであり0と異なる。PoCの具体的な属性・許容差は末尾のT2契約を参照。

## GT policy v1

以下はESCIの転載ではなく、部品検索向けに選んだルール。判定順に適用する。

1. Queryの必須条件が矛盾する、または判定に必要な商品属性が欠ける場合はunrateable。
2. 明示された必須条件（寸法・適合等）を満たさない、または別カテゴリなら0。
3. 必須条件を満たし、要求型番と完全一致なら4。
4. カテゴリと要求寸法が一致するなら3（寸法指定がない場合はこの条件で昇格しない）。
5. カテゴリ・要求用途・要求材質が一致するなら2（指定と判定根拠がある場合）。
6. 必須条件に反しないが意味的関連だけなら1。それ以外は0。

旧メモの「仕様不一致でも1」は必須仕様違反を過大評価するため変更した。source=implicitは学習用の判定候補として保持し、独立評価用GTへ自動昇格しない。未クリックだけで不適合とは判定しない。GT snapshot内はquery-productごとに採用判定を1件に確定し、競合した元判定はevidenceとして保持する。業務上の代替許容条件・曖昧な自然文の扱いは商材ごとに決める。

評価対象カタログ全体へルールを適用した完全判定GTをPoCの正式評価に使う。未判定・判定不能が残るqueryは正式gateを止め、探索用集計とcoverageのみ出す。部分qrelsのRecallは「判定済み集合に対するRecall」と明示し、正式評価と比較しない。

## MetricPolicy v1

指標実装にはir_measuresを使う方針とし、versionとproviderを固定する。未対応policyを暗黙のdefaultで計算しない。以下は本PoCの選択であり、参照リポ共通のdefaultではない。

| 指標 | 定義 |
|---|---|
| NDCG@10 | gain mapping `{0:0, 1:0, 2:1, 3:3, 4:7}`、DCGはgain/log2(rank+1)。指数化を再度かけない |
| Recall@100 | CandidateSetの上位100件に含まれるrelevance>=2の商品数 / catalog内の全該当商品数 |
| MRR@100 | 最終順位100位以内の最初のrelevance>=2の逆順位をquery単位で計算し平均 |
| Judgment coverage | 返却済み上位100件中judgedの割合。0件は分母0としてnull。別途query判定完了率を記録 |
| 集計 | QuerySetを母集合にquery単位macro平均。Sliceごとに対象数・評価可能数・欠落数を併記 |

全件judgedで正解が存在しないqueryは`no_relevant`とし、上記3指標の平均から除外して件数を必ず報告する。これは不完全GTとは別。正解があるqueryで正常0件なら3指標とも0。failed / not_runはnullであり0にしない。1件でも残れば正式比較はinconclusive。空集合もnull。スコア同点はproduct_id昇順で固定する。

比較signatureにはcatalog / queryset / split / gt / metric policy / simulation policyのchecksumを含む。検索設定・モデル・Featureは比較対象差分として別記録する。rerankのみの比較はCandidateSetも固定する。GT更新時は同一SearchRunを共通の新GTで再評価できるが、catalog/queryset/検索処理変更時は再検索する。

## 疑似オンラインイベントとKPI

共通項目はevent_id、event_type、event_time、session_id、run_id、query_id、simulation_policy_id。impressionはimpression_id、順位付きitems、release_idを持つ。0件も空itemsで1回記録する。click / conversionはimpression_idとproduct_idを必須とし、提示された商品だけに結合する。reformulationは元impression_idとnext_query_idを持つ。

同一event_id・同一payloadは重複として除外。同一IDで異なるpayloadはエラー。遅延interactionはrunの観測窓内で結合し、期限後の未結合は隔離する。再集計は別runとし、確定済み指標を書き換えない。観測窓の長さ・クリック確率・位置バイアス・conversion確率は版付きSimulationPolicyへ明示し、未設定ならシミュレーションを開始しない。

| KPI | 定義（観測窓が閉じた正常impressionが母集合） |
|---|---|
| Search Success Rate | 最上位がGT relevance>=2のimpression割合。0件は失敗 |
| CTR | 1回以上clickがあったimpression割合。複数clickを重複計数しない |
| Zero Result Rate | itemsが空のimpression割合。別zero_result通知との二重計数をしない |
| Reformulation Rate | 観測窓内にreformulationがあったimpression割合 |
| Conversion | 観測窓内にconversionがあったimpression割合 |
| Wrong Fitment Rate | 最上位が必須条件違反の非空impression割合。補助指標として記録 |

失敗検索・未結合イベントは別件数で報告し、1件でもある正式比較はinconclusive。分母0はnull。baseline/candidateは同じquery・session割当・乱数streamで比較する。改善材料に使うdevelopment simulationと採否に使うproduction検証を区別する。

## 交換形式・設定・移行

TREC qrelsは `query_id 0 product_id relevance`、runは `query_id Q0 product_id rank score run_id`。交換scoreは確定順位から単調減少値を付け、元scoreはJSONLに保持する。空結果はrun行に表せないためoutcomesを必須sidecarとする。qrelsのordinalとgain変換はpolicyで明示し、再importで欠落を検知する。

一般設定は `env/config.yaml`。ローカル秘密はignoreされた `env/secret.yaml`、共有秘密はDoppler等。既存成果物を破壊せず、schema変更時は新schema_versionと新IDへ変換し旧版を保持する。未対応版は読み込み拒否。変更taskには移行・互換・rollback検証を記録する。

関連: [03](./03_domain_model.md) / [06](./06_error_policy.md) / [実装計画](./tasks/03_active/20260921-search-quality-poc-implementation.md)。

## ローカル初期設定

`env/project.yaml`はprojectNameと実repoRootの正本。`env/config.yaml`内の相対パスはrepoRoot基準とする。projectNameは論理名`parts-search-quality-loop`を保持し、ディレクトリ名`ml-parts-search-quality-loop`と区別する。

初期値はFA部品・JA/EN・10,000 SKU・1,000 QueryFamily、family分割はtrain/tuning/holdout/production = 60/15/15/10%。Qdrantはlocalhost:6333。これらはローカルPoCの初期選択で、実験開始時にsnapshotへ固定する。カテゴリ属性規約は末尾のT2契約、Embedding等の仮置き値はenv/config.yamlを参照。

設定loaderは実装済み。project/configのprojectName一致、未知キー拒否、工程ごとの必須null検査、secret参照キーの検証を行う。接続adapterは未実装で、実値の使用・環境変数からの注入は後続対応とする。secret全体をconfigへmergeせず、認証情報は接続adapterにだけ渡す。秘密情報を除いた有効設定をmanifestへ保存する。環境変数overrideは現在未提供。

`split.seed`はfamilyの割当、`generationSeeds`は分割後の生成用。翻訳・派生を作る前にfamilyを分割し、seedの違いだけで独立性を保証しない。言語ごとの行数はfamily数と異なる。

qualityGateのnullは採用判定不可、simulation.enabled=falseはsimulation未実施を意味する。合格や指標0へ置き換えない。release.requireAcceptedDecisionは候補昇格に適用し、初回Baselineのbootstrapは08の別手順に従う。

## Foundation runの実装範囲

bootstrapのmanifestはschema_version、run_id、created_at、status、outputs（ファイル名→sha256）、metadataを持つ。metadataにはfoundation種別・code revision・dirty状態・ソース/lock checksum・Python/依存versionを記録する。出力は公開config.jsonとreadiness.json。secretは自動読込しない。

同一run_idのwriter予約と一時ディレクトリからのrenameで公開し、既存runは置換しない。通常例外は一時出力を片付ける。強制終了後に残った隠しlock/stagingは自動削除せず、writerが終了したことを確認して個別復旧する。検証は出力inventoryとchecksumを照合するもので、署名・改ざん防止機構ではない。未コミットコードのpatch保存・完全な再実行復元・モデルbundleは後続対応。

## T2 合成入力と完全判定GT（実装）

`fa_parts_attr_v1` は実商品の適合規約ではなくPoC用の仮置き。軸（shaft）、軸受
（bearing）、ボルト（bolt）をほぼ均等に生成する。全カテゴリで diameter / length、
material / standard / usage を持つ。寸法はmmへ正規化し、`original: {value, unit}`に
元値を残す。mm/cm/m/inに対応、1 in=25.4 mm。点指定の一致許容差は0.01 mm
（浮動小数比較の補助許容差1e-9 mm）。材質・規格・用途は文字列の完全一致。
`SYN-<CATEGORY>-V1`は架空規格である。

`constraints`は`required`/`optional`の辞書。寸法は`{value, unit}`または閉区間
`{min, max, unit}`で表す。区間指定には点指定の0.01mmを追加しない。
型番・カテゴリ・材質・規格・用途は文字列。未知の条件名や単位は拒否し、黙って無視しない。
必要な条件値または商品属性がnull/欠落ならunrateable。逆転区間や、必須カテゴリと
Queryカテゴリの矛盾もunrateable。欠損・矛盾を判定した後、必須違反を型番一致より
先に判定する。任意条件の不一致だけでは0へ落とさない。意味的関連の仮置きは
「同一カテゴリ」であり、別カテゴリの代替は認めない。

QueryFamilyは寸法組が一意な商品から重複なしで意図を選ぶ。SKU数よりfamily数が
多い設定は拒否する。familyをsplit.seedでshuffleし、最大剰余法で比率の端数を配分
（同率はsplit名昇順）。翻訳・表層変形より先に割当を確定する。
queries.generationSeedで意図を選び、split.generationSeedsで単位表記・文章の表層を
変える。1 familyに1 query typeを設定順に循環割当し、各設定言語につき1 Queryを作る。
自然文は構造化条件と一緒に生成するテンプレート文で、任意の自然文を解析する機能はない。
型番Queryは型番を希望条件、型番/寸法Queryは寸法を必須、自然文Queryは寸法を希望とする。
全Queryに必須規格と希望材質・用途を持つ。条件はすべて検索文にも表示する。

family→split対応は全familyをちょうど一度含む辞書。許可split、件数、集合digest、
Queryのfamily網羅、同family内の翻訳条件一致を検査する。単位正規化後に同じ条件を
持つ別familyも拒否し、query typeや言語だけ変えた同一意図の分割漏洩を防ぐ。
GT ID、rule ID、生成元商品ID、labelはQuery/商品入力へ保存しない。

`stage catalog`はcatalog.jsonl / queries.jsonl / splits.jsonを公開する。
manifest.metadataに生成設定（全seedを含む）、属性policy、件数、集合digest、
内容に基づくdataset_id / queryset_id / split_idを持つ。run_idは公開ごとに新規で、
同一設定なら行ID・split・内容ID・出力checksumは一致する。

`stage judgments --dataset <artifact>`は既存datasetのmanifest版・checksum・入力契約を
検査し、CatalogとQueryを`read_records`で読み直す。全直積をquery_id/product_id順に
書き出す。gt_idは入力内容とpolicyから決定し、GT manifestには入力のrun_id、内容ID、
manifest/output checksumを残す。判定不能もrelevance=nullの行として保持する。
summary.jsonにexpected_rows / rows / judged / unrateable / complete_queries /
no_relevant_queries / relevance_countsを持ち、判定不能が残る場合のstatusはinconclusive。
段階のcompletedは生成完了であり、正式評価の合格を意味しない。

既定規模は10,000 SKU・1,000 family・2,000 Query、GTは2,000万行。
GTはquery単位のバッファで検査・書出し、全GTのlist/bytesを保持しない。
storeのSHA-256生成と公開前checksum照合もストリーム処理。一時出力中に例外が起きた
runは公開せず、既存runを置換しない。GT読込は`records.io.iter_judgments(artifact)`を使い、
版/checksum、行契約、batchを跨ぐID順序・一意性、最終行数を検査する。最後まで消費して
検証を完了する。通常`read_records`の256 MiB上限は保持する。

未コミットソースの記録は既存foundationと同じrevision・dirty・source/lock checksumまで。
patchの自動保存・完全なコード復元は未実装であり、再現実行には同じソースとlockを保持する。

## T3〜T6の実装契約（2026-09-22）

- `parts_e5_v1`: NFKC、ハイフン統一、型番英字大文字、query/passage prefix。JA/EN商品文を結合し固定revision E5で正規化vector化する。exact cosine検索、同点はproduct_id昇順。index_idはcatalog checksumとembedding設定に依存し、実collectionはrunごとに独立する。
- `parts_features_v1`: vector_score, model_exact, category_exact, diameter_delta, length_delta, material_exact, standard_exact, usage_exactの8列。寸法差はmm、条件rangeは中点との差。欠損はJSON null＋missing_mask、LightGBM入力ではNaN。列順・default・変換版・checksumを保存し再読込時に照合する。
- 学習labelはtrain splitのみ使用。GT rule_idやlabelを推論Featureに含めない。ModelBundleはモデル、FeatureSchema、label_gainと入力checksumへ紐付く。
- 比較signatureはdataset/GT/metric/simulation設定に依存。candidate checksum一致とseed [11,22,33]を追加検査。gateはoffline_verdictだけを確定させ、**正式decisionはrelease段階（独立holdout＋simulation guardrail）で確定**する。gate単体のdecisionはinconclusiveのままにする。
- seed反復は**指標の分散を示すとは限らない**。gateは`seed_metric_spread`と`repetition_signal`を出し、trainerが決定的なら`no_metric_variance_across_seeds`と明示する。
