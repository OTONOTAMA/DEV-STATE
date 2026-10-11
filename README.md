# DEV_STATE

Lightweight, file-based development progress and evidence tracking for AI-assisted work. Python standard library only; no daemon, database, LLM API or automatic model routing. MIT licensed.

[English](#english) | [日本語](#日本語)

## English

### What it does

During context compaction, handoff or long-running AI development, an agent may forget progress or resume with a work state that differs from reality. DEV_STATE helps an AI resume interrupted development without repeatedly reconstructing what was done. It separates AI-declared progress from machine-collected hashes and test receipts. A read-only `status --compact` returns at most 4,096 UTF-8 bytes. State is bound to its root and owner; generation checks and OS writer locks reject conflicting updates.

It complements supplementary memory and checkpoints; it does not replace them. For selected policies, preferences and facts, see [Codex Auxiliary Memory](https://github.com/OTONOTAMA/Codex-Auxiliary-Memory). Stored progress is never execution authorization. A passing command is evidence about that command, not proof that an entire development task is correct.

### Download and setup

**Standard scope: PROJECT code/Hook, CHAT / SESSION state.** Common code is
installed at the intended working/Git root; progress and evidence live in
`DEV_STATE/codex-sessions/<session_id>/`. Project-local configuration limits its
effects; shared code does not mean shared progress. Never adopt another session's
state, even in the same project. Auxiliary Memory's project-shared facts are not
this chat's development progress authority.

Local files do not automatically share across people or PCs. Use one local writer
environment and keep live state, receipts, logs and private settings out of
Git/public uploads. Inspect access and tracked files: ignore rules do not untrack data.
GLOBAL/user-wide integration is not shipped. Codex must assess feasibility,
affected chats, ownership, duplicate Hooks and tests, then confirm intent/approval
for nonstandard changes. Do not silently overwrite, migrate or mix existing
Hooks/settings/memory/progress/trust. Agent preflight: [INTEGRATION.md](INTEGRATION.md).

Setup and validation are agent-led; human action is needed only for required choices or security/trust approval.

Give your AI agent **DEV_STATE-v1.1.1.zip** from [Releases](https://github.com/OTONOTAMA/DEV-STATE/releases) and the setup request below. Have it check SHA256SUMS.txt, extract into a new folder and verify the internal manifest. The automatically generated source archives are for development. The agent's verification command (also available for manual use) is:

```text
python -B -X utf8 tools/release.py --verify
```

Use a verified host Python. Windows/Python 3.14 is the tested environment; other interpreters and operating systems require local validation. No pip packages are required.

For an AI-assisted setup, give the extracted package to your AI with this instruction:

> Read README.md and INTEGRATION.md. Set up DEV_STATE for this chat using a new chat-owned state, preserving existing hooks, skills, checkpoints and authorization rules. Check the manifest, run the supplied isolated tests and manually check compact status. Do not adopt someone else's state. Only configure integrations within my authorized scope; explain any required trust review. Treat real hook delivery as unverified until observed.

Core operations work manually without a Skill or Hook. See [INTEGRATION.md](INTEGRATION.md) for exact CLI arguments, JSON templates and setup boundaries. Optional Codex setup is documented in [SETUP.md](DEV_STATE/codex-adapter-g7/SETUP.md). Bionic integration requires adapting its existing resume/checkpoint mechanism; a universal Bionic installer is not included.

### Package and safety

Saved state may be stale or incomplete. Identity, generation and evidence checks help detect mismatches, but do not guarantee correct task selection or perfect restoration.

- Common core, schemas, Windows launcher and isolated selftests.
- Optional Codex SessionStart adapter, hook template and isolated adapter tests.
- Fresh operation templates and integration guidance; **no personal chat state, receipts, credentials, private configurations or hook trust**.
- `verify` executes the specified command: authorize and inspect it before use. This is not a sandbox and does not constrain everything a child process can do.
- JSON schemas are descriptive; the core's runtime checks enforce its actual contracts.
- No automatic initialization, migration, all-turn saving or automatic approval restoration.
- The Codex adapter reads state only. After compact it can remind the AI to save clear material changes; the Hook itself never saves progress.
- Windows behavior is tested. Real delivery, trust and AI refresh behavior must be checked independently on each target client. Power-loss durability and cross-PC/cloud-sync concurrency are not guaranteed. Use one local writer environment; do not share live state between PCs.

### Maintenance

The release retains the existing portable v1.1 core and adapter unchanged. Runtime folder names remain stable. Read [docs/VALIDATION.md](docs/VALIDATION.md) and [docs/UNINSTALL.md](docs/UNINSTALL.md). Build from source with `python -B -X utf8 tools/release.py`; build-time tests use temporary fixtures, not installed chat state. `dist/` is generated, not source.

## 日本語

### 何をするもの？

コンテキスト圧縮・ハンドオフ・長時間のAI開発では、AIが進捗を忘れたり、実際と異なる作業状態から再開したりすることがあります。DEV_STATEは、AIが開発を中断・再開するとき、「どこまで実装したか」を毎回調べ直す負担を減らす軽量ツールです。AIの進捗申告と、マシンが採取したファイルhash・テスト証拠を分けて保存します。通常の復旧は読み取り専用の `status --compact`（最大4,096 UTF-8バイト）から始めます。状態は保存先と所有者に結び付けられ、世代の照合とOSの書込みロックで競合する更新を拒否します。

補助記憶・チェックポイントを置き換えるものではありません。選択したポリシー・好み・事実の保持には、相互補完する[Codex Auxiliary Memory](https://github.com/OTONOTAMA/Codex-Auxiliary-Memory)を利用できます。保存された進捗は実行許可ではなく、テスト1件のPASSを開発全体の完了とは扱いません。

### 導入方法

**標準はPROJECT内のコード/Hook、CHAT / SESSION別の状態です。** 共通機能は対象の
working/Git rootへ配置し、進捗・証拠は`DEV_STATE/codex-sessions/<session_id>/`で分離します。
設定の影響をプロジェクト内に限定する方式で、機能の共用は進捗の共有を意味しません。
同じプロジェクトでも別チャットの状態を採用しません。Auxiliary Memoryの共有事実も、
このチャットの進捗を確定する根拠とは別です。

複数人・複数PCへの自動共有はありません。単一ローカル環境で書き込み、閲覧範囲とGit追跡対象を
確認して実状態・receipts・ログ・固有設定の公開混入を防ぎます。ignoreは既存追跡を解除しません。
GLOBAL/ユーザー全体の導入は同梱機能ではなく、Codexが対応可否・影響・所有・Hook重複・検証を
検討し、意図と非標準変更の承認を確認します。既存Hook・設定・記憶・進捗・信頼を自動で
上書き・移行・混合しません。AI向け事前確認は`INTEGRATION.md`。

設置・検証はAIへ任せ、人間の操作は必要な選択やセキュリティ/信頼承認に限ります。

[Releases](https://github.com/OTONOTAMA/DEV-STATE/releases) の **DEV_STATE-v1.1.1.zip** と下記の依頼をAIへ渡し、SHA256SUMS.txt照合・新しいフォルダへの展開・内部manifest検証を任せてください。自動生成の Source code ZIP は開発用です。AIは確認済みのPC側Pythonで `python -B -X utf8 tools/release.py --verify` を実行し、内部manifestと隔離テストを確認します（手動実行も可能）。pipの追加ライブラリは不要です。

AIへのセットアップ依頼例：

> README.mdとINTEGRATION.mdを読み、このチャット専用の新しい状態としてセットアップして。既存のSkill・Hook・checkpoint・認可ルールを保持し、manifest照合・同梱の隔離試験・手動statusを確認して。他人や別チャットの状態は採用しない。許可された範囲だけ連携設定し、必要な信頼登録を案内して。実際のHook発火は観測するまで未確認扱いにして。

Codex用の連携部品は任意です。Bionicでは既存の復旧手順に合わせた統合が必要で、汎用の自動インストーラーはありません。HookやSkillなしでも共通コアを手動で利用できます。

### 大事な制約

保存状態が古い・不完全な場合があります。所有者・世代・証拠の照合は不一致の検出を助けますが、誤ったタスク選択や状態復元を完全には防ぎません。

個人の進捗・receipts・過去ログ・認証情報・固有設定・Hookの信頼情報は入っていません。`verify` は指定コマンドを実行するため、実行前に内容と許可を確認してください。子プロセス全体を封じ込めるサンドボックスではありません。

Hookは読み取り専用です。圧縮後にAIへ更新確認を促しても、全作業を自動保存したり最新進捗を保証したりはしません。Windows/Python 3.14を検証対象とし、別PC・別クライアントの実発火と信頼登録は各環境で確認が必要です。停電時の永続性やクラウド同期越しの複数PC同時更新は保証しません。

### 保守・ライセンス

MITライセンスです。既存のportable v1.1からコアとアダプターの動作は変更していません。保守方法・検証範囲・安全な撤去方法は `docs/` を参照してください。
