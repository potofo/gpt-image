# ギャップ分析: gpt-image-2-5-support

- 分析日: 2026-11-07
- 対象要件: `.kiro/specs/gpt-image-2-5-support/requirements.md`（Requirement 1〜12、**未承認**）
- 対象コード: `.claude/skills/gpt-image/`（scripts 8 ファイル・約 1,100 行、tests 14 ファイル・118 件）
- 外部調査: `research/gpt-image-2.5-sunburst-flare.md`

---

## 1. 現状の把握

### 1.1 モジュール構成と責務

| モジュール | 責務 | 2.5 対応との関係 |
|---|---|---|
| `models.py` | `GenerationParams` / `EditParams` / `AzureConfig` / `AuthHeader`（frozen dataclass）。`Quality` / `OutputFormat` / `Background` を `Literal` 型で定義 | 型の値の範囲が gpt-image-2 用に固定されている |
| `config.py` | `.env` の読み込み、`load_config()` で `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_API_VERSION` を読む | 引数を取らない。デプロイ名は 1 つだけ |
| `validation.py` | Fail Fast の検証。size 制約・列挙値・依存関係（transparent→png、compression→jpeg）、編集の入力画像と mask | 許可値がモジュール定数（`VALID_QUALITY` など）で、モデルによって切り替わらない |
| `client.py` | URL・リクエストボディの組み立て、429 リトライ、HTTP エラーの分類、Base64 デコード | URL は deployments 形式のみ。タイムアウトは関数の既定値（生成 120 秒・編集 180 秒）で、`run()` から渡していない |
| `storage.py` | タイトルの導出、保存、拡張子の対応表 | `_EXTENSION.get(fmt, fmt)` なので `webp` はそのまま `.webp` になる（**変更不要**） |
| `auth.py` | Entra ID を優先し、API キーにフォールバック | 影響なし |
| `generate_image.py` / `edit_image.py` | argparse、`ENV_DEFAULTS`（環境変数と組み込み既定の対応）、`run()` で各処理をつなぐ（依存を注入できる） | **argparse の `choices` に quality・format・background の値が直接書かれている** |

### 1.2 守るべき規約

- **処理の流れ**: `parse_args → load_config → validate → resolve_auth → generate/edit → save`。例外の種類ごとに `stderr` の接頭辞（パラメータエラー／設定エラー／認証エラー／API エラー[kind]）と終了コード 1 が決まっている
- **既定値の優先順位**: `CLI > 環境変数(.env) > 組み込み既定` を、両 CLI がそれぞれ持つ `ENV_DEFAULTS` と `pick_str` / `pick_int` で実現している（**2 つの CLI に同じ処理が重複**）
- **テスト**: `run()` に関数を注入してテストする（`load_config=lambda: FAKE_CONFIG` など）。HTTP は `http_post` を差し替える。実際の Azure を呼ぶテストはない。`pytest.ini` にマーカーの定義はない
- **依存ライブラリ**: `requests` と `azure-identity` のみ。**画像処理ライブラリ（Pillow など）はない**
- **コメントとメッセージ**: 日本語。エラー文には原因と、使える値を含める

---

## 2. 要件と既存コードの対応表

凡例: ✅ 既存で満たしている / 🔧 拡張が必要（Missing） / ❓ 調査が必要（Unknown） / ⚠️ 制約（Constraint）

