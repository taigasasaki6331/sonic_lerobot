# 右PIKA単体の開閉テスト（2026-09-18）

## 追加: 見やすい大きさへの開閉

ユーザーが「もっと大きく動かしていい」と許可。右だけ0.2→0.4→0.6rad、
頂点で3秒待機、0.4→0.2→0radの1往復を既存ドライバで実施しpassed=true。
頂点到達確認値0.5923rad、戻り到達確認値0.0225rad、disable後0.0061rad/Status0。
port_closed=true、914状態記録。受信再同期警告10回あり、通信品質課題は残る。
記録は同配置先result-larger/report.json。以前のresultは上書きしていない。
新しいラッパーの--opening-angleは0.15/0.6のみを選択可。追加の無断再実行は行わない。

ユーザーが右グリッパ単体の動作指令を明示許可。保持物なし・周囲安全の確認済み。
G1身体・腕・左グリッパ・ポリシーによる実機動作は禁止のまま。

## 実装

LeRobot commit79edf6a95948d0f0d75df1d54d0a5aad305f75a8のpika_gripper.pyを**無変更**で使用。
source SHA256 ef7c397ec33ada894fb164bea633b560e178b7fa1778e5bf89eeb1001be8e63e。
依存はpyserial3.5のwheelを隔離ディレクトリから直接importし、OS/既存venvにインストールなし。
wheel SHA256 c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0。
scripts/test_right_gripper.pyは既存connect/enable/set_angle_and_wait/disable/disconnectを呼ぶ
テスト用ラッパー。フックは記録・鮮度/このテストの角度範囲確認のみ。通信プロトコルは再実装せず。
Unitree SDKや全身ロボットクラスはimportしない。ゼロ点・電流制限・速度設定は変更しない。

## 結果: passed=true

- 初期角度-0.0066 rad、Status0（無効）。
- 目標0.15 rad: 実測0.126 rad、誤差0.024 rad。
- 目標0 rad: 実測0.0152 rad、誤差0.0152 rad。
- 許容差0.025 radの小さな開閉1往復に合格。高精度追従の証明ではない。
- 最後のdisable後、角度0.0062 rad、Status0を確認、ポートclose済み。
- 191状態記録。enable1回、位置目標4回（各目標2回）、disable2回（既存disconnect分を含む）。
- 既存受信処理の4096byte超過/再同期警告が4回発生。警告なしではない。
  継続運転品質や前回の異常電流値の原因が解決したわけではない。
- 事後fuserと該当Pythonプロセス確認は出力なし（一般ユーザーの可視範囲）。
- 本番WBC/LeRobotポリシー駆動の実機タスクを試したものではない。

## 保存先

- tiger: artifacts/gripper-motion/gripper-motion-elufwy/result/report.json
- GPU: /home/gpu-user/g1-pika-training/artifacts/gripper-motion-elufwy/
- G1: /home/unitree/g1-pika-gripper-motion-wGnbzI/result/report.json
- 実行コード/既存ソース/ライセンス/wheelは各配置ディレクトリに保持。

再実行は新しい出力先と現場安全確認が必要。自動起動や常設サービスにはしていない。
今後は既存の幅変換と状態配信を再利用して接続する。全身実機動作の許可とは扱わない。
