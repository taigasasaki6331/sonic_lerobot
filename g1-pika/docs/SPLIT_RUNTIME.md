# GPU PCへLeRobotとWBCを集約（2026-09-15）

GPU PC上の別プロセスでLeRobot ACT（CUDA）とDecoupled WBC（CPU）を動かす。
このPCはMuJoCo物理計算・模擬センサー送信・受信指令の検査/適用のみを担当し、
IK・バランスポリシー・重力補償を計算しない。G1には接続しない。

このPCから画像/記録state/シミュレーション身体状態を送信し、GPU PCから
29関節のq/dq/tau/kp/kdを返す。Unitree LowCmdではなくシミュレーション専用JSON。
両端のControlGuardで位置範囲・有限値・順序・連番を検査し、受信側は
検査済みコピーだけをMuJoCoのPDアクチュエータへ適用する。

## 起動

最終検証は [split-runtime-2026-09-15.json](split-runtime-2026-09-15.json)。
`artifacts/split-runtime/run-4eb3ocoz/` で全合格。
206 ACT action・3000 WBC関節目標・60シミュレーション秒を完走し、MuJoCo警告0。
単体40件合格。通信断/旧セッション/遅延では200件でローカル適用を止めた。
GPU側が遅れて計算した201件目は適用していない。両GPUサービスの正常終了を確認。

通常時p95: 画像なし往復11.895ms、画像付き往復57.439ms、WBC計算1.545ms、
GPU内ACT往復6.798ms。基準のPNG経路とは入力サイズ・配置・再生方式・標本数が異なる。
最小骨盤高さ0.744m、最大傾き0.095rad、最大水平移動0.133m。

```bash
make -C /home/developer/workspaces/g1_pika_ws/g1-pika split-runtime
```

単体40件、206フレーム全軌道・60シミュレーション秒、関節指令通信の断線・
旧セッション・0.8秒遅延を一括検証し、プロセス終了とレポート回収まで行う。
GUIはこの新しい経路にはまだ追加していない。`mock-runtime-view` は旧配置の表示用。

`artifacts/split-runtime/deployment.json` に保存した専用環境を再利用する。
初回だけ固定パッケージとvendorソース/モデルをGPUへコピーするため約2.4GBを転送する。
別の専用環境を作る場合のみ `SPLIT_ARGS=--new-deployment` を指定する。
30フレームの短縮確認は `SPLIT_ARGS=--quick`。本番環境の構築コマンドではない。

接続IP/SSH鍵は `assets/network/mock-runtime.json` と共通。
PC間WBCはGPU 192.0.2.9:6160、GPU内ACTは127.0.0.1:6161。
PC間は許可送信元192.168.1.25に限定。IPフィルター/UUIDは暗号認証ではなく、
信頼できる開発LANに限る。SSHは配置・起動・終了後の結果回収のみ。

Ctrl+Cで中断できる。中断時はリモート側がタイムアウトまで残る場合がある。
WBCの受信待ちは15秒、ACTの待機上限120秒、起動側timeoutは600秒。
通常完了ではSTOPで両サービスを終了する。既存サービスは停止/変更しない。

## 環境と保存場所

GPU専用配置: `/home/gpu-user/g1-pika-training/artifacts/split-wbc-bHU7TO/`。
Ubuntu22.04/Python3.10.12が両PCで一致することを確認し、新規venvへローカルの
固定site-packagesを複製した。既存GPU用Python3.12/CUDA環境は変更していない。
WBC環境は起動ごとに `requirements-wbc.lock` の全固定パッケージとモデルhash、
vendorのHEAD/差分を照合。異なるOS/ABIへの一般的なインストーラではない。
通常venv作成は最初失敗したため、ensurepipを使わないvenvへ複製する方式に変更した。
その初回の未使用ディレクトリ `split-wbc-ZEpNCh` は残してある。削除はしていない。

ローカルは `artifacts/split-runtime/run-*/` に入力・ログ・GPU推論記録・WBC結果・
受理された関節目標・時間分解・コードhash・合否を保存する。
元LeRobot、PIKA既存実装、固定モデルは変更せず、専用配置の自作スクリプトのみ同期する。

## 遅延削減

画像は学習と共通の `rgb_input` で640x480→128x96へ前処理してから、
float32をzlibで可逆圧縮する。量子化やfloat16変換はしない。
GPU側は前処理コードhash・展開サイズ・shape・範囲・有限値を確認し、二重resizeしない。
先頭フレームのJSONは565,135→320,818 bytesに縮小した。
旧PNG経路と新経路の先頭30推論結果の最大差は0だった。

画像は必要な制御tickだけ送り、その他は身体状態と関節目標の小さな往復にする。
画像なし往復、画像あり往復、WBC計算、GPU内ACT往復を分けて計測する。
デコード/前処理の一部は記録入力の事前生成へ移っているため、旧約111msとの比較を
そのまま実カメラのend-to-end改善率と解釈しない。

## 重要な制限

この経路は**lockstepシミュレーション**。通信/推論を待っている間は物理時間も止まる。
WBCは50Hzのシミュレーション時刻、ACTは25Hz相当の順次再生であり、
50Hz身体制御や30Hzカメラ推論のwall-clock実時間性能を証明しない。
画像と10D stateは記録episode39、身体状態はMuJoCo。画像閉ループではない。
実測G1状態の変換、身体状態推定、TCP/質量校正、グリッパ実測/駆動は未実装。

旧セッション・期限切れ・通信断では、後続関節目標を適用せずシミュレーションを終了する。
0.5秒は受理期限、ソケットの待機上限は0.6秒なので、無応答時の検出は最大0.6秒程度。
これは実機の安全停止ではない。以前のポリシー断時の「WBCを継続して目標保持」とも別。
GPUが途中で計算したaction数と、ローカルで実際に適用した関節目標数を区別して記録する。
実機制御権・停止遷移・低レベル送信・実タスク成功は引き続き未完了。
