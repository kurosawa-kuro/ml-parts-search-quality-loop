# CLAUDE.md

このファイルは Claude Code がこのリポジトリで作業する際の最小ガイド。

## Source of Truth

- Project overview: `README.md`
- Documentation index: `docs/00_index.md`
- Requirements: `docs/01_requirements.md`
- Architecture: `docs/02_architecture.md`
- Test strategy: `docs/07_test_strategy.md`
- Harness 全体像: `.claude/README.md`（このリポジトリの AI 制御一式）
- Harness アーキ本体: `docs/specs/kurosawa-thin-harness-architecture.md`（tool-agnostic マスター）＋ repo 固有 instantiation（`docs/specs/{runtime-protocol,capability-boundary,change-boundary,evidence-policy,judgment-memory}.md`）
- 判断日誌 / 蒸留記憶: `docs/decisions/decision-log.md` / `docs/memory/`
- Feature spec（実装前・1 機能ごと）: `SPEC.md`
- Task notes: `docs/tasks/`

**spec の使い分け（混同しない）**: `SPEC.md` = 今から作る 1 機能の使い捨て実装スペック（公式 Explore→Plan→Implement→Commit の入口、新セッションで実行）。`docs/specs/` = 恒久アーキ設計マスター。`docs/tasks/` = タスク台帳。

## コマンド

```bash
make setup        # uv.lockから.venvへ依存導入
make config-check # foundation設定検証
make run          # foundation run作成。検索・学習は実行しない
make dev          # make runと同じ。開発サーバーではない
make stages       # Golden Path 9段階と依存設定の一覧
make pipeline     # 9段階を実行。exit 2=blocked / 4=品質不採用
make test         # pytest。単体・CLI結合のみ（integration markerを除外）
make test-all     # integration markerも実行（実E5/Qdrantが要る）
make fmt          # Ruff import修正・format
make lint         # Ruff lint・format check
make build        # wheel / sdist build
```

現在のCLIは`config-check`、`bootstrap`、`verify-artifact`、`stages`、`stage`、`pipeline`、`activate`、`rollback`。
**Golden Path 9段階すべてが実処理**（contracts / catalog / judgments / retrieval / evaluation / training / gate / simulation / release）。

**終了コード**: 0=完了 / 1=実行エラー / 2=設定未確定で停止 / 3=骨組みのみ / **4=実行成功だが品質不採用**。
**2・3・4を成功と読み替えない。4と1を混同しない**（4は品質、1は実行の失敗）。

## 現在地

- 実装済み: T1〜T8の実処理。設定loader/schema、工程別blocker、成果物store、checksum、原子的run公開、契約validator＋手書きfixture、合成Catalog/Query/完全GT、E5+Qdrant検索、評価・Slice・FailureCase、構造化Feature＋LambdaRank、凍結Gate比較、**疑似オンラインsimulation（版付きpolicy・paired stream・KPI・GT候補）**、**独立評価→ReleaseBundle→active原子切替→rollback**。
- 段階状態（2026-09-22、CLI pipelineで実測）: 9段階すべて`completed`。小規模データではslice件数不足で`quality=inconclusive`（exit 4）。**採用されていないことを実行失敗と読み替えない。**
- 品質閾値は凍結値。**acceptedを得るために閾値を下げない**（下げるのはNon-scope）。
- 依存の制約: **`numpy<2` / Python`<3.13`**（x86_64 mac -> torch 2.2.2 -> numpy<2 -> Python<3.13 の連鎖）。LightGBMは`brew install libomp`が必要。
- 実装順: [マスタータスク](docs/tasks/03_active/20260921-search-quality-poc-implementation.md)のT1〜T8。
- 設定済み項目と後続の具体化・検証: [判断・設定台帳](docs/tasks/02_backlog/20260921-search-quality-poc-decisions.md)。未決値で正式評価を成功させない。

## アーキテクチャ

