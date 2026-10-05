# g1-pika

Unitree G1＋AgileX PIKA、LeRobot ACT＋GEAR-SONICの開発環境。
経路はACTの10次元action（局所位置3・回転6D columns・幅1）→TCP→IK→SONIC→身体制御。
グリッパ幅は別経路、PC間はZMQ、G1局所状態・低レベル制御はDDSです。

リポジトリルートから、GPU・G1不要のCPU開発を開始します。

```bash
make cloud-setup
make cloud-check
make cloud-body-runtime
make cloud-body-runtime BODY_SCENARIO=body_expiry
make cloud-body-runtime BODY_SCENARIO=recovery
```

既定はrecord-only。人工の局所状態・目標を使い、初期化→制御権取得候補→3秒初期参照／整定→通常制御→停止→終了を通します。
`recovery`は停止後の明示的なメモリ復帰を追加し、復帰後の再出力を拒否します。
上の入口はin-process envelopeで、ZMQ配送は検証しません。IPC版のコマンドは[共通owner](docs/BODY_OWNER.md)。
最新Cloud一括は131成功・3skip。以前の期限超過による停止も保持し、実時間性は未認定です。[成功・失敗の履歴](docs/PROGRESS.md)。
SDK側も同じowner状態機械へ接続しましたが、object compileのみでリンク・起動・機器I/Oは未検証です。

保存実入力の147/150 SONIC目標はURDF範囲外のままです。clipping・閾値緩和は行いません。
物理停止、実制御権、支持・装着条件、実時間性、実タスク性能は未検証です。
Cloudでは実機・カメラ・シリアル・DDS command publisher・通常G1Deployを起動しません。
データ本体・ACT重みは既存保存資産として維持され、公開コピーには含まれません。

[引き継ぎ](docs/HANDOFF.md) · [TODO](docs/IMPLEMENTATION_TODO.md) · [検証履歴](docs/PROGRESS.md) · [Cloud手順](docs/CLOUD_HANDOFF.md)

GPU環境の既存MuJoCo一括入口は`cd g1-pika && make run`（過去30秒統合確認済み）。
今回CloudではGPU／MuJoCoを再実行していません。[範囲と再現](docs/SONIC_MUJOCO.md)。
[旧README全文](https://github.com/taigasasaki6331/sonic_lerobot/blob/22999ade4b4035891157e9897c44172e2864acfa/g1-pika/README.md)と既存コード・証拠は保存しています。
ルートのπ0/π0.5・48D方式は別プロジェクトです。
