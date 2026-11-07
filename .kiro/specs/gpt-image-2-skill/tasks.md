# Implementation Plan

## 1. 基盤: スキル骨格・共通型・設定読み込み

- [x] 1.1 スキルディレクトリと共通型の整備
  - `.claude/skills/gpt-image/scripts/` に Python パッケージを作成し、依存（`requests`、`azure-identity`）を宣言する
  - 生成パラメータ・Azure 設定・認証ヘッダの共通データ型（quality/output_format/background の列挙含む）を定義し、デフォルト値を型に埋め込む
  - 観測可能な完了条件: 各モジュールから共通型を import でき、デフォルト値付きのパラメータ型がインスタンス化できる
  - _Requirements: 2.1_

- [x] 1.2 環境変数からの設定読み込み
  - `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT`（必須）と `AZURE_OPENAI_API_KEY`（任意）を環境変数から取得する
  - 必須変数が未設定のとき、キー値を一切含めない分かりやすいエラーを送出する
  - 観測可能な完了条件: 必須変数設定時に設定オブジェクトが得られ、未設定時はシークレットを漏らさず非ゼロで失敗する
  - _Requirements: 6.1, 6.2, 6.6_

## 2. コア: 検証・認証・保存・API クライアント

- [x] 2.1 (P) パラメータ検証ロジック
  - size を「両辺 16px 倍数 / 長辺 ≤3840 / 比 ≤3:1 / 総ピクセル数 655,360〜8,294,400」で検証し、違反時は API 呼び出し前にエラーにする
  - quality・output_format・background・n(1〜10) の列挙/範囲を検証する
  - 依存関係を検証する: `background=transparent` は `output_format=png` 必須、`output_compression` は jpeg 時のみ有効で png 指定時は警告して無視、値は 0〜100 に制限する
  - 観測可能な完了条件: 制約違反の各ケースが具体的な原因メッセージとともにエラー化し、正常値は検証済みパラメータとして返る
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4_
  - _Boundary: Parameter Validation_

- [x] 2.2 (P) 認証ヘッダの解決
  - Entra ID トークン取得（`DefaultAzureCredential`）を試行し、成功時は Bearer 認証ヘッダを構成する
  - 取得失敗または未構成時は API キーを用いた認証ヘッダにフォールバックし、両方不可なら認証エラーにする
  - トークン・キーを stdout/stderr/ログ・例外メッセージに一切出力しない
  - 観測可能な完了条件: Entra ID 利用可能環境では Bearer、未構成環境では api-key ヘッダが返り、両方不可で安全なエラーになる
  - _Requirements: 6.3, 6.4, 6.5_
  - _Boundary: Auth Resolver_
  - _Depends: 1.2_

- [x] 2.3 (P) 画像の保存
  - レスポンスの Base64 文字列をデコードし、`gpt-image-2_<timestamp>_<index>.<ext>` 形式の一意名で保存する
  - 複数枚を連番で保存し、出力ディレクトリが存在しなければ作成する
  - 保存した各ファイルの絶対パスのリストを返す
  - 観測可能な完了条件: N 枚の画像バイト列を渡すと N 個のファイルが連番命名で保存され、絶対パス一覧が返る
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Boundary: Image Storage_

- [x] 2.4 (P) Azure 画像生成 API クライアント
  - デプロイ名ベースのエンドポイントへ JSON リクエストを POST し、余裕あるタイムアウト（既定 120 秒）を設定する
  - HTTP エラーを種別分類する（401/403=認証、400=不正/モデレーション、429=レート制限、timeout）、モデレーション拒否はユーザー向け文言を付す
  - 429 は上限付き指数バックオフで再試行し、上限超過・その他異常は分類済みエラーを送出する
  - 観測可能な完了条件: モックレスポンスで成功時に画像バイト列を返し、429 で再試行、各 HTTP エラーが対応する種別のエラーになる
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.1, 8.2_
  - _Boundary: Image API Client_

## 3. 統合: CLI エントリポイント

- [x] 3.1 CLI 引数解析と全体オーケストレーション
  - `--prompt` を唯一の必須引数とし、その他をデフォルト付き任意引数として公開する（認証情報は引数で受け取らない）
  - 検証 → 認証解決 → API 呼び出し → 保存の順に各コンポーネントを統括し、成功時は保存先絶対パスを stdout に出力する
  - 異常時はエラー原因を stderr に出し、非ゼロ終了コードで終了する
  - 観測可能な完了条件: `--prompt` のみ指定でデフォルト設定の生成・保存が完走しパスが stdout に出る。不正引数や API エラー時は非ゼロ終了する
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 7.4_
  - _Depends: 2.1, 2.2, 2.3, 2.4_

## 4. 検証: スキルマニフェストとテスト

- [x] 4.1 SKILL.md の作成
  - frontmatter に `name` と、トリガー語（「画像生成」「画像を作る」「gpt-image」「Azure で画像生成」等）を含む `description` を記述する
  - 前提条件（必要な環境変数・デプロイ名・limited access）、パラメータ要約と推奨デフォルト、代表的なコマンド例（正方形 / 透過 PNG / JPEG 圧縮）を記載する
  - 認証情報は環境変数から読む旨を明記し、値・エンドポイントを直書きしない
  - 観測可能な完了条件: 関連依頼でスキルが読み込まれる description を備え、コマンド例どおりに CLI を起動でき、シークレットの直書きがない
  - _Requirements: 1.1, 1.2, 1.3, 6.2_
  - _Depends: 3.1_