| 要件 | 内容 | 現状 | 判定 | メモ |
|---|---|---|---|---|
| 1.1–1.3 | モデル種別 3 つ、優先順位、不正値のエラー | なし | 🔧 | `ENV_DEFAULTS` に `model`（`GPT_IMAGE_MODEL`）を追加し、`--model` を追加 |
| 1.4 | デプロイ名から推測しない | 該当なし | ✅ | 新たに推測処理を作らなければよい |
| 2.1–2.3 | モデル種別ごとのデプロイ名と、`AZURE_OPENAI_DEPLOYMENT` へのフォールバック | `load_config()` は引数なしで、デプロイ名は 1 つ | 🔧⚠️ | `load_config` の呼び出し方が変わる。テストは `load_config=lambda: FAKE_CONFIG` を注入しているので、**引数を追加すると既存テストが壊れる** |
| 2.4 | デプロイ名が決まらないときのエラー | `ConfigError` で必須変数の不足を通知している | 🔧 | エラー文にモデル種別ごとの変数名を加える |
| 2.5 | デプロイ名を CLI 引数で受け取らない | 守られている | ✅ | |
| 3.1–3.3 | quality の値をモデルで切り替え | `VALID_QUALITY` が固定、argparse の `choices` も固定 | 🔧⚠️ | **argparse の `choices` を外して検証を `validation.py` に任せる必要がある**。そうしないと `xhigh` が argparse の段階で弾かれ、エラー文も argparse 形式になる |
| 3.4 | 既定は `high` のまま | `ENV_DEFAULTS` が `high` | ✅ | |
| 4.1–4.3 | background の `opaque` | `VALID_BACKGROUND` が固定、`choices` も固定 | 🔧 | 3.x と同じ |
| 4.4 | 透過には png（webp が有効なら webp も） | `_validate_dependencies` が png 固定 | 🔧 | 透過に対応する形式を集合で持つ |
| 5.1 | 2.5 の size 制約 | `_validate_size` は「長辺/短辺 ≤ 3」で判定しており、1:3〜3:1 と同じ意味 | ✅ | 制約は gpt-image-2 と同じなので共通化できる |
| 5.2 | 3,686,400 ピクセル超で experimental の警告 | 警告を出す仕組みは `print(..., file=sys.stderr)` が 1 か所あるだけ | 🔧 | 検証の中で警告を出すか、警告を戻り値で返すかは設計で決める |
| 5.3–5.4 | edit の `auto` は検証しない／gpt-image-2 は変えない | 既存の通り | ✅ | |
| 6.1–6.5 | `--complexity` | なし | 🔧 | 両 CLI、両 Params、`_build_body` と `_build_edit_data` に追加 |
| 6.6 / 7.7 / 8.x | Azure の検証結果による有効・無効 | なし | 🔧❓ | 「有効化」を何で切り替えるか（コード内の定数／環境変数）を決める必要がある |
| 7.1–7.4 | `--markup`、mask と排他、gpt-image-2 では拒否 | mask の仕組みはある | 🔧 | `files` に markup の部品を追加。**multipart のフィールド名が Azure で `markup` かどうかは不明** ❓ |
| 7.5 | markup が PNG・50MB 以下 | `_validate_input_image` で拡張子と存在は確認している | 🔧 | サイズの確認を追加 |
| 7.6 | markup と先頭画像の寸法一致 | **寸法を読む処理がない** | 🔧⚠️ | PNG は IHDR を標準ライブラリで読める。**先頭画像が JPEG／WebP の場合は、ヘッダを解析するか Pillow を追加する必要がある** ❓ |
| 8.1–8.4 | WebP（検証後に有効化） | `VALID_FORMAT` は png/jpeg。エラー文に「WEBP は Azure 非対応」と直接書かれている | 🔧 | storage は対応済み。compression の依存関係（jpeg 専用）を jpeg/webp に広げる。client の `output_format == "jpeg"` という判定も 2 か所変える |
| 9.1–9.3 | Azure 実機での検証手順 | **実機テストの仕組みがない** | 🔧 | pytest マーカー（例: `live`）を `pytest.ini` に登録し、認証情報がなければ skip する。または独立したスクリプトにする |
| 9.4 | 結果を `research/` に記録 | — | 🔧 | 手作業か、スクリプトが Markdown を出力するか |
| 9.5 | api-version／エンドポイント形式の切り替え | `AZURE_OPENAI_API_VERSION` は設定できる。URL は deployments 形式で固定 | ❓🔧 | 2025-04-01-preview で新しい値が通れば対応不要。通らなければ v1 形式（`/openai/v1/images/...` で、`model` にデプロイ名）に対応する |
| 10.1–10.3 | 2.5 は 120 秒超のタイムアウト | 生成は 120 秒、編集は 180 秒（関数の既定値） | 🔧 | 生成は 2.5 のとき延ばす。編集の 180 秒は既に 120 秒を超えている。`run()` からタイムアウトを渡すか、client でモデル種別を見て決める |
| 11.1–11.4 | 後方互換 | 118 件のテストがある | ⚠️ | `load_config` の呼び出し方と、argparse の `choices` を外すことによる**エラーの出方の変化**（argparse の終了コード 2 → 検証エラーの終了コード 1。テストは `!= 0` しか確認していない）に注意（§2.1） |
| 12.x | SKILL.md・README・.env.example | gpt-image-2 前提の記述 | 🔧 | ドキュメントの更新。**steering の `tech.md`（「WEBP は Azure では非対応」「対象は gpt-image-2」）も更新対象** |

