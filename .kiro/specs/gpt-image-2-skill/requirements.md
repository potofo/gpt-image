# Requirements Document

## Introduction

本仕様は、Claude Code から Azure AI Foundry（Microsoft Foundry）の `gpt-image-2` モデルを呼び出して画像を生成する Agent Skill の要件を定義する。スキルは「Claude に API を手書きさせない（生成ロジックは自己完結したスクリプトに閉じ込める）」「パラメータは検証付きの名前付き CLI 引数 + 妥当なデフォルトで渡す」という2つの中心方針に従う。Claude は `SKILL.md` の手順どおりに `scripts/generate_image.py` を呼び出し、生成画像をローカルに保存する。

本書では、対象システムを次のように表す。
- **画像生成スクリプト**: `scripts/generate_image.py`（CLI 本体。検証・API 呼び出し・保存を担う）
- **画像生成スキル**: `SKILL.md` を含むスキル全体（Claude の起動・実行経路を含む）

## Boundary Context

- **In scope**: テキストプロンプトからの画像生成（`images/generations`）、`size`/`quality`/`output_format`/`background`/`output_compression`/`n`/`user` のパラメータ制御と検証、Base64 デコードによるローカル保存、Entra ID（キーレス）と API キーの両認証経路、エラーハンドリングとレート制限リトライ。
- **Out of scope**（初版・将来拡張）: 画像編集（`images/edits`）・マスク・インペインティング、ストリーミング（`stream`/`partial_images`）、バッチ／キュー処理、Web UI。
- **Adjacent expectations**: Azure サブスクリプションと Azure OpenAI（Foundry）リソースが作成済みで、`gpt-image-2` が limited access 登録の上デプロイ済みであること。API バージョンは `2025-04-01-preview` 以降。ローカルに Python 3.10+ と必要ライブラリ（`requests` または `openai` SDK、Entra ID 利用時は `azure-identity`）が利用可能であること。

## Requirements

### Requirement 1: スキルの起動とトリガー

**Objective:** Claude Code 利用者として、画像生成に関する自然な依頼でこのスキルが自動的に読み込まれてほしい。それにより、ツール名を意識せず画像を生成できる。

#### Acceptance Criteria

1. The 画像生成スキル shall `SKILL.md` の frontmatter に `name` と、「画像生成」「画像を作る」「gpt-image」「Azure で画像生成」などのトリガー語を含む `description` を定義する。
2. When 利用者が画像生成に関連する依頼を行ったとき、the 画像生成スキル shall このスキルを読み込み、`SKILL.md` の手順に従って画像生成スクリプトを呼び出す。
3. The 画像生成スキル shall `SKILL.md` に前提条件（必要な環境変数・デプロイ名・limited access）、パラメータの要約と推奨デフォルト、代表的な呼び出しコマンド例を記載する。

### Requirement 2: CLI インターフェースとデフォルト値

**Objective:** Claude として、必要な差分だけを名前付き引数で指定したい。それにより、未指定の項目は推奨デフォルトが適用され、最小限の指示で画像を生成できる。

#### Acceptance Criteria

1. The 画像生成スクリプト shall `--prompt` を唯一の必須引数とし、`--size`/`--quality`/`--format`/`--background`/`--compression`/`--n`/`--user`/`--output` をすべて任意の名前付き引数として公開する。
2. When `--prompt` のみが指定されたとき、the 画像生成スクリプト shall デフォルト値（`size=1024x1024`、`quality=high`、`format=png`、`background=auto`、`n=1`、`output=./`）で画像を生成・保存する。
3. If `--prompt` が指定されていないとき、then the 画像生成スクリプト shall API を呼び出さずにエラーを返し、非ゼロの終了コードで終了する。
4. The 画像生成スクリプト shall 認証情報を CLI 引数として受け取らない。

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
2. The 画像生成スクリプト shall 保存ファイル名を `gpt-image-2_<timestamp>_<index>.<ext>` 形式で一意に生成する。
3. When `--n` が 2 以上のとき、the 画像生成スクリプト shall 生成された各画像を連番で保存する。
4. When 保存が完了したとき、the 画像生成スクリプト shall 保存したファイルの絶対パスを `stdout` に出力する。
5. If `--output` で指定されたディレクトリが存在しないとき、then the 画像生成スクリプト shall ディレクトリを作成するか、明確なエラーを返す。

### Requirement 6: 認証とシークレット管理

**Objective:** セキュリティ担当者として、認証情報がモデルのコンテキストやログに漏れない方式で扱われてほしい。それにより、長期キーの流出リスクを抑えられる。

#### Acceptance Criteria

1. The 画像生成スクリプト shall エンドポイント・デプロイ名・API キーを環境変数（`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_API_KEY`）から取得する。
2. The 画像生成スキル shall `SKILL.md` およびスクリプト本体に認証情報・エンドポイント値を直書きしない。
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
