# 実入力統合とWBC送信なし確認（2026-09-18）

## 完了: 画像・身体状態・グリッパ→ZMQ→LeRobot

```sh
make -C /home/developer/workspaces/g1_pika_ws/g1-pika input-shadow
```

このコマンドは右シリアルを開くため接続リセットの可能性あり。保持物なし・周囲安全で使う。
enable/disable/目標は送らない。身体SDK・モード切替・LowCmdは起動しない。

- 既存PikaGripperはhash確認して無変更import。差分は受信時刻の記録、送信禁止、
  終了時にdisableを送らずthread停止/closeするライフサイクルのみ。
- 幅は既存PIKA ROS commit0f7f6b75a349ceccb252628f5f48a28aaf5c7b6bの
  getDistance式と0〜1.67角度クリップ/errorを移植。BSDライセンス同梱。
  校正済みの幅ではなく「エンコーダ角度から旧機構式で換算した幅」と明記。
- scripts/gripper_observation.py、LICENSE.pika_geometry、check_gripper_observation.py。
  境界・クリップ/error・単調性・非有限値の4単体テスト合格。
- 右RGB2視点＋35 motor q/dq＋IMU quaternion/gyro＋グリッパ角度/幅を
  G1同一monotonic時計で時刻付けし、有線ZMQでgalleriaへ30組送信。
- CUDA LeRobot ACTのstate[9]と残差幅デコードへ同じ実入力幅を使用。
  以前の仮幅0.04mは使わず、欠損時に仮幅へフォールバックもしない。
  stateの他9次元は既存current-TCP-relative identity契約を維持。
- 30/30推論成功、通信込みp95 34.288ms、推論p95 7.596ms。
- 入力幅0.000232339〜0.000240106m、予測幅0.000329448〜0.000344093m。
  今回の30組にはlegacy_range_errorなし。これで以前の通信異常が解消したとは判定しない。
- `make input-shadow`終了コード0。G1のポート/プロセス/6158待受の残留は確認されず。
- 5組/秒の診断、露光時刻同期ではなく受信時刻比較。連続30Hzや実機タスク成功ではない。

記録: tiger `artifacts/state-shadow/state-shadow-Pysyga/live-report.json`。
GPU `/home/gpu-user/g1-pika-training/artifacts/live-shadow/run-1c31drlw/`。

## 未完了: 実姿勢によるWBC初期化

`scripts/replay_real_wbc_shadow.py`を追加。保存済み実入力→既存FK/IK/WBC→JSONだけ。
G1への通信機能なし。MuJoCoはFK用途のみでmj_stepしない。galleriaでも実行した。

状態変換は固定本家のBodyStateProcessor._prepare_low_stateを参照:
JOINT2MOTOR=0..28、quaternion=wxyz、gyroを角速度に使用。
実機分岐と同じくbase xyz/linear velocityは0（実測ではない）。
BodyStateProcessor自体はconstructorがReleaseModeするためimport/起動しない。

現在の実測肩ロール:

| 関節 | 実測rad | 本家IK範囲rad |
|---|---:|---:|
| left_shoulder_roll_joint | -0.029517 | 0.19〜2.2515 |
| right_shoulder_roll_joint | 0.043778 | -2.2515〜-0.19 |

本家g1_supplemental_info.pyの制限から外れ、初期化時に
`Joint 1 violates configuration limits 0.19 <= -0.0295171477 <= 2.2515`で停止。
**WBC出力0件、passed=false。** tiger/galleriaで同じ結果。
実測角度のクリップ・制限緩和・実機姿勢変更は行わなかった。
これは独自保護による停止ではなく、固定した本家IKの初期姿勢条件。

記録: 同ローカルフォルダのwbc-shadow-local.json / wbc-shadow.json。
GPU WBC配置: /home/gpu-user/g1-pika-training/artifacts/split-wbc-bHU7TO/。
記録再生は完了しておらず、ライブACT→WBCの同時動作もまだ未検証。

## 次に必要なこと

本家の初期姿勢への移行方法と機体側制御権を確認し、現在姿勢からの手順を決める。
右グリッパ開閉の許可を身体・腕の許可に拡張しない。身体を動かす段階では別途許可が必要。
初期姿勢が整った後、同じ実入力→WBC出力記録を再確認する。
推論入力と関節出力が接続できたことを自立タスク完成や安全保証として扱わない。
