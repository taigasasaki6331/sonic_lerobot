# 進捗

## 2026-10-02 公開許可を受領、既存方式を保存してPIKAソースを移植

利用者が公開のままでの送信を了承。既存remoteのπ0/π0.5・48次元・PIKAなし実装を確認し、
今回のACT/10次元/PIKAをg1-pika/へ分離。root READMEの入口/AGENTS/Makeだけ追加し、既存src等は維持。
public exportは内部IP/ローカル配置/SSHキー名/機器識別子を例へ置換。秘密情報/資産は原本に保存。
URDFはmesh filenameだけ相対化、原本SHA/派生SHAを区別。モデル質量/関節/慣性は変更しない。
State.c/hの生成Sourceコメント匿名化で初回CRC試験がmanifest不一致停止。
コメントのみの差分を確認し、公開コピーのSHA記録を更新、public2で128成功/IPC2skip。
Gitの行末正規化が固定source SHAを壊さないよう、公開コピーのgitattributesでtext変換を無効化。
main/元ローカルworktreeのGit状態/固定上流/ログは保持。GPU/G1アクセス・実機動作なし。
公開ブランチ参照/実際の送信完了はGitHubのrefで確認し、Cloud環境作成とは区別する。

## 2026-10-02 指定GitHubに新ブランチ作成、公開設定の確認待ち

利用者指定taigasasaki6331/sonic_lerobotへGitHub接続の読み取りでpush権限/公開設定/mainを確認。
新規codex/cloud-handoff-20261002をmain68c7294475646f3bdb373594c806d7f1b95b9e86から作成し、refを照合。
既存main/README/src/tests/docs/patches/.githubの内容変更なし。galleria/G1接続なし。
非公開前提に対し実際はpublicなので、ソース/内部設定/履歴のアップロードは確認前に行わない。
クラウド環境は未作成。今後の移植では既存リポジトリ構成を保存して衝突を解決する。

## 2026-10-02 クラウド継続用のソースとCPU検証環境を準備

ユーザーはgalleriaのネットワークから離れ、G1起動不可。GPU/G1/デバイスへの接続なし。
OpenAI公式Cloud環境作成手順を確認し、GitHub選択/環境Publishを伴う別環境として整理。
cloud-exportは現行未コミットソースも別ディレクトリへコピーし、元Git/資産を保存。
1118ファイル/約9.1MBのソース、固定vendor部分/ライセンス、単一URDF、SHA manifest。
raw dataset/重み/鍵/known_hosts/映像/ログ/バイナリ/既存venv/Git履歴は収録しない。
vendorは完全checkoutではなくテスト用の部分コピー。LeRobot本体/推論依存/重みは別途必要。
README/AGENTS/HANDOFF/TODO/CLOUD_HANDOFFを更新し、クラウド開始指示と実機許可境界を保存。

初回exportのscannerはSDKヘッダ中のPEM書式説明をcredentialと誤検出してコピー前に拒否。
実データを伴う鍵パターンの判定へ修正。初回CPU試験はLeRobot LICENSE不足で失敗、
出典ライセンスを追加したsnapshot-20261002-check2で全18スクリプト成功。
既存Pythonを借りた検査後、専用.venv-cloudを新規作成、numpy==1.26.4のみ導入して再確認。
初回pipはsandbox DNS制限で失敗、許可されたネットワーク取得後にsetup/check成功。
128試験成功、IPC2件は明示skip。実SDKは構文検査のみ、native writerは疑似transport。
同じ独立venvでruntime --mode build成功、artifacts/body-runtime/run-31aw2i2p。
物理実行/IPC通し試験/Cloud VM/G1 aarch64性能の確認として扱わない。
validation-20261002.jsonへ結果を保存。最終ready snapshotには検証生成物を再収録しない。
GitHub送信先は未設定のまま、アップロード・クラウド環境作成は未実施。

## 2026-10-02 G1 record runtimeの統一起動、LeRobot/SONIC実入力runnerに接続

利用者の「細かなパーツではなく動かす施策を優先」に合わせ、runtimeの縦の経路を接続。
local_body_runtime＋native body_runtime：厳密な同一ホスト状態、3秒初期参照/姿勢整定、
既存SONIC envelope、native mailbox/owner loop、固定LowCmdデータ/CRC、停止候補まで一括。
SDK-free memory backendに固定、真のtrial contractへ人工ACKを昇格させない。
参照を再生成しても元SONIC source ageを保持。初回参照/変化/速度/期限/identity-lossのgateを維持。
同じtickのCRC-verified identity changeもnativeへ先に通知、重複正常tickの鮮度更新はしない。
receive_stateにraw motorstate/mode35項目を追加、record criterionゼロbitはfirmware健康判定ではない。

make body-runtime最終run-0ztzrug5：5.076秒、229目標/68受理/161保留、native通常2390＋停止候補1。
owner/入力thread終了、service exit0、最後のnative1004byte CRCが独立Pythonと一致。
最大開始gap8.4565ms、memory write最大0.2299ms。実SDK性能/500Hz実時間の認定でない。
expiry最終run-af7qw18j：人工peer通信とstdinを継続、局所身体入力のみ停止。
native writer_body_crc_health_or_age_invalidでラッチ、通常1915＋停止候補1、owner終了、期待exit1。
目標184/受理24/保留160、停止候補もmemoryのみ。物理停止はfalseのまま。

初回compile警告（破棄後object storage読取り）を生存中memcpyへ修正。
人工feeder最新tickが局所pipe処理前にpeerへ渡るraceを修正、future-tick gateは緩めていない。
初回応答期限失敗、sandbox IPC拒否、身体/目標を同時停止した旧expiry失敗も保存。
最終通常/期限切れ成功を可用性保証や過去失敗の隠蔽にしない。
serviceのSIGUSR1 thread dump、BLAS1thread設定を追加。自動再arm/ゲイン/期限閾値変更なし。

source/profile/manifestのportable packageとlaunch_body_runtime追加。
packageをSHA照合して実行ホストでcompile、--build-onlyのx86確認成功：
/tmp/g1-pika-body-runtime-7__6kwm0（初版）、最終packageの再確認は/tmp/g1-pika-body-runtime-tprmrnt3。
最終manifest SHA98aea9c9112039d1b1ac4e432ee363411f83b41ad2ee4b4d42d75159d8677612、
library SHA87b89852b5d3263bc04292a50047f9ab2c90d76c3c83fb9ad91ff301b5865838。最新aarch64は今回未実施。
既存online-recordにBODY_RUNTIME=1 ONLINE_SECONDS=5を追加、既存configは上書きしない。
GPUからG1へpackage配置/現地compile/局所CRC受信/既存ACT-IK-SONIC sink/終了/journal回収を接続。
実入力版はコード/構文/Make dry-runのみ。G1停止/右PIKA取り外し中、今回G1/GPU接続/機器I/Oなし。
実SDK送信・ownership/INIT/復帰/物理停止は未完了。右PIKA単体の他会話資産/許可を変更しない。

最終check-offline exit0（IPC6skip）、既存service IPC7成功、online loop20成功、
py_compile/diff check/Make dry-run成功。新個別テスト数を主成果にせず、起動/終了の通し結果を保存。
README/AGENTS/HANDOFF/IMPLEMENTATION_TODO/BODY_WRITERを更新。

## 2026-10-02 PIKA続報: 保持解除を誘発した数値破損を破棄、保持中の目標再送・再設定を廃止

利用者のfault-p_9teqe2原本を保持しanalysis.jsonを追加。
約0.0904 rad/−1500 mAで保持→Position2.0/Current−1082348536→10.23ms後disable→
36.41ms後から開き、最終0.4363 rad。受信破損をきっかけとした保持解除と整合する。
ホスト受信時刻の証拠で、旧正常電流/範囲外Positionの実急動作まで同じ根因と断定しない。

control_pika_gripper.py：grip目標0到達後の反復送信を終え、繰返しgrip Aは電流だけ変更。
閉じ切れない実測角度へ目標を戻す処理を廃止。interactive phaseのconnect固定も修正。
|Current|>=1,000,000 mAは破損フレームとして全体を破棄、状態/鮮度を更新しない。
1000 Aはモーター定格/許容電流ではなく桁破綻の検出用。角度範囲/250ms/ドライバ異常bitは維持。
範囲外Position1.7857/Current−340は引き続きラッチ停止。破損が続く場合も期限で停止。
rx.corrupt_frames/最大8生フレーム/telemetry_numeric_integrity_okを報告へ追加。

実機許可継続下のinteractive session-_2qc97o7：92.46秒、閉目標保持73.29秒。
grip0.2→1.0→0.5→1.0→1.5→1.8 A、保持中の位置送信0、整定後0.00009〜0.0012 rad。
同種数値破損1件（Position−2.0/Current−1080989582）を破棄、前後角度0.0009〜0.0011 rad。
異常受信直後にdisableせず、17.76秒後のquitで無効化・切断確認。追加録画/身体指令なし。
正常15201/拒否28（数値破損1）/再同期41、操作終了passed=true/数値受信品質false。
events/raw/report/analysisを保存。受信破損の発生自体は未解消、空動作で全電流出力/力は未確認。
単体51件42.104秒成功後、操作成功と受信品質の分離の回帰を追加し、最終52件43.801秒成功。
終了後のfuserに可視所有者なし、対象ファイルの末尾空白/追跡ファイルdiff check成功。
固定driver SHAは維持、公式UART形式変更なし。許可範囲はtiger単体PIKAのみ。

## 2026-10-02 動く統合経路を優先、make runでnative身体コマンド経由の30秒動作

ユーザーが、部品の詳細マイルストーンは後で割り振り、今は動かせる施策を優先と指示。
検査部品の追加ではなく、LeRobot→IK→SONIC→身体アダプター→MuJoCoの縦の動作経路を実装。
G1は停止の申告のまま。galleriaへのuname読み取りで稼働を確認して新規隔離配置のみを使用。
G1接続、実SDKclient/publisher/ReleaseMode、実機動作指令、機器I/Oはなし。

sim_body_gateway.cpp/.py：既存BodyIoAdapter/WriterKernelへsimulation-only transportを接続。
固定SDKのLowCmdデータクラス/CRCだけをリンクし、出力したnative float32 motor fieldsから
MuJoCoの500Hz物理トルクを計算する。SDK DDS traits/client/networkはリンクしない。
simulation-controllerの起動/解除→出力→停止候補→復帰を同じ動作経路で実行。
人工CRC/health/ownership/停止確認を実機事実として扱わず、メタデータへscopeを明記。
実機WriterMailboxの0.05rad/速度gateや既存設定は変更していない。
低レベルメモリ検査のデータクラス抽出をexport_data_headersへ共通化し、SHA/ライセンスを保持。
run_sonic_mujoco.pyにnative-body option、sonic_mujoco.pyに出力経路選択を追加。
旧直接PDモードは残す。Makeの統一起動口make run（既定30秒/動画）、RUN_SECONDS=3も用意。

3秒初回artifacts/sonic-mujoco/run-7yfd38m5：ACT90/SONIC150/native1600tick、完走/立位/範囲外0。
最終make runはrun-u9gljra3：ACT900/SONIC1500/native15100tick（0.2秒warmup込み）、
native memory出力15101件（最後の停止候補1件含む）、simulation解除/復帰各1。
最低高さ0.7312495m/傾き最大0.0800971rad/水平移動最大0.0192886m、目標/実測範囲超過0。
右TCP移動最大0.2808048mは起動整定も含む。1秒後以降の右腕関節変化幅最大0.3256742rad。
動作計算wall24.22秒、実時間保証なし。ACT/SONIC exit0、動画755frame/ffmpeg exit0。
ONNX/TRT前後SHA不変、plant/config/既存artifact上書きなし。
native stream SHA017084ebe8ac1ae2a49eb9cce7485864696d05f82e312e13e1b2e27a5fbc9b42。
body-runtime.jsonへpacket samplesも保存、report.jsonの表示はsamplesを除き冗長なhex出力を抑制。
動画中間frameと保存関節値で立位/腕運動を確認。保存RGB1組・幅仮定・固定gripper、
視覚タスク/把持/実G1起動・停止成功の認定ではない。
起動目標変化0.3436623rad/physical_step_gate_passed=falseを保存したまま。

必要なsmokeチェックのみ実施：native gateway2、既存LowCmd3、sim座標/ACT4＋4成功、diff check成功。
初回文書patchは不正contextで適用されず、正しいcontextで再適用。ソースの検証閾値緩和なし。
README先頭に動作入口/最終動画を追加。AGENTS/HANDOFF/TODOへ最新の統合優先方針と成果を記録。
次の優先は、実LowState/SDK backendをつなぐG1 runtimeと初期姿勢/停止経路の統合。
今回sim経路は実機用gateway完成ではなく、G1実機指令の承認を求める段階にはまだ入っていない。

## 2026-10-02 G1停止中、native writerを実装・TODO/判明課題を整理

ユーザーが日をまたいで再開、G1はシャットダウン中と通知。
最新の置換ワークスペース指示を読み、MuJoCo＋LeRobot/SONIC統合を許可する現行方針へ
AGENTS/HANDOFFを修正。実機動作指令なしは維持。今回G1/GPU接続・sim・機器I/Oなし。
既存dirty worktree/PIKA別作業/ログ/モデル/データを保存、追加install/OS変更なし。

body_writer.hpp：SDKなしnative 2ms設計の単一owner loop、最新値mailbox、独立停止要求を追加。
入力置換前のsession/sequence/時刻/元入力年齢/有限値/float32/モデル範囲/参照速度・変化を検査。
身体CRC/P-R/machine/進むtick/局所100ms鮮度とmotor診断、局所phaseの明示入力を要求する。
不正後に正常を送ってもfaultが消えず、重複tickは鮮度を更新しない。
10ms超のwriter gap/write遅延、write false/例外、身体/目標期限切れでstopをラッチし、
GPU/RPC/worker joinを先に待たず停止候補を要求する。missed周期のcatch-up burstはなし。
BodyIoAdapterに局所identity lossラッチを追加し、型式/P-R変更後の旧型式damping/復帰を禁止。
最初の参照適合/INIT/ownership/支持条件は未接続の実gateway責務で、診断ACKから作らない。
既存receiver/serviceはnative motor-health/局所phaseをまだ供給しない。実機出力へ接続なし。

check_body_writer.cpp/.pyとrun_body_writer_check.pyを追加、Make入口body-writer-check。
24条件成功、疑似時計150参照/1500周期と実thread5ケースを検査。
make body-writer-checkの保存先artifacts/body-writer/run-l9olmfsq/report.json。
短時間更新threadは39回/最大開始間隔2.118ms、25ms疑似write後はfaultで通常出力を再開しない。
sinkが停止確認trueを返してもloopのphysical_stop_confirmedはfalse。
2msは設計値、通常Linuxでの実時間保証/実SDKの周期・停止性能ではない。
初回C++ fixtureのmisleading-indentation警告を修正し、Werrorを維持して再検査。
Address/UndefinedBehavior sanitizerの24条件も成功。
初回LeakSanitizerはptrace環境で実行不能、detect_leaks=0でASan/UBSanのみ再検査。
メモリリーク検査の成功とは扱わない。RT priority/governor/capability変更なし。

adapterはtigerで19条件、固定SDK API flag0/1構文検査成功。
probe_body_io_build.pyの疑似試験期待値を19へ更新したが、G1停止中のため今回実行なし。
10月1日のFT3T3p（18条件）は旧版ソースのG1証拠。新しいwriter/adapterのG1確認は次工程。
最終make check-offline exit0、IPC6件は明示skip、git diff --check成功。

ユーザーが当初TODO/進行TODO/検証で判明課題を併記するmd資料を依頼。
docs/IMPLEMENTATION_TODO.mdへA1–A8（当初方針から再整理）、C1–C9（現行作業）、
P1–P9（事実と影響/対応）、ユーザー操作の必要時点、証拠/更新ルールを記載。
実入力目標範囲超過、教師起動TCP、sim/実gate差、CRCとmotor-healthの違い、
停止検出と物理停止の違い、保存画像/幅仮定、実入力長時間未確認、右PIKA取り外し、共有条件を整理。
データ/ACT候補は存在し、再収集/再指定を現時点の前提にしていない。
README/HANDOFF/AGENTSからリンク。BODY_WRITER/BODY_IO_ADAPTER/開発手順も更新。
次は局所motor診断・実gateway/INIT/ownership接続と限定現場検証。G1起動は必要工程で用途付き案内。

## 2026-10-01 実LowState CRC必須検証・身体SDK接続をbuild-onlyで追加

右PIKA取り外し中の条件を維持。G1読み取り/一時隔離配置/コンパイルのみ実施し、
実機動作指令、SDK実publisher/client、ReleaseMode/INIT/damping、カメラ/シリアルは起動なし。
再開時のワークスペース指示（シミュレーションなし）をAGENTS/HANDOFFの現行方針へ反映。
過去のMuJoCoコード/検証結果は保存し、再実行していない。
新規install/恒久設定変更なし。既存モデル/データ/他作業のPIKA修正を保存。

固定SDKのLowState/IMU/MotorState/CRCヘッダーSHAを固定し、state_crc.hへ全フィールドの
native memory再構成を実装（2092bytes、CRC offset2088、padding0、float bit維持）。
receive_state --verify-crcは全takeで照合、不一致exit3。生成IDL/C/Hは変更していない。
strict monitor/serviceは未確認/証拠欠落/CRC不一致をラッチ拒否し、後から正常でも再armしない。
低状態のCRC一致はmotor-health/所有権/支持/立位条件の証明とはしない。
128完全fixtureを固定SDK data-onlyクラス/C/Pythonで比較、x86_64/aarch64 native bytes完全一致。
SHA107b35f26ef7ea599eb47871ab1cdf53eb3ea5d31e93851269c919d69026302c。
fixtureの符号なし減算と構文検査のinclude不足はローカルで修正後、実配置した。
これらは試験構築の修正で、実G1のCRC不一致を観測したものではない。

