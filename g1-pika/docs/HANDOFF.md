# 引き継ぎ（2026-10-02整理）

> 公開用コピー：ネットワーク値・機器識別子・ローカルパスは例へ置換。保存試験結果は原本の記録で、例設定で実機試験した証拠ではありません。クラウドから機器接続・実機指令を行わないでください。


## 最新：クラウドへ継続するためのソース移行準備

ユーザーはgalleriaのネットワーク外、G1起動不可。GPU/G1接続はせず、CPU開発用の
cloud-export/cloud-setup/cloud-checkと[CLOUD_HANDOFF](CLOUD_HANDOFF.md)を追加。
未コミット分を含む現行ソース/固定vendor部分/URDFとSHA manifestを別ディレクトリへコピーする。
データ本体・重み・鍵・ログ・バイナリは除外し、元のGit・資産を保存する。
送信先は利用者指定のtaigasasaki6331/sonic_lerobot。
codex/cloud-handoff-20261002をmainの68c7294475646f3bdb373594c806d7f1b95b9e86から作成済み。
mainは変更せず、公開用コピーだけを新ブランチのg1-pika/へ配置する。クラウド環境は未作成。
利用者はpublicのままでの送信を了承。公開コピーの内部IP/配置/機器識別子は例へ置換する。
既存remoteはPIKAなしπ0/π0.5・48次元actionの別方式。src/tests/docs/patches/.githubを保存し、
ACT/10次元/PIKAをg1-pika/サブディレクトリへ配置して区別する。
公開コピーpublic2で128試験成功/IPC2skip。初回はgenerated/State.cのSource行を匿名化したため
manifest照合で停止した。コメントのみの差分を確認し、公開コピーの生成物SHAを別記録して再確認。
URDFもmesh filenameだけ相対化した派生SHAを記録。原本/固定上流は変更なし。
GPU/MuJoCoモデル推論・G1実入力/実機検証は後日。実機指令なしは継続。
分離コピーsnapshot-20261002-check2で専用venvを新規作成し、numpy1.26.4のみ導入。
cloud-checkの18スクリプト、128件成功/IPC2件明示skip、SDK-free runtime build成功。
ローカルx86/Python3.10での準備確認で、Codex Cloud上の起動確認ではない。
検証詳細はPROGRESSとartifacts/cloud-source/validation-20261002.json。

## 最新：G1側record runtimeの統一起動、既存LeRobot/SONICランチャーへ接続

細かな部品追加ではなく、起動から停止までの縦の経路を優先。
local_body_runtime.py/body_runtime.cpp/.pyで局所状態→BodyLifecycle INIT/整定→SONIC ZMQ→
native WriterMailbox/run_body_writer/BodyIoAdapter→固定LowCmdメモリ→停止候補を接続。
SDK client/DDS command publisherはリンクしない。人工ACK/局所phaseはrecord-onlyに限定。
保持目標のsource ageを持ち越し、参照再生成で期限を延長しない。identity loss/重複tick/制限は維持。
receive_stateのstreamへ35 raw_motor_state/motor_modesを追加、CRC canonical layoutは無変更。
raw bits=0をrecord criterionとして要求するが、firmwareの健全性認定ではない。

make body-runtime：最終artifacts/body-runtime/run-0ztzrug5、5秒229目標/68受理、
native通常2390回＋停止候補1、owner/入力thread正常終了、最後のnative memory CRC独立一致。
make body-runtime-expiry：最終run-af7qw18j、stdinを開きpeer目標通信を続け、身体だけ停止。
native writer_body_crc_health_or_age_invalidで停止ラッチ、通常1915回＋停止候補1、owner終了。
service exit1はこの故障試験の期待結果。人工入力/人工CRCmetadata/人工ownershipで、実G1の証拠ではない。
通常最大開始gap8.46msは10ms gate内だが、500Hz実時間性能の認定ではない。
初期試行のfuture-tick raceを人工feederで修正。初回応答期限/compile失敗を含む全ログを保存、
再試行での合格を失敗履歴削除/可用性保証に置き換えない。自動再接続・閾値緩和なし。

launch_body_runtime.pyとimmutable manifest/profile/source packageを追加。
build-onlyでmanifest照合→実行ホストで再compile。tiger x86 libraryをG1 binaryに流用しない。
既存online-recordへBODY_RUNTIME=1/ONLINE_SECONDS=5を追加：
tiger配置→GPU→G1現地build/厳密CRC reader→既存ACT/IK/SONIC目標sink→終了/journal回収。
今回G1は停止中、右PIKA取り外し中なのでG1接続/新aarch64 build/実入力版は未実行。
実SDK出力・現場ownership/INIT/停止/復帰は残る。物理動作起動口を提供/実行したとはしない。

check-offline exit0（IPC6明示skip）、既存local_body_service --ipcの7件成功、
online loop20件成功、py_compile/diff check/Make dry-run成功。
portable launcher --build-onlyもx86で成功。通常/expiryは最終ソースで再実行成功。
README/BODY_WRITER/IMPLEMENTATION_TODOを更新。G1起動は今の非実機作業のために求めない。

## 最新：部品の詳細より統合動作を優先、make runで30秒動作

ユーザーが、細部のマイルストーンは後で割り振るため、まず動かせる施策の開発を優先と指示。
実機指令なしを維持し、既存LeRobot/SONIC/MuJoCoへnative身体出力をつなぐ動作経路を実装。
`make run`はgalleriaだけでモデル照合/起動/30秒動作/終了/動画回収を一括実行する。
`make run RUN_SECONDS=3`で短い動作。G1は不要、実機送信モードへ自動切替しない。

新規sim_body_gateway.cpp/.py：BodyIoAdapter/WriterKernel＋固定SDK LowCmdデータクラス/CRCを再利用。
LowCmdに格納されたfloat32 q/dq/tau/kp/kdからMuJoCoのトルクを計算する。
SDK client/publisher/networkはリンクしない。simulation-controller解除/停止/復帰は人工backendのみ。
データクラス抽出をexport_data_headersへ共通化、固定SHA/ライセンスを維持。
実機WriterMailboxの0.05rad/速度gateは変更せず、simulationは物理準備完了を認定しない。
起動変化0.3437rad、physical_step_gate_passed=falseを記録したまま。

3秒artifacts/sonic-mujoco/run-7yfd38m5成功。
最終30秒run-u9gljra3：ACT900/SONIC1500、native15100tick（0.2秒warmup込み）。
立位/モデル範囲外0、最低高さ0.73125m、傾き最大0.08010rad、右TCP移動最大0.28080m（起動整定含む）。
保存出力の集計では1秒後以降の右腕実測関節変化幅最大0.32567rad。
動画755frame/ffmpeg exit0、ACT/SONIC exit0。ONNX/TRT前後SHA不変。
outputs/report.json/body-runtime.json/simulation.mp4/trajectory.jsonを回収。
動画中間frameと関節記録でPIKA付きG1の立位/腕運動を確認。
make check-sonic-simは既存4＋4/新規gateway2成功、LowCmd既存3成功、diff check成功。

保存画像1組・幅0.04m仮定・固定gripper/旧質量モデル、同期simulation-time。
視覚タスク/実把持/実時間性/実G1 INIT/ownership/物理停止の成功とはしない。
実機側は読み取り入力とSDK backendをこの動作経路へつなぐruntimeが次の優先。
右PIKA取り外し中の実構成、G1停止申告は変わらず。細部診断でこの統合を後回しにしない。

## 最新SONIC：G1停止中、native writerを送信なしで実装

2026-10-02再開。ユーザー申告はG1シャットダウン中。G1起動/接続を求めずローカル作業を実施。
最新ワークスペース指示はMuJoCo＋LeRobot/SONIC統合と実機側実装を継続、実機動作指令なし。
前日の「現在シミュレーションなし」は過去の状態。今回sim/GPU/G1接続・機器I/Oは実施なし。

`body_writer.hpp`へnative 2ms設計の単一owner loop・最新値mailbox・局所watchdogを追加。
全入力を置換前に検査し、不正→正常でfaultを隠さない。session/sequence/年齢/範囲/参照変化/速度、
身体CRC/P-R/machine/tick/motor診断と局所phaseを要求。GPU bodyを入力とするpeer APIはない。
身体/目標100ms期限、writer10ms超gap、write失敗/例外/遅延で停止ラッチ→停止候補要求。
GPU/RPC/joinを先に待たず、missed周期のcatch-up burst・自動復帰を行わない。
BodyIoAdapterにidentity lossラッチを追加し、型式/P-R変更後は古い型式のdamping/復帰も拒否する。
SDK-free24条件・adapter19条件成功。G1向けbuild runnerは19条件へ更新したが今回G1では未実行。
10月1日のFT3T3pは旧18条件コードのG1証拠で、今回最新コードの認定ではない。

`make body-writer-check`はローカルのみ、`artifacts/body-writer/run-l9olmfsq/report.json`を保存。
人工入力の150参照/1500周期と実thread5ケース。短時間更新は39回/最大開始間隔2.118ms、
25ms疑似write後はfaultで通常送信再開なし。実SDK実効性/500Hz実時間性/物理停止の検証でない。
停止候補SDKがブロックする可能性は残り、physical_stop_confirmedはfalse。
現在のreceiver/記録サービスからnative motor-health/局所phaseはまだ供給せず、実gateway未接続。
実ownership/INIT/最初の参照適合・SDK runtime/現場停止検証も未完。
詳細[BODY_WRITER](BODY_WRITER.md)。G1起動が必要な工程は目的付きでまとめて案内する。

ユーザー依頼で[IMPLEMENTATION_TODO](IMPLEMENTATION_TODO.md)を追加。
当初TODO（保存方針から再整理）/進行TODO/判明課題/ユーザー操作を区別し、READMEからリンク。
追加の継続承認を求めず、G1停止中に可能な送信なし開発を進める。
最終make check-offline exit0（IPC6件明示skip）、git diff --check成功。
ASan/UBSanの24条件も成功。ただしLeakSanitizerはptrace環境で実行不能、leak検査は未確認。

## 最新の実機構成：右PIKAグリッパ取り外し中

2026-10-01、ユーザーが別試験のためG1右腕のグリッパを取り外していると申告。
左PIKA/取付具/カメラ/配線が残っているか、USB接続先や再装着時期は未確認。
右PIKA付きモデルの質量/TCP/干渉条件を現在の実機の条件として扱わない。
先のLowState/ZMQ記録受信・native ABI/CRC試験は送信なしの診断であり、
PIKA装着・把持・PIKA付き全身制御が実機で成立したという証拠ではない。
既存データ/モデル/ログ/デバイス設定は保存し、取り外しだけを理由に削除・書換えしない。
身体状態読み取りや送信なし開発は継続可能。右PIKA入力/把持を必要とする試験は
再装着と実構成の確認後に行う。今回、新たな機器接続・実機指令・試験再実行なし。

## 最新PIKA: 受信破損による保持解除・保持中の目標再送を修正、1.8 Aまで再確認

利用者のinteractiveは終了。fault-p_9teqe2/trace.jsonを保存したままanalysis.jsonを追加。
保持0.0904 rad/約−1500 mA→Position2.0/Current−1082348536→10.23ms後ホストdisable→
36.41ms後から開く正常受信→最終0.4363 rad。今回のずれは自動無効化による保持解除と整合。
受信タイミングによる推定で、旧Current−340/Position1.7857の実急動作の根因は未確定。

