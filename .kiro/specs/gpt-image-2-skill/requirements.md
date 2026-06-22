# Requirements Document

## Introduction

本仕様は、Claude Code から Azure AI Foundry（Microsoft Foundry）の `gpt-image-2` モデルを呼び出して画像を生成・編集する Agent Skill の要件を定義する。スキルは「Claude に API を手書きさせない（生成・編集ロジックは自己完結したスクリプトに閉じ込める）」「パラメータは検証付きの名前付き CLI 引数 + 妥当なデフォルトで渡す」という2つの中心方針に従う。Claude は `SKILL.md` の手順どおりに `scripts/generate_image.py`（生成）または `scripts/edit_image.py`（編集）を呼び出し、結果画像をローカルに保存する。

本書では、対象システムを次のように表す。
- **画像生成スクリプト**: `scripts/generate_image.py`（生成 CLI 本体。検証・API 呼び出し・保存を担う）
- **画像編集スクリプト**: `scripts/edit_image.py`（編集 CLI 本体。入力画像の検証・`images/edits` 呼び出し・保存を担う）
- **画像生成・編集スキル**: `SKILL.md` を含むスキル全体（Claude の起動・実行経路を含む）

> 編集機能（Requirement 9〜12）と設定の優先順位／`.env` サポート（Requirement 2 の拡張・Requirement 6）は、初版（生成のみ）の後に追加された。本書はそれら実装済み機能を反映した最新版である（spec.json の updated_at を参照）。

## Boundary Context

- **In scope**:
  - **画像生成（`images/generations`）**: テキストプロンプトからの生成、`size`/`quality`/`output_format`/`background`/`output_compression`/`n`/`user` のパラメータ制御と検証。
  - **画像編集（`images/edits`）**: 既存画像をプロンプトで修正する単一画像編集、複数画像のマージ（ベース画像のオブジェクトを別画像のオブジェクトに置換）、`mask` によるインペインティング（編集領域の限定）。
  - **共通**: Base64 デコードによるローカル保存、Entra ID（キーレス）と API キーの両認証経路、エラーハンドリングとレート制限リトライ、`.env` ファイルおよびパラメータ既定値の環境変数（`GPT_IMAGE_*`）サポート、「CLI 引数 > `.env`（環境変数） > 組み込み既定」の優先順位。
- **Out of scope**（将来拡張）: ストリーミング（`stream`/`partial_images`）、バッチ／キュー処理、Web UI。
- **Adjacent expectations**: Azure サブスクリプションと Azure OpenAI（Foundry）リソースが作成済みで、`gpt-image-2` が limited access 登録の上デプロイ済みであること。API バージョンは `2025-04-01-preview` 以降。ローカルに Python 3.10+ と必要ライブラリ（`requests`、Entra ID 利用時は `azure-identity`）が利用可能であること。

## Requirements

### Requirement 1: スキルの起動とトリガー

**Objective:** Claude Code 利用者として、画像生成・編集に関する自然な依頼でこのスキルが自動的に読み込まれてほしい。それにより、ツール名を意識せず画像を生成・編集できる。

#### Acceptance Criteria

1. The 画像生成・編集スキル shall `SKILL.md` の frontmatter に `name` と、生成系トリガー語（「画像生成」「画像を作る」「gpt-image」「Azure で画像生成」など）に加え、編集系トリガー語（「画像を編集」「この画像を修正」「アップロードした画像を加工」「2枚の画像を合成/マージ」「オブジェクトを別画像のものに置き換え」など）を含む `description` を定義する。
2. When 利用者が画像生成に関連する依頼を行ったとき、the スキル shall このスキルを読み込み、`SKILL.md` の手順に従って画像生成スクリプト（`generate_image.py`）を呼び出す。
3. When 利用者が既存画像の編集・合成・置換に関連する依頼を行ったとき、the スキル shall このスキルを読み込み、`SKILL.md` の手順に従って画像編集スクリプト（`edit_image.py`）を呼び出す。
4. The スキル shall `SKILL.md` に前提条件（必要な環境変数・デプロイ名・limited access）、生成・編集双方のパラメータ要約と推奨デフォルト、代表的な呼び出しコマンド例を記載する。