make body-local-crc-check：local-body-EHFf0D、実165frame全CRC一致、mode_machine5/mode_pr0。
保存SONIC150件は全gate/受理0/抽象writer0/実機指令0、147件URDF超過は変更せず保存。
最大入力間隔20.97ms、sample因果年齢上界最大31.63ms、service/supervisor正常終了。
make body-local-crc-expiry-check：local-body-zwvbSW、77実frame全CRC一致。
50probe後、receiver転送だけ停止/stdin open維持。独立watchdogは最後のsampleから109.56ms、
転送停止から87.54msでfault。process終了353.39ms、service exit1は期待、supervisor exit0。
全対象thread/process終了。Python10ms監視の実時間保証/物理停止の試験ではない。

身体SDKアダプターを新規追加。SDK-free policy wrapperと固定SDK backendを分離。
現場試験契約が不足するとI/O拒否、constructorは解除しない、明示解除1回だけ、
publisher前のmode確認、局所CRC/P-R/machine/100ms鮮度/29関節範囲を検査する。
dampingは明示した29 kdのみ、stop latchを書込み前に立て、SDK成功でも物理停止確認false。
復帰は外部の現場停止確認記録＋元modeが必要、publisher close後にSelectMode、暗黙復帰なし。
契約bool/文字列/CheckMode返答だけで物理条件や排他的制御権を立証しない。
既定G1_PIKA_ENABLE_BODY_IO=0、flag1も動作許可ではない。実launcher/recordサービス接続なし。
make body-io-build-check：最終body-io-build-FT3T3p、G1 SDK object compile flag0/1成功。
SDKリンク/構築/実行なし、実行はSDK-free疑似transport18条件だけ。前回6PeMLBも保存。

新規CRC2/adapter2、monitor計11、probe3、service --ipc7成功。
最終make check-offline exit0（ローカルIPC6件は明示skip）、git diff --check成功。
README/AGENTS/HANDOFF/BODY_LIFECYCLE/SONIC_STARTUP_BOUNDARY/新BODY_IO_ADAPTERへ反映。
残りは実gateway/500Hz writer/実ownership・初期姿勢・独立停止要求の統合と現場検証。
保存出力147件の範囲超過/開始遷移の適合性、右PIKA再装着/構成確認、停止方法/実機試験許可は未解決。

## 2026-10-02 単体PIKA 1.0 A・1.8 A設定の段階閉じを目視確認

許可済み動作について目視の準備だけを調整し、同じdiagnoseを再実行。
1.0 Aは開動作/位置目標を変えない電流変更/段階閉じ/無効化・切断まで完了。
利用者は「滑らかに動き、跳ねなかった」と回答。session-34rt2oodに全記録/phase-analysis/analysis。
閉じ終わり0.0008 rad、正常895/拒否2/再同期52、passed=true。
希望の1.8 A設定も同じ有限手順で動作完了、利用者は「滑らかで、跳ねなかった」と回答。
session-rmky5u3tに全記録/analysis。閉じ終わり0.0022 rad、無効化/切断確認済み。
初回disable writeの77.45ms後、cleanupでPosition-2.0/Current-1081434178を受信しfaultラッチ。
異常文字列はraw.binにも存在。電流変更時だけの問題とは断定しない。

cleanup中のfaultでもpassed=trueになる判定漏れを今回の実記録で発見し修正。
completed=trueでもfaultがあればerror/passed=false。新規1含む46単体成功（42.109秒）。
元の1.8 A report.jsonのpassed=trueは原本として保存、analysis.jsonに補正判定false/理由を明記。
py_compile/git diff --check成功。閾値緩和・異常無視・固定ドライバ変更なし。
これは設定と空の短時間動作であり、1.8 Aの実電流/把持力/長時間安定を測った試験ではない。
受信欠損/数値破綻は残存。目視された旧試行の急動作の根因は未確定。
G1身体/腕の指令なし、追加の動画実装/録画なし、最後のPIKAは無効化/切断済み。
この無効化/切断はエージェントの診断sessionの結果。終了確認時には利用者側の
interactive PID997912（1.8 A設定）がポートを使用していたため、そのプロセスは停止せず保持。

## 2026-10-02 許可済み単体PIKA診断・閉じ指令前に異常受信

利用者が実機動作と周囲安全を明示確認したため、tiger直結PIKAを1回診断。
0.2 Aで0.6 radへ開き、1秒後に位置目標を変えず1.0 Aへ指令15だけを送信。
71.14ms後にPosition2.0000/Speed-2.000/Current-1083665548の正常JSONを受信してラッチ停止。
前後はPosition0.5919付近、異常値はraw.binに存在。PythonのJSON解析が作った数値ではない。
位置送信は0.6のみ、閉じ段階を実行せず。disable writeまで33.36ms/無効状態受信まで85.01ms。
disable_confirmed/port_closed=true、completed/passed=falseを保存。
artifacts/gripper-control/session-_a22sm42（全記録/analysis）とfault-dkh_7swk（直前後trace）。
電流変更と受信異常の時間的関連は記録したが、因果確定ではない。
9月18日の書込0の受信でも同種のPosition2.0/巨大Currentがあった。
利用者は今回目視していなかったため、実際の急動作の有無は未確認。

追加の10秒O_RDONLY受信：1619 JSON/不正3、位置0.7270〜0.7271、Statusは全0x00、
UART書込0、port close済み。artifacts/gripper-rx/inspect-sr25789s、同種の数値異常はこの記録ではなし。
PIKA魚眼の静止1枚のみcamera-preview-jsi2v8zcへ保存。後続の利用者指示で録画等の追加実装を止める。
動作許可の取り直しは不要、次の同条件の試験は利用者の目視準備を調整する。
G1身体/腕の指令・1.8 Aの動作は行っていない。コードは45単体試験済みのまま変更なし。

## 2026-10-02 PIKAの原因切り分け準備・機器情報読み取り

根因未確定のまま進めないとの指摘を受け、送信順序/固定ドライバ/公式SDKを再監査。
CLIの送信待ち中の異常検知を送信直前に再確認するよう修正。急動作の根因とは未確定。
公式説明は指令15(A)の電流設定で、位置制御の厳密な上限という解釈は未確認。
SDKコメント2 A/API_Doc Typical 8 Aが不一致。2 Aの入力上限を維持し最大使用可能値とはしない。
公式Status表の異常bit0x01〜0x20もラッチして中止、0x40/0x80だけなら異常にしない。

有限diagnose：基準電流で開く/保持、角度目標を変えず電流だけ変更/保持、同電流で段階閉じ。
基準0.2 A/比較1.0 A/open0.6/各hold1秒/目標変化率0.5の具体的手順を文書化。
保持±0.1 rad/閉じ中0.1 rad超開きで中止、後続段階へ進まずdisable/closeを試みる。
全raw RX/時刻付き段階・TX要求・write完了・RX・入力/最終reportをsession-*に保存。
write完了はMCU ACKではなく、段階完走も使用可否の認定ではない。
新規6件はqueued送信の異常停止、段階分離・全記録、電流のみ段階の逸脱で閉じ指令を出さない、
記録失敗時のcleanup、試験時間制限、Status異常bit/非異常bitを検査する。
python3 -I scripts/check_pika_gripper_control.pyは全45件成功（40.351秒）。
制御/検査/テストのpy_compileとgit diff --checkも成功。固定ドライバSHA一致。

利用者のUSB再接続後、ttyUSB0/ttyUSB50同一個体・fuser可視所有者なしを確認。
新規inspect_pika_gripper.pyで3秒の受信と公式GET_INFO10 bytesのみ、動作指令なし。
90,113 bytes/476 JSON/不正1、角度0.0266〜0.0268、Status0x00/Current0/V23.8、port close済み。
Version応答なし。artifacts/gripper-rx/inspect-6bgra11kに保存。
診断動作は未実行。実機動作指令なしの条件のため、具体的な1回の単体動作許可が必要。
固定ドライバ/他作業/旧ログ/他プロジェクトを保存。

## 2026-10-01 PIKA実機の跳ね申告・grip段階化とfault履歴

利用者が起動1.8 A/open0.6/grip1.0 A後のPosition1.7857/Speed17.964という正常JSONを提示。
無効化/切断はtrue。追質問に実際の動きも見えると回答。表示だけの異常と断定しない。
申告はartifacts/gripper-control/user-report-jix0j_cc/report.jsonへ保存、根因は未確定。
公式SDK Gripper/SerialCommと指令15(A)/22(rad)、float32 little-endian/CRLFを照合して一致。
実機ファームウェアの内部動作/設定受理は確認できていない。

grip開始時の0 rad一括目標を、実測角度から0へ50msずつ減らす目標へ変更。
既定0.5 rad/s、--grip-speedとset grip-speedで0 < 値 <= 2を指定（ソフトウェアの範囲）。
長い入力/シリアル遅延でも1回の変化量を速度×50ms以下にし、0で再送を続ける。
物体接触時の入力待ち/current調整/open/stopは維持、その他の位置操作は従来の到達待ち。
実測速度の制限やPID変更ではなく、跳ねの根因解消を確認したものではない。
異常時はdisable前の速度整定待ちを省く。250ms鮮度/異常値ラッチ/角度範囲/2 A上限は維持。
RX256/TX64のリング履歴、最初の異常前snapshot、直後RX128/TX32を保存する。
最終JSONに直前角度/経過ms/最後の位置目標とfault_logのtrace.jsonパスを追加。
--fault-log-dirで保存先変更、保存失敗でもdisable/closeを先に完了。

新規4を含む39単体成功。現在角度からの開始/長い遅延でも段階化/0到達/入力設定拒否、
Position1.7857の異常ラッチ/履歴保存/速度整定を待たないdisable要求/無効化確認、
ファイル保存失敗でもcleanupを検査。利用者の正確な異常JSONを追加試験で再生。
今回実機port open/動作指令なし。fuserでは現在の一般ユーザー可視範囲に所有者なし。
過去の競合を否定した検査ではない。実際の跳ね解消/高電流安定性は未確認。
1.0〜1.8 Aでの反復を続けないよう案内。測定器/ktを操作の前提にはしていない。
README/PIKA_GRIPPER_CONTROL/HANDOFF更新。旧データ/他作業/固定ドライバを保存。

## 2026-10-01 実機構成の更新：右PIKA取り外し中

ユーザーより、別試験のためG1右腕のグリッパを取り外していると通知。
AGENTS/HANDOFFへ反映。左側・取付具・カメラ・配線の状態は推測していない。
PIKA付きモデルの右側質量/TCP/干渉条件を現状の実機へ適用せず、
右PIKAが必要な入力統合/把持試験は再装着・構成確認後に実施する。
送信なし実装/身体読み取りは継続可能。保存データ・モデル・試験記録・設定は変更なし。
文書更新のみ。SSH/シリアル/実機指令/試験再実行なし。

## 2026-10-01 G1起動通知後、局所監視・記録専用ZMQを実配置

ユーザーの指摘を受け、G1を使う用途（記録専用配置/身体状態読み取り）を明示して起動を依頼。
「起動した」後、galleria経由の厳密SSH照合、G1/aarch64/Python3.10.12/numpy1.21.5、
libzmq/CycloneDDS0.10.2/gccを確認。pyzmq不在は不足依存ではなく、追加installなし。
probe_local_body.pyで隔離ディレクトリへ配置し、実LowState→G1局所監視→ZMQ記録受信を検証。
固定profile/config、RecordSession/BodyRecordClientを再利用。実mode_machine=5/mode_pr=0。
SSHの因果往復＋G1局所年齢でsample年齢を上界化し、別PCの時計を直接比較しない。
実body/SONIC配列を収容するためserviceのZMQ入力上限を64KiBに明示。
4KiB超messageを含むservice --ipc7件とprobe helper3件成功。

50件probe正常run-JkeUfC、独立期限切れrun-Jed7DQ、保存SONIC150件run-ziBcmhを保存。
最終make body-local-checkはartifacts/local-body/local-body-nZZEwC：150件全gate/受理0、
抽象writer0/実機指令0、147件の範囲超過を変更せず記録。
LowState164frame/最大間隔21.04ms、sample因果年齢上界最大24.41ms。
service/supervisor exit0、receiver対象限定TERM、feeder/reader/watchdog全終了。
最終期限切れlocal-body-IGY3In：50probe後にstdinを開いたまま転送のみ停止。
最後のsampleから101.31ms/転送停止から96.38msで異常を観測、process終了353.36ms。
service exit1は期待結果、supervisor exit0。全対象終了、raw状態/decisions/各stderr/journal/report回収。
Python監視の実時間保証や物理停止の試験ではない。保存目標の生成時刻鮮度も認定しない。
通常G1Deploy/実publisher/INIT/制御権変更/カメラ/シリアルは起動なし。
CRC未確認、物理停止・送信・引継ぎadapterは未完了。閾値/目標clippingによる合格化なし。
make check-offline一括exit0（既存4＋service2 IPC明示skip）、他作業のPIKA変更を保持。
再実行Make/README/BODY_LIFECYCLE/AGENTS/HANDOFFを更新。
続報：probe_g1_lowcmd_abi.py/make lowcmd-abi-checkでG1/aarch64 native LowCmdをデータ専用検証。
固定SDK data class（DDS traits除外）とCRCだけを一時compile、SDK client/publisherなし。
既存保存journal1540件、mode_machine=5は読取記録の診断値。x86_64/aarch64全native1004bytes一致、
独立Python CRC一致、G1バイナリexit0。artifacts/lowcmd-abi/lowcmd-abi-J7oor9へ回収。
memory SHA双方85c3ec8629d58d1b53ea4bbebff9ef94c2360b47d256d1169f344c180f0907dd。
LowState受信CRC/実DDS配送/firmware受理/実機動作の検証ではない。試験バイナリは終了済み。

## 2026-10-01 PIKA受信再同期を修正・警告の連発を抑制

利用者の対話ログは約4KBのbuffer resync警告が連発し、Positionの診断範囲外で終了。
0.6 rad移動1回/grip1回、無効化/切断は確認済みだが、異常値が未記録で原因値は不明。
固定ドライバの受信分割だけCLI側TelemetryFramerで置換し、次の完全な状態JSONから復旧。
文字列/エスケープ、全byte境界の分割、括弧欠損/文字列欠損、4KB超の正常burst、
部分バッファ上限、入れ子のmotorキー、motorstatus先頭、不正JSON後の復旧を検査。
警告は最大5秒に1回、最終JSONにrx統計/fault_detailを追加。異常値の具体値をerrorにも表示。
固定SHA/送信方式/2 A上限/250ms期限/異常値ラッチを維持。新規9件含む35単体成功。
テスト用の連続欠損でもopen/grip/current/open/stop/quitとcleanup成功、受信thread終了。

了承済みの実入力読み取りとしてtiger /dev/ttyUSB0をO_RDONLY/raw/460800で2秒受信。
flock/TIOCEXCL、UART書込0、動作指令なし。60,833 bytes/333フレーム、正常332/不正JSON1、
再同期2/破棄64 bytes、角度0.0016〜0.0019、最終Status0x00、排他解除/close済み。
保存先artifacts/gripper-rx/tiger-resync-q3qy5n6l/raw.bin/report.json/replay.json。
同記録をCLIラッパーに256 bytesずつ再生し同数/異常なし。
9月18日151,281 bytesも再生し正常830/拒否3、Position2.0/Current-1080385602のフレームを角度範囲で拒否。
修正後の実機開閉/電流設定/把持をこちらからは再実行していない。
README/PIKA_GRIPPER_CONTROL/HANDOFFへ反映。既存ソース・他プロジェクト・ログは保存。

## 2026-10-01 簡単な動作試行へ訂正、対話gripを追加

ユーザーは測定ではなく簡単に力を変えて試す意図だったと明示。測定提案への過剰な展開を訂正。
control_pika_gripper.pyの対話モードにgrip [A]を追加。
指定電流→enable→閉じ目標0 radを送って直ちに入力へ戻る。接触で閉じ切らなくても終了しない。
入力待ちに100msごとに既存位置指令を再送、鮮度/有効状態は従来同様確認。
currentで電流変更、open/move等でgrip再送解除、stop/quitは無効化処理。
0 < A <= 2を維持し、不正grip引数はenable/送信前に拒否。
PIKA_GRIPPER_CONTROLに最短操作例を追加し、以前の測定文書は参考履歴として保存。
実機シリアルopen/動作指令なし。測定器/ktはこの簡単操作に不要。
新規3件を含む26単体試験成功、送信なしCLIのopen/grip/current/open/stop/quitも正常終了。
変更範囲のgit diff --check成功。

## 2026-10-01 PIKAの把持力検証準備・電流範囲補強

ユーザーが出せる力の検証を希望。ロードセル/フォースゲージの照会に「測定器はまだない」と回答。
力Nの確定は測定器が必要。既知重量の保持能力の評価とは区別すると説明。
AgileX公式PIKA SDK gripper.pyのset_motor_torqueに0〜2 Aの記載を確認。
control_pika_gripper.pyの起動引数・Python API・current・torque換算に0 < A <= 2を強制。
超過は無送信拒否、ktにより超過した場合も同じ検査。23単体成功。
メーカー資料の最大力2kg表記は定義/測定条件が不明、ktや実機のN値に代用しない。
PIKA_FORCE_TEST.mdに測定器を使った段階計画と記録項目を準備。
現行closeは目標到達前提なので、接触時の期限付き保持/力の記録は別途実装が必要と明記。
測定器の条件に依存する実機試験は未実施。今回シリアルopen/動作指令なし。

