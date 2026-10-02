# 作業方針・モデル交代時の引き継ぎ

> 公開用コピー：ネットワーク値・機器識別子・ローカルパスは例へ置換。保存試験結果は原本の記録で、例設定で実機試験した証拠ではありません。クラウドから機器接続・実機指令を行わないでください。


## 現在の方針（2026-10-02整理、以下の履歴に優先）

### 目標と構成

- Unitree G1＋AgileX PIKAをLeRobot＋GEAR-SONICで動かす開発環境を完成させる。
  人がPIKAで収集したデータで学習し、最終的には自立・自律タスク実行を目指す。
- tigerは編集・配置・診断、galleriaは学習/ACT推論・IK・SONIC推論、G1搭載PCはセンサー/PIKA接続。
  galleria–G1は有線LAN、PC間通信はZMQ。DDSはG1側の状態受信・将来の低レベル制御用。
- LeRobot actionは局所相対位置3＋回転6D（columns）＋幅1の10次元。
  TCP→再利用IK→SONICの29関節参照へ変換。PIKA幅は別経路で扱う。
  SONIC公式VLAの78次元やDex3とは互換として扱わない。
- 旧Decoupled WBCは比較資産。IK/モデル部品の再利用と旧balance policyの実行を区別する。
- 固定ソース/モデルは `sources.lock.json`、実行先は `config/development.json`、
  G1接続/デバイスは `assets/network/g1-runtime-access.json` を参照する。

### 進め方と許可

- 2026-10-02クラウド移行：ユーザーはgalleriaのネットワークから離れ、G1も起動できない。
  現在ソースのクラウド引き継ぎを準備する。docs/CLOUD_HANDOFF.mdを追加入口とし、
  cloud-setup/cloud-checkでCPU・送信なし開発を継続。GPU/G1接続を試みず、起動を求めない。
  移行は実機動作の新規許可ではない。
  送信先はtaigasasaki6331/sonic_lerobot。新規codex/cloud-handoff-20261002ブランチを
  mainの68c7294475646f3bdb373594c806d7f1b95b9e86から作成済み。既存mainは変更なし。
  publicでの送信を利用者が了承。内部IP/ローカル配置/機器識別子を例へ置換したコピーだけ送信する。
  既存remoteはPIKAなしπ0/π0.5・48次元actionの別方式。既存src/tests/docsを変更せず、
  今回のACT/10次元/PIKAはremote g1-pika/へ配置し、root AGENTSで主対象を明示する。
  cloud exportのvendorは固定ソースの部分コピーで、完全なモデル/実行環境ではない。
- 2026-10-02最新の優先順位：部品の細部を詰めるマイルストーンは後でユーザーが割り振る。
  今は動かせる一本の経路の実装を優先し、その動作で有効性を評価できるようにする。
  個別診断/試験数の追加を主成果にしない。実機指令の許可範囲は引き続き変更しない。
- 許可済みの実装・配置・単体試験・記録再生・読み取り検証は途中で継続確認を求めず進める。
  ユーザーは確認の反復や細かな区切りを望まない。必要な質問は具体的な欠落情報に限定する。
- 2026-10-02の最新ワークスペース指示は「MuJoCoでLeRobot＋SONICの統合検証を行い、
  実機側実装も省略しない。実機動作指令なし、実入力の読み取りは了承済み」。
  前回引き継ぎの「現在シミュレーションなし」を置き換える。過去の結果/失敗も保存する。
  実機側の起動/送信/停止実装は送信なしで開発する。
  6〜12時間は過去のMuJoCo実装/初回検証の見積りで、実機側残作業・実機検証の総工数ではない。
  DDS実機publisher/通常G1Deployを診断として起動しない。リモコンのソフトウェア統合は対象外。
- 身体・腕・グリッパへの実機動作指令は現在の開発範囲では送信しない。
  9月18日の右PIKA単体開閉は完了した限定試験で、再実行や全身制御の許可に拡張しない。
