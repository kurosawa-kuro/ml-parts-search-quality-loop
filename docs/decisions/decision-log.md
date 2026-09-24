# Decision Log（判断日誌 / trade journal）

AI エージェント（と人間）が**実行中に下した判断**を時系列で残す append-only の日誌。
トレードで言う「売買日誌」に当たる: 何を・なぜそのサイズで賭けたか、損切りラインはどこか、結果はどうだったか。

## これは何で、ADR / task note と何が違うか

| | レンズ | 寿命 | 例 |
|---|---|---|---|
| `adr/` | **戦略** = アーキ決定（正本） | 長命 | 「runtime state はどこに置くか」 |
| `tasks/` | **個別建玉メモ** = 1タスクの作業記憶 | タスク中 | このタスクの Goal/Scope/証拠 |
| `decisions/`（ここ） | **売買日誌** = 通時の判断の振る舞い | 永続・追記専用 | 「曖昧 Goal にこの既定値で突っ込んだ」「scope外をdeferした」 |

task note は1タスクに閉じるので「最近このエージェントは曖昧スペックにフルレバで入りがち」といった**通時のレビュー**ができない。この日誌はそこを埋める。

## 運用ルール

- **append-only**。過去エントリは書き換えない。結果が後で判明したら `結果` 行だけ追記更新してよい。
- 新しいエントリは**末尾に足す**（古い順・上から下）。
- `--- session boundary <ts> ---` 行はセッション終了時に Stop hook が自動で挿入する。判断ゼロのセッションでは挿入されない。
- 何を書くかの引き金と手順は `.claude/skills/log-decision/` が正本。
- **secret・トークン・cookie・個人パス・実データを書かない**（`.claude/rules/security.md`）。判断の構造だけ残す。

## エントリ形式

```markdown
## <UTCタイムスタンプ> — <判断の一行要約>
- type: default-taken | scope-cut | approach-choice | rollback | risk-accepted | approval-deferred
- 根拠 (why): なぜこの判断か（＝建玉理由 / entry thesis）
- 影響範囲 (blast radius): 何が壊れうるか・可逆性（＝レバ/ロットサイズ）
- 撤退条件 (stop/revert): 何が起きたら戻すか・どう戻すか（＝損切りライン）
- 結果 (outcome): win | loss | open | 塩漬け（後追い更新可）
- link: task note / ADR / PR（任意）
```

---

_まだ判断は記録されていません。`log-decision` が末尾に追記します。_


## 2026-09-22T00:40Z — .gitignore の非アンカー `artifacts/` がソースを飲んでいた事故を修正し、同名衝突を改名で封じた
- type: rollback
- 根拠 (why): owner「パスが冗長というか、重複バグ問題」。調査すると `.gitignore` の素の `artifacts/` が成果物ディレクトリだけでなくソースモジュール `src/.../artifacts/` にも当たり、run 公開・検証の中核 store.py が git から欠落。git archive 相当で `ModuleNotFoundError: parts_search_quality_loop.artifacts` を実測。パターンを `/artifacts/` へアンカーし、衝突源のモジュールを `runstore.py` へ平坦化・改名して同種事故を名前で封じた。
- 影響範囲 (blast radius): 新規 clone が import 不能という致命的欠落だった。パッケージも `parts_search_quality_loop` → `parts_search`（CLI 名と一致、repo 名の繰り返しを除去）へ改名し 13 ファイルの参照を更新。git 管理下なので可逆。
- 撤退条件 (stop/revert): 改名で外部参照が壊れる場合は revert（配布前・利用者ゼロのため影響なしと判断）。
- 結果 (outcome): win
- link: tests/test_tooling.py

