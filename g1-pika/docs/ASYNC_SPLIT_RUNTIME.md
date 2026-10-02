# 非同期の身体/画像経路（2026-09-15）

## 到達点と未合格を分ける

非同期化を実装し、**GPU PC内のloopback診断**は全合格した。
物理60.000秒に対しwall-clock60.000068秒、206推論、2999関節目標を適用。
最大指令年齢50ms、最大物理時刻遅れ0.208ms、MuJoCo警告0。
身体往復p95 3.059ms、画像往復7.750ms、WBC計算1.657ms。
単体45件と、身体通信断・旧応答・身体応答遅延・推論遅延の4ケースも合格。
結果: [async-runtime-loopback-2026-09-15.json](async-runtime-loopback-2026-09-15.json)。
詳細: `artifacts/split-runtime/run-t72e4a86/`。

一方、**このPCとGPU PCのWi-Fi経路は未合格**。
短縮12秒/30推論は成功したが、60秒試験は206推論を受信した後、18.505秒で
100msの指令鮮度期限に達し、833指令でシミュレーションを終了した。
その試験のWBC計算最大は2.380ms、物理時刻遅れ最大5.759ms。
試験中の期限は変更せず、失敗を成功に読み替えていない。
結果: [async-runtime-wifi-2026-09-15.json](async-runtime-wifi-2026-09-15.json)。
詳細: `artifacts/split-runtime/run-wvvavyv0/`。

読み取り確認でGPUへの経路はwlp1s0（Wi-Fi）、eno1は未接続だった。
ネットワーク設定は変更していない。loopbackでは実行PCも変わるため、Wi-Fiだけが
唯一の原因と断定せず、次にPC間有線経路で比較する。G1はまだ不要。

## 実装

- 画像と身体状態のREQ/REPを別ソケット・別workerへ分離。
  ソケットの生成・送受信・破棄は各worker内だけで行い、物理ループはpollのみ。
- GPU側ACTは結果をGPU内ZMQ PUB/SUBでWBCへ渡す。
  WBCは推論応答を待たず、現在受信した身体状態から制御計算を進める。
- MuJoCoはwall-clockに合わせて200Hzで進む。通信中にも物理計算が進むことを
  待機中の物理step数で確認。初期関節目標を取得するbootstrapだけは開始前に待つ。
- 身体状態の送信機会は50Hz、画像要求は最大30Hz。応答が遅い場合は次の送信機会を
  見送るため、実更新率を50/30Hzに固定できると主張しない。
- PUB/SUBは欠落し得る。h1 actionは欠番・旧セッション・旧時刻を受け付けず試験停止。
  モデルhash、セッション、seq、GPU内の発行時刻を確認する。
- 通信障害後は同じ診断セッションへのSTOPを別REQソケットで試み、残留待機を解消。
  失敗時にも自動再開・自動再適用はしない。

推論に0.8秒の遅延を注入した試験では、遅延要求後も26件の関節目標が適用された。
WBCの指令年齢は約20ms以内を維持し、画像側の0.5秒期限で試験を停止した。
GPUが遅れて返した6件目のactionはWBCに適用せず、採用actionは5件のまま。
身体通信の異常では200件で関節目標の適用を止めた。

## 起動

このPCをMuJoCo側として2 PC通信を試すコマンド（現Wi-Fiでは未合格）:

```bash
make -C /home/developer/workspaces/g1_pika_ws/g1-pika async-runtime
```

通信経路を除いたGPU PC内診断:

```bash
make -C /home/developer/workspaces/g1_pika_ws/g1-pika async-runtime ASYNC_ARGS=--gpu-loopback
```

後者では記録入力を事前配置し、MuJoCoもGPU PCで動かす。2 PC通信の合格ではない。
短縮試験は `ASYNC_ARGS=--quick`。既存 `make split-runtime` はlockstep経路として残す。
専用配置と設定は [SPLIT_RUNTIME.md](SPLIT_RUNTIME.md) を参照。
新経路は身体6160番、画像6161番、GPU内PUB/SUBは127.0.0.1:6162番。
外向けポートは許可IPを制限するが、暗号認証ではない。開発LAN限定。

## 安全性と残作業

指令/応答鮮度100ms、画像応答500ms、物理時計遅れ50msを検査。
検査は5msの物理tick単位のため、停止時の観測値は100msを最大約1tick超える場合がある。
期限超過時は次の物理stepへ進まず、シミュレーションを終了する。実機の安全停止ではない。
この結果は通常Linux/Pythonでの短時間測定で、hard real-time保証ではない。
WBC自体も受信状態に応じて計算する構成で、独立した厳密50Hz周期スケジューラではない。
画像は記録データであり、実カメラ閉ループ・撮影/前処理込みの遅延測定ではない。

G1への接続・動作指令・グリッパ操作なし。全ケースでGPU側サービス終了を確認した。
次は有線2 PC経路の同条件比較。その後の実機状態変換・実測幅・校正・制御権・
停止遷移・低レベル送信の検証は引き続き別途必要。
