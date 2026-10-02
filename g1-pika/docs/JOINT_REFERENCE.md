# 時間整合した関節参照（2026-09-30）

LeRobot→IKで得た絶対関節目標を、現在の計算上の参照から連続的に更新する。
関節角・速度・加速度が更新前後で連続となる5次多項式を用い、目標到達時の速度/加速度はゼロ。
初回は実測q/dq、加速度ゼロをseedとする。SONICへ20ms間隔の未来10点と解析的dqを渡す。
更新ごとに計算上の現在値から再計画し、h1 actionを再適用しない。

実装: `scripts/sonic_joint_trajectory.py`。
`MeasuredStream`/観測workerに `joint_interpolation_s` オプションを追加した。
既定は従来の終点保持。新モードもrecord-only、鮮度/連番/履歴検査は従来どおり。
この補間は接地・力学・衝突・速度/加速度制限を扱わず、全身バランス計画の代替ではない。
姿勢quaternionは既存の終点保持のまま。0.4秒は診断値で、実機で決定した移行時間ではない。

## 検証結果

- 3単体試験: 始点/終点条件、有限差分と解析dq/ddq、再計画時のq/dq/ddq連続性、時計/不正入力。
- 観測生成15試験: 選択モードの時間更新、初回実測q、幅分離、終点入力条件、鮮度拒否など。
- `make check-offline` 成功。
- GPU人工入力3秒統合: `artifacts/full-record/run-ddwfs4mc`。
  ACT/IK93回・SONIC150回、4worker正常終了、hash検査成功、G1接続なし。
  開始間隔19.731〜20.221ms。この1回の値は実時間保証ではない。
- 9月24日実身体保存記録150窓でGPU推論: `artifacts/sonic-replay/run-ptukt__r`。
  推論計算完了、動作指令ゼロ。元の身体観測は補間/改変しない。

|参照|action履歴|初回最大目標差(rad)|全体最大目標差(rad)|出力がURDF外となる関節数|
|---|---|---:|---:|---:|
|従来のIK終点保持|毎回ゼロ|0.834031|0.836863|0|
|従来のIK終点保持|計算出力の再帰|0.834031|1.252513|2|
|時間整合した関節参照|毎回ゼロ|0.621668|0.867421|0|
|時間整合した関節参照|計算出力の再帰|0.621668|1.162244|3|

初回最大差は減ったが、全体の差・URDF外出力は解決しない。合格に読み替えない。
再帰条件では右足首roll・腰roll・腰pitchがURDF外。
目標差は未送信の計算目標と実姿勢の差で、追従誤差ではない。
未実行actionを戻す条件は閉ループの身体応答を表さない。

参照自体は保存した150×10点でURDF内。更新時のq/dq/ddq不連続は0。
計算参照の最大速度2.622933rad/s、最大加速度20.637852rad/s²。
サンプル点の確認であり、時間全域の制限保証やPIKA装着実機の許容値確認ではない。
保存データの再計画時刻は「そのpolicyを最初に使用した身体サンプル」の時刻であり、
元のGPU発行時刻を復元したものではない。オンラインworkerはcoordinatorの実時計で評価する。

## 再現

既存galleria環境が必要。G1の給電は不要。

```bash
make trajectory-fixture-check RATE_SECONDS=3
```

これは保存画像と人工入力時刻による統合確認。
実身体の保存記録での比較は、未使用の出力先を指定して以下を実行する。

```bash
.venv/bin/python -I scripts/prepare_online_ablation.py --report artifacts/full-record/run-b5do1ocs/outputs/report.json --mode causal_quintic_ik --transition-seconds .4 --output /tmp/g1-quintic-new.json
.venv/bin/python -I scripts/run_sonic_replay.py --prepared /tmp/g1-quintic-new.json --compare-recurrent
```

元比較との照合は `compare_online_ablation.py` に `--trajectory-run` を指定する。
今回のprepared/comparisonはrun-b5do1ocsの
`ablation-quintic-20260930.json` / `ablation-comparison-quintic-20260930.json`。

実入力の記録専用runnerも `--joint-interpolation-seconds .4` を受け付ける。
今回は新モードでG1入力を取得していない。既定の起動/設定を変更していない。

## 次の課題

### フレーム間の数値極値を追加検査

`audit_joint_reference.py`で各0.18秒予測窓の多項式微分の根と端点を評価。
150窓すべてで参照角度・速度のURDF範囲超過なし。
成果物: `artifacts/full-record/run-b5do1ocs/continuous-reference-audit-20260930.json`。
これは浮動小数点での数値極値検査で、区間演算による厳密な範囲証明ではない。
URDF速度はモデル値。加速度の許容値・実機の物理応答は確認していない。
予測窓の集合を調べており、その後の再計画を含む実機の実行軌道と解釈しない。

```bash
.venv/bin/python -I scripts/audit_joint_reference.py --report artifacts/full-record/run-b5do1ocs/outputs/report.json --output /tmp/g1-reference-extrema-new.json
```

関節参照4単体試験と観測生成15試験が成功。GPU/実機接続は不要。

初期姿勢/IK制約/SONICモデル適用条件、接地を含む参照生成、G1側送信・制御権・停止を詰める。
この補間だけで動作許可やhardware_readyを有効にしない。
