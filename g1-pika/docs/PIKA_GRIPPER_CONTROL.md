# PIKA gripperの開閉・トルク調整

`scripts/control_pika_gripper.py` で単体の `open` / `close` / `cycle` / `limit` / `interactive` / `diagnose` を指定する。
既定は右 `/dev/pika/right/gripper`。G1身体制御・ACT・SONICとは接続しない。
動作検証にはテスト用シリアルを使用。受信修正時はtigerの実機から2秒間読み取り、
動作指令を送らず終了した。その後、利用者の明示許可で単体PIKAの実機診断を実施している。

最新の利用者実行ではgrip後に実際の急動作も見えると申告された。
Position1.7857/Speed17.964を受信して異常停止、無効化/切断は確認済み。
根因は未確定。以下のgrip目標段階化は急な目標変更を減らす変更であり、
実機の跳ねが解消したことや高電流での安定性を確認したものではない。
その後の許可済み短時間試験では、1.0 A/1.8 A設定の段階閉じを目視で確認した（下記）。
角度閾値は拡大しない。以下の最新修正では、数値が破損したフレーム全体を受信不良として破棄する。

## 2026-10-02続報: 保持中の不要な目標再送・再設定と、破損受信による保持解除を修正

利用者の長時間interactive記録では、0.0904 rad/約−1500 mAで安定して保持していた。
Position2.0/Current−1082348536というJSONの後、ホストが10.23ms後にdisableを書き込み、
36.41ms後から正常な受信角度が開く方向へ変化し、最終0.4363 radになった。
今回のずれは、異常受信→自動無効化→保持解除による開きと整合する。
受信時刻による推定であり、以前のCurrent−340/Position1.7857の実急動作まで同じ原因と断定しない。
[利用者実行の原本と分析](../artifacts/gripper-control/fault-p_9teqe2/analysis.json)。

変更した動作:

- grip目標が0 radに達したら再送を終え、目標を維持する。状態監視は入力待ちでも継続。
- 把持/段階閉じ中の`grip A`再入力は電流だけ変更する。物体で閉じ切れない実測角度へ目標を戻さない。
- 電流の絶対値が1,000,000 mA以上のJSONは数値破損として全体を破棄し、角度/状態/鮮度を更新しない。
  この1000 Aという判定値は明らかな桁破綻を識別する値で、許容電流やモーター定格ではない。
- 正常受信の250ms期限、ドライバ異常bit、電流にこの破損がない範囲外角度の異常ラッチは維持。
  正常JSONのPosition1.7857/Current−340は引き続き停止する。
- interactiveの段階名を`interactive_idle`/`grip_ramp`/`grip_hold`等へ更新し、connectのままにしない。

修正後の許可済み実機interactiveは92.46秒で終了、うち閉目標保持73.29秒。
0.2→1.0→0.5→1.0→1.5→1.8 Aと設定変更し、保持中の位置再送0件。
整定後の正常受信角度0.00009〜0.0012 rad。同種の破損フレーム1件（Position−2.0/巨大Current）を
受信したが、前後250msの正常角度0.0009〜0.0011 radで保持を継続した。
disableは異常受信直後に送らず、17.76秒後のquitで送信し、無効化・切断を確認。
[修正後の実記録](../artifacts/gripper-control/session-_2qc97o7/analysis.json)。独立の目視/力測定はしていない。

正常15,201/拒否28（うち数値破損1）/再同期41、`telemetry_numeric_integrity_ok=false`。
`passed=true`は操作完了と終了処理の結果で、受信品質が正常になったという意味ではない。
最終JSONの`rx.corrupt_frames`/`rx.corrupt_samples`へ件数と最大8件の生フレームを残す。
受信破損そのものの根因は未解消。今回の実動作は空の閉動作で、1.8 A実出力/力の確認ではない。
利用者の先の保持ログでは約1.5 Aの電流が報告されていた。設定の読み戻し/ACKは引き続きない。
追加回帰を含む52オフライン試験で、破損による保持解除の回避/鮮度期限/実範囲外の停止を検証する。

