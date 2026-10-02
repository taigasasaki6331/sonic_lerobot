# G1なしの2 PC統合実装（2026-09-15）

このPCで模擬G1とMuJoCo/WBC、GPU PCで固定LeRobot ACT推論を実行する。
記録RGB2系統・記録10D状態・現在のシミュレーション身体状態をZMQでGPUへ送り、
戻った10D actionをローカルWBC→出力検査→MuJoCoへ接続する。
SSHはスクリプト配置・起動・終了後レポート回収だけに使用する。
実行中の画像・状態・actionはZMQ経路。G1へのSSH/DDS/serial接続はない。

## 一括起動と終了

検証結果: [mock-runtime-2026-09-15.json](mock-runtime-2026-09-15.json)。
GPU実推論の通常30/30件と異常後の新規セッション30/30件に成功。
旧セッション応答・通信断・0.8秒遅延は各5件でaction適用を止め、
各ケース600回のWBC出力と立位/追従の閾値内を確認。身体状態の送受信hashも一致。
単体35件合格。通常ケースの要求から応答適用までのp95は110.805msで、
30Hz実時間動作の達成を示す結果ではない。
ローカル結果は `artifacts/mock-runtime/run-qj1nhyge/`、GPU配置先は
`/home/gpu-user/g1-pika-training/artifacts/mock-runtime-ljIHQM/`。
全試験のGPUサービス終了コード0を確認。G1には接続していない。

このPCから実行する。GPU PCの既存専用環境・鍵認証・モデルが必要。

```bash
make -C /home/developer/workspaces/g1_pika_ws/g1-pika mock-runtime
```

単体試験、通常通信、旧セッション応答、通信断、遅延、異常後の新規セッションを
一括検証する。正常ケースは30推論、各ケース12シミュレーション秒。
終了時に `artifacts/mock-runtime/run-*/summary.json` のパスと合否を表示する。
異常ケースのシミュレータ終了コード1は、所定の停止理由と5件のみの適用、
WBC600出力・立位/追従検査を確認して初めて期待通りと扱う。

表示して正常経路だけ試す場合:

```bash
make -C /home/developer/workspaces/g1_pika_ws/g1-pika mock-runtime-view
```

表示は12秒で自動終了する。途中で閉じた場合は全期間の合格にはならない。
中断は実行ターミナルでCtrl+C。異常後の自動再開はしない。
GPUサービスは通常STOP応答で閉じ、入力断で15秒、SSH起動側の上限180秒でも終了する。
中断時はGPU側がタイムアウトするまで残る場合がある。他の既存サービスは止めない。

`mock-runtime-local` はGPUを使わないCPU/loopback代替の起動口。
GPU版とは別の実行環境なので、GPU版成功をこの代替やGUI版の検証済みとは扱わない。

## 設定と成果物

- 接続設定: `assets/network/mock-runtime.json`。GPU 192.0.2.9:6159、許可送信元192.168.1.25。
  アドレスはこのPC/GPU PC用。以前のG1側6158番サービスとは独立。
- GPUには `artifacts/mock-runtime-XXXXXX/` を新規作成し、今回の専用スクリプトだけ配置。
  既存LeRobot・学習済みモデル・既存スクリプトは上書きせず、依存もインストールしない。
- ローカルrunには30組のPNG/base64入力、単体ログ、ケース別の推論記録、
  シミュレーション結果・承認済みWBC出力・要約・実装ファイルhashを保存。
- 同じモデルhashとLeRobot commitを両PCで照合。GPU側はPythonとGPU依存lockを照合し、
  CUDAがなければ失敗する。CPUへの自動フォールバックや再学習はしない。

## 新しい状態境界と通信処理

`WbcState` は29個の関節名・q/dq、base pose 7、base velocity 6、時刻を持つ。
関節順序・次元・有限値・正規化wxyzクォータニオン・既知の座標規約を検査する。
`WholeBodyController.step_state(state, measured_poses)` へ制御入力を分離した。
既存MuJoCoアダプターがこのAPIを呼ぶ。初期化とTCP実測アダプターはまだMuJoCo依存。
分離前後の通常600フレームの関節目標差は今回0（数値完全一致）だった。
これは実機LowStateの35モーター配列を29関節へ変換する実装ではない。

ZMQソケットは専用worker threadが生成・使用・破棄し、制御ループはキューをpollする。
要求は一度に1件、HWM1、JSON最大2MB、応答期限0.5秒、UUIDセッションと連番を照合。
身体状態は送信時のコピーを保持し、GPUで記録したhash・seq・sim時刻と突き合わせる。
期限切れ/旧応答後は最後の承認TCP目標を保持し、MuJoCo内のWBCは継続する。
後から届く応答では停止ラッチを解除しない。新規セッションは新規実行として起動する。

IPフィルターとUUIDは暗号認証ではない。CURVE/TLSは未実装。
信頼できる閉じた開発LANの短時間試験用で、インターネット公開しない。

## 未完了と実機に持ち越す項目

画像と10D stateは検証episode 39の記録で、シミュレーションの描画画像ではない。
身体q/dq/baseは現在のMuJoCo状態。GPUでは身体状態を検査・対応記録するが、
現在のACTは身体状態ではなく記録10D stateを入力する。画像閉ループでも同期センサーでもない。
記録画像時刻、シミュレーション時刻、PCのwall-clockは別である。
通信はこの2 PCの既存LANを使用し、本番有線ネットワークの実時間性能を保証しない。
30Hzは要求上限で、応答に合わせて再生が遅くなる。停止期限も実機の安全認証値ではない。

実機のモーター対応、浮遊ベース状態推定・座標校正、TCP/取付質量、実測グリッパ幅、
制御権の取得/返却、実機停止遷移、低レベル送信、実タスク成功は未完了。
この成果物だけで実機動作を許可しない。WBC出力は引き続き抽象記録/MuJoCo専用。
