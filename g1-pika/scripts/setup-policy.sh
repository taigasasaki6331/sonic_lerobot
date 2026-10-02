#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
policy_python="${POLICY_PYTHON:-/home/developer/miniconda3/envs/pika_g1_ik/bin/python}"
"$policy_python" -I -c 'import sys; assert sys.version_info[:3] == (3, 12, 13), "Validated Python is 3.12.13; set POLICY_PYTHON explicitly"'
revision=$(python3 -I -c 'import json; print(json.load(open("sources.lock.json"))["lerobot"]["commit"])')
source_url=$(python3 -I -c 'import json; print(json.load(open("sources.lock.json"))["lerobot"]["url"])')
if [ ! -d vendor/lerobot ]; then
    git init vendor/lerobot
    git -C vendor/lerobot remote add origin "$source_url"
    git -C vendor/lerobot fetch --depth 1 origin "$revision"
    git -C vendor/lerobot checkout --detach "$revision"
fi
test "$(git -C vendor/lerobot rev-parse HEAD)" = "$revision"
git -C vendor/lerobot diff --exit-code HEAD
if [ ! -d .venv-policy ]; then
    "$policy_python" -I -m venv .venv-policy
fi
.venv-policy/bin/python -I -m pip --disable-pip-version-check --no-cache-dir install -r requirements-policy.lock
# The evaluator imports the verified vendor source directly; no editable install
# or separately resolved LeRobot wheel is needed for subsequent clean setups.
.venv-policy/bin/python -I -m pip --disable-pip-version-check --no-cache-dir check
echo 'Ready: make policy-eval (offline recorded observations only)'
