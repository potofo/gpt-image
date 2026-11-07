# Requirements Document

## Project Description (Input)
既存の gpt-image スキル（Azure Foundry 上の gpt-image-2 前提）を、gpt-image-2.5-sunburst と gpt-image-2.5-flare モデルに対応させる。research/gpt-image-2.5-sunburst-flare.md の調査結果を参照すること。主な対応: モデル種別の明示（環境変数）とモデル別許可値の切り替え、quality の xhigh/max/auto 追加、background=opaque 追加、2560x1440 超の experimental 警告、complexity パラメータ、edits の markup パラメータ（mask と排他）、Azure 検証後の WebP 対応、Sunburst/Flare の切り替え、gpt-image-2 との後方互換維持。

## Introduction

本仕様は、実装済みの `gpt-image` スキル（仕様: `.kiro/specs/gpt-image-2-skill/`、Azure AI Foundry 上の `gpt-image-2` 前提）を拡張し、2026-09-08 に GA となった `gpt-image-2.5-sunburst`（精度重視）と `gpt-image-2.5-flare`（速度重視）を利用できるようにするための差分要件を定義する。根拠となる調査結果は `research/gpt-image-2.5-sunburst-flare.md` にまとめている。

既存スキルの 2 つの中心方針（「Claude に API を手書きさせない」「パラメータは検証付きの名前付き CLI 引数＋妥当なデフォルトで渡す」）と、API 呼び出し前に不正値を弾く Fail Fast の方針はそのまま引き継ぐ。そのうえで、モデルによって許される値が違うことをスクリプトが理解し、モデルに合わない値を API 呼び出し前に検出できるようにする。

本書では、対象システムを次のように表す（既存仕様と同じ）。
- **画像生成スクリプト**: `scripts/generate_image.py`
- **画像編集スクリプト**: `scripts/edit_image.py`
- **画像生成・編集スキル**: `SKILL.md` を含むスキル全体
- **両スクリプト**: 画像生成スクリプトと画像編集スクリプトの両方

本書で使う用語:
- **モデル種別**: スクリプトが「呼び出し先のデプロイがどのモデルか」として扱う識別子。`gpt-image-2` / `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst` のいずれか。
- **2.5 系モデル**: `gpt-image-2.5-flare` と `gpt-image-2.5-sunburst` の総称。
- **Azure 未検証機能**: OpenAI の公式ドキュメントでは 2.5 系モデルでの対応が記載されているが、Azure のドキュメントでは確認できていない機能。`complexity`、`markup`、WebP 出力、および新しい値が通る api-version を指す（調査レポート §4.3）。

## Boundary Context

- **In scope**:
  - モデル種別の指定（環境変数・CLI 引数）と、モデル種別ごとの許可値の切り替え
  - Flare と Sunburst のデプロイを、呼び出しごとに切り替えること
  - `quality` の `xhigh` / `max` / `auto` 追加（2.5 系のみ）
  - `background` の `opaque` 追加（2.5 系のみ）
  - 2.5 系での size 制約の適用と、2560x1440 を超える解像度への experimental 警告
  - `complexity` パラメータ（生成・編集）と、`markup` パラメータ（編集のみ・`mask` と排他）
  - Azure 未検証機能を Azure の実環境で確認する手順と、その結果に基づく有効化（WebP を含む）
  - 2.5 系の処理時間に合わせたタイムアウト
  - `SKILL.md`・README・`.env.example` へのモデル選択と新パラメータの記載
  - `gpt-image-2` デプロイを使う既存利用者の後方互換
- **Out of scope**:
  - GPT Image 2.6（`gpt-image-2.6-*`。現時点で Azure では提供されていない）
  - GIF 出力・SVG 出力（OpenAI でもプレビュー・限定アクセスで、Azure にはドキュメントがない）
  - ストリーミング（`stream` / `partial_images`）、Batch API、Responses API（既存仕様と同じく対象外）
  - `gpt-image-1` 系・`gpt-image-1.5` への対応
  - デプロイ名からのモデル種別の自動推定（Azure ではデプロイ名を自由に付けられるため）
  - コスト（トークン使用量）の集計・表示
- **Adjacent expectations**:
  - Azure Foundry リソースに、利用するモデル（`gpt-image-2`、`gpt-image-2.5-flare`、`gpt-image-2.5-sunburst` のいずれか 1 つ以上）がデプロイ済みであること
  - 既存仕様 `gpt-image-2-skill` の要件（認証、保存、エラーハンドリング、`.env` の扱いなど）は、本書で変更すると明記したもの以外はそのまま有効であること

## Requirements

### Requirement 1: モデル種別の指定

**Objective:** スキル利用者として、使っているデプロイがどのモデルかをスクリプトに伝えたい。それにより、そのモデルで使えるパラメータと値だけが受け付けられるようになる。