### 2.1 見つかった制約と注意点

1. **argparse の `choices` と検証の二重管理**: 現在は quality・format・background の値を argparse と `validation.py` の両方で検査している。モデルごとに値が変わると argparse では表現できないため、検査を片方に寄せる必要がある。`choices` を外すと、不正値のときの終了コードが 2（argparse）から 1（ValidationError）に変わる。既存テストは `code != 0` しか確認していないため（`test_generate_image.py` / `test_edit_image.py`）、テストは壊れない。ただし利用者から見える挙動は変わる（どちらも非ゼロなので、要件 11.3 の「終了コードを変えない」に反するかどうかは解釈次第）。
2. **`load_config()` の呼び出し方**: モデル種別がわからないとデプロイ名を決められない。案は 3 つある。(a) `load_config(model)` にする、(b) モデル種別ごとのデプロイ名を `AzureConfig` にまとめて持たせる、(c) `run()` の中で解決して `replace()` で差し替える。(a) は注入しているテスト用の関数（引数なし）と合わなくなる。
3. **`Literal` 型**: 実行時には検査されないため、値を広げなくても動作はするが、型の意味としてはずれる。モデルごとの対応表に合わせて更新するのが望ましい。
4. **CLI 間の重複**: 2 つの CLI に `ENV_DEFAULTS` と `pick_*` が重複している。`model` と `complexity` を両方に足すと重複がさらに増える。

---

## 3. 実装方針の選択肢

### 方式 A: 既存コンポーネントの拡張

- `validation.py` に、モデル種別ごとの許可値を持つ dict（例: `MODEL_CAPABILITIES[model] = {quality: {...}, background: {...}, formats: {...}, supports_complexity, supports_markup}`）を置き、`_validate_enums` などがそれを参照する
- `config.py` に、モデル種別ごとのデプロイ名の環境変数の対応表を追加する
- `models.py` の Params に `model` と `complexity`（編集には `markup` も）を追加する
- `client.py` の `_build_body` / `_build_edit_data` / `edit` に新しいフィールドを追加し、タイムアウトをモデル種別で切り替える
- 両 CLI に引数と `ENV_DEFAULTS` を追加し、`choices` を外す

**良い点**: 新しいファイルがほぼ不要で、既存の規約（Fail Fast、注入でのテスト）にそのまま乗れる。変更の量が少ない。
**悪い点**: `validation.py`（現在 187 行）に、モデルの知識と寸法の読み取りが加わって大きくなる。CLI 間の重複も増える。

### 方式 B: 新しいコンポーネントの作成

- **`capabilities.py`（新規）**: モデル種別の一覧、モデルごとの許可値・対応機能・推奨タイムアウト、Azure の検証で有効にした機能のフラグを、1 か所にまとめて宣言する
- **`image_info.py`（新規）**: 標準ライブラリだけで PNG／JPEG／WebP のヘッダから寸法を読む（Pillow を使わない）
- **`tests/live/`（新規）**: Azure の実機で検証するテスト。マーカーと環境変数で、実行するかどうかを決める
- 既存モジュールはこれらを参照するだけにする

**良い点**: 「モデルの知識」がまとまり、2.6 などが今後追加されたときも対応表を 1 か所直すだけで済む。単体テストもしやすい。
**悪い点**: ファイルが増え、モジュール間のつながりを設計する必要がある。

### 方式 C: ハイブリッド（推奨候補）

