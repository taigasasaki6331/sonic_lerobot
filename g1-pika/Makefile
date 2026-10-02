.DEFAULT_GOAL := help
.PHONY: cloud-setup cloud-check cloud-export
CLOUD_PYTHON ?= .venv-cloud/bin/python
cloud-setup:
	bash scripts/setup-cloud.sh
cloud-check:
	$(CLOUD_PYTHON) -I scripts/check_policy_bundle.py
	$(CLOUD_PYTHON) -I scripts/check_control_guard.py
	$(CLOUD_PYTHON) -I scripts/check_policy_action.py
	$(CLOUD_PYTHON) -I scripts/check_gripper_observation.py
	$(CLOUD_PYTHON) -I scripts/check_sonic_reference.py
	$(CLOUD_PYTHON) -I scripts/check_sonic_observation.py
	$(CLOUD_PYTHON) -I scripts/check_sonic_history.py
	$(CLOUD_PYTHON) -I scripts/check_sonic_joint_trajectory.py
	$(CLOUD_PYTHON) -I scripts/check_body_lifecycle.py
	$(CLOUD_PYTHON) -I scripts/check_body_lifecycle_record.py
	$(CLOUD_PYTHON) -I scripts/check_body_io_adapter.py
	$(CLOUD_PYTHON) -I scripts/check_body_writer.py
	$(CLOUD_PYTHON) -I scripts/check_sonic_body_bridge.py
	$(CLOUD_PYTHON) -I scripts/check_local_body_monitor.py
	$(CLOUD_PYTHON) -I scripts/check_lowcmd_preview.py
	$(CLOUD_PYTHON) -I scripts/check_state_crc.py
	$(CLOUD_PYTHON) -I scripts/check_local_body_service.py
	$(CLOUD_PYTHON) -I scripts/check_online_record.py
cloud-export:
	@test -n "$(OUTPUT)" || (echo 'Usage: make cloud-export OUTPUT=new-directory (local only)' >&2; exit 2)
	python3 -I scripts/export_cloud_source.py --output "$(OUTPUT)"
.PHONY: run
.PHONY: body-runtime body-runtime-expiry body-runtime-build
body-runtime:
	.venv/bin/python -I scripts/run_body_runtime.py --seconds 5
body-runtime-expiry:
	.venv/bin/python -I scripts/run_body_runtime.py --seconds 5 --scenario body_expiry
body-runtime-build:
	.venv/bin/python -I scripts/run_body_runtime.py --mode build
RUN_SECONDS ?= 30
run:
	.venv/bin/python -I scripts/run_sonic_mujoco.py --seconds "$(RUN_SECONDS)" --warmup 0.2 --pika --lerobot --native-body --video
.PHONY: sonic-sim sonic-pika-sim sonic-teacher-sim sonic-policy-sim check-sonic-sim
check-sonic-sim:
	.venv/bin/python -I scripts/check_sonic_mujoco.py
	.venv/bin/python -I scripts/check_sonic_sim_actor.py
	.venv/bin/python -I scripts/check_sim_body_gateway.py
SIM_SECONDS ?= 5
sonic-sim:
	.venv/bin/python -I scripts/run_sonic_mujoco.py --seconds "$(SIM_SECONDS)" --warmup 0.2 --video
sonic-pika-sim:
	.venv/bin/python -I scripts/run_sonic_mujoco.py --seconds "$(SIM_SECONDS)" --warmup 0.2 --pika --video
sonic-teacher-sim:
	.venv/bin/python -I scripts/run_sonic_mujoco.py --seconds 15 --warmup 0.2 --pika --teacher assets/trajectories/episode0.json --video
sonic-policy-sim:
	.venv/bin/python -I scripts/run_sonic_mujoco.py --seconds "$(SIM_SECONDS)" --warmup 0.2 --pika --lerobot --video
.PHONY: bundle-check
bundle-check:
	python3 -I scripts/policy_bundle.py verify
.PHONY: bundle-export
bundle-export:
	@test -n "$(OUTPUT)" || (echo 'Usage: make bundle-export OUTPUT=path/to/new-bundle.tar.gz' >&2; exit 2)
	python3 -I scripts/export_policy_bundle.py --output "$(OUTPUT)"