## 2026-10-01 SONIC＋PIKA動力学閉ループ、保存RGB LeRobot統合30秒

galleria既存環境を再利用し、stdio専用SONIC→MuJoCo500Hz PDの閉ループと動画回収を実装。
自由基部/接触あり、バンド・root reset・目標clippingなし。実10観測/0.2秒warmup。
角速度BODY慣性軸をXBODY胴体軸へ修正、座標/時刻4＋actor4単体試験成功。
ACT bundle/保存RGB SHA照合、現sim TCPにfresh h1を適用し計画参照IKへ接続。
run-kv4ikn7u3秒成功、run-_z1bvt9z30秒ACT900/SONIC1500、両worker exit0・範囲外0。
最低高さ0.7312m、傾き0.0801rad、警告0。視覚/幅/実タスク/実時間/実機成功とは別。
最終コードrun-mkjlzx75も30秒同結果で成功、ONNX/TRTキャッシュの前後SHA不変を確認。
教師absolute TCP API追加、従来IK試験4→5成功。計画参照と実観測を分離。
run-pu1qxp7g教師15秒750推論で完走/立位/範囲外0、ただし起動TCP8.23cmで未合格。
再生開始後は独立FK再計算で3.39cm・移動7.54cm、全期間基準を緩めていない。
以前のwarmup1秒転倒・教師IK失敗・直接中立腕開始の4超過は保存。
SONIC_MUJOCO.md、Make起動口、README/AGENTS/HANDOFFへ反映。

実機側local_body_monitor.py/LocalSonicBodyBridgeを追加し、新規9単体成功。
GPU bodyコピーとG1ローカルLowStateを分離、重複/逆行/期限切れ/mode変化をラッチ。
receive_state --streamへmode_pr/mode_machine追加、固定SDKヘッダでC構文検査成功。
純粋コアでG1配置/実送信/制御権/物理停止はまだなし。CRC未確認を保持。
実機実装は省略せず次工程に残す。実機接続・動作指令なし。
続報：local_body_service.pyでG1側ローカルstdin LowState/ZMQ要求を分離。
独立10ms監視thread、EOF/期限切れラッチ、単一peer filter、確実なthread cleanup。
初回はPython起動前のpipe backlogで失敗し、最初の受理前だけ古い観測をdiscardするよう修正。
active期限切れは解除しない。終了時の試験側stdin BrokenPipe cleanupも修正。
人工入力/実local IPCの正常終了・GPU要求もEOFもない独立期限切れを含む7試験成功。
G1配置/実送信なし。ZMQ peerが局所身体観測を書き換えるAPIはない。
教師最終run-fpygotrmも同じ未合格を再現。再生区間3.39cm/0.1758radと全期間8.23cmを別記録。
ACT最終run-mkjlzx75と教師run-fpygotrmのONNX/TRT cache前後SHA不変、全worker終了確認。
この時点のcheck-offline一括exit0（新規local monitor9/actor4込み、既存IPC4skip）。
後続service5単体/IPC2追加後の一括結果は下記追記を参照。
最終make check-offlineもexit0（IPCは既存4＋新規service2を明示skip）。
新規serviceは別の--ipc実行で7/7成功、make check-sonic-simは座標/時刻4＋actor4成功。
git diff --check成功。実機出力を有効化する設定・コマンドは追加していない。
G1側実配置を進められるか、既存厳密host-key設定でgalleria→G1 uname読み取りを1回実施。
192.0.2.11:22が5秒でtimeout。G1の稼働は確認できず、ファイル配置/状態購読/指令なし。
G1起動を非実機作業の前提にしない。搭載PCのaarch64/依存/実入力検証は次回の接続時に残す。

## 2026-10-01 PIKAの対話CLIを追加

動的なユーザー入力で調整したい依頼に対応し、同じcontrol_pika_gripper.pyにinteractiveを追加。
open/close/move/cycle/current/status/params/set/kt/torque/enable/disable/stop/quitを実装。
初期disabled、最初の位置操作でenableし、その後は有効状態で入力を待つ。
currentは即時変更、setは次の操作へ適用。disableで接続維持、quit/EOF/Ctrl+C/異常でcleanup。
標準入力を50ms pollし状態鮮度を入力待ちにも確認。同じthreadから操作し送信競合を避ける。
位置到達確認中は同期処理。途中中断はCtrl+C、stopコマンドは動作完了後に処理される。
不正入力は無送信で継続、未到達/鮮度切れは失敗として終了。結果のmove記録を64件に制限。
既定のpreviewは未接続で入力/パラメータだけを検査し実測を捏造しない。
単発と対話で到達確認/無効化確認を共通化、固定PIKAドライバは無変更。
新規9件を含む22単体成功、送信なしCLIのパイプ入力/EOF処理も成功。
端末PTYでもcurrent/set/open/move/close/status/params/quitをpreview入力し正常終了。
make check-offline一括exit0（既存IPC4件skip）。固定ドライバのSHA一致、git diff --check成功。
README/HANDOFF/操作文書に起動コマンド、操作例、有効維持と単発の差、同期動作を記録。
実機接続/動作指令なし。身体/腕/SONICの実機出力やOS設定は変更していない。

## 2026-10-01 tiger直結PIKAのポート確認

ユーザーの/dev/pika欠落エラーに対応。前回の既定パスはG1搭載PC用だった。
ホストのls/udevadm/idで1a86:7522/ch341→/dev/ttyUSB0、ttyUSB50の同一リンク、
tigerのdialout所属/アクセス権を読み取り確認。シリアルopen/動作指令なし。
--port /dev/ttyUSB0付きの起動例と、G1既定パスについてhelp/接続前エラーを改善。
操作文書/HANDOFFに接続PCの違いを追記。自動ポート選択やOS権限変更は行っていない。

## 2026-10-01 PIKA単体開閉とトルク調整コードを作成

ユーザーのPythonコード依頼とトルク変更の追加依頼を受け、control_pika_gripper.pyを追加。
open/close/cycle/limit、電流上限A指定、利用者の確認済み実効トルク定数でN·m→A換算。
LeRobot commit79edf6a95948d0f0d75df1d54d0a5aad305f75a8のドライバを無変更移植。
assets/pika/gripperにSHA/元パス/Apache-2.0ライセンスを保持、pyserial3.5のみを実機依存とする。
既定はプレビューでserial import/openなし、実操作は利用者が--executeを指定した場合のみ。
位置到達を確認、古い/不正状態で追加操作拒否、終了と中断時にdisable/disconnect。
既存ROS initSerialの電流上限/1000→EFFORT_CTRL15を照合。上限ACKなしを結果へ明記。
13単体試験成功（固定ドライバのシリアルだけを置換、pyserial導入なしでも実行可能）。
cycle/電流指定とlimit/N·m換算の送信なしプレビューも成功。check-offlineへ組込み。
make check-offline一括exit0（既存IPC4件skip）。後続の無効化送信時刻照合も追加試験で成功。
README/HANDOFFとPIKA_GRIPPER_CONTROL.mdに操作/配置/単位/未検証範囲を記録。
実機接続/動作指令・シミュレーションなし。新しい電流値・トルク定数・実機動作は未検証。
身体/腕/SONICの実機出力や設定は変更していない。

## 2026-10-01 方針更新：MuJoCoでSONIC/LeRobot統合検証、実機実装は省略しない

ユーザーがMuJoCo案を採用し、実機実装をスルーする短縮案は不採用。
SONIC単体→PIKA/教師軌道→LeRobotの動力学閉ループ・動画・一括起動を進める。
6〜12時間はこのMuJoCo実装/初回検証の目安で、実機側実装/物理検証を含む総時間ではない。
旧WBCシミュレーション資産は再利用候補だが、旧balanceをSONICとして試験しない。
実機指令禁止/通常G1Deploy起動禁止は維持。root/repo AGENTS、HANDOFFの方針を更新。

## 2026-10-01 SONIC→身体受信部のrecord-only接続を実装

sonic_body_bridge.pyのenvelope/BodyLifecycle接続/RecordSession互換handler/client、
run_body_boundary.pyと2つのMake起動口を追加。既存online loopへ任意body_sinkを接続。
関節順序/身体tick/連番/幅/有限値/record-onlyを照合し、姿勢確認前の目標はgate。
出力は変更せず、PIKA幅は別metadata。通信時間を20ms期限に含め、終了例外でもworkerをcleanup。
接続7試験、online追加4試験（計20）成功、check-offline一括成功（既存IPC4件skip）。
fake推論workerと実受信handler/clientで50件の連続接続・全gate・幅保持・終了を確認。
保存実SONIC/身体150組のファイルrun-i0jva6mwとローカルZMQ IPC run-unswp0meが成功。
decision SHA8036c4c207fd430d51f5bf7fe0bb98e8c2885c434824a473cf165c0242bf199bで一致。
全150件gate/受理0、147件のURDF外（右ankle roll/waist roll）を記録。既存問題は解消していない。
受信thread終了、protocol ACKは記録終了のみ、身体stop_required/物理確認falseを維持。
初回socket bindはsandboxで拒否。ローカルIPCだけのescalation後成功、恒久権限変更なし。
今回GPU/G1接続・新規推論・シミュレーション・実機指令なし。
受信部はrecord-only、引継ぎ/INIT操作なし、writer未駆動。既存launcherの配置は変更せずsink既定無効。
README/BODY_LIFECYCLE/DEVELOPMENT_RUNBOOK/AGENTS/HANDOFFへ成果・起動口・未統合範囲を反映。

## 2026-10-01 身体ライフサイクル・LowCmdメモリ/CRCを送信なしで実装

継続指示に従い、body_lifecycle.py/profile.pyと診断config、保存実身体再生、
固定Unitreeデータクラス/CRCのstdio専用previewを追加。SDK通信/通常G1Deployは不使用。
明示的な引継ぎ要求/診断ACK、3秒の初期参照、実測q/dqの継続条件、入力/目標/所有権watchdog、
writer間隔/関節範囲/参照速度、停止要求ラッチ/診断復帰を実装。
古い入力が期限切れを解除しないこと、停止がGPU/clock/join待ちをしないこと、
記録bufferが256command/128event以内であることも検査。実機adapterではない。

状態機械23・保存再生3・LowCmd3の29追加試験成功。check-offline一括exit0、既存IPC4件明示skip。
make body-lifecycle-check/verify、lowcmd-preview、helpを追加。
保存run-b5do1ocsの実身体150件→1540抽象出力、SONIC目標受理0。
run-6arb9pnqで3秒settling、3.08秒body_watchdog_expired、停止後出力拒否、全journal再計算一致。
同入力のLowCmd preview run-uin1oocvは1540件・1004bytes、29motor/未使用6slot/ゼロpadding/
reserveと独立CRCが一致。mode_machine=0はfixture、native object memoryはDDS/CDR形式ではない。
上流SDK3ファイルとコード/入力/結果hashをreportへ記録。BSD-3-Clauseの原ライセンスを保持。
旧試作run-m6vvtdxs/run-gbadci9oも保存。最新再計算はrun-6arb9pnqを使用。

シミュレーション/新規GPU推論/身体・腕・グリッパ指令なし。
搭載PC ABI検証の可否を調べるuname読み取りのSSHは、galleria→G1でtimeout。
最初の自動承認レビュー期限切れはプロセス未作成。一度の許された再試行で接続timeout。
G1への配置/プログラム起動なし。電源/支持状態は未照会。起動依頼なしで非実機整備を継続。
BODY_LIFECYCLE.md/README/DEVELOPMENT_RUNBOOK/SONIC_STARTUP_BOUNDARY/AGENTS/HANDOFF更新。
実機制御権/停止/復帰adapter、初期参照の物理妥当性、aarch64 ABI/DDS受理、
SONIC出力範囲・実タスク性能は未完了。診断ACKや仮想500Hzを実機合格にしない。

## 2026-10-01 起動因子分析・開始契約監査・診断起動口を整備

ユーザーの「再開」に従い保存run-ofbwc_6tを分析。GPU再実行/G1接続/シミュレーション/実機指令なし。
全8背景でのチャネル切替ペア分析を追加しstartup-analysis-20261001.jsonへ保存。
q/gravityの初期感度は大きいが、dq/gyroのペア差はこの記録で0.003rad未満。
初期10周期以後も48/48条件にURDF超過が残る。履歴/参照の既定変更なし。
startup入力の定数寸法/順序/scale・基準結果の完全性・float32範囲・保存cache照合を補強。
補強後も48条件の基準/式/集計の保存再検証成功。

audit_startup_contract.pyとファイル専用C++oracleを追加。固定上流math関数で
150endpoint/1500履歴Quaternion使用の生値/正規化、mode0姿勢、仮heading起点を照合。
encoder姿勢float32差0、gravity差最大4.1723e-7、正規化Python/C++差0。
実際のINIT/制御権/heading reset/支持/停止は再現していない。
最終監査startup-contract-20261001-v2.json。初稿も保存し、gravity計算用のidentity参照の
無関係なheading集計だけ最終版から除外。decoder再推論や既定処理変更なし。

Makeの保存再検証/保存契約監査/GPU新規推論3起動口を追加。
起動因子11試験・開始契約4試験をcheck-offlineへ組込み、一括成功（IPC4件は明示skip）。
SONIC_STARTUP_ABLATION.md追加、README/TARGET_AUDIT/DEVELOPMENT_RUNBOOK/AGENTS/HANDOFF更新。
低レベル送信・初期遷移・制御権・物理停止・実タスク品質の未完了は維持。

## 2026-09-30 起動履歴の因子比較を実行、本日終了

独立引き継ぎの次段として保存入力のみの起動履歴診断を実装。
q/dq/gyro/gravityの16組合せ×記録IK保持/実姿勢保持/連続IK参照3種×150周期。
scripts/sonic_startup_ablation.py、run_startup_ablation.py、check_startup_ablation.pyを追加。
単体7件成功。prepareの定数読取りC++harnessは<vector>不足を修正後成功。
galleriaで48条件/7200推論を完了、worker exit0、コピーしたモデル/キャッシュSHA前後一致。
既存4基準のtoken/raw action/目標差0、目標変換式差0、参照ごとのencoder tokenは全16条件で一致。
結果回収・保存再検証成功: artifacts/sonic-startup-ablation/run-ofbwc_6t/。
G1接続/実機動作指令なし。閉ループ/物理停止/実タスク合格ではない。
ユーザーの本日終了指示で停止。因子結果の解釈・開始契約のソース照合・診断文書/起動口整備・
追加後のcheck-offline一括実行は再開時に行う。GPU再実行は不要。詳細はHANDOFF冒頭。

## 2026-09-30 独立起動履歴診断を検討方針へ反映

ユーザー指定のsonic_startup_diagnostic_handoff_20260930.mdと最新AGENTS/HANDOFFを読了。
外部ローカル成果のreport/verification/oracle-verificationを読取りで確認。
固定条件の現行目標再現・目標式変換・encoder tokenは差0。
起動Logger paddingはdecoder出力へ影響するが、初期10周期の最大目標−保存実測差は
1.252513→1.719764rad、URDF超過も残る。padding単独を根因/解決策と断定しない。
AGENTS/HANDOFFに根拠文書と、チャネル別起動履歴・参照との交差比較・開始条件契約の優先検討を記録。
既存の補間/極値監査/モデルbundle/30秒人工入力検証は完了扱いを維持。
今回は文書更新のみ。コード変更・追加実験・GPU/G1接続・USB/シリアルopen・動作指令なし。
独立診断の承認範囲を追加実験/実機動作へ拡張せず、停止/制御権の未検証を維持。

## 2026-09-30 モデル一式の固定・起動前照合・共有を実装

既存valid49/学習済みACTで運用整備を継続。config/policy-bundle.jsonを追加。
モデル7ファイル、RGB前処理/幅codec/GPU依存lock3ファイルのサイズ/SHA、10D/h1/columns/RGB/復号順、
固定LeRobot commitとデータ/split出典hashを記録。test set消費・再学習・モデル変更なし。
policy_bundle.pyをGPU ACT workerのready前に組込み、ローカル配置前とGPU実体を双方照合。
全経路/人工入力/実入力runnerと旧input-shadow配置も必要ファイルを転送するよう更新。
実入力runnerへの変更は今回G1入力を開いて動作確認してはいない。
bundle-exportは明示リストだけコピー後再検証、決定的tar.gz、同名上書き拒否、原子的公開。
14単体: 欠落/改変、codec/processor/IO違い、パス/出典違い、配布内容限定・再現性・上書き拒否など成功。
実ACT workerの改変拒否をGPUなしで試験。配布archiveの新規一時フォルダ展開→標準Python照合も成功。
make check-offline成功（IPC4件は明示skip、今回check-runtime再実行なし）。
GPU run-w2r_5_nu: 保存画像2組→ACT→IK→SONIC、3worker exit0、回収0。
GPU run-ssy2zdrv: 人工入力3秒/0.4秒参照、93policy/150control、4worker exit0、記録整合成功。
GPU run-ck4k0eu8: 対応上限30秒/0.4秒参照、903policy/1500control、4worker exit0、回収0・整合成功。
host間隔18.766〜21.324ms、20±2ms外0件、GC最大1.267ms。実時間保証/実入力/身体追従ではない。
診断配布archive: artifacts/diagnostic-act-bundle-20260930.tar.gz、17ファイル/43,459,792bytes、
SHA256 b61d3879eba76c94c225d9dab30052b988059c5ddc296d6dee3001c2daf9cdc4。
README/AGENTS/HANDOFF/DEVELOPMENT_RUNBOOK更新、POLICY_BUNDLE.md追加。
G1接続/身体・腕・グリッパ指令なし。既存環境・原本・重み・ログを変更していない。
未解決の目標差/URDF外・停止/制御権移行・動的参照・実タスク品質・新規PC全自動setupは引き続き残る。

