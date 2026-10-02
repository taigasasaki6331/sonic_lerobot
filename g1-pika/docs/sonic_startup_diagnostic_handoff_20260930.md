# Codex向け引継ぎ: SONIC出力契約レビューと起動履歴診断（2026-09-30）

## 受け取ったCodexへ

ユーザーの依頼により、別作業として完了した読み取り専用レビューと保存入力診断の結果を渡す資料です。既存Codex会話への投稿はしていません。実装の修正や追加実験を依頼・承認する文書ではありません。まず現行AGENTS.mdとdocs/HANDOFF.mdを読み、以下の結果を現在の検討へ取り込んでください。

今回の資料作成では、既存実装・AGENTS・HANDOFFは変更せず、この新規Markdownだけをプロジェクト内へ追加しました。Gitには既存の変更・未追跡ファイルが多数あり、ユーザー側の作業を保持しています。

### 最新作業との時点差

資料作成時に `/home/developer/workspaces/g1_pika_ws/AGENTS.md`、本repoのAGENTS.mdとdocs/HANDOFF.mdを再読しました。診断終了後、別CodexによりACT policy bundleの固定・照合・共有と、run-w2r_5_nu / run-ssy2zdrv / run-ck4k0eu8（最大30秒）の記録経路検証が追記されています。これらは既に完了した作業として扱い、SONIC目標差の解消や身体制御の合格と混同しません。

関節参照補間とフレーム間極値監査も既に実装・検証されています。本診断は既定のIK終点保持を固定しており、新しい補間を未実装と扱いません。

診断中のSHA照合では関連コード・文書の変更0でした。**資料作成時との再照合ではAGENTS.mdとdocs/HANDOFF.mdだけ更新され、記録したSONIC関連コード・上流ソース・URDF・元reportのSHAは一致**しています。この時点差は保存済み数値を変えません。将来コードやモデルが変わった場合は、以下を診断時点の結果として扱ってください。現在の実機状態や停止手段は今回確認していません。

## 独立レビューで確認した出力契約

LeRobotの局所相対TCP action（位置3＋回転6D columns＋幅1）から再利用IKで作る29関節参照を、SONIC mode 0の参照入力へ渡します。PIKA幅は別経路です。公式VLAの78次元actionやDex3ハンド指令と互換として扱いません。

- encoderは1247要素。mode scalar 0＋padding3、10×29の絶対参照q、10×29の参照dq、10×6の相対姿勢表現を使用し、他モードの領域は0。本条件はheading offset=0、上半身overrideなしです。
- decoderはtoken64＋履歴930＝994要素。履歴の順番はgyro30、(q−default)290、dq290、raw action290、gravity30。各履歴は古い→新しい順です。
- 観測q/dqはhardware順からIsaacLab順へ変換。action履歴はIsaacLab順のraw decoder出力です。最終目標は `raw_action[isaaclab_to_mujoco[i]] * g1_action_scale[i] + default_angles[i]` です。この配列順・scale・default変換に確定した不一致はありません。
- 上流LoggerはCONTROL開始後に身体と直前actionを記録し、不足履歴はzeroEntryで補います。現行の保存再生は最初から実身体10フレームとゼロaction10フレームを使用します。この開始条件の差を今回切り分けました。
- 既存の上流観測照合は整列済み10フレームを渡すmockを使用しており、起動Logger paddingや実機の閉ループを検証したものではありません。今回のoracleはpaddingを含めて150周期を対照しています。

停止・制御権は別の境界です。固定上流にはconstructorのReleaseMode、INITの姿勢移行、Stopのdamping目標処理がありますが、現行record_only workerはそれらを使いません。現行プロジェクトの低レベル送信・引継ぎ/復帰・物理停止は未実装/未検証という最新文書の記述と、上流に処理が存在する事実を区別してください。プロセス停止やSSH終了を物理停止と扱いません。根拠は `docs/SONIC_STARTUP_BOUNDARY.md:10` と `docs/HANDOFF.md` の現在の要約です。

独立診断は完了。ブロッカー・承認待ちはありません。診断時は既存プロジェクトを変更せず、保存入力だけで150周期×2条件を比較しました。G1への接続・指令、インストール、既存プロセスの停止・設定変更はありません。

## 結論

起動履歴の相違はSONIC出力を変えます。ただし、Loggerの起動paddingを再現しても計算目標のURDF超過は残り、最大の未送信目標と保存実測姿勢の差は初期10周期では大きくなりました。この相違だけを既存問題の原因や解決策と断定できません。

現行条件の150×29目標は既存保存出力を差0で再現しました。encoder tokenは両条件で全周期一致。関節順序・scale・default_anglesによる最終目標変換も全300出力で差0でした。比較する値は**SONIC decoder後の未送信q_target_hardwareと同周期の保存実測q**です。IK目標の誤差や実機の追従誤差ではありません。

