# SONIC＋LeRobotのMuJoCo統合検証

G1実機に接続せず、galleria内で動力学閉ループを検証する起動口。
通常G1Deploy、Unitree SDK、DDS publisher、PIKAシリアルを起動しない。
実機側実装・実機検証の代替ではない。

## 統一起動（2026-10-02）

```bash
make run                 # 30秒、native身体コマンド経由、動画も回収
make run RUN_SECONDS=3   # 短時間
```

LeRobot→IK→SONIC→C++ BodyIoAdapter/WriterKernel→固定LowCmdデータ→MuJoCo。
従来のPython直接PDとは異なり、native LowCmdに格納したfloat32の値からトルクを計算する。
sim_body_gatewayはsimulation backendに固定し、実SDK通信をリンク/選択できない。
停止候補・controller復帰の操作順はsimulationのみ、実機のownership/CRC/health/停止確認を代替しない。
実機WriterMailboxのstep/速度gateは変更していない。起動0.3437radによるphysical gate未合格は維持する。

最終`artifacts/sonic-mujoco/run-u9gljra3/outputs/`：30秒ACT900/SONIC1500/native15100tick、
立位・範囲外0、最低高さ0.73125m/傾き最大0.08010rad。右TCP移動最大0.28080mは起動整定も含む。
1秒後以降の右腕関節記録の変化幅最大0.32567rad。動画755frame、全worker/encoder終了。
モデル/キャッシュSHA不変。report.jsonとbody-runtime.jsonに動作経路/コマンドSHA/人工入力の範囲を保存。
保存RGB/幅仮定・固定PIKA、同期sim時間であり、視覚タスク/把持/実時間/実G1の成功ではない。

## 起動

既存配置は `config/development.json`。galleriaへの鍵SSH、CUDA12.8、
TensorRT10.13.3.9、IK用Python/MuJoCo3.3.4・NumPy1.26.4、ffmpegを使用。
ACTは別の固定 `.venv-gpu`、LeRobot/モデル/前処理をbundleで照合する。
新規PCの汎用setupではなく、既存GPU配置を再利用する。

```bash
make check-sonic-sim                      # ローカル単体、GPU/G1不要
make sonic-sim SIM_SECONDS=5              # G1単体、動画付き
make sonic-pika-sim SIM_SECONDS=10         # 固定PIKA付き、動画付き
make sonic-policy-sim SIM_SECONDS=30      # 保存RGB ACT＋実測sim TCP
make sonic-teacher-sim                    # 15秒。下記の起動TCP条件は未合格
```

結果は `artifacts/sonic-mujoco/run-*/outputs/` のreport.json、simulation.mp4、
observations.json、outputs.json、trajectory.json。ACTではactor.jsonも保存。
失敗時も新規フォルダへ回収し、以前の記録・モデル・キャッシュを上書きしない。
GPU側180秒で打ち切り、SSH側210秒。切断時は終了確認済みと扱わない。

## 検証条件

- genuine SONIC low_latency encoder/decoder。revision/hashはsources.lock.json。
  stdio専用C++ workerを使用し、旧balance policyはロードしない。
- 29関節の自由浮遊G1、床接触あり、500Hz物理・50Hz SONIC。
  バンド/固定基部/踏み中のroot resetなし。目標角度clippingなし。
  PDゲインは固定SONIC定数、トルク飽和はモデルのactuatorfrcrange。
- 最初の0.2秒に実際にPDで物理を進め、10件の観測履歴を収集。
  SONIC raw action履歴は起動前のみゼロ、推論開始後は直前の生出力を戻す。
  角速度はpelvisのregular body軸（XBODY）、理想観測でノイズなし。
  BODYの慣性軸との差は[MuJoCo3.3.4ソース](https://github.com/google-deepmind/mujoco/blob/3.3.4/src/engine/engine_support.c#L1064)と単体試験で確認。
- 物理は推論中停止する同期sim-time方式。実時間500Hz/ネットワーク期限の合格ではない。
  直接qposで初期化するのは開始時1回だけ。実機INIT/制御権移行ではない。
- plantは固定Decoupled資産／既存生成PIKAモデルを再利用。
  SONIC学習時の公式43DOF plantと一致するとは主張しない。
  PIKAは旧q=0固定・旧URDF慣性、カメラ/取付金具/ケーブル質量は未計測。

## 到達点（2026-10-01）

| 保存run | 条件 | 結果 |
| --- | --- | --- |
| run-vb3420cg | G1単体5秒 | 短時間立位成功。XBODY修正前の暫定結果 |
| run-_y3gmgz2 | 固定PIKA10秒 | 短時間立位成功。XBODY修正前の暫定結果 |
| run-mkjlzx75 | ACT＋固定PIKA30秒（最終再実行） | ACT900/SONIC1500、全worker exit0、範囲外0、傾き最大0.0801rad、モデル/TRTキャッシュ不変 |
| run-fpygotrm | 教師15秒、連続初期参照2秒 | 750推論・教師完了・範囲外0・立位維持。ただし全期間TCP誤差8.23cmで未合格。再生区間3.39cm/0.1758rad |

ACTはSHA照合した保存画像1組を繰り返し、幅入力は明示的な仮定0.04m。
各fresh h1 actionはその時の**実測sim TCP**へ適用する。脚/左腕は計画参照に保持。
画像が物理に反応する視覚閉ループではなく、タスク成功・グリッパ駆動も未検証。
30Hz ACT要求は50Hz制御tickへ量子化し、同じactionを繰り返し積算しない。
PC間の実装方針は引き続きZMQ。このGPU内検証のworker通信はstdio。

教師は既存episode0を縮小せず再生。SONIC既定姿勢から旧教師中立腕へ
既存JointTrajectoryで2秒かけて参照を遷移し、2秒settle後に再生する。
実測姿勢を次の脚/左腕目標へ採用し続けない。IKは計画seed、身体観測は実測で分離。
開始直後のTCP誤差が最大。教師開始後は保存結果の独立FK再計算で最大3.39cm。
全期間5cmの基準を緩めたり、起動区間を隠してpassed=trueにはしていない。
判定は高さ0.45m以上・傾き0.8rad以下・50Hz関節範囲確認、教師では
全期間TCP5cm/0.3rad・再生中移動4cm以上も要求する。これらは未校正の診断閾値。

## 保存した失敗と次工程

- run-7z15dipl：PDのみ1秒warmup中に姿勢が崩れ、SONIC開始後0.314秒で転倒閾値。
- run-wcpfr_i0：脚/左腕を毎回実測holdする参照でIK不合格。
- run-h573ztcq：SONIC既定腕基準の教師軌道がIK範囲外。目標を縮小せず保存。
- run-0oqn3cdd：教師中立腕で直接開始。起動4周期にwaist pitch目標範囲超過。
  連続参照遷移にしたrun-pu1qxp7gでは超過0だが、起動TCP条件は残る。

次は起動TCP過渡条件の解消と、G1側ローカル状態監視・低レベル送信・
実制御権/初期姿勢/物理停止adapterの統合。simの姿勢初期化やプロセス終了を
実機の起動/停止保証に流用しない。実機指令には別途具体的な許可・現場確認が必要。
sim開始時の目標変化最大0.3437radは既存body gateの0.05radより大きい。
sim合格を、そのままBodyLifecycleの受理条件や実機送信許可と解釈しない。
続報：G1側監視サービスは10月1日に実配置/実LowState CRC必須読取り診断済み。
実機出力とのruntime統合は未完。最新はHANDOFF/IMPLEMENTATION_TODOを参照する。