CLIはgripの0目標到達後に再送を終え、把持/段階閉じ中のgrip再入力は電流だけ変更。
実測角度への目標再設定をやめた。50ms監視/250ms鮮度/角度範囲/異常bitは維持。
|Current|>=1,000,000 mAは桁破綻の受信フレームとして全体を破棄し、状態/鮮度を更新しない。
許容電流/定格の判定ではない。正常電流を伴う範囲外角度は停止、破損が続けば状態期限切れで停止。
corrupt_frames/最大8件の生フレームとtelemetry_numeric_integrity_okを最終出力へ追加。
interactiveのphaseがconnectのままだった表示も修正。

許可継続下の実機session-_2qc97o7は92.46秒、閉目標保持73.29秒。
0.2→1.0→0.5→1.0→1.5→1.8 A、保持中の位置送信0件、整定後0.00009〜0.0012 rad。
同種破損1件は破棄して保持継続、前後正常位置0.0009〜0.0011 rad。
17.76秒後のquitで初めてdisable、無効化・切断確認済み。終了後のfuserも可視所有者なし。
正常15201/拒否28（数値破損1）/再同期41。passed=trueは操作完了/終了、数値受信品質はfalse。
events/raw/report/analysis保存、最終52オフライン試験成功（43.801秒）。ドライバ固定SHAは無変更。
受信破損そのものの根因/旧急動作の根因は残存。今回空動作の1.8 A設定で、全電流出力/力は未測定。
カメラ録画等の追加なし、G1身体/腕の動作なし。詳しくはPIKA_GRIPPER_CONTROL.md冒頭。

## PIKA履歴: 1.0 A・1.8 A設定の段階閉じを目視確認、受信異常は残存

周囲安全/単体動作の許可は下記のとおり継続。目視準備を合わせて同じdiagnoseを再実行。
1.0 A設定は開く/電流変更/段階閉じ/無効化・切断まで完了。利用者は「滑らかに動き、跳ねなかった」。
session-34rt2oodに全記録・phase-analysis・analysis、正常895/拒否2/再同期52、閉じ終わり0.0008 rad。
続いて希望範囲の1.8 A設定も同一手順で動作完了し、利用者は「滑らかで、跳ねなかった」。
session-rmky5u3tに全記録・analysis。閉じ終わり0.0022 rad、無効化/切断確認済み。
ただし最初のdisable writeの77.45ms後、cleanup中にPosition-2.0/Current-1081434178の正常JSONを受信。
値はrawにも実在。動作中の受信範囲外はなかったが、受信の数値破綻が解消した証拠ではない。
電流変更だけの原因と断定しない。ユーザーが跳ねを見た旧試行の根因も未確定。

この実記録でcompleted設定後のcleanup faultをpassed判定へ反映しない漏れが判明。
CLIにerrorを残してpassed=falseとする修正、新規回帰試験含む46件成功（42.109秒）。
1.8 Aの元report.jsonのpassed=trueは実行時の漏れとして原本を保持し、
analysis.jsonのcorrected_session_passed=falseで補正理由を明記。原本を黙って書き換えない。
コードの角度閾値/異常ラッチ/状態期限は緩めていない。固定ドライバ/SHA/指令形式も保持。
受信欠損/不正JSONも残る。今回の確認は設定と空の短時間動作で、全電流出力/力/長時間の保証ではない。
こちらの診断はすべて無効化・切断済み。追加の動画実装や録画はなし。G1身体/腕の指令もなし。
終了確認時には利用者側のinteractive（PID997912、1.8 A設定）が/dev/ttyUSB0を使用中。
こちらの診断の残留ではないため停止せず保持。今後このポートへ重ねて接続しない。

## PIKA履歴: 許可済み単体診断で閉じ指令前の受信異常を再現

利用者が「実機動かしてOKです、周囲の安全は確保済みです」と明示許可。
これはtiger直結単体PIKAの原因切り分けで、G1身体/腕/全身制御の許可ではない。
diagnoseを/dev/ttyUSB0で1回実行：基準0.2 Aで0.6 radへ開く→1秒保持→指令15だけ1.0 Aへ変更。
変更write完了の71.14ms後、正常JSONにPosition2.0000/Speed-2.000/Current-1083665548を受信。
前/次の正常フレームはPosition0.5919付近。異常文字列はraw.binに実在、Python生成値ではない。
後続のclose_rampは実行せず、位置目標は全送信で0.6 radのみ。
異常RXからdisable write33.36ms/無効Status受信85.01ms、disable_confirmed/port_closed=true。
session-_a22sm42にevents/raw/report/analysis、fault-dkh_7swkに前後履歴を保存。
completed/passed=falseを維持。閉じ目標の段階化だけでは今回の受信異常を防げない。
電流変更が原因との因果確定ではない。9月18日のO_RDONLY受信でも同種のPosition2.0/巨大Currentあり。
今回利用者は動きを見ていなかったため、実際の跳ねは確認していない。
無効状態の追加10秒O_RDONLY受信は1619 JSON/不正3、角度0.7270〜0.7271、全Status0x00。
inspect-sr25789sに保存、UART書込0/close済み。この範囲では同種の数値異常なし。
魚眼camera-preview-jsi2v8zcの静止1枚を取得。利用者が「余計な工数はかけなくていい」と指示し、
追加の動画/カメラ実装は行わない。次の同一診断は利用者の目視で確認する方針。
実機の動作許可は継続しているため取り直さず、目視の準備だけを調整する。
この最初の診断時点では1.8 A未実行。後続の設定動作確認は冒頭参照。
今回を安定使用/電流受理/把持力の証明にしない。

## PIKA履歴: 原因切り分けを準備・接続後の情報読み取り

「不透明な状態のまま進めない」という利用者指摘を受け、制御コードを再監査。
送信ロック待機中に異常がラッチされても旧コードは待機後の再検査なしで送信できた。
CLIのRLock内で検査してから上流送信を呼び、この抜けを修正。実際の跳ねの根因と断定しない。
公式SDKの指令15(A)の説明は電流設定。「厳密な電流上限」という解釈/設定ACKは未確認。
SDK実装コメント0〜2 AとAPI_DocのTypical 0〜8 Aが不一致。CLIの2 A上限は拡大しない。
APIのStatus表に従いbit0x01〜0x20を異常停止対象へ追加。0x40有効/0x80原点済みは除外。
利用者の異常フレームStatus0x40にはその時点の異常bitなし。

control_pika_gripper.py diagnoseを追加：基準0.2 Aで0.6 radへ開く→1秒保持→
位置目標を変えず電流15だけ1.0 Aへ変更/1秒受信→電流15の再送なしで段階閉じ→1秒後disable/切断。
保持中±0.1 rad、閉じ中開始より0.1 rad超の開きも受信threadでラッチし後続段階を中止。
実測速度制限や物理停止保証ではない。閉目標更新10秒/hold最大5秒/到達timeout最大10秒。
全受信raw.bin、段階/指令要求・完了/受信/入力のevents.jsonl、report.jsonをsession-*へ保存。
通常interactiveも--record-dir指定で全記録。記録失敗時は後続制御を中止、cleanupを優先。
固定ドライバ/SHA/符号化は無変更。新規6件を追加（全45件の検証結果はPROGRESS参照）。

利用者が「つないだ」と申告後、tiger /dev/ttyUSB0・alias ttyUSB50を再確認、fuserの可視所有者なし。
inspect_pika_gripper.pyで3秒受信/公式GET_INFO照会10 bytesのみ送信。動作指令なし。
90,113 bytes、476 JSON/不正1、角度0.0266〜0.0268、最終Status0x00/Current0/23.8 V、close済み。
Version応答なし。artifacts/gripper-rx/inspect-6bgra11kにraw/frames/report保存。
この無効状態の受信だけで跳ねの解消や1.0〜1.8 Aの使用可否を判断しない。
この準備時点ではdiagnose実機実行はまだなく、後から利用者の明示許可で上記1回を実行した。
具体的手順はPIKA_GRIPPER_CONTROL.mdの2026-10-02節。1.8 Aへ自動増加する試験ではない。

## PIKA履歴: 実際の跳ね申告、grip段階化と異常時の診断保存

利用者の再実行は起動1.8 A→open0.6→grip1.0 A、Position1.7857/Speed17.964を受信して終了。
JSON正常、disable_confirmed/port_closed=true。追質問に「実際の動きも見える」と回答。
単なる受信表示の問題としてフィルタで無視しない。直前の連続状態がなく根因は未確定。
artifacts/gripper-control/user-report-jix0j_cc/report.jsonへ申告を保存。
gripの0 radへの一括目標を変更し、実測開始角度から50msずつ段階的に減らす。
既定の目標変化率0.5 rad/s、--grip-speed / set grip-speedで0 < 値 <= 2を指定。
1更新も速度×50ms以下とし遅延分の追いつきジャンプをしない。0で同目標を再送。
物体接触での入力復帰/current/open/stopを維持。変更はgripのみ、実測速度の制限ではない。
異常値の範囲/ラッチ/250ms鮮度/電流2 A上限/固定ドライバは変更なし。
異常時はdisable前の速度整定待ちを省く。機械的な停止保証ではない。
fault_logのtrace.jsonに直前RX256/TX64、異常フレーム、直後RX128/TX32を上限付きで保存。
最終JSONに直前角度/経過ms/最後の位置目標、--fault-log-dirで保存先を変更可能。
保存エラーでも先にdisable/closeを完了。新規4含む39単体成功、提示異常フレームの再生も成功。
公式SDKの指令15(A)/22(rad)・float32 little-endian/CRLFと照合、一致。物理動作の証明ではない。
今回実機port open/動作指令なし、fuserの可視範囲では現在の所有者なし。
実際の跳ね解消は未確認。1.0〜1.8 Aの反復試行を続けず、異常閾値を広げて合格にしない。
詳細はPIKA_GRIPPER_CONTROL.mdの実際の跳ね/診断履歴を参照。

## PIKA履歴: 受信バッファ警告の連発を修正

ユーザーがtigerの対話実行中にread buffer hit約4KBの警告が連発し、異常角度で終了したログを提示。
ログ上は0.6 radへの移動1回/grip1回、disable_confirmed/port_closed=true。
旧ログに異常なPositionの値がなく、今回の停止値/ハードウェア原因は未確定。
固定ドライバの括弧待ち/4KB全破棄をCLI側TelemetryFramerで置換した。
次の完全なmotor/motorstatus JSONへ再同期、文字列/エスケープ対応、完全なフレームを先に解析、
部分バッファ4KB上限。固定ドライバ/送信方式/電流2 A上限/250ms鮮度/異常値ラッチは維持。
表示は最大5秒に1回、最終JSONにrx統計とfault_detail（具体的な値/受信フレーム）を追加。
新規9件含む35単体成功。欠損を流し続ける対話操作でも復旧・開閉・電流変更・無効化を確認。
実機動作指令は送らず、了承済みの読み取りのみtiger /dev/ttyUSB0で2秒実施。
60,833 bytes/333フレーム、正常332/不正JSON1、再同期2、角度0.0016〜0.0019、最終Status0x00。
UART書込0、close済み。artifacts/gripper-rx/tiger-resync-q3qy5n6lのraw/report/replayを保存。
保存9月18日記録でもPosition2.0/Current-1080385602を含むフレームは角度範囲で拒否。閾値緩和なし。
再起動の入口は従来どおりinteractive --port /dev/ttyUSB0 --current-limit-a 0.2 --execute。
修正後の実機開閉/把持は利用者による再実行待ち。詳細PIKA_GRIPPER_CONTROL.md。

