# G1搭載PCへの接続準備

2026-09-14。構成はgalleria（GPU推論）—有線LAN—G1搭載PC（PIKA USB接続）。
PIKAをgalleriaへ直接USB接続する案は撤回済み。WBC配置は搭載PC確認後に決める。

開発PCからの接続先: `unitree@192.0.2.7`。
ユーザーのログでUbuntu 20.04.6 / kernel 5.10.104-tegra / aarch64を確認。
ログイン時のROS選択はFoxy。自動接続での環境初期化は未確認。
ユーザーが受け入れたホスト鍵:
`SHA256:PUBLIC_EXAMPLE_NOT_VERIFIED`。
galleriaからの到達性・接続先アドレスは別途確認が必要。

開発PCの既存鍵ではBatchMode認証失敗。新規専用鍵を作成した:
`/home/developer/.ssh/g1_pika_g1_ed25519`（秘密鍵はリポジトリに保存・転送しない）。
公開鍵指紋: `SHA256:PUBLIC_EXAMPLE_NOT_VERIFIED`。
公開鍵登録後、専用鍵のBatchMode/StrictHostKeyChecking=yes接続成功。パスワードは記録しない。

開発PCの端末で実行:

```sh
ssh-copy-id -i /home/developer/.ssh/g1_pika_g1_ed25519.pub -o StrictHostKeyChecking=yes unitree@192.0.2.7
```

認証後は環境・カメラ・既存制御の読み取り確認を行う。
SSH鍵はOSアカウントへのアクセス権であり、技術的な読み取り専用制限ではない。
実機動作指令は禁止を維持。OS更新・既存サービス停止も行わない。

## 接続後の読み取り確認

後続の有線接続確認: galleria enp2s0=192.0.2.12 → G1 eth0=192.0.2.11。
eth1はDOWNのまま。実際の有線経路を確認済みで、既存ネットワーク設定は変更していない。
ping3回損失0、平均0.160ms。GPU PCからの専用SSH鍵認証も成功。
GPU専用秘密鍵は /home/gpu-user/.ssh/EXAMPLE_RUNTIME_KEY（GPU PCから持ち出さない）。
G1のauthorized_keysに公開鍵を追加し、restrict,from="192.0.2.12"を指定。
PTY・転送等は禁止だが、シェルコマンド自体を読み取り専用に制限するものではない。
旧known_hostsは残し、確認済み公開ホスト鍵をプロジェクト専用ファイルへ分離。
GPU上: /home/gpu-user/g1-pika-training/artifacts/g1_known_hosts_verified_20260914。
有線側の鍵を、既存の信頼済みWi-Fi接続で読んだホスト公開鍵と照合した。

- NVIDIA Orin NX Developer Kit、RAM約15 GiB（available約12 GiB）、ストレージ空き約1.8 TiB。
- Ubuntu 20.04.6、Python 3.8.10、ROS Foxy/Noeticのディレクトリあり。
- cv2/numpyはPython3 -Iで検出、pyrealsense2/zmqは未検出。ffmpeg/v4l2-ctlはPATH上になし。
  GStreamerとDockerのコマンドあり。バージョン固定・実際の画像取得はまだ未検証。
- 右D405（EXAMPLE_DEVICE_SERIAL）のカラー候補video10、魚眼capture候補video12、
  PIKA USBシリアルttyUSB4。番号は観測時点のみ。G1本体D435i（255323061835）とは別機器。
  左D405（012345678901）は今回の列挙にはない。
- eth0 UP: 192.0.2.11/24、wlan0 UP: 192.0.2.7/24、eth1 DOWN。
  ip route get 192.0.2.9 はwlan0を選択。現時点でgalleriaへの経路はWi-Fiであり、
  計画した有線LAN経路は未確認。既存eth0やルーティングは変更していない。
- master_serviceなど既存サービスが稼働。停止・再起動・SDK起動はしていない。

次はgalleria—G1間の有線接続状態を確認し、既存ロボット網と干渉しない経路を準備する。
後続で `make g1-camera-check` によるG1上の右D405/魚眼撮影とSSH回収に成功。
結果はartifacts/g1-camera/run-3usdfsex/。各30枚読んだ最後の画像を保存。
左手は再列挙でも未検出だが、ユーザー指示で深追いしない。
状態購読・GPU推論への接続はまだ未実行。順次撮影で同期は未検証。