- 2026-10-02の例外：今回の単体PIKA原因切り分けについて、利用者が
  「実機動かしてOKです、周囲の安全は確保済みです」と明示許可。
  tiger直結/dev/ttyUSB0の単体診断に適用し、G1身体・腕・全身制御へ拡張しない。
  0.2 Aで開く→電流だけ1.0 Aへ変更の1回を実施、異常受信で閉じ段階の前に停止。
  無効化・切断確認済み。証拠はartifacts/gripper-control/session-_a22sm42。
  同じ許可を取り直さず、目視の準備など必要な操作調整だけを行う。
  続報：同条件1.0 Aと希望範囲1.8 Aで段階閉じを実施し、利用者がどちらも
  「滑らかで跳ねなかった」と目視確認。session-34rt2ood/session-rmky5u3tを保存。
  1.8 Aはcleanup中の異常受信あり。終了時faultでもpassedになる漏れを修正、46単体成功。
  電流設定/短時間開閉の確認で、全電流出力・把持力・受信信頼性の認定ではない。
  カメラ録画等の追加工数は不要との利用者指示を守る。
  最新続報：利用者interactiveの数値破損→自動disable→保持解除による開きを保存履歴で確認。
  0目標到達後の再送と把持中grip再入力による実測角度への目標再設定を廃止。
  電流絶対値>=1,000,000 mAのフレームは全体を破棄し、状態/鮮度を更新しない。
  定格判定ではない。250ms期限/角度範囲/正常電流を伴う範囲外角度のラッチは維持。
  session-_2qc97o7は0.2〜1.8 A変更/保持73.29秒を完了、数値破損1件を破棄して保持継続。
  無効化・切断済み。52単体で検証。受信破損自体は未解消、旧実急動作の根因は未確定。
- G1カメラ・身体・右シリアルの読み取りは了承済み。毎回同じ了承を取り直さない。
  serial openのMCU resetの可能性は説明済み。読み取り了承を動作許可にしない。
- カメラ露出/FPS変更・復元と、受信プロセス限定の一時RR/1試験も了承のうえ完了済み。
  一時補助・対象プロセスは終了。恒久sudoers/capability/governor変更は許可範囲外。
- G1が使えなくても非実機作業を進める。過去の起動確認から現在の稼働を推測しない。
  非実機作業のためだけにG1起動を求めない。ネットワーク/ファイルの承認境界は尊重する。
- 実機試験の承認を求める場合、先に許可範囲内で実装・検証し、操作/範囲/終了方法を具体化する。
  作業を止める場合は必要な情報・権限と理由を明示する。単なる区切りを承認待ちとしない。

### 確認済みの到達点

- 10月2日最新続報：G1-local record runtimeを一つの起動経路へ統合。
  make body-runtime：同一ホスト状態→3秒初期参照/姿勢確認→既存ZMQ→native owner→メモリ停止。
  最終run-0ztzrug5は5秒/229目標/68受理/native通常2390＋停止候補1、正常終了。
  body-runtime-expiry/run-af7qw18jはpeer通信/stdin継続・身体入力停止でnative身体期限fault、全thread終了。
  人工身体/CRCmetadata/ownershipとSDK-free出力。物理/実時間成功として扱わない。
  receiverへraw_motor_state/motor_modesを追加、raw bits=0はrecord criterionでfirmware健全性認定でない。
  online-record BODY_RUNTIME=1 ONLINE_SECONDS=5へpackage配置/現地build/目標sink/停止/journal回収を実装。
  G1停止/右PIKA取り外し中につき実入力版とaarch64 buildは今回未実行。実SDK送信も未接続。
  初回future-tick raceを人工feederで修正、応答期限失敗等の全ログを保存。gate緩和/自動再armなし。
  最終check-offline成功（IPC6件skip）、別途既存service IPC7件成功。BODY_WRITER.md統一起動経路参照。

- 10月2日続報：make runを統一起動口として追加。
  LeRobot→IK→SONIC→native BodyIoAdapter/WriterKernel→固定LowCmdデータ→MuJoCoを接続。
  3秒run-7yfd38m5と最終30秒run-u9gljra3が完走、30秒ACT900/SONIC1500/native15100tick、
  立位/範囲外0、右TCP移動最大0.2808m（起動整定含む）、両worker/video exit0。
  停止候補/復帰はsimulationのみ。native gatewayはSDK-free simulation backendに固定。
  LowState CRC/health/ownershipは人工入力で、実G1の証拠にしない。
  physical_step_gate_passed=false（起動0.3437rad）を保存。実機WriterMailbox gateは変更なし。
  G1接続/実SDK起動/実機指令なし。READMEの「まず動作させる」とSONIC_MUJOCO.mdを参照。

