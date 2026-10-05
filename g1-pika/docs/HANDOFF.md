# 引き継ぎ（2026-10-02整理）

## 最新：出力直前の時刻・停止検査を修正

状態コピー後に時刻を採り、sink直前にも最新入力／停止／型式／100ms年齢／10ms経過を再検査する。
実呼出開始時刻をkernelへ記録し、watchdogのpacket／historyコピーを軽量statusへ分離した。
writer27条件・runtime3経路、最新cloud-checkは131成功／3skip／exit0。
SDKはobject compileのみ。以前の期限失敗を保持し、短時間成功を実時間・物理成功にしない。
[今回の検証](cloud-validation-admission-20261005.json)／[履歴](PROGRESS.md)。
以下の130成功／期限失敗は修正前の履歴。実入力147/150範囲外と実SDK／実機の未検証は継続。

## 2026-10-05 共通ownerで起動・停止・明示復帰を統合

指定ブランチ`codex/cloud-handoff-20261002`、起点`22999ade4b4035891157e9897c44172e2864acfa`からCloud CPU開発を継続。
前環境の未コミットworktreeは参照できず、会話記録と起点ソースから実装を復元した。
`body_owner_lifecycle.hpp`をG1-local record runtimeとbuild-only `UnitreeBodySession`で共有する。
初期化／制御権取得候補／初期姿勢遷移／通常制御／正常・異常停止／明示復帰／終了を分離。
record transportに実機用契約boolを人工的に付与せず、scopeを分け、SDK transportのrecord利用を拒否する。
同じownerだけがquery/release/publish/stop/restore/closeを行う。RPC後も局所期限・停止を再検査。
停止前に他workerをjoinせず、停止候補最大1回、復帰は局所操作のみで自動復帰・再armなし。
physical scopeは独立した初期姿勢確認契約が必要で、診断phaseを昇格させない。
SDKはflag0/1 object compileのみ。実SDKリンク・起動・機器I/O、最新G1/aarch64 buildは未実施。

ルート`make cloud-setup`、`make cloud-check`、`make cloud-body-runtime BODY_SCENARIO=normal|body_expiry|recovery`。
後者は既存envelope／局所worker／native ownerのin-process fixture。ZMQ配送は検証しない。
人工body・CRC metadata・ownershipはソフトウェア試験だけの入力。物理停止・実制御権の確認flagはfalse。
共通owner18条件、既存adapter19条件／native writer24条件、3種類のruntime通し試験を追加・確認。
一括Cloud検証は未合格：最新は130成功／3skip／normalのdeadline fault1失敗（make exit2）。
online単独再確認も2期限失敗。通し経路の成功履歴と安定性の未達を区別する。
実threadの10ms期限超過で停止した試行も保存し、閾値を緩めない。詳細結果は[PROGRESS](PROGRESS.md)。
このCloudではIPC bindが`EPERM`、`/proc`のPID表示がkill名前空間と異なるため、IPC2件と対象限定cleanup1件を明示skip。
初期setupはPython3.12／numpy1.26.4で成功、依存不足なし。既存GPU／G1／MuJoCoは起動しない。

[共通ownerとコマンド](BODY_OWNER.md)。実入力147/150のURDF範囲外、実起動／姿勢／支持・装着、
物理停止／実時間性／復帰の効果、PIKA統合／視覚・実タスク性能は未解決。
実演データとACT重みは既存保存資産として維持。今すぐユーザーの機器操作・資格情報は不要。

> 公開用コピー：ネットワーク値・機器識別子・ローカルパスは例へ置換。保存試験結果は原本の記録で、例設定で実機試験した証拠ではありません。クラウドから機器接続・実機指令を行わないでください。


以前の引き継ぎ・証拠は[2026-10-02版](https://github.com/taigasasaki6331/sonic_lerobot/blob/22999ade4b4035891157e9897c44172e2864acfa/g1-pika/docs/HANDOFF.md)に保存されています。
