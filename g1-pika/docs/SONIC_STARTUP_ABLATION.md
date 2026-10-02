# SONIC起動履歴・開始契約の切り分け（2026-10-01）

保存入力の診断。G1接続・実機指令・シミュレーションなし。
結論: 起動paddingへの感度は主にq/gravityで大きいが、48条件すべてにURDF外目標が残る。
paddingだけの変更、履歴の毎回ゼロ化、clippingを実機移行の解決策にしない。
未送信の目標と保存実測の差は、追従誤差・転倒・安全性の指標ではない。

## 条件と成果

[独立診断](sonic_startup_diagnostic_handoff_20260930.md)の固定条件を引き継ぎ、
q/dq/gyro/gravityそれぞれを現行の実履歴から上流起動paddingへ切り替える全16組合せを比較。
記録IK終点保持・実姿勢保持・連続IK参照（0.4秒）の3種、各150周期、48条件/7200推論。
各条件でraw action履歴をゼロから独立に開始し、直前の未実行出力を戻す。
保存身体はそのactionへ反応しない。実機閉ループの模擬ではない。
連続参照の開始時計は保存記録の初回policy使用時刻で、元のGPU publish時刻ではない。

- 推論実行日: 2026-09-30。galleriaのファイル/stdio専用SONIC worker、exit0、回収成功。
- 保存先: `artifacts/sonic-startup-ablation/run-ofbwc_6t/`。
- `outputs/report.json`: 全条件・既存4基準再現差0・関節変換式差0。
- `integrity.json`: 元の入力SHA/各出力/集計/モデル・キャッシュ整合性の再検証。
- `startup-analysis-20261001.json`: 各チャネルを切り替えた全8背景のペア比較。
- `startup-contract-20261001-v2.json`: 保存生Quaternionと開始契約のソース/テンソル監査。
  初稿`startup-contract-20261001.json`は保存したまま。v2ではgravity専用のidentity参照計算から
  実motionと無関係なheading集計を取り除いた。判断にはv2を使う。

固定encoder/decoderモデルSHA、4上流ソースSHA、元記録/参照出典は`input.json`に収録。
input SHA: `35beccf5c69a8ed79b1a4628c6dbc2b17494d3a07d65f415ff754c722cabbeb4`。
GPU用モデル/キャッシュ4ファイルは新規診断フォルダへコピーし、その実行前後SHAは一致。
同じ参照のencoder tokenは16条件で完全一致。既存診断の再現であり、モデル/既定動作の変更ではない。
10件の身体テンソルはseq9から一致するが、条件ごとのraw action再帰履歴は異なり続け得る。

## 起動paddingの影響

初期10周期のペア間最大関節目標差。各チャネルについて他3チャネルの全8背景を比較し、
その8個の最大差の最小〜最大を記載（rad）。寄与率でも改善量でもなく、非線形な再帰を含む。

| 参照 | q | dq | gyro | gravity |
|---|---:|---:|---:|---:|
| 記録IK保持 | 1.1168〜1.2427 | 0.00109〜0.00215 | 0.00144〜0.00228 | 0.8510〜1.3444 |
| 実姿勢保持 | 0.8796〜1.4420 | 0.00074〜0.00174 | 0.00111〜0.00245 | 0.6643〜1.1342 |
| 連続IK | 0.8548〜1.4046 | 0.00073〜0.00172 | 0.00117〜0.00240 | 0.7038〜1.1188 |

全paddingは3参照とも初期の最大目標−実測差を増やした。
記録IK1.252513→1.719764rad、実姿勢保持0.688827→1.266712rad、連続IK0.758657→1.226002rad。
最初の10周期を除いても48/48条件にURDF超過が残る。
dq/gyroの感度が小さいという判断はこの静的な保存記録に限定し、実運転一般へ拡張しない。
URDF範囲はモデル検査で、PD目標の許容範囲やメーカー認証済み制限とは同一視しない。

## Quaternion・座標系・開始契約

固定上流`g1_deploy_onnx_ref.cpp`と`math_utils.hpp`を読み、
`sonic_startup_math_oracle.cpp`で実際の上流数学関数だけをコンパイルして照合した。
SDK/DDS/deployはリンク・起動しない。93policy/150body記録の整合性も再照合。

