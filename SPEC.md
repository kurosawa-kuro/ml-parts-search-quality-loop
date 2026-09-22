# T3〜T6を連続実装し、最後にまとめて検証する

ユーザー指示: 可能な限り実装を進める。工程ごとの大規模検証は最後へまとめる。

- T3: 固定E5・Qdrant実検索、index識別、Candidate/Result/Outcome、失敗保持。
- T4: 完全GTをquery単位でストリーム評価、ir_measures、Slice/FailureCase。
- T5: 明示FeatureSchema、trainだけでLambdaRank、同一候補でrerank、モデル保存再読込。
- T6: 同一signature・分母・slice・反復seedを検査し、品質判定を保存。
- 接続: CLIの入力artifactを明示し、pipelineで依存を受け渡す。
- 実装箇所: pipelines/{inputs,retrieval,evaluation,training,gate}.py、stage/CLI、tests、関連docs。
- 方針: 既存dataset/GTを再利用し、大規模GTの再生成を検証のたびに行わない。
- 検証: 最後にfmt/lint/test/build、実Qdrant+固定E5の小規模一貫実行。
- 境界: productionのrelease切替や品質合格は未検証のまま宣言しない。

実行結果: T3〜T5完了、T6 offline比較実装。131 tests・lint・build成功。実pipeline接続21.16秒。T6系譜/品質終了コードとT7/T8が残る。大規模ML検証は未実施。