- **新規**: `capabilities.py`（モデルごとの対応表と機能フラグ）、`image_info.py`（寸法の読み取り）、Azure 実機検証の仕組み
- **拡張**: `validation.py`（対応表を参照して検証）、`config.py`（デプロイ名の解決）、`client.py`（フィールドとタイムアウト）、`models.py`、両 CLI
- **任意のリファクタ**: CLI 間の重複（`ENV_DEFAULTS` と `pick_*`）を共通モジュールに出すかどうかは、設計段階で範囲を決める（本仕様では必須ではない）
- **段階的な実施**:
  1. 対応表、モデル指定、quality・background の拡張、size の警告、タイムアウト（Azure で確認済みの範囲。要件 1〜5・10〜12）
  2. Azure 実機での検証（要件 9）
  3. 検証結果に基づいて complexity・markup・WebP を有効にする（要件 6〜8）

**良い点**: 確認済みの範囲を先に出せる。未確認の機能は機能フラグで閉じておけるので、Azure で拒否されても元に戻すのが簡単。
**悪い点**: 段階ごとにドキュメントの更新が必要になる。

---

## 4. 規模とリスク

| 範囲 | 規模 | リスク | 理由 |
|---|---|---|---|
| 要件 1〜5・10〜12（モデル指定、値の拡張、警告、タイムアウト、ドキュメント） | **M** | **低** | 既存の型と検証パターンの延長。ただし CLI・config・テストへの影響が広い |
| 要件 6（complexity） | S | 中 | 実装は単純だが、Azure が受け付けるかどうかが不明 |
| 要件 7（markup） | M | **中〜高** | 寸法の読み取り（JPEG／WebP）と、multipart のフィールド名が不明。Azure が受け付けるかも不明 |
| 要件 8（WebP） | S | 中 | 実装は少ないが、Azure のドキュメントが矛盾している |
| 要件 9（Azure 実機検証） | S〜M | 中 | 実機を呼ぶため、デプロイ・クォータ・費用が必要。CI では動かさない設計が必要 |
| **全体** | **M（3〜7 日）** | **中** | 既存の規約に乗れるが、外部 API の未確定事項が要件 6〜9 に集中している |

---

## 5. 設計フェーズへの申し送り

### 5.1 推奨方針

- **方式 C（ハイブリッド）**を第一候補とする。モデルごとの対応表を `capabilities.py` にまとめ、Azure で未確認の機能は機能フラグで無効にしたまま始める。
- 設計で決めておくべきこと:
  1. 許可値の検査を argparse と検証のどちらに寄せるか、それに伴う終了コードの変化をどう扱うか
  2. `load_config` の呼び出し方（モデル種別を渡す方法）と、既存テストで注入している関数との互換
  3. 機能フラグの持ち方（コード内の定数か環境変数か。利用者が誤って有効にしないこと）
  4. experimental の警告を出す仕組み（検証関数の中で `stderr` に出すか、警告を戻り値で返すか）
  5. 生成のタイムアウトを 2.5 で何秒にするか（例: 生成・編集とも 300 秒）
  6. CLI 間の重複を解消するリファクタを、この仕様の範囲に含めるか

### 5.2 調査が必要な項目（Research Needed）

| # | 項目 | 調べ方 |
|---|---|---|
| R1 | 2025-04-01-preview で `quality=xhigh/max/auto` と `background=opaque` が通るか | 要件 9 の実機検証 |
| R2 | 通らない場合、v1 形式（`/openai/v1/images/...?api-version=preview` で `model` にデプロイ名）で通るか。認証のスコープやヘッダに違いはあるか | 実機検証と Microsoft Learn |
| R3 | Azure の edits における markup の multipart フィールド名と形式（`markup` のファイル部品で送るのか） | 実機検証。OpenAI の SDK の multipart の組み立て方も参考にする |
| R4 | `complexity` を Azure が受け付けるか（受け付けない場合、無視されるのか 400 になるのか） | 実機検証 |
| R5 | Azure の 2.5 で `output_format=webp` を使えるか | 実機検証 |
| R6 | 寸法の読み取り: JPEG（SOF マーカー）・WebP（VP8／VP8L／VP8X）を標準ライブラリで読むか、Pillow を追加するか。EXIF の向き補正（OpenAI は「向き補正後の寸法」と記載）をどう扱うか | 設計で判断する。Pillow を追加しない場合は、先頭画像が PNG の場合だけ確認する妥協案もある |
| R7 | 2.5 の Azure クォータ（IPM）と 429 の頻度。今のリトライ回数（3 回）で足りるか | 実機検証と Foundry ポータル |
| R8 | `user` を Azure の 2.5 で使えるか（OpenAI では非推奨で `safety_identifier` が後継） | 実機検証。今回の要件の範囲外だが、警告の要否を判断するため |

