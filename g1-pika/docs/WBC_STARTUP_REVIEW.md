# 本家WBC起動・終了とIK初期値の調査（2026-09-18）

出典は固定vendor/GR00T-WholeBodyControl commit087f9ac01d46f6d8e4d0b73c01ae64799f292a38。
ソース調査と保存済み実入力の計算のみ。実機へ接続/送信/姿勢変更していない。

## 前回説明の訂正

本家BodyIKSolver.initializeは肩ロール±0.2radの**計算用初期値**で開始する。
こちらのWholeBodyControllerが直後に実測姿勢をIK初期値として上書きしていたため、
範囲外の実姿勢で例外となっていた。計算用seedと実機姿勢は別物。
「実機を初期姿勢に動かさなければ計算を進められない」は早計だった。

既定のsimulation動作を維持しつつik_seed_mode=upstream_defaultを追加。
本家seedを保つだけで、観測関節角・FK・関節制限は変更しない。
記録再生は --ik-seed-mode upstream_default で明示選択する。

## galleria再検証

- 保存済み実入力30組からWBC出力30件を計算できた（computation_completed=true）。
- IK位置誤差最大0.410499m、最後は左0.000461m/右0.022319m。
- 出力関節目標と実測との差は全関節/全記録で最大1.624134rad。
- 計算p95 0.930ms。ただし5Hzで採取した記録の再生であり実時間制御試験ではない。
- 既存シミュレーション相当のIK閾値0.02mに未達、passed=false、hardware_ready=false。
- 初期値を変えて計算できることは、実機に安全な遷移ができることを意味しない。
- 小さいwrist_tracking_error値は実測TCPと指令TCPの差であり、実機が出力へ追従した証拠ではない。
- 記録: artifacts/state-shadow/state-shadow-Pysyga/wbc-shadow-upstream-seed.json。
  最初のローカル検証wbc-shadow-upstream-seed-local.jsonは30件計算のみでpassed=trueとした
  旧判定の診断記録。IK誤差込みの最終判定はGPU版passed=falseを正とする。

## 本家起動順（実行していない）

1. run_g1_control_loop→G1Env→G1Body→BodyStateProcessor。
2. realの場合、BodyStateProcessor constructorでMotionSwitcherClient.CheckMode/ReleaseMode。
   既存モードが空になるまでループ。単なる状態受信として起動してはいけない。
3. BodyCommandSenderがrt/lowcmd publisherとPDゲインを初期化。
4. 制御ループはobserve→policy.get_action→env.queue_action→LowCmd.Write。
5. 下半身policyは既定use_policy_action=falseで観測関節角を返す。これは送信停止/無励磁ではない。
   `]`でpolicy action有効、`o`で無効。無効時も既定PDゲインは残る。
6. teleop側は最初の上半身目標を2秒先のtarget_timeとして補間。
   これはPIKA装着実機で検証済みの立ち上げ軌道ではない。

## 終了・停止（コード上の確認）

- KeyboardEStopはtmux kill-sessionまたはsys.exit。
- run_g1_control_loop finallyはdispatcher停止、ROS停止、env.close。
- G1Env.closeはsimulatorを閉じるだけ。実機の明示的なdamping送信/モード復帰はここにない。
- したがって「プロセス終了で実機が安全停止する」とは断定できない。
- 本家JointSafetyMonitorは位置違反を警告扱い、速度違反を停止判定としている。
  その監視を今回の出力専用再生で実機適用したわけではない。
- 本家run_real_checklistにはaction queue無効での状態確認、低ゲイン試験、
  周辺クリアランス、外部停止手段の用意が明記されている。

## 次の実機段階に必要な確認

現在の支持状態（吊り下げ/足接地）と停止手段を確認し、保持→初期姿勢→制御開始、
終了時の扱いを機体条件に合わせて決める。身体・腕の動作許可はまだない。
PC間ZMQの方針は維持。本家のROS制御ループやReleaseModeをそのまま起動しない。

## 支持状態の訂正と停止入力の準備

ユーザー確認: 吊り下げた状態で足が接地しており、リモコンもある。
「支持なしで接地」とは異なる。約5秒でdampingという記憶は未検証。
吊り下げの荷重支持/転倒防止能力と、低レベル制御中の停止動作は別途確認が必要。

固定本家のKeyboardEStopはバッククォートキーからプロセスを終了するだけ。
ユーザー指示によりリモコンのソフトウェア統合は対象外。
今回追加した生配列出力と未実行のテストfixtureは取り下げ、元の受信処理を維持。
リモコン統合を開始・終了処理の実装の前提にしない。
モーター送信、ReleaseMode、damping要求、リモコン操作は実行していない。

実機送信を作る前に必要な境界:
- 開始: 状態取得だけでは制御権を解放しない。明示操作でのみ別段階へ進む。
- 停止: G1側で扱い、GPU/ZMQ/SSHの応答待ちに依存させない。
- 通信断/プロセス停止: 明示的停止要求とは別に検証する。
- damping/無励磁/立位保持は別物。姿勢・支持条件に合わせた停止方式の確認が必要。
- 入力の受信確認は、停止指令の到達や物理的停止の検証を代替しない。

## 保存済み実入力による開始時の切り分け

`replay_real_wbc_shadow.py`に診断用のlower-body-mode/target-sourceと関節別統計を追加。
既定のcontroller/simulationは変更せず、送信なしの再生だけで比較した。

| 条件 | 最大IK位置誤差 | 最大の目標−実測関節差 |
| --- | --- | --- |
| 本家seed・Balance即時有効・記録action | 0.410499m | 1.624134rad（左肩yaw） |
| 本家seed・下半身実測値・初期TCP固定 | 0.410198m | 1.624134rad（左肩yaw） |
| 実測近傍の制限内seed・下半身実測値・初期TCP固定 | 0.025678m | 0.577043rad（右肩yaw） |

全条件30件完走、IKの0.02m基準には不合格。最終右IK誤差も約0.022m残る。
LeRobotの新しい動作目標なしでも腕の大きな差が発生するため、学習policyだけの問題ではない。
旧最大1.624radは初回瞬間ジャンプではなく30件全体の目標−実測差。
初回の左肩yaw差は−0.08rad、左足首pitch差は+0.984444rad。
下半身実測値モードでは15関節の目標−実測差はゼロになるが、物理的安全性は示さない。

projected_measuredは再生スクリプトだけの数値実験。
実測から作ったIK seedを既存の制限内へ射影し、そのseedで姿勢taskを初期化する。
実測観測・目標出力・関節制限は書き換えない。これも実機姿勢移行の代替ではない。
記録は5Hz相当で機体が出力に応答しないため、閉ループの安定性や50Hzの連続性は未検証。

結果: artifacts/state-shadow/state-shadow-Pysyga/wbc-startup-*.json。
次は初期姿勢とIK制約の適合を解決し、開始段階をBalance即時有効から分離して
シミュレーションで検証する。終了の実機動作/停止実効性は未完了のまま。
