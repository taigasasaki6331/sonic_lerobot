# LeRobotオフライン推論

## 入力調査の結果（2026-09-14・続報）

`make policy-input-check` で読取監査を再実行できる。

- checkpointのaction/stateについてmean/std/min/max/countの全10組が、
  `data_2608261323_g1_zero_relative_h1_final_50ep` の統計をfloat32化した値と完全一致。
  学習元データの有力候補だが、統計一致だけでは学習コード・全データの同一性は証明できない。
- 50ep版と現在49ep v3版のepisode 0の全254行でaction・state・深度PNG bytesが完全一致。
  RGB2系統・深度の読込テンソルもframe 0/127/253で完全一致。
- 学習設定のreturn_uint8=falseと今回true＋RGB/255の結果を同じ3点で照合し、完全一致。
  少なくともこの差を今回の不良出力の原因とは扱わない。
- 深度はuint16 PNG。checkpointの深度統計はRGB用ImageNetのmean/std（3ch）で、記録maxは1。
  生深度1chを正規化するとbroadcastで3chになり、先頭フレームの正規化絶対値最大254614。
  次元数が通るため、この不整合は推論時の例外にならない。
- 両データの深度metadataにis_depth_map/depth_unitがない。固定LeRobotのdepth_keysは名前ではなく
  metadataで判定するため、深度扱いから外れ、ImageNet統計を適用する経路に入る。
  `depth_output_unit=mm` を指定しただけでは実際の保存単位を検証したことにならない。
  前回の「57034mm」は正確には生の保存値57034であり、物理単位は未確認と訂正する。
- 読込処理の履歴では、uint16をint16にしてしまう旧ToTensor経路と、現在のfloat32経路にも差がある。
  学習PCの実際のコミット・変更内容はcheckpointにないため、どの経路で学習したかは不明。

診断用に、元PNGのPIL.convert('RGB')相当＋/255を16点だけ試した。これは深度の有効な
物理表現ではなく、255超を飽和させる仮説検証。既定処理・元データ・重み・統計は変更していない。
同じframe indexの比較:

| 指標 | 元の生値入力 | RGB変換の仮説 |
| --- | ---: | ---: |
| 並進L2平均誤差 | 1.813mm | 1.858mm |
| グリッパ幅MAE | 14.251mm | 41.030mm |
| 負の幅 | 5/16 | 0/16 |

負値は減っても、幅が約98mmに寄って誤差は悪化。仮説を修正案として採用しない。
32bit生深度とRGB統計の不整合は確認できたが、それが学習時から存在したか、推論時だけの差か、
モデル性能不良の主原因かは未確定。次に必要なのは学習PCのLeRobot commit・未コミット差分・実行ログ。
推論用の見かけの改善を目指して統計を差し替えたり、未確認のまま再学習や実機送信はしない。

監査記録: [policy-input-audit-2026-09-14.json](policy-input-audit-2026-09-14.json)。
仮説検証の生actionは `artifacts/policy-depth-probe.json`、元の全254予測はそのまま保持。

## 初回結果（2026-09-14）

episode 0の全254フレームでCPU推論を完了。実機移行の合格ではない。

- 並進誤差L2平均: 1.575mm（無動作: 1.566mm）。
- 回転誤差平均: 0.008199rad（無動作: 0.008093rad）。
- 幅MAE: 13.785mm（現在幅保持のMAE: 1.439mm）。
- 負の幅出力: 76/254。幅の出力範囲は -5.530〜100.836mm。
- 推論＋前後処理p95: 1058.87ms。データ読込・モデルロードはこの時間に含めない。
  4 CPUスレッドで計測。30Hzに必要な33.3msの周期を満たさない。

結果要約とモデルハッシュ: [policy-eval-episode0-2026-09-14.json](policy-eval-episode0-2026-09-14.json)。
生actionはローカルの `artifacts/policy-eval-latest.json` に保存。
全フレーム試験後にstrictロードを有効化し、1フレーム再試験で成功・先頭出力の完全一致を確認。
依存整合確認、教師変換テスト6件、既存Balance10秒試験も合格。

この1エピソードでは無動作を改善していない。モデル全般の性能不良と断定せず、
学習データとの対応、RGB/深度の前処理、正規化設定の意味、他エピソードの評価を確認する。
先頭深度の最大値は57034mmであり、無効値・単位・学習時処理との対応も調査対象。
クリップして問題を隠すことや、新規学習・ハードウェア送信は行っていない。

