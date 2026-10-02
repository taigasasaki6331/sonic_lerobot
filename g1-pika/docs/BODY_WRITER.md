# G1 native writer（送信なし開発）

2026-10-02。`scripts/body_writer.hpp`に2ms周期を設計目標としたC++ owner loopを追加。
**統一起動経路はrecord-only。実送信/制御権解除を行わない。**
G1上の最新コードのコンパイル、500Hz実送信、物理停止は未検証。

## 実装範囲

- `WriterMailbox`：同一ホストの身体/参照を最新値で保持。全入力を置換前に検査する。
  不正入力→直後の正常入力でもfaultが消えない。古いsession/連番不正/未来時刻/期限超過、
  q/dq/ゲイン/float32/29関節の範囲、参照変化0.05radとモデル速度を検査する。
  この設定は既存診断gateに合わせた設計値で、実機の安全規格・実測適合ではない。
- 身体のCRC/P-R/machine、進むtick、100ms以内の局所鮮度、motor診断の明示入力を要求。
  重複tickは年齢を更新しない。machine/P-R変更は停止ラッチ後でも記録し、古い型式のdamping/復帰を拒否。
  最新receiverは35個のraw_motor_state/motor_modesを出力する。
  record runtimeではraw bits=0を要求するが、firmwareのmotor健全性認定ではない。
  `motor_health_checked`や局所phaseのbool自体が物理的な事実を立証するわけではない。
- `WriterKernel`：同じ判定を疑似時計と実thread双方で利用。2ms未満で重ねて出力せず、
  遅れた周期をまとめて送るcatch-up burstを作らない。通常出力開始後の10ms超の間隔はfault。
- `run_body_writer`：`steady_clock`と停止要求で起床できるcondition variableによる単一owner loop。
  50Hz推論が更新した参照を保持し、毎周期で身体/目標の年齢を再検査する。
  目標更新停止、身体更新停止、書込みfalse/例外、10ms超の書込みで停止要求をラッチ。
  停止候補の呼出し前にラッチし、GPU/RPC/別workerのjoinを先に待たない。
- `AdapterWriterSink`：既存build-only SDKアダプターへの接続点。
  正の29 kdを呼出側で明示し、実機用の既定ゲインを選ばない。
  owner loopの前後を含め、同じ単一I/O-ownerだけがadapterを操作する契約。

身体データのAPIは将来の信頼できるG1-local gateway用であり、GPUのbodyコピーを受け入れる入口ではない。
別PCのmonotonicを直接比較しない。`source_age_bound`もG1側で保証した経過時間上界が必要。
現行BodyLifecycleの人工診断ACKから、局所phase/身体健全性/実機権限を生成しない。

## 停止・周期の限界

SDKのblocking/遅延は未検証。書込み中はこのthreadから割り込めず、
stop要求が通常書込みの直前チェックと実書込みの間に競合する場合も含め、
既に許可した1書込みを取り消せない。
遅い書込みの復帰後は通常出力を再開せず、停止候補を1回要求する。
停止候補自体もSDKでブロックし得る。G1-localの別途確認された停止手段が必要。

stop候補の成功を物理停止と表示しない。sinkがphysical_stop_confirmed=trueを返しても、
loop報告はfalseのまま。自動復帰/再arm/再接続は行わない。
2msは設計周期。通常Linux・mutex・条件変数の処理で、実時間保証はない。
RT優先度/governor/capability等の恒久変更はしていない。

## 検証

```bash
make body-writer-check
```

tigerのみ、既存g++/Pythonで実行。SDKリンク、ソケット、カメラ、serial、G1、GPU不要。
24条件を検査し、`artifacts/body-writer/run-*/report.json`へソースSHAと結果を保存する。
疑似身体/健康状態/準備完了/ゲイン/試験許可はすべて人工入力。
疑似時刻3秒では50Hz参照150件→500Hz判定1500回。実thread5ケースで待機→停止、
短時間の参照更新、write失敗/例外、25msの遅いwriteを検査した。
書込み時間の計測を実SDKの性能に代用しない。

