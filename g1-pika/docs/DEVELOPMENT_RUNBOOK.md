# 開発・終了・共有手順（実機検証前）

## 対象と非対象

現段階はrecord-only。学習済みACT→本家IK→ZMQ IPC→実SONIC推論を、
GPU PC内の持続プロセスで接続し、保存画像2組で完走を確認した。
独立30Hz/50Hzのスケジューリングも保存snapshot反復の短時間ソフトウェア試験で確認した。
実センサー入力は一時RR/1適用下の3秒試験で93policy/150control完走。低レベル送信は未統合。
長時間安定性や実機追従の検証ではない。この試験を本番オンライン動作と扱わない。
通常のG1Deployはモード切替/送信経路を持つため、この手順から起動しない。
G1の同時入力取得は読み取り了承後に実施済み。
その取得・オンライン記録の単一起動実装は[実入力統合](ONLINE_RECORD.md)にまとめた。
実入力用はACT/IK/観測生成/SONICの4ワーカー。[計算目標の監査](TARGET_AUDIT.md)は保存記録のみを使う。
通常の保存入力コマンドと異なり、`online-record`だけは読み取り了承が必要。

## 設定

`config/development.json`がGPU接続先・既存ビルド・モデル・IK分離環境・CUDA/TRT配置を集約。
`mode=record_only`、`hardware_output_enabled=false`以外は拒否する。
このフラグをtrueにしても実機機能は有効にならない。秘密鍵の中身やパスワードは保存しない。
別PCでは設定を複製し、各runnerの`--config /absolute/path.json`で指定する。
ACT候補配置と7ファイル・前処理・codecは`config/policy-bundle.json`。
GPU全経路runnerは新規試験配置へmanifestを転送し、GPU実体を照合してから推論する。
モデル一式の共有は[照合・配布手順](POLICY_BUNDLE.md)。モデル本体だけを持ち出さない。
G1側のUSB機器/SSH設定は従来の`assets/network/g1-runtime-access.json`。
旧シミュレーション/取得runnerの全設定を一括置換したわけではない。

診断用締切0.1秒（入力鮮度）、0.5秒（応答上限/入力間隔）は開発用であり、実機安全規格ではない。
受信時には元の入力年齢＋ローカル往復時間を検査する。
別PCのmonotonic時刻同士は引かない。実機の遅延/時計同期/停止実効性は別途検証する。

## 開発操作

リポジトリ直下から:

```bash
make doctor
make bundle-check
make check-offline
make check-runtime
make full-record-check
make rate-record-check
make online-fixture-check RATE_SECONDS=30
make sonic-tcp-check INPUT=artifacts/sonic-tcp/reinferred-endpoints-20260924.json
```

- doctor: ローカル読取りのみ。
- bundle-check: ACT7ファイル・codec/前処理/依存lock照合。標準Pythonのみ。
- check-offline: ソケットを開かない単体検査。既存Python3.10 `.venv`とg++が必要。
- check-runtime: ローカルIPCのみ。サンドボックスでbindが禁止される場合は実行承認が必要。
  権限エラーを成功・skipに読み替えない。通常単体側ではIPC2件を明示的にskipし、別コマンドで実行する。
- sonic-tcp-check: galleriaにSSH接続。IKはローカル、SONICはGPUの新規artifact内でコンパイル/推論。
  G1には接続しない。準備済みactionを使い、毎回画像ACT推論までやり直すコマンドではない。
- full-record-check: 保存画像→新しいACT推論→本家IK→ZMQ→実SONIC推論をすべてgalleriaで実行。
  各モデルは一度ロード。ACTは合成画像で3回ウォームアップしてからready。毎回新規配置し終了する。
  既存GPU画像2組とIK用分離環境に依存する。G1/カメラ/serialは開かない。
- rate-record-check: 同じ保存画像/身体snapshotを明示的に反復し、ACT/IK30回とSONIC50回を
  独立周期で実行する約1秒のソフトウェア試験。物理エンジンは使わない。実身体が追従する試験ではない。
  `make rate-record-check RATE_SECONDS=30`で30秒/ACT900回/SONIC1500回に延長できる。
  期間は整数1〜30秒に制限。既存の実入力取得コマンドの既定30フレームは変更していない。
- online-fixture-check: 新しい実入力用処理本体に、人工的な履歴/時刻と保存画像を入力する。
  4つの実ワーカーを使い、実機入力は開かない。実測の同期記録や物理応答ではない。
