# 身体制御の起動・停止要求プロトコル（送信なし）

2026-10-01。初期姿勢参照・制御権の引継ぎ要求・入力期限切れ・停止要求を、
機器へ接続しない状態機械として実装した。実機送信、物理停止、制御権の実際の移行は未実行。
SDK接続コードは後続でbuild-only実装済み、実gatewayへの統合は未完了（[SDKアダプター](BODY_IO_ADAPTER.md)）。
`hardware_output_enabled=true`は拒否する。既存ACT/IK/SONICのオンライン処理は変更していない。

## 責務と状態

10月1日続報：`local_body_monitor.py` / `LocalSonicBodyBridge`に、G1側同一ホストの
LowStateだけで更新する鮮度監視コアを追加。GPUが運ぶbodyコピーでは更新しない。
重複tickは時計を更新せず、逆行/期限切れ/モード変更はラッチして停止要求にする。
`receive_state --stream`はmode_pr/mode_machineも出力する。従来モードのCRCは未確認。
後続の`--verify-crc`/service `--require-crc`で実LowState CRCの検証も追加済み。
新規9単体試験成功。続いて`local_body_service.py`でstdinの同一ホスト受信とZMQのGPU要求を
分離し、独立10ms監視threadを実装。後続でG1/aarch64への配置・実入力検証も完了。
人工入力・ローカルIPCで正常終了と「GPU要求/EOFなし」の期限切れを含む7試験成功。
起動前の古いpipe backlogだけを捨て、最初の観測以後の期限切れは更新で解除しない。
ZMQ peerにlocal_state/INIT/takeover/execute APIは提供しない。
これは500Hz writerや実時間保証・物理停止adapterの実装ではない。
単体は`python3 -I scripts/check_local_body_service.py`、process/IPC追加は`--ipc`。
実配置にはG1ローカルのPython/numpy/libzmqと固定profile/configが必要。pyzmqは不要。
このサービスの対象TCPは明示bind IP＋単一peer IP、ZMQ認証は未実装（隔離された信頼リンク前提）。
物理停止/制御権/実送信の実装・検証は残る。

### G1局所サービスの実入力検証

G1を起動してgalleriaと有線接続し、tigerのリポジトリ直下で実行する。
固定接続情報はassets/network/g1-runtime-access.json、厳密なSSHホスト鍵照合を維持。
現行トポロジー以外へ暗黙に切り替えない。試験用TCP6077を対象IPだけにbindし、
peerは192.168.123.99/32のみ。暗号化・ZMQ認証はなく、信頼できる隔離LAN用。

```bash
make body-local-check
make body-local-expiry-check
```

前者は保存済み固定実SONIC150出力を、実LowStateで独立監視するG1サービスへ渡す。
LeRobot/SONICの再推論ではない。関節目標・PIKA幅は元の値を保存し、初期姿勢未確認で全てgate。
後者は50件の人工既定目標probe後、receiverからserviceへの転送のみ止める。
stdinは開いたまま、GPUから追加要求なしでもwatchdogが期限切れを検出する。
どちらも通常G1Deploy/LowCmd publisher/INIT/制御権変更/カメラ/シリアルを起動しない。
停止ACKは記録セッションの終了で、実機の停止ではない。

新規GPU artifact/G1 /tmpディレクトリだけを使用し、既存runtime・OS・依存を上書きしない。
service15秒/外側20秒timeout、終了時は自分の子process/threadだけを終了。
G1 Python3.10.12/numpy1.21.5/libzmq/CycloneDDS0.10.2を実確認、追加installなし。
入力上限64KiB。snapshotの年齢はSSH因果往復時間＋G1局所年齢で上界化する。
これはライブ身体sampleの診断転送年齢で、保存SONICの生成時刻の鮮度を主張しない。
実機制御用の身体状態転送・50Hz計算期限を、このSSH補助経路で代用しない。