---

# 設計フェーズの調査と判断（2026-11-07）

## Summary
- **Feature**: `gpt-image-2-5-support`
- **Discovery Scope**: Extension（軽量な調査。既存のパイプラインの拡張と、Azure API の未確定事項の整理）
- **Key Findings**:
  - モデルごとの差分は「許可値」「対応機能」「タイムアウト」「デプロイ名の環境変数」の 4 種類に整理でき、宣言的な対応表 1 つで表現できる
  - OpenAI の markup は multipart のフィールド名 `markup`（`image/png`）で送る。条件は「向き補正後に先頭画像と同じ寸法」「透過ピクセルを含む」「50MB 以下」「各 16,777,216 ピクセル以下」「mask と併用不可」
  - 既存テストは `load_config=lambda: FAKE_CONFIG`（引数なし）を注入しており、終了コードは `!= 0` しか確認していない。これを踏まえて互換性を保つ方法を決めた

## Research Log

### markup の multipart 形式
- **Context**: 要件 7.2 を実現するには、edits でのフィールド名と形式を決める必要がある（ギャップ分析の R3）
- **Sources Consulted**: [OpenAI Image generation guide「Guide an edit with markup」](https://developers.openai.com/api/docs/guides/image-generation)
- **Findings**: curl の例は `-F 'image=@kitchen.webp;type=image/webp' -F 'markup=@overlay.png;type=image/png'`。「After orientation, the annotation layer and the first image must have the same width and height」「The PNG must contain transparent pixels」
- **Implications**: client は `markup` のファイル部品を `image/png` で送る。寸法の確認には EXIF の向き補正への対応が必要（JPEG）。Azure で受け付けられるかは検証ツールで確認する

### エンドポイント形式（deployments 形式 / v1 形式）
- **Context**: 要件 9.5。2025-04-01-preview で新しい値が通らない場合の代わりの経路
- **Sources Consulted**: [Azure OpenAI REST reference (v1 preview)](https://learn.microsoft.com/en-us/azure/foundry/openai/reference-preview-latest)、[Foundry image how-to](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/dall-e)
- **Findings**: v1 形式は `POST {endpoint}/openai/v1/images/{generations|edits}?api-version=preview` で、`model` にデプロイ名を入れる。トークンのスコープについては、how-to の SDK の例が `https://ai.azure.com/.default` を使っている（既存コードは `https://cognitiveservices.azure.com/.default`）
- **Implications**: `api_style` で URL とボディを切り替える。スコープの違いは検証ツールの v1 形式の確認で 401 になるかどうかで判断し、必要なら別仕様で扱う（R2 の続き）

### 既存テストとの互換性
- **Context**: 要件 11.4（既存テストをすべて成功させる）
- **Sources Consulted**: `tests/test_generate_image.py` / `test_edit_image.py` / `test_integration.py`
- **Findings**: `load_config` は引数なしの lambda で注入されている。不正値のテストは `code != 0` だけを確認している
- **Implications**: D2、D3 を参照

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 定数を条件分岐で拡張 | validation の中で `if model == ...` と分岐する | 変更が少ない | モデルの知識が validation・client・config に散らばる | 2.6 を追加するときに直す箇所が多い |
| 宣言的な対応表（採用） | `capabilities.py` に `ModelCapability` を置き、各層はそれを参照する | 知識が 1 か所にまとまる。単体テストしやすい | ファイルが 1 つ増える | steering の「ロジックの集約」に合う |
| モデルごとのストラテジクラス | モデルごとに validator と client を作り分ける | 大きく違う場合に柔軟 | 差分が値だけの今回には大げさ | 不採用 |

## Design Decisions

### D1: モデルの知識を `capabilities.py` に集約する
- **Context**: 要件 1、3〜8、10 はどれも「モデルによって何が許されるか」に依存している
- **Alternatives Considered**: 1) validation の中で分岐する 2) 宣言的な対応表を作る 3) モデルごとのストラテジクラスを作る
- **Selected Approach**: 2。frozen dataclass の `ModelCapability` と、`get_capability` / `is_feature_enabled` などの純粋関数を用意する
- **Rationale**: 差分は値と機能の有無だけなので、データで表現するのがもっとも単純
- **Trade-offs**: モジュールが 1 つ増える代わりに、ほかの層からモデル名の分岐がなくなる