- measured-record-check STATE=...: 保存実身体履歴→ZMQ→観測生成→持続SONICとバッチ計算を照合。
- startup-ablation-verify RUN=...: 保存済み48条件/7200推論の出力・基準・式・集計を再照合。GPU/G1不要。
  起動口・必要ファイル・開始契約は[起動診断](SONIC_STARTUP_ABLATION.md)。
  startup-ablation-runは新規GPU推論専用で、上限150秒＋猶予3秒。既存結果の検討には不要。
- body-lifecycle-check: 制御権/初期参照/停止要求の26単体試験と保存実身体150件の再生。
  `body-lifecycle-verify RUN=artifacts/body-lifecycle/run-6arb9pnq`は既存journalのみ再計算。
- lowcmd-preview RUN=artifacts/body-lifecycle/run-6arb9pnq: 固定SDKのnative object/CRCをファイル専用で照合。
  DDS送信形式ではない。上記2系統はGPU/G1不要。[状態・設定・限界](BODY_LIFECYCLE.md)。
- body-boundary-check / body-boundary-ipc: 保存SONIC/身体150組を新しいrecord-only受信部へ渡す。
  前者はファイル専用、後者はローカルZMQ IPCだけ。後者のsocket bindが制限される環境では承認が必要。
  既存online loopへの接続点も実装したが、既定launcherの配置/動作は変更していない。
  姿勢未到達でgateされること、幅の別経路保持、受信thread終了を確認。実機出力機能ではない。

`config/body-lifecycle.json`は送信なしプロトコルの診断値のみ。
500Hz刻み/ゲイン/姿勢条件を実機安全性や実時間性能の合格として扱わない。
実機の所有権/停止/復帰adapterはbuild-onlyコードあり、実運用は未完。
native writerの送信なし試験は`make body-writer-check`（GPU/G1不要）。
[BODY_WRITER](BODY_WRITER.md)と[当初TODO・現在TODO・判明課題](IMPLEMENTATION_TODO.md)を参照。
diagnostic ACKで物理確認を代替しない。

## 起動・終了と異常処理

`RecordSession`/`RecordGate`はidle→running→stopped、異常時faultへ移行。
helloでsession/schema/record_onlyを確認し、応答のsession/連番/年齢を検査。
重複、古いsession、未来/非有限時刻、遅延、切断は結果を返さず通信資源を閉じる。
faultは再startで解除せず、新しいsessionを明示的に作り直す。自動再接続・再送・自動再開はしない。
`ReferenceMailbox`は異なる処理周期間の最新絶対参照保持を担当する。
h1相対actionはpublish前に一度だけ絶対目標へ変換し、読み出しのたびに積算しない。
重複/計算遅延/有効期限超過を拒否し、返却値変更が内部参照へ波及しないことを6試験で確認。
この部品を使う独立周期処理は反復snapshot条件と、一時RR/1下の3秒実入力で検証済み。
通常優先度/長時間の実入力安定性は未完了。
通常終了はstop/ack後close。ACKに失敗した場合もcloseして異常を残す。
これは記録処理の停止であり、実機の非常停止や脱力を実装/保証するものではない。

GPU保存入力runnerは1回限り。試験中のみ持続ワーカーを使い、常駐サービス/systemd/tmuxは作らない。
GPU側ジョブをtimeout120秒＋強制終了猶予3秒で囲み、ローカルSSH側も180秒で打ち切る。
SSH切断やCtrl-C直後に遠隔プロセスが即終了すると保証しない。上記の遠隔上限が残る。
full-record-checkは3モデルの起動を含めるため、GPU側上限180秒＋猶予3秒、ローカル210秒。
ビルド/モデル配置は既存資産を読み、新しい結果だけを生成する。
失敗時は最新artifactのgpu.log/report.jsonを調べ、出力を実機用に流用しない。
全経路runnerはSSHタイムアウト時もdeployment.jsonに失敗を残し、出力回収を試みる。
回収にも30秒の上限がある。遠隔終了を確認できなければ、その旨を明示して非ゼロ終了する。

## 実施した故障注入

`check-offline`には実際のローカル子プロセスを使う6試験も含む。
正常往復/終了、読取り期限、予期しない終了、過大応答、不正SONIC応答、厳密JSON検査を行う。
重複JSONキー・非有限値（1e999を含む）・非objectを拒否。
SONIC応答異常時は子プロセスを終了し、遅着した応答を次の要求へ流用しない。

