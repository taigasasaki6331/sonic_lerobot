# LeRobot→TCP→IK→SONIC（送信なし）

## 到達点

保存画像2組を固定LeRobot ACTで再推論し、10次元action→TCP目標→本家IK→
SONIC encoder/decoder→関節出力ファイルまで完走した。幅は別メタデータとして保持。
実機通信・指令・物理シミュレーションなし。LeRobotとSONICは異なるPython/C++環境を維持。

旧Decoupledから再利用したのは`BodyIKSolver`、`ReducedRobotModel`、PIKAモデルのみ。
旧Balance/Walkネットワークはこの経路で読み込まない。主要IKソース4点のhashを実行時検査。
身体モデルは既存生成URDF（hashはsources.lock）。未知の新規形状を作っていない。

## 参照の契約

- actionはlocal-relative-h1、回転6Dは列連結。既存TCP軸変換と境界検査を再利用。
- 腕IKの固定関節はその時点の実測脚・腰。上流は`fixed_values`だけでなく
  `pinocchio_wrapper.q0`を縮約モデル構築に使うため、q0も実測値に設定する。
  縮約前後の実測TCP FK一致を検査する。上流ソースは変更していない。
- 反復は最大20回×本家3step。制限外実測は変更せず、数値計算seedだけ投影し量を記録。
- 診断基準は位置2cm、姿勢0.15rad。ハードウェア許容値の認定ではない。
- 全29関節の候補は脚・腰を実測固定、両腕はIK。10フレーム先読みは終点保持、速度ゼロ。
  これは運動学的な参照候補であり、動的に妥当な全身軌道ではない。
- SONIC公式v1 packerでシリアライズを検査（送信なし）。回転/関節順をencoderにも同条件で入力。
- グリッパ幅はSONIC/Dex3入力に混ぜず別欄へ保持、出力で同値・未駆動を検査。

## 実施結果

1. 過去の実画像推論30件: IK位置誤差最大0.009692m、姿勢誤差最大0.009987rad。
   30件すべて診断基準内。複数条件を変えたため、改善を腰固定だけの効果とは断定しない。
2. 30候補をSONICで推論: 全出力有限、最大目標−実測差0.896344rad。
3. 保存画像のうち残っていた0/29番を画像hash照合後にACT再推論。
   新しい2 actionを同じ経路へ入力し完走、最大目標差0.895493rad。
   幅0.000329448/0.000337258mを独立メタデータで維持。グリッパ未駆動。
4. 単体試験60件成功（運動学の計算を含むが物理時間は進めない）。

記録:
- `artifacts/sonic-tcp/recorded-input-20260924.json`（30件、IK結果も内包）
- `artifacts/sonic-replay/run-3jpk7nc3/`（30件のSONIC）
- `artifacts/sonic-tcp/reinferred-endpoints-20260924.json`（画像再推論2件）
- `artifacts/sonic-replay/run-7ol6w3ks/`（1コマンド統合診断の実行確認）
- GPU画像再推論ログ: `artifacts/sonic-replay-btTurA/reinferred-endpoints/`

## 再実行

リポジトリ直下、galleria起動中。G1は不要:

```bash
make sonic-tcp-check INPUT=artifacts/sonic-tcp/reinferred-endpoints-20260924.json
```

これは**保存action以降**を再実行するコマンド。画像からの再推論そのものは
`reinfer_saved_endpoints.py`＋既存`probe_gpu_images.py`をGPUで別途実行する。
後者に`--frames`を追加したが既定は30件のまま。依存/モデル/codec確認を維持。

## 未完了と次の入力取得

`hardware_ready=false`。実測肩rollは本家IK制限外（左右とも）。制限を緩めていない。
衝突、開始姿勢への遷移、安定性、停止、実時間処理、PIKA実質量は未検証。
出力目標差はPD制御上ゼロとは限らず、ここだけで動作可否・原因を断定しない。

過去30件は約5Hzのsnapshot。今回のSONIC履歴は明示的な繰り返し合成。
別日に取得した50Hz身体状態を同時刻のカメラ入力と偽って結合していない。
同時取得されたカメラ・幅・10フレーム身体履歴の確認はユーザー指定で最後の実機検証へ延期。
非実機工程の継続条件としてG1起動を要求しない。

取得側へ`--archive-sonic-inputs`を実装。全30画像ペアをGPU保存し、各ペアに
実測身体10フレームを添付。20ms±2ms、有限値、tick更新、最新snapshotとの一致を検査する。
新しい実機取得経路は未実行（単体検査のみ）。準備できたら次を使う:

```bash
python3 -I scripts/run_state_shadow.py --gripper-state --archive-sonic-inputs
```

このコマンドはG1/GPUに接続し、カメラと右グリッパserialを開く。
動作指令・モード変更はないがserial openでMCUリセットの可能性がある。
G1給電・接続の準備とその操作の了承後に実行する。取得完了後は保存入力で作業可能。
画像はGPU側live-shadowの出力ディレクトリ、reportはtiger側へも回収する。
