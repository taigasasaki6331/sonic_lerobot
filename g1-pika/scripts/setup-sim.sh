#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-balance}" in
    balance) requirements_file=requirements-sim.lock ;;
    wbc) requirements_file=requirements-wbc.lock ;;
    *) echo 'Usage: setup-sim.sh [balance|wbc]' >&2; exit 2 ;;
esac
python3 -I -c 'import sys; assert sys.version_info[:2] == (3, 10), "Use Python 3.10 (validated: 3.10.12)"'
git lfs version
revision=$(python3 -I -c 'import json; print(json.load(open("sources.lock.json"))["wbc"]["commit"])')
source_url=$(python3 -I -c 'import json; print(json.load(open("sources.lock.json"))["wbc"]["url"])')
checkout=vendor/GR00T-WholeBodyControl
if [ ! -d "$checkout" ]; then
    git init "$checkout"
    git -C "$checkout" remote add origin "$source_url"
    git -C "$checkout" fetch --depth 1 --filter=blob:none origin "$revision"
    git -C "$checkout" sparse-checkout set --no-cone /decoupled_wbc/ /docs/source/references/ /LICENSE /legal/ /.gitattributes /.lfsconfig
    GIT_LFS_SKIP_SMUDGE=1 git -C "$checkout" checkout --detach "$revision"
else
    test "$(git -C "$checkout" rev-parse HEAD)" = "$revision" || { echo 'Unexpected WBC revision; preserving checkout.' >&2; exit 1; }
    git -C "$checkout" diff --quiet HEAD || { echo 'Modified WBC checkout; preserving changes.' >&2; exit 1; }
fi
git -C "$checkout" lfs pull --include='decoupled_wbc/sim2mujoco/resources/robots/g1/**,decoupled_wbc/control/robot_model/model_data/g1/**' --exclude=''
if [ ! -d .venv ]; then
    python3 -I -m venv .venv
fi
.venv/bin/python -I -m pip --disable-pip-version-check --no-cache-dir install -r "$requirements_file"
.venv/bin/python -I -m pip --disable-pip-version-check --no-cache-dir check
echo 'Setup complete. Run: make sim (balance) or make wbc (IK + WBC)'