### Requirement 2: CLI インターフェースとデフォルト値

**Objective:** Claude として、必要な差分だけを名前付き引数で指定したい。それにより、未指定の項目は推奨デフォルトが適用され、最小限の指示で画像を生成できる。

#### Acceptance Criteria

1. The 画像生成スクリプト shall `--prompt` を唯一の必須引数とし、`--size`/`--quality`/`--format`/`--background`/`--compression`/`--n`/`--user`/`--output` をすべて任意の名前付き引数として公開する。
2. When `--prompt` のみが指定されたとき、the 画像生成スクリプト shall デフォルト値（`size=1024x1024`、`quality=high`、`format=png`、`background=auto`、`n=1`、`output=./images`）で画像を生成・保存する。
3. If `--prompt` が指定されていないとき、then the 画像生成スクリプト shall API を呼び出さずにエラーを返し、非ゼロの終了コードで終了する。
4. The 画像生成スクリプト shall 認証情報を CLI 引数として受け取らない。
5. The 画像生成スクリプト shall 各任意引数の既定値を「CLI 引数 > 環境変数（`.env` 含む） > 組み込み既定」の優先順位で解決する。対応する環境変数は `GPT_IMAGE_SIZE` / `GPT_IMAGE_QUALITY` / `GPT_IMAGE_FORMAT` / `GPT_IMAGE_BACKGROUND` / `GPT_IMAGE_COMPRESSION` / `GPT_IMAGE_N` / `GPT_IMAGE_OUTPUT_DIR` / `GPT_IMAGE_USER`。

### Requirement 3: パラメータ値の検証（size 制約）

**Objective:** 利用者として、不正な `--size` 指定を API 呼び出し前に検出してほしい。それにより、無駄な API 呼び出しと不明瞭なエラーを避けられる。

#### Acceptance Criteria

1. If `--size` の両辺のいずれかが 16px の倍数でないとき、then the 画像生成スクリプト shall API を呼び出さずにエラーを返す。
2. If `--size` の長辺が 3840px を超えるとき、then the 画像生成スクリプト shall API を呼び出さずにエラーを返す。
3. If `--size` のアスペクト比が 3:1 を超えるとき、then the 画像生成スクリプト shall API を呼び出さずにエラーを返す。
4. If `--size` の総ピクセル数が 655,360 未満または 8,294,400 を超えるとき、then the 画像生成スクリプト shall API を呼び出さずにエラーを返す。
5. If `--quality` / `--format` / `--background` / `--n` に許容範囲外の値が指定されたとき、then the 画像生成スクリプト shall API を呼び出さずにエラーを返す。

### Requirement 4: パラメータ依存関係の検証

**Objective:** 利用者として、互いに矛盾するパラメータの組み合わせを事前に検出してほしい。それにより、Azure 側の制約に起因する失敗を未然に防げる。

#### Acceptance Criteria

1. If `--background transparent` が指定され、かつ `--format` が `png` でないとき、then the 画像生成スクリプト shall API を呼び出さずにエラーを返す。
2. When `--compression` が指定され、かつ `--format` が `png` のとき、the 画像生成スクリプト shall 警告を `stderr` に出力したうえで `--compression` を無視する。
3. Where `--compression` が指定され `--format` が `jpeg` のとき、the 画像生成スクリプト shall `output_compression` を API リクエストに反映する。
4. The 画像生成スクリプト shall `--compression` の値を 0〜100 の範囲に制限する。

### Requirement 5: 画像生成と出力保存

**Objective:** 利用者として、生成された画像がローカルに保存され、その場所を知りたい。それにより、Claude が結果のパスを提示できる。

#### Acceptance Criteria