- 10月2日再開：ユーザー申告はG1シャットダウン中。今回G1/GPU接続・sim再実行なし。
  body_writer.hppのnative 2ms owner loop/mailbox/局所期限/独立停止要求を追加し、
  SDK-free疑似通信先24条件成功。run-l9olmfsqへソースSHA/実thread計測を保存。
  疑似時計の150参照/1500周期と実thread5ケース。25ms疑似write後はfault、通常送信再開なし。
  モーター健全性/初期姿勢/ownershipの実gatewayは未接続、2ms設計値は実時間保証でない。
  BodyIoAdapterに局所identity lossラッチを追加、最新tiger19条件成功。
  10月1日のG1 compile FT3T3pは旧18条件の版で、今回版G1 compileは未実施。
  次はBODY_WRITER.md/IMPLEMENTATION_TODO.mdを参照。
  ユーザー依頼の当初TODO/進行TODO/判明課題をIMPLEMENTATION_TODO.mdで対応付ける。
  最終check-offline exit0（IPC6件明示skip）。ASan/UBSan成功、LeakSanitizerは環境制約で未確認。

- 10月1日SONIC MuJoCo自由基部/接触閉ループと保存RGB LeRobot接続を追加。
  run-_z1bvt9zは30秒ACT900/SONIC1500・範囲外0・両worker exit0。
  画像は保存1組・幅0.04m仮定、視覚タスク/実時間/実機の合格ではない。
  教師run-pu1qxp7gは完走/立位/範囲外0だが起動TCP8.23cmで未合格。
  2秒参照遷移と計画/実測の分離、失敗ログを保存。SONIC_MUJOCO.md/HANDOFF冒頭参照。
  旧balanceを使用していない。G1接続・実機指令なし。
  local_body_monitor/LocalSonicBodyBridgeは同一ホスト入力の純粋コア、新規9試験成功。
  GPU bodyコピーをlocal watchdogの更新に使わない。実writer/物理停止は未完了。
  続報local_body_serviceで独立10ms監視thread/stdin入力/ZMQ記録受信を実装、人工入力IPC含む7試験成功。
  後続でG1/aarch64配置・実入力検証済み。500Hz writer・実時間保証・実停止として扱わない。
  最新ユーザーの起動通知後、G1 Python3.10.12/numpy1.21.5/libzmq/CycloneDDS0.10.2を確認。
  追加インストール不要（pyzmq不在でもctypes libzmqを使う）。mode_machine=5/mode_pr=0。
  make body-local-check：実LowState＋保存SONIC150件をGPU→G1 TCPへ、全件gate/受理0/指令0。
  最新artifacts/local-body/local-body-nZZEwC、147件の範囲超過は保存したまま未解決。
  続報make lowcmd-abi-check：固定データクラスだけをG1/aarch64でcompile、保存1540件の
  LowCmd native memory1004bytesがx86_64/独立Python CRCと一致、binary exit0。
  artifacts/lowcmd-abi/lowcmd-abi-J7oor9。DDS型登録/client/publisherなし。
  mode_machine=5は保存読取値による診断。DDS配送/firmware受理は未検証。
  make body-local-expiry-check：stdinを開いたまま転送停止、約101msで局所異常を観測。
  process終了は約353ms、物理停止ではない。最新local-body-IGY3In、全対象process/thread終了。
  保存SONICの鮮度/実時間/タスク品質の合格ではない。この旧runではCRC未確認。
  続報make body-local-crc-check：固定SDK native LowState2092bytesのCRCを実受信で必須検証。
  128全フィールドfixtureが独立Python CRCおよびx86_64/G1 aarch64と一致。
  local-body-EHFf0Dは実165frame全CRC一致、保存SONIC150件全gate/受理0/指令0。
  CRC不一致はreceiver exit3、strict monitorも未確認/不一致をラッチ拒否する。
  make body-local-crc-expiry-checkのlocal-body-zwvbSWは実77frame全CRC一致、
  最後のsampleから109.56msで異常、転送停止からprocess終了353.39ms。物理停止/実時間保証ではない。
  新規CRC2＋monitor追加2試験、最終check-offline成功（IPC6件明示skip）。
  LowStateのCRC一致はモーター健全性・制御権・立位条件の証明ではない。
  身体SDKアダプターをbuild-onlyで追加。body_io_adapter.hppはSDKなしの契約/呼出順序、
  unitree_body_transport.cppは固定SDKへの実接続コードで、既定compile flag0は全I/O拒否。
  body-io-build-FT3T3pでG1 object compile flag0/1成功、SDK-free疑似transport18条件成功。
  SDKをリンク/実行していない。実launcher/500Hz writer/現場停止確認/実gateway統合は未完了。
  診断ACK・契約bool・SDK書込み成功を物理停止/制御権確認にしない。
  通常G1Deployは禁止継続。詳細BODY_IO_ADAPTER.md/HANDOFF冒頭参照。
  後続の最終コード再実行の保存先はPROGRESSを参照する。

