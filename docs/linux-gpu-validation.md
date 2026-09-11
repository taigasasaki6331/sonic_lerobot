# Linux GPU validation handoff

This is an uncommissioned integration core. Do not connect a real robot for initial tests.
Windows CPU tests do not verify CUDA, model quality, C++ compilation or physical stability.

## 1. Reproduce the CPU checks first

```bash
git clone https://github.com/taigasasaki6331/sonic_lerobot.git
cd sonic_lerobot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
git clone https://github.com/NVlabs/GR00T-WholeBodyControl.git ../gear-sonic
git -C ../gear-sonic checkout 087f9ac01d46f6d8e4d0b73c01ae64799f292a38
GEAR_SONIC_ROOT=../gear-sonic pytest -q
git -C ../gear-sonic apply --check ../sonic_lerobot/patches/gear-sonic-timeout-hold.patch
```

Record OS, GPU/VRAM, NVIDIA driver (`nvidia-smi`), Python and git revisions.
Install Gear-SONIC's own environments, assets and deployment dependencies following its pinned
instructions. Keep its environment separate from the LeRobot environment if dependencies conflict.
The timeout patch is opt-in: apply and compile it in a disposable Gear checkout for the simulator.
An apply check alone is not a compile or safety test.

## 2. Learning environment

Install `pip install -e '.[learning]'`, then the pinned LeRobot pi0/pi05 model-specific dependencies
and compatible CUDA PyTorch/FFmpeg. Check `torch.cuda.is_available()` before loading models.
Use README's dataset export, prepare and training commands. A genuine collected dataset is required;
the current PICO continuous retargeter and Gear camera adapter are not bundled.
Do not substitute zero joint targets or synthetic data for deployment validation.

Preparation must produce config/model weights, sonic_schema.json, policy_preprocessor.json,
policy_postprocessor.json and associated processor state files. Load these with the pinned
LeRobot factory, run one training step, save, reload, and check output shape [B,T,48] and finite
values. Repeat for BOTH pi0 and pi05. This has not been executed on the Windows development host.
Verify dataset statistics and absolute-action settings survive reload. Keep the schema file with
the final trained checkpoint; it is not automatically copied by upstream training.

## 3. Simulator acceptance

Follow README's official sim/deployment commands; keep gateway on the deployment host.
Start with held measured upper references, then small arm/waist changes in IDLE. Confirm joint
ordering, reference tracking and finite measured feedback before trying slow walk and stop.
Then test squat and double kneel separately, waiting for each transition to settle.

For inference use a trained matching checkpoint and a real timestamped RGB provider. Measure
warmup, median/worst inference latency and repeated refreshes; the default observation-age limit
is 0.4 seconds, not a guarantee that an arbitrary GPU meets it. Check repeated HOLD/re-arm cycles.

Independently interrupt the inference producer, state stream, and gateway process. Check zero
movement, held upper reference and expected static mode; also inspect actual posture, contacts
and tracking errors. Gateway death requires testing the C++ fallback, not the Python watchdog.
Restarted clients must explicitly re-arm. Do not auto-resume on reconnection.

## 4. What to send back

Send revision hashes, hardware/software versions, commands, full traceback or compiler errors,
pytest output, inference latency statistics and simulator logs/video. Exclude credentials.
Report each gate as passed/failed/not run. Real-robot trials require a separate supervised safety
procedure, suitable support/emergency stop and successful simulator checks; no fall prevention
claim is made by this repository.