| 契約 | ソースで確認した内容 | 保存記録での確認・限界 |
|---|---|---|
| q/dq順序 | GatherRobotStateToLogger（2826行〜）でhardware→Isaac、qのみdefault差分 | 固定目標変換式と既存4基準は差0 |
| base IMU | 同関数（2912行〜）はLowStateのwxyz/gyroを直接取得 | 受信Cも生値を保存。センサー実軸の校正・CRCは未検証 |
| Quaternion | 上流の回転行列関数は内部正規化、gravityのquat_rotateは正規化しない | 本実装は実Quaternionを正規化。1500履歴使用でgravity float32差最大4.1723×10⁻⁷、encoder姿勢差0 |
| orientation6D | GatherMotionAnchorOrientationMutiFrame（616行〜）はmode0、先頭2列を行順に平坦化 | 正規化済みPythonとC++は保存入力で差0。LeRobotの列連結6Dと区別する |
| heading | UpdateHeadingState/ComputeApplyDeltaHeading（559/593行〜）は初期base/ref yawを合わせる | 最初の保存base/refを仮の起点とするとdelta −0.000199814rad、orientation float32差最大0.000199667。元のreset/frame0は未再現 |
| INIT/CONTROL | InitControl（2746行〜）は3秒default姿勢指令。CONTROLで初めてLoggerへ追加（3869行〜） | 記録専用経路はINITを実行していない。最初のdefault差最大1.148424rad、全期間最大1.148460radは右wrist roll |
| 時刻 | 上流LoggerはCONTROL 20ms周期で記録し不足分をzeroEntryで埋める | 保存endpoint間隔19.4645〜20.9485ms、tick差19/20/21/22。元のLogger時計/制御開始は再現しない |
| raw action | CreatePolicyCommand（3141行〜）はraw Isaac出力をlast_actionに保存 | 本比較の履歴もraw順序、ただし未実行action。計算の再帰と実機応答を区別する |

zeroEntryはquaternion=[0,0,0,0]。上流gravity関数では+Zになる。
identity quaternionの−Zとは違い、実センサー値として生成しない。
正規化や仮heading起点の差は小さいが、この監査ではその差をdecoderへ再入力していない。
小さな入力差が出力へ影響しないと証明したわけではなく、根因を断定しない。
defaultとの差もINIT前後の条件が異なる事実であり、その差だけで原因や必要な実機動作を決めない。

## 再現・確認

リポジトリ直下、既存`.venv`（numpy等）とg++が必要。
保存成果の確認にGPU/G1の起動は不要。

```bash
make startup-ablation-verify RUN=artifacts/sonic-startup-ablation/run-ofbwc_6t
make check-offline
make startup-contract-audit OUTPUT=/tmp/sonic-startup-contract-new.json
```

出力先は未使用名を指定（既存成果の上書き拒否）。全8背景の分析の再生成:

```bash
.venv/bin/python -I scripts/sonic_startup_ablation.py summarize \
  --input artifacts/sonic-startup-ablation/run-ofbwc_6t/input.json \
  --results artifacts/sonic-startup-ablation/run-ofbwc_6t/outputs \
  --output /tmp/sonic-startup-analysis-new.json
```

推論を新規に再実行する場合だけgalleriaが必要（G1不要）:

```bash
make startup-ablation-run INPUT=artifacts/sonic-startup-ablation/run-ofbwc_6t/input.json
```

新規artifactへ配置、GPU側上限150秒＋TERM後3秒、SSH側180秒、出力回収30秒。
`config/development.json`の既存GPUビルド/モデル/鍵/依存配置を使用する。
元記録からprepareし直す場合は`run_startup_ablation.py --prepare-only --baseline-directory ...`。
独立診断の外部成果（prepared-01/inputs.jsonとresults-01/startup.json）も必要。
共有先では上記の準備済みinputと48条件の結果を揃えれば、外部ディレクトリなしで保存検証できる。
inputには既存出典のローカルパス文字列が残るが、鍵の内容やパスワードは含めない。

## 次の開発境界

既定の履歴/参照/正規化/headingを今回の結果だけで変更しない。
配列変換不一致とpadding単独説を優先根因とする証拠は得られなかった。
次は初期姿勢・全身参照の適用条件と、制御権/遷移/停止の実機境界を設計する。
上流INITを診断のために実行したり、単にdefaultへ寄せて動かして確かめる手順は提供しない。
低レベル送信・制御権/停止・支持条件の検証は別課題。
実機動作が必要な場合は具体的な範囲と終了方法を定義し、明示許可を得る。
