---
name: gpt-image
description: >-
  Azure (Microsoft Foundry) の gpt-image-2 と gpt-image-2.5 系（Flare / Sunburst）でテキストから画像を生成・編集し、ローカルに保存します。
  「画像を生成して」「画像を作って」「gpt-image で画像生成」「Azure で画像生成」「イラスト/ロゴ/背景画像を作成」
  に加え、「画像を編集して」「この画像を修正して」「アップロードした画像を加工」「2枚の画像を合成/マージして」
  「この画像のオブジェクトを別画像のものに置き換えて」といった依頼で使用します。
  透過 PNG・JPEG 圧縮・任意解像度・複数枚生成・画像編集（単一/複数画像マージ・マスク）に対応。
  2.5 系では高画質（xhigh/max）・不透明背景も使えます。
---

# gpt-image 画像生成・編集スキル

Azure AI Foundry にデプロイした `gpt-image-2`、`gpt-image-2.5-flare`、`gpt-image-2.5-sunburst` を呼び出し、テキストプロンプトからの画像生成と、既存画像の編集（単一画像の修正・複数画像のマージ）を行ってローカルに保存します。
API 呼び出し・検証・保存はすべて `scripts/` 配下のスクリプトに閉じ込められています。**API を手書きせず、必ずこれらのスクリプトを呼び出してください。**

- 画像生成（テキスト→画像）: `scripts/generate_image.py`
- 画像編集（画像＋プロンプト→画像）: `scripts/edit_image.py`

## 前提条件

1. Azure OpenAI（Foundry）リソースに、使うモデル（`gpt-image-2` / `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst`）がデプロイ済みであること。
2. 以下の環境変数が設定されていること（**値はここに書かず、必ず環境変数または `.env` で渡す**）:
   - `AZURE_OPENAI_ENDPOINT` … 例: `https://<resource>.openai.azure.com`（必須）
   - デプロイ名（必須。どちらか一方）:
     - モデル種別ごとのデプロイ名 … `AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2` / `AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_FLARE` / `AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_SUNBURST`
     - 共通のデプロイ名 … `AZURE_OPENAI_DEPLOYMENT`（モデル種別ごとの変数が無いときに使われる）
   - `GPT_IMAGE_MODEL` … 既定のモデル種別（任意。既定 `gpt-image-2`）
   - `AZURE_OPENAI_API_KEY` … API キー認証を使う場合のみ（任意）
   - `AZURE_OPENAI_API_VERSION` … 既定 `2025-04-01-preview`（任意）
   - `AZURE_OPENAI_API_STYLE` … エンドポイント形式 `deployments`（既定）/ `v1`（任意）
   - `AZURE_OPENAI_TOKEN_SCOPE` … Entra ID のトークンスコープ（任意。既定 `https://cognitiveservices.azure.com/.default`）
3. **`.env` 対応**: 次の 2 か所の `.env` が自動で読み込まれます。`.env.example` をコピーして使ってください。
   - プロジェクトの `.env`（カレントディレクトリから上位へ探索し、最初に見つかったもの）
   - スキルフォルダの `.env`（この `SKILL.md` と同じフォルダ。グローバルインストール時に、どのプロジェクトからでも使える共通設定を置く場所）

   優先順位は **OS 環境変数 > プロジェクトの `.env` > スキルフォルダの `.env`** です。どれも未設定の値だけを補完します。
4. 認証は **Entra ID（キーレス）を優先**します。`az login` 済みなら自動でトークンを使用し、未構成なら `AZURE_OPENAI_API_KEY` にフォールバックします。
5. Python 3.10+ と依存ライブラリ（`pip install -r requirements.txt`：`requests`, `azure-identity`）。

## モデルの選び方

| モデル種別（`--model`） | 特徴 | 向いている依頼 |
|------|------|------|
| `gpt-image-2.5-flare` | 速い（gpt-image-2 より約 50% 低レイテンシ）・高品質 | 試作・ラフ案・大量生成・日常的な画像 |
| `gpt-image-2.5-sunburst` | 最も精密（遅い） | 最終成果物、細部・文字・商品の形を崩したくない編集、長い編集の繰り返し |
| `gpt-image-2` | 従来のモデル（既定） | 2.5 系をデプロイしていない環境 |

