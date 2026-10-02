# 学習済みモデルの照合・起動・共有

既存valid49データと学習済みACTを使う。再収集・再学習は今回の変更に不要。
候補モデルの品質合格や実機制御とは別の、ファイル整合性・入出力契約の検査。

## 固定単位

`config/policy-bundle.json` にモデルの相対配置先、7ファイルのサイズ/SHA256、
画像前処理・幅codec・GPU依存lockの3ファイル、LeRobot commit、データ/split出典hashを固定。
重みだけを交換せず、保存pre/postprocessorと正規化状態を一式として扱う。
manifestは署名ではなく、出典や再配布許可を暗号的に保証しない。

- state/actionは10次元、h1、回転6D columns、相対移動はm。
- 入力は左右ではなく**右手の2種類のRGB**。D405 RGB→pikaDepthCamera、魚眼→pikaFisheyeCamera。
- 640×480 RGBを訓練と同じbilinear/antialiasで128×96へ縮小。depthは不使用。
- ACT→保存postprocessorの逆正規化→実測幅を足すcodec→外部10D action、の順。
- 幅は未来の絶対幅m。codec前のネットワーク出力は幅差分で、そのままグリッパへ送らない。
- この検査は出力をclipしない。幅較正・タスク成功・身体安定性を認定しない。

## 通常操作

リポジトリ直下で:

```bash
make bundle-check
make check-offline
make full-record-check
```

最初の2つはGPU/G1/通信不要。GPU診断runnerは配置前にローカルbundleを照合し、
manifestと検査コードを新規GPU試験フォルダへ配置する。
ACT workerがGPU上の7+3ファイルを再照合してから重みをロードする。
欠落・改変・不一致はready前に異常終了。元データやモデルを修復/上書きしない。
`--measured-state` のSONICのみの再生ではACT照合を要求しない。

GPUワーカーを単独で使う場合は配置済み検査コードとmanifestを指定:

```bash
/path/to/.venv-gpu/bin/python -I /path/to/probe_gpu_images.py \
  --root /path/to/g1-pika-training \
  --policy-bundle /path/to/policy-bundle.json \
  --images /path/to/new-diagnostic-output --diagnostic-width 0.04
```

これは保存PNG2枚の仮定幅診断。実機入力や幅較正を代替しない。
省略時のmanifestは `ROOT/config/policy-bundle.json`。
新しいモデルへ変更する場合はmanifest・codec・既存runnerのモデルhash条件を一致させてレビューする。
hash更新だけで候補を実機用として承認しない。

## メンバーへのモデル共有

```bash
make bundle-export OUTPUT=artifacts/new-diagnostic-act.tar.gz
```

出力親フォルダは事前に存在すること。既存出力は拒否する。
モデル7ファイル、必要コード/依存lock、manifest、固定ソース情報、LeRobotのLICENSE参照、
検査手順、配布内容hashだけを明示リストで梱包する。学習データ・SSH鍵・他ログは含めない。
コピー後もbundleを照合。同じ入力なら同じ圧縮内容になる。配布する権利は別途確認する。

受領側は**新規フォルダ**へ展開し、その中で:

```bash
python3 -I scripts/policy_bundle.py verify
```

照合はPython3.10以上の標準ライブラリだけで実行できる。
推論にはPython3.12.13、固定GPU依存、固定LeRobotソース、CUDA対応環境が別途必要。
パッケージは環境インストーラー/全身制御ランチャーではない。
IK/SONIC/G1再構築は[開発手順](DEVELOPMENT_RUNBOOK.md)と[ビルド記録](SONIC_BUILD.md)を参照。

## 2026-09-30検証

- 欠落/改変/codec/processor/IO/パス/出典違い、配布内容限定・再現性・上書き拒否など14試験成功。
  GPU未導入環境でも実ACT workerが改変をready前に拒否する試験を含む。
- `make check-offline` 成功。IPCの明示skip4件は別検査扱い。
- `artifacts/full-record/run-w2r_5_nu`: 保存画像2組→ACT→IK→SONIC、3worker exit0、回収成功。
- `artifacts/full-record/run-ssy2zdrv`: 人工入力3秒、93policy/150control、4worker exit0、記録照合成功。
  関節参照は選択式0.4秒補間。人工時計/身体snapshotで、実入力や力学の試験ではない。
- `artifacts/full-record/run-ck4k0eu8`: 同じ処理の対応上限30秒、903policy/1500control、
  4worker exit0、記録照合成功。host間隔18.766〜21.324ms、20±2ms外0件。
  実時間保証・実入力30秒・身体追従の合格にはしない。
- 配布用 `artifacts/diagnostic-act-bundle-20260930.tar.gz`: 17ファイル、43,459,792bytes。
  SHA256 `b61d3879eba76c94c225d9dab30052b988059c5ddc296d6dee3001c2daf9cdc4`。
  新規一時フォルダへ展開して、受領側の標準Python照合も成功。

今回G1へ接続/送信していない。モデル品質・SONIC目標差/URDF外・停止/制御権移行の未解決事項はそのまま。