.PHONY: audit-record
audit-record:
	@test -n "$(INPUT)" -a -n "$(OUTPUT)" || (echo 'Usage: make audit-record INPUT=report.json OUTPUT=new-audit.json' >&2; exit 2)
	python3 -I scripts/audit_motion_record.py --report "$(INPUT)" --output "$(OUTPUT)"
.PHONY: help doctor check-offline
.PHONY: check-runtime
check-runtime:
	python3 -I scripts/check_runtime.py --ipc
	python3 -I scripts/check_zmq_transport.py
	python3 -I scripts/check_body_history_transport.py --ipc
.PHONY: sonic-build
.PHONY: sonic-replay
.PHONY: sonic-tcp-check
sonic-tcp-check:
	@test -n "$(INPUT)" || (echo 'Usage: make sonic-tcp-check INPUT=path/to/report.json' >&2; exit 2)
	.venv/bin/python -I scripts/run_sonic_tcp_check.py --input "$(INPUT)"
.PHONY: sonic-service-check
.PHONY: body-lifecycle-check body-lifecycle-verify
.PHONY: lowcmd-preview lowcmd-abi-check
.PHONY: body-io-build-check
.PHONY: body-writer-check
body-writer-check:
	.venv/bin/python -I scripts/check_body_writer.py
	.venv/bin/python -I scripts/run_body_writer_check.py
body-io-build-check:
	.venv/bin/python -I scripts/probe_body_io_build.py
lowcmd-abi-check:
	.venv/bin/python -I scripts/probe_g1_lowcmd_abi.py
.PHONY: body-boundary-check body-boundary-ipc
.PHONY: body-local-check body-local-expiry-check
.PHONY: body-local-crc-check body-local-crc-expiry-check
body-local-crc-check:
	.venv/bin/python -I scripts/probe_local_body.py --saved-sonic --verify-crc
body-local-crc-expiry-check:
	.venv/bin/python -I scripts/probe_local_body.py --expire --verify-crc
body-local-check:
	.venv/bin/python -I scripts/probe_local_body.py --saved-sonic
body-local-expiry-check:
	.venv/bin/python -I scripts/probe_local_body.py --expire
body-boundary-check:
	.venv/bin/python -I scripts/check_sonic_body_bridge.py
	.venv/bin/python -I scripts/check_local_body_monitor.py
	.venv/bin/python -I scripts/run_body_boundary.py
body-boundary-ipc:
	.venv/bin/python -I scripts/run_body_boundary.py --ipc
lowcmd-preview:
	@test -n "$(RUN)" || (echo 'Usage: make lowcmd-preview RUN=path/to/body-lifecycle-run (files only)' >&2; exit 2)
	.venv/bin/python -I scripts/run_lowcmd_preview.py --run "$(RUN)"
body-lifecycle-check:
	.venv/bin/python -I scripts/check_body_lifecycle.py
	.venv/bin/python -I scripts/check_body_io_adapter.py
	.venv/bin/python -I scripts/check_body_writer.py
	.venv/bin/python -I scripts/check_body_lifecycle_record.py
	.venv/bin/python -I scripts/record_body_lifecycle.py
body-lifecycle-verify:
	@test -n "$(RUN)" || (echo 'Usage: make body-lifecycle-verify RUN=path/to/saved-run' >&2; exit 2)
	.venv/bin/python -I scripts/record_body_lifecycle.py --verify "$(RUN)"
.PHONY: startup-ablation-verify startup-ablation-run startup-contract-audit
startup-ablation-verify:
	@test -n "$(RUN)" || (echo 'Usage: make startup-ablation-verify RUN=path/to/saved-run' >&2; exit 2)
	.venv/bin/python -I scripts/sonic_startup_ablation.py verify --input "$(RUN)/input.json" --output "$(RUN)/outputs"
startup-ablation-run:
	@test -n "$(INPUT)" || (echo 'Usage: make startup-ablation-run INPUT=path/to/prepared-input.json (GPU only)' >&2; exit 2)
	.venv/bin/python -I scripts/run_startup_ablation.py --prepared "$(INPUT)"
startup-contract-audit:
	@test -n "$(OUTPUT)" || (echo 'Usage: make startup-contract-audit OUTPUT=path/to/new-audit.json (files only)' >&2; exit 2)
	.venv/bin/python -I scripts/audit_startup_contract.py --output "$(OUTPUT)"
.PHONY: full-record-check
full-record-check:
	python3 -I scripts/run_full_record_check.py