## 2026-09-30 既存データ再確認とTODO訂正

データ指定を求めた直前のTODOは既存学習記録の確認不足だったため訂正。
ローカルvalid49原本の存在、manifest記載17ファイルのサイズ/SHA256一致、学習済みACT重みの存在を確認。
49episode/10881frame、39/5/5episode分割、145行除外後採用8693/1022/1021。
メタデータtasks.parquetはtask_index0/task文字列null。データ未準備という意味ではない。
AGENTS/HANDOFFに所在・学習済み状態を追加し、再指定・再収集をユーザーのTODOから取り下げる。
G1/GPU接続、学習再実行、元データ変更なし。

## 2026-09-30 継続確認を挟まず参照のフレーム間極値を監査

前回の終了は結果報告の区切りであり、追加承認待ちではないとユーザーへ説明。
JointTrajectory.extremaとaudit_joint_reference.pyを追加。
数値多項式根と端点で0.18秒予測窓内のq/dq/ddq極値を評価するファイル専用監査。
run-b5do1ocsの150窓で参照の角度/速度はURDF内。加速度制限は未確認。
continuous-reference-audit-20260930.jsonを保存。厳密な区間保証・実機閉ループ保証とは扱わない。
既知のsmoothstep極値・端点では見落とすovershootを含む4単体、観測15試験成功。
G1/GPU接続・動作指令・既存設定変更なし。SONIC出力側の目標差/URDF外は未解決のまま。

## 2026-09-30 時間整合した関節参照を選択式で統合

scripts/sonic_joint_trajectory.pyを追加。実測q/dq・加速度ゼロから開始し、IK終点へ5次補間。
更新時のq/dq/ddq連続性を維持し、20ms未来10点のqと解析dqをSONICへ渡す。
MeasuredStream/観測worker、record-only runnerへ選択式で統合。既定の終点保持は変更なし。
make trajectory-fixture-check RATE_SECONDS=3を追加。
3多項式単体・15観測試験、make check-offline成功。
GPU人工入力run-ddwfs4mc:93policy/150control・4worker exit0、保存整合成功。
GPU保存実身体run-ptukt__r:150窓×2履歴条件、計算完了・指令ゼロ。
新参照の再帰条件最大差1.162244rad、URDF外は右足首roll/腰roll/腰pitch。
従来から初回差は改善したが、全体/範囲の問題を解決したとは言えない。
保存参照点の最大dq2.622933rad/s、ddq20.637852rad/s²。実機の制限保証なし。
保存再計画の時刻はpolicy初使用の身体時刻。元のGPU発行時刻の復元ではない。
詳細JOINT_REFERENCE.md。新モードでのG1入力/動作/接地検証は行っていない。
最初のgalleria実行は自動承認レビュー期限切れで未開始、一度の再試行で成功。

## 2026-09-30 モデル交代のおさらいとAGENTS整備

会話、既存AGENTS/README/HANDOFF/監査資料、固定設定、保存artifactを読取りで照合。
run-b5do1ocsをverify_online_record.pyで再確認し、93policy/150control/186画像の整合性成功。
ワークスペースルートにAGENTS.mdを作成、repoの既存AGENTS.mdに現行方針/到達点/残課題を集約。
HANDOFF冒頭に現状要約を追加し、以下の古い「最新」「未実行」「承認待ち」との優先順位を明記。
9月25日のユーザー申告「吊り下げ、両足は浮いている」を保存。停止方法は未回答のまま。
今回は文書整理とファイル監査のみ。G1/GPU接続・新規推論・実機指令・OS設定変更は行っていない。

## 2026-09-24 最新: 上流観測関数の直接照合とSONIC起動境界

check_sonic_upstream_history.pyを追加しmake check-offlineへ登録。
固定SHAの上流C++関数を通信なしのharnessで実行し、32組×10フレームを照合。
decoder930要素はfloat32で完全一致、encoder1247要素はatol1e-7で一致。
mode0/heading補正なし/上半身overrideなし。logger時間補間や実機応答の検証ではない。
make check-offline成功、make check-runtimeはsandboxのIPC bind拒否後、許可環境で全35件成功。
SONIC_STARTUP_BOUNDARY.mdに上流constructorのReleaseMode、3秒INIT、500HzWriter、
StopのWait後一回damping、destructorにStopがない点を記録。
現在の支持状態と確認済み停止手段をユーザーへ質問。過去の支持/約5秒dampingを現在の検証済み条件として流用しない。
追加動作許可はまだ求めていない。現場条件が判明後、限定試験と停止方式を具体化する。
G1への接続/指令/設定変更はこの追加作業では行っていない。

## 2026-09-24 最新: 保存入力の目標監査と4条件GPU比較

ユーザーへの返答時にG1へSSH接続成功、稼働時間2:10、試験プロセスなしを確認。
G1を停止する操作はしていない。以降は保存入力のみで作業、追加承認待ちなし。
audit_motion_record.pyと3単体試験、make audit-recordを追加。make check-offline全体exit0。
prepare_online_ablation.py / compare_online_ablation.py、run_sonic_replayの--compare-recurrentを実装。
150×29出力を保存履歴から完全再現（最大差0）。実姿勢保持でも最大1.179329radの差が残る。
詳細・限定事項・再現方法はTARGET_AUDIT.md。指令ゼロ、hardware_ready=false。
当初のIK参照では右足首roll/腰rollがURDF外。原因未確定で、ゼロ履歴やclippingによる回避はしていない。
README/開発手順の「G1未実行」記述を訂正。

## 2026-09-24 最新: 一時RR/1適用下の3秒実入力統合が完走

ユーザーがG1端末で補助を起動。稼働確認後に3秒入力専用試験を開始。
artifacts/full-record/run-b5do1ocs: passed=true、実画像186枚、ACT/IK93回、SONIC150回。
入力2プロセス・GPU4workerの終了コードはすべて0、入力cleanup残存0、記録hash整合成功。
priority-report.jsonを同artifactへ回収し、対象パスが今回の/tmp/g1-pika-online-NB8kmO/receive_stateと一致することを検査。
PID9310/9374にRR/1が実際に適用され、両方process_exited。補助は66.728秒で正常終了、errors=[]。
優先度を上げたプロセスは残っていない。恒久設定変更なし、身体/腕/グリッパ動作指令ゼロ。

身体履歴の実受信間隔19.464〜20.948ms、150窓の最終サンプル間時間2.979702秒。
policy参照生成完了時の最大年齢57.983ms。
GPU開始間隔18.021〜22.237ms、20ms±2msからの外れ1件、GC最大0.467ms。
これは一回の短い比較試験の成功であり、CPU待ちだけが根本原因だという確定や長時間/実時間保証ではない。
以前の通常優先度3秒失敗ログも保存。hardware_ready=false、物理停止/制御権/追従検証は未実施のまま。
通常のmake online-recordは自動昇格しない。今回の一時補助は終了しており、次回の優先度比較には再起動が必要。

## 2026-09-24 一時優先度試験の了承取得、sudo認証待ち

ユーザーが受信プロセスだけの一時優先度調整を「よい」で了承。
G1のsudo -n -lはpassword required。優先度変更はまだ実施していない。認証情報は取得/保存していない。
temporary_receiver_priority.pyをG1の/tmp/g1-pika-priority-m4jFgz/へ配置・構文検証・hash一致確認。
script SHA256=57a5105f8dfeadde5d7bcbbfeea836c7c81395b2dc7debb49d392f30774206c6。
新規起動されたunitree所有のreceive_state --stream、専用一時フォルダ、バイナリSHA256一致をすべて条件にする。
対象binary SHA256=7196b097f972c08d4aa545f920ee67bdf521aca4d7117645332e6224376fc134。
最大2プロセス、RR優先度1、最大90秒。終了/INT/TERM時は生存対象を通常スケジューラへ復元。
RT CPU quotaは既存950000/1000000usを読み取り確認のみ。恒久設定・sudoers・capabilityを変更しない。
ユーザーがG1端末でsudo実行しREADY表示後に知らせる必要がある。その後、90秒以内に3秒入力専用統合を起動する。
補助が期限切れなら試験を開始せず、新しいlog名で再実行が必要。root補助の記録priority-report.jsonも回収する。
優先度変更を終えたという主張や、未実施の性能改善を成功として扱わない。

## 2026-09-24 最新: 1秒合格、3秒の実入力安定性は未達

魚眼の30fps化と露出/FPS復元は完了。run-zmw1z4fsの1秒合格を、長時間合格へ拡大解釈しない。
3秒試験は複数回失敗し、すべてログ・部分記録を保持。最新run-rqy0jijhの直接原因は画像側に同梱する
実身体履歴の受信間隔23.177ms（20ms±2msの条件外）。カメラsource停止後、参照104.217msとなり計算側も停止。
その前のrun-srluqgwuでは22.023msを検出。run-ievsw1s2は53 policy/87 control後に参照115.609msで停止。
受信を固定周期へ修正してポーリング遅れの累積を除去したが、OS実行遅延まで解消したとは言えない。
変更: state_receiver/sample_clock.hとC単体、check_sample_clock.pyを追加。受信時刻は実時刻のまま。
欠落slotの複製/補間・閾値緩和はしていない。実入力の再現安定性は未達。

取得要求は独立30Hzタイマーではなく、30fpsの新規カメラペア到着へ追従するよう変更。
人工入力fixtureも30Hzの到着待機を模擬する。身体は受信済み20件から次の実10件窓を順次返し、100ms鮮度で拒否。
現在の単体online16件、身体transport16件（IPC込み）、全ローカルIPC35件、C時計1件が成功。
最終GPU人工入力3秒回帰run-a5n12vh1: 93policy/150control、4worker exit0、記録hash整合成功。
host間隔19.085〜20.879ms。人工入力であり、実センサーの周期安定性を証明しない。

G1の入力プロセス残存なしを確認。CPU governor=schedutil、照会時1.344/1.421GHz、上限1.984GHz。
負荷平均約0.16、通常スケジューラTS、ユーザーのリアルタイム優先度上限0。
照会は停止後の値であり、これだけで周期乱れの原因をCPU周波数と断定しない。
次の切り分け候補は受信プロセスのみの一時的な優先度調整（sudo権限が必要）。了承前には行わない。
OS永続設定、CPU governor、優先度は今回変更していない。身体・腕・グリッパ動作指令はゼロ。

## 2026-09-24 魚眼15fpsの原因を受信バッファへ切り分け

ユーザーが露出/FPSの一時変更・保存/復元を了承。身体/グリッパの動作指令は未許可・未送信。
新規scripts/probe_camera_exposure.pyで元の露出・format・frame intervalを変更前に保存。
露出/FPS復元を照会確認。artifacts/exposure-test-1、exposure-test-2に設定・実測時刻・画像を回収。

同じMJPG640x480/30fps要求での比較:
- 自動露出・受信buffer1: 15.0121Hz。
- 手動10ms・buffer1: 15.0117Hz、画像平均輝度約15.6（自動時約106）。
- 手動5ms・buffer1: 15.0116Hz、平均約8.1。露出短縮は改善せず。
- 元の自動露出・buffer4: 29.9616Hz、平均約106.1。
- 60fps要求・buffer4: 設定照会は30fps、実測29.9711Hz。60fpsは成立しない。

露出はauto=3/absolute=156、frame interval=1/30へ復元済み。永続的な撮影設定変更なし。
本番入力コードの魚眼受信bufferを4へ変更（D405は1のまま）。専用readerは常時読み、最新1件だけ保持。
run-ewuj3gq3では実ACT30回・SONIC49周期まで通過、最後は118.736msの参照鮮度で停止。
有限試験の撮影開始が推論開始より早いため入力が先に尽きる点を修正: 新規policy入力を3件追加取得。
1秒は33 policy/50 control、30秒は903/1500。古い参照の有効期間延長やデータ複製ではない。
別試験run-ke5clytqは初期入力103.140msで停止。2カメラのJPEG90圧縮を各readerへ移し並行化。
元の画像受信時刻を保持し、圧縮時刻へ置き換えない。開始後の100ms鮮度/周期/重複検査は維持。

最終的には両カメラ4buffer・各readerのJPEG90圧縮とし、実際の受信年齢25ms以内の新規ペアを最大100ms待つ。
ACT JPEG展開/同じtensor配置とIKソルバを入力開始前にウォームアップ（合成出力は破棄）。
run-zmw1z4fsで1秒の実入力統合完走: 33policy/50control、画像66枚、入力2+worker4すべてexit0。
画像/身体記録hash整合成功、残存プロセスなし。host周期17.692〜23.179ms、±2ms外れ6件、実時間保証なし。
3秒延長run-klyw3swfは初期host間隔37.048msで最新身体窓へ飛び、重複/欠落検査で停止。
受信bufferを20実測件へ拡張し、前回の次の実窓を返すよう修正。鮮度100msと履歴20ms±2msを維持。
未保持/古い窓は拒否し、時刻の加工/欠落補間はしない。ローカルIPC35試験成功。

## 2026-09-24 入力専用実機試験・魚眼15Hzを確認

ユーザーの「OK」でカメラ/身体/右serialの入力専用試験を了承済み（serial openのMCU reset可能性を説明済み）。
動作指令、制御権変更、シミュレーションは一切実施していない。実入力の統合試験はまだ不合格。

- 身体単独8秒: artifacts/sonic-state/sonic-state-evXVZs、388件/379窓すべて20ms±2ms条件成立。
- 初回run-mv0rd6vd: カメラ起動中の身体周期乱れを起動前から保持して停止。
  handshake時だけ新しい実測10件を待つよう修正。開始後の異常/欠落検査は維持。
- run-oe8bzdu6: 実画像/幅/身体→ACT→IK→SONICの計算出力1件を記録、次周期で参照113.753msとなり100ms条件で停止。
  画像要求24.119ms、初回ACT往復22.541ms、IK11.270ms。送信はゼロ。
- 画像取得とACT/IKを別スレッド・容量1キューで並行化。キュー内経過時間も鮮度に含む。
  同じ画像を通さず、G1側で新規フレームを最大100ms待つ。
  画像処理後の年齢へ全RTTを加えていた二重計上を修正: source age + RTT - 実測server処理時間。
  処理時間の有限値/非負/RTT以内を検査。PC間時計差は使わず、100ms閾値は変更していない。
- 最新実入力run-_kwxxgseも参照102.722msで停止。G1入力プロセス4件を対象限定で終了、残存0を確認。
- 中間run-bcvjqtvcは前回異常終了後の身体service残存でport競合。
  SSH終了だけに頼らず、今回の一時フォルダの受信専用プロセスのみ終了/確認する処理を追加。
  無関係プロセスが残ること・広いパスを拒否することをローカル実プロセス試験で確認。

推論/DDSを外し右カメラ2台＋右幅だけ30組取得して切り分け:
artifacts/input-timing-20260924.json。魚眼15.0098Hz、RealSense30.0061Hz（実frame counter/受信時刻差）。
魚眼の実間隔は約63〜69ms。グリッパ受信年齢は約0.5〜6.5ms。
設定照会ではMJPG640x480、要求周期1/30、Auto Exposure=3、Exposure Absolute=156。
したがって「30fps設定済み＝30fps取得済み」ではない。露出/USB/カメラfirmwareのどれが原因かは未確定。
v4l2-ctlは未導入だが、scripts/inspect_video.cのG系ioctlのみで照会済み。インストールは不要だった。
撮影設定の変更は今回の読み取り了承範囲では行っていない。

並行化後のGPU人工入力回帰: run-lcxa6t1z、30 policy/50 control、4 worker exit0、記録hash整合成功。
実入力との違いは従来どおり明示。単体全体・ローカルIPC33件成功、追加online試験15件成功。
次に必要なのは魚眼の撮影設定の一時変更を伴う30fps切り分けの了承。身体/グリッパ動作許可とは別。
実機動作、初期姿勢/衝突/停止・制御権、動的全身参照は未完了。hardware_ready=falseを維持。

## 2026-09-24 G1再起動後の接続確認

ユーザーがG1起動を通知。galleria経由の厳格host key検証付きSSH接続成功。
有線経路enp2s0/source192.168.123.99、G1 hostname unitree-g1-nx、kernel5.15.148-tegraを確認。
右gripper symlinkはttyUSB5。TCP6158/6159の待受なし。
この確認ではカメラ/シリアルを開かず、DDS購読や動作指令も実施していない。
MCU reset可能性を含む入力専用試験の了承をまとめて確認中。

## 2026-09-24 実入力用の統合起動・独立身体履歴経路を実装（G1未実行）

途中で承認不要なのに終了しない方針で継続。G1への接続/指令は行わず、入力専用実装まで進めた。
G1身体履歴を画像と独立してZMQ受信するservice/client、実測履歴から毎周期観測を更新するworkerを追加。
30Hz ACT/IKの絶対参照と50Hz身体観測を接続。h1の再積算なし、幅の指令送信なし。
run_online_loopと4 workerの起動/終了、G1入力sourceの配置/受信専用Cビルド/90秒上限を実装。
make online-recordはDEVICE_READ_ACK=1なしではSSH前に停止。**実機側の新経路は未実行**。
設定config/online-record.json、詳細docs/ONLINE_RECORD.md。ユーザー指定どおり実機取得は最後へ延期。

保存実身体388件/379区間でZMQ→観測worker→SONIC持続推論とバッチ計算の一致を確認。
最新artifacts/full-record/run-x2w0eq6u: 関節出力差0、観測回転最大差8.95e-18、両worker exit 0。
画像/LeRobotを別日の身体履歴と混ぜず、実測姿勢保持参照だけを比較している。

