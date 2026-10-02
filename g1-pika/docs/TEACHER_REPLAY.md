# 教師action再生（2026-09-14）

## 起動と確認済み範囲

`make teacher-view`。画面なしは `make teacher`、単体テストは `make check-teacher`。
追加インストール不要。学習用画像・動画は読み込まない。

既存LeRobot v3データセット
`/home/developer/workspaces/pika_ws2/datasets/data_2608261323_valid49_g1_zero_relative_h1_final_v3`
からepisode 0を選択。254フレーム、30 Hzの10次元actionのみをJSONスナップショット化した。
元データは変更していない。出典ファイル・SHA-256・元の項目名・抽出バージョンをJSONに保存。
このローカルデータの第三者配布権は確認していない。外部公開・push前に確認すること。

30秒の動力学試験に合格。右TCP移動最大8.395cm、目標移動最大7.519cm、
位置追従誤差最大3.403cm、姿勢誤差最大0.1159rad、IK位置誤差最大0.258mm。
胴体高さ最小0.744m、傾斜最大0.0872rad、MuJoCo警告0。
閾値は従来のまま。ユーザーがGUI完走を確認し、30秒の合格ログを提供。
GUI実時間79.25秒、WBC処理p95 9.05ms。リアルタイム性能の合格を意味しない。
結果は [teacher-30s-2026-09-14.json](teacher-30s-2026-09-14.json)。

## 変換契約

- action: 相対並進3 + 相対回転6D + 次フレームのグリッパ幅1。horizonは1。
- 回転は列順 `[r00,r10,r20,r01,r11,r21]`。
  データの項目名は行順を示すが、数値と既存変換コードは列順。
  明示的な指定と直交性チェックを行い、誤った並びを黙って正規化しない。
- ローカル相対変換を旧retarget実装と同じ順番で累積する。
  軸変換 `A = [[0,0,1],[0,-1,0],[1,0,0]]` は旧URDFのTCP→tracking回転。
  `p_next = p + R A delta_p`, `R_next = R A delta_R A^T`。
  軸原点の追加オフセットは0とする。実機較正の正しさを証明したものではない。
- 開始目標は新WBCの初期TCP（pelvis基準）へ再配置。
  元データの腕全関節0の絶対開始姿勢は再現しない。新WBCの肩rollは左右±0.2rad。
- 30 Hzで各actionを一度だけ積分し、位置線形補間・回転SLERPで50 Hzへ渡す。
  50 Hzごとに同じdeltaを重複積分しない。254番目の末尾actionも1刻みとして扱うため8.4667秒。
- 初期安定化2秒＋再生＋終了保持最低2秒が必要。時間不足は実行前に拒否。
  既定30秒、繰り返しなし。`--playback-rate`のみ明示変更可能、並進縮小や姿勢無効化はしない。
- 幅は保存・範囲報告のみ（約0.388〜89.435mm）。代替モデルの可動範囲へ変換せず、爪は固定。

## データ診断の訂正と未検証項目

前回報告した並進10.36mm・回転行列要素0.08385の「残差」は診断の誤りだった。
stateは絶対姿勢ではなく、毎フレームの現在TCPを原点とする単位姿勢＋現在のグリッパ幅。
異なる原点を持つstateを隣接差分にしてもactionとは比較できない。
元converterの `convert_pose_row_to_relative_state` と全49エピソード10,881フレームで確認。
初回結果JSONの旧診断値は履歴として残すが、データ異常の証拠として扱わない。

`make dataset-check` で全件再確認できる（このPCのsystem Python/pyarrow 23.0.1を使用）。
姿勢state契約とaction回転の直交性、フレーム連続性、fps、件数を検査。
姿勢の絶対軌道との照合・動画同期・データ品質の全面検証は含まない。

グリッパ幅はゼロ化されないため別途 `action[t].width` と `state[min(t+1,last)].width` を比較。
1µmを超える不一致145件、最大78.96mm。episode 0ではframe 69だけが3.331mm不一致。
こちらは実際の値の不一致だが、原因は未同定。加工・同期・元ログとの照合が必要。
実機開閉や把持の検証には進まない。元データと教師action自体は一切変更していない。
診断結果は `artifacts/dataset-check-latest.json`、記録は
[dataset-check-2026-09-14.json](dataset-check-2026-09-14.json)。

## LeRobotとの境界と次の工程

現在: 保存LeRobot action → 座標変換・時刻補間 → TCP目標 → IK → Decoupled WBC → MuJoCo。
最終: 実カメラ等の観測 → 指定LeRobotのポリシー推論 → actionアダプタ → WBC側の身体制御・低レベル送信。
Makeは起動のショートカットにすぎず、LeRobotを置き換えるものではない。

今回LeRobot本体や既存robotクラスは起動していない。旧 `send_action` 経路は実機送信を含むため再利用しない。
オンライン推論では観測時点のTCPに対する目標生成、action chunkの時刻・horizon、タイムアウトを別途設計する。
教師の累積再生器をそのままオンライン制御器として流用しない。
次は使用する学習済みモデルを確定し、保存観測からの推論actionをオフライン検査する。
その後WBC接続へ進む。グリッパ幅の不一致は別途元データへ遡って調べる。
実機制御開始は別段階。把持、カメラ込み実測質量・慣性・衝突外形の検証も未完了。

## スナップショット再抽出

通常の再生に以下は不要。このPCのsystem Pythonにある `pyarrow==23.0.1` を抽出専用に使用した。
再抽出時は同バージョンとNumPy/SciPyが必要。シミュレーション依存には追加していない。

```bash
python3 scripts/export_teacher.py \
  /home/developer/workspaces/pika_ws2/datasets/data_2608261323_valid49_g1_zero_relative_h1_final_v3 \
  --episode 0 --rotation-layout columns --output assets/trajectories/episode0.json
```

単体テストは回転の行/列、非可換なローカル変換、30/50/200 Hzでの到達目標一致、
速度変更、開始・終了条件、非有限値拒否を確認する。実機通信機能はない。
現在は6件。単位stateを絶対姿勢と誤認しない回帰試験と、幅不一致の検出も含む。

## 推論環境の事前確認

指定LeRobotの固定コミット79edf6a9のpyprojectはPython >=3.12。
WBCのPython 3.10環境へ混在させず、推論を別プロセス・別環境にする。
既存 `pika_g1_ik` conda環境は3.12.13だが、datasets 5.0.0がソースの `<5.0.0` 制約と不一致。
そのまま再現可能な新規環境として採用しない。既存環境には変更を加えていない。

ローカル候補には `zero_relative_50ep_act_h1_v2`、
`replace_tape_g1_pika_relative_h1_v2_act`、複数の学習途中チェックポイント、
HFキャッシュの `act_umi_true_relative_h1` がある。使用モデルはユーザー確認中。
学習設定のsteps値だけでは保存チェックポイントの到達step・性能を判断しない。
今回はモデルロード・推論、ダウンロード、実機通信のいずれも未実施。
