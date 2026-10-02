# ZMQによる実画像・G1状態の受信と推論記録

2026-09-14。DDSはG1内部のrt/lowstate購読、PC間データ転送はZMQへ分離した。
SSHはプログラムの配置・起動・終了確認のみ。画像・状態パケットはSSHを通さない。

## 確認結果

- G1の既存ROS列挙はbad_alloc/timeout。既存SDKはgo2型のみだったため変更せず保留。
- 既存CycloneDDS 0.10.2のidlc/libddscを使い、送信型・DataWriterを含まないC受信器を
  /tmp/g1-pika-state-Lsxpddにビルド。rt/lowstateをeth0/domain0で5秒購読し、
  有限な関節角/速度・IMU quaternionを4567件、tick更新4410件受信した。
  最大受信間隔4.271ms。CRCは未検証、実機制御への採用判定ではない。
- IDLは既存unitree_sdk2_python commit 65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5の
  LowState_/IMUState_/MotorState_のフィールドから転記。出典とBSDライセンスはscripts/state_receiver/に保存。
- readerのCLOCK_MONOTONICとG1カメラread時刻で対応付け、状態age100ms以内・
  画像readと状態受信の差100ms以内を検査。露光時刻同期・CRC・機体設定の妥当性は別途必要。
- G1の有線192.168.123.164:6158にZMQ REPをbindし、TCP_ACCEPT_FILTERで
  GPU PC 192.168.123.99のみ許可。REQから受けるのはseq/stopだけで、動作指令経路はない。
- 両PCの既存libzmqをctypesから使用。G1 4.3.2、GPU 4.3.4。
  新規pip/aptインストールなし。これらは環境由来の版を記録したもので新しい依存lockではない。
- 画像2視点＋G1実状態30組をZMQで受信しGPU推論・記録まで成功。body tickも30種類。
  通信込みp95 35.014ms、GPU推論p95 7.965ms、画像/状態受信時刻差最大63.153ms。
  最大5組/秒の診断なので30Hzの達成を示すものではない。
- 終了後にZMQ待受ポートが閉じていることを確認。IPC単体3試験（送受信・timeout・不正出力拒否）合格。
  サンドボックス内のIPC拒否後、外側で実行。構文・diff検査も合格。

## 配置と記録

- ローカル要約: docs/zmq-state-shadow-2026-09-14.json。
- GPU runner: /home/gpu-user/g1-pika-training/artifacts/zmq-runner-n9lmjY/。
- GPU結果: /home/gpu-user/g1-pika-training/artifacts/live-shadow/run-r7jp86l3/。
- G1一時reader: /tmp/g1-pika-state-Lsxpdd/receive_state。
  再起動等で消えた場合は再ビルドが必要。現段階は診断配置で、常設サービスではない。

## 未完了の境界

推論に使った入力は実画像＋current-TCP identity＋仮の幅4cm。
受信したG1のq/dq/IMUは画像との対応を記録しただけで、ACT入力へ直接流し込んでいない。
実測幅は既存ドライバのリセット/disable副作用を避けるため未接続。
ZMQはIP制限のみでCURVE等の認証・暗号化は未実装。信頼した有線網の短時間診断に限定する。
推論出力のG1向け送信、実機用WBC配置・制御権管理、非常停止・通信断時処理、
機体/TCP/グリッパ較正、実機の自立タスク評価は未完了。動作指令禁止は継続。
