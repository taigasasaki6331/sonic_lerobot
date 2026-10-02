#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Never use the local GPU setup, SSH, DDS, cameras, or serial ports here.
command -v g++ >/dev/null
command -v gcc >/dev/null
python3 -I -c 'import sys; assert (3,10) <= sys.version_info[:2] <= (3,12), "Use Python 3.10–3.12"'
python3 -I -c 'import ctypes; ctypes.CDLL("libzmq.so.5")'
test -f vendor/GR00T-WholeBodyControl/gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/include/policy_parameters.hpp || {
    echo 'Missing cloud source subset. Use the prepared cloud export, not git archive of old HEAD.' >&2
    exit 2
}
if [ ! -d .venv-cloud ]; then python3 -I -m venv .venv-cloud; fi
.venv-cloud/bin/python -I -m pip --disable-pip-version-check install -r requirements-cloud.lock
.venv-cloud/bin/python -I -m pip --disable-pip-version-check check
echo 'Ready: make cloud-check (CPU, no robot/GPU access)'
