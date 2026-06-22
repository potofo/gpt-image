# gpt-image-2 画像生成 Agent Skill 要件書

Claude Code から Azure (Microsoft Foundry) の `gpt-image-2` モデルを呼び出して画像を生成する Agent Skill の要件をまとめる。

---

## 1. 目的・概要

Claude Code 上で「画像を生成して」という依頼があったとき、Azure AI Foundry にデプロイした `gpt-image-2` モデルを使って画像を生成し、ローカルにファイルとして保存する Agent Skill を提供する。

設計の中心方針は次の2点。

1. **モデル（Claude）に API を手書きさせない。** 画像生成ロジックは自己完結したスクリプトに閉じ込め、Claude は SKILL.md に書かれた手順どおりにスクリプトを呼び出すだけにする。
2. **パラメータは CLI 引数 + 妥当なデフォルト値で渡す。** `size` / `quality` / `output_format` / `background` などは検証付きの名前付き引数として公開し、指定がなければ推奨デフォルトを使う。

---

## 2. スコープ

> 注（2026-06-23 更新）: 本書は初版（生成のみ）の要件メモ。実装はその後、画像編集（images/edits）と `.env`／環境変数による既定値解決を追加した。最新の正式要件は `.kiro/specs/gpt-image-2-skill/requirements.md`（Requirement 9〜12 ほか）を参照のこと。

含むもの:

- テキストプロンプトからの画像生成（images/generations）
- 画像編集（images/edits）: 単一画像のプロンプト編集、複数画像のマージ（オブジェクト置換）、`mask` によるインペインティング
- `size`・`quality`・`output_format`・`background`・`output_compression`・`n` のパラメータ制御
- 生成・編集画像のローカル保存（Base64 デコード）
- `.env`／環境変数（`GPT_IMAGE_*`）による既定値解決（優先順位: CLI 引数 > `.env` > 組み込み既定）
- 認証情報の安全な受け渡し

含まないもの（将来拡張）:

- ストリーミング（`stream` / `partial_images`）
- バッチ・キュー処理、Web UI

---

## 3. 前提条件

- Azure サブスクリプションと Azure OpenAI（Foundry）リソースが作成済みであること。
- `gpt-image-2` モデルがデプロイ済みであること。gpt-image 系モデルは **限定アクセス登録**（limited access）が必要。
- 利用する API バージョンは `2025-04-01-preview` 以降（gpt-image-2 / 任意解像度 / ストリーミング対応版）。
- ローカルに Python 3.10+ と `requests`（または `openai` SDK）、`azure-identity`（Entra ID 認証時）が利用可能であること。

### エンドポイント

```
POST https://<resource-name>.openai.azure.com/openai/deployments/<deployment-name>/images/generations?api-version=2025-04-01-preview
```

- `<deployment-name>` は gpt-image-2 をデプロイしたときに付けたデプロイ名。
- リクエストボディは JSON（`Content-Type: application/json`）。

---

## 4. 機能要件

### 4.1 スキルの起動条件

SKILL.md の `description` に、「画像生成」「画像を作る」「gpt-image」「Azure で画像生成」などのトリガー語を含め、関連する依頼で Claude が自動的にこのスキルを読み込めるようにする。

### 4.2 スクリプトインターフェース（パラメータの推奨渡し方）

画像生成は `scripts/generate_image.py` に実装し、**パラメータはすべて名前付き CLI 引数として公開する**。Claude は差分だけを指定すればよく、未指定の引数はスクリプト側の推奨デフォルトが適用される。

```bash
python scripts/generate_image.py \
  --prompt "夕暮れの東京タワー、水彩画風" \
  --size 1024x1024 \
  --quality high \
  --format png \
  --background auto \
  --n 1 \
  --output ./out
```

設計ルール:

- **必須引数は `--prompt` のみ。** その他はすべて任意で、デフォルトを持つ。
- **値の検証はスクリプト内で行う**（不正な値は API に投げる前にエラーにする）。下表の制約を実装する。
- **認証情報は CLI 引数で渡さない。** 環境変数経由でのみ取得する（§5.1）。
- 終了コードでエラーを通知し、`stderr` に原因を出力する（API キー等は出力しない）。

### 4.3 パラメータ仕様（gpt-image-2）

| 引数 | API パラメータ | 取り得る値 | デフォルト | 備考 |
|------|----------------|------------|------------|------|
| `--prompt` | `prompt` | 任意のテキスト | （必須） | 生成内容の指示 |
| `--size` | `size` | 任意解像度（制約は下記） | `1024x1024` | プリセット推奨: `1024x1024`（正方・最速）, `1536x1024`（横長）, `1024x1536`（縦長） |
| `--quality` | `quality` | `low` / `medium` / `high` | `high` | `low` は低遅延用途向け |
| `--format` | `output_format` | `png` / `jpeg` | `png` | **WEBP は Azure では非対応** |
| `--background` | `background` | `auto` / `transparent` | `auto` | `transparent` は `output_format=png` が必須 |
| `--compression` | `output_compression` | `0`–`100` | `100` | **JPEG 出力時のみ有効** |
| `--n` | `n` | `1`–`10` | `1` | 1リクエストで生成する枚数 |
| `--user` | `user` | 任意文字列 | （任意） | 利用状況トラッキング用 ID |
| `--output` | （ローカル） | ディレクトリパス | `./` | 保存先 |

