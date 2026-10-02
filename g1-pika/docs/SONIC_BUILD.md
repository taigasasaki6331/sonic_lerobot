# SONICビルド・モデル単体確認（2026-09-24）

## 結果

- 固定コード087f9ac0のg1_deploy_onnx_refをgalleriaでビルド成功。実行していない。
- low_latencyモデルをHF revision6733128a3d8a523b1418b06bca3cdf61c8b0987fで固定。
- encoder/decoder/observation_config/LICENSE/config.jsonのみ取得。サイズと上流LFS/Git hashを照合。
- TensorRT10.13.3.9でengine構築と合成入力単体推論成功。encoder64出力、decoder29出力が有限値。
- モデル同士を実観測で結合した試験ではない。姿勢保持・追従・実機安全性は未検証。
- 既存単体36件成功。実機/DDS接続、シミュレーション、OS変更なし。

## 配置

- ローカルログ: artifacts/sonic-build/run-ajg4uq3q/
- GPUビルド: /home/gpu-user/g1-pika-training/artifacts/sonic-build-PCETNV/
- GPUモデル: /home/gpu-user/g1-pika-training/artifacts/sonic-models-6733128-low-latency/
- GPU単体結果: 上記モデル内smoke-h72vaepx/（engineはGPU固有成果物として扱う）

## 再実行

ローカルから `make sonic-build`。専用新規ディレクトリへコピーしてビルドのみ実行。
galleriaの依存はCUDA12.8.93、TensorRT10.13.3.9、ORT C++1.16.3、g++11.4.0。
ROS2は無効。CMake4.4向けにCMAKE_POLICY_VERSION_MINIMUM=3.5を指定。
GoogleTestは本家CMakeのv1.14.0取得を利用。すべての推移依存の完全な再現固定は未完了。

GPUでモデル単体試験を再実行する場合（制御バイナリは起動しない）:

```bash
env LD_LIBRARY_PATH=/home/gpu-user/TensorRT-192.0.2.3/lib:/usr/local/cuda-12.8/lib64 \
  python3 -I /home/gpu-user/g1-pika-training/scripts/smoke_sonic_tensorrt_20260924.py \
  --models /home/gpu-user/g1-pika-training/artifacts/sonic-models-6733128-low-latency
```

## 実装と未完了

上流ソースは無改変。SDK3ライブラリはGPU側ステージに限定してLFSポインタhashと照合して取得。
tigerのgit-lfs取得が長時間未完了のため中断し、公開media URLで同一内容を取得した。
旧学習環境へ追加pip/aptは行っていない。

今回のlow_latency選択は参照streamの初期検証用。既存LeRobotモデルの互換を保証しない。
encoder入力1247、decoder入力994。G1関節参照は10未来フレームstep1であり、
SMPLの4フレームと混同しない。既存約5Hzの実記録を50Hz実時間履歴と扱わない。
次は本家観測生成を再利用する送信なし経路と、TCP→全身参照の成立を検証する。