#### Acceptance Criteria

1. The 両スクリプト shall モデル種別として `gpt-image-2` / `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst` の 3 つを受け付ける。
2. The 両スクリプト shall モデル種別を「CLI 引数 `--model` > 環境変数 `GPT_IMAGE_MODEL`（`.env` を含む）> 組み込み既定 `gpt-image-2`」の優先順位で決定する。
3. If 受け付けていないモデル種別が指定されたとき、then the 両スクリプト shall API を呼び出さずに、受け付けるモデル種別の一覧を含むエラーを標準エラー出力に表示し、非ゼロの終了コードで終了する。
4. The 両スクリプト shall モデル種別をデプロイ名から推測しない。

### Requirement 2: Flare / Sunburst のデプロイ切り替え

**Objective:** スキル利用者として、Flare と Sunburst の両方をデプロイしておき、呼び出しごとに使い分けたい。それにより、「ラフ案は Flare で作り、仕上げは Sunburst で行う」という使い方ができる。

#### Acceptance Criteria

1. The 両スクリプト shall モデル種別ごとのデプロイ名を、モデル種別ごとの環境変数（`.env` を含む）で設定できるようにする。
2. When モデル種別に対応するデプロイ名の環境変数が設定されているとき、the 両スクリプト shall そのデプロイ名を呼び出し先に使う。
3. When モデル種別に対応するデプロイ名の環境変数が設定されていないとき、the 両スクリプト shall 既存の `AZURE_OPENAI_DEPLOYMENT` を呼び出し先に使う。
4. If 呼び出し先のデプロイ名がどの環境変数からも決まらないとき、then the 両スクリプト shall API を呼び出さずに、設定すべき環境変数名を含むエラーを表示し、非ゼロの終了コードで終了する。
5. The 両スクリプト shall デプロイ名を CLI 引数として受け取らない（既存仕様の「接続情報は環境変数からのみ取得する」方針を維持する）。

### Requirement 3: quality の拡張

**Objective:** 2.5 系モデルの利用者として、新しい品質設定 `xhigh` / `max` / `auto` を使いたい。それにより、品質と速度・コストのバランスを細かく選べる。

#### Acceptance Criteria

1. While モデル種別が 2.5 系モデルであるとき、the 両スクリプト shall `--quality` に `low` / `medium` / `high` / `xhigh` / `max` / `auto` を受け付ける。
2. While モデル種別が `gpt-image-2` であるとき、the 両スクリプト shall `--quality` に `low` / `medium` / `high` だけを受け付ける。
3. If モデル種別で受け付けない `--quality` の値が指定されたとき、then the 両スクリプト shall API を呼び出さずに、そのモデル種別で使える値の一覧を含むエラーを返す。
4. The 両スクリプト shall `--quality` の組み込み既定を、モデル種別にかかわらず `high` のままとする（既存の挙動を変えない）。
5. The 画像生成・編集スキル shall `SKILL.md` に「2.5 系の `high` は gpt-image-2 の `high` と消費トークンが異なる」「`max` は処理時間とコストが大きい」ことを記載する。

### Requirement 4: background の拡張

**Objective:** 2.5 系モデルの利用者として、背景を不透明にする `opaque` を明示的に指定したい。それにより、透過させたくない画像で背景が確実に塗られる。

#### Acceptance Criteria

1. While モデル種別が 2.5 系モデルであるとき、the 両スクリプト shall `--background` に `auto` / `opaque` / `transparent` を受け付ける。
2. While モデル種別が `gpt-image-2` であるとき、the 両スクリプト shall `--background` に `auto` / `transparent` だけを受け付ける。
3. If モデル種別で受け付けない `--background` の値が指定されたとき、then the 両スクリプト shall API を呼び出さずに、そのモデル種別で使える値の一覧を含むエラーを返す。
4. If `--background transparent` が透過に対応しない出力形式と組み合わされたとき、then the 両スクリプト shall API を呼び出さずにエラーを返す（透過に対応する形式は `png`。Requirement 8 で WebP が有効になった場合は `webp` も含む）。

### Requirement 5: size 制約と experimental 解像度の警告

**Objective:** 2.5 系モデルの利用者として、使える解像度の範囲を API 呼び出し前に確認したい。また、品質が安定しない解像度を指定したときには気付けるようにしたい。

#### Acceptance Criteria

