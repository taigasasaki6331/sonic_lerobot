# G1 CH341復旧用（2026-09-18、インストール確認済み）

ユーザーのsudo実行後、2台のch341 bind、右リンク→ttyUSB5、ttyUSB4/5の
unitree:dialout/0660をSSH読み取りで確認済み。インストールスクリプトの再実行は不要。
実通信・再起動後の再認識は未検証。以下は復旧時のソース・作業手順の記録。

ソース: Linux stable v5.15.148、commit `6139f2a02fe0ac7a08389b4eb786e0c659039ddd`。
https://github.com/gregkh/linux/blob/6139f2a02fe0ac7a08389b4eb786e0c659039ddd/drivers/usb/serial/ch341.c

ch341.c SHA256: `f66d070eab6235b8a5c7a06a283d2feecb8fa3d81bc1323c847c2d2cbf7bd410`。
無変更で使用。GPL-2.0、同じcommitのLICENSES/preferred/GPL-2.0をLICENSEとして同梱。
新規ドライバの自作ではなく、既存のLinux標準ドライバの追加ビルド。

G1の既存5.15.148-tegraヘッダー/Module.symversでビルド成功。
vermagic `5.15.148-tegra SMP preempt mod_unload modversions aarch64`、
alias `usb:v1A86p7522...`、依存usbserialも既存。ロード互換性はまだ未検証。
ビルド成果は `/home/unitree/g1-pika-ch341-xaK9Y1/ch341/ch341.ko`。
module.sha256はこのビルドのhash。再ビルド時には検証後にhashも更新する。

```sh
make -C /lib/modules/5.15.148-tegra/build M=/home/unitree/g1-pika-ch341-xaK9Y1/ch341 modules
```

## G1端末からのインストール

グリッパの周囲を空け、保持物を取り除いてから実行する。
ドライバbind時にも初期化/DTR/RTS操作があるため、アプリ指令なしでもリセットの可能性がある。

```sh
sudo sh /home/unitree/g1-pika-ch341-xaK9Y1/ch341/install.sh
```

sudoパスワードはユーザー自身がG1端末で入力。こちらには共有しない。
既存ファイル/モジュールがある場合は停止し上書きしない。途中失敗時は再実行せずログを確認。
システムへ追加するのは次の2ファイルとdepmodの索引更新のみ:

- /etc/udev/rules.d/70-g1-pika-serial.rules
- /lib/modules/5.15.148-tegra/updates/g1-pika/ch341.ko

udevは7522のTTYのみunitree所有/0660、ModemManagerのプローブを除外。
右の現在の接続位置1-2.1.4.4.4に/dev/pika/right/gripperを付ける。
左は標準by-pathを使用し、未確認の左右名は付けない。
旧tigerのsensor_serial.rulesは全7522にttyUSB50を付けるので移植しない。
別USBポートへ移動したら右のルールを再照合する。
ロード後は機器列挙のみ。シリアルopen・既存グリッパconnect関数は呼ばない。
再起動後の自動ロードはUSB aliasに任せる。カーネル更新時は再ビルドが必要、DKMSは未導入。

戻す場合は使用プロセスがないことを確認してch341をunloadし、上記の追加2ファイルだけを
退避してdepmod/udevルールを再読込する。FTDIや既存udevファイルは触らない。