最終正常runはartifacts/local-body/local-body-nZZEwC/outputs/。
150件全gate/受理0/抽象writer0/実機指令0、147件の範囲超過は未解決のまま記録。
実LowState164件、最大間隔21.04ms、snapshot年齢上界最大24.41ms。
mode_machine=5/mode_pr=0、CRC未確認。service/supervisor exit0、receiver TERM(-15)、全thread終了。
最終期限切れrunはlocal-body-IGY3In/outputs/。
最後のsampleから101.31msで異常を観測（転送停止から96.38ms）、process終了は353.36ms。
期待するservice exit1/supervisor exit0。検出時刻と終了時刻は別journalで照合。
実時間保証・物理停止時間・実機追従・タスク成功の認定ではない。
raw状態、decisions、receiver/service/supervisor stderr、service-report、reportを回収済み。
単体probe helper3件とservice --ipc7件、一括check-offline成功（IPC6件明示skip）。

`scripts/body_lifecycle.py`は身体状態と29関節目標を受け取る純粋なロジック。
SDK・DDS・ZMQ・シリアル・MotionSwitcherを呼ばない。
出力は`abstract_29_joint_record_NOT_Unitree_LowCmd`であり、送信するパケットではない。

```text
idle → observing → ownership_pending → owned
  → initializing → settling → ready → tracking
                     ↓（異常または停止要求）
              fault / stop_required
                → return_pending → closed
```

- 観測開始・オブジェクト生成で制御権解除や初期移行を暗黙に行わない。
- 引継ぎ、停止、復帰のACKは`diagnostic_ack_not_physical_confirmation`のみ。
  保存再生では人工的に与える。実機がACKした、停止した、復帰したという証拠にはしない。
- 初期移行時間が終了しただけではSONIC目標を受け付けない。
  実測q/dqの姿勢条件が一定時間継続してから`ready`となる。
  この条件は接地・IMU姿勢・接触力・衝突・バランスを検査しておらず、実機準備完了ではない。
- ローカル入力年齢、身体tickの単調性、制御権ACKの年齢、目標session/連番/年齢、
  関節範囲・目標変化・参照速度、writerの間隔を検査する。
  他PCのmonotonic時刻同士を引かない。遅着した新しい入力で期限切れを解除しない。
- 異常・停止要求は目標を破棄してラッチし、自動再接続/再開しない。
  `request_stop`はGPU応答やworker終了を待たないが、**物理停止を行う関数ではない**。
  内部記録はcommand256件/event128件まで。外部の記録用journalは別。

## 初期参照と設定

`body_lifecycle_profile.py`が固定上流`policy_parameters.hpp`をデータ専用で読み取り、
default_angles/kp/kd、生成済みPIKA URDFの関節順・範囲・速度を出典hashとともに保存する。
上流のkp/kdを引用したのであって、PIKA装着機の安全なゲインを認定したわけではない。

初期参照は既存`JointTrajectory`を再利用した3秒の5次多項式候補。
開始時の保存実測q/dqからdefault_anglesへ移り、区間の角度/速度極値をモデル範囲で検査する。
上流INITの「毎周期の実測角を再使用するblend」とは異なる。
参照のdqは記録するが、抽象motor出力のdq/tauは上流同様0。
加速度・トルク・干渉・支持条件・物理的な追従は未検証。

`config/body-lifecycle.json`は診断用の設定値で、安全規格や実機採用値ではない。

| 設定 | 診断値 |
| --- | ---: |
| 初期参照 / 姿勢条件の継続時間 | 3秒 / 0.5秒 |
| 姿勢q / dqの許容差 | 0.02rad / 0.05rad/s |
| 身体入力 / 計算目標の年齢上限 | 各0.1秒 |
| 引継ぎ待ち / 制御権ACKの年齢上限 | 各0.5秒 |
| 目標の一回の変化上限 / writer間隔上限 | 0.05rad / 0.01秒 |
| 診断control / writer刻み | 0.02秒 / 0.002秒 |

writer刻みは保存再生の仮想時計。500Hzの実時間スケジューラを実装・保証したものではない。
元のSONIC出力に残るURDF外目標をclippingや閾値緩和で解決していない。

## 検証と再現

ローカルの既存`.venv`、g++、固定vendorソース、生成済みURDFを使う。GPU/G1不要。

```bash
make check-offline
make body-lifecycle-check
make body-lifecycle-verify RUN=artifacts/body-lifecycle/run-6arb9pnq
make lowcmd-preview RUN=artifacts/body-lifecycle/run-6arb9pnq
```