.PHONY: rate-record-check
.PHONY: measured-record-check online-record
.PHONY: online-fixture-check
.PHONY: trajectory-fixture-check
trajectory-fixture-check:
	python3 -I scripts/run_full_record_check.py --online-fixture --rate-seconds "$(RATE_SECONDS)" --joint-interpolation-seconds .4
online-fixture-check:
	python3 -I scripts/run_full_record_check.py --online-fixture --rate-seconds "$(RATE_SECONDS)"
measured-record-check:
	@test -n "$(STATE)" || (echo 'Usage: make measured-record-check STATE=path/to/state.jsonl' >&2; exit 2)
	python3 -I scripts/run_full_record_check.py --measured-state "$(STATE)"
BODY_RUNTIME ?= 0
ONLINE_SECONDS ?=
online-record:
	@test "$(DEVICE_READ_ACK)" = "1" || (echo 'Not started: G1 camera/serial/body read approval required. Serial open may reset MCU.' >&2; exit 2)
	python3 -I scripts/run_full_record_check.py --online-config config/online-record.json --allow-device-read $(if $(filter 1,$(BODY_RUNTIME)),--body-runtime,) $(if $(ONLINE_SECONDS),--online-seconds "$(ONLINE_SECONDS)",)
RATE_SECONDS ?= 1
rate-record-check:
	python3 -I scripts/run_full_record_check.py --rate-check --rate-seconds "$(RATE_SECONDS)"
sonic-service-check:
	@test -n "$(INPUT)" || (echo 'Usage: make sonic-service-check INPUT=path/to/report.json' >&2; exit 2)
	.venv/bin/python -I scripts/run_sonic_tcp_check.py --input "$(INPUT)" --service-check
sonic-replay:
	@test -n "$(STATE)" || (echo 'Usage: make sonic-replay STATE=path/to/state.jsonl' >&2; exit 2)
	.venv/bin/python -I scripts/run_sonic_replay.py --state "$(STATE)"
sonic-build:
	python3 -I scripts/run_sonic_build.py

help:
	@echo 'make sonic-sim / sonic-pika-sim SIM_SECONDS=5 : SONIC MuJoCo closed loop on GPU PC; NO G1/SDK/DDS'
	@echo 'make sonic-policy-sim SIM_SECONDS=30 : saved RGB ACT + MuJoCo body feedback; not visual task validation'
	@echo 'make sonic-teacher-sim : teacher TCP replay with SONIC; startup TCP check currently NOT passed'
	@echo 'make bundle-check  : verify ACT weights + processors + codec + RGB preprocessing (no GPU/G1)'
	@echo 'make bundle-export OUTPUT=new.tar.gz : verified diagnostic model export; no datasets/keys or hardware launcher'
	@echo 'make doctor        : local read-only inventory (no robot access)'
	@echo 'make check-offline : local tests (no simulation, network or motor commands)'
	@echo 'make check-runtime : local ZMQ IPC lifecycle tests (no G1 access)'
	@echo 'make body-lifecycle-check : ownership/initial-pose/local-watchdog protocol + saved-body replay; no actuator IO'
	@echo 'make body-boundary-check : existing saved SONIC outputs -> body lifecycle (files only)'
	@echo 'make body-boundary-ipc : same record-only boundary over LOCAL ZMQ IPC; no G1/GPU'
	@echo 'make body-local-check / body-local-expiry-check : actual G1 LowState + GPU ZMQ record-only gate/watchdog; NO motor commands'
	@echo 'make body-local-crc-check / body-local-crc-expiry-check : same read-only checks with mandatory native LowState CRC'
	@echo 'make body-io-build-check : G1 SDK binding OBJECT compilation + fake-only adapter tests; NO SDK executable or commands'
	@echo 'make body-writer-check : local native 2ms writer + fake IO faults; NO SDK/G1/GPU; save regression report'
	@echo 'make run [RUN_SECONDS=30] : LeRobot -> IK -> SONIC -> native SIM body command -> MuJoCo/video; NO G1'
	@echo 'make body-lifecycle-verify RUN=saved-run : recompute saved lifecycle journal (no GPU/G1)'
	@echo 'make lowcmd-preview RUN=body-lifecycle-run : pinned native LowCmd layout/CRC preview; no DDS or actuator IO'
	@echo 'make lowcmd-abi-check : compare saved native memory/CRC on G1 aarch64; NO DDS or actuator IO'
	@echo 'make startup-ablation-verify RUN=saved-run : verify existing 48-condition result (no GPU/G1)'
	@echo 'make startup-ablation-run INPUT=prepared.json : new GPU-only factorial inference; not needed to inspect saved results'
	@echo 'make startup-contract-audit OUTPUT=new.json : saved quaternion/heading/start-pose audit (no GPU/G1)'
	@echo 'make full-record-check : archived RGB -> ACT -> IK -> ZMQ -> SONIC on GPU PC, then exit'
	@echo 'make rate-record-check : repeated archived snapshot, independent ACT/IK 30Hz and SONIC 50Hz software test'
	@echo 'make online-fixture-check RATE_SECONDS=30 : online coordinator with synthetic inputs; GPU only, no G1'
	@echo 'make trajectory-fixture-check RATE_SECONDS=3 : same GPU-only test with causal joint lookahead (not a balance plan)'
	@echo 'make measured-record-check STATE=path/to/state.jsonl : archived measured history through ZMQ/observation/SONIC'
	@echo 'make online-record : G1 input-only integration; blocked without explicit DEVICE_READ_ACK=1 (see docs/ONLINE_RECORD.md)'
	@echo 'make sonic-replay STATE=path/to/state.jsonl : saved-state GPU inference only (no G1 access)'
	@echo 'make sonic-tcp-check INPUT=path/to/report.json : saved LeRobot action -> IK -> SONIC (no G1 access)'
	@echo 'make sonic-service-check INPUT=path/to/report.json : same plus persistent SONIC / GPU-local ZMQ IPC'
	@echo 'SONIC integration is in progress; hardware launch is not provided.'