## PIKA履歴: 測定ではなく簡単な動作試行、gripを追加

ユーザーが「試したいだけ、測定したいわけではない、さくっと動かしたい」と訂正。
測定器/kt/測定計画を操作の前提にしない。既存対話CLIへgrip [A]を追加。
指定電流でenable/閉じ目標0 radを送り、到達待ちをせず入力へ戻る。
物体接触で閉じ切らなくても未到達エラーなし。入力待ち中に100msで同目標を再送。
currentで調整、openで開く、stopで無効化、quitで切断。電流0 < A <= 2と鮮度検査を維持。
open等の移動/stopでgrip再送を解除し、古い閉じ目標が後から再送されないようにする。
把持成功や力Nの確認ではない。実機へは今回も指令を送っていない。
新規3件を含む26単体試験成功、送信なしCLIの操作例も正常終了。
以前の測定提案は現在の希望と異なるため参考記録として保存。

## PIKA履歴: 力測定の相談・電流範囲を補強

ユーザーが実際にどこまで力を出せるかの検証を希望。async照会に「測定器はまだない」と回答。
最大把持力Nの確定には圧縮測定器が必要。既知重量の保持試験は保持能力の評価として区別する。
kt上限の相談に続いて公式AgileX PIKA SDK set_motor_torqueの0〜2 A記載を確認。
control_pika_gripper.pyにMAX_CURRENT_A=2を追加し、引数/API/current/torque換算を全て範囲検査。
超過はクリップせず無送信で拒否。23単体試験成功、実機接続/動作指令なし。
PIKA_FORCE_TEST.mdにN単位の圧縮測定、定義/開口幅/センサー定格、低電流からの段階計画を記載。
一般closeはセンサー接触でも未到達になるため、そのまま力測定に使わない。
接触の期限付き保持/測定器の読取りは未実装、測定器条件を確認して具体化する。
2 A上限は連続拘束運転の保証ではなく、ktや実測最大力は未確認。

## SONIC履歴：実LowState CRCと身体SDKアダプターのbuild-only検証

右PIKA取り外し中の条件を維持し、身体読み取り・送信なし開発だけを実施。
この10月1日作業では当時のワークスペース指示に従いシミュレーションなし。
その後の現行方針は10月2日冒頭を参照。以前のMuJoCo結果/実装は保存。
厳密SSH照合でG1到達/aarch64を確認。新規パッケージinstall、既存環境/モデル/設定の上書きなし。
実機publisher/ReleaseMode/INIT/damping/カメラ/シリアルを起動していない。

`state_receiver/state_crc.h`は固定SDKのnative LowState2092bytesを全フィールドから再構成し、
paddingを0にしたCRCを照合する。`receive_state --verify-crc`は全受信で検査、不一致はexit3。
strict monitor/serviceはCRC必須・証拠欠落/不一致をラッチ拒否。旧コマンドは未確認を明記したまま保存。
128全フィールドfixtureのnative bytesがx86_64/G1 aarch64で完全一致、独立Python CRCも一致。
双方SHA107b35f26ef7ea599eb47871ab1cdf53eb3ea5d31e93851269c919d69026302c。

`make body-local-crc-check`最終結果は`artifacts/local-body/local-body-EHFf0D/outputs/`。
実LowState165frame全CRC一致（mode_machine=5/mode_pr=0）、最大間隔20.97ms、
sample因果年齢上界最大31.63ms。保存SONIC150件は全gate/受理0/抽象writer0/実機指令0。
147件のモデル範囲超過は変更せず残す。保存SONICの生成時刻鮮度/実追従/タスク品質の合格ではない。
`make body-local-crc-expiry-check`は`local-body-zwvbSW/outputs/`。
77実frame全CRC一致、50probe後stdinを開いたまま転送のみ停止、独立監視で
最後のsampleから109.56ms/転送停止から87.54msでfault、process終了353.39ms。
期待service exit1、supervisor exit0、全対象process/thread終了。10ms Python監視は物理停止/実時間保証でない。
CRC一致もモーター異常/支持/制御権/立位の確認ではない。

`body_io_adapter.hpp` / `unitree_body_transport.cpp/.hpp`を追加。
明示クエリー→1回だけの解除→mode確認→身体publisher、明示kdによるdamping候補、
外部の現場停止確認記録→publisher close→元mode復帰のSDK接続コード。
既定compile flag0は全I/O拒否。現行recordサービスは呼ばず、実機launcherも提供しない。
契約bool/停止確認文字列を実際の物理条件や排他的制御権の証拠にしない。
停止ラッチは書込み前、SDK Write成功でもphysical_stop_confirmed=false。
型式/P-R変更後のdamping/復帰は拒否。destructorの暗黙解除/停止/復帰、既定kdの勝手な選定なし。

`make body-io-build-check`最終結果は`artifacts/body-io-build/body-io-build-FT3T3p/outputs/`。
G1でflag0/1双方のSDK object compile成功。リンク/SDK構築/実行なし。
実行はSDK-free疑似transport18条件のみ。新規単体2、CRC2、monitor計11、service IPC7成功。
最終`make check-offline` exit0（既存IPC6件明示skip）。詳細[BODY_IO_ADAPTER.md](BODY_IO_ADAPTER.md)。

次の実装は実gateway（局所body/モーター状態・セッション/目標期限・初期姿勢・制御権）と
500Hz writer/独立停止要求の統合。SDK書込みの遅延/実時間性/物理停止は未検証。
保存SONICの範囲超過と実開始条件の適合性も未解決。通常G1Deployや実送信は引き続き禁止。
右PIKAを必要とする実機統合は再装着・実構成確認後。途中の継続確認を求めず送信なし実装を進める。

## SONIC履歴：G1ローカル記録サービスを実配置・読み取り検証

ユーザーへ用途を明示して起動を依頼し、「起動した」の通知後に実施。
galleria→G1の厳密SSH鍵照合に成功。G1 aarch64/Python3.10.12/numpy1.21.5、
libzmq.so.5/CycloneDDS0.10.2/gcc11.4.0を確認。pyzmq不在だがctypes実装のため追加install不要。
galleriaの有線src192.168.123.99→G1 192.0.2.11/enP8p1s0。実LowStateはmode_machine=5/mode_pr=0。

scripts/probe_local_body.pyで新規GPU artifact＋G1 /tmpフォルダだけへ配置。
同一ホストreceiver→stdin→local_body_service、GPU→G1はZMQ TCP6077/単一peer filter。
G1-local鮮度はGPUが更新できない。snapshotの年齢はSSH因果往復＋G1-local年齢で上界化し、
異なるホストのmonotonicを引かない。保存SONIC自体の生成時刻の鮮度とは別。
サービスのmessage上限を明示64KiBへ修正（実body＋SONIC配列は既定4KiBを超え得る）。

make body-local-checkの最終runはartifacts/local-body/local-body-nZZEwC。
既存固定実SONIC150出力を変更せず送り、全件gated_initial_pose_not_ready、受理0/抽象writer0/実機指令0。
147件のURDF超過もそのまま記録。実LowState164frame、最大間隔21.04ms、因果年齢上界最大24.41ms。
service/supervisor exit0、受信processは対象限定TERM(-15)、feeder/監視thread終了。
これより前の50件probe/150件試験の記録も保存。ライブSONIC再推論・実機追従の合格ではない。

make body-local-expiry-checkの最終runはlocal-body-IGY3In。
50件のprobe後、stdinを開いたまま実LowState転送のみ停止（receiverは排出を継続）。
独立watchdogが最後のsampleから101.31ms、転送停止から96.38msで異常を観測。
process終了は停止から353.36ms。期待するservice exit1、supervisor exit0、全対象終了。
検出とprocess終了を分けたjournalを保存。10ms Python監視の実時間保証/物理停止とは扱わない。

通常G1Deploy、LowCmd publisher、制御権変更、INIT、カメラ、シリアルを起動していない。
CRCは未確認のまま。停止ACKは記録セッション終了だけ。
残る実機出力/制御権/初期姿勢/物理停止adapterは従来どおり未完了。
続いてprobe_g1_lowcmd_abi.py/make lowcmd-abi-checkを実装・実行。
固定SDKのDDS traitを除いたデータクラスとCRCのみ、G1に一時compileして保存1540抽象出力を比較。
artifacts/lowcmd-abi/lowcmd-abi-J7oor9：1004bytes native memoryがx86_64/aarch64で全件完全一致、
SHA両方85c3ec8629d58d1b53ea4bbebff9ef94c2360b47d256d1169f344c180f0907dd、独立Python CRCも一致。
読み取り記録mode_machine=5を診断値に使用。binary exit0、SDK client/publisherなし。
LowCmd native ABIのみの検証で、DDS/CDR配送/firmware受理/LowState受信CRCの認定ではない。
check-offline一括exit0（IPC6件明示skip）、service --ipc7件、probe helper3件成功。
README/BODY_LIFECYCLE/Make/AGENTSへ反映。以前の「G1未配置」はこの追記より前の状態。
今後、必要な実機作業の前に用途付き稼働確認を行い、過去の起動/timeoutから現在状態を推測しない。

## SONIC履歴：動力学閉ループ・LeRobot接続、G1ローカル監視コア

scripts/sonic_mujoco.py/run_sonic_mujoco.py/sonic_sim_actor.pyを追加。
galleriaの既存MuJoCo3.3.4/IK環境・固定SONIC/TRTを再利用、新規job内だけでstdio推論。
G1接続、通常G1Deploy、DDS publisher、シリアル、実機動作指令なし。
自由基部・床接触・500Hz物理/50Hz SONIC、バンド/root reset/目標clippingなし。
実観測10件のPD warmupは0.2秒、raw actionは推論開始後に生出力を履歴へ戻す。
MuJoCo mjOBJ_BODYは慣性軸なので、角速度をmjOBJ_XBODYへ修正。4座標/時刻＋4actor試験成功。

保存RGB ACT＋実測sim TCP→IK→SONICの3秒run-kv4ikn7u、30秒run-_z1bvt9z成功。
30秒はACT900/SONIC1500・両worker exit0・モデル範囲外0・傾き0.0801rad・最低高さ0.7312m。
画像は保存1組を固定、幅0.04mは仮定。視覚閉ループ/グリッパ/実タスク/実時間の合格ではない。
SONIC単体5秒run-vb3420cg、PIKA10秒run-_y3gmgz2も立位。これらはXBODY修正前の暫定結果。
最終コード30秒再実行run-mkjlzx75も同結果で成功、ONNX/TRTキャッシュ前後SHA不変。