実入力用処理本体＋実モデル4 workerを人工入力で30秒検証。
最新artifacts/full-record/run-u1cqm5a6: ACT/IK900回・SONIC1500回、4 worker exit 0。
入力画像/身体snapshot反復と人工時刻であり、実測同時入力/物理応答/リアルタイム保証ではない。
GPU実行間隔15.387〜25.157ms、20ms±2ms外れ2件を明示。身体履歴の50Hz/重複/窓の重なりは別検査。
40ms以上の処理停止、20ms計算期限、100ms鮮度で拒否。物理的安全基準とは扱わない。

記録有効化後の中間試験でGC最大19ms・期限超過を検出し、失敗ログも保存。
大量の身体窓をGC対象heapに保持せず、hash付き個別記録へ変更。最新GC最大0.758ms。
閾値を広げてこの停止を通していない。別途、sourceの20ms±2msをhost schedulingへ誤適用していた検査は分離。
JPEGは内容hashで重複排除。回収はログ優先＋tar圧縮、パス/リンク/上書き/容量を検査して展開。
最新成果の展開38MB、回収archive約1.5MB。900画像時点/1500身体記録の全hash整合も検査成功。

次の実機依存工程は、利用可能になったG1のカメラ・右serial・身体状態の入力専用統合確認。
serial openのMCU reset可能性を含む読み取り了承が必要で、今は要求/実行しない。
動作指令/低レベル送信、動的参照の成立、初期肩角度・衝突・停止/制御権は未完了。
単体とローカルIPC試験も成功。旧実装・モデル・driver・OS設定は上書きしていない。

## 2026-09-24 子プロセス異常終了と診断ログ回収を補強

G1未接続のまま続行。JSON重複キー/非有限値/非objectとSONIC応答識別を厳格化。
応答異常時に子プロセスを閉じ、次要求への遅着応答混入を防止。実プロセス6試験成功。
全経路runnerはSSH期限超過でもdeployment.jsonとログを残し、時間制限付きで結果回収。
遠隔終了未確認を成功と扱わない。READMEの一律120秒表記を全経路180秒へ訂正。
check-offline成功（IPC2件は別試験）。GPU独立周期再試験も成功:
artifacts/full-record/run-oi4rpe04、ACT/IK30回・SONIC50回、全3 worker exit 0。
保存snapshot反復であり、実身体追従/オンライン入力/動的安定性は未検証。
実機承認要求なし、動作指令なし。
さらに周期試験を整数1〜30秒へ拡張し、30秒の保存snapshot反復試験に成功。
artifacts/full-record/run-wi6j6n4x: ACT/IK900回、SONIC1500回、全3 worker exit 0。
制御開始最大遅れ約0.982ms。短時間・単一入力の結果で、実時間保証/動的安定性の証明ではない。
make rate-record-check RATE_SECONDS=30で再現。ローカルIPC19試験も成功。

## 2026-09-24 設定集約・起動終了/異常試験・GPU内持続推論接続

G1同時入力取得はユーザー指示で最後へ延期。G1接続/指令/物理シミュレーションなし。
config/development.jsonにGPU/IK/モデル配置を集約、record_only以外拒否。ローカル時計の鮮度/連番/session gate追加。
保存出力のIPC故障注入6条件成功、実SONIC子プロセス不正要求3条件成功。通常子プロセスは全て終了確認。
SONICモデル1回ロードでZMQ IPC30要求完走、バッチとの差0。file/stdin以外のSDK通信なし。
さらにGPU内のACT3.12/IK3.10/SONIC C++を持続プロセスとして接続、保存画像2組で全経路成功。
初回ACT約260msをready前合成ウォームアップへ移し、全経路2件約28.51/24.02ms。周期保証ではない。
make full-record-checkで再現（画像再推論含む）。全3worker exit 0、出力幅は独立メタデータ。
成果artifacts/full-record/run-diyy8jud、詳細DEVELOPMENT_RUNBOOK.md。README/共有/終了手順を更新。
異周期用の絶対参照mailboxも追加し6試験成功。h1重複積算を避け、期限切れはfault保持。
make rate-record-checkでACT/IK30回とSONIC50回を独立周期実行し成功。保存snapshot反復を明示。
artifacts/full-record/run-tlvk3izg、3 worker exit 0、制御開始最大遅れ約0.225ms（短時間、実時間保証なし）。
未完了: 実入力の同時取得/周期検証・動的全身参照・初期姿勢/衝突/停止・実機送信。

## 2026-09-24 LeRobot画像再推論→TCP→本家IK→SONICの接続

旧WBCネットワークを使わない本家IK専用adapter追加。実測脚・腰で縮約モデルを構成しFK照合。
保存30 actionのIK最大位置誤差0.009692m/姿勢0.009987rad。肩制限外実測とseed投影を明示。
SONIC30件完走、さらに保存画像2組を固定ACTで再推論して同経路2件完走。幅は別欄で同値確認。
make sonic-tcp-checkで保存action以降を1コマンド再実行し成功。hardware_ready=falseを維持。
全画像＋各画像時点の実身体10フレームを保存するarchive-sonic-inputsを実装、実機未実行。
単体60件。G1接続/指令/物理シミュレーションなし。成果・再現・次取得条件はSONIC_TCP_PIPELINE.md。
時間同期した実入力は未取得（旧5Hz画像記録と別日の50Hz記録を混ぜていない）。

## 2026-09-24 保存履歴の比較自動化・上流回転演算照合

G1接続なし。固定本家C++の姿勢/重力関数と512組で2e-14以内の一致を確認。
履歴の直前actionゼロ固定/計算出力更新を各379窓比較。最大目標差0.608018/1.109443rad。
実出力に追従しない保存状態の開ループ比較であり、実機不安定性や原因確定を意味しない。
make sonic-replay STATE=...で準備/ビルド/2条件推論/回収/統計まで1コマンド化、実行成功。
結果artifacts/sonic-replay/run-bxnd4ew3。ONNX hash/入力SHA/コードSHA/ログ保存。
49単体成功。初期差の根本原因、全Gather同等性、LeRobot→有効全身参照は未完了。
実機承認要求なし、動作指令/シミュレーションなし。詳細SONIC_OBSERVATION.md。

## 2026-09-24 G1の8秒実履歴取得・SONIC送信なし推論

G1起動を受けgalleria経由SSH成功。受信専用LowStateを8秒取得し388フレーム回収。
20ms±2msの10フレーム窓379組、最大間隔21.629ms。配置/ビルド/取得区間9.387秒。
受信プロセス終了確認、電源不要をユーザーへ連絡。実機指令/モード変更/カメラ/serialなし。
実履歴379組を本家TRT encoder→decoderへ入力し全出力有限。実測固定参照、過去actionゼロ。
目標と実測の最大差0.608018rad、hardware_ready=false。閉ループ/LeRobot統合は未検証。
record_sonic_state/prepare_sonic_history_diagnostic追加、単体45件成功、diffチェック成功。
記録artifacts/sonic-state/sonic-state-McdQQD、詳細SONIC_OBSERVATION.md。

## 2026-09-24 観測組立とencoder→decoder連結診断

本家Gather*式を照合しmode0観測builderを追加。source hash/関節順/6D/履歴順を検査。
本家TRTInferenceEngine再利用のファイル専用C++で30件×2条件の連結推論成功。
trtexecと本家のengine形式差（64byte hash）を本家変換関数で解決。
5Hz保存記録の不足履歴は明示的合成。記録姿勢と未合格IK候補を試しただけで、
実入力50Hz・実時間・追従は未合格。最大目標差0.6533/0.9154rad。
単体41件成功。G1 SSH読取り確認はtimeoutで受信起動に至らず。実機指令なし。
詳細SONIC_OBSERVATION.md。現在の不足は高頻度実状態と有効な全身参照。

## 2026-09-24 SONIC C++ビルド・TensorRT単体推論成功

make sonic-build用runnerを追加し、新規GPUディレクトリで本家C++を無改変ビルド成功。
SDKライブラリ3点は固定LFS hash検証。実機制御バイナリは起動せず。
公式low_latencyモデルをrevision6733128で固定、encoder/decoder/config/license取得・hash検証。
TensorRT engine構築と合成入力推論が双方成功、64/29出力の有限値確認。
ログ回収済み、sources.lock/README更新、既存36テスト成功。
これは実入力統合・動作検証ではない。次は参照/履歴観測の本家実装再利用。
詳細SONIC_BUILD.md。実機接続、シミュレーション、追加pip/aptなし。

## 2026-09-24 galleria復旧・SONIC wire形式の実装

SSH復旧。CUDA12.8.93、TensorRT10.13.3.9、ORT C++1.16.3、主要ビルド依存を確認。
固定上流の必要ソースをLFS展開なしで取得成功。旧vendor HEAD/ソース変更なし。
SONIC公式packerと関節配列をhash確認して使う送信機能なしのadapterを追加。
v1ヘッダ1280byte、全29関節順変換、wxyz/frame index/有限値を単体検証。
doctorをTensorRTのsymbolic defineとPATH外nvccに対応。全36テスト成功。
実機接続/送信、シミュレーション、GPU環境変更なし。SONICビルド/実推論はまだ未完了。

## 2026-09-24 SONIC移行開始（シミュレーションなし）

- ユーザー承認の新計画に合わせAGENTSを更新。旧Decoupled検証は保存。
- 同じ固定コミットのtreeにSONICが存在することを確認し、追加ソース取得を開始。
- 公式VLAの78次元と既存ACT10次元は非互換。関節参照v1を利用する候補を記録。
  全29関節参照/IsaacLab順変換が必要で、直接接続の成立は未検証。
- READMEを簡潔な現状/操作/制約中心へ変更。旧全文はREADME_LEGACY.mdへ保存。
- makeの既定をヘルプにし、doctor/check-offlineを追加。診断・単体30件成功。
  既存gripperテストの-I時importを修正。実機/カメラ/serial/シミュレーション実行なし。
- galleriaへの読み取りSSHはNo route to host。GPU依存確認・ビルドは未実施。
- ソース取得の初回自動審査はタイムアウト、許可された再試行を1回実施。
  再試行は取得が長時間完了しなかったため中断（exit 130）。上流HEADは不変。
  SONIC追加ソースは未配置、取得をバックグラウンドに残していない。
  詳細/今後の条件はSONIC_MIGRATION.md。環境完成・SONIC実推論成功とは扱わない。

## 2026-09-18 初期目標差の送信なし切り分け

保存済み実入力再生に下半身の本家有効/無効、初期TCP固定、関節別差分統計を追加。
LeRobot目標を外しても左肩yawの最大差1.624radは残り、IK初期化側の影響を確認。
実測近傍の制限内IK seed実験で最大IK誤差0.410m→0.0257m、最大関節差0.577radまで
縮小するが、0.02m基準は未達。初回左足首pitch差0.984radはBalance即時有効側で発生。
本家/シミュレーション既定動作は変更なし。実機接続/指令なし、リモコン追加なし。
既存ControlGuard10件、WbcState7件テスト成功。詳細WBC_STARTUP_REVIEW.md。

## 2026-09-18 支持状態の確認・リモコン統合は対象外

G1は吊り下げで足接地、リモコンありとユーザー確認。支持なし立位という解釈を訂正。
ユーザー指示でリモコンをソフトウェアに含めない。今回追加した受信拡張と未実行の
テストfixtureのみ取り下げ、既存受信機能を維持。遠隔配置・実機指令はなし。
停止実効性が検証済みになったわけではない。開始/終了処理と初期目標差の検証へ戻る。

## 2026-09-18 本家起動処理の確認・IK seedの切り分け

本家BodyIKSolverの計算seedを維持する選択肢を追加し、実測値と計算初期値を分離。
galleriaで実入力30件→WBC出力30件まで計算成功。IK最大0.410499m、最終右0.022319mで
0.02m基準には未達、passed=false。既存失敗記録も保持、実機指令なし。
本家ReleaseMode/LowCmd開始、初回2秒の上半身補間、終了処理をソースで確認。
終了だけで実機安全停止/モード復帰を保証しないことを記録。
詳細WBC_STARTUP_REVIEW.md。既存WbcState7テスト成功、simulation既定seedは変更なし。
既存PIKA付きWBCの12秒シミュレーションもpassed=trueで回帰確認。

## 2026-09-18 実入力統合成功・WBC初期姿勢条件を特定

既存PikaGripperの受信専用ライフサイクル＋旧ROS幅式を再利用して、画像/身体/グリッパを
有線ZMQに統合。make input-shadowで仮幅を除いたLeRobot実推論30件成功。
通信込みp95 34.288ms、推論7.596ms。グリッパseq30種類と実入力の使用を確認。
幅変換4テスト、既存WbcStateテスト、構文/diff検査を実施。
実記録からのWBC送信なし再生はtiger/galleriaとも本家肩ロール制限で初期化停止、出力0。
制限は変更せず停止理由を保存。身体姿勢・制御権は変更しない。
詳細REAL_INPUT_INTEGRATION.md、記録artifacts/state-shadow/state-shadow-Pysyga/。

## 2026-09-18 右グリッパ拡大テスト

ユーザーの追加許可で右0.2→0.4→0.6rad、3秒待機、段階的に0radへ戻すテスト成功。
頂点実測0.5923rad、戻し0.0225rad、disable確認後0.0061rad/Status0、port close済み。
914状態と結果をresult-largerへ保存。既存ドライバ無変更、身体/腕/左の指令なし。
受信再同期警告10回は残る。詳細RIGHT_GRIPPER_MOTION.md。

## 2026-09-18 右PIKA単体の実機開閉成功

ユーザー明示許可で、固定LeRobotのPikaGripperを無変更利用し0.15rad→0radの1往復。
実測0.126/0.0152rad、許容差0.025rad以内。最後にStatus0（無効）とport close確認。
191状態、右のみenable/位置/disable送信。身体・腕・左・zero/電流設定は操作なし。
pyserial3.5は隔離wheelからimport、既存環境変更なし。結果と使用ソースを回収。
受信再同期警告4回あり、通信品質問題解消とは扱わない。詳細RIGHT_GRIPPER_MOTION.md。

## 2026-09-18 既存グリッパ実装の再利用方針に訂正

ユーザー指摘を受け独自保護の追加を止め、固定LeRobotと既存PIKA ROSを調査。
LeRobot受信は不正JSON無視・角度電流をそのまま保存。ROSは0〜1.67へクリップ/error付き、
既存リンク機構式で幅に換算する。前回の厳格なpassed判定は診断独自であることを明記。
必要最小差分は受信専用ライフサイクルと既存幅変換の接続。未移植、実機アクセスなし。
詳細GRIPPER_REUSE_REVIEW.md。

## 2026-09-18 右グリッパ5秒受信実施

ユーザーの接続リセット了承後、右のみO_RDONLY/raw460800で5秒受信。
151281byte、JSON832件、Position取得成功。アプリUART書込/動作指令0。
不正JSON1件（NUL混入）、角度2.0/電流-1080385602が2件ありpassed=false。
生データにも異常が存在。原因は未特定、実測幅・LeRobot入力への採用なし。
結果をG1/GPU/tigerに保存し、終了後ポート使用プロセス未検出。
受信/解析コードと6単体テスト、診断角度範囲検査を追加。詳細GRIPPER_STATE_RX.md。

## 2026-09-18 グリッパ状態取得の事前調査

固定LeRobot commit79edf6a95948d0f0d75df1d54d0a5aad305f75a8のpika_gripper.pyを再確認。
460800 baudの連続JSON状態出力だが、既存connectはopen時MCUリセットの注意書き、
disconnectはdisable送信あり。そのクラスは受信専用には使用しない。
G1のTCP状態配信6101は待受なし。fuserはttyUSB4/5使用者を表示しなかった
（一般ユーザーによる確認であり、全プロセスの非使用を保証しない）。
G1 Python3のserialモジュールは未導入。標準ライブラリtermiosによる受信なら追加pip不要。
ただし標準ライブラリでもTTY open/close時のDTR/RTS変化は否定できないため、
保持物なし・指先周囲安全・接続リセット許可をユーザーに確認してから短時間受信へ進む。
この作業ではポートopen・UART送信・実機動作指令なし。受信器の実機試験は未実施。

## 2026-09-18 CH341ロード・udev反映確認

ユーザーによるsudoインストール成功後、galleria経由で読み取り検証。
1-2.1.3.4:1.0と1-2.1.4.4.4:1.0のdriverが双方ch341。
ttyUSB4/5はunitree:dialout/0660。右専用リンク/dev/pika/right/gripperはttyUSB5を指す。
右のModemManager除外2属性とunitreeによるread/write権限を確認。
シリアルopen/グリッパ接続関数/動作指令なし。再起動後の自動ロードと実通信は未検証。

## 2026-09-18 CH341復旧準備（sudo操作待ち）

旧tigerのsensor_serial.rules/魚眼ruleと既存setup_device.pyを確認。
ttyUSB50共通リンクは左右で競合するため流用せず、G1側に旧PIKA ruleがないことも確認。
Linux stable v5.15.148 commit6139f2a02fe0ac7a08389b4eb786e0c659039dddのCH341を
無変更でG1ユーザー領域にビルド。7522 alias、tegra/aarch64 vermagic、依存usbserial確認。
成果: /home/unitree/g1-pika-ch341-xaK9Y1/ch341/。固定ソース・ライセンス・hash・
競合しない右専用udev名・インストールスクリプトをassets/drivers/ch341へ保存。
sudo -nはパスワード要求。インストール/モジュールロード/udev反映はまだ実施していない。
ユーザー自身のG1端末でsudo sh .../install.shを実行する必要あり。
ロードはUART初期化を伴うためグリッパ安全確保を案内。実機動作指令・シリアルopenなし。

