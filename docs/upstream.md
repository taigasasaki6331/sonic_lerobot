# Pinned upstream evidence

GEAR-SONIC: `087f9ac01d46f6d8e4d0b73c01ae64799f292a38`.

* `gear_sonic/utils/teleop/zmq/zmq_planner_sender.py`: builder, 1280-byte header, planner v1.
* `gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/include/input_interface/zmq_manager.hpp`:
  parses 17 upper positions, tracks stale planner input, defaults to IDLE after 1s.
* `gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/include/localmotion_kplanner.hpp`:
  official locomotion enum 0..26 (web tutorials list fewer modes).
* `gear_sonic/scripts/pico_manager_thread_server.py`: FeedbackReader's UPPER_INDEX order;
  full-body pose publisher initializes 29 joint positions to zero and fills wrists only.
* `gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/include/output_interface/output_interface.hpp`:
  `body_q_measured` already has default offsets added; do not add them again.
  `base_trans_measured` is fixed, not a localization estimate.

LeRobot: `b6ec0060779550c0a157ae34feb89e0cf86012a8`.

* `policies/pi0` and `policies/pi05`: action projections padded to max_action_dim;
  pi0 also has state_proj. pi05 encodes state through its processor.
* `policies/factory.py`: get_policy_class / make_pre_post_processors.
* `datasets/lerobot_dataset.py`: create / add_frame / save_episode / finalize.

No upstream source is vendored. Codec behavior is reproduced and checked against the pinned builder.