教師はabsolute TCP IK APIを既存TcpReferenceへ追加。従来candidate API/実測holdモードは保存。
SONIC既定腕基準ではIK範囲不足、旧教師中立腕を参照に採用（軌道縮小なし）。
毎回実測脚/左腕を目標化すると参照が流れるため、計画参照/実観測を分離。
run-pu1qxp7gは2秒連続参照遷移＋教師15秒750推論、教師完了・立位・範囲外0。
全期間TCP最大8.23cm（開始0.2秒時点）でpassed=falseを維持。
教師開始後の独立FK再計算では最大3.39cm、移動7.54cm。起動区間を除外して全体合格にはしていない。
以前のwarmup1秒転倒、実測holdのIK失敗、直接中立腕開始の4目標超過も全て保存。
make sonic-sim/sonic-pika-sim/sonic-teacher-sim/sonic-policy-sim/check-sonic-simを追加。
動画の中間frameでPIKA付きG1の立位・腕運動を目視確認。詳細SONIC_MUJOCO.md。

実機側の準備としてlocal_body_monitor.py/LocalSonicBodyBridgeを追加。
同一ホストLowStateの受信時刻/進むtick/有限値/mode_pr/mode_machineを独立監視。
GPUのbodyコピーでlocal watchdogを更新しない。重複tickは鮮度更新なし、異常はラッチ。
receive_state --streamへmode_pr/mode_machineを追加（読み取りのみ）。CRCは未確認のまま明記。
新規9単体試験成功、C receiverの固定SDKヘッダで構文検査成功。
G1へ配置/接続していない。続いてlocal_body_service.pyにstdin状態入力/ZMQ要求を分離した
記録専用processと独立10ms監視threadを実装。人工入力・local IPCの正常終了/独立期限切れを含む7試験成功。
peerにlocal_state/INIT/takeover/executeは提供せず、初期姿勢未確認で全目標gate。
Python監視は実時間保証・500Hz writer・物理停止ではない。G1/aarch64実配置/実入力検証は次工程。
起動前の古いpipe backlogのみdiscard、初観測以後の期限切れはラッチ。TCPは単一peer filter、認証未実装。
実送信/制御権/実初期姿勢/物理停止adapterは依然未完了。リモコン統合は対象外。
最終教師ログrun-fpygotrm：750推論/立位/範囲外0、全期間TCP8.23cmで未合格を再現。
teacher_replay_tracking_within_threshold=trueは再生区間3.39cm/0.1758radの診断だけで、overall passではない。
ONNX/TRT cache前後hash不変、worker exit0。teacher anchorは実機姿勢ではなく計画中立TCP。

既存・他作業の変更（PIKA単体制御追加など）は保持し、この作業では操作していない。
実機実装を省略しない、実機指令なしを維持。次の許可確認は具体的な実機試験条件が揃った段階のみ。
最終check-offline exit0（IPC既存4＋service2は明示skip）、service --ipcは7/7成功、
check-sonic-simは4＋4成功、git diff --check成功。
同日、galleria→G1 uname読み取り1回は22番接続timeout。搭載PCへの実配置はなし。
simの合格判定はBodyLifecycle実機受理条件の合格ではない。
simの起動目標変化最大0.3437radは既存body gate0.05radより大きく、実開始条件を未照合。
今回条件のPD warmup1秒失敗も、実機3秒PD INITの成立を仮定しない材料として残す。
次工程は起動過渡/開始条件と、身体送信・制御権・物理停止adapterの実装/統合。
G1読み取り許可を動作許可へ広げず、接続timeoutだけで実機の電源状態を断定しない。

## 最新コード: PIKAの対話CLI

ユーザー依頼でcontrol_pika_gripper.pyにinteractiveモードを追加。
open/close/move/cycle/current/status/params/set/kt/torque/enable/disable/stop/quit。
実行はinteractive --port /dev/ttyUSB0 --current-limit-a 0.2 --execute（0.2 Aは入力例）。
位置操作後は有効状態を維持し、入力から電流上限/次の目標を調整できる。
開始時はdisabled、最初の位置操作でenable。disableで入力へ戻り、quit/EOF/Ctrl+C/異常でcleanup。
Linux stdinを50ms pollし入力待ちも鮮度/状態を確認、物理停止の保証とは区別。
位置操作/cycle待機は同期で、途中停止はCtrl+C。stop入力は現在の操作完了後に処理。
入力エラーは無送信で継続、未到達/状態異常はcleanupして失敗。最新64moveのみ保持。
既定のpreview対話はserial import/openなし、状態は捏造しない。
固定ドライバ無変更、単発と共通の到達/disable確認関数を使用。
新規9＋既存13の22単体試験成功、送信なし実CLIの複数入力とPTY操作も成功。
make check-offline一括exit0（既存IPC4件skip）。実機指令なし。
詳細はPIKA_GRIPPER_CONTROL.md。身体/腕/SONICの出力経路は変更していない。

## 最新コード: PIKA単体開閉・電流上限（トルク調整）

同日続報: ユーザーがtigerにPIKAをUSB接続し、既定G1用パスが存在せず接続前に失敗。
ホストのudevadm/lsをポートを開かず確認。1a86:7522/ch341→ttyUSB0、ttyUSB50は同一symlink。
tigerのdialout所属とアクセス権あり。--port /dev/ttyUSB0付きコマンドを案内。
コードの--port help/欠落ポートメッセージと操作文書を修正。実機指令なし。

ユーザー依頼によりscripts/control_pika_gripper.pyを追加。open/close/cycle/limit、
--current-limit-a、確認済み実効定数必須の--torque-limit-nmを実装。
固定LeRobotドライバをassets/pika/gripperへ無変更移植、出典/Apacheライセンスを同梱。
既定は接続なしプレビュー、--execute時だけ実シリアル。今回の実機接続/指令はなし。
位置到達/状態鮮度、disable/disconnect、中断/失敗処理とJSON結果を用意。
EFFORT_CTRL=15の単位Aは既存ROS initSerialの/1000変換と照合。
上限のreadback/ACKはないため、送信済みを設定受理・物理トルク確認と混同しない。
実効トルク定数は未確認で既定値を作らず、過去9月18日の試験許可も再使用していない。
13単体試験と送信なしプレビュー成功、check-offlineへ追加、一括成功（既存IPC4件skip）。
詳しい操作・配置・検証範囲はPIKA_GRIPPER_CONTROL.md。
既存ACT/SONIC/body record-onlyの設定は変更せず、身体の実機出力は未提供のまま。

## 最新方針：MuJoCo統合検証を再導入、実機側実装も継続

ユーザーがMuJoCoによるLeRobot＋SONIC統合検証の案を採用。
工数短縮のために実機実装を省略する案は不採用。実機指令なしは継続。
SONIC単体の動力学閉ループ→PIKA/教師軌道→LeRobot接続と一括起動・動画/結果を順に作る。
実機側の起動/送信/停止/制御権adapterと共有手順も完成目標に残す。
6〜12時間はMuJoCo側の実装/初回検証の見積り。安定動作の保証や実機側総工数とは別。
保存画像ACT接続とsimulation画像の実タスク成功は区別し、後者は初回検証範囲外。
既存のMuJoCoコードはDecoupled WBC用で、旧balance policyをSONIC検証の代用にしない。
simulationと実機通信を隔離し、通常G1Deploy/実機DDS publisherを起動しない。
以降の過去の「シミュレーションなし」は、この最新指示より前の方針。

## 最新: SONIC出力と身体受信部を送信なしで接続

sonic_body_bridge.pyに既存q_target_hardware→BodyLifecycleの接続、RecordSession互換handler/clientを追加。
session/連番/身体tick/29関節順/有限値/PIKA幅/record-onlyを照合。
初期姿勢未確認なら目標をgate、ready後なら既存BodyLifecycle検査へ渡す。幅は別metadataで未駆動。
run_online_loopへ任意body_sink接続を追加し、SONIC計算後・commit前に受信decisionを記録。
通信時間も既存20ms期限に含め、sink異常・終了ACK失敗でも入力/GPUをcleanupする。
既存launcherへの配置は変更せず、sinkは既定無効。実機送信・通常G1Deploy起動はしていない。

接続7＋online追加4試験成功、online計20。一括check-offline成功（既存IPC4件明示skip）。
fake推論＋実handler/clientで50件の連続接続・全件gate・幅保持・終了を確認。
make body-boundary-check（ファイルのみ）/body-boundary-ipc（ローカルZMQだけ）を追加。
保存run-b5do1ocsの実SONIC/身体150組で両経路成功、decision SHA一致。
最新artifacts/body-boundary/run-i0jva6mw（ファイル）/run-unswp0me（IPC）。
全150姿勢未確認でgate、受理0、指令0。147件の範囲外（右ankle roll/waist roll）は未解決。
受信thread終了を確認し、protocol ACK後も身体phase=stop_required、物理停止を確認したとは扱わない。
初回IPC bindはsandbox PermissionError、限定したローカル試験のescalationで成功。権限恒久変更なし。

今回はGPU/G1接続・推論再実行・シミュレーション・実機指令なし。
BODY_LIFECYCLE/README/DEVELOPMENT_RUNBOOK/AGENTS/PROGRESSを更新。
接続部は記録診断用、引継ぎ/INIT APIや500Hz writerは起動しない。
残る実G1側では独立したLowState監視、送信/停止/制御権adapter、ネットワーク鮮度の保証が必要。
GPU転送の身体値・往復ACKをローカル身体監視/物理停止の代用にしない。
以下の過去の「オンライン接続していない」は、今回の任意接続点追加より前の状態。

## 以前（同日）: 身体ライフサイクルとLowCmdデータ専用検証を実装

継続指示に従い送信なし実装を進めた。追加承認待ちではない。
新規body_lifecycle.py/profile.py、record_body_lifecycle.py、LowCmd preview一式と診断configを追加。
引継ぎ要求/初期参照/姿勢条件の継続/目標受理/局所watchdog/停止要求/復帰要求を状態機械にした。
初期移行は既存JointTrajectoryの3秒5次多項式候補で上流の動的blendとは異なる。
初期時間終了だけでreadyにしない。身体/所有権ACK/目標の鮮度、順序、範囲/参照速度を検査。
停止要求はGPU/SSHやjoinを待たずラッチするが、物理停止は実装していない。
診断ACKは実機確認ではない。hardware_ready/output=false、true拒否を維持。

23状態機械＋3再生/改変検出＋3LowCmd試験成功、追加後のcheck-offline exit0（既存IPC4件は明示skip）。
make body-lifecycle-check / body-lifecycle-verify RUN=... / lowcmd-preview RUN=... を追加。
保存run-b5do1ocsの身体150件を変更せず使用し1540件の抽象出力を生成。
最新artifacts/body-lifecycle/run-6arb9pnq。診断時計3秒でsettling、3.08秒で入力期限切れ。
身体は未駆動で姿勢到達未確認なのでSONIC目標受理0。停止後の出力拒否とjournal完全再計算は成功。
固定Unitree SDKデータクラス/CRCのみを一時コンパイルしDDSリンク/登録は不使用。
最新artifacts/lowcmd-preview/run-uin1oocvで1540件のnative memory 1004bytes、
29motor・未使用6slot・padding/reserve・独立Python CRC一致。fixture mode_machine=0。
これはDDS/CDR通信形式でも実機受理試験でもなく、G1 aarch64 ABIも未検証。
コード/入力/出典/結果SHAは各reportに保存。試作段階の以前のrunも削除していない。

GPU新規推論・シミュレーション・実機指令なし。galleria経由のG1 uname読み取りを試みたが接続timeout。
最初の権限レビューは期限切れで実行されず、指示に従った一度の再試行が上記timeout。
G1へのファイル配置・プログラム起動はなし。現在のG1電源/支持状態を推測しない。
BODY_LIFECYCLE.md、README、DEVELOPMENT_RUNBOOK、SONIC_STARTUP_BOUNDARYを更新。