## 2026-09-22T00:45Z — テスト runner を unittest から pytest へ移した（様式ではなく契約が要求）
- type: approach-choice
- 根拠 (why): owner「論理的に適切な選択でテストを整備せよ」。07_test_strategy は実 engine での結合テストを要求し、rules/tests.md は「実接続テストは明示マークで分け既定の make test から外す」と定める。**unittest に marker 機構が無くこの分離が実装できない**ため、pytest は要求を満たす唯一の選択。既存 TestCase は pytest がそのまま実行するので期待値の書き換えは不要（弱めていない）。
- 影響範囲 (blast radius): Makefile の test ターゲットと dev 依存。既存 34 テストの期待値は不変。marker 設定だけでは分離の保証にならないため、分離が効いていること自体を test_tooling.py で検査。
- 撤退条件 (stop/revert): pytest 固有機能に依存した箇所は無いので unittest へ戻せる。
- 結果 (outcome): win
- link: docs/07_test_strategy.md


## 2026-09-22T01:00Z — Embedding 実行ライブラリを実測し、自分の推奨（fastembed 第一候補 / multilingual-e5-small）を撤回
- type: rollback
- 根拠 (why): owner「問題発覚時点でつぶしなさい」。revision 固定可否を「T3 着手時に実測」と先送りしたのが誤り。両候補を実際に導入して確認した結果、fastembed 0.8.0 は `revision` param を持たず、`multilingual-e5-small` もレジストリに無い（`multilingual-e5-large` 1024dim/2.24GB のみ）。05 の「index は embedding revision の checksum から識別」を実装できない。sentence-transformers 3.0.1 は `revision` / `local_files_only` を持ち契約を満たす。
- 影響範囲 (blast radius): T3 の実装前提。先送りしたまま fastembed で実装したら、index 同一性の契約を破った状態が後から発覚し、再現性の根拠が崩れていた。torch 依存を受け入れる判断が新たに要る。
- 撤退条件 (stop/revert): owner が軽さを優先して fastembed を採るなら、05 の revision 契約を「fastembed バージョン + モデル名」へ緩める改訂が必要。契約を黙って破らない。
- 結果 (outcome): open
- link: docs/tasks/02_backlog/20260921-search-quality-poc-decisions.md


## 2026-09-22T01:30Z — 未決事項を全部「論理的に妥当な仮置き」で確定させ、blocked を 8/9 -> 1/9 にした
- type: default-taken
- 根拠 (why): owner「どうせ実測しないとわからないから一旦論理的に正しそうな選択肢で仮置きしか不可能では。当たり前の事になぜコストかけて止まってる」。正しい。最適値は実データで動かすまで決まらないので、既定を置いて進める方が情報が早く手に入る。owner 判断を待つ形にしていたのが誤り。
- 影響範囲 (blast radius): env/config.yaml の 13 項目。すべて設定値なので後から変更可能。品質 Gate のしきい値（NDCG +0.01 等）は baseline 測定後に必ず見直す前提。
- 撤退条件 (stop/revert): 実測後に閾値・policy を上書きする。仮置きであることを decisions doc に明記した。
- 結果 (outcome): win
- link: docs/tasks/02_backlog/20260921-search-quality-poc-decisions.md

## 2026-09-22T01:35Z — 依存を実導入し、制約の連鎖（x86_64 -> torch 2.2.2 -> numpy<2 -> Python<3.13）を確定
- type: risk-accepted
- 根拠 (why): 依存追加を「T3 実装時に」と先送りしていたのも誤り。実際に入れたところ (1) numpy 2.x + torch 2.2.2 が RuntimeError (2) qdrant-client が Python 3.14 で numpy>=2.3 を要求して lock 解決不能 (3) lightgbm が libomp 不在で dlopen 失敗、の 3 件が判明。いずれも後の工程で必ず踏む。
- 影響範囲 (blast radius): requires-python を >=3.11,<3.13 へ狭めた。numpy<2 が全体制約になり、今後のライブラリ選定がこれに縛られる。torch でインストールは重くなる。
- 撤退条件 (stop/revert): arm64 Mac へ移れば torch の上限が外れ制約が緩む。その時に requires-python と numpy を見直す。
- 結果 (outcome): win
- link: pyproject.toml

## 2026-09-22 — T2の商材仮置きと完全GTのストリーム処理