実SONIC保存出力2件をローカルZMQ IPCで再生し、正常終了、別session、別連番、
実機出力フラグ、120ms遅延、切断の6条件すべてを検査。
正常時2件、異常時0件を上位へ返し、全通信スレッド終了を確認。
記録: `artifacts/sonic-replay/run-7ol6w3ks/ipc-fault-report.json`。
この試験の鮮度はローカル再生要求の経過時間であり、古い実機記録を新鮮と認定しない。

再現:

```bash
python3 -I scripts/check_recorded_transport.py \
  --input artifacts/sonic-replay/run-7ol6w3ks/input.json \
  --results artifacts/sonic-replay/run-7ol6w3ks/zero.json \
  --report /tmp/sonic-ipc-fault-report.json
```

出力先は未使用ファイルを指定する。

## 他メンバーへの共有

1. README・本手順・sources.lock・requirementsの固定版を共有する。
2. `config/development.json`はホスト固有値を確認して複製する。SSH秘密鍵は共有しない。
3. vendorの固定commit、PIKAアセット出典、SONIC/LeRobotモデルのライセンスを確認する。
4. モデル/学習データ/生成URDF/診断artifactは通常Git外。必要なものを権限確認のうえ別途配布する。
   ACT一式のみなら`make bundle-export OUTPUT=artifacts/new-name.tar.gz`。
   全環境・データを含まない。受領側の新規フォルダで`python3 -I scripts/policy_bundle.py verify`。
   モデルの取得/ビルドはSONIC_BUILD.md。新しいbuildパスを設定ファイルへ反映する。
5. 新規PCではdoctorで不足を列挙する。旧make setupをSONIC環境の自動導入と誤認しない。
   現状は既存2台向けに検証した環境で、クリーンPCの完全自動bootstrapは未提供。

## 実機検証時に残す判断

同時刻の全画像/幅/実身体履歴、実計測に基づく遅延、初期肩角度とIK制限の整合、
全身参照の動的妥当性、衝突、開始/終了と制御権移行、支持/停止手段の実効性、
実機送信の明示許可。これらを単体成功や有限出力だけで合格にしない。
画像取得のためのserial openもMCU resetの可能性があるため、実機作業時にまとめて確認する。

## 持続推論の検証記録

- SONIC単独: `artifacts/sonic-replay/run-q2yvxxlr/service-report.json`。
  30要求すべてバッチ版との関節出力差0、ワーカーexit 0。GPU内ZMQ往復約3.67〜4.42ms。
  `make sonic-service-check INPUT=...`で再実行可能。
- 実SONIC子プロセスの形状違い/重複要求/不正幅は3条件とも出力せずexit 1。
  記録`artifacts/sonic-replay/run-tdl2uj_5/pipe-fault-report.json`。
- 全経路: `artifacts/full-record/run-diyy8jud/outputs/report.json`、
  GPU `/home/gpu-user/g1-pika-training/artifacts/sonic-full-LLf21i/`。
  保存画像0/29番の2組、ACT/IK/SONIC全てexit 0。グリッパ幅は別欄で維持。
  合成ウォームアップ後のACT推論約6.36/6.34ms、全経路約28.51/24.02ms。
  2点だけの計測で周期性能やp95を保証しない。初回ウォームアップなしは約284msだった。
  SONIC要求の鮮度ゲートは生成後の要求区間だけを測定し、元の古い画像や全ACT/IK遅延を新鮮と認定しない。
- 共通ZMQでJSONの`1e999`が無限大になるケースも拒否する。legacy IPC5試験も成功。
- 独立周期: `artifacts/full-record/run-tlvk3izg/outputs/report.json`。
  ACT/IK30回、SONIC50回、3 worker exit 0、制御開始時刻の計画からの最大遅れ約0.225ms。
  同一snapshotを反復していることをscopeに明記。SONIC過去actionは計算出力を履歴に戻すが未駆動。
  短時間・単一静的入力の結果なので実時間保証や身体安定性の合格とはしない。
  応答検査強化後の再試験も成功: `artifacts/full-record/run-oi4rpe04/outputs/report.json`。
  ACT/IK30回、SONIC50回、全3 worker exit 0。G1接続・指令なし。
  30秒延長試験: `artifacts/full-record/run-wi6j6n4x/outputs/report.json`。
  ACT/IK900回・SONIC1500回、全3 worker exit 0、制御開始最大遅れ約0.982ms。
  同一保存入力反復であり、実センサーや身体安定性の検証ではない。