残る実装はG1側の実送信/物理停止/制御権adapterと統合。停止方式は未決定。
実機条件・停止実効性を確定せず勝手にdamping/holdを選ばない。
未解決のSONIC目標範囲・参照適用条件はこの実装で解消していない。
詳細と次工程は[BODY_LIFECYCLE.md](BODY_LIFECYCLE.md)。非実機作業でG1起動を求めない。

## 以前（同日）: 起動因子比較の分析・開始契約照合・診断整備を完了

ユーザーの「再開」により9月30日の保存結果から継続。今回GPU/G1接続・新規推論・実機指令なし。
詳細と再現は[起動診断](SONIC_STARTUP_ABLATION.md)。既存推論のGPU再実行は不要。
run-ofbwc_6t/startup-analysis-20261001.jsonに全8背景のチャネル切替ペアを集計。
q/gravityは初期の目標差への感度が大きく、dq/gyroはこの記録では0.003rad未満。
初期10周期を除いても48/48条件にURDF超過が残る。既定padding/参照/正規化/heading変更なし。

audit_startup_contract.py/sonic_startup_math_oracle.cppを追加。固定上流数学関数のみで
150endpoint/1500履歴Quaternion使用を照合。startup-contract-20261001-v2.jsonが最終監査。
生値/正規化のencoder姿勢float32差0、gravity差最大4.1723e-7、正規化Python/C++差0。
最初の保存base/refを仮heading起点としたdeltaは−0.000199814rad。
元のINIT/制御権/heading resetは未再現で、decoderへの差分再入力・物理応答は未検証。
最初のdefault姿勢差最大1.148424rad、全期間最大1.148460radは右wrist roll。
これを根因・必要な実機遷移・安全性として断定しない。

起動診断のschema/有限値/float32範囲/定数寸法/全基準/モデルキャッシュ整合検査を補強。
startup-ablation-verify（保存検証）/startup-contract-audit（保存監査）/
startup-ablation-run（GPUのみ新規推論）をMake/help/READMEへ追加。
起動因子11試験・開始契約4試験、追加後のmake check-offline成功（IPC4件は明示skip）。
保存48条件の検証は補強後も成功。check-runtimeや既存GPU試験の再実行なし。

次の境界: 初期姿勢・全身参照の適用条件と、制御権/遷移/停止の実機設計。
通常G1Deploy/INITを診断用に起動しない。送信なしの準備と実機動作許可を区別する。
以下の9月30日終了記録は履歴で、現在の承認待ち/作業停止ではない。

## 本日終了・再開地点（2026-09-30）

ユーザーの「今日は終了です」により作業を停止。承認待ちではなく明示的な終了。
直前のgalleria保存入力診断は終了・回収済みで、バックグラウンド推論を継続していない。
G1への接続・身体/腕/グリッパ動作指令なし。

新規 scripts/sonic_startup_ablation.py / run_startup_ablation.py / check_startup_ablation.py により、
q・dq・gyro・gravityの起動paddingを全16組合せで切り替え、既存3参照と交差比較。
3参照は記録IK終点保持・実姿勢保持・0.4秒の連続IK参照。
各150周期、48条件/7200推論。ローカル単体7件成功。
保存先: artifacts/sonic-startup-ablation/run-ofbwc_6t/。
outputs/report.json / integrity.jsonに結果・再検証を保存。
既存4基準（3参照＋記録IKの上流padding）のtoken/raw action/目標再現差は全て0、
目標変換式差0、同一参照のencoder tokenは16条件で一致。
worker exit0、コピーしたモデル/キャッシュの実行前後SHA一致、回収・保存再検証成功。
これは保存身体が計算actionへ反応しない因子比較で、物理安定性/実機合格ではない。

再開時はまず保存済みchannel_contrasts/conditionsを解釈する（GPU再実行は不要）。
次に生Quaternion・座標系・heading/CONTROL開始契約のソース照合を完了し、
診断文書・README・Makefile/check-offlineへの組込みを行う。これらは未完了。
今回の追加7試験は単独実行済みだが、追加後のcheck-offline一括実行は未実施。
prepare-only入力はrun-8sju8eoq/input.json、実推論はそれを--preparedで再使用。
初回prepareのC++定数読取りharnessに不足していた<vector>を追加してから再実行成功。
元ソース/モデルを修正せず、既定起動履歴や参照方式も変更していない。

## 最新受領: SONIC出力契約・起動履歴の独立診断

[独立診断の引き継ぎ](sonic_startup_diagnostic_handoff_20260930.md)を現行AGENTS/HANDOFFと併せて読了。
ローカル成果のresults-01/report.json・verification.json・ルートoracle-verification.jsonも読取り照合。
受領時の作業は検討方針/引き継ぎの文書更新のみ。続く実装/分析は冒頭の新しい記録を参照。

診断条件は固定low_latencyモデル、記録IK終点保持、mode0/heading=0、保存身体150周期。
現行の実身体10件から開始する条件と、上流Logger zeroEntryで起動履歴不足をpaddingする条件を比較。
現行150×29目標の元保存出力再現差0、目標式の関節順序/scale/default変換差0、encoder token差0。
起動履歴はdecoder出力を変えるが、paddingでもURDF超過は残る。
初期10周期の最大目標−保存実測差は現行1.252513rad、padding1.719764rad。
以後140周期でも右足首roll/腰rollの超過が残る。差は未送信目標と保存実測の比較で、追従誤差ではない。
実身体が計算actionへ反応しない再帰履歴の収束を、物理安定性として扱わない。

今後の優先検討:

1. 起動履歴のq/dq・gyro・ゼロQuaternion由来gravityをチャネル別に切り分ける。
2. 同じ起動2条件を、既存の実姿勢保持/IK終点保持/連続関節参照と交差比較する。
3. 保存生Quaternion・座標系・時刻・上流CONTROL開始時の観測/参照契約を照合する。

受領時点では検討方針のみ。その後の48条件診断と開始契約照合は冒頭を参照。
paddingだけを根因/修正解としない。
既存補間・極値監査・ACT bundle・30秒人工入力試験は完了済みとして維持。
独立診断は実機送信・低レベル停止・制御権移行の検証/承認を追加しない。
外部成果の所在・固定SHA・再現手順は上記文書へ集約。コード/モデル変更後は診断時点の結果として扱う。

## 最新実装: モデル一式の照合・診断起動・共有

config/policy-bundle.jsonにACT7ファイル、RGB前処理/幅codec/依存lock3ファイル、
入出力契約、LeRobot commit、データ/split出典hashを集約。モデル変更・再学習なし。
policy_bundle.pyのファイル専用照合をACT workerのready前に組込み。
全経路runnerはローカル/GPU双方を照合し、manifestを新規試験配置へ転送。
make bundle-check / bundle-exportを追加。配布は明示17ファイルのみ、データ/鍵/他ログなし。
14単体成功、check-offline成功（IPC4件は明示skip）。
galleria run-w2r_5_nuは保存画像2組の3worker exit0、回収成功。
run-ssy2zdrvは人工入力3秒93policy/150control、4worker exit0、保存整合成功。
さらにrun-ck4k0eu8で対応上限30秒903policy/1500control、4worker exit0、保存整合成功。
host間隔18.766〜21.324ms、20±2ms外0件。人工時刻/身体snapshot、実時間保証なし。
diagnostic-act-bundle-20260930.tar.gzを保存。詳細POLICY_BUNDLE.md。
G1には接続/送信していない。新規PC全自動setupや身体送信は依然未完成。
合格はファイル/記録経路だけで、SONIC目標差/URDF外・タスク品質・物理停止の解決ではない。

## 最新確認: 実演データと学習済みモデルは既存

ユーザーへTODOでデータ指定を求めた案内を訂正。データ準備は完了済みで、再依頼不要。
ローカル原本: /home/developer/workspaces/pika_ws2/datasets/data_2608261323_valid49_g1_zero_relative_h1_final_v3。
49episode/10881frame/30fps、manifest記載17ファイルのサイズ/hashを今回再照合し全一致。
GPUコピー: /home/gpu-user/g1-pika-training/datasets/valid49（9月14日検証済み、今回SSH照会なし）。
固定splitは39/5/5episode、幅h1不一致145frame除外後の採用数8693/1022/1021。
ローカルACTモデルartifacts/full-rgb-residual/run-xg1fn3b_/pretrained_model/model.safetensorsの存在確認。
学習/検証・保存再読込は実施済み。実タスク品質の最終合格と区別する。
taskメタデータはtask_index=0、task文字列null。具体的なタスク名称はこのメタデータからは不明。
データの所在をもう一度ユーザーに尋ねず、assets/datasetsとGPU_TRAINING.mdを先に確認する。

## 最新追加: 参照のフレーム間極値を監査

承認待ちではなく、ユーザーの継続指示に沿ってファイル専用検査を追加。
JointTrajectory.extrema/audit_joint_reference.pyで150予測窓の数値極値を評価。
参照のURDF角度/速度超過なし、加速度制限は未確認。厳密な区間保証ではない。
保存先run-b5do1ocs/continuous-reference-audit-20260930.json、再現JOINT_REFERENCE.md。
関節参照4・観測15試験成功。G1/GPU接続なし。SONIC出力の差は依然未解決。

## 最新追加: 時間整合した関節参照を実装・GPU検証

JointTrajectory（5次多項式）とMeasuredStreamの選択式補間、runnerの
--joint-interpolation-seconds、make trajectory-fixture-checkを追加。既定は終点保持を維持。
q/dq/ddqの連続性・解析微分3試験と観測15試験、make check-offline成功。
GPU人工入力3秒run-ddwfs4mc:93policy/150control、4worker終了、記録整合成功。
保存実身体の比較run-ptukt__r:計算完了。再帰条件の初回差0.621668rad、最大1.162244rad、URDF外3関節。
改善だけを合格としない。接地/力学/制限/姿勢quatの連続性は未解決。
詳細・再現・保存先はJOINT_REFERENCE.md。G1へ新規接続/指令は行っていない。
galleria推論の最初の承認レビューは期限切れ、許可された一度の再試行は通過・正常終了。

## 現在の要約（以下の過去記録に優先）

目標はUnitree G1＋AgileX PIKAをLeRobot＋GEAR-SONICで動作させる開発環境。
現状は実入力→ACT→TCP/IK→SONIC推論→保存の経路まで。実機出力・自律タスクは未完成。
galleriaがGPU処理、G1搭載PCがカメラ/PIKA/身体入力、tigerが編集/配置/記録回収。
PC間ZMQ、DDSはG1側の状態受信。低レベル送信は今後WBC側に集約する。
シミュレーションとリモコンソフトウェア統合は実施しない。

確かな最新実入力記録は9月24日のrun-b5do1ocs。
一時RR/1下で3秒、93policy/150control、186画像、全入力/worker正常終了。
9月30日にverify_online_record.pyを再実行し保存整合性成功。新規実機試験なし。
GPUの保存入力/人工入力試験は冒頭の最新実装を参照。
通常優先度の3秒失敗、計算目標差/URDF外、未実行action再帰の限界はTARGET_AUDIT.md参照。
上流観測関数の配列照合は合格。これで閉ループ安定性や参照の物理的成立が確定したわけではない。