1. While モデル種別が 2.5 系モデルであるとき、the 両スクリプト shall `--size` に既存仕様と同じ制約（両辺が 16px の倍数、長辺 3840px 以下、アスペクト比 1:3〜3:1、総ピクセル数 655,360〜8,294,400）を適用し、違反した場合は API を呼び出さずにエラーを返す。
2. While モデル種別が 2.5 系モデルであるとき、when `--size` の総ピクセル数が 2560x1440（3,686,400 ピクセル）を超えるとき、the 両スクリプト shall 処理を続けたうえで、その解像度が experimental である旨の警告を標準エラー出力に表示する。
3. The 画像編集スクリプト shall `--size auto` のときは size 制約の検証と experimental の警告を行わない（既存仕様と同じ）。
4. While モデル種別が `gpt-image-2` であるとき、the 両スクリプト shall size に関する既存の挙動（検証とエラー文言）を変えない。

### Requirement 6: complexity パラメータ

**Objective:** 2.5 系モデルの利用者として、モデルが描画前にどれだけ計画するか（complexity）を指定したい。それにより、処理時間・意図しない変更・仕上がりのバランスを調整できる。

#### Acceptance Criteria

1. The 両スクリプト shall 任意の CLI 引数 `--complexity` を公開し、`low` / `medium` / `high` を受け付ける。対応する環境変数は `GPT_IMAGE_COMPLEXITY` とし、既定値は「未指定（API に送らない）」とする。
2. When `--complexity` が指定され、モデル種別が 2.5 系モデルであるとき、the 両スクリプト shall その値をリクエストに含める。
3. When `--complexity` が指定されていないとき、the 両スクリプト shall リクエストに complexity を含めない。
4. If モデル種別が `gpt-image-2` のときに `--complexity` が指定されたとき、then the 両スクリプト shall API を呼び出さずに、2.5 系モデル専用のパラメータである旨のエラーを返す。
5. If `--complexity` に `low` / `medium` / `high` 以外の値が指定されたとき、then the 両スクリプト shall API を呼び出さずにエラーを返す。
6. Where Requirement 9 の検証で Azure が complexity を受け付けないと確認されたとき、the 画像生成・編集スキル shall `--complexity` を無効化するか、`SKILL.md` に利用できない旨を記載する。

### Requirement 7: markup パラメータ（画像編集）

**Objective:** 2.5 系モデルで画像を編集する利用者として、編集箇所や内容を描き込んだ注釈画像（markup）で指示したい。それにより、マスクを作らなくても、編集位置を視覚的に伝えられる。

#### Acceptance Criteria

1. The 画像編集スクリプト shall 任意の CLI 引数 `--markup` を公開し、注釈を描いた透過 PNG のファイルパスを 1 つ受け付ける。
2. When `--markup` が指定され、モデル種別が 2.5 系モデルであるとき、the 画像編集スクリプト shall markup 画像をリクエストに含め、先頭の入力画像に対する注釈として送信する。
3. If `--markup` と `--mask` が同時に指定されたとき、then the 画像編集スクリプト shall API を呼び出さずに、両者は併用できない旨のエラーを返す。
4. If モデル種別が `gpt-image-2` のときに `--markup` が指定されたとき、then the 画像編集スクリプト shall API を呼び出さずに、2.5 系モデル専用のパラメータである旨のエラーを返す。
5. If `--markup` のファイルが存在しない、PNG でない、または 50MB を超えるとき、then the 画像編集スクリプト shall API を呼び出さずに、原因を含むエラーを返す。
6. If `--markup` の画像の寸法が先頭の入力画像の寸法と一致しないとき、then the 画像編集スクリプト shall API を呼び出さずに、両者の寸法を含むエラーを返す。
7. Where Requirement 9 の検証で Azure が markup を受け付けないと確認されたとき、the 画像生成・編集スキル shall `--markup` を無効化するか、`SKILL.md` に利用できない旨を記載する。

### Requirement 8: WebP 出力（Azure 検証後に有効化）

**Objective:** 2.5 系モデルの利用者として、WebP で出力したい。それにより、透過を保ったまま PNG よりファイルサイズを小さくできる。ただし Azure のドキュメントでは対応状況が矛盾しているため、実際に動作を確認できた場合に限って有効にする。

#### Acceptance Criteria

1. Where Requirement 9 の検証で Azure の 2.5 系モデルが WebP 出力に対応していると確認されたとき、the 両スクリプト shall モデル種別が 2.5 系モデルの場合に限り `--format webp` を受け付ける。
2. Where WebP 出力が有効なとき、the 両スクリプト shall `--compression` を `jpeg` と `webp` の両方で有効とし、`--background transparent` と `webp` の組み合わせを受け付ける。
3. Where WebP 出力が有効なとき、the 両スクリプト shall 保存するファイルの拡張子を `.webp` とする。
4. If `--format webp` が指定され、WebP 出力が有効になっていないか、モデル種別が `gpt-image-2` であるとき、then the 両スクリプト shall API を呼び出さずに、使える形式を示すエラーを返す。