## 2026-09-18 SSD換装後の受信・画像・GPU推論復旧

`make state-shadow`を実装し、状態5秒4,619件・画像/状態30組の有線ZMQ転送とLeRobot
推論、正常終了、結果回収まで実行成功。通信込みp95 34.116ms、GPU推論7.500ms。
G1の既存ライブラリを使用し追加インストールなし。DDS生成C/Hを固定hash付きで保存。
旧eth0/ホスト鍵ハードコードを新設定へ切替。魚眼2台は右D405とUSBハブpeerを照合して選択。
Python構文/diff・Cビルド・不正IF拒否を検証。失敗3段階も隠さず記録。
G1のPIKA USB Serial 2台は未bind、ch341モジュールなし、headers既存。
ユーザーによる別途インストールが必要。実機動作指令・シリアルopen・サービス変更なし。
詳細: [STATE_SHADOW_RESTORE.md](STATE_SHADOW_RESTORE.md)。

## 2026-09-14 RGB-only新規ACT学習・再読込

ユーザーの継続指示により、既存モデル/データを保存したまま新規CPU学習を実施。

- LeRobot ACT（小型・VAEなし・事前学習backboneなし）、RGB2系統128×96、相対state/action10D。
- 学習episode 0〜3の64件、検証episode 4〜5の32件をseed固定で抽出。深度はモデルへ渡さない。
- 幅h1不一致は補正せず除外。選択/除外の全frame indexを保存。
- 統計は学習64件のみ。共通画像処理・モデル・processor・キャッシュ・学習スクリプトを保存。
- 100ステップ、500ステップとも完走。サンプルhashと先頭100損失が完全一致。
- モデル/processor再読込後に96予測の完全一致を確認。分割・統計・変換・ハッシュ検査も成功。
- 検証幅MAEは100→500で20.933→3.063mm。ただし現在幅保持2.207mmより悪く、負値7/32。
- 検証並進誤差は2.514mm（無動作2.314mm）。実機用に十分な性能ではない。
- キャッシュ入力からの検証推論p95は34.43ms。画像読込・縮小・WBCを含む周期は未検証。
- 開発初回のshard漏れで検証16件になったrunは無効化し、全shard読込/件数拒否を追加して再実行。
- `make train-rgb-smoke`、`make eval-rgb-smoke`、`make check-rgb-smoke` を追加。
- 元データ・既存モデル・WBC経路は変更なし。外部GPUジョブ・実機送信なし。

次は学習データ量と学習量を拡大し、検証用とは別の最終評価episodeも確保する。
本学習用のGPU PCが利用できるかユーザーへ確認中。
詳細: [RGB_TRAINING.md](RGB_TRAINING.md)。

## 2026-09-14 入力・正規化の原因切り分け

- 全action/state統計のfloat32一致により、モデルと50ep final版の対応を確認（学習履歴の証明ではない）。
- episode 0の254行のaction/state/深度bytesは現在49ep v3版と完全一致。
  RGBと深度の読込値、return_uint8設定差の吸収も代表3点で一致。
- 深度metadataにis_depth_map/depth_unitがなく、深度がImageNet統計の対象に入る。
  checkpointの3ch画像統計に生深度1chを適用するとbroadcastされ、先頭の正規化値最大254614。
- 深度の保存単位を前回mmと断定した記述を訂正。設定はmmだがmetadata欠落で変換されず、単位未検証。
- PIL RGB化＋/255の診断を16点で実施。対応する元入力より幅MAEが14.251→41.030mmへ悪化。
  この変換を正式修正として採用せず、既定処理と元データを維持。
- `make policy-input-check` を追加。元254フレーム結果は上書きせず保存。
- 学習PCの実際のLeRobot commit・ローカル差分・ログが不明で、学習時処理を確定できない。
  入力/統計の不整合と、モデルの不良出力の主原因が同じかは未確定。

次は学習時コードの確認が必要。実機送信・新規学習なし。
詳細: [POLICY_EVAL.md](POLICY_EVAL.md)。

## 2026-09-14 LeRobot CPUオフライン推論

ユーザーが `zero_relative_50ep_act_h1_v2` の使用を承認。中断後の「つづき」から実装再開。

- 新規 `.venv-policy`（Python3.12.13）を作成。既存conda環境・WBC venvは変更なし。
- ユーザー承認のもとCPU依存をダウンロード。LeRobotは固定commitをvendorへ複製。
- `requirements-policy.lock` に依存を固定、実行時バージョン検査を追加。pip check成功。
- 保存RGB2系統・深度mm・相対stateを用い、checkpointの正規化/逆正規化で実推論。
- Pythonネットワーク監査フック＋HFオフライン設定で全254フレーム完了。
- 並進L2誤差平均1.575mm、無動作1.566mm。今回のepisodeでは改善を確認できない。
- 負のグリッパ幅76/254、幅MAE13.785mm。推論処理p95 1058.87msで30Hzに未達。
- 全frame indexの連続性、後続strictロードでの先頭予測の完全一致を確認。
- 教師テスト6件・既存Balance10秒・WBC依存確認も成功。
- `make policy-eval`、短縮版 `make policy-eval POLICY_STEPS=4`、`make setup-policy` を追加。
  別PCでのクリーンsetupは未検証。推論結果はartifacts、要約・ハッシュはdocsに記録。

推論完了と実機適合を区別する。WBCへのpolicy接続・実機通信は未実施。
次は学習データとの対応、深度を含む前処理、正規化と他episodeの評価を調査する。
CPU周期の問題も残るため、直ちに実機へ進める段階ではない。
詳細: [POLICY_EVAL.md](POLICY_EVAL.md)。

## 2026-09-14 推論前のチェックポイント事前検査

- `make policy-check` を追加。標準ライブラリだけで設定・入力形状・重みファイルの存在、
  SHA-256、safetensorsヘッダとデータ範囲を読み取り検査する。推論・通信は実行しない。
- `zero_relative_50ep_act_h1_v2` はACT chunk_size=1 / n_action_steps=1、出力10D。
  現在のデータにstate・RGB2系統・depthの入力形状が一致し、静的検査に合格。
- `replace_tape_g1_pika_relative_h1_v2_act` は実ファイル上ではchunk_size=100 / n_action_steps=100。
  初期h1アダプタの条件を満たさず、検査が非ゼロ終了することを確認。
  複数step出力一般の無効性を意味せず、今回はchunkの意味を未検証のまま接続しないという制約。
- 推奨候補は前者。ただし学習データ名は `zero_relative_50ep` であり、現在の49ep版との
  同一性・回転並び・学習処理の対応を確認済みとは扱わない。
- 推論はモデル選択の回答待ち。環境準備・モデルロードは未実施。
  既存モデル/データ/環境に変更なし。実機指令なし。

起動: `make policy-check`。別モデルは `POLICY=/path/to/pretrained_model` を指定。
結果は `artifacts/policy-check-<モデル名>.json`。

## 2026-09-14 教師GUI合格・データ契約の訂正

- ユーザーからteacher-viewの30秒完走・合格ログを受領。実時間79.25秒、WBC p95 9.05ms。
- 前回「並進約1cmのずれ」とした診断は誤り。stateは毎フレーム現在TCPに対する単位姿勢で、
  絶対姿勢のように隣接差分を計算してはいけない。converterと全49エピソード10,881フレームで確認。
- exportとシミュレーション結果の診断を修正。元データ・保存action・再生軌道は変更なし。
- 全件監査 `make dataset-check`、再利用可能な相対state生成器、回帰テストを追加。
- テスト6件と教師30秒再生に合格。254フレームのactionが変更前と完全一致し、
  TCP誤差・移動・胴体高さ・傾斜の結果も変更前と一致することを確認。
- グリッパ幅のh1対応には145件の不一致（最大78.96mm）が残る。episode 0はframe 69の3.331mm。
  原因未同定。爪固定の試験と区別し、開閉・把持へは進めない。
- 指定LeRobotはPython >=3.12、WBCは3.10。推論用別環境が必要。
  既存condaはdatasetsの依存制約に不一致があり、そのまま固定環境とは扱わない。
- 学習済みモデルが複数存在するため、使用するモデルをユーザーへ確認。
  モデル推論・新規環境インストール・実機通信はまだ行っていない。

詳細と監査結果: [TEACHER_REPLAY.md](TEACHER_REPLAY.md)。

## 2026-09-14 教師actionとWBCの接続

ユーザーと外観の精密再現は現段階で必須でないと整理し、代替モデルの制限を明記して教師再生へ進んだ。
カメラ・金具・配線の質量/慣性/衝突外形は未計測のままで、実機適合の判断には使わない。

- 既存LeRobot v3データのepisode 0（254フレーム）をハッシュ付きJSONに抽出。画像は不使用。
- 回転6Dの項目名と数値の並び不一致を確認。列順を明示し、直交性を検査。
- ローカル相対10D actionから右TCP目標を生成。30 Hzを一度だけ積分して50 Hzへ補間。
- 並進量・再生速度は1倍。初期TCPに再配置し、姿勢も追従。左腕・爪は固定。
- 30秒試験合格。右TCP移動8.40cm、最大位置誤差3.40cm、最大姿勢誤差0.116rad、警告0。
- 単体テスト4件成功。従来Balance・PIKA往復試験、30姿勢のモデル整合、依存確認も成功。
- 教師再生に不足する12秒指定が実行前に拒否されることを確認。
- `make teacher-view` / `make teacher` / `make check-teacher` を追加。
- 当時は状態の隣接差分とactionの残差（並進最大10.36mm）を報告したが、上記の通り比較方法が誤りだった。
  教師action経路の成立と、データ品質・元観測軌道の完全再現は区別する。

詳細: [TEACHER_REPLAY.md](TEACHER_REPLAY.md)。ポリシー推論は未接続。実機送信・外部pushなし。

## センサー付き公開モデルの調査（2026-09-14）

公式 `agilexrobotics/agx_arm_sim` に別のPIKA名URDFを確認:
https://github.com/agilexrobotics/agx_arm_sim/blob/master/agx_arm_description/urdf/pika_gripper_description.urdf
グリッパ本体＋左右指の3リンクで、本体0.18972kg、各指0.033674kg。
今回移植したPiper共通の3メッシュとは別のファイル名を参照している。
このURDFにはRealSense/魚眼カメラの独立したリンクやカメラ定義がない。
ただしメッシュ内部に何が含まれるかは未確認であり、完成組立CADの不存在は断定しない。

公式SDKにはRealSenseと魚眼カメラの両方を扱うコードがある:
https://github.com/agilexrobotics/pika_sdk/blob/master/pika/gripper.py
ドライバの存在と、カメラ込みの組立CAD/URDFの公開は別に扱う。
今回調べた公式公開物からはセンサー込み完成版URDFを確認できなかった。
調査のみで、モデル差し替えやメーカーへの問い合わせ送信は行っていない。

## 最新の訂正：グリッパ形状の同定（2026-09-14）

ユーザーの「実物PIKAと形状が違う」という指摘を受け、移植STLとPiper側STLを照合。
3点すべてのSHA-256が一致。本体質量・慣性もPiper URDFの値と一致した。
旧PIKA用定義を実物PIKAの形状と扱った説明を訂正する。
過去の合格結果は代替グリッパモデルでのシミュレーション確認であり、実物PIKAの適合検証ではない。
当初はCAD差し替えを優先したが、その後のユーザーとの整理により、代替モデルと明記して教師接続を先行する。
今回の診断では形状や制御コードを変更せず、出典と検証範囲の説明を訂正した。

## 2026-09-14 初期構築

完了:

- OS・CPU・RAM・ディスク・GPU・Git/LFS・Python・Docker/Composeを読み取りで確認。
- `g1-pika/` にmainブランチのローカルGitリポジトリを初期化。既存リポジトリは変更なし。
- 指定PIKAブランチ、LeRobot、公式Decoupled WBCのSHAを `sources.lock.json` に記録。
- Decoupled WBCをvendorに取得。大型のSONIC/MotionBricksは導入せず。
- 専用Python 3.10仮想環境とCPUシミュレーション依存を導入・固定。
- CPU上でBalance ONNXを用いた10秒間の自由基底MuJoCo試験に成功。
- `python -I -m pip check`：依存不整合なし。
- 最終 `make check` 成功。同じ姿勢・変位結果を再現。setupスクリプトの構文確認、固定依存のローカル照合も成功。
- 初期実装・引き継ぎ・計測記録をローカルの初期コミットに保存。リモート作成・pushなし。

結果: [初回計測JSON](balance-baseline-2026-09-14.json)。
物理200Hz、推論50Hz。胴体高さ最小0.743m、最大傾斜0.0592rad（約3.4°）、
最大水平移動0.110m、推論p95約0.322ms、MuJoCo警告0。
10秒はシミュレーション時間。画面なしの実計算時間は約0.65秒（モデルロード時間除外）。

この試験はWBCの下半身Balanceモデル＋腕0保持の最小動力学チェック。
上半身IKを含む公式全体ループ、PIKA装着、教師軌道、ポリシー接続は未完了。
歩行モデルはハッシュを記録しただけで動作未検証。
実機通信・指令送信なし。Dockerコンテナ起動なし。GUI未確認。

## 2026-09-14 GUI確認と終了判定の修正

ユーザーからG1が表示され、立ち続けていたとの報告あり。
ログは実時間33.20秒に対してシミュレーション11.10秒。
胴体高さ最小0.743m、最大傾斜0.0592rad、水平移動最大0.110m、MuJoCo警告0。
旧コードは指定30秒を完走していないことを `passed: false` / exit 1 としていた。
記録された値と終了分岐から、viewerの終了検出による未完了と判断できる。
ユーザーが手動で閉じたか、別の理由でviewerが閉じたかは未確認。
GLFWのWaylandウィンドウ位置警告は出ているが、表示・物理計算は継続している。

修正: 完了、表示終了による中断、試験失敗をstatusで区別。
中断は合格にはせず、正常終了扱いとする。要求時間と終了理由もJSONに残す。
GUI同期を物理200Hzから最大約30Hzへ減らす。速度改善は実GUIで未計測。
検証: [画面なし30秒試験](balance-30s-2026-09-14.json)に合格、MuJoCo警告0。
viewerを模したテストで開始直後・2ステップ後の終了が中断扱いになることと、
高さの閾値違反が引き続き失敗・exit 1になることを確認した。

## 次に行う作業

教師軌道をPIKA TCP目標へ接続し、到達性・追従誤差・座標契約を評価する。
その後、指定LeRobotの学習・推論へ接続する。現在の試験目標はまだポリシーの出力ではない。

## 2026-09-14 上半身IK＋公式WBCの統合

- `scripts/wbc_controller.py` で固定コミットの公式クラスを直接接続。
  BodyIKSolver → InterpolationPolicy → G1DecoupledWholeBodyPolicy（下半身G1GearWbcPolicy）→ MuJoCo。
- ONNX読み込みだけCPU provider・1スレッドを明示する派生クラスを使用。
  観測生成、履歴、action生成・合成、IK本体は上流コードを使用。
- Pinocchioの関節並びとMuJoCoの関節名を照合。初期左右手首のFKも行列で照合。
- IKの肩クリアランス制限に合わせ初期肩rollを左右±0.2radとした。
  腰は下半身制御に属し、IKは左右腕14関節だけを解く。
- 目標: pelvis基準、右手首を前6cm・上4cmへ10秒周期で往復。左手首は基準位置を保持。
  最初の2秒は静止。胴体は自由基底であり、初期化後の姿勢上書きは行わない。
- 公式RobotModelの腕重力補償を有効化。世界重力を現在のpelvis座標へ変換して使用。
  重力補償なしの試験では最大位置誤差5.25cm・姿勢誤差0.318radで設定閾値を超えた。
  閾値を緩めず、重力補償後に合格した。
- Python依存を `requirements-wbc.lock` に完全なバージョン一覧として保存。
  `make setup-wbc` / `make wbc` / `make wbc-view` を追加。

検証: [30秒試験結果](wbc-30s-2026-09-14.json)。
右手首移動最大7.06cm、左右手首位置誤差最大2.295cm、姿勢誤差最大0.112rad。
IKの位置誤差最大0.057mm。胴体高さ最小0.744m、傾斜最大0.0675rad、MuJoCo警告0。
IK＋補間＋下半身推論のp95約3.03ms（物理ステップや重力補償の時間はこの値に含まない）。
30秒のシミュレーションは画面なしで約5.75秒（初期化除外）。
`make check`で既存Balance試験と依存整合も確認済み。
負の検証として腕の指令だけを固定すると、立位を維持しても追従誤差7.63cmで不合格になることを確認。
同試験中にPythonのsocket接続・bind・sendto・名前解決を禁止する監査フックを入れ、
WBC初期化から12秒シミュレーション終了までこれらの呼出しがないことも確認した。

制限: ROS/公式G1Envの全起動経路は未実行。教師軌道・PIKA・学習ポリシーは未接続。
この合格は指定した小さい往復動作の初期チェックであり、精密作業や外乱耐性を保証しない。
実機SDK、ROS、DDS、シリアル送信は起動していない。

## 2026-09-14 PIKA付きモデルの移植・検証

ユーザーからPIKAなしWBCのGUI30秒完走を確認済み（実時間40.78秒、passed=true）。
ユーザーの最新希望は、途中で区切らず実装から実行コマンドまで進めること。AGENTSにも反映。

- 固定PIKAコミットからジェネレータとSTL3点を `assets/pika/` へ移植。
  元の未コミット変更は保存。バイト列照合・ハッシュ・出典・ライセンス宣言を記録。