未完了: 動的全身参照、G1側送信、実際の制御権引継ぎ/復帰、実機初期姿勢遷移、通信断/物理停止、
長時間入力安定性、実タスク性能、新規PCの再構築手順。現在hardware_ready=false。
送信なしの状態機械/初期参照/停止要求・LowCmdメモリ検証は冒頭の最新実装を参照。
通常G1Deployはconstructorでモード解除、INITで姿勢移行があるため起動しない。
実機送信の許可は得ていない。9月18日の右グリッパ単体試験許可は今回の全身動作へ拡張しない。

現場の最新申告（9月25日）: 吊り下げ、両足は地面から離れている。
停止方法は未回答。質問済みなのは停止操作・結果・通常/低レベル制御のどの条件で確認したか。
過去の足接地/約5秒dampingを検証済み現状にしない。9月30日G1稼働は未照会、GPU診断は上記で実施。
この情報不足は実機試験の設計に関係する。承認不要の実装・保存入力検証を止める理由にしない。

モデル交代時はルートのAGENTS.md→本repoのAGENTS.md→この要約を読む。
細かな区切りで継続了承を求めず、必要な判断/承認を具体化する。

以下は時点ごとの記録。複数の「最新」見出しは当時のもの。

## 最新: 観測配列の上流照合完了、現場条件を照会

check_sonic_upstream_history.pyの2テスト成功。上流関数を直接抽出したC++harnessと
Pythonのencoder/decoderを32組で比較。限定条件と未検証範囲はTARGET_AUDIT.md。
make check-offline / check-runtime（IPC許可環境）成功。
SONIC_STARTUP_BOUNDARY.mdを追加。通常G1Deployのconstructorで制御権変更があるため起動禁止。
ユーザーへ「現在の支持状態と確認済み停止手段」をasyncで質問済み。
これは実機動作の承認依頼ではなく、限定試験を設計するための欠落情報。
旧履歴の吊り下げ/5秒dampingを検証済みと仮定しない。動作送信ゼロを維持。

## 最新: 追加承認待ちなし、保存入力の目標監査

G1へSSH接続・稼働を確認済み（確認時uptime2:10）。試験プロセス終了、電源操作なし。
現在の診断はG1の給電不要。TARGET_AUDIT.md参照。
run-b5do1ocsにmotion-audit.jsonとablation-comparison.jsonを保存。
記録IK再生run-n4vkz49qは元150×29出力と完全一致。
実姿勢保持run-b0x8o3amでも再帰action履歴で最大1.179329rad差、URDF外5関節。
IKだけが原因とは言えず、未実行actionの再帰履歴は閉ループ検証ではない。
次は観測/参照の上流互換性と初期姿勢の適用条件の切り分け。実機送信なしで進められる。
make check-offline成功。通常G1Deployは引き続き起動禁止。

## 最優先: 一時優先度で3秒実入力試験成功、全プロセス終了済み

ユーザーが補助を起動し、RR/1をreceive_state 2プロセスへ適用した3秒試験が成功。
artifacts/full-record/run-b5do1ocs: 93policy/150control、実画像186枚、入力2+worker4すべてexit0、hash整合成功。
priority-report.jsonで今回の対象パスとの一致、PID9310/9374のRR/1適用・終了を確認。
補助も66.728秒で終了、恒久設定変更なし。身体間隔19.464〜20.948ms、参照生成年齢最大57.983ms。
通常優先度の3秒失敗と区別。短い一回の成功で原因確定/長期安定/実機運動の合格としない。
hardware_ready=false、指令ゼロ、物理停止・制御権・動的参照・実機追従は未検証。
補助は現在終了済み。再試験時は再起動・新しいoutput名が必要（上書き拒否）。自動sudoや恒久権限追加は未実施。
今回の結果の整理・保存は完了。過去の「sudo待ち」「3秒未達」は以下の履歴であり最新状態ではない。

## 最新: 一時優先度試験は了承済み、sudo認証だけユーザー操作待ち

「よい」で受信プロセスの一時優先度調整を了承。sudo -nはpassword requiredで、まだ変更していない。
G1配置済み: /tmp/g1-pika-priority-m4jFgz/temporary_receiver_priority.py。
ユーザー実行: sudo python3 -I 同script --allow-temporary-priority --output /tmp/g1-pika-priority-m4jFgz/priority-report.json
READY通知後、補助の残り90秒内で3秒実入力試験を起動する。起動済み確認前に通常優先度試験を繰り返さない。
補助は新規・unitree所有・厳格path/argv/binary SHA一致のreceive_state最大2つだけRR/1にする。
完了/90秒/INT/TERMで復元。永久権限追加やOS設定変更なし。rootの記録を回収し実際の優先度適用/復元を検証。
詳細SHAと条件はPROGRESS.md先頭。読み取り・一時優先度以外の動作指令は未許可。

## 最優先: 3秒の実入力安定性は未達、優先度変更は未承認

魚眼の30fps化と設定復元、1秒合格は下記のとおり。以後の3秒試験は不合格。
最新run-rqy0jijh: カメラ側実身体履歴23.177msを検出してsource停止、続いて参照鮮度超過。
固定周期サンプル計時を導入したが、実受信時刻のばらつきはまだある。閾値は広げていない。
新規画像到着に取得要求を同期、身体20件bufferから実連続窓を配信。ソフト単体は成功。
受信プロセスの一時的優先度調整が次の候補だが、sudoを伴うため了承前に行わない。
G1 schedutil/通常TS、ulimit -r=0を読み取り確認。全入力プロセス終了済み。動作指令ゼロ。
GPU人工入力3秒回帰run-a5n12vh1は93policy/150control、全worker正常終了・hash整合成功。
最新の成功と不合格を区別して伝えること。1秒成功だけでhardware_ready=trueにしない。

## 最新: 魚眼30fps化、1秒実入力統合が完走

露出/FPS一時変更はユーザー了承済みで比較し、元のauto=3/absolute=156/interval1/30へ復元確認済み。
artifacts/exposure-test-1、exposure-test-2。露出短縮はFPSに効かず、魚眼buffer1→4で15.012→29.962Hz。
受信スレッドで両カメラJPEG90を並行圧縮し、各4bufferから最新のみ保持。
元の受信時刻を維持し、実際に新しく受信年齢25ms以内のペアを最大100ms待つ。100ms総鮮度条件は維持。
ACTのJPEG展開/実画像と同じtensor配置、IKソルバを入力取得前にwarmup。合成初期化出力は破棄。
有限取得はpolicy秒数×30+3件（終了余裕）、control秒数×50件。既定1秒、最大30秒のまま。

run-zmw1z4fs: 実画像66枚/33policy/50control完走。2source+4worker exit0、残存なし。
記録hash整合成功、hardware_ready=false、動作指令ゼロ。host周期17.692〜23.179msで実時間保証なし。
3秒延長run-klyw3swfは初期37msのhost間隔で身体窓を飛ばして停止（詳細stderr保存）。
受信bufferを20実測件にし、次の実窓を順番に返す修正を追加。鮮度100ms/20±2ms/重なり検査は維持。
未保持/古い窓の穴埋めなし。ローカルIPC35試験成功。長時間・物理動作の成立は未検証。
シミュレーションなし、G1Deploy未起動、身体・腕・グリッパ動作指令は今回も未許可・未送信。

以下は以前の段階。最新の判断はこの節とPROGRESS.md冒頭を優先。

## 最新: 入力専用試験実施、魚眼は実測15Hz

G1起動通知→入力専用試験への「OK」を受領済み。読み取りの再承認は不要だった。
実機動作指令は未許可・未送信。最新実入力run-_kwxxgseは100ms参照鮮度条件で不合格。
G1入力プロセスは今回の一時フォルダに対象限定して終了・残存0確認済み。
推論/DDSなしのカメラ単独切り分けでも魚眼15.0098Hz、D40530.0061Hz。
artifacts/input-timing-20260924.json。カメラ設定照会はMJPG640x480/1/30秒、Auto Exposure=3。
設定値と実FPSが一致しない原因は未確定。撮影設定変更はしていない。
次は撮影設定を一時変更する30fps切り分けの了承が必要。動作指令とは別の境界。
実入力取得とACT/IKを並行化、鮮度の処理時間二重計上を修正、異常終了時の対象限定cleanupを追加。
閾値緩和/フレーム複製/保存入力へのfallbackはしていない。詳しい失敗経緯はPROGRESS.md冒頭。
追加online単体15件、ローカルIPC33件、GPU人工入力30/50回の回帰run-lcxa6t1zは成功。

以下は以前の段階の記録。最新の境界は上記を優先する。

## 以前: 実入力用の起動/記録コードまで実装、G1は未接続

G1入力は最後へ延期という指定を維持。新しい実機入力起動コードはまだ実行していない。
`make online-record DEVICE_READ_ACK=1`は将来の読み取り了承後だけ実行する。動作指令機能はない。
詳細docs/ONLINE_RECORD.md。GPUモデル準備→G1受信専用C/カメラ/右幅→ZMQ→4 worker→記録→全終了を実装。
設定config/development.json + config/online-record.json + assets/network/g1-runtime-access.json。
G1-PC間ZMQ、DDSはG1側rt/lowstate受信のみ。リモコン統合なし、シミュレーションなし。

検証済み:
- run-u1cqm5a6: 実入力用処理本体の人工入力30秒試験、ACT/IK900・SONIC1500、4 worker exit 0。
- run-x2w0eq6u: 保存実身体379窓の持続観測/SONICとバッチ関節出力差0、2 worker exit 0。
- 30秒試験の全画像hash・900 capture/1500 body記録の整合検査成功。
いずれもG1未接続。人工入力を実測同期データと誤認しない。実身体の物理応答未検証。

中間試験の記録heap増大でGC最大19msによる期限超過を検出。hash付き個別記録に変更し最大0.758ms。
成功試験でもhost実行間隔15.387〜25.157ms、20ms±2ms外れ2件。リアルタイム保証とはしない。
身体50Hz履歴の厳格検査と、host時計逆行/40ms停止検査を分離。前回の厳密一致失敗は回転丸め差8.95e-18。
詳細経緯と失敗artifactはPROGRESS.md。勝手な再接続/閾値緩和/実機出力有効化をしない。

次の実機依存工程は入力専用統合の確認。G1起動・読み取り了承（serial openでMCU resetの可能性）が必要。
G1利用不可の間はこの取得を要求しない。動作指令の承認と混同しない。
低レベル送信、動的全身参照、初期姿勢/衝突/停止・制御権移行はなお未完了。

以下は以前の段階の記録。現在の境界は上記を優先する。

最新追加: 保存snapshot反復の30秒周期試験に成功。artifacts/full-record/run-wi6j6n4x。
ACT/IK900回・SONIC1500回、3 worker exit 0。再現make rate-record-check RATE_SECONDS=30。
実機/物理応答なし。最大開始遅れ約0.982msは今回の観測値で実時間保証ではない。
子プロセスJSON応答の厳格検査/異常終了を追加し6試験成功。ローカルIPC19試験成功。
SSH期限超過でも失敗記録と時間制限付き結果回収。遠隔終了未確認を正常扱いしない。
現時点でユーザー承認要求はない。実機工程は延期のまま。

