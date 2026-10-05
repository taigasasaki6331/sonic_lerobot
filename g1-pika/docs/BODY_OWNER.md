# 共通owner：起動・停止・明示復帰（2026-10-05）

`body_owner_lifecycle.hpp`をrecord runtimeとbuild-only `UnitreeBodySession`が共有する。
オブジェクト生成にI/Oはなく、最初の操作で単一owner threadを固定する。
record C/Python APIにはSDK transportを選ぶ入口がない。Unitree transportの既定compile flagは0。

| 段階 | 明示操作・条件 |
|---|---|
| 初期化 | `initialize()`でquery channelとCheckModeだけ。解除・身体出力なし |
| 制御権取得候補 | `acquire(local_evidence_reader)`でReleaseModeは最大1回。既存modeの空確認後にpublisher初期化。RPC後とpublisher後に局所期限／停止要求を再確認 |
| 初期姿勢遷移 | `begin_initialization()`後、既存BodyLifecycleの3秒参照／姿勢整定をnativeへ渡す。局所phaseを明示 |
| 通常制御 | recordのready/trackingを診断条件として受理。physical scopeは別途`confirm_initial_pose(physical_trial)`が必要 |
| 停止・異常停止 | 通常終了とfaultを区別してラッチ。通常出力終了後に停止候補は最大1回。identity lossでは古い型式の停止候補も禁止 |
| 明示復帰 | 停止後に同じownerが`recover(scope, stop_observation, fresh_local_evidence_reader)`を実行。publisherを閉じて以前のmodeへ復帰候補。失敗時の再試行なし |
| 終了 | `close()`はresource終了だけ。復帰を暗黙実行しない。復帰後もmailboxはラッチされたまま、再出力・再armなし |

scope、TrialContract、停止観測文字列、SDK成功は呼出側の契約入力で、物理条件を証明するものではない。
record scopeはmemory-only transportだけを受理し、実機用契約boolを人工的にtrueにしない。
physical scopeで人工診断phaseやrecord停止観測を承認として使わない。
実際の支持／姿勢／制御権／停止観測を供給する実機gateway・現場操作は残る。

## 起動入口

リポジトリルート：

```bash
make cloud-setup
make cloud-check
make cloud-body-runtime
make cloud-body-runtime BODY_SCENARIO=body_expiry
make cloud-body-runtime BODY_SCENARIO=recovery
```

direct版は既存LocalBodyRuntimeWorker、SONIC envelope、native 2ms ownerを通す。
人工の身体は初期参照へ追従するfixture。CRC metadata／motor raw zero／制御権はすべて人工で、実G1の合格にしない。
独立native期限とPython監視を維持し、身体停止中も人工peer目標を送る。
通常終了と復帰は5秒、身体期限切れは約4秒で期待fault。reportのpassedは各シナリオの期待結果への一致。
`artifacts/body-runtime/`へ入力fixture・目標応答・native最終パケット／履歴／reportを保存する。

IPCが可能なCPUホストでは、`g1-pika/`から追加検証する：

```bash
.venv-cloud/bin/python -I scripts/check_local_body_service.py --ipc
.venv-cloud/bin/python -I scripts/run_body_runtime.py --seconds 5
.venv-cloud/bin/python -I scripts/run_body_runtime.py --seconds 5 --scenario body_expiry
.venv-cloud/bin/python -I scripts/run_body_runtime.py --seconds 5 --scenario recovery
```

IPC socketは短い一時パスに固定して長いcheckout pathによるUNIX socket制約を避ける。
local serviceは`--record-recovery-note`を局所CLIだけで受ける。ZMQはhello/record/stopのままで、復帰・初期化・局所状態のpeer APIは追加しない。
`stop()`はwriter終了を待ち、`finish()`でownerを終了する。復帰はこの間に同じownerへ要求する。
native停止前に入力／GPU workerをjoinしない。SDK Write／停止候補がブロックする場合の物理的な代替停止は未検証。

## SDKの接続範囲と残課題

`UnitreeBodySession`はUnitreeBodyTransport・physical BodyIoAdapter・WriterMailbox・共通ownerを組み立てるbuild-only C++接続点。
Cloudはflag0/1双方のobjectをcompileするだけで、SDKリンク・構築実行・DDS登録・送信をしない。
2ms設計、身体／目標100ms、writer gap10ms、関節step0.05rad、URDF／速度制限を維持。
scheduler遅延はfaultとして記録し、retry・閾値緩和・自動再armで通さない。実時間保証はない。

G1/aarch64の最新build、実SDKリンク／起動、LowState firmware motor解釈、支持・装着・停止方式、
実ownership／初期姿勢／通常送信／停止／復帰の効果と期限、147/150範囲外の解決が残る。
LeRobot ACTの実タスク、視覚閉ループ、PIKA幅／把持も別の未検証範囲。
[TODO](IMPLEMENTATION_TODO.md)と[履歴](PROGRESS.md)を参照する。
