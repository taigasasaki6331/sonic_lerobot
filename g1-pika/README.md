# g1-pika

> 公開用コピー：ネットワーク値・機器識別子・ローカルパスは例へ置換。保存試験結果は原本の記録で、例設定で実機試験した証拠ではありません。クラウドから機器接続・実機指令を行わないでください。


Unitree G1＋AgileX PIKAを **LeRobot＋GEAR-SONIC** で動かすための開発環境。
移行開発中。**SONICの実機動作は未検証、動作指令用の起動コマンドは未提供**です。

## クラウドで開発を続ける（GPU・G1不要）

現在の未コミット実装を含む引き継ぎ用ソースを `make cloud-export OUTPUT=新規ディレクトリ` で作成。
非公開GitHubへ配置後、クラウドでは `make cloud-setup` → `make cloud-check`。
CPU・送信なし検証用で、データ本体・重み・鍵は含めません。GPU/実機検証は接続できる環境で行います。
[移行手順とクラウド用の開始指示](docs/CLOUD_HANDOFF.md)。

## まず動作させる（現行はMuJoCo、G1不要）

```bash
make run
```

galleriaで既存モデルを使い、**LeRobot→IK→SONIC→native身体コマンド→MuJoCo**を30秒実行します。
起動・終了と動画保存まで一括。短く試す場合は`make run RUN_SECONDS=3`。
最終確認：[30秒の動画](artifacts/sonic-mujoco/run-u9gljra3/outputs/simulation.mp4)、
[実行結果](artifacts/sonic-mujoco/run-u9gljra3/outputs/report.json)。立位と腕の運動を確認済み。
保存RGB/幅仮定/固定PIKAモデルでの検証で、実カメラ・把持・実タスク成功の証明ではありません。
実機送信モードはありません。実G1の初期姿勢・制御権・停止経路の統合は残っています。

G1側runtimeの起動から停止までを、G1なしで確認する入口：

```bash
make body-runtime
make body-runtime-expiry
```