doctor:
	python3 -I scripts/doctor.py

check-offline:
	python3 -I scripts/check_policy_bundle.py
	python3 -I scripts/check_doctor.py
	.venv/bin/python -I scripts/check_control_guard.py
	.venv/bin/python -I scripts/check_wbc_state.py
	.venv/bin/python -I scripts/check_policy_action.py
	.venv/bin/python -I scripts/check_gripper_observation.py
	python3 -I scripts/check_pika_gripper_control.py
	.venv/bin/python -I scripts/check_sonic_reference.py
	.venv/bin/python -I scripts/check_sonic_observation.py
	.venv/bin/python -I scripts/check_sonic_history.py
	.venv/bin/python -I scripts/check_sonic_joint_trajectory.py
	.venv/bin/python -I scripts/check_sonic_upstream_math.py
	.venv/bin/python -I scripts/check_sonic_upstream_history.py
	.venv/bin/python -I scripts/check_startup_ablation.py
	.venv/bin/python -I scripts/check_startup_contract.py
	.venv/bin/python -I scripts/check_body_lifecycle.py
	.venv/bin/python -I scripts/check_body_io_adapter.py
	.venv/bin/python -I scripts/check_body_writer.py
	.venv/bin/python -I scripts/check_body_lifecycle_record.py
	.venv/bin/python -I scripts/check_sonic_body_bridge.py
	.venv/bin/python -I scripts/check_local_body_monitor.py
	.venv/bin/python -I scripts/check_sonic_sim_actor.py
	.venv/bin/python -I scripts/check_local_body_service.py
	python3 -I scripts/check_local_body_probe.py
	.venv/bin/python -I scripts/check_lowcmd_preview.py
	.venv/bin/python -I scripts/check_sonic_replay.py
	.venv/bin/python -I scripts/check_sonic_tcp_reference.py
	python3 -I scripts/check_state_history.py
	python3 -I scripts/check_sample_clock.py
	.venv/bin/python -I scripts/check_state_crc.py
	.venv/bin/python -I scripts/check_sonic_tcp_pipeline.py
	python3 -I scripts/check_runtime.py
	python3 -I scripts/check_record_worker.py
	python3 -I scripts/check_reference_mailbox.py
	python3 -I scripts/check_sonic_process.py
	.venv/bin/python -I scripts/check_sonic_measured_stream.py
	python3 -I scripts/check_body_history_transport.py
	python3 -I scripts/check_online_record.py
	python3 -I scripts/check_motion_record.py
	python3 -I scripts/check_temporary_receiver_priority.py
	python3 -I scripts/check_recover_outputs.py

.PHONY: setup setup-wbc sim sim-view wbc wbc-view pika pika-view check check-pika

.PHONY: input-check
input-check:
	python3 -I scripts/inspect_inputs.py

