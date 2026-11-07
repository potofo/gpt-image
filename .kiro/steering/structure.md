# プロジェクト構成

## 構成の考え方

本リポジトリは2つのレイヤーで構成される。

1. **開発プロセス基盤** — Kiro 流の Spec-Driven Development を駆動する仕組み（`.kiro/`、`.claude/commands/`）。
2. **プロダクト成果物** — Claude Code の Agent Skill 本体（`.claude/skills/gpt-image/`、実装済み・生成＋編集）。

スキルは「自己完結したディレクトリ」として配置し、起動条件・手順（`SKILL.md`）と実行ロジック（`scripts/`）を分離する。

## ディレクトリパターン

### Agent Skill 本体（実装予定）
**場所**: `.claude/skills/gpt-image/`
**目的**: スキルの起動条件・使い方とその実行ロジックを自己完結させる。
**構成例**:
```
.claude/skills/gpt-image/
├── SKILL.md              # frontmatter（name/description にトリガー語）+ 前提・パラメータ要約・コマンド例
├── scripts/
│   ├── generate_image.py # 画像生成 CLI（images/generations）
│   ├── edit_image.py     # 画像編集 CLI（images/edits・単一/マージ/mask）
│   └── （config/models/validation/auth/client/storage を共通モジュールとして分割）
├── tests/                # pytest
└── requirements.txt
```

### 仕様（Specs）
**場所**: `.kiro/specs/`
**目的**: 個別フィーチャーの要件 → 設計 → タスクを形式化する。`/kiro:spec-*` コマンドで管理。

### ステアリング（Steering）
**場所**: `.kiro/steering/`
**目的**: プロジェクト全体のルール・コンテキストをプロジェクトメモリとして保持する。

## 出力ファイルの命名規則

- 生成・編集画像: `<title>_<timestamp>_<index>.<ext>`。`<title>` はプロンプトから導出した安全なファイル名（禁止文字除去・空白ハイフン化・切り詰め、空なら `image`）、`<timestamp>` はマイクロ秒精度。`--n > 1` のときは同一 timestamp + 連番で保存。
- 既定の保存先は `./images`（無ければ自動作成、`--output`／`GPT_IMAGE_OUTPUT_DIR` で変更可）。
- 保存後は **絶対パスを `stdout`** に出力し、Claude がユーザーに提示できるようにする。

## 設定・既定値の解決

- 認証・接続: `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT`（必須）、`AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_API_VERSION`（任意）。
- パラメータ既定値: `GPT_IMAGE_*`（`GPT_IMAGE_SIZE` 等）。優先順位は **CLI 引数 > `.env`（環境変数） > 組み込み既定**。
- `.env` はカレントから上位へ探索し、OS 環境変数を上書きせず未設定分のみ補完する。

## ドキュメントの言語

プロジェクトファイルに書き出す Markdown（requirements / design / tasks / steering 等）は、その spec の `spec.json.language`（未設定時は日本語）に従う。

## コード構成の原則

- **ロジックの集約**: API 呼び出し・検証・保存はスクリプトに閉じ込め、`SKILL.md` には手順とコマンド例のみを記述する。
- **シークレットを構成に置かない**: 認証情報は環境変数経由でのみ受け渡す（`.claude/skills/` 配下のファイルに直書きしない）。
- **入力検証の前倒し**: 不正なパラメータは API 呼び出し前にスクリプトで弾く。

---
_ディレクトリツリーではなくパターンを記述する。パターンに従う新規ファイルは更新不要_
