# 計算目標の監査（2026-09-24）

2026-10-01追記: [起動履歴・開始契約の診断](SONIC_STARTUP_ABLATION.md)で、
16起動条件×3参照すべてにURDF超過が残ることを確認。
paddingだけの修正を採用せず、Quaternion/headingと未再現のINIT条件を分けて記録した。
以下は9月24日時点の比較結果で、物理閉ループの合格ではない。

実機動作の許可・追従評価ではない。G1への指令はゼロ。
対象は `artifacts/full-record/run-b5do1ocs/outputs/report.json`。
記録SHA256: `11d9cc3ad0e297f1bf0551a25b68ef66b5455ed18163936f7914a696d8013dec`。
93policy/150control、186画像の保存整合検査に合格。

## 結果

元記録の最大目標差は右肩pitchの1.252513rad、初回0.834031rad。
右足首rollは147/150回、腰rollは139/150回でローカルURDFの範囲を超えた。
実測姿勢は全関節で同URDF範囲内。目標は送信しておらず、差を追従誤差と解釈しない。
PD用目標と物理関節範囲の意味は同一とは限らず、この監査だけではモデル故障を断定しない。

同じ150個の実身体履歴を固定したGPU再推論:

|参照|過去action入力|最大目標差(rad)|URDF外の関節数|
|---|---|---:|---:|
|記録されたIK|毎回ゼロ|0.836863|0|
|記録されたIK|計算出力を履歴へ戻す|1.252513|2|
|最新実姿勢の保持|毎回ゼロ|0.605528|0|
|最新実姿勢の保持|計算出力を履歴へ戻す|1.179329|5|

記録IK＋再帰履歴は元記録の150×29出力を完全再現（最大差0）。
joint順序・scale・defaultの式は固定した上流送信直前の式と一致。
参照を実姿勢に置き換えても差が残り、LeRobot/IKだけを原因とはできない。
再帰履歴は実機で実行されていないactionであり、閉ループの物理挙動を表さない。
毎回ゼロ化して合格扱いにする変更、出力clipping、実機送信は行っていない。

成果物: 同runの `motion-audit.json` / `ablation-comparison.json`、
`artifacts/sonic-replay/run-n4vkz49q`（IK）/ `run-b0x8o3am`（実姿勢保持）。

## 再現

出力ファイルは上書き禁止。未使用の出力名を指定する。

```bash
make audit-record INPUT=artifacts/full-record/run-b5do1ocs/outputs/report.json OUTPUT=/tmp/g1-target-audit-new.json
.venv/bin/python -I scripts/prepare_online_ablation.py --report artifacts/full-record/run-b5do1ocs/outputs/report.json --mode measured_hold --output /tmp/g1-ablation-new.json
.venv/bin/python -I scripts/run_sonic_replay.py --prepared /tmp/g1-ablation-new.json --compare-recurrent
```

最初の2コマンドはローカルファイルのみ、最後はgalleriaのGPUのみ。G1の給電不要。
`recorded_ik`も同じ手順で作成できる。
`compare_online_ablation.py --report ... --recorded-run ... --hold-run ... --output ...`で比較を保存する。

## 未解決・次の検査

### 上流関数との照合を追加

`check_sonic_upstream_history.py`は固定SHAの上流C++から観測関数をそのまま抽出し、
通信を持たないmock logger/motionでコンパイルする。ランダム32組×10フレームで比較。
decoder履歴930要素はfloat32で完全一致、encoder1247要素は絶対許容差1e-7で一致。
encoderはmode0・heading補正なし・上半身overrideなしの条件。
mockは既に整列した履歴を渡すため、上流loggerの時間補間やDDSを検証してはいない。
この範囲では配列の並びや姿勢変換の不一致は見つからなかった。
この結果で静的参照の適用範囲や閉ループ安定性を証明したとは扱わない。

観測と参照の上流互換性、初期姿勢/モデルの適用範囲、動的な全身参照生成を引き続き確認する。
物理停止・制御権・安全な初期遷移は別途未検証。現在は追加承認待ちではない。
