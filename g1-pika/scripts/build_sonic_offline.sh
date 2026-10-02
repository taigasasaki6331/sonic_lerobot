#!/usr/bin/env bash
# Compile only. Never start G1Deploy or establish a network connection.
set -euo pipefail
if [[ $# != 1 ]]; then
  echo 'Usage: bash build_sonic_offline.sh /absolute/sonic-build-directory' >&2
  exit 2
fi
sonic_stage="$1"
test -f "$sonic_stage/sonic_offline_infer.cpp"
test -f "$sonic_stage/build/src/TRTInference/libTRTInference.a"
sonic_trt_root=${SONIC_TRT_ROOT:-/home/gpu-user/TensorRT-192.0.2.3}
sonic_cuda_root=${SONIC_CUDA_ROOT:-/usr/local/cuda-12.8}
g++ -std=c++20 -O2 "$sonic_stage/sonic_offline_infer.cpp" \
  -I"$sonic_stage/gear_sonic_deploy/src/TRTInference" \
  -I"$sonic_stage/gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/include" \
  -I"$sonic_cuda_root/include" -I"$sonic_trt_root/include" \
  "$sonic_stage/build/src/TRTInference/libTRTInference.a" \
  -L"$sonic_trt_root/lib" -L"$sonic_cuda_root/lib64" \
  -Wl,-rpath,"$sonic_trt_root/lib:$sonic_cuda_root/lib64" \
  -lnvinfer -lnvonnxparser -lcudart -ldl -pthread \
  -o "$sonic_stage/sonic_offline_infer"
