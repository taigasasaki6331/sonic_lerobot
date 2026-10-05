# 進捗

## 2026-10-05 継続：native出力直前の時刻検査を修正

利用者の停止理由の確認を受け、送信なし作業を再開。前回はコミット保存後にターンを終了したため、
その後の実装処理は実行していなかった。継続許可やG1起動を待つ条件ではない。

writerの状態コピー前に採った時刻を、コピー後の検査へ使っていた箇所を修正。
同一ホストの新しい受信がコピーへ入ると、古いpoll時刻より未来に見える余地もあった。
時刻はコピー後に取得し、sink直前に最新状態・停止・型式・body/reference年齢・10ms経過を再確認する。
実sink呼出開始をkernelへ記録し、古いpoll時刻を次の出力間隔の起点にしない。
監視のhot pathを軽量statusへ分離し、5msごとのpacket／owner historyコピーを外した。
最終reportには失敗を含む最大観測gap、admission遅延、停止時のbody/reference年齢を残す。
旧snapshotのC ABI配列は拡張せず、容量検査付きの追加APIで取得する。
この修正が以前のCloud scheduling faultの根因をすべて解消したとは結論しない。

writer27条件成功：最初の出力までの遅延、10ms境界、出力直前のbody/reference期限、型式変更・停止優先、
actual call startによる次周期の時刻基準を検査。既存のSDK-free実thread／25ms遅いsinkの停止も維持。
個別runtime通常／身体期限切れ／明示復帰3件成功。
ルートmake cloud-checkは20スクリプト／134件、131成功・3明示skip・exit0。
SDK flag0/1 object compile成功。py_compile／git diff --check成功。
実SDK I/O／G1／GPU／MuJoCo／カメラ／シリアル／DDS command publisherは起動しない。

最新cloud-check-1zmg5uuw：normal通常2394回／受理71、recovery通常2397回／受理72、owner終了。
body_expiry通常1897回／受理21、身体年齢100.315msで期待fault、通常再開なし・owner終了。
3件の最大観測gapは3.770ms／3.359ms／6.813ms。これは当該短時間fixtureだけの計測で、実時間保証ではない。
人工姿勢／CRC metadata／ownership、独立packet CRC一致を実G1の姿勢・制御権・停止の証拠にしない。
実入力147/150範囲外と、物理停止・SDK blocking・実起動・実タスクの未検証は維持。
以前の失敗はcloud-validation-20261005.jsonと既存artifactsに保存、新結果は[今回の検証](cloud-validation-admission-20261005.json)。
[共通owner](BODY_OWNER.md)とHANDOFF／TODOへ反映。

## 2026-10-05 Cloud CPUで共通ownerを統合、期限超過・環境制約も保存

指定ブランチ／起点22999adeから再取得。前環境の未コミットworktreeは参照できず、会話記録から復元した。
rootのπ0/π0.5コード、main、データ・ACT資産・固定vendor・既存証拠は変更しない。
READMEを簡潔なCloud入口へ変更し、旧全文は既存Git履歴に保存。

body_owner_lifecycle.hppで初期化／制御権取得候補／初期参照／通常制御／通常・異常停止／明示復帰／終了を分離。
record runtimeとSDKのUnitreeBodySessionが同じownerを使用する。record APIはmemory backendに固定。
query/release/publisher/通常出力/停止/復帰/closeは単一ownerだけ、RPC後にも局所期限と停止を再確認。
物理contractを人工的にtrueにせず、record scopeとphysical scopeを分けた。
physical初期姿勢確認には別途の局所契約入力が必要。bool・scope・文字列を物理証拠にしない。
停止候補最大1回、復帰は局所明示操作のみ。復帰後も再出力／再arm不可、closeは暗黙復帰しない。
owner履歴、writer終了／owner終了、faultラッチ、復帰ACKを最終journalへ残す。

ルート実行：`make cloud-setup`成功（Python3.12／numpy1.26.4、既存venv専用、依存不足なし）。
初回`make cloud-check`は127成功／IPC2skip／cleanup1失敗。
この環境では`os.getpid()`=5に対し`/proc/self/status`のPid=1448、NSpid=1448/5だった。
Cloud試験は番号不一致時、子processの開始・cleanupの実行前に明示skipする。
自分の子processへ直接terminateする後始末は維持。別名前空間の/proc番号をkillへ変換しない。

