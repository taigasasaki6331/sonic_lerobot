# Codex Cloudへの引き継ぎ（2026-10-02）

> 公開用コピー：ネットワーク値・機器識別子・ローカルパスは例へ置換。保存試験結果は原本の記録で、例設定で実機試験した証拠ではありません。クラウドから機器接続・実機指令を行わないでください。


## 現在の環境と目的

ユーザーはgalleriaのネットワークから離れており、G1も起動できない。
クラウドでは実装・CPUテストを続け、GPU/MuJoCoのモデル推論・実入力・実機検証は接続可能時に戻す。
クラウド移行は実機送信の許可ではない。SSH鍵・パスワードを持ち込まず、LANへの接続も要求しない。
目標・到達点・残課題の正本は `AGENTS.md` → `docs/HANDOFF.md` → `docs/IMPLEMENTATION_TODO.md`。

## 移行パッケージ

```bash
make cloud-export OUTPUT=artifacts/cloud-source/new-snapshot
```

現在の未コミット/未追跡コードも含む、新規ディレクトリへのローカルコピー。元のGit・ファイルは変更しない。
ソース、設定、README/引き継ぎ、ライセンス、PIKA形状、データmanifest、固定URDFを収録。
固定SONIC/Unitree SDKのテストに必要なソース部分を `vendor/` に収録し、各ファイルSHAを
`cloud-source-manifest.json` に保存する。完全な上流checkoutや実行環境ではない。
Git履歴、認証ファイル、known_hosts、実演データ本体、モデル重み、映像、ログ、バイナリ、venvは除外。
設定/文書に既存ホスト名・IP・絶対パスは残るが、クラウドでそれらに接続する手順ではない。
既存データ・学習済みACTがなくなったわけではない。ローカル/GPUの保存資産として維持する。
パッケージの `.gitignore` のみ、収録vendorとURDFをGitに含められるよう変更する。

公開先は**非公開GitHubリポジトリ**を想定。
利用者指定は `https://github.com/taigasasaki6331/sonic_lerobot`。
新規 `codex/cloud-handoff-20261002` は作成済み（起点main、SHA68c7294475646f3bdb373594c806d7f1b95b9e86）。
確認時のvisibilityはpublicで、利用者は公開のままでの送信を了承。
`export_cloud_source.py --public --output 新規ディレクトリ` は配置情報を例へ置換した別コピーを作る。
URDFはmesh filenameだけ相対パス化し、原本SHAと派生SHAを記録。関節/慣性パラメータは変えない。
元のローカル設定/URDF/ログは変更しない。公開例をそのまま実機へ配置しない。
remote既存のπ0/π0.5・48次元/PIKAなし方式を保存し、今回のACT/10次元/PIKAは`g1-pika/`へ配置する。
クラウドではroot AGENTSに従い、`cd g1-pika`して作業する。両方式の依存・actionを混同しない。
パッケージ生成だけでは、GitHubへの公開・Codex Cloud環境の作成・会話の転送は行われない。
既存GitHubに送る場合は、その既存内容を確認して統合し、force push/上書きをしない。

## クラウドのセットアップ

Linux、Python 3.10〜3.12（現地確認は3.10）、gcc/g++、make、libzmq.so.5、Python venv/pipが必要。
不足時のUbuntuパッケージは `build-essential python3-venv libzmq5`。
セットアップ処理はsudo/aptを自動実行せず、不足を表示する。

```bash
make cloud-setup
make cloud-check
```

専用 `.venv-cloud` と `requirements-cloud.lock` を使用。既存 `.venv` は変更しない。
`cloud-check` はaction/観測・履歴/身体状態機械/SDK構文・データCRC/native疑似writer/online fake workerの
18スクリプト。機器接続、モデル推論、物理シミュレーション、実機送信は行わない。
local body serviceのIPC2ケースは通常チェックでは明示skip。IPC可能な環境で追加する場合：

```bash
.venv-cloud/bin/python -I scripts/check_local_body_service.py --ipc
.venv-cloud/bin/python -I scripts/run_body_runtime.py --seconds 5
.venv-cloud/bin/python -I scripts/run_body_runtime.py --seconds 5 --scenario body_expiry
```

後二つは人工入力/SDK-freeメモリ出力の統一起動。スケジューラ条件で期限試験が失敗し得る。
失敗を閾値緩和や自動再armで隠さない。クラウド結果はG1/aarch64・500Hz実時間・物理停止の認定ではない。
`make run` / `online-record` / GPU・G1 probeはクラウドで実行しない。
CUDA/TensorRT/ACT/SONIC重み/完全IK/MuJoCo環境はこのCPUパッケージの対象外。

## 最初のクラウドタスクへ貼る指示

> このリポジトリのAGENTS.md、docs/CLOUD_HANDOFF.md、docs/HANDOFF.md、
> docs/IMPLEMENTATION_TODO.mdを読み、Unitree G1＋PIKA＋LeRobot＋GEAR-SONICの開発を継続してください。
> 現在galleriaへ接続できず、G1も起動できません。コード実装と送信なし検証を進めてください。
> make cloud-setup / make cloud-checkを確認し、細かな診断の追加より一本の起動・停止経路を優先してください。
> 次の開発対象は、既存G1-local record runtimeとbuild-only Unitree SDK接続部の統合設計・実装です。
> 実SDKの初期化/制御権/送信/停止/復帰を明示的に分離し、既定record-onlyと疑似transportで検証してください。
> 実機・カメラ・シリアル・DDS publisher・通常G1Deployは起動せず、秘密鍵を要求しないでください。
> 保存実入力では147/150件のSONIC目標がURDF範囲外で、実機移行の阻害要因として残っています。
> clipping/閾値緩和/偽の状態で合格にせず、MuJoCo成功と実機未検証を区別してください。
> 未コミット変更・データ・証拠を保存し、README/HANDOFF/TODOへ変更と検証範囲を記録してください。
> 必要な判断・権限がない限り、途中の継続確認は不要です。

## Codex側の操作

非公開GitHubにコードが置かれた後、Cloudの環境作成で対象リポジトリを選択し、上記CPUセットアップと
テストを指示する。セットアップ結果を確認してPublishし、新規タスクへ上記指示を貼る。
GitHub接続/リポジトリ選択/環境Publishはユーザーアカウント側の操作が必要。
[公式の環境作成手順](https://learn.chatgpt.com/docs/environments/cloud-environments)。