- 利用者がモデルを指定しなければ、`--model` は付けずに既定（`GPT_IMAGE_MODEL`、未設定なら `gpt-image-2`）に任せる。
- 「まず案を出して、気に入ったものを仕上げる」依頼では、Flare で試作し、採用案を Sunburst で編集・仕上げる。
- `--model` で指定したモデル種別と、呼び出し先のデプロイ（上記の環境変数）は一致させること。一致していないと API が 400 を返す。

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
| `--model` | `GPT_IMAGE_MODEL` | `gpt-image-2` / `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst` | `gpt-image-2` | 「モデルの選び方」を参照 |
| `--quality` | `GPT_IMAGE_QUALITY` | `low` / `medium` / `high`（2.5 系は + `xhigh` / `max` / `auto`） | `high` | `low` は低遅延向け。下の注意を参照 |
| `--format` | `GPT_IMAGE_FORMAT` | `png` / `jpeg` | `png` | WEBP は Azure では現在使えない |
| `--background` | `GPT_IMAGE_BACKGROUND` | `auto` / `transparent`（2.5 系は + `opaque`） | `auto` | `transparent` は `--format png` 必須 |
| `--compression` | `GPT_IMAGE_COMPRESSION` | `0`–`100` | `100` | JPEG 出力時のみ有効 |
| `--complexity` | `GPT_IMAGE_COMPLEXITY` | `low` / `medium` / `high` | （未指定） | **現在 Azure では使えない（指定するとエラー）。指定しないこと** |
| `--n` | `GPT_IMAGE_N` | `1`–`10` | `1` | 生成枚数 |
| `--user` | `GPT_IMAGE_USER` | 任意文字列 | （任意） | 利用状況トラッキング用 ID |
| `--output` | `GPT_IMAGE_OUTPUT_DIR` | ディレクトリパス | `./images` | 保存先（無ければ作成） |

### 2.5 系の注意

- **quality**: 2.5 系の `high` は、gpt-image-2 の `high` より消費トークンが少ない（gpt-image-2 の `medium` 程度）。品質名が同じでも重さは違う。`xhigh` は約 2 倍、`max` は約 4 倍のトークンと時間がかかるため、`max` は利用者が明示的に最高品質を求めたときだけ使う。
- **experimental な解像度**: 2.5 系では総ピクセル数が 2560x1440 を超える解像度は experimental（警告を出して続行する）。
- **処理時間**: 2.5 系は最大 2 分程度かかることがある（タイムアウトは 300 秒）。

### `--size` の制約（全モデル共通）

次をすべて満たす必要があります（違反は API 呼び出し前にエラー）:
- 両辺がそれぞれ **16px の倍数**
- 長辺が **3840px 以下**
- アスペクト比が **3:1 以下**（縦長は 1:3 以上）
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

2.5 系で試作（Flare）→ 仕上げ（Sunburst）:
```bash
python scripts/generate_image.py --prompt "新商品のポスター案" --model gpt-image-2.5-flare --quality medium --n 4
python scripts/edit_image.py --prompt "文字を鮮明にし、商品のロゴを正確に保つ" --image ./images/<採用案>.png --model gpt-image-2.5-sunburst --quality xhigh
```

不透明背景（2.5 系）:
```bash
python scripts/generate_image.py --prompt "白背景の商品写真" --model gpt-image-2.5-flare --background opaque
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
| `--markup` | （なし） | 透過 PNG パス | （任意） | **現在 Azure では使えない（指定するとエラー）。編集箇所の限定には `--mask` を使う** |
| `--model` / `--complexity` | `GPT_IMAGE_MODEL` / `GPT_IMAGE_COMPLEXITY` | 生成と同じ | 生成と同じ | `--complexity` は現在使えない |
| `--size` | `GPT_IMAGE_EDIT_SIZE` | `WxH` または `auto` | `auto` | `auto` は入力画像に合わせる。`WxH` 指定時は生成と同じ制約 |
| `--quality` | `GPT_IMAGE_QUALITY` | 生成と同じ（モデル種別で変わる） | `high` | |
| `--format` | `GPT_IMAGE_FORMAT` | `png` / `jpeg` | `png` | |
| `--background` | `GPT_IMAGE_BACKGROUND` | 生成と同じ（モデル種別で変わる） | `auto` | `transparent` は `--format png` 必須 |
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

### 使える機能（Azure での動作確認状況）

| 機能 | 状態 |
|------|------|
2026-11-07 に Azure の実機（Sweden Central、Flare）で確認した結果です。

| 機能 | 状態 |
|------|------|
| 2.5 系の `quality`（xhigh / max / auto）・`background=opaque` | 使える（実機で確認済み） |
| `--complexity`・`--markup` | 使えない（Azure が `Unknown parameter` で拒否する。スクリプトも API 呼び出し前にエラーにする） |
| `background=transparent`（2.5 系） | 未確認（レート制限で判定できなかった。指定はできるが、失敗したら `auto` / `opaque` に切り替える） |
| WebP 出力 | 使えない（実機で確認できるまで無効） |