- 実演データは準備済み。データ不足や保存先不明としてユーザーへ再指定/再収集を求めない。
  ローカル原本は `/home/developer/workspaces/pika_ws2/datasets/data_2608261323_valid49_g1_zero_relative_h1_final_v3`。
  49episode/10881frame/30fps。9月30日、manifest記載17ファイルの存在・サイズ・SHA256一致を再確認。
  GPUコピーは `/home/gpu-user/g1-pika-training/datasets/valid49`（9月14日転送検証済み、最新稼働は未照会）。
  manifest/splitは `assets/datasets/valid49-files.json` / `valid49-split.json`。
  学習39・検証5・テスト5episode。幅h1不一致145行を除外し、採用8693/1022/1021frame。
  ACT学習済みモデルは `artifacts/full-rgb-residual/run-xg1fn3b_/pretrained_model` にローカル保存あり。
  現行推論で使用する診断モデル。実タスク性能の合格とは別。GPU_TRAINING.md/GRIPPER_RESIDUAL.md参照。
  データのtask欄は文字列 `null`。データ存在と具体的なタスク名称の記述を混同しない。

- ACT候補はconfig/policy-bundle.jsonでモデル7ファイル＋前処理/codec/依存lockを固定。
  make bundle-checkはファイル専用。GPU全経路runnerもready前に再照合する。
  モデル本体だけ差し替えず、残差幅の復号順を維持する。
  make bundle-exportは診断モデル一式のみ、データ/SSH鍵/他ログなし。POLICY_BUNDLE.md参照。
  9月30日run-w2r_5_nu（保存画像2組）とrun-ssy2zdrv（人工入力3秒）が全worker exit0。
  run-ck4k0eu8は同じ処理の対応上限30秒、903policy/1500control、4worker exit0、記録整合成功。
  身体制御やモデル品質の合格ではない。新規PC全自動setupとは区別する。

- 9月24日、一時RR/1下の3秒実入力試験でACT/IK93回・SONIC150回・画像186枚を記録。
  `artifacts/full-record/run-b5do1ocs/outputs/report.json`。入力2プロセス・GPU4worker正常終了。
  記録整合性は9月30日にもファイル専用で再確認。通常優先度の3秒失敗ログも保存。
- 保存入力を再構築した150×29目標出力は元記録と完全一致。
  上流観測C++関数との比較と `make check-offline` / `make check-runtime` は9月24日成功。
  これらを長時間安定性や実機の閉ループ追従の合格と扱わない。
- 右PIKA単体の開閉は9月18日にユーザーが目視確認済み。CH341復旧・右デバイス設定も記録済み。
- 現在の経路は `record_only` / `hardware_output_enabled=false`。
  trueは拒否され、実機送信コマンドは未提供。通常G1Deployを診断目的で起動しない。

### 残課題と現場条件

- 2026-10-01最新ユーザー申告：別試験のため、G1右腕のPIKAグリッパは取り外し済み。
  左側、取付具、カメラ、配線の残存/接続状態はこの申告から推測しない。
  既存PIKA付きモデルの右側質量/TCP/干渉条件を現在の実機へ適用しない。
  読み取り・送信なし実装は継続可能。右PIKA入力/把持を必要とする実入力統合・実動作試験は
  再装着と構成確認後に行う。既存モデル/学習データ/試験ログは変更せず保存する。
- 10月1日続報：sonic_body_bridge.pyのRecordSession互換受信部/clientとonline loopの任意sink接続を追加。
  保存実SONIC/身体150組をファイル/ZMQ IPC双方で渡しdecision SHA一致。
  最新artifacts/body-boundary/run-i0jva6mw（ファイル）/run-unswp0me（IPC）。全150姿勢未確認でgate、
  受理0/指令0、147件の範囲外は未解決。幅は別metadata、受信thread終了。
  新規接続7＋online追加4試験、online計20成功、check-offline一括成功（既存IPC4件skip）。
  make body-boundary-check/ipcはG1/GPU不要。既存launcherへの配置は未変更、sinkは既定無効。
  受信APIは引継ぎ/INIT/500Hz writerを起動しない。局所LowState監視は後続で実配置済み。
  実SDKアダプターは後続でbuild-only追加、実gateway/送信運用/物理停止は未完了。