- 純正の掌・指を除去して左右PIKAへ置換。片側206.0255gは旧URDF由来の未実測値。
- 爪は関節値0で固定。PIKAの衝突形状を有効化し、G1の29関節と自由基底を維持。
- IKの目標を `right_pika_tcp` へ切替。取付・TCP・トラッカー軸は元の定義を継承。
- G1の元URDFとMJCF間の腰・肩の原点差、固定部品の慣性集約差を生成モデル側で統一。
  元のWBCコード・アセットは変更していない。
- 30姿勢で両エンジンのTCPの位置・回転、全関節重力トルクを照合。
  総質量はともに33.4131939704kg。誤差は浮動小数点丸め程度。
- 30秒の動力学試験に合格。右TCP移動6.83cm、位置追従誤差最大3.40cm、
  姿勢誤差最大0.0841rad、胴体高さ最小0.744m、MuJoCo警告0。
- OSMesaでPIKA近接画像を描画して確認。対話GUIは未確認。
- `make check` の既存Balance試験と依存確認も成功。

起動: `make pika-view`。画面なし: `make pika`。モデル整合＋動作試験: `make check-pika`。
依存追加なし。`make setup-wbc` の環境をそのまま使用する。
計測: [30秒結果](pika-30s-2026-09-14.json)、[モデル整合結果](pika-model-check-2026-09-14.json)。
詳細と制限: [PIKA_MODEL.md](PIKA_MODEL.md)。

未完了: 取付金具・配線・センサーを含む実測質量、左側取付の実機照合、
開閉・把持、教師軌道、LeRobot接続。今回の動作合格を実機検証済みとは扱わない。
実機への指令送信なし。

## 環境上の注意

### 2026-09-14 GPU PCへのSSH接続準備

- ユーザーの承認により、このPCに接続専用Ed25519鍵を作成。
  保存先はリポジトリ外の `/home/developer/.ssh/EXAMPLE_GPU_KEY`。
  自動接続用にパスフレーズなし。既存鍵・SSH設定は変更していない。
- ユーザーによる公開鍵登録後、専用鍵でのSSH接続に成功。
  GPU PCはUbuntu 22.04.5、kernel 6.8.0-138-generic、RAM 94GiB、
  ルートディスク空き268GiB。Python 3.10.12、Git 2.34.1、Docker実行ファイルあり。
  `/home/gpu-user/miniforge3` と既存の `sk_dev` 内datasets/lerobot等を確認。
  既存環境・データの変更やインストールは行っていない。
- `nvidia-smi` は `Driver/library version mismatch` で失敗。
  読み込み済みNVIDIA kernel moduleは580.173.02、インストール済み
  NVMLライブラリは580.178.04。不整合を確認した。
  OSも再起動を要求（reboot-required.pkgsにはlibc6）。
  更新後の未再起動が原因候補だが、解消は再起動後の確認が必要。
  GPUはPCI ID 10de:2d04を確認、製品名・VRAM・CUDA動作は未確認。
  その後ユーザーが再起動し、SSHで不整合解消を確認した（下記）。
- パスワード・秘密鍵内容はこの記録やリポジトリに保存しない。
  次は鍵認証による読み取り確認。実機への指令送信は引き続き禁止。

### 2026-09-14 再起動後のGPU・CUDA確認

- 専用鍵で再接続成功。RTX 5060 Ti、VRAM 16311MiB、driver 580.178.04。
  `nvidia-smi` 正常、確認時GPU使用率0%、表示系のみ72MiB使用。
  この表示は確認時点のもので、将来のGPU空きを保証しない。
- 既存 `/home/gpu-user/sk_dev/lerobot` はソースではなくPython仮想環境。
  Python 3.12.12、torch 2.11.0+cu128、torchvision 0.26.0+cu128、
  lerobot 0.6.2、datasets 4.8.5。
  この環境で32x32行列のCUDA積・逆伝播・同期と結果/勾配の検査に成功。
  compute capability (12,0)、PyTorch runtime CUDA 12.8。
  nvidia-smiのCUDA 13.0表示とは区別する。ACTのGPU学習はまだ未検証。
- Miniforgeのpika_g1_ik環境はPython 3.12.13、torch 2.11.0、
  torchvision 0.26.0、lerobot 0.6.1、datasets 4.8.5。既存環境は変更しない。
- 既存ソース `/home/gpu-user/sk_dev/src/lerobot` は
  d451fe4f1f1b00a812f95aa9534389b5e42ab155、未追跡src/lerobot/original/あり。
  指定79edf6a9ではないため、今回用に別の固定ソース/環境を準備する必要がある。
- GPU PCのzero_relative_50epはメタデータ上50 episodes / 11091 frames / 30fps。
  ローカルRGB試験のvalid49とは別扱い。全データ同一性は未確認。
- 次: 新規の専用作業フォルダ・GPU依存lockを準備し、正しいデータを照合/配置、
  LeRobot ACTのGPU短時間試験から進める。既存データやソースの変更、
  パッケージ導入、本学習、実機への指令送信は今回行っていない。

### 2026-09-14 専用GPU環境・LeRobot ACT短時間試験

- 上記の環境確認後、ユーザーの「次」で専用環境構築へ進んだ。
  `/home/gpu-user/g1-pika-training` にPython 3.12.13の独立venvを作成。
  既存環境は変更せず、torch 2.10.0+cu128 / torchvision 0.25.0+cu128を導入。
  全依存をrequirements-gpu.lockに記録、pip check合格。
- LeRobot 79edf6a9を転送してHEAD・差分確認。
  CPU受理済みrun-i507ue81の学習64・検証32フレームキャッシュを転送し、
  SHA256一致を確認。49エピソード全体の転送ではない。
- 新規GPUスクリプトで100ステップ学習。有限損失/勾配、保存、strict再読込後の
  全96予測完全一致を確認。学習部分2.007秒、キャッシュ推論p95 4.747ms。
  検証グリッパMAE18.193mmは現在幅保持2.207mmより悪く、タスク成功ではない。
- 実行時ネットワーク禁止。モデル・processor・出典・コード/依存hashを保存。
  run-53_xcoexをローカルartifactsにもバックアップ。
  make gpu-smoke（短時間の再実行）、make gpu-report（読み取り）を追加。
  make gpu-report動作確認、既存check-rgb-smokeとdiff --checkも合格。
- 次はvalid49全データ照合/転送、学習・検証・テスト分割と本学習用の
  再開可能なジョブ実装。本学習・実機指令送信はまだ行っていない。
  詳細: [GPU_TRAINING.md](GPU_TRAINING.md)。

### 2026-09-14 valid49転送・固定分割・再開ジョブ検証

- valid49全17ファイル、965670614 bytesを専用GPUフォルダのdatasets/valid49へコピー。
  全パス・サイズ・SHA256を照合して一致。既存データは変更していない。
  ファイル記録: assets/datasets/valid49-files.json。
- 候補分割はepisode 0..38学習、39..43検証、44..48テスト。
  グリッパh1不一致145行を除外し、採用数8693/1022/1021。
  全採用/除外frame indexをassets/datasets/valid49-split.jsonに記録。
  GPU PC側でも元データから再計算してバイト一致。セッション独立性は未確認。
- train_gpu_smokeにoptimizer・CPU/CUDA RNG・step・損失・modelのcheckpointを追加。
  別runへの再開、入力/コード/依存の同一性確認、weights_only読込。
- gpu_jobは別セッションsupervisor、ログ/状態保存、supervisor経由の排他ロック。
  SSH起動接続終了後のジョブ継続を確認。job-40hv11d8はexit 0。
  20連続と10+再開10で損失・モデル・96予測・optimizer・乱数が完全一致。
  結果: docs/gpu-resume-2026-09-14.json。
- ローカル負のテスト3件・構文検査・diff --check合格。
- ここまでのGPU学習は96フレームの小型試験のみ。全データ用トレーナーと本学習は未実施。
  次は固定splitに従うRGB読込・学習統計・評価・再開を本学習ループへ接続する。
  実機指令は引き続き送信していない。

### 2026-09-14 全学習データRGB基準実験

- 固定LeRobotDataset/pyavと共通rgb_inputで、train8693/validation1022フレームを読込。
  全ファイルhash・episode/frame対応を確認。test画像は未使用。
- 小型ACTのままbatch16、1000stepsを実行。シャッフル一巡方式で学習全8693件を使用。
  延べ15989サンプル。train-only統計の保存値を再計算して完全一致確認。
- job-iccbwufmは約274秒で成功、学習部分27.736秒。
  1278フレームのstrict再読込予測一致、GPU推論p95 4.825ms（縮小済みキャッシュ入力）。
- 500stepから再開して1000へ進んだ結果も、損失・モデル・予測・optimizer・
  サンプラー/CPU/CUDA RNGが連続1000stepと完全一致。
- 検証位置誤差2.066mm（無動作2.115mm）、回転0.010942rad（無動作0.010474rad）、
  幅3.030mm（現在幅保持1.767mm）。保持基準を総合的に上回れず実機使用不可。
- 初回run-79a2ge2g、再開run-6tprwbow。詳細はGPU_TRAINING.md。
  ローカル負のテスト4件・構文検査・diff --check合格。
- 次は検証splitで学習量/モデル設定を比較する。最終test・実機はまだ使わない。

### 2026-09-14 学習量3000/10000比較・入力依存診断・変換境界

- 学習量だけを変えた事前指定比較を実行。job-hklhlkpcは約315秒で成功。
  最初の1000損失は既存基準実験と完全一致。単一seed、test未使用。
- 3000stepは位置2.045mm/幅2.087mm、10000stepは位置2.096mm/幅2.042mm。
  幅保持1.767mmを下回れず、負の幅が4/87件。両モデルとも不採用。
  10000stepの回転誤差も無動作より悪く、学習量増加だけでは解消しない。
- 画像ペアのシャッフルで幅誤差が約38mmへ増加。画像無視ではない。
  現在幅シャッフルは約6mm。自然な入力対応を壊した感度診断であり因果的証明ではない。
- run-bdq1hvyr/1r5b65hh、比較comparison-4_1ryl5iと入力診断を保存。
  詳細はGPU_TRAINING.md、機械可読はlearning-curve/image-dependenceの2026-09-14.json。
- 純粋関数policy_action.pyを追加。測定済み現在TCPへの相対h1変換、予測6D正規化、
  明示座標契約、不正値/シミュレーション境界超過の拒否。6単体テスト合格。
  タイムアウト/sequence/実機停止はこの部品の範囲外。WBC/実機には未接続。
- 次: 幅の測定値利用・モデル構成を検証splitで比較する。どちらのモデルも実機へ配信しない。

### 2026-09-14 グリッパ幅の変化量学習比較

- 内部ターゲットをfuture_width-current_widthにし、出力復元で現在幅を加算するcodecを実装。
  外側の10D h1/columns/将来絶対幅契約と元データは維持。
  metadata action_codec.jsonとcodecコードhashを保存。旧policy-check/policy-evalは
  custom codec検出時に拒否し、未復元の残差値を絶対幅として扱わない。
- 同一小型ACT、cache/split/seed42/batch16、3000stepで直接幅方式と比較。
  job-uwo2noeu成功、run-xg1fn3b_。学習84.586秒、cache推論p95 4.933ms。
- 検証幅MAE1.603mm（直接幅2.087mm、現在幅保持1.767mm）に改善。
  位置2.024mm（保持2.115mm）。ただし回転0.010511rad（保持0.010474rad）、
  負幅2件、最小-4.192mmが残るため不採用。最終test/実機は未使用。
- 内部目標のtrain-only統計照合、codec込み1278予測の保存・strict再読込一致に合格。
  ローカル6テスト、旧policy-check、policy-action6テスト、構文/diffチェック合格。
  codec付き途中再開の独立比較は未実施。モデルとcodec等は両PCへ保存。
- 次は変化量方式を候補として、非物理的出力と回転予測を改善/検証する。
  詳細: GRIPPER_RESIDUAL.md、gripper-residual-2026-09-14.json。

### 2026-09-14 実推論からシミュレーションWBCへの接続

- ユーザー方針に従い、学習指標の追加改善を前進の条件にせず接続試験へ進んだ。
- 記録RGB/stateを固定LeRobot ACTへ入力し、codec復元後の10D actionを
  ローカルpipe経由でTCP変換・IK・Decoupled WBCへ接続。実機送信なし。
- 測定姿勢へ目標を毎回置き直す初期方式は16指令でworkspace超過。
  約3.5 mmの指令合計に対し約13 cmのドリフトを確認し、失敗記録を保存。
  測定TCP軸の差分を制御参照へ積み上げ、ゼロ指令なら目標保持する方式へ変更した。
- 90/90実推論・12秒の立位/追従検査に合格。stale/負幅の注入は5指令後に
  意図どおり拒否・目標保持し、立位を維持。異常runは終了コード1のまま記録。
- bridge単体4テスト合格。既存teacher再生30秒・254フレームも合格。
- make policy-sim / policy-viewを追加。詳細と再現コマンドはPOLICY_SIM.md。
  CPU要求応答p95約110 msで同期実行のため、実時間30/50 Hzの検証ではない。
  記録観測でありカメラ閉ループではなく、グリッパ固定、タスク成功は未検証。
- 次は指令を送らない実機状態・カメラ入力確認と、推論/WBCの実時間分離の準備。
  今回の接続合格を実機への動作許可とは扱わない。

### 2026-09-14 実機入力の準備・接続確認

- ローカルPCのUSB/video/networkを読み取りのみで確認。
  video0..3はすべてIntegrated_Webcam_HD。USB列挙にもPIKA/RealSenseは見えない。
  eno1はDOWN・アドレスなし、Wi-Fiは192.168.1.25/24。
  これはこのPCの接続状況であり、GPU PC側の接続状態は今回確認していない。
- `make input-check` を追加。標準Pythonのみでデバイス名・USB製品・物理NIC・
  アドレスを列挙。撮影開始、SDK起動、G1探索、動作指令、ネットワーク設定変更はしない。
  検出結果は標準出力のJSON。機器の使用可能性の合否判定ではない。
- 次の物理操作: PIKAカメラを使うPCへUSB接続し、input-checkで再確認。
  G1状態受信や実時間経路の検証は未実施。動作指令禁止を維持。

### 2026-09-14 PIKA実カメラ2視点の撮影確認

- ユーザーのUSB接続後、D405、DECXIN、USB Serialを列挙で確認。
  USB Serialは開かず、G1・グリッパへの指令は送信していない。
- `make camera-check` を追加。sysfsの製品名とV4L2対応形式でcapture nodeを選び、
  候補が0件/複数なら拒否。video番号やvideo50エイリアスは固定しない。
- 実行時は魚眼video10/MJPEG、D405カラーvideo8/YUYVを選択。
  各640x480/30fpsを要求し、30番目の画像をPNG保存。各撮影に20秒の上限。
  2画像とも取得成功・目視確認済み。室内とPIKAが見え、魚眼視点/カラー視点を確認。
- 結果: artifacts/camera-check/run-4plz79uh/report.json と2枚のPNG。
  構文検査・diff --check合格。今回の撮影ツールは既存システムのffmpeg/v4l2-ctlを使用し、
  新規依存をインストールしていない（この診断ツールの依存はlock対象外）。
- これは順次撮影の疎通検査。同期・実効fps・深度・較正・学習時と同じ画像前処理は未検証。
  次は実画像を学習時の2視点入力形式へ合わせる。実機指令禁止は維持。

### 2026-09-14 両手接続と左右識別

- ユーザー指定により既存一式を右手、追加一式を左手として追加前後のudev情報を照合。
- D405は右EXAMPLE_DEVICE_SERIAL、左012345678901（USB報告値、一意性は未保証）。
  魚眼は左右とも01.00.00で重複を確認。USBシリアルも個体番号なし。
- 魚眼/USBシリアルの共通by-idが左を指すため、by-idのみでは左右指定不可。
  このPCのby-path対応と現在nodeをDEVICE_IDENTITY.mdへ保存。
- 読み取りのみ。左右選択コードは未実装、別PCでの接続位置は再登録が必要。

### 2026-09-14 USB 2/3の対応調査

- sysfsのpeerリンクでこのPCのUSB 2/3ポート対応（port2同士、port3同士）を確認。
  D405と同じ物理接続のUSB 2側機器を対応付ける手掛かりを得た。
- ただしサンドボックス外のlsusb -tでも左右PIKAがどちらも列挙されず、
  実機器を使ったハブ対応確認は進められない。再接続または接続先PCの確認が必要。
- 自動左右選択・内部ID調査は未完了。撮影・シリアル通信・動作指令なし。

### 2026-09-14 非同期推論とWBC継続

- ユーザー方針に従い、このPCのUSB識別調査は終了。本番PCへの接続時に再開する。
- 別プロセスACTへの非ブロッキングpipe要求/応答を実装。未完了は1件だけ、
  応答待ちはWBCの目標保持を継続し、0.5秒の壁時計期限切れをラッチする。
- make policy-async / policy-async-viewを追加。記録画像30フレームの実推論と
  12秒立位/追従検査合格。bridge p95 0.141 ms、WBC計算p95 6.565 ms。
- 6番目の応答を250 ms保留するdelay試験も30/30指令で合格。
  silence試験は5指令後に期限切れを検出し、以降目標保持で12秒立位維持。
  異常runは期待どおりpassed=false/終了コード1。MuJoCo警告は全3runで0。
- 非同期単体5テスト合格（疑似時計・実pipe部分読取/空/EOF）、既存bridge4/action6も合格。
  構文検査・diff --check合格。記録はASYNC_POLICY.mdとasync-policy-2026-09-14.json。
