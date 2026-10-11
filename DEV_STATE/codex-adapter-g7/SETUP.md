# Codex用連携部品 — 別PCへの導入

## 役割

startup/resume/compactで、このセッションの保存状態を復旧する。
compact + 共通コアexit0/status OK/reconciliation HASH_MATCHの場合だけ、AIへ更新確認を促す。
Hookは読取専用。全作業の自動保存、情報喪失の復元、最新進捗の保証ではない。
sourceをhook_sourceへ保持し、指示込みadditionalContextを4096 UTF-8 bytes以内にする。

## 導入

標準はPROJECT内の共通機能とCHAT / SESSION別の状態。機能の設置先と進捗の共有範囲は別です。
同じプロジェクトでも別チャットの進捗やAuxiliary Memoryの共有タスクを採用しません。
GLOBAL導入は提供せず、非標準の変更には対応可否・影響・所有・重複・検証と意図/承認の確認が必要。
複数人/複数PCでローカル状態が自動共有されるわけではありません。単一ローカル環境で書き込みます。
導入前にINTEGRATION.mdの事前確認を読み、Git追跡/公開への実状態・receipts・個人情報・固有設定の
混入を防ぎ、既存コード/Hook/記憶/進捗/信頼を勝手に上書き・移行・混合しません。
対象と許可が明確な標準構成では、AIが不要な再質問なく導入・検証します。

Standard = PROJECT-local common code/Hook, CHAT / SESSION-owned progress.
Follow INTEGRATION.md preflight: no other-chat state adoption, no implicit GLOBAL
setup or cross-PC/user sharing, no private data in Git, no unapproved overwrite,
migration, mixing or trust changes. For clear standard setup, proceed autonomously.

1. manifestのhashとbytesを確認する。Python標準ライブラリ以外の追加依存なし。
2. このPCのホストPythonを確認する。Windows/Python 3.14が元環境の検証対象。
3. 共通コアと本部品を `<working-root>/DEV_STATE/` に同梱構造どおり配置する。
   Git環境では最寄りrepository root、非Gitでは共通コアmarkerがあるrootを使う。
4. 確認済みPythonで `python -B -X utf8 test_post_compaction_refresh.py` を本フォルダから実行する。
   専用fixtureだけを作成し、終了後削除する。既存状態・Hookを変更しない。
5. hooks.template.jsonのPython/adapterプレースホルダーを導入先の絶対パスで置換する。
6. 対象プロジェクトのHook設定へSessionStart handlerをマージする。
   既存Hookを上書きせず、user/project/pluginの二重登録を避ける。
7. 新Hook定義を導入先の正規UI/CLIでユーザーが信頼登録する。trusted_hashをコピー・偽造しない。
8. 実セッションIDを機械証拠で確認し、task_id/context_keyを同じIDで初期化する。
   状態は `<working-root>/DEV_STATE/codex-sessions/<session_id>/`。
   状態未作成時はHookが何もしない。過去PCの状態やGOをコピーしない。

## 確認

起動/再開: 正しいroot、identity、generation、整合性が注入され、更新指示がないこと。
実compact: hook_source=compactとDEV_STATE_REFRESH指示が1回届くこと。
AI運用: 同じタスクの未記録差分だけ正規コアで保存し、変更なし・不明・対象外なら保存しないこと。
AI更新の試験は許可された専用状態を使い、既存開発状態を試験のために改変しない。
異常状態では更新指示なし。診断に従い、別rootを探さない。
手動イベント再生や隔離テストPASSを、実compactの確認済みと混同しない。

## 更新・復元

既存コアはv1.1で変更されていない。既存アダプター更新時は旧ファイルを保全し、本部品を差し替える。
設定や信頼レビューが必要な場合は正規手順で行う。ZIP展開だけでは登録しない。
復元は保全した旧アダプターへ戻す。state/current/receiptは書き換えない。
個別PCのPythonパスや信頼情報は本配布物には含めない。
