# g1-pika — 旧Decoupled WBC検証記録

旧READMEを保存。以下の起動例は旧構成用です。リンクは移動前のルート基準です。

## 現在の起動口（2026-09-15）

非同期版は `make async-runtime`。GPU内loopbackでは206推論/実時間約60秒を完走しましたが、
現Wi-Fiの2 PC経路は指令鮮度期限超過で未合格です。
成功した診断の再実行は `make async-runtime ASYNC_ARGS=--gpu-loopback`。
詳細と有線比較の残作業は [ASYNC_SPLIT_RUNTIME.md](docs/ASYNC_SPLIT_RUNTIME.md)。

LeRobotとWBCをGPU PC側へ集約した新経路は `make split-runtime`。
このPCはMuJoCo物理計算を担当し、206フレーム全軌道と通信断まで一括検証します。
通信待ちで物理時間も止まるシミュレーション専用構成です。
詳細は [SPLIT_RUNTIME.md](docs/SPLIT_RUNTIME.md)。

G1なしで、このPCとGPU PCを使う統合試験は `make mock-runtime`。
模擬G1の記録画像・状態→ZMQ→GPU上のLeRobot ACT→WBC→MuJoCoを通し、
通信断・遅延・旧応答・新規セッションも一括検証します。
表示付きの正常試験は `make mock-runtime-view`。
接続設定・終了方法・未完了項目は [MOCK_RUNTIME.md](docs/MOCK_RUNTIME.md)、
再開情報は [HANDOFF.md](docs/HANDOFF.md)。実機への動作指令は禁止のままです。

以下は従来の個別試験です。

RGBのみの新規LeRobot ACT学習試験を追加しました。
`make train-rgb-smoke` でCPU小規模学習、`make eval-rgb-smoke` で保存モデルの再読込評価。
詳細は [RGB_TRAINING.md](docs/RGB_TRAINING.md)。実機には送信しません。

**形状の訂正（2026-09-14）:** 現在の「PIKA付き」試験に使うSTL3点は、ローカルのPiper用グリッパと完全一致する。
旧PIKA用定義を移植した代替モデルであり、実物PIKAの形状・質量を検証したものではない。
実物に対応するCAD・仕様の確認と差し替えが必要。詳細は [PIKA_MODEL.md](docs/PIKA_MODEL.md)。

Unitree G1＋AgileX PIKAによる自立・自律タスク実行のための新規リポジトリ。
代替PIKAモデルで教師軌道・LeRobot実推論を公式Decoupled WBC＋上半身IKへ接続しています。
実機状態/画像の受信専用診断はありますが、実機動作指令の送信は行いません。
既存PIKA実装を変更しません。

## 起動

このPCではセットアップ済み。リポジトリ内で以下を実行します。

```bash
make teacher-view
```

既存データのepisode 0（254フレーム）を再生し、結果を `artifacts/teacher-latest.json` に保存します。
最初の2秒は姿勢安定化、その後約8.47秒で右先端の教師軌道を再生し、30秒まで最終目標を保持します。
速度・並進量は元のまま、開始位置と姿勢だけ現在のTCPへ合わせます。左腕と爪は固定です。
画面なしは `make teacher`、変換の単体テストは `make check-teacher`。
全49エピソードの状態/action形式の確認は `make dataset-check`。
推論前のチェックポイント静的検査は `make policy-check`（モデルの推論は実行しません）。
保存観測からのLeRobot推論評価は `make policy-eval`。専用Python環境で実行し、WBC/実機へは送信しません。
推論環境・範囲の説明は [POLICY_EVAL.md](docs/POLICY_EVAL.md)。
これは保存actionの再生であり、学習済みLeRobotポリシーの推論ではありません。
データ形式の注意点・次の接続方針は [TEACHER_REPLAY.md](docs/TEACHER_REPLAY.md)。

従来の往復試験は `make pika-view`（結果は `artifacts/pika-latest.json`）。
青いPIKAと赤いTCPマーカーを表示し、立位から右TCPを前方6cm・上方4cmへ滑らかに往復させます。
画面なしは `make pika`、モデル整合と動作の検証は `make check-pika`。
PIKAなしの試験は `make wbc` / `make wbc-view`。
旧Balance単体試験も `make sim` / `make sim-view` で実行できます。
PIKAなしのWBC動作はユーザーがGUIで30秒完走を確認済み。
PIKA付きは画面なしの試験と近接画像の描画を確認済み。対話GUIは未確認です。
描画性能によって実時間は30秒より長くなります。表示更新は最大約30Hzに抑えています。
途中で画面を閉じると `status: interrupted`（未完了）で正常終了します。
`passed: true` は指定のシミュレーション時間を完走し、閾値内だった場合だけです。
別のUbuntu 22.04 / Python 3.10＋Git LFS環境への導入は `make setup-wbc`（Balance単体だけなら `make setup`）。
新規取得の手順は用意済みですが、別PCでのクリーンインストールは未検証です。
Python依存は `requirements-wbc.lock` / `requirements-sim.lock`、外部コードとモデルは `sources.lock.json` で固定しています。
Pythonは `-I` で起動し、既存ROSの `PYTHONPATH` やユーザーsite-packagesの混入を防ぎます。

## 試験の範囲

MuJoCoの自由基底・重力・接触・トルク制御を用います。初期姿勢設定後に胴体位置を上書きしません。
公開Balance ONNXと上半身制御をCPUで50Hz、物理を200Hzで実行します。
WBCモードは公式のBodyIKSolver、InterpolationPolicy、G1GearWbcPolicy、G1DecoupledWholeBodyPolicyを接続。
腕には公式RobotModelの重力補償と公式PDゲインを使います。
ROS/DDSを含む公式起動スクリプト全体ではなく、制御クラスをMuJoCoへ直接接続したランナーです。
PIKAモードの目標はpelvis基準の `right_pika_tcp`。爪は閉状態に固定しています。
PIKAは旧URDFの質量・慣性（片側約206g）を使用。取り付け金具・配線の追加質量は未計上です。
Walkモデルの動作、爪の開閉・把持、外乱耐性、実機適合性は未検証。
PIKA付きでの最大TCP追従誤差は約3.4cm。精密な作業の成立を示すものではありません。
合格閾値は初期スモーク試験用で、実機の安全基準ではありません。

## 記録

- [引き継ぎ・PC環境](docs/HANDOFF.md)
- [進捗・次の作業](docs/PROGRESS.md)
- [採用候補と出典](docs/WBC_ASSESSMENT.md)
- [PIKAモデルの出典・構成・制限](docs/PIKA_MODEL.md)

WBC取得コード・モデルは `vendor/`、仮想環境は `.venv/` に隔離し、Git管理対象外としています。
移植したPIKA部品は `assets/pika/` でGit管理し、生成モデルは `artifacts/models/` に保存します。
GitHubへのリポジトリ作成・pushはまだ行っていません。
