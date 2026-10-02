# Decoupled WBCの初期評価

確認日: 2026-09-14。固定リビジョンは `sources.lock.json` を参照。

## 位置づけ

[公式Decoupled WBC文書](https://nvlabs.github.io/GR00T-WholeBodyControl/references/decoupled_wbc.html)は
Ubuntu 22.04、NVIDIA GPU、Docker/NVIDIA Container Toolkitを前提とする。
このPCはGPU要件を満たさない。ただし実ソースの
`decoupled_wbc/control/policy/g1_gear_wbc_policy.py` はCPUに推論出力を置き、
CPU ONNX RuntimeでBalanceモデルの実行に成功した。
公式Docker構成をこのPCで検証したという意味ではない。

[公式リポジトリ](https://github.com/NVlabs/GR00T-WholeBodyControl)はDecoupled WBCとGEAR-SONICを別コンポーネントとして収録。
今回は `decoupled_wbc` のみを対象とする。

## 付属簡易例からの変更

比較元: `decoupled_wbc/sim2mujoco/scripts/run_mujoco_gear_wbc.py`。
設定: `decoupled_wbc/sim2mujoco/resources/robots/g1/g1_gear_wbc.yaml`。

- YAML内の `ft92.onnx` / `ft109.onnx` は当該ツリーにない。公式制御設定が使う公開Balanceファイルを明示指定。
- 簡易例の `cuda:0` 固定とTorch依存を避け、NumPy＋ONNX RuntimeのCPU providerを明示。
- キーボード監視を省き、ゼロ移動指令、有限時間、計測出力に限定。
- 初期脚関節をYAMLのdefault_anglesへ設定。腕は0。胴体はXMLの初期高さ0.793mから自由運動。
- 86次元観測×6履歴→15次元の脚・腰action。これとLeRobotの10次元TCP actionは別物。
- 初期化後はトルクから `mj_step` で運動を計算。描画だけの関節再生ではない。

## 次に確認する適合性

1. 本体 `G1DecoupledWholeBodyPolicy` と上半身IKの直接接続をCPUで検証済み（詳細はPROGRESS）。公式ROS起動全体は未検証。
2. 旧URDFのPIKA質量・慣性、取付変換、TCPを移植した装着モデルで30秒試験済み。実測の取付金具・配線等は未反映（PIKA_MODEL.md）。
3. 下半身の姿勢変化が教師TCP軌道の基準座標に与える影響を定義する。
4. 10次元actionの回転6Dの並び、合成順、相対基準、グリッパ単位、推論周期を固定する。
5. LeRobotは別環境にする。旧ドキュメントはPython 3.12を想定し、WBCのfull extrasも別のLeRobotコミットを指定するため、一括インストールしない。

## 再利用候補と既存変更

既存PC上の `/home/developer/workspaces/pika_ws2/src/pika_ros` のHEADは指定ブランチのリモートSHAと一致。
ただし未コミット変更・未追跡ファイルが多数ある。変更・移植は未実施。
同HEADの `docs/G1_PIKA_RETARGETING.md` で指定LeRobotと10次元actionを再確認した。

- `src/g1_pika_description/`：URDF、PIKA meshes、生成スクリプトが候補。
- TCP軸は+X上、+Y開閉、+Z前。取付変換の正本は `scripts/generate_urdf.py`。
- グリッパ通信は `src/sensor_tools/src/serial_gripper_imu.cpp` 等が候補。通信コードは本試験に取り込まない。
- ローカルLeRobotのoriginと基準コミットを確認。基準SHAを完全長で固定済み。

## 出典・ライセンス

外部コード・アセット・モデルは元リポジトリから取得し、変更せずvendor配下に保持する。
公開モデルには `policy/NVIDIA Open Model License` が同梱されている。
コードの利用条件は上流の `LICENSE` と `legal/` を参照する。
取得した上流LICENSEはコードをApache-2.0、モデル重みをNVIDIA Open Model Licenseと明記している。
現時点ではPIKA部品の再配布・ライセンス整理は未実施。移植時に各部品のライセンスを個別に確認する。
