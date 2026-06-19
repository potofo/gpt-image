# プロジェクト構成

## 構成の考え方

本リポジトリは2つのレイヤーで構成される。

1. **開発プロセス基盤** — Kiro 流の Spec-Driven Development を駆動する仕組み（`.kiro/`、`.claude/commands/`）。
2. **プロダクト成果物** — Claude Code の Agent Skill 本体（`.claude/skills/gpt-image-2/`、これから実装）。

スキルは「自己完結したディレクトリ」として配置し、起動条件・手順（`SKILL.md`）と実行ロジック（`scripts/`）を分離する。

## ディレクトリパターン

### Agent Skill 本体（実装予定）
**場所**: `.claude/skills/gpt-image-2/`
**目的**: スキルの起動条件・使い方とその実行ロジックを自己完結させる。
**構成例**:
```
.claude/skills/gpt-image-2/
├── SKILL.md              # frontmatter（name/description にトリガー語）+ 前提・パラメータ要約・コマンド例
├── scripts/
│   └── generate_image.py # 画像生成本体（CLI 引数 + 検証 + 保存）
└── references/
    └── parameters.md     # パラメータ詳細リファレンス（任意）
```

### 仕様（Specs）
**場所**: `.kiro/specs/`
**目的**: 個別フィーチャーの要件 → 設計 → タスクを形式化する。`/kiro:spec-*` コマンドで管理。

### ステアリング（Steering）
**場所**: `.kiro/steering/`
**目的**: プロジェクト全体のルール・コンテキストをプロジェクトメモリとして保持する。

## 出力ファイルの命名規則

- 生成画像: `gpt-image-2_<timestamp>_<index>.<ext>`（`--n > 1` のときは連番で保存）。
- 保存後は **絶対パスを `stdout`** に出力し、Claude がユーザーに提示できるようにする。

## ドキュメントの言語

プロジェクトファイルに書き出す Markdown（requirements / design / tasks / steering 等）は、その spec の `spec.json.language`（未設定時は日本語）に従う。

## コード構成の原則

- **ロジックの集約**: API 呼び出し・検証・保存はスクリプトに閉じ込め、`SKILL.md` には手順とコマンド例のみを記述する。
- **シークレットを構成に置かない**: 認証情報は環境変数経由でのみ受け渡す（`.claude/skills/` 配下のファイルに直書きしない）。
- **入力検証の前倒し**: 不正なパラメータは API 呼び出し前にスクリプトで弾く。

---
_ディレクトリツリーではなくパターンを記述する。パターンに従う新規ファイルは更新不要_
