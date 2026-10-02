# G1身体SDKアダプター（build-only）

2026-10-01。身体送信・制御権解除/復帰・damping候補のSDK接続コードを追加した。
**現行の記録サービスからは呼ばず、実機起動コマンドも提供しない。**
実SDKのリンク・起動・実動作・物理停止を検証したものではない。

## 実装範囲

- `body_io_adapter.hpp`：通信先を注入する薄いアダプター。コンストラクターでI/Oしない。
  record-only/診断ACKではI/O不可。試験許可・支持/停止手順・実構成の契約が欠けても拒否する。
  契約値は将来の現場操作フローから渡す入力で、boolや文字列だけで物理条件を立証しない。
- `unitree_body_transport.cpp/.hpp`：固定Unitree SDKのCheckMode/ReleaseMode/SelectModeと
  `ChannelPublisher<LowCmd_>`への実接続コード。既定`G1_PIKA_ENABLE_BODY_IO=0`で全I/Oを拒否。
  ビルドflagを変えても動作許可や現場準備の代わりにはならない。直接backendを呼ぶ実行入口はない。
- クエリー用channelと身体publisherは別の明示操作。クエリーだけでReleaseModeしない。
  解除は1回のみ、RPC失敗/既存mode残存ではpublisherを開かない。
  CheckModeの空nameはその時点のSDK返答で、排他的な制御権leaseの証明ではない。
- 通常出力は同一ホストCRC/年齢100ms以内/P-R/machine一致、有限値/float32/29関節範囲/ゲインを検査。
  sourceは信頼できるG1-local監視から渡す必要があり、GPUが申告したbodyで代用しない。
  セッション・目標期限/変化/速度・初期姿勢・モーター異常などの上位gateway検査は別責務。
- LowCmdはmode_pr=0、29motor、未使用6slot/reserve/paddingは0、固定CRC関数を使用。
  Dex3・PIKAへの出力は実装しない。PIKA幅をbody motor指令にしない。
- damping候補は呼出側が明示した正の29 kdのみ。既定8などを勝手に採用しない。
  q/dq/tau/kp=0の候補であり、ゲイン/実停止の妥当性は未検証。
  停止ラッチをSDK書込みより先に立て、GPU応答/RPC/joinを先に待たない。
  SDK Writeのblocking/遅延は未検証、停止時間の保証はない。
- SDK書込み成功は`physical_stop_confirmed=false`のまま。
  モード復帰は別途の現場停止確認記録が必要で、publisherを閉じてから以前のnameをSelectModeする。
  machine/P-R変更後のdamping/復帰は拒否し、物理的な別停止手段を必要とする。
  destructor/error cleanupで解除・停止・復帰を暗黙に行わない。

このアダプターは単一のG1 I/O-owner threadから使う設計。
500Hz scheduler、実時間保証、LowState reader、物理的な非常停止装置ではない。
現行BodyLifecycleの人工ACKを、実機adapterの承認/実制御権の確認へ変換しない。

## 検証・再現

```bash
# ローカル、通信なし：疑似transportとSDK APIの構文検査
.venv/bin/python -I scripts/check_body_io_adapter.py

# G1/galleriaが必要：G1でobject compile＋SDKを使わない疑似transportだけ実行
make body-io-build-check
```

新規2単体試験（10月1日内部18条件、10月2日identity lossラッチ追加で19条件）成功。
既定IO禁止、許可条件不足、勝手な解除なし、RPC失敗、
解除再試行禁止、publisher前のmode確認、古い/CRC未確認/型式変更入力、範囲外、書込み失敗、
停止ラッチ後の送信拒否、停止候補値、復帰前確認/close順序を検査した。
疑似試験の許可・停止確認は人工入力で、現場の承認ではない。

G1/aarch64最終結果は`artifacts/body-io-build/body-io-build-FT3T3p/outputs/`。
10月1日版SDK接続コードはflag0/1双方でobject compile成功（リンク/実行なし）。
実行したのはSDKヘッダーすら使わない疑似transportの18条件のみ。
SDKソース・ライセンスを隔離ディレクトリへコピーし、既存環境は上書きしていない。
前回run-6PeMLBも保存。新たなパッケージinstallなし。
10月2日のnative writer接続/identity lossラッチ追加版はtigerで確認、G1再compileは未実施。
[native writer](BODY_WRITER.md)も実出力には未接続。

## 次に残る実装

1. G1-local monitor/物理ownership/初期姿勢と接続する実gateway。
   モーター状態・型式・支持/装着条件・セッション/期限を統合し、診断ACKと分離する。
2. 500Hz writerと独立停止要求、通信断/SDK書込み失敗時の実運用。
   native 2ms loop/停止要求は10月2日疑似通信先で実装・検査済み、実機統合は未完。
   実時間計測・停止方法の現場確認、SDK linking/起動/終了の検証が必要。
3. LeRobot→IK→SONICの実機用起動遷移/参照適合性。
   保存出力の147件の範囲超過は未解決、simの起動変化量も実機gateと未一致。
4. 限定試験の現場条件と明示許可。右PIKA取り外し中のため、PIKA TCP/質量や把持条件を
   現実機の条件に使わず、PIKAを使う試験は再装着/構成確認後に行う。
