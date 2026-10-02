# 現在幅を使うACT比較実験

外側のactionは従来どおり10D（h1相対並進3、columns回転6D、将来の絶対グリッパ幅）。
学習内部のみ、最後の値を `future_width - measured_current_width` に変換する。
正規化統計もこの内部目標を使い、学習8693フレームだけから計算する。
元データ・キャッシュは変更しない。関節制御・グリッパ通信・WBC接続はしない。

推論順:

1. RGB2/測定state → 保存済みpreprocessor → 固定LeRobot ACT
2. 保存済みpostprocessorで正規化を戻す（この時点の最後の値は変化量）
3. `gripper_codec.decode_action` で観測時の測定幅を足す
4. 外側10D actionとして評価（幅のクリップなし）

重要: この実験モデルを通常のACT checkpointとしてそのまま使ってはいけない。
モデルディレクトリの `action_codec.json` と必須decoderを合わせて使用する。
既存のlegacy policy-check/policy-evalはcustom codecを検出すると読み込みを拒否する。
他の汎用LeRobotツールはこの追加メタデータを自動解釈しない。
今回の学習ループはcodec込みでstrict再読込後の1278予測一致を検査する。
codecコードhashも再開時の同一性に含め、元コードをrunに保存する。
コード変更前のcheckpointは現行スクリプトで再開できない。保存済み元コードを使うこと。

比較条件は3000step、seed42、同一RGBキャッシュ、同一小型ACT、batch16、
学習39/検証5エピソードで固定。比較対象は直接幅を予測した3000stepのrun-bdq1hvyr。
同じ検証集合を再利用しているため未使用テスト性能ではない。最終testは引き続き未使用。
内部目標・正規化の変更は共有ネットワーク全体の学習にも影響するため、
位置や回転の性能も同時に確認する。

```bash
make gpu-gripper-residual
make gpu-gripper-report
```

起動はSSH切断に耐えるsupervisor経由。結果は最後に完了した比較で、ジョブ状態とは別。
実験結果・モデルは `artifacts/gripper-residual` / `artifacts/full-rgb-residual` に分離する。
既存の直接幅予測モデルは上書きしない。

## 2026-09-14 結果

job-uwo2noeuは約106秒でexit 0。学習部分84.586秒、キャッシュ推論p95 4.933ms。
モデルrun-xg1fn3b_、比較comparison-oszk3de9。保存・strict再読込後の外側1278予測一致、
学習のみの内部目標統計・キャッシュ/コードhash照合に合格。

| 検証1022件 | 直接幅3000step | 変化量3000step | 無動作/現在幅保持 |
| --- | ---: | ---: | ---: |
| 位置L2平均 | 2.045mm | 2.024mm | 2.115mm |
| 動く区間577件の位置L2 | 3.100mm | 3.057mm | 3.317mm |
| 回転角誤差平均 | 0.010403rad | 0.010511rad | 0.010474rad |
| 幅MAE | 2.087mm | 1.603mm | 1.767mm |
| 負の幅 | 4件 | 2件 | 0件 |

幅MAEは直接幅予測より約23%、保持より約9%低下した（この検証集合内の記述値）。
変化量方式の幅範囲は-4.192〜96.835mm、回転の縮退は0件。
回転保持基準・非負幅条件を満たさず、診断条件全体には不合格。モデルはまだ不採用。
統計的有意差・未知環境での成功・実機使用可は主張しない。
変化量ターゲット方式は幅改善の候補として残し、次に出力の物理的妥当性と回転を検証する。

旧policy-check/policy-evalのcustom-codec拒否、codec往復/元データ非変更を含む
ローカル6テストに合格。旧モデルのstatic policy-checkも合格、既存policy-action6テストも合格。
この実験でのcodec付き途中再開の独立比較はまだ未実施（保存・再読込比較は実施済み）。
通常ACTのままこのcheckpointを運用することは禁止。WBC/実機/最終testは未使用。
結果は [gripper-residual-2026-09-14.json](gripper-residual-2026-09-14.json)。
モデル/processor/codec/予測/レポートを両PCへ保存。再開checkpointはGPU PCのみ。
