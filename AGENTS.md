# Cloud continuation

The active project for this branch is `g1-pika/`: Unitree G1 + AgileX PIKA,
LeRobot ACT (10D local TCP action) + GEAR-SONIC.
Before working, read `g1-pika/AGENTS.md`, `g1-pika/docs/CLOUD_HANDOFF.md`,
`g1-pika/docs/HANDOFF.md`, and `g1-pika/docs/IMPLEMENTATION_TODO.md`.

- Work in `g1-pika/`. Use root `make cloud-setup` / `make cloud-check`, which delegate there.
- Cloud work is code development and CPU/record-only validation. No GPU PC/G1 access is available.
- Do not open cameras/serial ports, start DDS command publishers or normal G1Deploy,
  transfer robot control ownership, or send any physical robot/gripper commands.
  Historical standalone PIKA permissions are not Cloud actuation authority.
- No SSH credentials, datasets, trained weights, real input logs, or GPU libraries are bundled.
  Public deployment values are examples, not a verified local setup.
- Preserve all existing/uncommitted code and evidence. Do not clip unsafe SONIC outputs,
  relax safety gates, fabricate state, or claim CPU/simulation success as hardware validation.
- Continue approved implementation without repeated continuation questions. Ask only for
  missing choices/authority genuinely needed; do not request hardware startup for CPU work.
- Prioritize the existing G1-local runtime / SDK adapter integration and a coherent
  startup/shutdown path over unrelated component diagnostics. Update README/HANDOFF/TODO.

The pre-existing root `src/sonic_lerobot`, `tests`, `patches`, `pyproject.toml`, and
older docs implement a DIFFERENT pi0/pi0.5, 48D planner-reference path with no PIKA.
They are retained unchanged. Do not confuse or silently merge their action/state
schemas or LeRobot pins with the 10D PIKA/ACT project. Root README explains both.