### D2: quality・format・background の検査を validation に一本化する
- **Context**: argparse の `choices` はモデルによって値を変えられない
- **Alternatives Considered**: 1) `choices` を全モデルの値の和集合にし、validation でモデル別に再検査する 2) `choices` を外す
- **Selected Approach**: 2
- **Rationale**: 1 では、許可値がまた 2 か所で管理されることになる。2 では検査が 1 か所になり、エラー文にモデル名と使える値を入れられる
- **Trade-offs**: 不正値のときの終了コードが 2 から 1 に変わる（どちらも非ゼロ。既存テストは `!= 0` だけを確認）。argparse のヘルプに選択肢が自動で表示されなくなるため、ヘルプの文字列に値を書く

### D3: 既定モデルでは `load_config()` を引数なしで呼ぶ
- **Context**: `load_config` はモデル種別がわからないとデプロイを決められない。一方、既存テストは引数なしの lambda を注入している
- **Alternatives Considered**: 1) 常に `load_config(model)` を呼び、テストダブルを修正する 2) デプロイの解決を別の注入関数に分ける 3) 既定モデルのときだけ引数なしで呼ぶ
- **Selected Approach**: 3。`load_config(model: ModelName = DEFAULT_MODEL)` とし、`run()` は `model == DEFAULT_MODEL` のとき引数なしで呼ぶ
- **Rationale**: 既定モデルでは、引数なしの呼び出しと `load_config("gpt-image-2")` が同じ意味になる。そのため分岐しても動作は変わらず、既存テストを変更せずに済む（11.4）。2 では、`load_config` が `AZURE_OPENAI_DEPLOYMENT` を必須とする現在の挙動とモデル種別ごとの環境変数（2.3）が両立しない
- **Trade-offs**: `run()` に分岐が 1 つ増える。将来テストダブルを見直すときに、この分岐を外せる
- **Follow-up**: 統合テストで「既定モデルでは引数なしで呼ばれる」ことを確認する

### D4: タイムアウトはモデル別の値を client で補う
- **Context**: 要件 10。テストでは `generate(config, auth, params)` の 3 引数で注入している
- **Selected Approach**: `timeout: Optional[float] = None` とし、`None` のときは `ModelCapability` の値を使う。gpt-image-2 は 120 秒と 180 秒（従来どおり）、2.5 系は 300 秒
- **Rationale**: `run()` からタイムアウトを渡すと、注入しているテストダブルのシグネチャが合わなくなる

### D5: 機能フラグはコード内の定数にし、complexity と markup は最初から有効にする（設計レビューで改訂）
- **Context**: 要件 6.6、7.7、8.1。Azure での動作がわからない機能をどう出荷するか
- **Alternatives Considered**: 1) 環境変数で有効にする 2) コード内の定数 `AZURE_ENABLED` にし、すべて無効で出荷する 3) コード内の定数にし、complexity と markup は有効、WebP は無効で出荷する
- **Selected Approach**: 3（2026-11-07 の設計レビューで、ユーザーの判断により 2 から変更）。初期値は `complexity=True`、`markup=True`、`webp=False`。検証ツールの結果を `research/` に記録し、拒否された機能は False に、受け付けられた WebP は True に変える
- **Rationale**: 要件 6.2 と 7.2 は「2.5 系なら無条件にリクエストに含める」と書いており、すべて無効にする案（2）は要件と食い違う。WebP は要件 8.1 で「確認できたら有効にする」と明記されているため無効から始める。環境変数で切り替えられるようにしない理由は、利用者が誤って有効にしないためと、変更の根拠をコードレビューで確認できるようにするため
- **Trade-offs**: Azure が complexity や markup を拒否する場合、確認してフラグを変えるまでは、利用者に API の 400 エラーが返る。400 のエラー文でモデル種別とデプロイの確認を促し、`SKILL.md` にも注意書きを入れて影響を抑える

