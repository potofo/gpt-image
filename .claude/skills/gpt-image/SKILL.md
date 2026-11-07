---
name: gpt-image
description: >-
  Azure (Microsoft Foundry) の gpt-image-2 モデルでテキストから画像を生成・編集し、ローカルに保存します。
  「画像を生成して」「画像を作って」「gpt-image で画像生成」「Azure で画像生成」「イラスト/ロゴ/背景画像を作成」
  に加え、「画像を編集して」「この画像を修正して」「アップロードした画像を加工」「2枚の画像を合成/マージして」
  「この画像のオブジェクトを別画像のものに置き換えて」といった依頼で使用します。
  透過 PNG・JPEG 圧縮・任意解像度・複数枚生成・画像編集（単一/複数画像マージ・マスク）に対応。
---

# gpt-image-2 画像生成・編集スキル

Azure AI Foundry にデプロイした `gpt-image-2` を呼び出し、テキストプロンプトからの画像生成と、既存画像の編集（単一画像の修正・複数画像のマージ）を行ってローカルに保存します。
API 呼び出し・検証・保存はすべて `scripts/` 配下のスクリプトに閉じ込められています。**API を手書きせず、必ずこれらのスクリプトを呼び出してください。**

- 画像生成（テキスト→画像）: `scripts/generate_image.py`
- 画像編集（画像＋プロンプト→画像）: `scripts/edit_image.py`

## 前提条件

