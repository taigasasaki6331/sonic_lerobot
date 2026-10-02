# G1実画像からgalleriaでのGPU推論

2026-09-14。右PIKAのD405カラー・魚眼をG1搭載PCで撮影し、開発PCで回収後、
galleriaへ転送。学習済みACTの実推論に成功した。G1へのaction送信は行わない。

- G1画像: artifacts/g1-camera/run-3usdfsex/。
- galleria上の画像・実行スクリプト・結果:
  /home/gpu-user/g1-pika-training/artifacts/image-probe-Ee18Sq/。
- ローカル結果: docs/g1-images-gpu-2026-09-14.json。
- 実装: scripts/probe_gpu_images.py。GPU環境lockとLeRobotコミットを検査し、
  codecのhashを照合。モデルはstrict読込、前処理は学習用rgb_inputをそのまま再利用。
- PNGをRGBとして読んでCHWへ変換し、640x480から128x96へ縮小。
  転送後の2枚のSHA256は回収元と一致。元ファイルの改変なし。
- 診断用の現在幅0.04mを明示入力。実測値ではなく、姿勢stateはcurrent-TCP identity。
  残差幅をcodecで将来絶対幅へ復元。出力10Dは有限、幅予測約0.038891m。
- GPU推論p95は約5.268ms（warmup5回、同じ画像ペア20回）。
  前処理・推論・出力復元を含み、撮影・通信・ファイル読込を除く。

このpassedは疎通のみ。画像は順次取得した静止画、幅は仮値であり、リアルタイム
カメラ閉ループや行動の正しさを検証したものではない。
通信もG1→開発PC→galleriaの回収経路で、計画した直結有線LANでの連続転送は未検証。
推論プロセスはネットワーク禁止のPython監査を使い、SDK/serial/低レベル送信処理を含まない。
依存や既存の学習コードを変更せず、新規診断フォルダ内にスクリプト・画像・結果のみ配置した。