## 2026-10-02: 1.0 A・1.8 A設定での実機開閉結果

利用者の実機動作許可・周囲安全確認のもと、目視の準備を合わせて診断を実施した。

| 設定 | 動作結果 | 目視結果 | 受信/終了結果 |
|---|---|---|---|
| 1.0 A | 電流変更と段階閉じまで完了、終わり0.0008 rad | 滑らか、跳ねなし | 範囲外数値なし、無効化/切断確認 |
| 1.8 A | 電流変更と段階閉じまで完了、終わり0.0022 rad | 滑らか、跳ねなし | cleanup中にPosition-2.0/巨大Current、無効化/切断確認 |

開く段階は0.2 A/0.6 rad、閉じ目標の変化率0.5 rad/s、各hold1秒。
[1.0 Aの記録](../artifacts/gripper-control/session-34rt2ood/analysis.json)、
[1.8 Aの記録と判定補正](../artifacts/gripper-control/session-rmky5u3t/analysis.json)。
設定と空の短時間動作の確認で、全電流出力や把持力を確認したものではない。
受信欠損/不正JSONと数値破綻は残存。旧試行で目視された急動作の根因は未確定。

1.8 A試験で、動作completed設定後のcleanup faultでもpassed=trueとなる漏れが判明。
現在のコードは終了時のfaultもerror/passed=falseへ反映し、新規回帰試験含む46件成功。
元の1.8 A report.jsonは実行時の原本を維持し、analysis.jsonに補正false/理由を明記した。
角度範囲/状態鮮度/異常ラッチは変更せず、数値異常を無視して試験を完走させたものではない。
利用者指示に従い追加カメラ録画実装は行わない。

## 2026-10-02: 原因を切り分ける有限診断

利用者の実機動作許可/周囲安全確認後、この手順を1回実行した。
0.2 Aで0.6 radへ開き、目標を変えず1.0 Aへ電流指令15だけを送信した71.14ms後に、
Position2.0000/Speed-2.000/Current-1083665548のJSONを受信して停止。
前/次の正常値はPosition0.5919付近で、異常文字列も分割前のraw.binに実在する。
閉じ段階は実行せず、位置目標は0.6 radのみ。異常RXからdisable writeまで33.36ms、
無効Status受信まで85.01ms、無効化/切断は確認済み。
[実機の全記録](../artifacts/gripper-control/session-_a22sm42/report.json)、
[送信/受信時刻の分析](../artifacts/gripper-control/session-_a22sm42/analysis.json)。
completed/passed=falseを保持。実際の動きは利用者が見ていなかったため未確認。
電流変更が数値異常の原因とまでは断定しない。9月18日の書込0の受信でも同種の数値異常が記録されている。
追加の無効状態10秒O_RDONLY受信は1619 JSON/不正3、角度0.7270〜0.7271、Status全0x00で、
同種の数値異常はなかった。[追加受信](../artifacts/gripper-rx/inspect-sr25789s/report.json)。
次の同条件試験は利用者の目視で確認し、カメラ録画等の追加実装は行わない。