#### gpt-image-2 の `size` 制約（任意解像度）

`gpt-image-2` は固定サイズではなく任意解像度をサポートする。`--size` は以下をすべて満たす必要があり、満たさない場合はスクリプトでエラーにする。

- 両辺がそれぞれ **16px の倍数**であること。
- 長辺が **3840px 以下**（4K まで）。
- アスペクト比が **3:1 以下**。
- 総ピクセル数が **655,360 〜 8,294,400** の範囲内。

#### パラメータ依存関係の検証ルール

- `--background transparent` を指定したら `--format` は `png` でなければならない（`jpeg` ならエラー）。
- `--compression` は `--format jpeg` のときのみ有効。`png` 指定時は警告して無視する。

### 4.4 出力

- API レスポンスの `data[].b64_json`（Base64 文字列）をデコードして画像ファイルとして保存する。
- ファイル名は `gpt-image-2_<timestamp>_<index>.<ext>` のように一意にする。
- 複数枚（`--n > 1`）の場合は連番で保存する。
- 保存したファイルの絶対パスを `stdout` に出力し、Claude がユーザーに提示できるようにする。

---

## 5. 非機能要件

### 5.1 セキュリティ（認証・シークレット）

認証方式は次の優先順で実装する。

1. **推奨: Microsoft Entra ID 認証（キーレス）。** `azure-identity` の `DefaultAzureCredential` を使い、ローカルでは `az login`、クラウドでは Managed Identity からトークンを取得する。長期間有効なキーを保存しない。
2. **代替: API キー認証。** キーは環境変数 `AZURE_OPENAI_API_KEY` から読み取り、リクエストヘッダ `api-key` に設定する。

必須ルール:

- エンドポイント・デプロイ名・キーは **環境変数**（`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_API_KEY`）から取得する。
- **SKILL.md やスクリプト本体に値を直書きしない**（モデルのコンテキストに載るため）。
- API キーを使う場合は **Azure Key Vault** に保管し、定期ローテーションする。
- キーやトークンを `stdout` / `stderr` / ログに出力しない。

### 5.2 エラーハンドリング

- HTTP エラー（401/403/429/400 等）を区別し、原因を分かりやすく `stderr` に出す。
- コンテンツモデレーションによる拒否（プロンプトが有害判定）は、その旨をユーザーに伝えられるメッセージにする。
- `429`（レート制限）時は指数バックオフでリトライ（上限付き）。

### 5.3 パフォーマンス

- 生成は概ね 10〜30 秒。タイムアウトは余裕を持って設定する（例: 120 秒）。

---

## 6. ファイル構成

```
.claude/skills/gpt-image-2/
├── SKILL.md              # 起動条件・使い方・コマンド例
├── scripts/
│   └── generate_image.py # 画像生成本体（CLI 引数 + 検証 + 保存）
└── references/
    └── parameters.md     # パラメータ詳細リファレンス（任意）
```

### SKILL.md に含めるべき内容

- frontmatter の `name` と `description`（トリガー語を含める）。
- 前提（環境変数・デプロイ名・limited access）。
- パラメータの説明と推奨デフォルト（§4.3 の要約）。
- 代表的な呼び出しコマンド例（正方形 / 透過 PNG / JPEG 圧縮など）。
- 認証情報は環境変数から読む旨の明記（値は書かない）。

---

## 7. 受け入れ基準

- [ ] `--prompt` のみの指定で、デフォルト（1024x1024 / high / png / auto）で画像が生成・保存される。
- [ ] `--size` に制約違反の値（16の倍数でない、4K超、比率超過、ピクセル数範囲外）を渡すと API 呼び出し前にエラーになる。
- [ ] `--background transparent --format jpeg` の組み合わせがエラーになる。
- [ ] `--n 3` で3枚が連番で保存される。
- [ ] 環境変数未設定時に、キーを出力せず分かりやすいエラーを返す。
- [ ] Entra ID（`az login` 済み）と API キーの両方の認証経路で生成できる。
- [ ] SKILL.md・スクリプトに API キーやエンドポイントが直書きされていない。

---

## 8. 参考

- Azure AI Foundry 画像生成 how-to（generations / edits、API オプション、size・quality・output_format・background・output_compression の仕様）: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/dall-e
- gpt-image 系モデルの limited access 登録: https://aka.ms/oai/access
- API キーの安全な取り扱い（Key Vault）: https://learn.microsoft.com/en-us/azure/key-vault/general/apps-api-keys-secrets

> 注: 公式ドキュメントのコード例コメントには `background` / `output_format` を「GPT-image-1 only」と記す箇所と、「GPT-image-1 と gpt-image-2 の両方がサポート」と記す本文があり、表記に揺れがある。実装時は使用する `api-version` で実際の挙動を必ず検証すること。