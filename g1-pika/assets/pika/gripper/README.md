# PIKA単体ドライバ

`pika_gripper.py` はLeRobotから無変更で移植。

- 出典: https://github.com/taigasasaki6331/lerobot
- commit: `79edf6a95948d0f0d75df1d54d0a5aad305f75a8`
- 元パス: `src/lerobot/robots/unitree_g1_pika/pika_gripper.py`
- SHA256: `ef7c397ec33ada894fb164bea633b560e178b7fa1778e5bf89eeb1001be8e63e`
- ライセンス: Apache-2.0（同梱の `LICENSE` と元ファイルの著作権表示を保持）
- 依存: Python 3.10以上、pyserial 3.5

`scripts/control_pika_gripper.py` がこのファイルだけを動的に読み込む。
LeRobotの全パッケージ、Unitree SDK、ROS、SONICは不要。
操作方法は `docs/PIKA_GRIPPER_CONTROL.md`。
