# グリッパ既存実装の再利用調査

2026-09-18。独自の保護機構を拡大せず既存コードを先に確認する、というユーザー方針に従う。
本作業はソース調査のみで実機ポートを開かず、既存コードも変更していない。

## 確認した出典

- LeRobot: vendor/lerobot、commit79edf6a95948d0f0d75df1d54d0a5aad305f75a8。
  src/lerobot/robots/unitree_g1_pika/pika_gripper.py、unitree_g1_pika.py。
- 既存PIKA ROS: /home/developer/workspaces/pika_ws2/src/pika_ros、
  commit0f7f6b75a349ceccb252628f5f48a28aaf5c7b6b。
  src/sensor_tools/src/serial_gripper_imu.cpp（該当ファイルのgit差分なし）。

## 結果

1. LeRobotの_parse_frameは不正JSONを無視し、正常JSONのPosition/Currentをそのまま保存する。
   受信角度の範囲検査・外れ値除外・幅への換算はここにはない。
   set_angleの0〜1.67制限は送信側であり、受信検査と混同しない。
2. ROSのreceiving（766行以降）は受信角度を0〜1.67へクリップし、範囲外ならerror=true。
   その後getDistance（608行以降）でリンク機構から幅を計算し、
   `2*(getDistance(angle)-getDistance(0))`をdistanceとして配信する。
   電流値はそのまま。コメントアウトされた電流制限処理は有効な保護と扱わない。
3. 今回の-0.0067はROS既存処理なら角度0/error=trueに、2.0は1.67/error=trueになる。
   クリップは通信異常の修復ではなく、2.0を全開相当の幅に変換する点にも注意。
4. 前回診断の「不正JSON1件でもpassed=false」と仮の[-0.05,1.72]範囲は
   診断コード独自の判定であり、既存PIKAの合否基準ではない。
   生データの異常は実在するが、独自基準の不合格を通信全体の故障と断定しない。

## 採用方針

- 既存の受信/状態型とROSの角度→幅の式を優先し、根拠なしの線形換算を作らない。
- 受信専用運用に必要な差分（接続/終了時のenable/disableを呼ばない）だけを分離する。
- 幅へ換算する場合も元角度・既存error相当を保持し、クリップ値を正常な実測値と偽装しない。
- 学習データの幅生成経路との一致を確認してから、現行推論の仮幅0.04mを置換する。
- 独自安全基盤の追加を次段階の前提にはしない。実機動作指令禁止は継続。

このターンでは移植・ポリシー接続は未実施。過去の診断結果/コードは履歴として保持。
