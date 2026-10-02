# GPU学習環境と短時間試験

GPU PCの専用作業場所: `/home/gpu-user/g1-pika-training`。
既存のsk_dev、Miniforge環境、データは変更しない。実機への指令は禁止。

## 環境

Python 3.12.13からsystem-site-packagesを継承しない `.venv-gpu` を作成。
CPU試験のtorch 2.10.0 / torchvision 0.25.0をCUDA 12.8版に変更。
組合せは[PyTorch公式配布表](https://pytorch.org/get-started/previous-versions/)に基づく。
`requirements-gpu.in` は初回導入用。解決後の全依存を
`requirements-gpu.lock` に記録し、試験はlockと実環境を照合してから実行する。
LeRobotは `sources.lock.json` の79edf6a9をvendorへ転送し、HEADと差分を検査。
GPU PCにある別コミットの既存LeRobotは使用しない。

## 今回の対象

49エピソード全体の転送・本学習ではなく、CPUの受理済みrun-i507ue81から
`samples.safetensors` と `manifest.json` を `assets/gpu-smoke-input/` へ転送。
キャッシュhashをmanifestと照合。学習64・検証32フレームはCPU試験と同一。
元parquetのhash、選択フレーム・除外理由は転送したmanifestに記録されている。
GPU PCの50エピソード版データは今回使わない。

小型ACT（RGB2、128x96、10D state/action、chunk1、VAEなし、事前学習重みなし）を
新規初期化して学習する。CPUモデル重みの追加学習ではない。
CPU試験とはデバイスや初期評価の有無が異なり、学習損失の完全一致は要求しない。
統計は学習64フレームのみ。深度入力なし。seed42、batch4、AdamW、lr1e-4。
ネットワーク接続は禁止する監査フックを試験プロセス内で有効にする。

実行（GPU PC上、依存lock配置後）:

```bash
cd /home/gpu-user/g1-pika-training
.venv-gpu/bin/python -I scripts/train_gpu_smoke.py --steps 100
```

このPCからの再実行は `make gpu-smoke`、結果を見るだけなら `make gpu-report`。
この2つのtargetは今回の接続先・専用鍵・専用ディレクトリを明示している。
再実行はリモートに配置済みのスクリプトを使用し、自動ソース同期は行わない。
`make gpu-smoke` は専用supervisorを別セッションで起動し、ジョブのパスを返す。
`make gpu-job-status GPU_JOB=<返されたパス>` で状態とログ末尾を確認する。
`make gpu-report` は最後に成功したrunの報告であり、進行中ジョブの状態ではない。
supervisor経由のジョブは排他ロックで同時実行を拒否する。
上記の直接Python実行は前景実行なので、SSH接続を維持する必要がある。

各実行は固有runディレクトリを作り、保存済みモデルを上書きしない。
checkpointとprocessorをstrict再読込し、全96フレームの出力完全一致を要求。
報告にはモデル評価、有限損失、ソース・依存・キャッシュhashを残す。
推論時間はCUDA同期付きでCPUキャッシュからGPU推論・CPU出力まで。
動画デコード・縮小・実カメラ・WBCは含まない。

モデル・optimizer・CPU/CUDA乱数・step・損失履歴を一定間隔で
`resume-step-XXXXXX.pt` へ一時ファイルからrenameして保存する。
`--resume <自分で生成したcheckpoint> --steps <再開後の総ステップ数>` で再開する。
入力キャッシュ・依存lock・コード・LeRobot commitが違う場合は再開を拒否する。
weights_only=Trueで読み込むが、他者から渡された任意のcheckpointは使わない。
再開ごとに新しいrunを作り、再開元を上書きしない。途中再開の対象は現在の小型ACT試験。
現在は全学習データを読む小型ACT基準実験も実装済み（下記）。
SSH切断耐性と通常終了後の再開は確認済みだが、電源断・強制kill・GPU障害は未試験。
OS再起動でジョブは停止し、statusがrunningのまま残る可能性がある。
その場合は実プロセスを確認し、最後に完了したcheckpointから別ジョブで再開する。
この短時間試験の合格はタスク成功や実機使用可を意味しない。

## 状態

2026-09-14: 専用環境導入、pip check、キャッシュ転送hash照合に成功。
100ステップ学習・保存・strict再読込後の96予測完全一致に合格。
runは `artifacts/gpu-smoke/run-53_xcoex`。結果・モデルは両PCに保存。
学習部分2.007秒（環境準備・初期化・評価・保存を含まない）。
キャッシュ入力推論p95 4.747ms（train/validationの合計96回、CUDA同期付き）。
検証32件の並進誤差2.253mm、無動作2.314mm。
グリッパ誤差18.193mm、現在幅保持2.207mm。実機使用には不十分。
評価詳細: [gpu-smoke-2026-09-14.json](gpu-smoke-2026-09-14.json)。
ローカルの既存 `make check-rgb-smoke` も再実行して合格。

## 49エピソード転送・分割・再開テスト

2026-09-14追記:

- valid49全17ファイル（965,670,614 bytes）を `datasets/valid49` へコピー。
  元の全ファイルの相対パス・サイズ・SHA256とGPU PC側が完全一致。
  記録は `assets/datasets/valid49-files.json`。既存50エピソード版は未変更。
- 学習episode 0..38、検証39..43、テスト44..48を候補分割として固定。
  グリッパh1不一致145行を補正せず除外し、採用数は学習8693・検証1022・テスト1021。
  元10881行から10736行を採用。`assets/datasets/valid49-split.json` に全frame indexを記録。
  両PCで再計算した分割ファイルもバイト一致。統計は学習のみ、テストはモデル選択に使わない。
  セッション単位の独立性や近似重複は未検証で、真の未知環境性能の保証ではない。
- SSH起動接続を閉じてから再接続し、ジョブ `job-40hv11d8` の終了コード0を確認。
  連続20ステップと、10ステップ終了後に新プロセスから20まで再開した場合を比較。
  損失全履歴・model・全96予測・optimizer・CPU/CUDA RNGが完全一致。
  [再開テスト結果](gpu-resume-2026-09-14.json)。確認コマンドは `make gpu-resume-report`。
  checkpoint自体はGPU PCの各runに保存。この再開試験の重みはローカル未バックアップ。
- 今回の最新gpu-smoke報告は再開テストの20ステップrun-suuhyij9。
  以前の100ステップrun-53_xcoexは保存したまま。品質が改善したという意味ではない。
- 現行training_secondsはcheckpoint保存時間も含むため、旧100ステップ2.007秒とは計測範囲が異なる。
- 負のテスト3件（破損データ、symlink/データ内manifest拒否、不正step拒否）に合格。

この時点では全データの学習は未実施だった。次節で基準実験を実施した。

## 全学習データの小型ACT基準実験（2026-09-14）

`build_full_rgb_cache.py` は固定splitと全ファイルhashを確認し、
固定LeRobotのLeRobotDataset/pyavで学習・検証の採用画像をデコードする。
CPU試験と同じ `rgb_input` を再利用。各フレームのepisode/frame indexを検査し、
RGB2系統・state/actionをキャッシュへ保存。テストepisode 44..48の画像は読まない。
未使用の深度がDataset内部で読まれる場合はあるが、入力・キャッシュ・統計には含まない。
キャッシュはGPU PCの `artifacts/full-rgb-cache/cache-6f9in3_c`。

`train_gpu_smoke.py --full-data` が同じ小型ACTで基準実験を行う。
128x96 RGB2、dim128、encoder1/decoder1、ResNet18ランダム初期化、VAEなし、chunk1。
これは本番モデル構成の決定ではない。batch16、seed42、AdamW lr1e-4、1000 steps。
各epochをランダム順で一巡し、末尾の小さいbatchも使う。途中のサンプラー順序・位置・
CPU/CUDA RNGもcheckpointに保存。正規化は学習8693フレームだけのmean/std。

初回run: `artifacts/full-rgb-baseline/run-79a2ge2g`。
機械可読の結果: [full-rgb-baseline-2026-09-14.json](full-rgb-baseline-2026-09-14.json)。
学習8693フレーム全件を使用、延べ15989サンプル（約1.84 epoch）。
学習部分27.736秒（checkpoint保存を含む）。画像キャッシュ作成・初期化・評価は別。
起動ジョブjob-iccbwufmは全体約274秒でexit 0。
学習診断256フレーム（等間隔選択）＋検証1022全フレームで保存・strict再読込の予測完全一致。
テスト1021フレームは評価しない。

| 検証指標 | 小型ACT | 無動作/現在幅保持 |
| --- | ---: | ---: |
| 並進L2平均 | 2.066mm | 2.115mm |
| 動きが1mm超の577フレームの並進L2 | 3.203mm | 3.317mm |
| 回転角誤差平均 | 0.010942rad | 0.010474rad |
| グリッパ幅MAE | 3.030mm | 1.767mm |

回転6Dは予測値をcolumnsのGram-Schmidtで回転行列に戻して評価。
縮退ベクトル0件、負の幅0件、予測幅1.565〜94.398mm。指令値クリップはしていない。
推論p95 4.825msは縮小済みキャッシュ入力・CUDA同期付きで、実カメラやWBCを含まない。
位置の改善はわずかで、回転・幅は保持基準に劣る。タスク成功・実機使用可とは扱わない。
過去の96フレーム試験と検証集合が違うため、直接の性能改善比較はしない。

500stepのcheckpointから新プロセスで1000まで再開したrun-6tprwbowも確認。
全損失・model・1278予測・optimizer・サンプラー・CPU/CUDA RNGが連続実行と完全一致。
現在のfull-rgb-baseline-latestはこの再開run。同じ予測であり別モデルの性能改善ではない。
`check_full_rgb_run.py` は保存済み正規化統計を全学習データから再計算し完全一致を確認。
モデル/processor/予測/レポートは両PCに保存。大きな再開checkpointと画像キャッシュはGPU PCのみ。

起動・確認（このPC）:

```bash
make gpu-full-train
make gpu-job-status GPU_JOB=<起動時に返されたジョブのパス>
make gpu-full-report
```

gpu-full-trainはキャッシュ生成から新規1000step学習・評価監査を実行する。
再実行ごとに別cache/runを作るため、容量を消費する。ソース自動転送はしない。
gpu-full-reportは最後に成功した監査結果で、実行中ジョブの状態ではない。
今回の初回ジョブは監査を後から実行した。次回以降の起動スクリプトに監査を接続済み。

次: 学習量やモデル設定の比較を検証splitのみで行い、保持基準を上回れるか調べる。
最終testはモデル選択に使わない。実機通信・ポリシーのWBC接続・閉ループタスク検証は未実施。

## 学習量比較と入力依存診断（2026-09-14）

事前に3000/10000step、同一モデル/seed42/キャッシュ/検証splitを固定して比較した。
3000stepは新規学習、10000stepはそこから再開。双方の最初の1000損失が
以前の受理済み1000step基準実験と完全一致。最終testは未使用。
上限をfull-dataモードのみ10000へ拡張。コードhashが変わったため旧checkpointは
現行スクリプトから再開不可（保存済みの元コード・依存を復元する必要がある）。

| 検証1022フレーム | 3000step | 10000step | 無動作/現在幅保持 |
| --- | ---: | ---: | ---: |
| 並進L2 | 2.045mm | 2.096mm | 2.115mm |
| 動く区間577フレームの並進L2 | 3.100mm | 3.019mm | 3.317mm |
| 回転角誤差平均 | 0.010403rad | 0.010720rad | 0.010474rad |
| 幅MAE | 2.087mm | 2.042mm | 1.767mm |
| 負の幅出力 | 4 | 87 | 0 |

学習時間は3000stepが82.625秒、追加7000stepが190.789秒（checkpoint保存込み）。
ジョブjob-hklhlkpc全体は約315秒で完了。両モデルとも保持基準に対する全診断条件を
満たさず不採用。10000stepの幅最小は-4.699mm。クリップして合格扱いにはしていない。
run-bdq1hvyr（3000）、run-1r5b65hh（10000）を保存。最新参照は10000stepだが採用モデルではない。
単一seed・反復した検証評価であり、有意差やタスク成功を主張しない。

同じ1022検証フレームで、2カメラをペアでシャッフル（seed314159）して状態は維持、
または現在グリッパ状態のみシャッフルして画像は維持する診断も実施。
通常入力のstrict再読込予測は、保存済み結果と完全一致した。

| 幅MAE | 通常 | 画像ペア入替 | 現在幅入替 |
| --- | ---: | ---: | ---: |
| 3000step | 2.087mm | 38.449mm | 6.539mm |
| 10000step | 2.042mm | 38.745mm | 6.300mm |

画像に対する出力依存は確認できた。画像を無視しているという仮説は支持しない。
ただし画像と状態の自然な対応を壊す診断なので、因果的なタスク理解を証明するものではない。
幅の推定が視覚に強く依存している可能性があり、現在幅の明示利用・モデル構成の比較が次の候補。
現段階でaction契約変更・幅補正・ハードウェア配信はしていない。

`make gpu-learning-curve` で同じ比較を別runとして実行、`make gpu-learning-report` で最新比較を確認。
比較は検証済みキャッシュと初回1000step参照runを必要とし、キャッシュ再生成はしない。
元モデル・processor・予測・レポートは両PCに保存、再開checkpointはGPU PCに保持。
機械可読結果は `docs/learning-curve-2026-09-14.json` と `docs/image-dependence-2026-09-14.json`。

シミュレーション接続に向けた純粋な10D→TCP目標変換も別途準備し、6単体テストに合格。
詳細: [POLICY_ACTION_BOUNDARY.md](POLICY_ACTION_BOUNDARY.md)。WBCへの実接続はまだ行っていない。

続いて現在幅＋変化量方式を比較し、幅MAEは保持基準を下回ったが、負幅と回転の課題が残った。
通常ACTとして直接利用できない実験codecを含むため、必ず
[GRIPPER_RESIDUAL.md](GRIPPER_RESIDUAL.md) の出力復元要件を確認すること。
