# Validation and remaining acceptance gates

## Automated here

* Schema dimensions, mode one-hot handling, quaternion validity, upper ordering.
* Byte equality with official planner and command builders when GEAR_SONIC_ROOT is set.
* Actual localhost ZeroMQ state -> gateway -> planner roundtrip.
* Fresh-state/action timeout discrimination, kneel hold, slow-walk stop, session/ticket replay rejection.
* Upper-reference slew, velocity limits, mode dwell and transition rejection.
* Dataset timing and metadata validation before LeRobot export.
* Malformed RPC rejection, bounded prediction-noise decoding, per-action observation-age guard.
* Fresh processor factory arguments and saved filenames (mocked, NOT a GPU/model roundtrip).

## Not verified by these tests

1. C++ compilation, encoder/planner checkpoint compatibility and MuJoCo physical trajectories.
2. Physical standing/squatting/kneeling transitions. Command mode is NOT measured posture completion.
3. Joint-specific mechanical/collision limits (broad angle bounds are only input sanity checks).
4. Continuous PICO SMPL -> G1 arm/waist retargeting: converter still needed, stock v3 is rejected.
5. Gear composed-camera adapter and sensor-clock synchronization. Current camera API uses a local
   receive timestamp; it cannot establish camera exposure time or network latency. The OpenCV provider
   is a local-camera example, not a replacement for the official robot camera server.
6. Full π0/π0.5 checkpoint expansion, GPU training/inference and LeRobot video export in the pinned
   Linux environment. Core tests do not install multi-GB models or claim successful fine-tuning.
7. Autonomous mode prediction quality and one-hot diffusion/flow loss behavior after training.

## Sim commissioning sequence

Start official simulator, matching C++ model+observation config, then local gateway. Engage via
official operator controls. Verify fresh state before arming a producer. Begin with held measured
upper references; then small arm/waist changes at IDLE, slow walk and stop, squat and IDLE,
double-kneel and IDLE. Wait for each transition to settle. Remove GPU input and verify local
planner stream persists with zero movement. Restart producer: old epochs/chunks must fail.
Test gateway death separately with the C++ patch. Record actual posture/foot contacts and tracking
error, not just packet receipt, before marking this physically tested.

## Scope of the first push

This is a reviewable bridge core and data/inference adapters, not a completed end-to-end PICO
teleoperation product. Missing integration items above are intentionally visible rather than
silently generating invalid upper targets or synthetic measured state.
