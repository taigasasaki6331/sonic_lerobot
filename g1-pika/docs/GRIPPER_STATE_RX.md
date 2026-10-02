# 右グリッパ受信診断 2026-09-18

ユーザーが保持物なし・周囲安全・接続リセット許可を確認した後に5秒間実施。
追加インストールなし。既存PikaGripperのconnect/disconnectは使用せず、標準Pythonで
右/dev/pika/right/gripperをO_RDONLYでopen。460800 baud/8N1、raw、echo/IXON/IXOFF無効。
flockとTIOCEXCLで排他、終了時に排他解除してclose。左は開かず、アプリのUART書込は0。
termios/ドライバによる初期化・DTR/RTS変化は別であり、無副作用を保証するものではない。
終了時にecho/HUPCLを元に戻さずraw/HUPCL offのままとする。enable/disable/zero/目標指令なし。

## 結果

- 151,281 byte、正常JSON832件、Positionフィールド832件。
- 最終値: Position -0.0067（旧実装ではrad）、Current 0、Voltage 24.7、Status 0x00。
- raw角度範囲 -0.0068〜2.0。2.0の2件はCurrentも-1080385602。
- JSON不正1件: byte21601で拒否したフレームにNULが混入。
- この電流数値はraw.binに2回実在し、JSON解析が新しく生成した数値ではない。
- 原因は未特定（ファームウェア/通信/機器等を切り分けていない）。
- **診断passed=falseを保持**。受信経路が動くことと実測入力が信頼できることを区別する。
- 終了後fuser/該当pythonプロセス確認に出力なし。ただし一般ユーザーの可視範囲。

記録:

- ローカル `artifacts/gripper-rx/gripper-rx-3abs2q/result/` (raw.bin, frames.json, report.json)
- G1 `/home/unitree/g1-pika-gripper-rx-mpQ9Bd/result/`
- GPU `/home/gpu-user/g1-pika-training/artifacts/gripper-rx-3abs2q/result/`
- 実行時ソースは同GPU/ローカル親ディレクトリのread_gripper_state.pyに保持。

## 実装・検証

scripts/read_gripper_state.py、check_gripper_state.pyを追加。連結JSON・分割受信・
文字列内括弧・非有限値・サイズ上限・観測された外れ値の6テスト合格。
プロトコル参照は固定LeRobot commit79edf6a95948d0f0d75df1d54d0a5aad305f75a8の
unitree_g1_pika/pika_gripper.py。既存コードは変更していない。
受信後、診断用の角度範囲[-0.05,1.72]を追加（旧公称0〜1.67に仮の0.05余裕）。
これは未較正の診断閾値で、物理限界・安全保証ではない。新範囲検査の版は実機再実行していない。
観測値2.0は単体テストで拒否。実機用の時系列鮮度/不連続値/通信断処理は未接続。

次はこの実記録を使って異常値・欠損時の入力拒否と停止境界を実装する。
指先幅への換算/較正は未実施。現行推論の仮幅0.04mをこの角度で置換していない。
本番状態配信はZMQへ統合する方針。今回は有限時間の診断ファイル回収のみ。