.PHONY: camera-check
camera-check:
	python3 -I scripts/check_cameras.py

setup:
	bash scripts/setup-sim.sh

setup-wbc:
	bash scripts/setup-sim.sh wbc

sim:
	.venv/bin/python -I scripts/sim_balance.py

sim-view:
	.venv/bin/python -I scripts/sim_balance.py --viewer --seconds 30

wbc:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --seconds 30

wbc-view:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --viewer --seconds 30

pika:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --pika --seconds 30

pika-view:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --pika --viewer --seconds 30

check-pika:
	.venv/bin/python -I scripts/check_pika_model.py
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --pika --seconds 30

check:
	.venv/bin/python -I -m pip --disable-pip-version-check --no-cache-dir check
	.venv/bin/python -I scripts/sim_balance.py --seconds 10

.PHONY: teacher teacher-view check-teacher
teacher:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --pika --teacher assets/trajectories/episode0.json --seconds 30

teacher-view:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --pika --teacher assets/trajectories/episode0.json --seconds 30 --viewer

check-teacher:
	.venv/bin/python -I scripts/check_teacher.py

.PHONY: dataset-check
dataset-check:
	python3 scripts/check_dataset.py

# Static inspection only; does not choose or execute a model.
POLICY ?= /home/developer/workspaces/pika_ws2/models/zero_relative_50ep_act_h1_v2/pretrained_model
DATASET ?= /home/developer/workspaces/pika_ws2/datasets/data_2608261323_valid49_g1_zero_relative_h1_final_v3
.PHONY: policy-check
policy-check:
	.venv/bin/python -I scripts/check_policy.py --policy "$(POLICY)" --dataset "$(DATASET)"

POLICY_STEPS ?= 254
.PHONY: policy-eval
policy-eval:
	.venv-policy/bin/python -I scripts/policy_eval.py --policy "$(POLICY)" --dataset "$(DATASET)" --steps "$(POLICY_STEPS)"

.PHONY: setup-policy
setup-policy:
	bash scripts/setup-policy.sh

.PHONY: policy-input-check
policy-input-check:
	.venv-policy/bin/python -I scripts/audit_policy_inputs.py

.PHONY: train-rgb-smoke
RGB_STEPS ?= 500
train-rgb-smoke:
	.venv-policy/bin/python -I scripts/train_rgb_smoke.py --steps "$(RGB_STEPS)"

.PHONY: eval-rgb-smoke
eval-rgb-smoke:
	.venv-policy/bin/python -I scripts/train_rgb_smoke.py --evaluate-latest

.PHONY: check-rgb-smoke
check-rgb-smoke:
	.venv-policy/bin/python -I scripts/check_rgb_smoke.py

# Explicit remote training only; no robot connection. Requires prepared GPU workspace.
GPU_STEPS ?= 100
.PHONY: gpu-smoke gpu-report
gpu-smoke:
	ssh -i /home/developer/.ssh/EXAMPLE_GPU_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes galleria@192.0.2.9 '/home/gpu-user/g1-pika-training/.venv-gpu/bin/python -I /home/gpu-user/g1-pika-training/scripts/gpu_job.py start --kind smoke --steps $(GPU_STEPS)'

gpu-report:
	ssh -i /home/developer/.ssh/EXAMPLE_GPU_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes galleria@192.0.2.9 'cat /home/gpu-user/g1-pika-training/artifacts/gpu-smoke-latest.json'

.PHONY: gpu-resume-report gpu-job-status
gpu-resume-report:
	ssh -i /home/developer/.ssh/EXAMPLE_GPU_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes galleria@192.0.2.9 'cat /home/gpu-user/g1-pika-training/artifacts/gpu-resume-check.json'

gpu-job-status:
	@test -n "$(GPU_JOB)" || { echo 'Specify GPU_JOB=/home/gpu-user/g1-pika-training/artifacts/jobs/job-...'; exit 2; }
	ssh -i /home/developer/.ssh/EXAMPLE_GPU_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes galleria@192.0.2.9 '/home/gpu-user/g1-pika-training/.venv-gpu/bin/python -I /home/gpu-user/g1-pika-training/scripts/gpu_job.py status --job "$(GPU_JOB)"'