- CPU推論は依然30 Hz未達。記録フレームの再生速度を落とした接続検証であり、
  実時間周期保証・実画像閉ループ・実機利用の合格ではない。実機指令送信なし。

### 2026-09-14 一括通し実行

- make end-to-endを追加し実行完了。既存学習済みACT、episode39全206フレーム、
  60秒の非同期WBCシミュレーションに合格。指令206/206、警告0、TCP誤差最大3.40 cm。
- WBC計算p95 7.439 ms、bridge p95 0.603 ms。実時間周期保証とは区別する。
- 単体15件合格。続く応答断試験も5指令後に期限切れを検出、12秒立位保持。
  応答断sim自体は終了コード1を維持し、一括runnerが期待結果として検証。
- artifacts/end-to-end/run-1cshuxmqに個別ログ・結果、docs/end-to-end-2026-09-14.jsonに要約。
  新しいreport-dir指定で実行ごとの証拠を分離。構文・diff検査合格。
- 追加学習・USB調査・実機送信なし。記録画像からシミュレーションまでの通し確認であり、
  自律把持、本番配置、実観測同期、実機用安全/通信経路は未完了。
  開発PCの試験追加は区切り、残作業をEND_TO_END.mdに集約した。

### 2026-09-14 G1搭載PCのSSH準備

- 本番構成をgalleria—有線LAN—G1搭載PC、PIKAはG1側USB接続と確認。
- 開発PCからunitree@192.168.1.18へユーザーのパスワード接続成功。
  自動鍵認証はPermission denied。専用Ed25519鍵を開発PCの.sshに新規作成。
- 公開鍵登録はユーザー操作待ち。接続情報・手順はG1_ACCESS.md。
  秘密鍵・パスワードはリポジトリに保存しない。実機指令送信なし。

### 2026-09-14 G1搭載PCへの鍵接続成功

- 専用鍵でunitree@192.168.1.18へBatchMode接続成功。環境・USB・サービスを読み取り確認。
- Orin NX/約16GB RAM/Python3.8。cv2/numpyあり。右PIKAのD405 EXAMPLE_DEVICE_SERIAL、
  DECXIN、USB Serialを確認。本体D435iもあるためカメラの混同を避ける必要あり。
- galleria 192.168.1.27への現在経路はwlan0。eth0は192.168.123.164、eth1はDOWN。
  本番の有線接続状態を確認する必要がある。ネットワーク設定・既存サービスは変更なし。
- 詳細はG1_ACCESS.md。G1上の撮影・状態受信・推論・動作指令はまだ実行していない。

### 2026-09-14 左手再確認・G1上の右手カメラ取得

- USB再列挙でも左D405 012345678901は見えず、DECXIN/PIKA USB Serialも各1台。
  ユーザー指示に従い原因調査は保留し、右手で次の作業へ進めた。
- make g1-camera-checkを追加。SSH標準入力で撮影コードを実行し、G1にはファイルや依存を配置しない。
  既存OpenCV4.2.0で右D405カラーと魚眼を各30フレーム読み、最後の640x480画像を回収成功。
  D405は既知シリアル指定、魚眼はDECXINが1台の場合のみ選択。複数時は拒否する。
- 結果: artifacts/g1-camera/run-3usdfsex/report.json と2画像。
  順次撮影・Wi-Fi/開発PC経由の確認であり、同期・実効fps・本番通信性能の合格ではない。
  G1側設定変更・シリアル通信・動作指令なし。構文・diffチェック合格。
- 次は回収実画像をgalleriaのGPU推論へ渡す。現在幅はまだ実測取得できていないため、
  仮の幅を使う場合は診断専用と明記し、実機制御には使用しない。

### 2026-09-14 G1実画像でgalleria GPU推論

- 回収済み右PIKA2視点をgalleriaの新規artifacts/image-probe-Ee18Sqへ転送。
  2画像のSHA256は元と一致。既存依存・コードを変更せず診断スクリプトを新規配置。
- 固定GPU環境/LeRobot、学習時rgb_input、strict ACT読込、codec復元で10D推論成功。
  現在幅は診断用の仮値0.04mと明記。出力は記録のみでG1へ返していない。
- 同一画像20回のGPU前処理/推論/復元p95 5.268ms。撮影・転送時間は含まない。
  静止画・仮stateの疎通試験であり、リアルタイム閉ループ・タスク性能は未検証。
- 詳細G1_IMAGE_INFERENCE.md、機械可読g1-images-gpu-2026-09-14.json。
  構文・diffチェック合格。次は有線連続画像経路と実測状態入力。実機指令禁止は維持。

### 2026-09-14 連続画像のGPU推論を一括実行

- ユーザーの「細切れにせず進める」に従い、継続カメラreader・SSH転送・GPU推論・
  30組の記録・正常終了までmake live-shadowで一括実行し成功。
- 両視点counter/seq重複なし。GPU p95 12.539ms、開発PC基準の画像要求→推論応答p95 195.699ms。
  カメラread時刻差最大37.833msで厳密同期ではない。最大5組/秒の診断、30Hz未検証。
- G1/galleriaともWi-Fi経路。有線設定・サービス・既存コードは変更せず、新規診断フォルダのみ使用。
  実機動作指令・シリアル通信はなし。幅は仮値4cm。結果LIVE_SHADOW.mdに集約。
- 既存PikaGripperのconnectでリセット注意、disconnectでdisable送信を確認し、
  そのままの流用は見送った。実測幅・G1状態は未入力。安全確認なしにserialをopenしない。
- scripts/g1_camera_stream.py、run_live_shadow.pyを追加しprobe_gpu_images.pyにstream経路を追加。
  構文・diff検査合格、実行レポートから30seq/10D/送信なし/フレーム更新を照合。
- 次は本番有線経路、開発PC中継除去、実測状態同期。実機指令禁止を維持。

### 2026-09-14 有線直通で画像取得・GPU推論

- galleria enp2s0 192.0.2.12 → G1 eth0 192.168.123.164の有線経路を確認。
  ping3回損失0、平均0.160ms。G1 eth1はDOWNのまま。ネットワーク設定変更なし。
- GPUの旧ホスト鍵登録は保持し、信頼済みG1公開鍵をプロジェクト専用ファイルへ固定。
  GPU専用SSH鍵を新規作成し、G1へrestrict/from=192.168.123.99付き公開鍵を追加。
  秘密鍵の転送なし。有線鍵認証でhostname読取成功。
- run_live_shadow.pyにGPU上直接実行を追加し、make wired-shadow経由の配置で
  画像30組をG1→GPU PC直通で取得・推論・記録・正常終了まで確認。
- GPU前処理/推論p95 12.586ms、要求→推論応答p95 33.817ms。30seqを照合。
  最大5組/秒の診断なので30Hz保証ではない。幅は仮値、G1動作指令は送信していない。
- 結果wired-live-2026-09-14.json、詳細LIVE_SHADOW.md。構文/diff検査合格。
  次は実測状態と時刻同期。既存グリッパドライバの副作用回避は引き続き必要。

### 2026-09-18 G1有線接続の読み取り確認

- ssh-copy-idで1鍵追加とのユーザー報告後、galleria→G1の専用鍵SSHに成功。
  新OSはUbuntu22.04.5/aarch64/Python3.10.12、有線IFはenP8p1s0。
  右D405とDECXIN魚眼をby-idで確認したが、PIKA USB Serialは同時点のserial/by-idにはなし。
  libddsc/libddscxx/libzmqとgccは存在、idlcはPATH上未検出。旧ROS/DDSパスなし。
  接続情報をassets/network/g1-runtime-access.jsonへ保存。旧ランナーは未更新のためそのまま再使用しない。
  実機動作・カメラ起動・サービス/ネットワーク設定変更なし。
- galleriaとG1を有線接続したとのユーザー報告後、tiger→galleria専用鍵SSHに成功。
  galleria enp2s0=192.168.123.99から192.168.123.164への有線経路、ping2/2・平均0.193msを確認。
  新しいG1ホスト公開鍵をgalleriaの新規専用ファイル
  `/home/gpu-user/g1-pika-training/artifacts/g1-access-lw4t5m/known_hosts` に配置。
  厳格なホスト照合は通過したが、galleria専用鍵でG1ユーザー認証はPermission denied。
  次はgalleria端末でssh-copy-id。G1のOS確認コマンドには到達していない。
  パスワード取得・動作指令・ネットワーク設定変更・旧鍵ファイル上書きは行っていない。
- 後続: ユーザーがG1ローカル端末で新指紋を確認。取得公開鍵をSHA256で照合し一致。
  プロジェクト専用known_hostsを更新し旧鍵を別ファイルへ保存。グローバル設定は未変更。
  SSHのホスト照合は通過したが、専用鍵のユーザー認証でPermission denied。
  次はユーザーのパスワード操作によるssh-copy-id。GPU側接続設定は未更新。
- eno1 UP、192.0.2.10/24。192.168.123.164への経路はeno1、ping2/2成功、平均0.133ms。
- 専用鍵・保存済みホスト鍵ファイル・StrictHostKeyChecking=yesでSSHを試行。
  ED25519鍵が以前と異なり認証前に停止。今回提示された未検証指紋は
  `SHA256:PUBLIC_EXAMPLE_NOT_VERIFIED`。
  known_hostsは書き換えていない。機体/搭載PCの変更をユーザーへ確認する。
- カメラ起動・状態購読・動作指令・ネットワーク設定変更は行っていない。
- ユーザー指示を反映し、開発PC↔GPU PCの有線検証を必須とする方針を撤回。
  本番GPU PC↔G1経路の実装に必要な作業を優先する。

### 2026-09-15 非同期化と通信経路の切り分け

- 身体状態と画像を別worker/別REQ-REPへ分離。GPU側ACT→WBCにはGPU内PUB/SUBを追加。
  MuJoCoは通信中もwall-clockに追従し、期限超過で次の物理stepへ進まず終了する。
- 短縮2 PC試験12秒/30推論に成功したが、全試験では206推論受信後18.505秒に
  100ms指令鮮度期限へ達し、833指令で停止。全試験は未合格のまま保存。
  `artifacts/split-runtime/run-wvvavyv0/`、async-runtime-wifi-2026-09-15.json。
- 読み取りで経路はwlp1s0/Wi-Fi、eno1未接続を確認。設定変更はしていない。
  WBC計算最大2.380ms、物理時刻遅れ最大5.759msだったが、原因をWi-Fiだけに断定しない。
- GPU内loopbackへMuJoCoも配置する切り分けでは、206推論/2999指令/60秒を完走。
  wall-clock60.000068秒、最大指令年齢50ms、物理遅れ0.208ms。単体45件と異常4ケース合格。
  推論遅延要求後も26指令を適用でき、画像期限超過後は後続actionを適用しなかった。
  `artifacts/split-runtime/run-t72e4a86/`、async-runtime-loopback-2026-09-15.json。
- 最大TCP位置誤差0.036010m、姿勢0.095447rad、ソースhash一致・構文・diff検査も確認。
  GPU側サービスは全終了。G1接続/指令/グリッパ操作は行っていない。
- 次は有線2 PC比較。物理接続が必要なため、現時点で同等の有線合格は主張しない。
  hard real-time、実機停止、実カメラ閉ループは未検証。
  詳細 [ASYNC_SPLIT_RUNTIME.md](ASYNC_SPLIT_RUNTIME.md)。

### 2026-09-15 GPU PCへLeRobotとWBCを集約

- GPU PCに固定Python3.10 WBC環境を新規複製。既存CUDA LeRobot環境とは別プロセス。
  このPCはMuJoCo物理と受信関節目標の検査・適用だけを担当する新経路を追加。
  G1には接続せず、動作指令も送っていない。
- `make split-runtime` で専用配置の再利用、単体40件、206フレーム/60シミュレーション秒、
  関節通信断・旧セッション・0.8秒遅延、サービス終了/結果回収まで一括実行成功。
  最終run `artifacts/split-runtime/run-4eb3ocoz/`。206 ACT/3000 WBC指令、MuJoCo警告0。
  異常ケースは200指令で適用停止。遅れてGPUが計算した指令を適用しないことを確認。
- 学習共通resize後のfloat32を可逆圧縮し、画像を必要tickだけ送信。
  先頭packet565135→320818bytes。旧PNG方式との先頭30予測差は0。
  p95は画像なし11.895ms、画像付き57.439ms、WBC1.545ms、GPU内ACT往復6.798ms。
  配置・再生方式・入力処理が異なるため、旧111msからの実カメラ改善率とは扱わない。
- 状態/TCP追従閾値、コードhash一致、構文、diff検査も確認。
  詳細 [SPLIT_RUNTIME.md](SPLIT_RUNTIME.md)、結果 split-runtime-2026-09-15.json。
- lockstepで通信待ち中は物理時間も止まる。ACT25Hz相当・WBC50Hzのsim時刻であり、
  実時間性能/安全停止/実機状態変換/実測幅/実タスク成功は未検証。
  旧mock-runtime表示は旧配置のままで、新split経路のGUIは未実装。

### 2026-09-15 G1なしの2 PC統合

- ユーザー指示で実機接続を後回しにし、このPCとGPU PCだけを使用。
  G1へのSSH/DDS/serial接続、実機動作指令、依存の変更は行っていない。
- `WbcState` と `step_state` を追加し、状態入力の次元/関節順序/有限値/
  クォータニオン/既知の規約を検査。通常600フレームの目標は分離前と数値完全一致。
- 記録RGB/state＋MuJoCo身体状態→ZMQ→GPU LeRobot ACT→非同期TCP目標→
  ローカルWBC→出力guard→MuJoCoを実装。専用workerがソケットを所有、要求1件、
  期限/セッション/連番を検査。実行中の画像・状態・actionをSSHで運ばない。
- `make mock-runtime` で新規配置・単体35件・正常/異常5ケース・終了/結果回収を一括化。
  最終run `artifacts/mock-runtime/run-qj1nhyge/` は全合格。
  通常30件、異常後の新規セッション30件が完走。旧応答・通信断・遅延は各5件で
  action適用を止め、WBC600出力・立位/追従閾値内を維持。身体状態の送受信hashも照合。
- 正常時request p95 110.805ms。30Hzや実機安全停止の達成とは扱わない。
  ACTは記録画像/stateを使用するため画像閉ループではない。実機状態変換・幅実測・
  座標校正・制御権/停止/送信の実機統合は未完了。
- GPUへの追加は固有 `artifacts/mock-runtime-ljIHQM/` への専用スクリプト配置のみ。
  全ケースのサービス終了コード0を確認。README/HANDOFF/起動設定を更新。
  詳細: [MOCK_RUNTIME.md](MOCK_RUNTIME.md)、結果: mock-runtime-2026-09-15.json。
  GUI版とCPU loopback代替の起動口は用意したが、この時点の実行検証はGPU版のみ。

### 2026-09-15 WBC出力の検査・記録境界

- `control_guard.py` とMuJoCo接続を追加。関節順序・有限値・位置範囲・連番・
  状態時刻・所有者を検査し、faultをラッチ。実機送信は存在しない。
- `make check-guarded-wbc` 成功。単体10件、通常12秒、教師30秒、
  LeRobot ACT実推論206/206フレームを含む60秒シミュレーション成功。
  承認済みWBC出力は順に600/1500/3000件。
- 状態遅延・停止フラグ・NaN・所有者違い・関節順序違いの5ケースは、
  それぞれ100件で記録を止め、期待したfault理由と終了コード1を確認。
  別途、既存action/bridge/async単体15件と構文・diff検査も成功。
- 結果: `artifacts/guarded-runtime/run-d5oeeika/summary.json`。
  実装範囲・未検証事項・起動方法: [CONTROL_GUARD.md](CONTROL_GUARD.md)。
  シミュレーション終了を実機の安全停止と解釈しない。実機指令は禁止のまま。
  今回SSH/実機接続なし。ZMQ通信構成とLeRobotの責務は変更していない。

### 2026-09-14 DDS状態受信とPC間ZMQへ分離

- G1既存DDS0.10.2で受信専用Cをビルドしrt/lowstateを5秒購読、4567件受信。
  機体指令なし。IDL出典/ライセンス保存。CRCは未検証。
- ユーザー確認に従いSSHデータ転送の拡張を止め、PC間をZMQへ変更。
  G1有線6158番のREP、GPU REQ、送信元IP制限・HWM/サイズ/timeout制限を設定。
  既存libzmqを利用して依存追加なし。SSHは配置・起動管理のみ。
- 実画像＋q/dq/IMUを30組受信、全seq/body tick更新を検証しGPU推論・記録成功。
  通信込みp95 35.014ms、GPU p95 7.965ms、画像/状態の受信時刻差最大63.153ms。
  IPC3試験・構文・diff検査合格、終了後のZMQポート閉鎖も確認。
- グリッパ幅は仮4cm。body状態は対応記録のみ、実機WBC/停止系は未完成。
  詳細ZMQ_STATE_SHADOW.md、要約zmq-state-shadow-2026-09-14.json。

- NVIDIA GPUなし（初回ローカルPC確認）。CPU最小試験は成功したが、公式GPU/Docker構成の適合とは別。
- snap版uvはサンドボックス制限で使えなかったためPython標準venvを採用。
- 初回pip呼出しでは既存ROSのPYTHONPATH由来の外部パッケージ警告が出た。
  `-I`で隔離して再確認すると不整合なし。以後のsetup/起動にも`-I`を適用。
- ワークスペース直下の保護された空 `.git` は変更していない。
- 最新のユーザー希望により、必要な実装・検証からコマンド提示まで続けて進める。
- 別PCでのクリーンsetupは未検証。GUIはユーザー確認済みだが、修正後の描画速度は未計測。
  setupはG1用LFSアセットのみを明示取得する。