`body-lifecycle-check`は23状態機械試験＋3journal試験、保存実身体の再生を実行する。
初期参照の極値、期限切れ、時計逆行、連番、姿勢未到達、停止後の拒否、記録改変を検査。
LowCmd previewの3試験も`check-offline`へ追加。一括検査exit0、既存IPC4件は明示skip。
シミュレーションは実行していない。

最新の保存再生は`artifacts/body-lifecycle/run-6arb9pnq/`。
9月24日のrun-b5do1ocsのhash照合済み身体150件を変更せず使用し、1540件の抽象出力を保存。
実身体はこの参照で動いていないため姿勢到達を確認せず、SONIC目標受理は0件。
3秒で`settling`、最後の入力後の診断時刻3.08秒で`body_watchdog_expired`。
停止後の出力拒否と診断ACKによる終了は確認したが、身体の停止・復帰は確認していない。
`body-lifecycle-verify`は4ファイルのhashと全出力・状態遷移を再計算して照合する。
この再生の時計は加速した保存timelineで、実入力の鮮度や性能の測定ではない。

## LowCmdのデータ専用プレビュー

### 続報：実LowStateのCRC検証

`state_receiver/state_crc.h`でnative LowState2092bytesを全フィールドから再構築。
DDS allocatorのpaddingをCRCへ混入させず、固定SDKのゼロpaddingデータクラスと比較する。
不一致はreceiver exit3/EOFとして局所監視を失敗させ、後からの新しい観測でラッチを解除しない。
従来のCRC未確認record-onlyモードは比較用に保存し、既定の動作を勝手に変更していない。

```bash
make body-local-crc-check
make body-local-crc-expiry-check
```

SDK/C/Pythonの128完全state fixtureでlayout/CRCが一致。破損field/CRCと非ゼロallocator paddingも検査。
x86_64/aarch64 native fixture SHAは双方
107b35f26ef7ea599eb47871ab1cdf53eb3ea5d31e93851269c919d69026302c。
G1実入力run-EHFf0D（artifacts/local-body/）は165frame全CRC一致、150保存SONIC全gate/指令0。
147件の範囲超過は保存したまま。最大入力間隔20.97ms/因果年齢上界31.63ms。
CRC必須monitorは未確認/証拠欠落/値不一致を拒否する。G1 mode_machine=5/mode_pr=0。
strict期限切れrun-zwvbSW：77frame全CRC一致、stdinを開いたまま転送停止、
最後のsampleから109.56msで異常を観測、process終了353.39ms。物理停止や実時間保証ではない。
通常SDK/実publisher/シリアルを起動していない。CRCは通信データ整合性であり、
モーター正常性・支持条件・排他制御権・実機安全性の証明ではない。

`lowcmd_preview.py/.cpp`は固定Unitree SDKのLowCmd/MotorCmdデータクラスとCRC関数のみを使用。
DDS型登録を除いて一時コンパイルし、元のBSD-3-Clauseライセンスを保持する。
SDKの通信ライブラリをリンクせず、publisherや通常G1Deployを起動しない。
SDKの3ファイルhashはコードと各reportに固定。独立したPython CRC計算とも比較する。

最新結果は`artifacts/lowcmd-preview/run-uin1oocv/`。
1540件すべてでnative memoryサイズ1004bytes、29motorの順序/float32、
未使用6motorの無効化、reserve/paddingのゼロ、CRCが一致した。
`mode_pr=0`、motor mode=1、mode_machine=0は**診断fixture**であり、実機型式の検出値ではない。
保存hexはnative object memoryであってDDS/CDRの通信形式ではない。
上記run単体ではG1のaarch64 ABI/firmware、DDS配送、実機受理は未検証。

後続の`make lowcmd-abi-check`はSDKデータクラスだけをG1でコンパイルし、
同じ保存抽象journal1540件をx86_64/aarch64で比較する（galleria/G1起動が必要）。
DDS型登録を除いたLowCmd/MotorCmd＋CRCだけをexport、SDK client/publisherをリンクしない。
読み取り記録のmode_machine=5を診断値として使用するが、現在の制御型式の確認とは扱わない。
artifacts/lowcmd-abi/lowcmd-abi-J7oor9で全1540件/1004bytesのnative memoryが完全一致。
SHA256は両環境85c3ec8629d58d1b53ea4bbebff9ef94c2360b47d256d1169f344c180f0907dd。
独立Python CRCとも一致、G1バイナリexit0。ファイル入出力だけで動作指令なし。
**LowCmd native ABIの照合と、LowState受信CRC（未確認）は別**。
DDS/CDR通信、firmware受理、実writer、物理停止、実機追従は依然未検証。

