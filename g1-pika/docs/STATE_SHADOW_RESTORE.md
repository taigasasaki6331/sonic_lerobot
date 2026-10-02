# SSD換装後の受信専用経路（2026-09-18）

起動（tigerから）:

```sh
make -C /home/developer/workspaces/g1_pika_ws/g1-pika state-shadow
```

galleriaへ小さな診断コードを新規ディレクトリに配置し、G1の/tmpで状態受信器を
ビルドする。5秒の状態確認後、右2視点と状態30組を有線ZMQでgalleriaへ送り、
固定LeRobot ACTで推論して記録。終了後に結果JSONと配置コードをtigerへ回収する。
サービス登録・シリアルポートopen・実機動作指令・全身制御の起動は行わない。
SSHは配置・起動・記録回収、DDSはG1内部のrt/lowstate受信専用。

## 成功記録

- `make state-shadow` が終了コード0で完了。
- ローカル: `artifacts/state-shadow/state-shadow-8QqGfK/` のstate-check.json / live-report.json。
- GPU画像・stderrを含む全記録: `/home/gpu-user/g1-pika-training/artifacts/live-shadow/run-hd7f1y1k/`。
- 5秒の状態受信4,619件、不正値0件、tick更新4,447件、最大受信間隔2.139ms。
- 実画像/状態30組→推論30件。通信込みp95 34.116ms、推論p95 7.500ms。
- これは5組/秒の診断であり、30Hz実時間性能・タスク成功・実機安全性を意味しない。
- ACT入力のTCPはidentity、幅は仮値0.04m。G1状態は対応を記録しただけ。
  CRC・実測幅・実機状態からのWBC入力・実機停止系は未完了。
- G1側のカメラ/受信器終了とZMQ 6158待受終了を確認。

## 換装後の環境と変更

- G1 Ubuntu22.04.5 / aarch64 / Python3.10.12 / kernel5.15.148-tegra。
- DDS0.10.2は/usr/localに既存。OpenCV4.8.0、ZeroMQ4.3.4も既存。
- IFはenP8p1s0。受信器はG1_STATE_INTERFACEの明示を必須とし、不在/不正IFは購読前に拒否。
- 接続設定はassets/network/g1-runtime-access.json。旧SSH鍵ファイルは使わない。
- 生成器idlcはtigerの/tmpにCycloneDDS commit
  `9995905bce6c4cf9f740d6438bbf7fcfd1c83dfd`からビルド。
  CMake: BUILD_EXAMPLES=OFF, BUILD_TESTING=OFF, ENABLE_SSL=NO,
  ENABLE_SECURITY=NO, ENABLE_SHM=NO。
  実行時LD_LIBRARY_PATHを同ビルドlibだけに固定して既存ROSとの混在を防止。
- scripts/state_receiver/generated/にIDL生成済みC/Hとhash manifestを保存。
  既存State.idlの出典/ライセンスは同ディレクトリの親を参照。
  G1へのidlc/ROS/pip/apt追加インストールは不要だった。
- Python構文/diff検査、ローカルCビルド、不在/不正IFの拒否を確認。

## 左右カメラ

同じシリアルのDECXINが2台あるため、by-idを左右選択には使わない。
右D405 serialEXAMPLE_DEVICE_SERIALに対応するby-pathを確認し、魚眼は同じハブのUSB2側を指定。
sysfsの1-2.1.4-port4と2-2.1.4-port4、右ハブport2のpeer関係も読み取り確認した。
カメラ起動時にD405シリアルとポート一致、魚眼のDECXIN所属を検査。
これはUSB接続による対応で、画角・較正の確認ではない。差し替え時は設定を再照合する。
左魚眼もUSBでは列挙されたが、左D405は今回列挙されていない。

## 別途必要: PIKAシリアルドライバの復旧

G1には1a86:7522のUSB Serialが2台あるが、lsusb -tのDriverは空でTTYが生成されていない。
FTDI ttyUSB0〜3は別機器なのでPIKAと誤認しない。modinfo ch341/ch343はnot found。
tigerのch341では1a86:7522 aliasを確認したが、x86_64用モジュールはG1へ流用不可。
G1用には**5.15.148-tegra/aarch64に合い、1a86:7522を対応IDに含むch341**が必要。
nvidia-l4t-kernel-headersは36.4.3-20250107174145がインストール済み。
別途ユーザーがインストールする方針。適合ソース/ビルド/ロードは本作業では未実施。
ドライバのbind/openはPIKA側をリセットする可能性があるため、ロード後も自動でグリッパを開かない。

## 失敗も保持

最初の生成器は既存ROSライブラリ混在で失敗し、未完成C/Hの遠隔ビルドも失敗。
固定libとSHM無効で解消し、配置前hash確認を追加した。
次は同型魚眼2台の拒否で停止（run-9tx_26v8）。左右を推測せずUSB対応を確認して修正。
run-cf_31sjkは30組成功したがscp結果回収で失敗。回収を修正した最終runは正常終了。
失敗を合格扱いせず、一時ディレクトリも上書きしていない。