1. Azure OpenAI（Foundry）リソースに `gpt-image-2` がデプロイ済みであること（gpt-image 系は [limited access 登録](https://aka.ms/oai/access)が必要）。
2. 以下の環境変数が設定されていること（**値はここに書かず、必ず環境変数または `.env` で渡す**）:
   - `AZURE_OPENAI_ENDPOINT` … 例: `https://<resource>.openai.azure.com`（必須）
   - `AZURE_OPENAI_DEPLOYMENT` … gpt-image-2 のデプロイ名（必須）
   - `AZURE_OPENAI_API_KEY` … API キー認証を使う場合のみ（任意）
   - `AZURE_OPENAI_API_VERSION` … 既定 `2025-04-01-preview`（任意）
3. **`.env` 対応**: プロジェクトフォルダ直下に `.env` を置くと自動で読み込まれます（カレントディレクトリから上位へ探索）。`.env.example` をコピーして使ってください。**OS 環境変数が優先**され、`.env` は未設定分のみ補完します。
4. 認証は **Entra ID（キーレス）を優先**します。`az login` 済みなら自動でトークンを使用し、未構成なら `AZURE_OPENAI_API_KEY` にフォールバックします。
5. Python 3.10+ と依存ライブラリ（`pip install -r requirements.txt`：`requests`, `azure-identity`）。

## 使い方

必須引数は `--prompt` のみ。その他は省略可で、推奨デフォルトが適用されます。差分だけ指定してください。

```bash
python scripts/generate_image.py --prompt "夕暮れの東京タワー、水彩画風"
```

成功すると、保存したファイルの絶対パスが標準出力に1行ずつ表示されます。これをユーザーに提示してください。

**保存先とファイル名**:
- `--output` 未指定時は、カレントディレクトリ直下の `./images` フォルダに保存します（無ければ自動作成）。
- ファイル名はプロンプトから導出したタイトルを使い、`<タイトル>_<タイムスタンプ>_<連番>.<拡張子>` 形式で一意になります（例: `夕暮れの東京タワー、水彩画風_20260620T055249_0.png`）。

## パラメータ

**デフォルト値の優先順位**: `CLI 引数 > .env（環境変数） > 組み込み既定`。よく使う設定は `.env` に下表の環境変数で書いておけば、毎回 CLI で渡す必要がありません。

| 引数 | 環境変数 | 取り得る値 | 既定 | 備考 |
|------|----------|------------|------|------|
| `--prompt` | （なし） | 任意のテキスト | （必須） | 生成内容の指示 |
| `--size` | `GPT_IMAGE_SIZE` | `WxH`（任意解像度） | `1024x1024` | 推奨: `1024x1024`（正方・最速）, `1536x1024`（横長）, `1024x1536`（縦長） |
| `--quality` | `GPT_IMAGE_QUALITY` | `low` / `medium` / `high` | `high` | `low` は低遅延向け |
| `--format` | `GPT_IMAGE_FORMAT` | `png` / `jpeg` | `png` | WEBP は Azure 非対応 |
| `--background` | `GPT_IMAGE_BACKGROUND` | `auto` / `transparent` | `auto` | `transparent` は `--format png` 必須 |
| `--compression` | `GPT_IMAGE_COMPRESSION` | `0`–`100` | `100` | JPEG 出力時のみ有効 |
| `--n` | `GPT_IMAGE_N` | `1`–`10` | `1` | 生成枚数 |
| `--user` | `GPT_IMAGE_USER` | 任意文字列 | （任意） | 利用状況トラッキング用 ID |
| `--output` | `GPT_IMAGE_OUTPUT_DIR` | ディレクトリパス | `./images` | 保存先（無ければ作成） |

### `--size` の制約（gpt-image-2）

次をすべて満たす必要があります（違反は API 呼び出し前にエラー）:
- 両辺がそれぞれ **16px の倍数**
- 長辺が **3840px 以下**
- アスペクト比が **3:1 以下**
- 総ピクセル数が **655,360〜8,294,400**

## コマンド例

正方形・デフォルト:
```bash
python scripts/generate_image.py --prompt "桜並木の通学路、アニメ風"
```

透過 PNG（ロゴ・アイコン向け）:
```bash
python scripts/generate_image.py --prompt "ミニマルな山のロゴ" --background transparent --format png
```

JPEG 圧縮・横長:
```bash
python scripts/generate_image.py --prompt "海岸沿いの道路、写真風" --size 1536x1024 --format jpeg --compression 80
```

複数枚・保存先指定:
```bash
python scripts/generate_image.py --prompt "猫のキャラクター案" --n 4 --output ./out
```

## 画像編集（単一画像の修正・複数画像のマージ）

既存画像をプロンプトで修正します。`scripts/edit_image.py` を使い、`/images/edits` エンドポイント（multipart）を呼び出します。生成と同じ認証・保存・検証の仕組みを共有します。

必須引数は `--prompt` と **最低 1 枚の `--image`**。`--image` を複数指定すると画像のマージ（合成）になります。

```bash
python scripts/edit_image.py --prompt "<編集指示>" --image <入力画像パス> [--image <追加画像> ...] [--mask <透過PNG>]
```

成功すると、編集後の画像の絶対パスが標準出力に表示されます（生成と同じ命名規則・保存先）。

### 2つのモード

1. **単一画像の編集**: `--image` を 1 枚だけ渡し、プロンプトで修正内容を指示します（例: 色変更・オブジェクト追加/削除・スタイル変更）。
2. **複数画像のマージ（オブジェクト置換）**: `--image` を複数渡します。**先頭がベース画像**、2枚目以降が参照素材です。ベース画像の一部のオブジェクトを、別画像のオブジェクトに置き換えられます。プロンプトで「どのオブジェクトを何に置き換えるか」を明確に書いてください。置換領域をピンポイントで限定したい場合は、ベース画像と同サイズの**透過 PNG マスク**を `--mask` で渡します（**透過部分のみが編集対象**になります）。

### 画像編集のパラメータ

| 引数 | 環境変数 | 取り得る値 | 既定 | 備考 |
|------|----------|------------|------|------|
| `--prompt` | （なし） | 任意のテキスト | （必須） | 編集内容の指示 |
| `--image` | （なし） | 画像パス（複数可） | （必須・1枚以上） | 入力画像。複数でマージ。先頭がベース。`png`/`jpg`/`jpeg`/`webp`、最大 16 枚 |
| `--mask` | （なし） | 透過 PNG パス | （任意） | 編集領域を示すマスク（透過部分のみ編集）。PNG 必須 |
| `--size` | `GPT_IMAGE_EDIT_SIZE` | `WxH` または `auto` | `auto` | `auto` は入力画像に合わせる。`WxH` 指定時は生成と同じ制約 |
| `--quality` | `GPT_IMAGE_QUALITY` | `low` / `medium` / `high` | `high` | |
| `--format` | `GPT_IMAGE_FORMAT` | `png` / `jpeg` | `png` | |
| `--background` | `GPT_IMAGE_BACKGROUND` | `auto` / `transparent` | `auto` | `transparent` は `--format png` 必須 |
| `--compression` | `GPT_IMAGE_COMPRESSION` | `0`–`100` | `100` | JPEG 出力時のみ有効 |
| `--n` | `GPT_IMAGE_N` | `1`–`10` | `1` | 生成枚数 |
| `--user` | `GPT_IMAGE_USER` | 任意文字列 | （任意） | トラッキング用 ID |
| `--output` | `GPT_IMAGE_OUTPUT_DIR` | ディレクトリパス | `./images` | 保存先 |

### 画像編集のコマンド例

単一画像の編集（プロンプトで修正）:
```bash
python scripts/edit_image.py --prompt "空を夕焼けに変える" --image ./images/landscape.png
```

マスクで領域を限定して編集（インペインティング）:
```bash
python scripts/edit_image.py --prompt "帽子を赤いベレー帽に置き換える" --image ./photo.png --mask ./hat_mask.png
```

複数画像のマージ（ベース画像のオブジェクトを別画像のオブジェクトに置換）:
```bash
python scripts/edit_image.py \
  --prompt "ベース画像の人物が持つカバンを、2枚目の画像の赤いリュックに置き換える" \
  --image ./base.png \
  --image ./red_backpack.png \
  --mask ./bag_region.png
```

透過 PNG で出力（合成結果を切り抜き素材に）:
```bash
python scripts/edit_image.py --prompt "背景を透過にしたロゴ" --image ./logo.png --background transparent --format png
```

## 注意事項

- **認証情報・エンドポイント値をプロンプトやコマンドに直書きしないでください。** すべて環境変数から読み取られます。
- エラー時は終了コードが非ゼロになり、原因が標準エラー出力に表示されます（キー・トークンは出力されません）。
- コンテンツモデレーションで拒否された場合は、その旨のメッセージが表示されます。プロンプトを見直してください。
- `--background` / `--compression` の挙動は使用する `api-version` に依存する場合があります。想定どおりに動かない場合は `AZURE_OPENAI_API_VERSION` を確認してください。