公式SDKの `set_motor_torque()` は指令15にAを送信し、0〜2 Aと記載する。
説明はモータ電流の設定であり、このファームウェアで「位置制御の厳密な電流上限」として
機能することや、指令15だけで制御モードが変わらないことは裏付けられていない。
CLIの互換オプション名 `--current-limit-a` は維持するが、指定電流の受理/制限動作は未検証。
参考: [公式Gripper](https://github.com/agilexrobotics/pika_sdk/blob/master/pika/gripper.py)。
同リポジトリの[API_Doc.md](https://github.com/agilexrobotics/pika_sdk/blob/master/API_Doc.md)には
「Typical range 0〜8 A」とあり、実装コメントの0〜2 Aと不一致。
メーカー資料だけからこの個体の最大/連続電流を断定できず、CLIの2 A入力上限は拡大しない。

送信待ち中に異常がラッチされると、旧ラッパーは待機後に再検査せず送信できた。
CLIのserial lockを再入可能にし、lock取得後に異常/鮮度/有効状態を確認してから上流送信を呼ぶ。
この抜けはオフラインで再現/修正済みだが、利用者の急動作の根因だと断定しない。
固定ドライバ本体/SHA、指令番号、float32符号化は変更しない。
同API資料のStatus表に従い、0x01〜0x20の異常bitもラッチし、後続制御を中止する。
0x40は有効、0x80は原点設定済みで、これらだけでは異常扱いにしない。
提示された跳ねフレームは0x40で、このフレーム自体にドライバ異常bitは記録されていない。

以下は**単体グリッパを空にし、可動域から人/物を離した状態での診断手順**。
準備時点では実機動作指令なしだったが、上記単体試験については利用者の明示許可を受けている。
通常操作の再開や1.8 Aの反復試行を勧める手順ではない。最初の比較は1.0 Aのみとする。

```bash
python3 -I scripts/control_pika_gripper.py diagnose \
  --port /dev/ttyUSB0 --angle 0.6 \
  --diagnostic-baseline-a 0.2 --current-limit-a 1.0 \
  --grip-speed 0.5 --hold 1 --timeout 3 --execute
```

| 段階 | 指令と観察 | 切り分けること |
|---|---|---|
| `baseline_current` / `baseline_open` | 無効状態で0.2 A、enable、0.6 radへ開く | 基準電流での開動作 |
| `baseline_hold` | 位置目標を変えず1秒受信 | 電流変更前の角度の変動 |
| `current_change_hold` | 指令15だけを1.0 Aへ変更し1秒受信。指令22は送らない | 閉じ目標を出す前に動くか |
| `close_ramp` | 指令15は再送せず、現在角度から目標を0へ段階的に減らす | 閉動作で初めて跳ねるか |
| `closed_hold` / `cleanup` | 目標0を維持し1秒後、disable確認/切断 | 有限時間で終了 |

基準の0.2 Aもメーカー保証済みの安全値ではない。位置到達の許容差は従来と同じ0.025 rad。
閉じ目標の更新は最大10秒、開動作のtimeoutは最大10秒、各holdは最大5秒。
到達/通信エラーやCtrl+Cでもdisable/切断を試みる。
全般の受信角度範囲/250ms鮮度検査に加え、保持段階では開始角度から±0.1 rad、
閉じ段階では開始角度より0.1 rad超開く受信値を中止条件とする。
これは今回の切り分け用の条件であり、較正済みの機械限界・実測速度制限・物理停止保証ではない。
受信threadで条件を検査するため、次の入力pollまでに戻った角度も見逃さずラッチする。
最後の `last_operation_phase` / `fault_detail.phase` で、どの段階まで進んだかを確認できる。

`diagnose` は自動的に `artifacts/gripper-control/session-*/` に以下を保存する。
通常のinteractive等にも `--record-dir artifacts/gripper-control` を追加すると同じ全記録を保存する。

- `events.jsonl`: 通し番号、monotonic秒、段階、入力、送信要求/完了/例外、受信状態/拒否値。
- `raw.bin`: JSON分割前の全受信バイト。途中欠損/破棄データも残す。各readのoffset/sizeはjournalに記録。
- `report.json`: 終了理由、段階、cleanup結果、設定値。起動時に制御コード/固定ドライバのSHAもjournalに保存。

送信完了時刻はホストのwriteが返った時刻で、MCU受理時刻/ACKではない。
記録失敗時は後続制御を止め、disable/切断を優先する。受信フレームに機器時刻や連番はない。
`passed=true` は**この1回が中止条件に触れず終了したこと**だけを示し、
根因解消、1.0〜1.8 Aの使用可否、力やトルクの値を保証しない。
電流変更だけで跳ねれば閉じ目標変更はその事象の原因から除外できる。
基準保持から跳ねれば高電流変更だけを原因にはできない。
閉じ段階だけで跳ねた場合も、記録を見て制御/機器側の切り分けを続ける。

接続後の読み取り確認は `scripts/inspect_pika_gripper.py` で実施可能。
既定はO_RDONLYで受信のみ。`--query-version` 指定時だけ公式の `GET_INFO\r\n` 10 bytesを送る。
enable/disable/電流/位置指令を送るAPIは持たず、ポートを開く際のMCU resetは起こり得る。
2026-10-02の接続後確認は3秒、90,113 bytes、476 JSON/不正1、角度0.0266〜0.0268 rad、
最終Status0x00/Current0/23.8 V。Version応答なし（rawにもVersion/Firmware文字列なし）。
動作指令0、GET_INFO照会10 bytesのみ、close済み。
[受信記録](../artifacts/gripper-rx/inspect-6bgra11k/report.json)。静止受信であり開閉の証拠ではない。

## すぐ開閉・掴む操作を試す

```bash
python3 -I scripts/control_pika_gripper.py interactive --port /dev/ttyUSB0 --current-limit-a 0.2 --execute
```

```text
pika> open 0.6
pika> grip 0.2
pika> current 0.4
pika> open 0.6
pika> stop
pika> quit
```

`grip 0.2` は電流上限0.2 Aを指定し、現在の角度から段階的に閉じて入力へ戻る。
閉じ目標の変化率は既定0.5 rad/s。`--grip-speed 0.2` または `set grip-speed 0.2` で変更できる。
これはソフトウェア側の位置目標の変化率で、実測速度の上限を保証するものではない。
物体に当たって0 radまで閉じられなくても未到達エラーにしない。
`current` で電流を変え、`open` で開く。kt設定や測定器はこの操作に不要。
電流は `0 < A <= 2`。対象物で試し、指を挟まない。

## 受信警告・異常角度の表示

`read buffer hit ... bytes ... resyncing` の連発は、固定ドライバが欠けたJSONの
括弧を待ち続け、4KBを超えるたびに受信バッファ全体を破棄する際の表示。
指令直前のinput-buffer flushなどでもJSONの途中が欠ける可能性がある。
CLI側の受信分割処理を修正し、次の完全なmotor/motorstatus JSONから復旧する。
文字列中の括弧/エスケープを扱い、完全なフレームを処理してから部分バッファの4KB上限を適用する。
固定ドライバ本体・SHA・送信方法は変更していない。

再同期の表示は最大5秒に1回。最終JSONの `rx` に正常/拒否フレーム数、再同期回数、
破棄バイト数、残バッファサイズを残す。壊れたJSONと上記の数値破損フレームは状態を更新しない。
250msの鮮度期限と範囲外角度での停止は維持し、破損電流を伴うフレームの角度を正常値へ補正しない。
異常値で終了した場合はerrorに具体的な値、`fault_detail` にフィールド名/値/受信フレーム
（最大1024文字）を表示する。復旧後の正常データで異常の記録を消さない。

2026-10-01ユーザー実行ログでは0.6 radへの移動1回、grip1回の後、異常角度で終了。
disable_confirmed/port_closedはtrue。異常値そのものが旧ログになく、停止原因の値は未確定。
受信修正の35単体試験成功。tiger `/dev/ttyUSB0` の2秒受信は60,833 bytes、333フレーム、
正常332/不正JSON1、再同期2回、角度0.0016〜0.0019 rad、範囲外なし、最終Status0x00。
アプリUART書込0、ポートclose済み。開閉・電流設定の実機再試験ではない。
[受信記録](../artifacts/gripper-rx/tiger-resync-q3qy5n6l/report.json)と
[256-byte分割再生](../artifacts/gripper-rx/tiger-resync-q3qy5n6l/replay.json)を保存した。
9月18日の記録も再生し、既知のPosition2.0/Current-1080385602を含むフレームを角度範囲で拒否した。

## 実際の跳ね・診断履歴

利用者の再試行は起動1.8 A→open0.6 rad→grip1.0 AでPosition1.7857/Speed17.964を受信。
追質問に「実際の動きも見える」と回答。受信JSONは正常であり、単なる表示問題と扱わない。
[利用者申告の保存](../artifacts/gripper-control/user-report-jix0j_cc/report.json)。
閉じ目標0に対して大きな角度を受信したが、直前の連続状態/送信履歴がなく根因は未確定。

gripは初回に現在の実測角度を目標にし、その後50msごとに0へ目標を減らす。
1更新の変化量はgrip-speed×50ms以下。入力/シリアル処理が遅れても遅延分を一気に追いつかせない。
0に達したら同じ目標を保持し、接触による未到達は従来同様入力へ戻れる。
変更はgripのみ。open/close/move/cycleは従来の到達待ち操作で、速度設定の対象ではない。
新しい速度制御指令/PID設定や測定値の平滑化は使用しない。

異常値のラッチ時はdisable前の速度整定待ちを省き、最終JSONの `fault_log` に
`artifacts/gripper-control/fault-*/trace.json` の保存先を表示する。
異常直前の正常受信256件/送信64件、異常フレーム、直後の受信最大128件/送信32件を保存する。
時刻はグリッパオブジェクト作成からのmonotonic秒で、送信所要時間も残す。
最終JSONにも直前角度/直前状態の経過ms/最後の位置目標を追加する。
保存先は `--fault-log-dir` で変更可能。保存失敗でも無効化/切断処理を先に完了する。
ソフトウェアのdisable要求であり、機械的な停止時刻の保証ではない。

送信形式を[公式SerialComm](https://github.com/agilexrobotics/pika_sdk/blob/master/pika/serial_comm.py)と照合し、
指令1 byte＋float32 little-endian＋CR/LFは一致。指令15はA、22はradを扱う
[公式Gripper](https://github.com/agilexrobotics/pika_sdk/blob/master/pika/gripper.py)とも整合する。
この一致でファームウェアの実際の制御動作や電流設定の受理を確認したことにはならない。
新規4件を含む39単体成功。段階目標/長い処理遅延/0到達/設定拒否、提示された異常値での
履歴保存・即時disable要求・無効化確認、保存失敗でもcleanupすることを検査した。
今回実機ポートは開かず指令なし。fuserでは現在の可視範囲に所有者なし。
過去の瞬間に別プロセスがいなかった証明ではない。実機の跳ね解消は未確認。

## 対話モード（接続したまま調整）

tigerの接続先を明示して起動する。0.2 Aは入力例でありメーカー推奨値ではない。

```bash
python3 -I scripts/control_pika_gripper.py interactive --port /dev/ttyUSB0 --current-limit-a 0.2 --execute
```

起動後は `pika>` にコマンドを入力する。初期状態では位置目標を送らず、
最初のopen/close/move/cycleで自動的にenableする。
開閉後も有効状態を維持し、次の入力を待つ。単発モードとは終了時期が異なる。
`current` は有効状態のままでも電流上限を変更できる。

```text
pika> status
pika> current 0.2
pika> open 0.6
pika> move 0.3
pika> current 0.15
pika> close
pika> set angle 0.8
pika> set hold 2
pika> cycle
pika> disable
pika> quit
```

| コマンド | 動作 |
|---|---|
| `help` | 一覧表示 |
| `status` | 実測状態表示。positionはrad、currentはドライバの生値 |
| `params` | 開き角度・到達期限・cycle待機時間・指定電流上限・トルク定数 |
| `open [rad]` | 指定角度へ開く。省略時は設定した開き角度 |
| `close` | 0 radへ閉じる |
| `grip [A]` | 指定電流（省略時は現在の設定）で段階的に閉じて入力へ戻る。物体接触による未到達を許容 |
| `move rad` | 0〜1.67 radの任意目標へ移動 |
| `cycle [rad]` | 開く→設定した時間待機→閉じる |
| `current A` | 電流上限を送信（0 < A <= 2）。読み戻し/ACKなし |
| `kt Nm/A` | 利用者が確認済みの実効トルク定数を設定（送信なし） |
| `torque Nm` | 設定したktでN·m→Aへ換算して電流上限を送信 |
| `set angle rad` | open/cycleの既定開き角度を変更（0より大きく1.67以下） |
| `set timeout seconds` | 到達期限を変更（0より大きく30以下） |
| `set hold seconds` | cycleの開いた後の待機時間を変更（0〜60） |
| `set grip-speed rad/s` | gripの閉じ目標の変化率（0より大きく2以下、既定0.5）。grip中は次の更新へ適用 |
| `enable` | 有効化。位置目標は送らない |
| `disable` / `stop` | 無効化を確認し、接続したまま入力へ戻る |
| `quit` / `exit` | 無効化・切断して終了 |

パラメータのsetは送信せず次の操作へ適用する。`open 0.6` の引数はその操作限り。
既定角度の変更は `set angle 0.6` を使う。
grip中は入力待ちでも50msごとに段階目標を更新し、状態鮮度/有効状態を確認する。
0 radに達した後は閉じ目標を維持し、再送を終える。把持中のgrip再入力は電流だけ変更する。
open/move/close/cycle/disable/stopはgrip再送を解除する。quit/中断時も通常の無効化・切断を行う。
閉じ目標を出したことだけを示し、接触検出・力測定・把持成功の確認は行わない。
N·m換算に使うktは既定なし。起動時に `--torque-constant-nm-per-a` だけを指定することもできる。
電流上限の変更前値は読み戻せず、終了時の自動復元は行わない。

Ctrl+C/SIGTERM、Ctrl+D/標準入力EOFでも終了処理を行う。
入力待ちでは50msごとに状態を確認し、250ms以上古い状態や異常を検出すると
disable/disconnectを試みて終了する。別の送信threadは作らず同じ制御threadで処理する。
入力ミスは指令を送らず訂正して継続できる。未到達や通信異常は失敗として終了する。
通信断・電源断・SIGKILL時の物理停止を保証する機能ではない。

位置操作は到達確認まで同期的に待つ。`stop` を含む次のコマンドはその完了後に処理する。
移動やcycle待機の途中で中断する場合はCtrl+Cを使用する。
`set hold` はcycleだけに適用し、open/close/moveの後は即座に入力へ戻る。
最終JSONのmove_countは合計、movesには最新64件のみ保存する。

送信なしで入力方法を試すには `--execute` を外す。
`pika[preview]>` では指令計画とパラメータだけを表示し、serial import/open・動作指令なし。
statusも実測値を生成しない。物理シミュレーションではない。

```bash
python3 -I scripts/control_pika_gripper.py interactive --port /dev/ttyUSB0
```

## 接続せずに確認

リポジトリ直下で実行する。`--execute` がなければpyserialも読み込まず、ポートも開かない。

```bash
python3 -I scripts/control_pika_gripper.py cycle --angle 0.6 --current-limit-a 0.2
python3 -I scripts/check_pika_gripper_control.py
```

2つ目はシリアル入出力をテスト用オブジェクトに置換する単体試験。
固定ドライバ本体のJSON解析・送信バイト列・受信thread・到達/無効化処理を使用し、
CLI側でJSONの欠損復旧と異常値の検査を行う。
実機接続・シミュレーション・GPU通信はない。pyserialのインストールも不要。

## 実機で使う場合

### tigerへUSB接続した場合

2026-10-01のポートを開かない確認では、PIKA USB Serial `1a86:7522` は
`/dev/ttyUSB0`（ch341）、`/dev/ttyUSB50` はその同一デバイスへのsymlink。
`/dev/tty50` はUSBシリアルではない。tigerはdialout所属、対象デバイスへのアクセス権あり。
G1搭載PC用の既定 `/dev/pika/right/gripper` はtigerに存在しないため、ポートを指定する。

```bash
python3 -I scripts/control_pika_gripper.py cycle --port /dev/ttyUSB0 --angle 0.6 --current-limit-a 0.2 --execute
```

この確認ではポートを開かず動作指令なし。デバイス番号は再接続時に変わり得る。
一覧確認には `ls -l /dev/serial/by-id/ /dev/ttyUSB*` を使う。

### 共通条件

PIKAが接続されたPC上で実行する。Python 3.10以上とpyserial 3.5が必要。
未導入なら専用venvに `python -m pip install pyserial==3.5` で導入する。
既存の状態受信やgripper bridgeを先に終了し、同じシリアルを複数プロセスで開かない。
保持物を外し、指や周辺物が開閉範囲にない状態で操作する。
接続時は既存ドライバがMCU reset後の1秒待機を行う。

以下は利用者が実機を操作するための例。0.2 Aは入力例であり、
メーカー推奨値・安全上限や、実機確認済みの設定値ではない。

```bash
# 指定電流上限で0.6 radに開き、1秒待ち、0 radへ閉じて無効化
python3 -I scripts/control_pika_gripper.py cycle --angle 0.6 --hold 1 --current-limit-a 0.2 --execute

# 開くだけ / 閉じるだけ（電流設定を送らず、既存設定を使用）
python3 -I scripts/control_pika_gripper.py open --angle 0.6 --execute
python3 -I scripts/control_pika_gripper.py close --execute

# 電流上限設定だけ送る（enableや位置目標は送らない）
python3 -I scripts/control_pika_gripper.py limit --current-limit-a 0.2 --execute
```

`--port` で接続先、`--timeout` で各目標の到達期限（既定3秒、最大30秒）、
`--hold` で各到達後の待機時間（既定1秒、最大60秒）を変更する。
開く角度は `(0, 1.67] rad`、閉じ目標は0 rad。既定0.6 radは全開ではない。
既定の右パスなら、9月18日に記録したUSB by-pathとの一致も確認する。
配線が変わって照合に失敗した場合は左右を再確認する。
`--port` を変更した場合の左右識別は利用者が行う。

すべてのモードで終了時にdisableとdisconnectを行う。
単発のopen/close/cycle/limitは各操作完了後、interactiveはquit/中断/異常時に終了する。
`open` も待機時間終了後に無効化するため、開いた姿勢の保持や把持保持を保証しない。
Ctrl+C/SIGTERM時も無効化を試みる。通信断・電源断・SIGKILL時の物理停止は保証できない。
終了コード0は到達（位置操作時）・新しい状態による無効化・切断の確認成功。
到達許容差は0.025 rad、250ms以上古い状態や異常角度でenable/電流/位置指令を拒否する。
受信角度 `[-0.05, 1.72]` は既存診断と同じ余裕を持たせた範囲で、較正済み機械限界ではない。
最終JSONに失敗理由を出し、失敗時は終了コード1。disableは古い状態でも送信を試みる。

## トルクと電流の関係

既存ドライバの `set_effort_limit(current_amps)` はPIKA `EFFORT_CTRL=15` に
電流上限をfloat32 little-endianの **A単位** で送る。
既存pika_rosも `motor_current_limit` を1000で割って同じ指令へ渡している。
出典は `docs/GRIPPER_REUSE_REVIEW.md` 記載のpika_ros commit
`0f7f6b75a349ceccb252628f5f48a28aaf5c7b6b`、
`src/sensor_tools/src/serial_gripper_imu.cpp` の `initSerial()`。

ラッパーには `set_current_limit(gripper, current_a)` も用意した。
接続済みのグリッパへ呼ぶと値を検査して上流APIへ渡す。
電流上限を省略した開閉ではこの指令は一切送らない。
設定前の上限値を読み取れないため、自動復元はしない。再接続後の設定保持も未検証。

N·m指定は、**対象軸について確認した実効トルク定数** を利用者が渡す場合のみ可能。
電流への換算は `current_A = torque_Nm / torque_constant_Nm_per_A`。
減速比を含む対象軸の実効値と、モータ単体の定数を混同しない。
PIKAのトルク定数はこのプロジェクトで未確認のため、既定値は用意していない。

2026-10-01の仕様調査で[AgileX公式PIKA SDK](https://github.com/agilexrobotics/pika_sdk/blob/master/pika/gripper.py)
の `set_motor_torque(current)` に0〜2 Aの範囲記載を確認した。
このCLIは正の電流設定だけを受け付けるため、起動引数・current・torque換算・Python APIで
`0 < A <= 2` を強制する。超過時はクリップせず拒否し、指令を送らない。
2 AはSDKの範囲上限であり、連続拘束運転の許可・実機の安全保証・推奨開始値ではない。
ktは正の有限値を受け付ける換算定数であり、実機の把持力を決める可変パラメータとは区別する。
把持力測定の準備と未決定事項は[PIKA_FORCE_TEST.md](PIKA_FORCE_TEST.md)。

```bash
# TAUとKTは利用者が確認した値を指定する。まず送信なしで換算を確認。
python3 -I scripts/control_pika_gripper.py cycle --torque-limit-nm "$TAU" --torque-constant-nm-per-a "$KT"
```

これは電流上限へ換算した設定であり、N·mの直接閉ループ制御や把持力Nの指定ではない。
状態JSONには上限値の読み戻し/ACKがない。
`limit_command_sent=true` はUART書き込み完了、`limit_readback_available=false` は
設定値・物理トルクを確認できないことを示す。`passed=true`もトルク精度・設定受理の証明ではない。

## 別PCへ配置

リポジトリ構成を保って `scripts/control_pika_gripper.py` と
`assets/pika/gripper/`（ソース、LICENSE、出典README）を配置すればよい。
別の場所に置くなら `--driver /path/to/pika_gripper.py` を指定する。
固定SHAの照合は維持し、既存vendorや9月18日の試験配置を上書きしない。

2026-10-01単発実装: 13件の単体試験とプレビュー成功、make check-offline一括成功（既存IPC4件skip）。
電流上限をenable前に設定、正確な指令15のバイト列、位置指令の再利用、
設定だけの操作、上限省略、未到達/中断の後処理、鮮度切れ/不正受信の拒否、
N·m換算の必須定数、不正設定値、無効化失敗の非成功扱い、
disable送信以前の無効状態を完了確認に使わないことを確認した。
実機による電流上限・N·m換算・新ラッパーの開閉検証は未実施。

2026-10-01対話追加: 新規9件を含む22単体試験成功。
接続1回で複数操作・有効状態での電流変更、入力ミスの無送信/回復、set/kt/torque/cycle、
disable後の再enable、EOF/中断のcleanup、入力待ちの鮮度切れ、previewの未接続、
複数行貼り付け/末尾EOFと入力のない間の健康確認を検査。送信なしの実CLI入力も成功。
端末PTYの複数入力/quitでもpreviewが正常終了。make check-offline一括exit0（既存IPC4件skip）。
実機での対話操作は今回未実施。

2026-10-01電流範囲補強: 23単体試験成功。2 Aを境界として、超過電流・換算結果の
送信前拒否、拒否後に以前の設定を維持することを追加確認。実機指令なし。

2026-10-01ユーザー訂正: 測定ではなく、簡単に力を変えて操作を試したい。
対話gripを追加。物体接触でも入力へ戻り、電流変更・開く操作へ続けられる。
固定ドライバは無変更、実機でのgrip操作は今回未実施。
26単体試験成功。物体接触中の入力復帰/電流変更/開く操作、再送とstop解除、
不正grip引数の無送信を確認。送信なしCLIの最短操作例も正常終了。
