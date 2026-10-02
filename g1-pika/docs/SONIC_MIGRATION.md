# GEAR-SONIC移行計画（2026-09-24）

## 方針

LeRobot＋PIKAを維持し身体制御をSONICへ接続。シミュレーションとリモコン統合なし。
実機動作は別途許可が必要。旧Decoupled WBCは保存するが、その修正を必須工程にしない。

## 実装・環境確認（2026-09-24）

- galleria SSH復旧。GPU RTX5060Ti、driver580.178.04。
- CUDA12.8.93は/usr/local/cuda-12.8/bin/nvccに存在（SSH PATHにはない）。
- TensorRT10.13.3.9は/home/gpu-user/TensorRT-10.13.3.9に存在。ヘッダと共有libを確認。
- ONNX Runtime C++1.16.3は/opt/onnxruntimeに存在。上流install_deps.sh指定版と一致。
- g++11.4.0、cmake4.4.0、just、Eigen3.4、yaml-cpp0.7、libzmq4.3.4、zlib開発版あり。
- 追加インストール/OS変更なし。ビルド成立・GPU実推論は未確認。
- SONICのsrc/cmake/scripts、Python utils、手順書を部分checkout。モデルは取得しない。
- sonic_reference.pyは上流packerをhash確認して直接使用し、v1 bytesを生成するだけ。
  関節順は固定policy_parameters.hppのmujoco_to_isaaclabを読み取り、逆向き混同をテスト。
  q/dq全29関節、wxyz、frame indexを検査。速度や下半身参照は自動捏造しない。
- 36単体試験成功。これはPythonのwire形式検証で、C++受信・encoder/decoder実行ではない。

次はC++ビルド用の残りソース/依存の確認、checkpoint固定、記録参照での推論。
動作参照生成（TCP→全身参照）と開始・終了の実機適合は未完了。

## 互換性

既存固定コミット087f9ac01d46f6d8e4d0b73c01ae64799f292a38のtreeには
gear_sonic/gear_sonic_deployが存在する。従来はsparse checkoutで未配置。
SONICソースを追加取得し、コード版を無条件更新しない。

公式VLAは64次元token＋左右7関節hand。既存10次元ACTとは直接互換でない。
公式stream v1はIsaacLab順の29関節位置/速度を要求。ハード順からの変換が必要。
全29関節に意味のある参照が必要で、腕以外のゼロ埋めで代用しない。
候補はTCP→IK→全身参照→SONIC encoder/decoder。成立は未確認。
PIKA幅はDex3フィールドへ詰めず、別経路で処理する。

## 工程・完了条件

1. 固定ソース/ライセンス/入力/依存を照合し、GPU PCの導入差分を特定。
2. 座標・関節順変換と参照形式を通信なしで試験。
3. 隔離環境でSONICをビルド・ロードし記録入力から出力を検証。
4. LeRobot→参照→SONIC→出力保存を接続し、開始/終了/通信断を検証。
5. 現地確認を集約し、支持・停止方法・許可を確認後に限定実機試験。

記録再生では立位安定性/停止性能は証明できない。公式はシミュレーションを推奨するが
ユーザー要件で実行しない。参照生成が成立しなければ流用限界を明示する。
コード/モデル/設定の版と停止理由を保存。未検証の実機起動を通常手順へ掲載しない。

## 出典（オンライン版は固定コードとの照合が必要）

- https://github.com/NVlabs/GR00T-WholeBodyControl
- https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/vla_inference.html
- https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/zmq.html
- https://nvlabs.github.io/GR00T-WholeBodyControl/getting_started/installation_deploy.html