### D6: 寸法は標準ライブラリで読み、読めない場合は確認を省いて警告する
- **Context**: 要件 7.6。依存ライブラリを増やさない（steering）
- **Alternatives Considered**: 1) Pillow を追加する 2) 標準ライブラリでヘッダを解析する（PNG・JPEG・WebP）3) PNG だけを確認する
- **Selected Approach**: 2。JPEG は EXIF の Orientation（5〜8）で幅と高さを入れ替える。判定できない場合は `None` を返し、検証側は警告して API の判定に任せる
- **Rationale**: 入力画像の形式（png・jpg・webp）をすべて扱える。依存も増えない
- **Trade-offs**: 解析処理の保守が必要になる。珍しい形式では確認を省くことになる

### D7: 実機での検証は pytest とは別のスクリプトにする
- **Context**: 要件 9.2（通常のテストと分ける）、費用の管理
- **Alternatives Considered**: 1) pytest のマーカーと環境変数で skip する 2) 独立したスクリプト `tests/live/verify_azure.py` にする
- **Selected Approach**: 2。pytest の収集対象外の名前にし、手動で実行する。結果は Markdown で出力する
- **Rationale**: 確認項目ごとに「受け付けられた／拒否された」を記録したいので、pass / fail の二値で表すテストより、レポートを出すツールのほうが合っている。うっかり実行して費用がかかることもない

### D8: 検証を通さずに送る公開関数 `client.post_raw` を設ける（設計レビューで追加）
- **Context**: 要件 9.1、9.3。検証ツールは、検証で弾かれる値も Azure に送って可否を確かめる必要がある。当初の設計では `_build_url` などの内部関数に頼っていた
- **Alternatives Considered**: 1) 検証ツールが内部関数を直接使う 2) 検証ツールが HTTP を自前で組み立てる 3) client に公開関数 `post_raw` / `build_url` を設ける
- **Selected Approach**: 3。`post_raw` はステータスにかかわらず `RawResponse` を返し、v1 形式では `model` を自動で加える。`generate` / `edit` も `post_raw` の上に作り直す
- **Rationale**: URL とボディの組み立てを 1 か所にまとめられ、検証ツールと本番の送信処理が同じ組み立て方を使うことが保証される
- **Trade-offs**: client の公開面が増えるため、シグネチャの変更が Revalidation Triggers の対象になる

### D9: `resolve_auth` にトークンのスコープの引数を追加する（設計レビューで追加）
- **Context**: 要件 9.5。Microsoft のドキュメントでは、v1 形式の例で `https://ai.azure.com/.default` を使っている
- **Selected Approach**: `resolve_auth(api_key, credential=None, scope=TOKEN_SCOPE)`。`AzureConfig.token_scope` は `AZURE_OPENAI_TOKEN_SCOPE` で上書きでき、既定は従来の値。`run()` は `scope=config.token_scope` を渡す
- **Rationale**: 認証の方式自体は変えずに、v1 形式で必要になったときの経路を用意できる。既存のテストダブル（`lambda api_key, **kw`）とも互換がある
- **Follow-up**: 検証ツールの結果、v1 形式で従来のスコープが 401 になった場合だけ、API 形式ごとに既定を変える

## Risks & Mitigations
- Azure が 2.5 系の新しい値をどちらの形式でも受け付けない → 機能フラグを False のままにして `SKILL.md` に記載する（要件 6.6、7.7 の範囲内）
- v1 形式でトークンのスコープが違う → `resolve_auth` にスコープの引数を設け（D9）、検証ツールで 2 つのスコープを試す。結果に応じて既定のスコープを変える
- complexity・markup が Azure で拒否される（最初から有効にしたため利用者に 400 が返る）→ 実装の直後に検証ツールを実行し、拒否されたら `AZURE_ENABLED` を False にする
- JPEG の寸法の読み取り誤り → 代表的なサンプル（ベースライン、プログレッシブ、EXIF の向きあり）で単体テストする。読み取れない場合は確認を省く
- 2.5 系の `high` と gpt-image-2 の `high` の違いで、利用者が混乱する → `SKILL.md` に明記する（3.5）