- [x] 4.2 単体テスト（検証・認証・保存・設定）
  - 検証: 16px 非倍数 / 4K 超 / 比 3:1 超 / ピクセル数範囲外 / 列挙値外、透過+jpeg のエラー、png+compression の警告と無視を検証する
  - 認証: Entra ID 成功で Bearer、未構成で api-key、両不可でエラーを検証する
  - 保存・設定: 命名規則と連番・絶対パス・ディレクトリ作成、必須環境変数未設定時のキー非出力エラーを検証する
  - 観測可能な完了条件: 上記ケースの単体テストがすべてパスする
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 5.2, 5.3, 5.5, 6.3, 6.4, 6.5, 6.6_

- [x] 4.3 統合テスト（モック API）
  - `--prompt` のみでデフォルト生成・保存まで完走することを検証する
  - `--n 3` で 3 枚が連番保存されること、429 応答後のバックオフ成功、400 モデレーション応答時のユーザー向けメッセージを検証する
  - 観測可能な完了条件: モック API を用いた一連の統合テストがすべてパスする
  - _Requirements: 2.2, 5.1, 5.3, 7.2, 7.3_
  - _Depends: 3.1_

- [ ]* 4.4 実環境 E2E 検証（任意・要 Azure リソース）
  - Entra ID（`az login` 済み）経路と API キー経路の双方で実際に画像生成できることを確認する
  - `--background transparent --format png` で透過 PNG が出力されることを確認する
  - 観測可能な完了条件: 両認証経路で実画像が保存され、透過 PNG が生成される（acceptance criteria 6.3/6.4 を実機で確認）
  - _Requirements: 6.3, 6.4_
  - _Depends: 3.1_

## 5. 拡張: 設定の優先順位・.env・命名（初版後に追加）

> 初版（生成のみ）リリース後に実装済み。本セクションはスペックドリフトの遡及記録。

- [x] 5.1 `.env` サポートと既定値の優先順位解決
  - カレントから上位へ `.env` を探索して読み込み、OS 環境変数を上書きせず未設定分のみ補完する
  - 各任意引数を「CLI 引数 > 環境変数(.env) > 組み込み既定」で解決する（`GPT_IMAGE_*`）
  - `AZURE_OPENAI_API_VERSION` を環境変数から取得し、未設定時は既定 `2025-04-01-preview` にフォールバックする
  - 観測可能な完了条件: `.env` の値が CLI 未指定時に反映され、OS 環境変数が優先される（`tests/test_dotenv.py`, `tests/test_env_defaults.py`）
  - _Requirements: 2.5, 6.1, 6.2.1_
  - _Boundary: Config Loader_

- [x] 5.2 プロンプト由来 title による一意ファイル名
  - プロンプトから安全な title を導出（禁止文字除去・空白ハイフン化・切り詰め・空なら image）し、`<title>_<timestamp>_<index>.<ext>`（マイクロ秒精度）で保存する
  - 保存先の既定を `./images` とし、無ければ作成する
  - 観測可能な完了条件: プロンプト由来の読みやすいファイル名で保存され、`--n>1` が連番になる（`tests/test_storage.py`, `tests/test_title.py`）
  - _Requirements: 5.2, 5.3, 2.2_
  - _Boundary: Image Storage_

## 6. 拡張: 画像編集（images/edits・初版後に追加）

> 初版スコープ外だった編集機能を、共通層を再利用して追加実装済み。本セクションはその遡及記録。

- [x] 6.1 EditParams 型と編集入力検証
  - `EditParams`（images: 1〜16, mask, size 既定 auto 等）を共通型に追加する
  - 入力画像の存在/種別/拡張子（.png/.jpg/.jpeg/.webp）、mask の PNG 必須、size!="auto" 時の size 制約を検証し、列挙値・依存関係は生成と共通化する
  - 観測可能な完了条件: 不正な枚数・欠落・非対応拡張子・非 PNG マスクが API 前にエラー化する（`tests/test_edit_validation.py`）
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
  - _Boundary: Parameter Validation_

- [x] 6.2 編集 API クライアント（multipart）
  - 共通リトライ/エラー分類を `_request_with_retry` に抽出し、`generate` と共有する
  - `images/edits` へ multipart で POST する `edit()` を追加（`image[]` 繰り返し、任意 `mask`、Content-Type 非設定、size=auto は省略、compression は jpeg 時のみ）
  - 観測可能な完了条件: 単一/複数画像・mask の送信、auto 省略、429 リトライ、エラー分類がモックで検証される（`tests/test_edit_client.py`）
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 8.3_
  - _Boundary: Image API Client_
  - _Depends: 6.1_

- [x] 6.3 編集 CLI エントリポイントとマージ対応
  - `edit_image.py` を追加し、`--prompt` と最低 1 個の `--image`（複数でマージ・先頭ベース）、`--mask` ほかを公開する
  - 検証 → 認証 → `edit` → 保存を統括し、結果の絶対パスを stdout に出力する（生成と同一規約）
  - 観測可能な完了条件: 単一編集・複数画像マージが完走しパスが出力され、不正引数/欠落画像/API エラーで非ゼロ終了する（`tests/test_edit_image.py`）
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 12.1, 12.2_
  - _Depends: 6.1, 6.2_

- [x] 6.4 SKILL.md の編集機能ドキュメント
  - frontmatter の `description` に編集系トリガー語を追加し、編集の2モード（単一編集・マージ）、`--mask` の使い方、パラメータ表、コマンド例を記載する
  - 観測可能な完了条件: 編集系依頼でスキルが読み込まれ、コマンド例どおりに `edit_image.py` を起動できる
  - _Requirements: 1.1, 1.3, 1.4, 12.3_
  - _Depends: 6.3_
