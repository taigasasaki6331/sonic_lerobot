# PIKA移植部品の出典

追記: STL3点は同じPCの `PikaAnyArm/piper/piper_ros/piper_description/meshes/` と
SHA-256がすべて一致した。実物PIKA専用CADとの確認は取れていないため、Piperと同じ代替形状として扱う。

取得元: https://github.com/kufusha/pika_ros
固定コミット: `0f7f6b75a349ceccb252628f5f48a28aaf5c7b6b`。

- `*.STL`: `src/g1_pika_description/meshes/pika/` の3ファイルを変更せず移植。
  ローカルのコピー元と固定Gitコミットのバイト列が一致することを確認。
- `source/generate_urdf.py`: 同パッケージの `scripts/generate_urdf.py`。
  元コードを保存し、`add_pika()` の取付変換・TCP・質量・慣性定義だけを呼び出す。
- `source/package.xml`、`source/README.md`: 同パッケージの宣言・説明を保存。
- `source/REPOSITORY_LICENSE`: 元リポジトリ直下のBSD-3-Clauseライセンス文書を保存。

パッケージはApache-2.0を宣言しているが、リポジトリ直下はBSD-3-Clause（Tixiao Shan名義）。
出典を残すため両方の情報を保存する。STLごとの権利者・CADの由来は元ファイルからは確定できていない。
Apache-2.0本文も `APACHE-2.0.txt` に添付。

取付部品の定義は変更せず、新規ビルダー `scripts/pika_model.py` で次を行う。
純正ハンドを除去、爪をq=0で固定、衝突用mesh追加、G1側の運動学・慣性をWBCのMJCFに統一。
生成物は `artifacts/models/`。配線・取付金具・センサーの追加質量は未計上。
元リポジトリのプログラムやグリッパ通信を起動することはない。