最初の保存結果：`artifacts/body-writer/run-l9olmfsq/report.json`、全24条件成功。
短時間threadは39回、最大開始間隔2.118ms。25ms疑似write後はdeadline faultで通常出力再開なし。
実G1での周期/停止の確認ではない。`make check-offline`へも試験を組み込む。

## 次の接続

1. 実LowState motor診断とnative入力の取得/変換。保存時刻の再生とライブの同一ホスト時刻を分離する。
2. 実gatewayで初期参照/実測q,dq/ownership/支持・構成/セッションを統合する。
   最初の参照適合とINITも上位の責務で、このloopはINIT軌道を勝手に作らない。
3. G1起動後に最新ソースのbuild-only確認。実SDKのlink/起動は別工程として扱う。
4. 現場条件と明示許可が揃ってから限定実送信/停止検証。未解決の保存SONIC範囲超過をそのまま送らない。

全体TODOと判明した課題は[IMPLEMENTATION_TODO](IMPLEMENTATION_TODO.md)を参照。

## 統一起動経路

10月2日続報。`local_body_service --native-runtime`で、局所stdin受信・既存SONIC ZMQ envelope・
BodyLifecycleの3秒初期参照/姿勢整定・native WriterMailbox/run_body_writer/BodyIoAdapterを接続。
native I/O-ownerだけが記録backendの解除/出力/停止候補を操作する。
LowCmdは固定SDKのデータクラス/CRCを使う1004byteメモリ。SDK通信ライブラリはリンクしない。
GPUのbodyコピー・診断ACKを実機の鮮度/制御権/準備完了に昇格させない。
保持中のSONIC目標も元のsource ageを引き継ぎ、参照の再生成で寿命を延ばさない。
q変化0.05rad/モデル速度/期限/identity-loss gateは維持、重複tickは鮮度更新しない。

```bash
make body-runtime
make body-runtime-expiry
make body-runtime-build
```

G1/GPU不要。人工の身体・目標と局所IPCを使用。初期参照→姿勢確認→目標受理→停止を通す。
初期姿勢へ動いた身体・CRC一致metadata・ownershipはfixtureで、実測や実CRC検証ではない。
通常最終`run-0ztzrug5`：5秒、229目標/68受理、native通常2390回＋停止候補1回、owner/入力thread終了。
期限切れ最終`run-af7qw18j`：人工peerの目標通信/stdinを継続し、身体入力だけ停止。
native reason=writer_body_crc_health_or_age_invalid、通常1915回＋停止候補1回、異常終了1が期待結果。
両方最後のメモリCRCは独立Pythonと一致。2ms設計値は500Hz実時間保証ではない。

packageの`runtime/launch_body_runtime.py --build-only`はSHA照合後、実行ホストでnative libraryを再build。
tigerのx86 binaryをG1/aarch64用とみなさない。G1停止中につき今回のaarch64 buildは未実施。
G1でのstandalone launcherはinterface/endpoint/peerを明示し、同一ホストの読み取り専用receiverを起動する。
通常G1Deploy/MotionSwitcher/LowCmd publisherを起動する入口ではない。

既存LeRobot→IK→SONIC実入力ランチャーにも接続済み（コードのみ、今回G1未起動）：

```bash
make online-record DEVICE_READ_ACK=1 BODY_RUNTIME=1 ONLINE_SECONDS=5
```

G1起動・右PIKA/カメラ再装着と構成確認後に行う**読み取り＋メモリ出力**試験用。
現状は右PIKA取り外し中なので今の実行は求めない。
immutable package配置/現地compile/局所CRC受信/目標sink/終了・journal回収までrunnerに組み込む。
GPU ACT/IK/SONICが実G1のnative runtimeに接続して通ること自体は未検証。
保存SONICの147/150範囲外や初回0.3437radをclipして流す実装ではない。
物理SDK出力・実ownership/INIT/復帰/停止方式の検証は残る。現場確認と明示許可を別途要する。