同一ホスト状態→初期参照/姿勢確認→ZMQ目標→native owner loop→停止要求を一括実行。
人工入力・メモリ出力だけを使います。[実装範囲・実入力への接続](docs/BODY_WRITER.md#統一起動経路)。
実SDKの送信/制御権・物理停止は未検証のままです。

## 到達点と検証範囲

実入力の記録専用起動は実装済み。一時RR/1適用下で3秒のG1入力試験が完走しました。
計算目標の実姿勢との差・URDF範囲超過は未解決です（[記録監査](docs/TARGET_AUDIT.md)、[実入力統合](docs/ONLINE_RECORD.md)）。
起動履歴と3参照の48条件比較を完了。paddingだけでは超過は解消せず、
配列の照合結果と未再現の開始条件を[起動診断](docs/SONIC_STARTUP_ABLATION.md)に整理しました。
実機移行には[起動・停止の確認事項](docs/SONIC_STARTUP_BOUNDARY.md)が残っています。
MuJoCo動力学閉ループを追加し、固定PIKA＋保存RGBのLeRobot ACT→IK→SONICを
30秒完走しました（ACT900回、SONIC1500回）。実機・視覚タスク成功とは別です。
教師再生も立位で完走しましたが、起動TCP誤差の基準は未合格。
[再現コマンド・動画・検証範囲](docs/SONIC_MUJOCO.md)。実機側の実装も継続します。
起動・停止要求の状態機械とLowCmdメモリ/CRCの送信なし検証を追加しました。
物理停止・制御権移行の実運用は未検証です。[範囲と再現](docs/BODY_LIFECYCLE.md)。
G1側の独立LowState監視とGPU→G1 ZMQ記録受信も配置・検証済み。
保存SONIC150件は全件保留、実機指令0。状態更新停止時の診断watchdogも確認しました。
LowState受信CRCの実G1照合も成功。身体SDKアダプターはbuild-onlyで追加し、
G1でコンパイル検査済みですが、実出力へは未接続です。[SDK接続部](docs/BODY_IO_ADAPTER.md)。
native 2ms writerの送信なし実装・故障注入も追加しました。[範囲と限界](docs/BODY_WRITER.md)。
**[当初TODO・現在の進捗・判明した課題](docs/IMPLEMENTATION_TODO.md)**を一覧で管理しています。

## 構成

- **galleria（GPU PC）**：LeRobot学習・推論、参照変換、観測生成、SONIC推論。実機出力は未接続。
- **G1搭載PC**：カメラ・PIKA接続、状態取得。GPU PCとは有線LAN。
- **tiger**：編集・配置・診断。制御通信の中継には使いません。
- PC間はZMQ、身体の低レベル送信はWBCに集約します。

既存actionは相対位置3＋回転6D＋幅1の10次元で、SONIC公式VLAの78次元とは非互換。
TCP→本家IK→SONIC関節参照入力の保存入力診断は実装済み。実時間・実機での成立は未検証です。
PIKA幅は別経路で扱い、Dex3の7関節ハンドとして扱いません。

PIKA単体の開閉と電流上限によるトルク調整は
[`control_pika_gripper.py`](scripts/control_pika_gripper.py)で指定できます。
既定は送信なしのプレビュー。実機操作・依存・N·m換算の条件は
[PIKA単体操作](docs/PIKA_GRIPPER_CONTROL.md)を参照してください。
`interactive --port /dev/ttyUSB0 --execute` で接続を維持した対話操作もできます。
`open` / `close` / `move` / `current` / `status` を入力し、`quit` で無効化・切断します。
`grip 0.2` で段階的に閉じ、物体に当たっても入力へ戻って電流を調整できます。
`--grip-speed` / `set grip-speed` は閉じ目標の変化率です。実機の急動作の原因は未確定で、
実測速度の上限や跳ねの解消を確認した機能ではありません。
受信JSONの欠損からの復旧を修正し、異常値は最終JSONに具体的な値と受信データを表示します。
この単体スクリプトはSONIC/身体制御の出力とは接続していません。

## 既存データ・学習済みモデル

実演データは準備済み（valid49、49episode/10881frame、学習39・検証5・テスト5episode）。
所在・固定manifestは `assets/datasets/` と [学習記録](docs/GPU_TRAINING.md)を参照。
既存ACT候補は `artifacts/full-rgb-residual/run-xg1fn3b_/pretrained_model`。
学習完了と実タスク品質の合格は区別します。データ再指定・再収集は不要です。
モデル・正規化・幅codec・RGB前処理を `config/policy-bundle.json` で一式固定しています。

```bash
make bundle-check
make bundle-export OUTPUT=artifacts/new-diagnostic-act.tar.gz
```

GPU/G1不要。共有パッケージにデータ・認証情報・他ログは含めません。
実機用ランチャーではありません。[照合・共有手順](docs/POLICY_BUNDLE.md)。

## セットアップと診断

既存環境を上書きせず、リポジトリ直下で実行します。

```bash
make doctor
make check-offline
make check-runtime
make full-record-check
```

`make body-lifecycle-check`は初期参照・期限切れ・停止要求を保存身体入力で検査します。
`make lowcmd-preview RUN=artifacts/body-lifecycle/run-6arb9pnq`はLowCmdのデータ構造とCRCを照合します。
どちらもGPU/G1への接続・シミュレーション・実機送信はありません。
`make body-boundary-check`は保存SONIC出力→身体受信部の接続、
`make body-boundary-ipc`は同じ接続をローカルZMQで検査します（実機接続なし）。
G1起動・galleriaとの有線接続後、`make body-local-check`で保存SONIC150件の記録受信、
`make body-local-expiry-check`で状態転送停止時の独立監視を再現できます。
カメラ/シリアル/実機動作指令なし、試験後は対象プロセスを終了します。
`make lowcmd-abi-check`はG1/aarch64とx86_64の保存LowCmdデータ/CRCを比較します。
DDS送信なしで1540件の一致を確認済み。受信LowStateのCRC確認とは別です。
現在のCRC必須検証は`make body-local-crc-check` / `make body-local-crc-expiry-check`。
`make body-io-build-check`はG1でSDK接続コードをobject compileするだけで、実SDKを起動しません。
`make body-writer-check`はtigerでnative周期/入力異常/停止要求を疑似通信先へ実行し、記録を保存します。
GPU/G1/SDK実行不要。実機500Hzや物理停止の認定ではありません。

`doctor`はローカルのソース・ツール・依存候補を読み取るだけ。
GPU PCでも同じスクリプトで配置先を診断できます。
`check-offline`は既存 `.venv` を使い、通信・シミュレーション・実機送信なしで試験します。
`check-runtime`はローカルZMQ IPCで起動/終了・切断を検査します（G1接続なし）。
`make startup-ablation-verify RUN=artifacts/sonic-startup-ablation/run-ofbwc_6t`は
保存済み48条件の結果を再検証します（GPU/G1不要）。
`full-record-check`は保存画像→LeRobot→本家IK→ZMQ→実SONIC推論をgalleria内で再実行し、全ワーカーを終了します。
画像・IK用分離環境・モデルは既存GPU配置を使用します。G1は不要です。
`make rate-record-check`で保存snapshotを反復した30Hz/50Hz独立周期の短時間試験もできます。
`make rate-record-check RATE_SECONDS=30`で30秒まで延長できます（実機・物理エンジン不使用）。
`make online-fixture-check RATE_SECONDS=30`は実入力用の処理本体を人工入力で検証します。
`make trajectory-fixture-check RATE_SECONDS=3`は時間整合した関節参照を同じGPU経路で検証します。
結果・残る目標差は[関節参照](docs/JOINT_REFERENCE.md)を参照してください。
モデル一式の照合を含む4worker処理は、人工入力30秒/ACT903回・SONIC1500回で完走しました。
実入力の30秒安定性を確認したという意味ではありません。[検証記録](docs/POLICY_BUNDLE.md)。
新規PCの完全自動setupは未提供です。共有・再構築条件は[開発手順](docs/DEVELOPMENT_RUNBOOK.md)を参照し、旧 `make setup` で代用しません。

コード・SONICモデルrevision/hash・主要ビルド依存は `sources.lock.json` に記録しています。
galleriaではCUDA12.8、TensorRT10.13.3.9、ONNX Runtime C++1.16.3を確認済み。
関節参照のパケット生成、C++ビルド、TensorRTの合成入力単体推論は成功。
保存画像2組のLeRobot再推論→本家IK→SONICまでファイル専用診断で完走しています。
同時取得した実画像・実身体履歴の記録専用統合は、上記3秒試験で完走しました。
実機動作・長時間運転の検証は未完了です。
実機状態388フレームから実履歴379組のencoder→decoder連結推論を確認済み。
参照は実測姿勢固定、過去SONIC actionはゼロの送信なし診断で、閉ループ検証ではありません。
詳細は [観測・連結推論の範囲](docs/SONIC_OBSERVATION.md)。

保存済み身体状態の比較推論は次の1コマンドで再現できます（galleriaが必要、G1不要）。

```bash
make sonic-replay STATE=artifacts/sonic-state/sonic-state-McdQQD/state.jsonl
```

過去actionをゼロ固定する条件と、直前の計算出力を戻す条件を比較し、
`artifacts/sonic-replay/`へ結果・関節別差・計測時間を保存します。
既存GPUビルド/モデルの配置に依存します。新規PC用の汎用インストーラーではありません。

保存LeRobot action→TCP→IK→SONICの診断:

```bash
make sonic-tcp-check INPUT=artifacts/sonic-tcp/reinferred-endpoints-20260924.json
```

幅は別データとして維持。脚・腰固定の運動学的候補で、動的な全身軌道ではありません。
結果・取得手順・残課題は [TCP統合診断](docs/SONIC_TCP_PIPELINE.md) を参照。
公式資料のTensorRT指定はx86_64が10.13、Jetsonが10.7です。固定ソースとの照合が必要です。
`nvidia-smi`のCUDA表示はToolkit/TensorRTが導入済みという意味ではありません。

## 設定・入力確認・ログ

- SONIC保存入力診断の設定：`config/development.json`（GPU接続・ビルド/モデル・CUDA/TRT）。
  record_only以外は拒否。秘密鍵やパスワードの内容は保存しません。
- 起動/終了・故障注入・別PCへの共有：[開発手順](docs/DEVELOPMENT_RUNBOOK.md)。
- ACT候補の配置先とファイル固定：`config/policy-bundle.json`。起動前にローカル/GPU両方で照合します。

`make sonic-build` はgalleriaの新規フォルダでコンパイルのみ行います（SSHと取得通信あり）。
制御プログラムは起動しません。ローカル結果は `artifacts/sonic-build/`。
モデル単体確認の手順と配置は [SONICビルド記録](docs/SONIC_BUILD.md) を参照。

- 接続先・デバイス：`assets/network/g1-runtime-access.json`
- ローカルの入力一覧：`make input-check`
- 身体状態だけ8秒取得：`python3 -I scripts/record_sonic_state.py`（tigerから実行、G1起動が必要）。
  カメラ・シリアル・動作指令は使わず、結果は `artifacts/sonic-state/`。取得後の解析はG1不要。
- 既存の実入力統合：`make input-shadow`。G1/GPUへ接続しカメラ・右シリアルを開きます。
- 結果：`artifacts/`。認証情報は記録しません。

シリアルopenにはリセットの可能性があります。受信専用でも無影響とは限りません。

## 起動・終了と制約

既定の `make` はヘルプのみ。SONIC deploy/launcherは起動しません。
記録専用の開始/終了・古い入力拒否・異常時closeは検証済み。実機の制御権移行・停止は未検証です。
診断ジョブはGPU側120秒（全経路試験は180秒、強制終了猶予3秒）で打ち切る設定です。
起動履歴の48条件比較はGPU側150秒です。
正常終了時は全ワーカーの終了を確認します。SSHタイムアウト時は遠隔終了確認済みとは扱いません。
SSH切断やプロセス終了を物理的安全停止と扱いません。

受信プロセスの一時RR/1優先度で、G1の実入力3秒試験が完走しました（ACT/IK93回・SONIC150回、全プロセス正常終了）。
魚眼の15fps問題は受信buffer4で約30fpsへ改善。露出/FPSは元の設定を維持しています。
通常優先度では3秒試験が失敗しています。一時優先度は解除済みで、長時間安定性・実機動作は未検証です。
持続推論・独立周期処理は保存入力条件で検証済みですが、実機入力・低レベル送信の完成とは扱いません。
実入力用の単一起動手順と読み取り承認境界は[実入力統合](docs/ONLINE_RECORD.md)にまとめています。

2026-10-01方針更新：MuJoCo統合検証と実機側実装を並行して進めます。
実機動作指令は送信しません。GPU内のMuJoCoは`make sonic-policy-sim SIM_SECONDS=30`。
リモコン統合なし。実機試験は支持・停止方法の確認と明示許可後に実施します。
旧WBCの初期目標差は未解決で、旧試験結果をSONICへ流用できません。
PIKA形状・質量・幅較正と、学習モデルの実タスク成功も未確認部分があります。

## トラブル対応・詳細

`.venv`やSONICソースの欠落は診断出力を確認してください。旧vendorの上書きや
OS/ドライバの自動更新はせず、配置先の不足依存をまとめて導入します。

- [移行計画・互換性](docs/SONIC_MIGRATION.md)
- [進捗](docs/PROGRESS.md)／[引き継ぎ](docs/HANDOFF.md)
- [実入力統合](docs/REAL_INPUT_INTEGRATION.md)／[右グリッパ確認](docs/RIGHT_GRIPPER_MOTION.md)
- [旧WBC開始調査](docs/WBC_STARTUP_REVIEW.md)／[旧README](docs/README_LEGACY.md)