|比較値|現行: 最初10周期|padding: 最初10周期|現行: 以後140周期|padding: 以後140周期|
|---|---:|---:|---:|---:|
|最大目標−保存実測差 rad|1.252512876|1.719764170|1.131385117|1.163652441|
|右足首roll URDF超過周期数|7|4|140|136|
|waist roll URDF超過周期数|0|2|139|137|

padding条件の最初10周期には左肘・左膝にも各1周期の超過があります。保存実測姿勢のURDF超過は全150周期で0。最大差の箇所は現行seq=2の右肩pitch、padding条件seq=5の左肩pitchです。

|両条件の最大絶対差|最初10周期 seq=0..9|以後 seq=10..149|
|---|---:|---:|
|encoder token|0|0|
|raw action|3.933726072|2.479341388|
|最終目標 rad|1.302244576|0.474508207|

身体観測のテンプレート差はseq=0..8だけで、seq=9以降は0です。その後は各条件がそれぞれの計算raw actionを履歴へ入れるため差が残ります。最終seq=149では目標差1.150214780e-6 rad、raw action差6.675720215e-6まで縮小しました。保存された身体は計算actionに反応しないため、この減衰を物理的な追従・安定性と解釈しません。

## 条件と再現範囲

- 入力: `g1-pika/artifacts/full-record/run-b5do1ocs/outputs/report.json`と関連保存身体150窓。ファイル整合検査成功、policy93件・身体150件・画像186ファイル。
- 同一モデル: low_latency revision `6733128a3d8a523b1418b06bca3cdf61c8b0987f`。encoder SHA256 `60be43157f57d812f38bdbb740a5de5d5d070e8840d9edc16f02a91a6d06255b`、decoder SHA256 `c4ac2e74045e7cbfb568f15e6bf47ea7ce023df7a94322af50be223e0a628bab`。
- 同一参照: 既存run-n4vkz49qと一致する記録IK終点保持、参照qを10フレーム複製、参照dq=0、保存capture姿勢。両条件ともencoder入力は同じ。
- 現行条件: 最初から保存実身体10フレームを使用。raw action履歴10フレームはゼロ開始。
- padding条件: 最初の保存制御周期の身体から履歴を1→10フレーム蓄積。不足部分は上流LoggerのzeroEntry。正規化済みbody_q=0、dq/gyro/action=0、Quaternion=(0,0,0,0)。このQuaternionを上流quat_rotate_dで変換した重力は(0,0,+1)。identity Quaternionの(0,0,-1)に置換していません。
- action履歴: 初期ゼロ、各条件の**未送信raw action**を独立して再帰投入。hardware目標や保存済みraw actionを診断推論の履歴に使用していません。
- 両条件の実身体Quaternion正規化とheading offset=0は現行実装に合わせて固定。上流Logger/Gatherのpadding処理を正確に比較する実験であり、上流のINIT姿勢移行・制御権操作・生Quaternionの扱い・実閉ループ全体の再現ではありません。開始時点は保存記録のseq=0です。
- galleriaの既存Python環境にはORTがなく、既存TensorRT workerを使用。実行直前GPU使用率0%、compute processなし、load 0。2条件を逐次実行し推論比較は3.288秒。RTX 5060 Ti / driver 580.178.04 / Python 3.12.13 / g++ 11.4.0 / 既存TensorRT 192.0.2.3、CUDA 12.8。

## 根拠コード

元プロジェクト: `/home/developer/workspaces/g1_pika_ws/g1-pika`。
上流基点: `vendor/GR00T-WholeBodyControl/gear_sonic_deploy/src/g1/g1_deploy_onnx_ref`（固定commit `087f9ac01d46f6d8e4d0b73c01ae64799f292a38`）。

- 上流 `src/state_logger.cpp:180,199,474`: GetLatestの不足フレームpaddingとzeroEntry（base_quat/body_q/actionもゼロ）。
- 上流 `src/g1_deploy_onnx_ref.cpp:1454,1502,1547,1592,1613`: q/dq/action/gyro/gravityの履歴Gather。`2847`で観測qのdefault差引き、`2946`で身体と直前actionの記録、`3869`でCONTROL周期の身体記録。
- 上流 `src/g1_deploy_onnx_ref.cpp:3140`: raw IsaacLab actionを関節順変換・scale・default加算し、送信用float目標を作成。
- `scripts/sonic_observation.py:43,55`: 現行参照とdecoder履歴。`scripts/sonic_offline_infer.cpp:52,63,90`: encoder→decoder、同じ最終目標式（診断保存はdouble）、record_only stdio。
- 本診断 `prepare.py`: 同一参照と2条件の身体テンプレート作成。`compare.py`: 各条件の独立raw action再帰・保存のみのworker。`oracle_test.py`: 実上流Logger/Gather関数を抽出したC++ oracle。`verify_results.py`: 保存出力の再検算。

元AGENTS/HANDOFFも読み直し、最新の参照補間・参照極値監査は解消済み作業として認識しています。今回の条件は既定のIK終点保持に固定し、新しい補間の再評価はしていません。準備時から検算時まで、記録した関連コード・文書のSHA変更は0です。元プロジェクトのdirtyな作業へ変更は加えていません。