1. When API レスポンスを受信したとき、the 画像生成スクリプト shall `data[].b64_json` を Base64 デコードして画像ファイルとして保存する。
2. The 画像生成スクリプト shall 保存ファイル名を `<title>_<timestamp>_<index>.<ext>` 形式で一意に生成する。ここで `<title>` はプロンプトから導出した安全なファイル名（ファイルシステム禁止文字を除去し空白をハイフン化、最大長で切り詰め、空になる場合は `image`）、`<timestamp>` はマイクロ秒精度（`%Y%m%dT%H%M%S%f`）とする。
3. When `--n` が 2 以上のとき、the 画像生成スクリプト shall 生成された各画像を同一 timestamp + 連番 index で保存する。
4. When 保存が完了したとき、the 画像生成スクリプト shall 保存したファイルの絶対パスを `stdout` に出力する。
5. If `--output` で指定されたディレクトリが存在しないとき、then the 画像生成スクリプト shall ディレクトリを作成するか、明確なエラーを返す。

### Requirement 6: 認証とシークレット管理

**Objective:** セキュリティ担当者として、認証情報がモデルのコンテキストやログに漏れない方式で扱われてほしい。それにより、長期キーの流出リスクを抑えられる。

#### Acceptance Criteria

1. The 画像生成スクリプト shall エンドポイント・デプロイ名・API キー・API バージョンを環境変数（`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_API_VERSION`）から取得する。`AZURE_OPENAI_API_VERSION` 未設定時は既定 `2025-04-01-preview` を用いる。
2. The スキル shall `SKILL.md` およびスクリプト本体に認証情報・エンドポイント値を直書きしない。
2.1. The スクリプト shall カレントディレクトリから上位へ `.env` ファイルを探索し、最初に見つかったものを読み込む。ただし OS 環境変数を優先し、`.env` は未設定の変数のみを補完する（既存の OS 環境変数を上書きしない）。
3. Where Entra ID 認証が利用可能なとき、the 画像生成スクリプト shall `DefaultAzureCredential` でトークンを取得するキーレス認証を優先する。
4. Where API キー認証を用いるとき、the 画像生成スクリプト shall `AZURE_OPENAI_API_KEY` を読み取りリクエストヘッダ `api-key` に設定する。
5. The 画像生成スクリプト shall API キー・アクセストークンを `stdout` / `stderr` / ログに出力しない。
6. If 必要な環境変数が未設定のとき、then the 画像生成スクリプト shall キー値を出力せずに分かりやすいエラーを返す。

### Requirement 7: エラーハンドリングとリトライ

**Objective:** 利用者として、失敗の原因が分かるメッセージを受け取りたい。それにより、設定ミスやモデレーション拒否に適切に対処できる。

#### Acceptance Criteria

1. If API が HTTP エラー（401 / 403 / 429 / 400 等）を返したとき、then the 画像生成スクリプト shall エラー種別を区別し、原因を `stderr` に出力する。
2. If プロンプトがコンテンツモデレーションで拒否されたとき、then the 画像生成スクリプト shall その旨を利用者に伝えられるメッセージを出力する。
3. When API が 429（レート制限）を返したとき、the 画像生成スクリプト shall 上限付きの指数バックオフでリトライする。
4. The 画像生成スクリプト shall エラー発生時に非ゼロの終了コードで終了する。

### Requirement 8: パフォーマンスとタイムアウト

**Objective:** 利用者として、生成に時間がかかっても途中で不当に打ち切られないでほしい。それにより、通常の生成（おおむね 10〜30 秒）が安定して完了する。

#### Acceptance Criteria

1. The 画像生成スクリプト shall API 呼び出しに余裕のあるタイムアウト（例: 120 秒）を設定する。
2. If タイムアウトに達したとき、then the 画像生成スクリプト shall 明確なエラーを返し、非ゼロの終了コードで終了する。
3. The 画像編集スクリプト shall 編集 API 呼び出しに余裕のあるタイムアウト（例: 180 秒。複数画像入力を考慮し生成より長め）を設定する。

### Requirement 9: 画像編集の CLI インターフェース

**Objective:** Claude として、アップロード済みの既存画像をプロンプトで編集したい。それにより、生成と同じ操作感で画像の修正・合成を行える。

#### Acceptance Criteria