- 10月1日、送信なしBodyLifecycleと固定SDK LowCmdメモリ/CRC previewを実装。
  初期参照/姿勢確認待ち/局所watchdog/停止要求/診断引継ぎ・復帰を検査する純粋なロジック。
  新規23＋3＋3試験、一括check-offline成功（既存IPC4件は明示skip）。
  保存150身体入力→1540抽象出力、姿勢未到達のためSONIC受理0、入力期限切れで停止要求。
  最新artifacts/body-lifecycle/run-6arb9pnq、LowCmd preview run-uin1oocvの1540件で独立CRC一致。
  ACKは人工診断、500Hzは保存timeline、mode_machine=0はfixture、native memoryはDDS形式ではない。
  既存ACT/IK/SONICオンライン経路に実機出力は接続していない。
  後続でSDK接続コードのみbuild-only追加済み、実初期姿勢/制御権/物理停止の運用は未完了。
  以前のuname照会はtimeoutだったが、最新起動通知後は記録専用配置/検証に成功。
  G1が必要な試験では稼働確認を具体的に求め、timeoutだけで電源状態を推測しない。
  次はBODY_LIFECYCLE.md/HANDOFF冒頭を参照。通常G1Deployは引き続き起動しない。
- 9月30日の起動履歴16組合せ×既存3参照の保存入力診断は完了・回収済み。
  run-ofbwc_6tで48条件/7200推論、4基準再現差0、worker exit0、保存再検証成功。
  10月1日に再開し全8背景のチャネル比較・保存生Quaternion/開始契約照合・文書/Make組込みを完了。
  初期感度はq/gravityで大きいが、初期10周期以後も48/48条件でURDF超過が残る。
  生値/正規化のencoder姿勢はfloat32差0、gravity差最大4.1723e-7。
  上流INIT/制御権/実機heading resetは未再現。既定動作は変更していない。
  docs/SONIC_STARTUP_ABLATION.md、HANDOFF冒頭を参照。GPU再実行やG1起動は不要。
  起動診断11・開始契約4試験をcheck-offlineへ組込み、一括成功（IPC4件は明示skip）。
- 独立レビュー `docs/sonic_startup_diagnostic_handoff_20260930.md` を受領・読了。
  固定モデル/記録IK終点保持/mode0/heading=0の150周期×2条件で、現行保存出力の再現差0、
  関節順序・scale・defaultによる目標式差0、encoder token差0。
  起動Logger paddingは出力へ影響するが、URDF超過は残り、初期10周期の最大目標−保存実測差は
  1.252513→1.719764rad。paddingだけを根因/解決策と断定したり、既定実装へ即採用しない。
  zeroEntryのゼロQuaternion由来gravity=+Zは上流padding固有の条件で、実入力へ捏造しない。
  起動履歴のチャネル別切り分け、既存参照との交差比較、保存生Quaternion/座標系/時刻の照合は完了。
  実機CONTROL開始条件の再現は未完了。既存補間・極値監査を再開発しない。
  文書受領は追加実験/実機動作の新規承認ではない。結果は未送信・保存身体固定の診断。
- 計算目標と実姿勢の差（最大約1.25rad）とURDF外目標を観測。
  実姿勢保持の参照でも差が残る。未実行actionの再帰履歴を閉ループ検証と解釈しない。
  ゼロ履歴・clipping・閾値緩和で結果だけを合格にしない。詳細 `docs/TARGET_AUDIT.md`。
- 9月30日、q/dq/ddq連続の関節参照補間を選択式で実装。既定はIK終点保持のまま。
  GPU人工入力3秒run-ddwfs4mc成功、保存実身体150窓run-ptukt__r推論完了。
  補間は接地/力学/制限を扱う全身計画ではなく、参照生成/モデル適用条件は未完了。
  詳細 `docs/JOINT_REFERENCE.md`。新モードの実機入力/実機出力は試験していない。
- G1側低レベルSDK接続はbuild-only、実際の制御権引継ぎ/復帰、実機初期姿勢遷移、
  500Hz送信・通信断・物理停止の実gateway統合/実検証は未完了。
  要求の状態機械・初期参照・診断watchdogは上記の送信なし実装と区別する。
  通常SONIC constructorはReleaseMode、INITは姿勢変更を伴う。
  プロセス/SSH終了を物理停止と扱わない。詳細 `docs/SONIC_STARTUP_BOUNDARY.md`。
