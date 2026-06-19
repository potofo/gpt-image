# gpt-image-2 画像生成スキル

*他の言語で読む: [English](./README.md)*

Azure AI Foundry（Microsoft Foundry）の `gpt-image-2` モデルを使い、テキストプロンプトから画像を生成してローカルに保存する [Claude Code](https://claude.com/claude-code) **Agent Skill** です。

このスキルは次の2つの方針に従います。

1. **Claude に API を手書きさせない。** 生成ロジック（リクエスト組み立て・検証・保存）はすべて自己完結した Python スクリプトに閉じ込め、Claude は `SKILL.md` の手順どおりにスクリプトを呼び出すだけです。
2. **パラメータは検証付きの CLI 引数 + 妥当なデフォルトで渡す。** 必須は `--prompt` のみ。その他はデフォルトにフォールバックし、そのデフォルトは `.env` で自由にカスタマイズできます。

---

## 特長

- Azure OpenAI `images/generations` によるテキスト→画像生成
- 全パラメータ制御: `size` / `quality` / `output_format` / `background` / `output_compression` / `n` / `user`
- API 呼び出し前の事前検証（size 制約・パラメータ依存関係）
- キーレスの **Microsoft Entra ID** 認証（優先）と **API キー** フォールバック
- 認証情報**および**デフォルトパラメータの `.env` 対応
- 既定で `./images` に、プロンプト由来の一意なタイトルでファイル保存

---

## 前提条件

- Azure サブスクリプションと Azure OpenAI（Foundry）リソース。
- `gpt-image-2` モデルがデプロイ済みであること。gpt-image 系は[限定アクセス登録](https://aka.ms/oai/access)が必要です。
- API バージョン `2025-04-01-preview` 以降（`2024-02-01` 等の古い版は gpt-image-2 **非対応**）。
- Python 3.10+ と `requirements.txt` の依存ライブラリ（`requests`, `azure-identity`）。

---

## インストール

スキルは自己完結したディレクトリ（`SKILL.md`, `scripts/`, `requirements.txt`）です。**グローバル**（全プロジェクトで利用可能）または**プロジェクト単位**でインストールできます。

### グローバルインストール（推奨）

個人用の Claude Code スキルディレクトリ（`~/.claude/skills/`）にコピーします。ここに置いたスキルは、どのプロジェクトを開いていても、すべての Claude Code セッションで利用できます。

**macOS / Linux**

```bash
# このリポジトリのルートで実行
mkdir -p ~/.claude/skills
cp -r .claude/skills/gpt-image-2 ~/.claude/skills/

# Python 依存ライブラリのインストール
pip install -r ~/.claude/skills/gpt-image-2/requirements.txt
```

**Windows (PowerShell)**

```powershell
# このリポジトリのルートで実行
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item -Recurse -Force ".claude\skills\gpt-image-2" "$env:USERPROFILE\.claude\skills\"

# Python 依存ライブラリのインストール
pip install -r "$env:USERPROFILE\.claude\skills\gpt-image-2\requirements.txt"
```

コピー後、スキルは次の場所に配置されます。

- macOS / Linux: `~/.claude/skills/gpt-image-2/`
- Windows: `C:\Users\<ユーザー名>\.claude\skills\gpt-image-2\`

Claude Code を起動（再起動）し、`gpt-image-2` スキルが一覧に表示されることを確認してください。「画像を生成して」「〜の画像を作って」などの依頼で自動的に読み込まれます。

### プロジェクト単位のインストール

このリポジトリのように、プロジェクトの `.claude/skills/gpt-image-2/` に置いたままにします。その場合は当該プロジェクト内でのみ利用可能です。依存ライブラリは同様にインストールします。

```bash
pip install -r .claude/skills/gpt-image-2/requirements.txt
```

---

## `.env` による設定

認証情報とデフォルトパラメータは**環境変数**から読み込まれます。手動で変数を export しなくて済むよう、スキルは `.env` ファイルからも読み込めます。

### 1. テンプレートから `.env` を作成

```bash
# プロジェクトルートで実行
cp .env.example .env      # macOS / Linux
# Copy-Item .env.example .env   # Windows PowerShell
```

作成後、`.env` を編集して Azure の値を入力します。

> **セキュリティ:** `.env` は秘密情報を含みます。コミット・共有しないでください。本リポジトリの `.gitignore` は `.env` を除外済みです（`.env.example` は追跡対象として保持）。

### 2. `.env` の探索と適用の仕組み

- スキル実行時、**カレントディレクトリから上位へ**ディレクトリツリーを辿って `.env` を探索し、最初に見つかったものを使用します。`.env` はプロジェクトルートに置いてください。
- **OS 環境変数が常に優先**されます。`.env` は、シェルに未設定の変数のみを補完します。
- 探索はスキルの設置場所ではなく「実行した場所」を基準にするため、**グローバルインストール**したスキルでは次のいずれかを推奨します。
  - 使用する各プロジェクトに `.env` を置く、または
  - OS レベルの環境変数として設定する、または
  - 対象プロジェクト群を包含する親ディレクトリに `.env` を1つ置く。

### 3. Azure 接続用の変数

| 変数 | 必須 | 説明 |
|------|------|------|
| `AZURE_OPENAI_ENDPOINT` | ✅ | リソースのベース URL。例: `https://<resource>.openai.azure.com`（デプロイ名やパスは含めない） |
| `AZURE_OPENAI_DEPLOYMENT` | ✅ | `gpt-image-2` に付けたデプロイ名 |
| `AZURE_OPENAI_API_KEY` | — | API キー認証時のみ。未設定ならキーレス（Entra ID）認証を使用 |
| `AZURE_OPENAI_API_VERSION` | — | 既定 `2025-04-01-preview` |

### 4. `.env` でのデフォルトパラメータ設定（重要機能）

すべての生成パラメータについて、**好みのデフォルト値**を `.env` に設定できます。つまり、よく使う size / quality / format などを一度設定しておけば、毎回フラグを付けずに「〜の画像を作って」と頼むだけで済みます。

**優先順位: CLI 引数 > `.env`（環境変数） > 組み込み既定。**

| パラメータ | 環境変数 | 組み込み既定 | 取り得る値 |
|------------|----------|--------------|------------|
| size | `GPT_IMAGE_SIZE` | `1024x1024` | `WxH`（後述の size 制約参照） |
| quality | `GPT_IMAGE_QUALITY` | `high` | `low` / `medium` / `high` |
| 出力形式 | `GPT_IMAGE_FORMAT` | `png` | `png` / `jpeg`（WEBP 非対応） |
| 背景 | `GPT_IMAGE_BACKGROUND` | `auto` | `auto` / `transparent`（transparent は `png` 必須） |
| 圧縮 | `GPT_IMAGE_COMPRESSION` | `100` | `0`–`100`（JPEG のみ） |
| 枚数 | `GPT_IMAGE_N` | `1` | `1`–`10` |
| 出力先 | `GPT_IMAGE_OUTPUT_DIR` | `./images` | 任意のディレクトリパス（無ければ作成） |
| ユーザー ID | `GPT_IMAGE_USER` | （なし） | 任意の文字列 |

`.env` のデフォルト設定例:

```dotenv
# 常に横長・高画質 PNG を ./assets に出力する
GPT_IMAGE_SIZE=1536x1024
GPT_IMAGE_QUALITY=high
GPT_IMAGE_FORMAT=png
GPT_IMAGE_OUTPUT_DIR=./assets
```

上記の設定では、`python scripts/generate_image.py --prompt "狐"` だけで 1536×1024 の高画質 PNG が `./assets` に生成されます（追加フラグ不要）。なお、その実行で `--size 1024x1024` を渡せば、`.env` の値より CLI が優先されます。

注釈付きの完全なテンプレートは [`.env.example`](./.env.example) を参照してください。

---

## 使い方

### Claude Code から

自然言語で依頼するだけです。例:「Azure で水彩画風の富士山の画像を作って」。Claude がスキルを読み込んでスクリプトを実行し、保存先のパスを報告します。

### CLI から直接

```bash
python scripts/generate_image.py --prompt "静かな日本庭園、水彩画風"
```

成功すると、保存した各ファイルの絶対パスが標準出力に1行ずつ表示されます。

#### 例

```bash
# 既定の正方形 PNG を ./images に
python scripts/generate_image.py --prompt "桜並木の通学路、アニメ風"

# 透過 PNG（ロゴ・アイコン向け）
python scripts/generate_image.py --prompt "ミニマルな山のロゴ" --background transparent --format png

# 圧縮 JPEG・横長
python scripts/generate_image.py --prompt "海岸沿いの道路、写真風" --size 1536x1024 --format jpeg --compression 80

# 複数枚を任意フォルダへ
python scripts/generate_image.py --prompt "猫のキャラクター案" --n 4 --output ./out
```

### パラメータ

| 引数 | 環境変数 | 取り得る値 | 既定 | 備考 |
|------|----------|------------|------|------|
| `--prompt` | （なし） | 任意のテキスト | **必須** | 生成内容の指示 |
| `--size` | `GPT_IMAGE_SIZE` | `WxH` | `1024x1024` | 推奨: `1024x1024`, `1536x1024`, `1024x1536` |
| `--quality` | `GPT_IMAGE_QUALITY` | `low`/`medium`/`high` | `high` | `low` は低遅延向け |
| `--format` | `GPT_IMAGE_FORMAT` | `png`/`jpeg` | `png` | WEBP は Azure 非対応 |
| `--background` | `GPT_IMAGE_BACKGROUND` | `auto`/`transparent` | `auto` | `transparent` は `--format png` 必須 |
| `--compression` | `GPT_IMAGE_COMPRESSION` | `0`–`100` | `100` | JPEG のみ |
| `--n` | `GPT_IMAGE_N` | `1`–`10` | `1` | 生成枚数 |
| `--user` | `GPT_IMAGE_USER` | 任意の文字列 | （任意） | 利用状況トラッキング用 ID |
| `--output` | `GPT_IMAGE_OUTPUT_DIR` | ディレクトリパス | `./images` | 無ければ作成 |

### size 制約（gpt-image-2）

`--size` は次を**すべて**満たす必要があり、違反時は API 呼び出し前にエラーになります。

- 両辺がそれぞれ **16px の倍数**
- 長辺が **3840px 以下**
- アスペクト比が **3:1 以下**
- 総ピクセル数が **655,360 〜 8,294,400**

### 出力とファイル名

- 既定の出力先は `./images`（無ければ自動作成）。
- ファイル名は `<タイトル>_<タイムスタンプ>_<連番>.<拡張子>` 形式。`<タイトル>` はプロンプトから導出します（ファイル名に使えない文字を除去し、長さを制限）。複数枚（`--n > 1`）は連番で保存されます。

---

## 認証

1. **Microsoft Entra ID（キーレス・優先）。** `DefaultAzureCredential` を使用。ローカルでは `az login`、クラウドでは Managed Identity を利用します。長期間有効なキーを保存しません。
2. **API キー（フォールバック）。** Entra ID が使えず `AZURE_OPENAI_API_KEY` が設定されている場合、`api-key` ヘッダでキーを使用します。

シークレットは環境変数 / `.env` からのみ読み取り、`SKILL.md` やスクリプトに直書きせず、標準出力・標準エラー・ログにも一切出力しません。

---

## 開発

```bash
cd .claude/skills/gpt-image-2
python -m pytest -q
```

テストは、検証・認証解決・保存/命名・API クライアント（HTTP モック）・`.env` 読み込み・パラメータ既定値の優先順位・CLI オーケストレーションを網羅しています。

本プロジェクトは Kiro 流の仕様駆動開発で構築しました。仕様は `.kiro/specs/gpt-image-2-skill/` 以下にあります。

---

## ライセンス

[MIT License](./LICENSE) の下で提供されます。