.PHONY: gpu-full-train gpu-full-report
gpu-full-train:
	ssh -i /home/developer/.ssh/EXAMPLE_GPU_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes galleria@192.0.2.9 '/home/gpu-user/g1-pika-training/.venv-gpu/bin/python -I /home/gpu-user/g1-pika-training/scripts/gpu_job.py start --kind full-rgb --steps 1000'

gpu-full-report:
	ssh -i /home/developer/.ssh/EXAMPLE_GPU_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes galleria@192.0.2.9 'cat /home/gpu-user/g1-pika-training/artifacts/full-rgb-audit-latest.json'

.PHONY: gpu-learning-curve gpu-learning-report check-policy-action
gpu-learning-curve:
	ssh -i /home/developer/.ssh/EXAMPLE_GPU_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes galleria@192.0.2.9 '/home/gpu-user/g1-pika-training/.venv-gpu/bin/python -I /home/gpu-user/g1-pika-training/scripts/gpu_job.py start --kind learning-curve'

gpu-learning-report:
	ssh -i /home/developer/.ssh/EXAMPLE_GPU_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes galleria@192.0.2.9 'cat /home/gpu-user/g1-pika-training/artifacts/learning-curve-latest.json'

check-policy-action:
	.venv/bin/python -I scripts/check_policy_action.py

.PHONY: gpu-gripper-residual gpu-gripper-report
gpu-gripper-residual:
	ssh -i /home/developer/.ssh/EXAMPLE_GPU_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes galleria@192.0.2.9 '/home/gpu-user/g1-pika-training/.venv-gpu/bin/python -I /home/gpu-user/g1-pika-training/scripts/gpu_job.py start --kind gripper-residual'

gpu-gripper-report:
	ssh -i /home/developer/.ssh/EXAMPLE_GPU_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes galleria@192.0.2.9 'cat /home/gpu-user/g1-pika-training/artifacts/gripper-residual-latest.json'

POLICY_SIM_RUN ?= artifacts/full-rgb-residual/run-xg1fn3b_
.PHONY: policy-sim policy-view check-policy-bridge
policy-sim:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --pika --policy-run "$(POLICY_SIM_RUN)" --seconds 12

policy-view:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --pika --policy-run "$(POLICY_SIM_RUN)" --seconds 12 --viewer

check-policy-bridge:
	.venv/bin/python -I scripts/check_policy_bridge.py

.PHONY: policy-async policy-async-view check-policy-async
policy-async:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --pika --policy-run "$(POLICY_SIM_RUN)" --policy-async --policy-frames 30 --seconds 12

policy-async-view:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --pika --policy-run "$(POLICY_SIM_RUN)" --policy-async --policy-frames 30 --seconds 12 --viewer

check-policy-async:
	.venv/bin/python -I scripts/check_async_policy.py

.PHONY: end-to-end
end-to-end:
	python3 -I scripts/run_end_to_end.py

.PHONY: guarded-wbc guarded-wbc-view check-control-guard
guarded-wbc:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --pika --seconds 12 --guard-output

guarded-wbc-view:
	.venv/bin/python -I scripts/sim_balance.py --controller wbc --pika --seconds 12 --guard-output --viewer

check-control-guard:
	.venv/bin/python -I scripts/check_control_guard.py

.PHONY: check-guarded-wbc
check-guarded-wbc:
	python3 -I scripts/check_guarded_runtime.py

.PHONY: mock-runtime mock-runtime-local mock-runtime-view
mock-runtime:
	python3 -I scripts/run_mock_runtime.py

mock-runtime-local:
	python3 -I scripts/run_mock_runtime.py --local

mock-runtime-view:
	python3 -I scripts/run_mock_runtime.py --viewer

.PHONY: split-runtime
split-runtime:
	python3 -I scripts/run_split_runtime.py $(SPLIT_ARGS)

.PHONY: async-runtime
async-runtime:
	python3 -I scripts/run_split_runtime.py --nonblocking $(ASYNC_ARGS)

.PHONY: g1-camera-check
g1-camera-check:
	python3 -I scripts/g1_camera_snapshot.py

.PHONY: live-shadow
live-shadow:
	python3 -I scripts/run_live_shadow.py

# Verified deployment on galleria; images never pass through this development PC.
.PHONY: wired-shadow
wired-shadow:
	python3 -I scripts/run_state_shadow.py

.PHONY: state-shadow
state-shadow: wired-shadow

.PHONY: input-shadow
input-shadow:
	python3 -I scripts/run_state_shadow.py --gripper-state