最優先: G1を起動できないので同時入力は最後の実機検証へ延期。非実機継続のため起動を求めない。
make full-record-checkを追加、GPUだけで保存RGB→ACT→本家IK→ZMQ IPC→実SONICが全経路成功。
artifacts/full-record/run-diyy8jud/outputs/report.json、remote sonic-full-LLf21i、3 worker exit 0。
ACT warmup3回、全経路2件約28.51/24.02ms。独立50Hz/実時間の保証はない。
ReferenceMailbox部品は6単体成功。make rate-record-checkで独立30Hz/50Hzも反復snapshot条件で完走。
最新周期試験artifacts/full-record/run-tlvk3izg、30/50回、全worker exit 0、最大開始遅れ0.225ms。
実センサーや動的身体追従の試験ではない。userは実機工程を最後へ延期しているので今G1起動を求めない。
設定config/development.json、IK環境は既存split-wbc-bHU7TOをソース改変なし再利用。
SONIC単独30要求run-q2yvxxlrはバッチと差0。IPC異常6条件、実SONIC異常3条件も成功。
開発/共有/終了手順はDEVELOPMENT_RUNBOOK.md。常駐サービスなし、G1接続/指令なし。
今後の未完了を隠さない: 実入力での周期処理/動的参照/初期姿勢・衝突/制御権移行・停止/実機送信。

最優先の最新成果: 保存画像2組のACT再推論→TCP→本家IK→SONICの送信なし接続が完走。
make sonic-tcp-check INPUT=...で保存action以降を再現できる。詳細SONIC_TCP_PIPELINE.md。
30件の運動学IKは位置最大0.009692m/姿勢0.009987rad。ただし実測肩rollは本家制限外のまま。
脚・腰実測固定の終点保持参照であり動的全身軌道ではない。hardware_ready=false。
artifact run-3jpk7nc3(30件)、run-7ol6w3ks(画像再推論2件、1コマンド再実行)。単体60件。
新archive-sonic-inputsで全画像＋実身体10フレームを同時保存するコードは実機未実行。
次はG1給電とカメラ/右serial読取り操作の了承後、その取得を実施。serial openはMCU resetの可能性。
このターンG1へ接続していない。過去の身体単独取得後はG1電源不要と通知済み。

最新: make sonic-replay STATE=...でGPU保存状態比較を1コマンド実行可能。
artifacts/sonic-replay/run-bxnd4ew3/report.json、GPU sonic-replay-fqkEVb。
過去actionゼロ/計算出力履歴の最大目標差0.608018/1.109443rad、各379窓。
これは開ループ診断で根本原因は未確定。PD目標差を追従誤差・不安定性と断定しない。
本家C++ quaternion関数を直接比較する512ケーステスト成功、全Gather同等性は未証明。
単体49件。G1未接続・指令なし。次は初期化/参照契約とLeRobot→有効全身参照の実装。

最優先の最新情報: G1起動後SSH成功、8秒の実LowState388件を回収済み。
G1受信処理終了を確認し、今回の取得に電源不要と通知。以後GPU/ローカルだけで作業可能。
artifacts/sonic-state/sonic-state-McdQQD/に生記録・取得report・history入力/出力。
実履歴379窓のSONIC連結推論完走、最大目標差0.608018rad。参照は実測固定、過去actionゼロ。
実機指令なし、hardware_ready=false。単体45件成功。次はGather*照合/初期目標差/有効参照。
下記の「SSH timeout」「高頻度記録不足」は過去経緯で、現在は解消済み。

最新: SONIC観測組立と本家TRTによるencoder→decoder連結を実装。
記録snapshot/未合格IK候補を各30件診断、有限出力。ただし履歴は合成、hardware_ready=false。
41単体成功。次は高頻度実状態と有効全身参照が必要。G1へのSSHはtimeout、GPUは接続可。
詳細SONIC_OBSERVATION.md。通常制御バイナリ/シミュレーションは起動していない。

最新の成果: SONIC C++ビルド成功、low_latencyモデルをrevision6733128で固定し
TensorRT合成入力単体推論成功（encoder64/decoder29有限出力）。実機制御は未起動。
詳細SONIC_BUILD.md。次は実観測履歴/参照生成を含む送信なし統合で、まだ完了ではない。

最新: galleria SSH復旧、CUDA12.8.93/TensorRT10.13.3.9/ORT C++1.16.3あり。
SONIC必要ソースの部分取得成功。sonic_reference.pyで公式packer再利用、関節順変換と
wire検査を実装。make check-offlineは36件成功。実機接続なし、モデル/ビルドは未完了。
次は残りビルドソースとcheckpointを固定して送信なし推論へ。詳細SONIC_MIGRATION.md。

## 2026-09-24の優先方針

目標はLeRobot＋GEAR-SONIC＋PIKA。シミュレーション/リモコン統合なし。
旧Decoupledの改善を先に完了させる工程へ戻らない。身体・グリッパ実機指令は禁止。
make doctor/check-offlineを追加し30件成功。既定makeはヘルプ。
READMEを更新、旧全文はdocs/README_LEGACY.mdへ保存。
SONIC候補は同じ固定上流のgear_sonic/gear_sonic_deploy。追加取得は長時間未完了で
中断（exit 130）。HEAD不変、バックグラウンド取得なし。必要なソースのみの取得を再検討。
既存ACT10Dは公式VLA78Dと非互換。関節参照v1候補の成立を調べる。
galleriaの192.168.1.27へSSHはNo route to host。GPU導入確認は未完了。
次は取得した固定ソースのprotocol/関節順/依存を確認、GPU復帰後に診断・ビルド。

## 最新の到達点

初期差の記録再生比較を追加。LeRobot目標なしでも腕の差は残る。
診断専用projected_measured seedでIK最大0.0257mまで縮小するが基準未達。
実機送信へ進める結果ではない。既定controllerは変更せず、下半身即時有効化と
腕IK初期化を別々に扱う必要がある。詳細WBC_STARTUP_REVIEW.md末尾。

ユーザー確認: G1は吊り下げで足が接地。リモコンあり、dampingまで約5秒という記憶は
未検証。支持なし立位という解釈は訂正。吊り具の荷重支持能力/停止実効性は未確認。
ユーザー指示でリモコンのソフトウェア統合は対象外。今回追加した生データ出力と
未実行テストfixtureは取り下げ済み、リモコンを実装に含めない。
本家KeyboardEStopはPCキーからプロセス終了、リモコン直結停止ではない。

2026-09-18訂正: 肩ロール例外は本家seedをこちらが実測値で上書きしたため。
実機姿勢変更を計算の前提とせず、ik_seed_mode=upstream_defaultで本家seedを維持して
実入力30件→WBC30出力までgalleriaで完走。ただしIK最大0.4105m/最終右0.0223m、
閾値0.02m未達でpassed=false。出力はファイルだけ。WBC_STARTUP_REVIEW.md参照。
本家起動はReleaseMode/LowCmd送信を伴い、終了は実機damping/モード復帰を保証しない。
次の実機段階には現在の支持状態と停止手段の確認が必要。身体・腕は未許可。

2026-09-18本実装: `make input-shadow`で画像＋q/dq/IMUgyro＋右グリッパをZMQ統合、
実エンコーダ由来の旧機構式幅でLeRobot推論30件成功（仮幅なし）。詳細REAL_INPUT_INTEGRATION.md。
実入力記録を既存WBCへ入れる送信なし再生も実行したが、実肩ロール左-0.0295/右+0.0438が
本家IK範囲左>=0.19/右<=-0.19外で初期化停止。WBC出力0件、未完了。
次は本家の初期姿勢移行・制御権手順の確認。制限緩和/実測値捏造/実機姿勢変更はしていない。
身体・腕は未許可。今回グリッパへのenable/disable/目標も送信なし。

追加許可で右0.6radまで段階開き・3秒保持・閉じを実行成功。頂点0.5923rad、
最終無効化/close確認済み。result-largerに保存。身体・腕・左は操作していない。

2026-09-18 右グリッパの小さな開閉テストをユーザーが許可し実行成功。
既存PikaGripper無変更、0.15rad→0radの1往復、実測0.126/0.0152rad。
disable確認・port close済み。記録RIGHT_GRIPPER_MOTION.md。
許可は右グリッパ単体テストのみ。G1身体・腕・左・ポリシー実機動作は禁止継続。
従前の「動作指令なし」はそれ以前の記録。今回は右へenable/目標/disableを送信した。

2026-09-18方針訂正: 独自保護を拡大せず既存PIKA/LeRobotを再利用。
調査済み: LeRobotは受信角度をそのまま保持、ROSは0〜1.67へクリップ/error付きで幅換算。
既存の角度→幅の機構式を発見。前回診断の厳格なpassed=falseは独自基準。
次は受信専用ライフサイクルと既存幅変換の最小接続を検討。詳細GRIPPER_REUSE_REVIEW.md。
以下の「次は独自保護」方針より本項を優先。

2026-09-18 右グリッパ受信まで実行済み。接続リセットはユーザー了承済み。
5秒JSON832件を受信したが、不正JSON1・角度2.0/電流-1080385602が2件。
passed=falseのまま記録。通常の最終角度-0.0067、24.7V、Status0x00。
シリアルはclose済み、アプリUART書込/動作指令なし。追加インストールなし。
詳細GRIPPER_STATE_RX.md。次は記録を使う異常入力拒否、幅較正とZMQ統合は未完了。
以下の安全確認待ち/open未実施という記述は過去の記録。

2026-09-18 状態取得準備: 既存ZMQ状態配信6101なし、Python serial未導入。
既存PikaGripper.connectはリセット、disconnectはdisable副作用ありで使用しない。
標準ライブラリ受信でもopen時信号変化の保証はできない。右グリッパの保持物なし・
周囲安全・リセット可能性の了承を確認待ち。シリアルポートはまだ開いていない。

2026-09-18 CH341復旧完了: ユーザーがsudo install.shを実行後、SSH読み取りで
2台ともch341へbind済みと確認。右/dev/pika/right/gripper→ttyUSB5、もう1台ttyUSB4。
両方unitree:dialout/0660、右にID_MM_DEVICE_IGNORE/ID_MM_PORT_IGNORE=1。
unitreeの右ポートread/write権限も確認（openはしていない）。再起動後は未検証。
次は既存connectのリセット/disable副作用を避けたグリッパ状態取得経路の検討。
以下のインストール待ち・ドライバなし記述は過去の記録。

2026-09-18 CH341: G1用ドライバのビルドまで完了、sudoインストール待ち。
G1端末で `sudo sh /home/unitree/g1-pika-ch341-xaK9Y1/ch341/install.sh`。
グリッパ周囲を安全にしてから実行（bind時のUART初期化/リセット可能性あり）。
詳細assets/drivers/ch341/README.md。未ロード、シリアル未open。

2026-09-18受信経路復旧完了: `make state-shadow`（wired-shadowも同じ入口）。
G1の5秒状態受信4,619件、右2視点＋状態30組→有線ZMQ→galleria LeRobot推論30件、
正常終了とtigerへの記録回収まで成功。通信込みp95 34.116ms。実機指令なし。
詳細はSTATE_SHADOW_RESTORE.md。設定ファイルは新ランナーから使用するよう更新済み。
DECXIN2台はUSBハブpeer照合で右を選択。左D405は未検出。
PIKA USB Serial 1a86:7522は2台見えるがドライバなし。G1のch341復旧を別途ユーザーが担当予定。
適合版は5.15.148-tegra/aarch64・7522対応必須、kernel headersは既存。シリアルは開いていない。
以下は以前の時点の記録。