## 検証と成果

- Logger/Gather oracle: 2テスト成功。実上流抽出処理との150周期float32差0。保存raw actionはoracle検証ベクトルにだけ使用。
- 集計境界の独立テスト: 1テスト成功（10周期/以後、URDF件数、基準再現）。
- 出力検算: schema/finite/連番150×2、目標式差0、token同一、集計再計算一致、現行保存基準差0。
- 元ONNX・元TRTキャッシュの前後SHA一致。新規フォルダのONNXは読取リンク、TRTキャッシュはコピーし、キャッシュ書込先を新規フォルダに限定。
- `results-01/current.json` / `startup.json`: 全周期のtoken64、raw action29、最終目標29と計算時間。
- `results-01/report.json`: 条件別・最初10/以後/全体の集計。
- `results-01/per-period-differences.json`: 全周期の身体テンプレート/token/raw/目標の差。
- `results-01/verification.json`, `oracle-verification.json`, `prepared-01/input-report.json`: 検証結果。
- `prepared-01/inputs.json`: 同一encoder/参照、保存実測、身体テンプレート、元ファイルSHA。
- `source-model-hashes-before.txt` / `after.txt`, `runtime-manifest.txt`, `run.log`: 非変更と実行記録。

ローカル成果: `/home/developer/Documents/Codex/2026-09-30/task/sonic-startup-diagnostic-20260930-a41f`。
galleria成果: `/home/gpu-user/g1-pika-training/artifacts/sonic-startup-diagnostic-xyWsSeys`。
上流ソース出典・ライセンスは `UPSTREAM-LICENSE.txt`。通常G1Deployは使用せず、コピーした通信機能のないfile/stdio workerだけをコンパイル・実行しました。

## 再実行手順

以下は再現のための手順です。実行時は空き資源と許可範囲を再確認し、既存ファイルを上書きしない出力名を選びます。

tigerで入力を再構築・oracle検証:

```bash
D=/home/developer/Documents/Codex/2026-09-30/task/sonic-startup-diagnostic-20260930-a41f
PY=/home/developer/workspaces/g1_pika_ws/g1-pika/.venv/bin/python
"$PY" -B -I "$D/prepare.py" --output "$D/prepared-02"
"$PY" -B -I "$D/oracle_test.py"
"$PY" -B -I "$D/verify_results.py"
```

`verify_results.py`は保存済みresults-01を検算します。`prepare.py`は固定上流や入力hashが変わると停止します。

承認された既存SSH接続でgalleriaに入り、配置済み同一入力の比較を別出力へ再実行:

```bash
D=/home/gpu-user/g1-pika-training/artifacts/sonic-startup-diagnostic-xyWsSeys
nice -n 10 timeout --signal=TERM --kill-after=3s 90s bash "$D/build_sonic_offline.sh" "$D"
LD_LIBRARY_PATH=/home/gpu-user/TensorRT-192.0.2.3/lib:/usr/local/cuda-12.8/lib64 \
  nice -n 10 timeout --signal=TERM --kill-after=3s 120s \
  /home/gpu-user/g1-pika-training/.venv-gpu/bin/python -B -I "$D/compare.py" \
  --input "$D/inputs.json" --binary "$D/sonic_offline_infer" \
  --encoder "$D/models/model_encoder.onnx" --decoder "$D/models/model_decoder.onnx" \
  --output "$D/results-02"
```

既存の診断binaryを使う場合、compile行は不要です。出力先が既存ならcompareは停止します。途中で失敗した場合は未完成出力を消して再使用せず、新規名を選びます。新規モデル/cache追加・新しい認証/権限変更は不要です。

## 原因候補の優先順位と次の切り分け（今回は実行していない）

1. **起動履歴のどのチャネルが初期差を作るか。** 相違と出力への影響は確定しました。身体q/dq、gyro、ゼロQuaternion由来gravityを一つずつ置換する保存再生を同一参照・モデルで比較し、各条件のraw action再帰を保つ。起動paddingのどの成分が主因かは今回未分離です。
2. **参照のモデル適用条件。** paddingでもURDF超過が残るため、既存の実姿勢保持/IK終点保持/連続関節参照に同じ2起動条件を掛け合わせ、参照と起動履歴の効果を分離する。参照dq=0や姿勢/heading条件の成立は今回固定した前提で、誤りと確定したわけではありません。既存補間・極値監査は古い未実装課題として追いません。
3. **保存観測と上流開始条件の契約。** 本診断はQuaternion正規化とheading=0を双方で固定しています。保存された生Quaternion・座標系・時刻、上流CONTROL開始時のq/dq/参照定義と初期化文書をファイルだけで対照し、未検証前提を一覧化する。これも実閉ループ・支持状態・停止手段の評価とは区別する。

scale/default/orderの変換に今回の誤差はありません。未送信再帰では身体反応が欠けるため、これらのオフライン切り分けで実機追従性や全原因を確定することはできません。修正は提案にとどめました。