- 最新のユーザー申告（9月25日）は「吊り下げ、両足は地面から離れている」。
  以前の足接地情報に戻さない。吊り下げで立位バランスを検証したと扱わない。
- 停止方法は未回答。以前の「約5秒でdamping」は確認済みと扱わない。
  停止操作・結果・確認条件を質問済み。再開時に同じ曖昧な質問を繰り返さない。
- PIKA形状/質量/較正の未確認部分と、学習モデルの実タスク性能も残る。
  別メンバー/新規PC用の完全自動setupは未提供。

### 実装・記録・確認

- `README.md` を簡潔な入口、`docs/HANDOFF.md` を最新状態、`docs/PROGRESS.md` を履歴とする。
  作業後に更新し、古い「最新」「未実行」「承認待ち」を現状として引用しない。
- `docs/IMPLEMENTATION_TODO.md`はユーザー依頼の当初計画/現在TODO/検証で判明した課題。
  新規課題・完了条件・証拠を更新し、当初の基準と実機未検証を区別する。
- 他フォルダの既存実装、dirty worktree、学習データ、モデル、ログを保存する。
  移植部品の出典/コミット/ライセンス、依存バージョンを残す。
- 秘密鍵の中身/パスワードを保存しない。既存ホスト鍵照合を無効化しない。
- 必要な検査だけ実行する。文書更新だけでGPU/実機試験を再実行する必要はない。
  `make check-offline` は通信なし、`make check-runtime` はローカルIPC、
  `make full-record-check` はgalleriaだけで保存入力を使う。
  GPU/実機runnerの配置・設定を確認し、旧 `make setup` をSONIC環境構築の代用にしない。

## 2026-09-24時点の履歴（現在の方針は上記）

- ユーザーがG1起動を通知（2026-09-24、最新）。SSHによる読取り接続確認は再開。
- カメラ/右シリアル/身体の入力専用統合は読み取り了承後に実施。動作指令の許可とは別。
- 2026-09-24: 入力読み取りと、魚眼の露出/FPS一時変更・保存/復元をユーザーが了承済み。身体/グリッパ動作指令の許可ではない。
- 同日、受信プロセスだけの一時的優先度調整（sudo使用）も「よい」で了承済み。ユーザーが補助を起動し、RR/1で3秒の入力専用試験が完走。補助・対象プロセスは終了済み。恒久的なsudoers/capability/governor変更は範囲外。
- 非実機の実装・検証を進めるためにG1の起動を求めない。途中の区切りごとに継続確認を求めない。

- 目標はLeRobot + GEAR-SONIC + Unitree G1 + AgileX PIKAの開発環境。
- シミュレーションは実行しない。単体試験、記録再生、送信なし検証で開発する。
- 旧Decoupled WBCは比較資産として保存し、SONICと同一視しない。
- 身体・腕・グリッパへの実機動作指令は今回の開発作業では送信しない。
- リモコンのソフトウェア統合は対象外。
- 実装・試験・簡潔なREADME整備までまとめて進め、確認は必要な判断/実機許可に集約。
- システムの承認境界は尊重する。承認不要にするための権限拡張は行わない。

## 旧方針・経緯（参考用、現在の指示ではない）

- 実機への動作指令は禁止。シミュレーションのみ実行する。
- 2026-09-18の明示許可の例外: 右PIKAグリッパ単体の小さな開閉テストのみ許可。
  G1身体・腕・左グリッパ・ポリシーによる実機動作は引き続き禁止。
- 他フォルダの既存実装を変更しない。必要部品は出典・コミット・ライセンスを記録して移植する。
- Decoupled WBCとSONICを区別する。現段階の第一候補はDecoupled WBC。
- LeRobotは学習・推論を担当し、身体制御・低レベル送信はWBC側に集約する。
- 手順はWBC単体シミュレーション、PIKA付きモデル、教師軌道、ポリシー接続の順。
- 依存コード・モデル・実行環境を固定する。未固定・未検証項目を明記する。
- 作業後はdocs/PROGRESS.mdを更新する。ユーザーは慣れてきたため、実装・検証から実行コマンドの提示まで続けて進める（2026-09-14の明示指示）。