2026-09-18最新: ユーザーのssh-copy-id後、tiger→galleria→G1の鍵認証に成功。
G1はunitree-g1-nx / Ubuntu22.04.5 / aarch64 / Python3.10.12。
有線IFは旧eth0ではなくenP8p1s0（192.0.2.11）。
右D405 serialEXAMPLE_DEVICE_SERIALとDECXIN魚眼を列挙で確認。画像取得はまだ行っていない。
serial/by-idにはFTDI4ポートのみで、旧PIKA USB Serialはこの一覧では確認できなかった。
既存libddsc/libddscxxは/usr/local/lib、libzmqあり。gccあり、idlcはPATH上では未検出。
旧ROS/DDSインストール先は存在せず、旧ランナーをそのまま起動しない。
接続台帳: assets/network/g1-runtime-access.json（旧ランナーへの設定反映は未実施）。
次は新環境に合わせた受信専用経路の復旧。実機指令・カメラ起動・サービス変更なし。

2026-09-18 galleria→G1確認: tiger→galleria専用鍵SSHは成功。
galleria enp2s0=192.168.123.99からG1 192.168.123.164へ有線経路を確認、ping2/2成功・平均0.193ms。
実機ローカルで照合済みの新ホスト鍵をgalleriaの新規ファイル
`/home/gpu-user/g1-pika-training/artifacts/g1-access-lw4t5m/known_hosts` へ配置。
galleriaの `/home/gpu-user/.ssh/EXAMPLE_RUNTIME_KEY` によるG1認証はPermission denied。
次は **galleriaの端末** から対応する.pubをssh-copy-idで登録する。G1のパスワード入力はユーザー自身。
今後の呼称はgalleria=開発/本番GPU PC、tiger=作業用ノート、G1搭載PC=unitree-g1-nx。
旧ホスト鍵ファイルやネットワーク設定は変更せず、実機動作指令も送っていない。

2026-09-18追記: SSD換装との申告後、ユーザーがG1ローカル端末でED25519指紋
`SHA256:PUBLIC_EXAMPLE_NOT_VERIFIED` を確認。
ssh-keyscanで取得した公開鍵のSHA256が一致したため、assets/network/g1_known_hostsを更新。
旧鍵は同ディレクトリのg1_known_hosts_before_ssd_20260918へ保存。グローバルknown_hostsは未変更。
StrictHostKeyChecking=yesでホスト照合は通過したが、専用クライアント鍵では認証失敗。
次は開発PCからssh-copy-idで専用公開鍵を登録する（パスワード入力はユーザー自身）。
GPU側の旧ホスト鍵ファイル/認証設定はまだ更新していない。実機指令なし。

2026-09-18: ユーザーがG1と開発PCを有線接続。eno1=192.0.2.10/24から
192.168.123.164へping2/2成功、平均0.133ms。SSHは保存済みホスト鍵との不一致で停止。
提示されたED25519指紋は `SHA256:PUBLIC_EXAMPLE_NOT_VERIFIED`。
この鍵は未検証。既存known_hostsを変更せず、機体/搭載PCの変更有無をユーザーへ確認する。
認証・機器列挙には到達していない。動作指令・カメラ起動・設定変更なし。

進め方の訂正: 開発PC↔GPU PCの有線性能比較を前提条件にしない。
ユーザーは最短の本番実装を希望。本番GPU PC↔G1経路と、G1入力変換・停止系を優先し、
開発用通信の改善を深追いしない。以下の有線比較予定は過去の方針である。

最新の非同期版は `make async-runtime`。画像と身体の別worker、GPU内ZMQ PUB/SUB、
wall-clockに追従するMuJoCoを実装。GPU内loopbackは206推論/60秒・単体45件・
異常4ケースに合格。**2 PCの現Wi-Fi経路は100ms鮮度期限超過で未合格**。
期限は緩めていない。次はPC間有線で同条件比較（G1不要）。
詳細・成功と失敗の両記録: [ASYNC_SPLIT_RUNTIME.md](ASYNC_SPLIT_RUNTIME.md)。

最新の配置は `make split-runtime`。GPU PCのCUDA ACTとCPU WBCへ責務を集約し、
このPCは模擬G1/MuJoCo物理計算と指令の検査・適用だけを担当する。
画像/状態→ZMQ→ACT/WBC→ZMQ→MuJoCo。詳細 [SPLIT_RUNTIME.md](SPLIT_RUNTIME.md)。
lockstepのため実時間制御ではない。実機指令禁止は維持。

G1を使わない2 PC統合を追加: `make mock-runtime`。
模擬G1（記録画像/state＋MuJoCo身体状態）→ZMQ→GPU LeRobot推論→
このPCのWBC→出力検査→MuJoCo。一括起動・異常試験・終了・記録まで実装。
詳細 [MOCK_RUNTIME.md](MOCK_RUNTIME.md)。本番G1との接続確認は後回しというユーザー指示に従う。
実機指令禁止を維持。現在ACTは記録画像/state、WBCはシミュレーション状態を使用し、
画像閉ループ・実測幅・実機用状態変換・停止系は未完成。

2026-09-15: WBC関節目標の検査・faultラッチ・記録専用境界をMuJoCoへ接続。
一括検証は `make check-guarded-wbc`、表示は `make guarded-wbc-view`。
詳細と実機に適用できない範囲は [CONTROL_GUARD.md](CONTROL_GUARD.md)。
本番の低レベル送信・停止系が完成したわけではない。実機指令禁止を維持。
PC間ZMQとLeRobot学習/推論の方針は継続。以下は過去の到達点を含む履歴。

2026-09-14: ZMQ_STATE_SHADOW.md。G1のDDS受信専用Cプログラムでq/dq/IMUを受け、
画像と共に有線ZMQでGPUへ送る30組の診断に成功。SSHは起動管理のみへ分離。
実測幅・実機用WBC・停止系は未完了。診断成功を実機制御完成と扱わない。

有線直通版 `make wired-shadow` も実行成功。G1 eth0 192.168.123.164と
galleria enp2s0 192.168.123.99間で画像30組を直接転送・GPU推論・記録。
開発PCの画像中継なし。通信込みp95 33.817ms（5組/秒の診断）。
幅の実測・G1状態同期は未完了、実機指令なし。wired-live-2026-09-14.json参照。

最新は `make live-shadow`。G1で連続取得した右2視点30組をgalleriaでGPU推論し記録、
プロセス終了まで一括実行成功。幅は仮値4cm、実機送信なし。
詳細・結果パスはLIVE_SHADOW.md。有線未接続のため現時点はWi-Fi/開発PC中継。
既存グリッパドライバは接続リセット/切断disableの副作用があるため実測受信に未使用。

G1搭載PCで回収した右PIKA実画像2視点をgalleriaへ転送し、GPU ACT推論にも成功。
幅は仮値4cmの診断のみ、出力記録だけで実機送信なし。詳細はG1_IMAGE_INFERENCE.md。
本番の有線連続画像転送・実測グリッパ幅・G1状態受信は未接続。

`make end-to-end` で単体15件・実推論206/206フレームの60秒シミュレーション・応答断試験を
一括実行し、すべて期待結果に一致。記録: docs/end-to-end-2026-09-14.json。
実機タスクは未完成。開発PCの細かな試験追加は区切り、本番環境へ進むための残作業を
[END_TO_END.md](END_TO_END.md) に集約した。実機指令禁止は維持。

非同期pipe経路を追加。最新の起動は `make policy-async-view`。
推論中もWBCを継続し、要求期限切れで目標保持するシミュレーション専用実装。
詳細は [ASYNC_POLICY.md](ASYNC_POLICY.md)。USB左右識別の実装は本番PC接続時へ延期。

記録RGB/state → 固定LeRobot ACT実推論 → TCP目標 → Decoupled WBC → MuJoCoの接続に成功。
90指令・12秒の立位検査と異常応答時の目標保持を確認した。
起動は `make policy-view`。詳細・制限は [POLICY_SIM.md](POLICY_SIM.md)。
学習指標の追い込みを接続試験の前提にしない方針へ変更。実機への動作指令は禁止を維持。
カメラ閉ループ・実時間制御・実機採用は未達。次は指令なしの実機入力確認と実時間経路の準備。
PIKAカメラ接続後、DECXIN魚眼とRealSense D405カラーの画像取得に成功。
`make input-check` は列挙のみ、`make camera-check` は短時間撮影してPNGを保存。
有線eno1は直近列挙でDOWN。G1状態受信・動作指令は未実施。
撮影結果: artifacts/camera-check/run-4plz79uh/。学習時との画角・前処理一致は未検証。

## 目的

Unitree G1にAgileX PIKAを装着し、人間がPIKAで収集したデータで学習したポリシーにより、自立した状態でタスクを自律実行する。

## ユーザーからの既存実装の確認事項

現在はG1を吊り下げ、右腕制御を試験中。既存コードは変更せず保存し、新規実装に必要な部品だけ移植する。

- 既存実装: https://github.com/kufusha/pika_ros/tree/feature/g1-pika-retarget-package
- 指定LeRobot: https://github.com/taigasasaki6331/lerobot 、基準コミット `79edf6a9`。
- actionは相対位置3＋回転6D＋グリッパの10次元。
- PIKA付きURDF、TCP軸変換、グリッパ通信が再利用候補。
- 現行実機経路は `rt/lowcmd` を使用し、立位バランス制御はない。
- 現行MuJoCo動画は運動学的確認であり、動力学的な立位検証ではない。

これらは引き継ぎ情報。ソースで再確認した項目は進捗・調査記録に分けて残す。

## 新規実装の責務と順序

LeRobot（学習・推論）→ action/TCP変換 → WBC（上半身IK・下半身制御）→ シミュレータ。
将来の低レベル送信もWBC側へ集約し、LeRobotから並行して送信しない。

1. 素のG1でDecoupled WBC単体の動力学シミュレーション。
2. PIKAの質量・慣性・接触形状・TCPを含むモデルで検証。
3. 座標系・単位・時間間隔を定義した教師軌道の追従。
4. 10次元actionを出力するポリシーを接続。

実機への動作指令はまだ送らない。立位が確認できた場合も実機利用の承認とは扱わない。

## 初回PC確認

Ubuntu 22.04.5 LTS / kernel 6.8.0-138-generic / x86_64。
Intel Core i5-10310U（4コア8スレッド）、RAM約32GiB、空きディスク約150GiB。
PCI GPUはIntel UHD Graphicsのみ。`nvidia-smi`なし。CUDAディレクトリの存在はGPU利用可能の根拠にしない。
Git 2.34.1、Git LFS 3.0.2、Python 3.10.12、Docker 29.7.2、Compose v5.5.0。
Docker daemonへの接続はサンドボックス外で成功。ランタイムはrunc系のみ。
ROS_DISTRO=humble。snap版uvはサンドボックス内では起動に失敗。

ワークスペース直下には保護された空の `.git` があり、有効なGitリポジトリではなかった。
そのため新規リポジトリを `/home/developer/workspaces/g1_pika_ws/g1-pika` に作成する。
