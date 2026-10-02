# SONIC観測・連結推論診断（2026-09-24）

## 実装

最新の追加検証: 本家`math_utils.hpp`を直接includeした通信機能なしC++と比較し、
正規化したランダム姿勢512組で相対回転6D・重力方向が絶対誤差2e-14以内で一致。
ヘッダーhashを固定。これは回転演算部分の照合で、全Gather*の同等性証明ではない。
関節順/default subtraction/履歴順は固定GatherRobotStateToLogger/GetLatestとソース照合。
StateLoggerはdtとsample_dtが一致すると直近フレームをstride=1で選び、oldest-firstに反転する。
現在の比較は履歴が揃った10フレーム以降のみ。起動直後のゼロpadding挙動は対象外。

`sonic_observation.py`は固定G1DeployのGather*式に従うmode0専用の観測組立。
上流コードhashを検査し、配列/有限値/正規化クォータニオンを検証する。
encoder1247、decoderはtoken64＋履歴930。非選択teleop/SMPL欄は本家同様ゼロ。
姿勢参照は絶対関節角、状態履歴はdefault_anglesを引いたIsaacLab順。
回転6DはSONIC用の最初の2列を行順展開。LeRobotの列連結6Dと混同しない。
履歴は古い→新しい順で、last_actionは正規化前のSONIC出力（IsaacLab順）。

`sonic_offline_infer.cpp`は本家TRTInferenceEngine/ConvertONNXToTRTと
関節変換/出力スケールを再利用し、ファイル入力→encoder→decoder→ファイル出力のみ実行。
DDS/SDKをリンクせず、カメラ・シリアル・ネットワークを開かない。
観測組立式の単体確認は行ったが、G1Deploy gathererとの全入力での数値同等性は未証明。

## 実履歴取得と連結推論（最新）

G1起動後に既知ホスト鍵でSSH確認。受信専用Cコードを一時フォルダでビルドし、
8秒だけLowStateを受信。388フレーム、最大間隔21.629ms、10フレーム窓379組すべてが
20ms±2msの間隔条件を満たした。厳密な周期50Hzや実時間保証を示すものではない。
配置・ビルド・取得はgalleria上の計測区間で9.387秒（初回SSHやローカル回収は別）。
timeoutによる終了コード124は8秒制限の予定どおり。終了後pgrepで受信プロセスなしを確認。
動作指令・モード変更・カメラ・serial操作なし。CRC検証は未実装。

`prepare_sonic_history_diagnostic.py`で実際の10フレームのq/dq/gyro/姿勢履歴を使用。
参照は各窓末尾の実測姿勢を固定し、過去SONIC actionはゼロとして明示。
G1はこの出力で動いていないため、閉ループ履歴・LeRobot統合の検証ではない。
GPUで379組すべてencoder→decoder推論完走、有限出力。
目標−実測最大0.608018rad、初回0.605433rad。hardware_ready=falseを維持。
単体試験45件成功。build_sonic_offline.sh自体も今回実行成功。

保存先: `artifacts/sonic-state/sonic-state-McdQQD/`
（state.jsonl、report.json、history-input.json、history-output.json）。
GPU側: `/home/gpu-user/g1-pika-training/artifacts/sonic-state-McdQQD/`。
状態SHA256: `9e6fb54e064f99a49dc5f55f0da76303a264fbddc634dfc6e78de8731b234ee6`。
今回の取得後はG1電源不要とユーザーへ連絡済み。

```bash
python3 -I scripts/record_sonic_state.py
# 出力された今回の保存先を --input に指定。--output は新規ファイルにする。
.venv/bin/python -I scripts/prepare_sonic_history_diagnostic.py \
  --input artifacts/sonic-state/sonic-state-McdQQD/state.jsonl \
  --output /tmp/sonic-real-history-input.json
```

モデルの実ファイル名は`low_latency/model_encoder.onnx`と`model_decoder.onnx`。
初回はencoder.onnxという誤った引数で停止し、manifestの名前に訂正して完走した。

## 過去action履歴の比較（最新）