### Requirement 9: Azure 未検証機能の検証

**Objective:** スキルの開発者として、Azure 未検証機能が Azure の実環境で使えるかどうかを、再現できる手順で確認したい。それにより、未確認の機能を利用者に公開してしまうことを防げる。

#### Acceptance Criteria

1. The 画像生成・編集スキル shall Azure 上の 2.5 系モデルのデプロイに対し、次の項目の可否を確認する検証手順（自動テストまたは手順書）を提供する: `quality=xhigh` / `max` / `auto`、`background=opaque` / `transparent`、`output_format=webp`、`complexity`、`markup`、および使用する api-version。
2. The 検証手順 shall 通常の自動テスト（モックを使う単体テスト）とは分けて、Azure の認証情報が設定されているときにだけ実行されるようにする。
3. When 検証手順を実行したとき、the 検証手順 shall 項目ごとに「受け付けられた／拒否された（HTTP ステータスとエラー内容）」を記録する。
4. The 画像生成・編集スキルの開発者 shall 検証結果を `research/` 配下に記録し、Requirement 6〜8 の有効・無効の判断の根拠とする。
5. If 既定の api-version（`2025-04-01-preview`）で 2.5 系の新しい値が拒否されると確認されたとき、then the 画像生成・編集スキル shall 新しい値が受け付けられる api-version またはエンドポイント形式で呼び出せるようにし、その設定方法を `SKILL.md` に記載する。

### Requirement 10: タイムアウト

**Objective:** 2.5 系モデル（特に Sunburst や高い quality）の利用者として、処理時間が長くなっても途中でタイムアウトしないでほしい。

#### Acceptance Criteria

1. While モデル種別が 2.5 系モデルであるとき、the 両スクリプト shall API 呼び出しのタイムアウトを 120 秒より長くする（OpenAI のドキュメントで、複雑なプロンプトの処理に最大 2 分かかるとされているため）。
2. When タイムアウトが発生したとき、the 両スクリプト shall 既存仕様と同じく、タイムアウトである旨とその秒数を表示し、非ゼロの終了コードで終了する。
3. While モデル種別が `gpt-image-2` であるとき、the 両スクリプト shall 既存のタイムアウト値を変えない。

### Requirement 11: 後方互換

**Objective:** 既存の `gpt-image-2` 利用者として、設定を何も変えずにこれまで通りスキルを使い続けたい。

#### Acceptance Criteria

1. When `GPT_IMAGE_MODEL` と `--model` のどちらも指定されていないとき、the 両スクリプト shall モデル種別を `gpt-image-2` として扱い、既存仕様と同じリクエスト内容・検証・既定値・出力で動作する。
2. While モデル種別が `gpt-image-2` であるとき、the 両スクリプト shall 本仕様で追加したパラメータ（`complexity`、`markup`）をリクエストに含めない。
3. The 両スクリプト shall 既存仕様の CLI 引数・環境変数・終了コード・標準出力の形式（保存したファイルの絶対パスを 1 行ずつ出力）を変えない。
4. The 画像生成・編集スキル shall 既存の自動テストを、本仕様の変更後もすべて成功させる。

### Requirement 12: ドキュメントとスキルの案内

**Objective:** Claude とスキル利用者として、モデルの選び方と新しいパラメータの使い方を `SKILL.md` などで確認したい。それにより、Claude が依頼に合ったモデルとパラメータを選べるようになる。

#### Acceptance Criteria

1. The 画像生成・編集スキル shall `SKILL.md` に、3 つのモデル種別の違い（Flare は速度重視、Sunburst は精度重視、gpt-image-2 は従来のモデル）と、モデルの指定方法（`--model`、`GPT_IMAGE_MODEL`、モデル種別ごとのデプロイ名の環境変数）を記載する。
2. The 画像生成・編集スキル shall `SKILL.md` のパラメータ表に、モデル種別ごとに使える値（`quality`、`background`、`format`）と、新しいパラメータ（`--model`、`--complexity`、`--markup`）を記載する。
3. The 画像生成・編集スキル shall `SKILL.md` に、Claude 向けの使い分けの指針（例: 試作や大量生成は Flare、細部の保持や最終成果物は Sunburst）を記載する。
4. The 画像生成・編集スキル shall `SKILL.md` の frontmatter の `description` に、2.5 系モデル（Sunburst / Flare）での生成・編集に対応していることを含める。
5. The 画像生成・編集スキル shall `.env.example` と README（英語版・日本語版）に、モデル種別とモデル種別ごとのデプロイ名の環境変数の設定例を追記する。
6. The 画像生成・編集スキル shall 設定値（エンドポイント・キー・デプロイ名の実値）を `SKILL.md` や README に書かない（既存仕様のセキュリティ方針を維持する）。
