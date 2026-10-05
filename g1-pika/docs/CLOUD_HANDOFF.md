# CloudでのCPU開発（2026-10-05）

主対象はg1-pika/のACT＋PIKA＋GEAR-SONICです。ルートのπ0/π0.5・48D方式は別実装です。
Cloudはコード開発とrecord-only検証を行います。GPU／G1／カメラ／シリアル／DDS command publisher／通常G1Deployは起動しません。
実演データ・ACT重みは既存保存資産で、公開コピーに含まれないことを消失・未準備と解釈しません。

リポジトリルート：

```bash
make cloud-setup
make cloud-check
make cloud-body-runtime
make cloud-body-runtime BODY_SCENARIO=body_expiry
make cloud-body-runtime BODY_SCENARIO=recovery
```

Linux、Python3.10〜3.12、gcc/g++、make、libzmq.so.5、venv/pipが必要です。
専用.venv-cloudへrequirements-cloud.lockのnumpy1.26.4を導入し、既存.venvは変更しません。
Cloudチェックは20スクリプト。共通owner18条件とdirect runtimeの通常／身体期限切れ／明示復帰を含みます。
SDK flag0/1のobject compileだけを行い、SDK link／constructor実行／機器I/Oは行いません。

最新Cloud検証は131成功／3skip／exit0。出力直前の時刻検査を修正しました。
以前の期限超過・未合格も[履歴](PROGRESS.md)に保持し、実時間性の保証とは分けます。
IPC2ケースは既定skip。この環境ではbindがEPERMでした。
/procとkillのPID名前空間が異なる場合、該当cleanup試験は子process開始・送信前に明示skipします。
real-threadのdeadline faultはskipへ変換せず保存します。実時間保証・物理停止を認定しません。

Cloud入口のdirect版はin-process envelopeで、ZMQ配送を検証しません。
IPC可能なCPU環境ではg1-pika内で追加確認できます：

```bash
.venv-cloud/bin/python -I scripts/check_local_body_service.py --ipc
.venv-cloud/bin/python -I scripts/run_body_runtime.py --seconds 5
.venv-cloud/bin/python -I scripts/run_body_runtime.py --seconds 5 --scenario body_expiry
.venv-cloud/bin/python -I scripts/run_body_runtime.py --seconds 5 --scenario recovery
```

後三つは人工body／目標／ownership／CRC metadataとSDK-freeメモリ出力です。
人工姿勢やACKを実機の準備・制御権・停止の証拠にしません。
100ms入力、10ms writer gap、0.05rad step、URDF／速度制限を維持し、clip／閾値緩和／自動再armを行いません。
make run／online-record／GPU・G1 probeはCloudで実行しません。

[共通owner](BODY_OWNER.md) · [HANDOFF](HANDOFF.md) · [TODO](IMPLEMENTATION_TODO.md) · [成功・失敗履歴](PROGRESS.md)。
以前のCloud移行・公開コピー生成の記録は[2026-10-02版](https://github.com/taigasasaki6331/sonic_lerobot/blob/22999ade4b4035891157e9897c44172e2864acfa/g1-pika/docs/CLOUD_HANDOFF.md)に保持されています。