ユーザー指定モデル: `/home/developer/workspaces/pika_ws2/models/zero_relative_50ep_act_h1_v2/pretrained_model`。
ACT、chunk_size=1、n_action_steps=1。実機・WBCへは送信しない。

## 実行

```bash
make policy-eval
```

episode 0の254フレームをCPUで評価する。短縮確認は `make policy-eval POLICY_STEPS=4`。
短縮時は先頭だけでなく、エピソード全体から等間隔に抽出する。
結果は `artifacts/policy-eval-latest.json`。生の推論action・教師action・対応frame_index、
モデルファイルのSHA-256、入出力誤差、推論時間を保存する。
再実行で最新結果は上書きされる。初回の全フレーム結果はdocsに別途保存する。

これは録画データを入力するオフライン評価で、実機の動きに応じて観測が変化する閉ループ評価ではない。
実行完了はタスク成功・安全性の合格を意味しない。出力を自動的にMuJoCoや実機へ渡さない。

## 環境と再現性

- `.venv-policy`: Python 3.12.13。WBCの `.venv` / Python 3.10とは分離。
- LeRobotは `vendor/lerobot` の固定コミット79edf6a95948d0f0d75df1d54d0a5aad305f75a8を直接import。
  実行時にgit SHAと追跡ファイルの変更を検査する。既存の編集済み作業ツリーはimportしない。
- Torch 2.10.0+cpu、torchvision 0.25.0+cpu、NumPy 2.2.6、datasets 4.7.0、PyAV 15.1.0。
  依存の固定一覧は `requirements-policy.lock`。実行時に各バージョンも照合。
- 初回は固定ソースからLeRobot wheelも導入したが、実行では検証済みvendorソースを優先する。
  再セットアップの `make setup-policy` は固定依存＋vendor直接importを使用する。
- setupのPythonは既存condaのPythonバイナリを借りるが、既存のsite-packagesは継承しない。
  別PCでは `POLICY_PYTHON=/path/to/python3.12` を指定（検証版3.12.13に限定）。
  クリーンな別PCでのセットアップは未検証。セットアップだけはダウンロード通信が必要。

## 入力・出力の扱い

- 固定LeRobotのLeRobotDatasetを使用し、録画RGB2系統、深度、相対stateを読み取る。
- RGBのuint8だけを0〜1へ変換。深度は学習設定に従いmmを要求するが、metadataに単位がないため
  実際には生値が返される（物理単位は未検証）。既定では255で割らない。
- 正規化・逆正規化はcheckpointに付属するprocessorとsafetensorsの統計を使用。
  評価データの統計への置換、重みの学習、モデル設定ファイルの書き換えはしない。
- CPUへの変更とbackbone追加ダウンロードの無効化のみメモリ上で設定。
  モデル重みは `strict=True` でロードし、欠落を許容しない。
- 回転6Dは教師側で確認した列順を評価に使用。ネットワーク出力の回転誤差は
  Gram-Schmidtで回転行列化して計測するが、保存する生actionは変更しない。
  このモデルの学習元と現在の49epデータの同一性・変換履歴は独立した確認事項。
- 無動作比較はゼロ並進・単位回転・現在のグリッパ幅。全ゼロactionは使わない。
  並進m、回転rad、幅mを分けて報告し、単位を混ぜた平均値だけで性能を判断しない。
- HFオフライン設定に加え、Python監査フックでsocket connect/bind/sendto/name resolutionを拒否。
  ハードウェアAPI、カメラデバイス、DDS送信を使わない。キャッシュは新規repoの `.cache/policy` 内。

## 次段階へ進む条件

負のグリッパ幅、推論周期不足、無動作に対する改善不足は隠さず報告する。
これらの対処なしに実機試験へ進まない。とくに30Hzデータのh1 actionを、推論の完了時刻ごとに
無条件で適用すると時刻の意味が変わるため、非同期処理を追加するだけでは解決しない。
次は入力・正規化・学習元データの対応と複数エピソードでの品質を確認し、
CPU推論の高速化または別の推論計算機を検討する。新規学習や外部GPU契約は未実施。