- 判断: `fa_parts_attr_v1`を架空shaft/bearing/bolt、共通寸法・材質・規格・用途で具体化。
  寸法はmm、点指定許容差0.01mm。実商品ではないこと、同一カテゴリを意味的関連とする
  仮置き、必須条件を満たす場合だけ代替を認めることを05へ記録。
- 根拠: 前回のowner方針「仮置きで進め実測後に調整」に従う。Queryは構造化条件と
  JA/EN文を同時に生成し、未実装の自然言語解析にGTの成立を依存させない。
- 分割: familyを先に固定して翻訳を生成。同じ条件の別familyは、単位正規化後に検出して拒否。
  1 familyごとに各言語1 Query。IDは公開runと内容IDを分け、再生成の同一性と不変公開を両立。
- 大規模処理: 既定GTは2,000万行。負例の省略やサンプリングは完全判定契約を破るため、
  query単位の検査とJSONL逐次書込・checksumを採用。入力snapshotから別工程で判定し、
  正解ID・rule IDを検索入力へ入れない。
- 調整条件: 実商品の適合規約や分布を導入する際は新policyとして固定し、同じ版の意味を
  後付けで変更しない。T3以降の品質改善効果は今回の生成完了とは別に検証する。

## 2026-09-22 seed 反復を「頑健性の証拠」と表示しない

- 判断: gate が `seed_metric_spread` と `repetition_signal` を出力する。現在の trainer 構成
  （`deterministic: true`・bagging/feature subsample 無し）では seed が指標を動かさないため、
  `no_metric_variance_across_seeds` と明示する。
- 根拠: 実測で seed [11,22,33] の model checksum は異なるのに NDCG@10 が小数9桁まで一致した。
  「3 seed 通った」を分散の小ささと読むと誤る。反証可能な形で事実を出す方を選ぶ。
- 非対象: trainer へ乱択（bagging 等）を入れて分散を作ること。品質そのものが動くため別判断。
  品質閾値も変更しない。
- 調整条件: trainer 構成に乱択を入れる判断をしたときは、repetition の意味を再定義してから
  `repetitionSeeds` の扱いを決める。

## 2026-09-24 GTは全行を残し、gzipで保存する（0行の畳み込みは採らない）

- 判断: `judgments.jsonl` を `judgments.jsonl.gz` にする。行の意味・件数・順序・検証は変えない。
  「relevance>0 と unrateable だけを行にし、0 は判定済み集合＋例外リストで表す」sparse 案は採らない。
- 実測（2,000万行・4.61 GiB の実artifact）: relevance分布は 0=17,778,676 / 1=1,480,474 /
  2=738,850 / 3=1,332 / 4=668、unrateable=0。sparse なら残るのは 11.1%（約 540 MB）。
  同じデータの gzip は 96.75 MB → 1.366 MB（**70.8倍**、level 6）で、全体で約 68 MB になる。
  圧縮の書込は 240 MB/s・40万行の読み戻しは 0.1 s なので、実行時間には現れない。
- 根拠: sparse は容量で gzip に負けたうえ、失うものが 2 つある。(1) 完全判定の検証が
  「ファイルから行数・ID順序・一意性を確認する」形から「エンコーディングの宣言を信じる」形へ
  落ちる。(2) 0 行の `reason`（mandatory_violation / category_mismatch / unrelated）が
  集計値に潰れ、GT policy の誤りを行単位で追えなくなる。容量が同じなら検証を残す方を選ぶ。
- 実装: `runstore` は `.jsonl.gz` を gzip streaming で書き、checksum は**書いたバイト列**から取る
  （書き戻して取ると `verify_run` が同一バイト列同士の比較になり、切断を検出できない）。
  `mtime=0` で内容が同じなら同一 checksum。`records.io.iter_jsonl` は `.gz` を透過展開する。
- 調整条件: gzip でも足りない規模（例: catalog 10万 SKU で GT 20億行）になったら、
  sparse ではなく Parquet + 列圧縮へ進む。sparse 案は以降検討しない。