1. The 画像編集スクリプト shall `--prompt` と最低 1 個の `--image` を必須とし、`--image`（複数指定可）/`--mask`/`--size`/`--quality`/`--format`/`--background`/`--compression`/`--n`/`--user`/`--output` を名前付き引数として公開する。
2. If `--prompt` または `--image` が一つも指定されていないとき、then the 画像編集スクリプト shall API を呼び出さずにエラーを返し、非ゼロの終了コードで終了する。
3. The 画像編集スクリプト shall 認証情報を CLI 引数として受け取らず、Requirement 6 と同一の認証・設定経路（環境変数・`.env`・優先順位）を共有する。
4. The 画像編集スクリプト shall `--size` の既定値を `auto`（入力画像に合わせる）とし、`auto` のときサイズ制約検証をスキップする。`auto` 以外の `WxH` 指定時は Requirement 3 と同一の size 制約を適用する。
5. When 編集が完了したとき、the 画像編集スクリプト shall 結果画像を Requirement 5 と同一の命名規則・保存規約で保存し、絶対パスを `stdout` に出力する。

### Requirement 10: 画像編集の API 呼び出し（images/edits）

**Objective:** 利用者として、編集要求が Azure の編集エンドポイントに正しく送信されてほしい。それにより、入力画像とプロンプトに基づく編集結果が得られる。

#### Acceptance Criteria

1. The 画像編集スクリプト shall `{endpoint}/openai/deployments/{deployment}/images/edits?api-version={api_version}` に `multipart/form-data` で POST する。
2. The 画像編集スクリプト shall 入力画像を `image[]` フィールド（単一でも `image[]`）として送信し、`--mask` 指定時は `mask` フィールドを追加する。
3. The 画像編集スクリプト shall `Content-Type` ヘッダを手動設定せず、HTTP クライアントが boundary 付きで設定するに任せる。
4. The 画像編集スクリプト shall `--size auto` のとき `size` フィールドを送信せず、`--format jpeg` のときのみ `output_compression` を送信する。
5. The 画像編集スクリプト shall 生成と同一のエラー分類（auth/rate_limit/bad_request/moderation/timeout/unknown）と 429 指数バックオフリトライを適用する。

### Requirement 11: 画像編集の入力検証

**Objective:** 利用者として、不正な入力画像・マスクを API 呼び出し前に検出してほしい。それにより、無駄な API 呼び出しと不明瞭なエラーを避けられる。

#### Acceptance Criteria

1. If `--image` が 0 個のとき、then the 画像編集スクリプト shall API を呼び出さずにエラーを返す。
2. If 入力画像が 16 個を超えるとき、then the 画像編集スクリプト shall API を呼び出さずにエラーを返す。
3. If 入力画像または `--mask` のパスが存在しない／ファイルでない／対応拡張子（`.png`/`.jpg`/`.jpeg`/`.webp`）でないとき、then the 画像編集スクリプト shall API を呼び出さずにエラーを返す。
4. If `--mask` の拡張子が `.png` でないとき、then the 画像編集スクリプト shall API を呼び出さずにエラーを返す（マスクは PNG 必須）。
5. The 画像編集スクリプト shall 列挙値・依存関係の検証（quality/format/background/n、`background=transparent` は `format=png` 必須、`compression` は jpeg 限定）を生成と共通の規則で適用する。

### Requirement 12: 複数画像のマージ（オブジェクト置換）

**Objective:** 利用者として、ベース画像の一部のオブジェクトを別画像のオブジェクトに置き換えたい。それにより、複数素材を合成した1枚を得られる。

#### Acceptance Criteria

1. When `--image` が複数指定されたとき、the 画像編集スクリプト shall 先頭の画像をベース、2 個目以降を参照素材として `image[]` に順序どおり送信する。
2. Where `--mask` が指定されたとき、the 画像編集スクリプト shall マスクの透過領域のみを編集対象とする（ベース画像のその領域を置換対象とする）インペインティングを行う。
3. The 画像編集スキル shall `SKILL.md` に、単一画像編集とマージ（先頭がベース・`--mask` で領域限定）の使い分けと、置換内容をプロンプトで明示する旨のガイドを記載する。