- ソースは `src/parts_search/` 配下に置く（import名は`parts_search`。CLI名`parts-search`と一致）。
- **`.gitignore`のパターンはアンカーする**（`/artifacts/`）。素の`artifacts/`は同名のソースモジュールにも当たり、`src`配下のコードをgitから消した実害がある（2026-09-22）。`tests/test_tooling.py`が退行を検査する。
- 非機密の設定は `env/config.yaml`、ローカル秘密情報は `env/secret.yaml`、チーム共有・本番クレデンシャルは Doppler (`doppler.yaml`) で管理する。
- 設計・運用ドキュメントは `docs/` 配下。権威順位と更新規約は `docs/00_index.md` に従う。
- パス別ルールは `.claude/rules/` 配下に置く。
- 一回性の作業計画は `docs/tasks/`、繰り返し使う作業手順は `.claude/skills/` に置く。

## 作業ルール

- 作業開始時に`pwd`と`git rev-parse --show-toplevel`を実行し、両方が`/Users/kurosawa/Dev/ml-parts-search-quality-loop`を指すことを確認する。会話の直前まで扱っていた別リポジトリを優先しない。
- ユーザーがフルパスを指定した場合、そのパスを最優先の作業対象とし、書き込み前後に変更パスを検査する。
- 推測でコードを書かない。コマンドを書いたら実際に実行して確認する。
- 仕様変更は連動する `docs/` とテストを同一 PR で直す。drift を作らない。
- 既存の関数・ユーティリティ・パターンを優先的に再利用する。
- task note を仕様の正本にしない。確定内容は `docs/specs/`、`docs/adr/`、`docs/runbooks/` に昇格する。
- **Scope invariant（常時）**: 作業中に Goal/Scope 外の変更・前提崩れ・追加副作用・docs と実装の矛盾を見つけたら即実装しない。`control-change` で分類するか follow-up task に残す。「ついで修正/共通化/改名」は scope creep。

## AI Runtime Protocol（薄い・常時）

Thin Harness の常時手順。詳細は `.claude/README.md` と `docs/specs/runtime-protocol.md`、停止条件は同 §「停止して owner に確認する」。

> **このハーネスは重い既定で出荷されている。** 新規生成直後は、まず skill `harness-trim` を1回回し、このプロジェクトの脅威モデルに合わせて hooks / rules / permissions / agents / skills を keep・delete・adjust する（削除は想定手順で scope creep ではない）。以降は下記の常時手順に従う。

1. Goal / Scope / Done を言い直す。
2. Weight Class を判定（Light / Standard / Heavy → `classify-task`）。Light は以降の重い手順をスキップしてよい。
3. owner-only 判断・保護 capability・allowed/forbidden paths を確認（`scan-decisions` / `capability-boundary.md` / `change-boundary.md`）。
4. Standard/Heavy の新機能は **plan モードで探索（編集せず読む）→ `SPEC.md` を自己完結で記述（触るファイル/IF 名指し・Non-scope・末尾 E2E 検証）→ 可能なら新セッションで実行**。その後 skeleton + TDD contract を先に固める（`plan-skeleton`）。
5. scope 内で最小変更を当てる。複数 attempt が要るなら停止条件付きで回す（`reconcile-task`）。
6. 必要 Evidence Level（≥2、本番は4）で検証（`verify-completion` / `evidence-policy.md`）。
7. scope 拡大・保護境界接触・二度違う理由で検証失敗 → 停止して owner へ。
8. 非自明な判断を下した時だけ記録（`log-decision`）。

## Taskの開始点

T1は基盤完了（`docs/tasks/05_done/`に証跡。未作成の正常fixtureはT3〜T6へ移管）。T2も実装済み。次はT3 [Vector Baseline検索とSearchRun](docs/tasks/02_backlog/2026-09-22-VectorBaseline検索とSearchRun.md)。各taskを`03_active`へ物理移動してから着手し、依存taskを飛ばさない。

T2以降はmanifestの版を検査し、`records`の`read_records`を通す。大規模GTは版/checksum/行契約付き`iter_judgments`を使う。各工程が自前で`json.load`すると、schema_version検査が抜けた経路が1本できる。
