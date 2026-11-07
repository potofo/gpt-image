# 技術スタック

## アーキテクチャ

Claude Code の **Agent Skill** として実装する。Claude は `SKILL.md` に記述された手順に従い、自己完結した Python スクリプトを CLI として呼び出す。生成ロジック・パラメータ検証・保存処理はすべてスクリプト側に閉じ込め、モデルのコンテキストには API 詳細やシークレットを載せない。

```
ユーザー依頼 → Claude（SKILL.md の手順）→ generate_image.py / edit_image.py（検証・API 呼び出し・保存）→ Azure gpt-image-2 / gpt-image-2.5-flare / gpt-image-2.5-sunburst
```

モデル種別ごとの違い（使える値・機能・タイムアウト・デプロイ名の環境変数）は `scripts/capabilities.py` の対応表だけで宣言し、他のモジュールはモデル名で分岐しない。

## コア技術

- **言語**: Python 3.10+
- **対象モデル / API**: Azure AI Foundry `gpt-image-2`・`gpt-image-2.5-flare`・`gpt-image-2.5-sunburst`（`images/generations`・`images/edits`）、API バージョン `2025-04-01-preview` 以降。エンドポイントは deployments 形式（既定）と v1 形式（`/openai/v1/images/...`）に対応
- **HTTP / SDK**: `requests`（SDK は使わない）
- **認証**: `azure-identity`（Entra ID 認証時）
- **画像ヘッダの解析**: 標準ライブラリのみ（Pillow などの画像ライブラリは追加しない）

> gpt-image-2 / 1 系は **限定アクセス登録（limited access）** が必要。2.5 系は Azure で GA。

## 開発標準

### パラメータ設計

- 必須引数は `--prompt` のみ。他はすべて任意で推奨デフォルトを持つ。
- 値の検証は **API へ投げる前にスクリプト内で行う**（不正値は終了コードとともに `stderr` でエラー）。
- パラメータ依存関係を検証する（例: `--background transparent` は `--format png` 必須、`--compression` は JPEG 時のみ有効）。
- `size` 制約（全モデル共通）: 両辺が 16px の倍数 / 長辺 3840px 以下 / アスペクト比 3:1 以下 / 総ピクセル数 655,360〜8,294,400。2.5 系では 2560x1440 超を experimental として警告する。
- モデル種別によって許される値（quality の xhigh/max/auto、background の opaque、complexity、markup）は対応表で検証する。argparse の `choices` には書かない。

### セキュリティ（最重要）

- エンドポイント・デプロイ名・キーは **環境変数**（`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_API_KEY`）からのみ取得する。
- **`SKILL.md` やスクリプト本体にシークレットを直書きしない**（モデルのコンテキストに載るため）。
- キー・トークンを `stdout` / `stderr` / ログに出力しない。
- 認証は **Entra ID（キーレス、`DefaultAzureCredential`）を優先**し、API キー認証を代替とする。API キーは Azure Key Vault で管理しローテーションする。

### エラーハンドリング

- HTTP エラー（401/403/429/400 等）を区別して原因を `stderr` に出す。
- コンテンツモデレーション拒否は、ユーザーに分かるメッセージにする。
- `429`（レート制限）は上限付き指数バックオフでリトライ。

## 主要な技術的判断

- **ロジックのスクリプト化**: Claude に API を直接書かせず、再現性・検証・安全性をスクリプトに集約する。
- **キーレス優先**: 長期間有効なキーを保存しないため Entra ID 認証を第一選択とする。
- **API 仕様の検証必須**: `background` / `output_format` の対応について公式ドキュメントに表記揺れがあるため、使用する `api-version` で実挙動を必ず検証する。WEBP は Azure では未確認のため無効（`capabilities.AZURE_ENABLED` のフラグで管理し、Azure 実機での確認結果を `research/` に記録してから切り替える）。

## パフォーマンス

生成は概ね 10〜30 秒。タイムアウトは余裕を持って設定する（gpt-image-2: 生成 120 秒・編集 180 秒、2.5 系: 300 秒。2.5 系は複雑なプロンプトで最大 2 分程度かかる）。

---
_標準とパターンを記述し、依存関係の網羅列挙は避ける_