新規共通owner18条件、既存adapter19条件、native writer24条件成功。
SDK flag0/1 object compile成功。固定CycloneDDS headersのoverloaded-virtual等の警告あり。
SDKリンク・constructor実行・DDS登録／publisher・実機I/Oなし。
py_compile、git diff --check、Cloud起動入口のMake dry-run成功。

`check_body_runtime.py`の最初の個別一括は3件成功（cloud-check-ld86aawm）：

| 人工シナリオ | 通常native出力 | 受理目標 | 結果 |
|---|---:|---:|---|
| normal | 2402 | 71 | 初期参照／整定／通常制御／停止／owner終了 |
| body_expiry | 1907 | 23 | peer目標継続中の局所身体期限fault、停止候補／owner終了 |
| recovery | 2401 | 71 | 通常停止後に明示復帰、再出力拒否／owner終了 |

すべて最後のnative packet CRCが独立Pythonと一致、物理／hardware確認flagはfalse。
direct版はin-process envelopeでZMQ配送を検証しない。人工の姿勢／CRC metadata／ownershipをG1の成功にしない。

**一括Cloud検証は未合格**。最新20スクリプト／134件の実行は130成功／3skip／1失敗、make exit2。
cloud-check-_j7oerd6では身体期限切れと明示復帰は成功、normalがwriter_deadline_gapで停止。
前のcloud-check-xagj1rqlはnormal/recovery成功、body_expiryが起動中の同fault。
cloud-check-4tt41ggtは3シナリオとも期限fault（身体gap100ms超を含む）。
初回run-_i0yg7drのrecoveryも同faultで中止。閾値緩和／clip／自動再arm／試行内retryなし。
最後のonline単独再確認も17成功／1skip／2失敗（reference age107.84ms、queued camera expiry）。
名前空間制約の確認は明示skip。timing試験をskipへ変換して合格にしない。
Cloudでの期限／スケジューラ安定性は未解決で、単発成功を可用性・500Hz実時間保証にしない。

追加`check_local_body_service.py --ipc`は5成功／2失敗。両失敗はIPC bindのEPERM。
通常cloud-checkのIPC2skipを維持する。IPC版のruntimeはこの環境で配送未確認。
socket pathは短い/tmpにして長いcheckout由来のUNIX socket長制約を避けた。

結果・各試行のphase／fault／出力数／CRC／source SHA／ログSHAは[cloud-validation-20261005.json](cloud-validation-20261005.json)。
人工入力fixture／target replies／reportはartifacts/body-runtimeへ全試行を保存、実ログや認証情報は公開しない。
追加入口はルート`make cloud-body-runtime BODY_SCENARIO=normal|body_expiry|recovery`。
SDK-free source packageに共通owner headerを追加し、既存G1-local launcher用のSHA manifest／現地compile経路を維持。
G1/aarch64の新配置／build、実SDK link／ownership／姿勢／送信／停止／復帰は未検証。
147/150範囲外、右PIKA実構成、支持／物理停止、実時間性、視覚／把持／実タスク性能は残る。
GPU／G1／MuJoCoは今回起動せず、ユーザーの機器操作・資格情報は今は不要。
[共通owner](BODY_OWNER.md)、[TODO](IMPLEMENTATION_TODO.md)、[HANDOFF](HANDOFF.md)へ反映。


以前の進捗・失敗・実入力／シミュレーション証拠は[2026-10-02版](https://github.com/taigasasaki6331/sonic_lerobot/blob/22999ade4b4035891157e9897c44172e2864acfa/g1-pika/docs/PROGRESS.md)に保存されています。

GitHub保存時の自動承認レビューが、履歴文書の接続・操作情報を含むアップロードを拒否。
安全な代替として、今回の文書をCPU実装・検証に限定し、既存履歴は起点コミットへの参照で保持する。
BODY_IO_ADAPTER／BODY_LIFECYCLE／BODY_WRITERの既存全文は変更せず、今回の統合説明はBODY_OWNERへ集約する。

自動承認レビューはonline_input_sources.pyのアップロードも運用接続情報を理由に拒否。
この補助変更は公開対象から外し、既存公開版を変更せず保持する。PID guardの試行版はローカルGit履歴に保存。
Cloud試験は名前空間不一致でcleanupへ到達しない。実環境での対象限定終了とPID namespace整合は未検証。