10月1日の初回G1照会はタイムアウトだったが、ユーザーの起動通知後は上記の記録サービス配置・
実入力検証に成功した。LowCmd previewのaarch64/実機送信検証を行った意味ではない。
現在の電源や支持状態は過去の結果から推測せず、G1が必要な試験前に用途付きで確認する。

## 次の実装・実機境界

### SONIC出力との接続（2026-10-01追加）

`sonic_body_bridge.py`に既存`q_target_hardware`を変更せず渡す接続部と、
既存`RecordSession`互換の受信handler/clientを実装した。
session/連番/身体tick/29関節順序/有限値/幅/record-onlyを照合し、
姿勢確認前は`gated_initial_pose_not_ready`として目標を受理しない。
その間のモデル範囲外も記録する。ready後はBodyLifecycleの範囲/変化/速度検査を通す。
PIKA幅はメタデータのみ。motor/Dex3指令に変換しない。

```bash
make body-boundary-check
make body-boundary-ipc
```

前者はソケットなし、後者はローカルUnixソケットのZMQのみ。G1/GPUへ接続しない。
ファイル再生run-i0jva6mw、IPC再生run-unswp0me（`artifacts/body-boundary/`）で
保存実身体/SONIC150組を受信し、decisionファイルのhashが一致。
全150件は姿勢未確認でgateされ、抽象目標受理0/指令0、幅は全件保存値と一致。
147件でモデル範囲外（右ankle roll/waist roll）を記録。以前の問題を解消した結果ではない。
IPC受信threadの終了を確認。protocolの停止ACKは通信/記録終了だけで、身体は`stop_required`のまま。

`run_online_loop(..., body_sink=...)`へ同じclientを渡せる接続点を追加。
SONIC計算後・履歴commit前に渡し、通信時間も20ms計算期限へ含める。
各outputに受信decisionを保存し、終了時は入力/GPUのjoin前にsinkを終了する。
sinkの異常/終了ACK失敗でも他workerをcleanupする。
7接続部試験＋既存online試験へ4追加、online計20試験成功。一括check-offline成功（IPC4件skip）。
fake推論worker＋実handler/clientでは50件を通し、全件gate/幅保持/終了を確認。

接続点は既定では無効。既存GPU/実入力launcherに新しい受信部を自動配置したわけではない。
今回の受信部は引継ぎ/INIT操作を通信APIとして提供せず、500Hz writerも駆動しない。
実G1で動かした試験ではなく、保存再生のsource_age=0はlive鮮度ではない。
実装したRecordSessionは記録診断用で、実機停止の配送経路に流用しない。
将来のG1実送信部では身体監視をローカル実LowStateから独立させ、
GPUが転送した身体値やクライアントの往復検査だけで鮮度を認定しない。

### 残る実機adapter

1. G1側の独立した送信/停止adapter：入力途絶・GPU停止でもローカルで作動させる。
   GPU/SSH応答やworkerのjoinを停止の前提にしない。停止方式は現在未決定で勝手に選ばない。
2. 実際の制御権引継ぎ/復帰、robot variant/mode_machine、LowState検証、aarch64 ABI/DDSの照合。
   診断ACKを物理確認へ読み替えない。通常G1Deployのconstructorを流用して暗黙に解除しない。
3. 支持/停止の実効性、PIKA干渉とゲイン、初期姿勢・SONIC参照の適用条件を確定する。
   最小の試験範囲・終了条件を具体化して、その実機動作に対する明示許可を受ける。

現在、上記の実機出力adapterは未提供。READMEの診断コマンドを動作コマンドに転用しない。
関連：[上流起動境界](SONIC_STARTUP_BOUNDARY.md)、[目標監査](TARGET_AUDIT.md)、
[開始契約照合](SONIC_STARTUP_ABLATION.md)、[開発手順](DEVELOPMENT_RUNBOOK.md)。