`make sonic-replay STATE=.../state.jsonl`で入力作成→GPUで専用C++ビルド→
2条件の推論→結果回収→関節別統計まで実施。G1は接続しない。
ONNX hashを実行前に照合。各回新規ディレクトリ、入力SHA/コードSHAとログを保存する。

実行済み結果: `artifacts/sonic-replay/run-bxnd4ew3/report.json`。
GPU: `/home/gpu-user/g1-pika-training/artifacts/sonic-replay-fqkEVb/`。

|条件|窓数|最大目標−実測差|最大差の関節|encoder＋decoder p95|
|---|---:|---:|---|---:|
|過去actionゼロ固定|379|0.608018rad|左肘|0.551ms|
|計算した出力を次の履歴へ戻す|379|1.109443rad|左足首pitch|0.551ms|

両条件の初回差は同一0.605433rad。計算出力を戻す条件は、初期履歴ゼロから
各推論後に29値を追加し、次回入力で使用する。系列欠落は拒否する。
ただし身体記録は実出力に応じて変化しないため**閉ループではない**。
差の増加から実機の不安定性や観測バグが証明されたわけではない。
またPD位置目標と実測値の差は実タスクの追従誤差そのものではなく、ゼロになるとは限らない。
今回の差を小さく見せるclip/ゲイン変更/モデル変更は行っていない。
p95はGPU内の連結推論区間のみ（同期とCPU処理込み）。通信込み50Hz達成の証明ではない。
hardware_ready=false、実機指令なし。単体49件成功。

## 以前のsnapshot診断結果と限界

保存実入力は約5Hzであり、実際の50Hz履歴がない。診断では各snapshotを10回繰り返し、
過去SONIC actionはゼロとして明示的に合成。production用データとは扱わない。
require_50hzは5Hz列を拒否する。記録を補間しただけで実履歴合格にはしない。

- 実測姿勢の固定参照: 30件の連結推論完走、全出力有限、目標−実測最大0.653275rad。
- 記録LeRobot action→既存の未合格IK候補: 30件完走、全出力有限、差最大0.915419rad。
- 候補IKは元のpassed=falseを維持。候補参照は各フレームで定姿勢と仮定した診断であり、
  妥当な未来軌道・実時間推論・機体の追従を示さない。LeRobot推論の再実行もしていない。
- hardware_ready=false、出力ファイルだけ。有限値は制御品質の合格基準ではない。
- 単体試験41件成功。シミュレーション・実機指令なし。

結果はartifacts/sonic-build/run-ajg4uq3q/のsnapshot-*/candidate-*。
GPU側はsonic-build-PCETNV。既存trtexec engineは本家キャッシュと異なる。
本家は64byte hash付き.trtを使うため、本家変換関数で再生成した。
builder動的ロードにはプロセス限定LD_LIBRARY_PATHのTensorRT/libも必要。

## 再現

入力生成はローカルの既存.venvで行う（物理エンジンはimportしない）:

```bash
.venv/bin/python -I scripts/prepare_sonic_snapshot_diagnostic.py \
  --input artifacts/state-shadow/state-shadow-Pysyga/live-report.json \
  --output /tmp/sonic-snapshot-input.json
```

出力先は新規ファイルに限定。`--candidate-reference`で記録再生候補を診断に指定可能。
GPU作業フォルダへC++と入力を配置し、`build_sonic_offline.sh`でコンパイルする。
GPU専用実行ファイルの引数はencoder.onnx decoder.onnx input.json output.json。
LD_LIBRARY_PATHはTensorRT10.13.3.9/libとCUDA12.8/lib64を指定。通常deploy.shを起動しない。

## 次に必要なもの

1. 実履歴取得は完了。次は本家Gather*との数値同等性と初期出力差の切り分け。
2. 初期履歴/直前出力の扱いと、TCP actionから制約を満たす全身参照の生成。
3. 全経路を正しい時刻・座標で接続した送信なし検証。その後に実機段階。

G1起動前のSSH timeoutは解消済み。取得後は再接続せず保存データで作業可能。
