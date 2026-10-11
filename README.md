# DEV_STATE

Lightweight, file-based development progress and evidence tracking for AI-assisted work. Python standard library only; no daemon, database, LLM API or automatic model routing. MIT licensed.

## English

### What it does

DEV_STATE helps an AI resume interrupted development without repeatedly reconstructing what was done. It separates AI-declared progress from machine-collected hashes and test receipts. A read-only `status --compact` returns at most 4,096 UTF-8 bytes. State is bound to its root and owner; generation checks and OS writer locks reject conflicting updates.

It complements supplementary memory and checkpoints; it does not replace them. Stored progress is never execution authorization. A passing command is evidence about that command, not proof that an entire development task is correct.

### Download and setup

Download **DEV_STATE-v1.1.0.zip** from [Releases](https://github.com/OTONOTAMA/DEV-STATE/releases). The automatically generated source archives are for development. Check the ZIP against the supplied SHA256SUMS.txt, extract into a new folder, then verify the internal manifest:

```text
python -B -X utf8 tools/release.py --verify
```

Use a verified host Python. Windows/Python 3.14 is the tested environment; other interpreters and operating systems require local validation. No pip packages are required.

For an AI-assisted setup, give the extracted package to your AI with this instruction:

> Read README.md and INTEGRATION.md. Set up DEV_STATE for this chat using a new chat-owned state, preserving existing hooks, skills, checkpoints and authorization rules. Check the manifest, run the supplied isolated tests and manually check compact status. Do not adopt someone else's state. Only configure integrations within my authorized scope; explain any required trust review. Treat real hook delivery as unverified until observed.

Core operations work manually without a Skill or Hook. See [INTEGRATION.md](INTEGRATION.md) for exact CLI arguments, JSON templates and setup boundaries. Optional Codex setup is documented in [SETUP.md](DEV_STATE/codex-adapter-g7/SETUP.md). Bionic integration requires adapting its existing resume/checkpoint mechanism; a universal Bionic installer is not included.

### Package and safety

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

AIが開発を中断・再開するとき、「どこまで実装したか」を毎回調べ直す負担を減らす軽量ツールです。AIの進捗申告と、マシンが採取したファイルhash・テスト証拠を分けて保存します。通常の復旧は読み取り専用の `status --compact`（最大4,096 UTF-8バイト）から始めます。

補助記憶・チェックポイントを置き換えるものではありません。保存された進捗は実行許可ではなく、テスト1件のPASSを開発全体の完了とは扱いません。

### 導入方法

[Releases](https://github.com/OTONOTAMA/DEV-STATE/releases) の **DEV_STATE-v1.1.0.zip** をダウンロードし、SHA256SUMS.txtで照合して新しいフォルダへ展開してください。自動生成の Source code ZIP は開発用です。確認済みのPC側Pythonで `python -B -X utf8 tools/release.py --verify` を実行すると、内部manifestと隔離テストを確認できます。pipの追加ライブラリは不要です。

AIへのセットアップ依頼例：

> README.mdとINTEGRATION.mdを読み、このチャット専用の新しい状態としてセットアップして。既存のSkill・Hook・checkpoint・認可ルールを保持し、manifest照合・同梱の隔離試験・手動statusを確認して。他人や別チャットの状態は採用しない。許可された範囲だけ連携設定し、必要な信頼登録を案内して。実際のHook発火は観測するまで未確認扱いにして。

Codex用の連携部品は任意です。Bionicでは既存の復旧手順に合わせた統合が必要で、汎用の自動インストーラーはありません。HookやSkillなしでも共通コアを手動で利用できます。

### 大事な制約

個人の進捗・receipts・過去ログ・認証情報・固有設定・Hookの信頼情報は入っていません。`verify` は指定コマンドを実行するため、実行前に内容と許可を確認してください。子プロセス全体を封じ込めるサンドボックスではありません。

Hookは読み取り専用です。圧縮後にAIへ更新確認を促しても、全作業を自動保存したり最新進捗を保証したりはしません。Windows/Python 3.14を検証対象とし、別PC・別クライアントの実発火と信頼登録は各環境で確認が必要です。停電時の永続性やクラウド同期越しの複数PC同時更新は保証しません。

MITライセンスです。既存のportable v1.1からコアとアダプターの動作は変更していません。保守方法・検証範囲・安全な撤去方法は `docs/` を参照してください。
