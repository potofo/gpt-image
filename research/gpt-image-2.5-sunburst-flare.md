# GPT-Image-2.5-Sunburst / GPT-Image-2.5-Flare 調査レポート

- 調査日: 2026-11-07
- 目的: 既存の `gpt-image` スキル（Azure Foundry 上の `gpt-image-2` 前提）を `gpt-image-2.5-sunburst` / `gpt-image-2.5-flare` に対応させるため、新機能・パラメータの変更点・Azure 固有の制約を整理する。
- 情報源の信頼度表記: **[一次/OpenAI]** OpenAI 公式ドキュメント・API リファレンス、**[一次/Azure]** Microsoft Learn・Microsoft 公式ブログ、**[二次]** サードパーティの解説・再販業者。

---

## 1. エグゼクティブサマリー

| 項目 | 結論 |
|------|------|
| リリース | 2026-09-08（スナップショット `-2026-09-08`）。Azure Foundry でも同日付バージョンで **GA** |
| モデル ID | `gpt-image-2.5-sunburst` / `gpt-image-2.5-flare`。**`gpt-image-2.5` 単体の ID は存在しない**（model not found） |
| 位置付け | **Sunburst** = 最高品質・編集精度重視（遅い）。**Flare** = 高速・日常用途の既定（gpt-image-2 より高品質かつ約 50% 低レイテンシ） |
| 主な新機能 | `quality` に **`xhigh` / `max`** 追加、`quality` 既定が **`auto`**、**`background: opaque/transparent` を正式サポート**（gpt-image-2 では透過はプレビュー）、**`complexity`**（計画量）、**`markup`**（手書き注釈による編集指示）、WebP 出力 |
| サイズ制約 | gpt-image-2 とほぼ同じ（16px 倍数・最大 3840x2160・総ピクセル 655,360〜8,294,400）。**アスペクト比の下限 1:3 が明記**、**2560x1440 超は experimental** |
| 料金 | トークン単価は gpt-image-2 と同一（画像出力 $30/1M、画像入力 $8/1M、テキスト入力 $5/1M）。ただし品質ごとの消費トークンが異なる |
| Azure 上の差分 | 生成・編集エンドポイント、quality 6 段階、サイズ制約、n=1〜10 は Microsoft Learn で確認済み。**`complexity` / `markup` / WebP / ストリーミング / API バージョン**は Azure ドキュメントに 2.5 向けの記述がなく **実機検証が必要** |
| スキル対応の要点 | `VALID_QUALITY` に `xhigh`/`max`/`auto` 追加、既定値見直し、`background=opaque` 追加、2560x1440 超の experimental 警告、（Azure 対応確認後に）`--complexity` / `--markup` / WebP |

---

## 2. モデル概要

### 2.1 2 つのバリアント

| | GPT-Image-2.5-Sunburst | GPT-Image-2.5-Flare |
|---|---|---|
| OpenAI の説明 | 編集精度が最も重要な場面向けの最上位モデル | "our fastest model for high-quality, everyday image generation" |
| Azure の説明 | "Most capable model for image generation and editing; best when editing precision matters most" / 最高忠実度 | "Fastest model for high-quality, everyday image generation" / 速度とコストに最適化 |
| 速度 | 遅い（精度優先） | 速い。gpt-image-2 比 **約 50% 低レイテンシ**（OpenAI・Microsoft 発表） |
| 推奨用途 | 最終成果物、細部の保持、長い編集チェーン、商品画像・キャンペーン素材 | 大量生成、ラフ案、マーケ素材、通常の本番ワークロード |
| スナップショット | `gpt-image-2.5-sunburst-2026-09-08` | `gpt-image-2.5-flare-2026-09-08` |

推奨ワークフロー（[二次] Luma AI）: **Flare で方向性を探索 → 採用案を Sunburst で仕上げる**。

### 2.2 ベンチマーク（参考）

- Arena Image Edit リーダーボード（2026-09-09 時点）: Sunburst **1520**、Flare **1491**（[二次] 検索結果より。一次ソース未確認）。

### 2.3 モダリティとエンドポイント [一次/OpenAI]

- 入力: テキスト・画像 / 出力: 画像のみ
- 対応エンドポイント: `v1/images/generations`、`v1/images/edits`、`v1/batch`
- 機能: Inpainting
- Responses API の image generation ツール: **ドキュメント間で記述が矛盾**。モデルページでは Responses は「非対応」とされる一方、画像生成ガイドや一部の解説では Responses の `image_generation` ツールから利用可能とされる。本スキルは Images API のみを使うため影響はない。

### 2.4 後継・関連モデル

- **GPT Image 2.6**（`gpt-image-2.6-sunburst` / `gpt-image-2.6-flare`）が 2026-11 上旬に OpenAI API に追加された（OpenAI の API リファレンスの model enum に記載。リリース日 2026-11-04 は [二次]）。GIF 出力・markup・SVG・complexity などとあわせて紹介されている。
- **Azure Foundry のモデル一覧（2026-10-29 更新）には 2.6 は未掲載**。Azure で使えるのは現時点では 2.5 まで。
- `gpt-image-1` は 2026-10-23 に OpenAI API で提供終了。OpenAI は移行先として 2.5 を案内している。

---

## 3. パラメータ変更点（gpt-image-2 → gpt-image-2.5）

### 3.1 比較表

| パラメータ | gpt-image-2（現行スキル） | gpt-image-2.5 Sunburst/Flare | 出典・確度 |
|---|---|---|---|
| `model` | `gpt-image-2` | `gpt-image-2.5-sunburst` / `gpt-image-2.5-flare`（+ `-2026-09-08`） | 一次（OpenAI/Azure） |
| `prompt` 長 | Azure: 4,000 文字 | **Azure: 4,000 文字**（OpenAI は 32,000 文字） | 一次（Azure モデル一覧） |
| `quality` | `low` / `medium` / `high` | **`low` / `medium` / `high` / `xhigh` / `max` / `auto`**。**既定 `auto`** | 一次（OpenAI/Azure） |
| `size` | 任意 `WxH`、16 倍数、長辺 ≤3840、比 ≤3:1、総ピクセル 655,360〜8,294,400 | 同上 ＋ **比は 1:3〜3:1**、**最大 3840x2160**、**2560x1440 超は experimental**、`auto` 可 | 一次（OpenAI/Azure） |
| `background` | `transparent` は **プレビュー**扱い（OpenAI）。Azure の旧リファレンスでは「gpt-image-1 のみ」 | **`opaque` / `transparent` を正式サポート**、既定 `auto` | 一次（OpenAI）。Azure は未明記 |
| `output_format` | `png` / `jpeg`（Azure は WEBP 非対応と記載） | OpenAI: `png` / `jpeg` / `webp`（+ `gif`/`svg` はプレビュー・限定アクセス） | OpenAI は一次。**Azure は記述が矛盾**（後述） |
| `output_compression` | 0〜100（JPEG のみ） | 0〜100（**JPEG と WebP**） | 一次（OpenAI） |
| `n` | 1〜10 | 1〜10 | 一次（Azure） |
| `complexity` | なし | **新規** `low` / `medium` / `high`。省略時 `high` | 一次（OpenAI）。Azure 未記載 |
| `markup`（edits） | なし | **新規**。注釈を描いた透過 PNG を先頭画像に重ねて編集位置・内容を指示。`mask` と併用不可 | 一次（OpenAI）。Azure 未記載 |
| `mask`（edits） | PNG・アルファ付き・先頭画像と同サイズ | 同じ（`markup` とは排他） | 一次 |
| 入力画像数（edits） | 最大 16 | 最大 16 | 一次 |
| `input_fidelity` | gpt-image-2 では指定不可（省略必須） | **ドキュメントに記載なし** → 送らないのが安全 | 一次（記載なし） |
| `moderation` | `auto` / `low` | `auto` / `low` | 一次（OpenAI） |
| `stream` / `partial_images` | 0〜3（Azure は gpt-image-2 までを明記） | 0〜3（OpenAI）。partial 1 枚につき +100 出力トークン | OpenAI は一次。Azure 未記載 |
| `user` | 任意 | OpenAI では **非推奨**。後継は `safety_identifier`（128 文字以下） | 一次（OpenAI）。Azure は未確認 |
| 応答 | `data[].b64_json` | 同じ（URL 返却なし）。`quality`・`size`・`background`・`output_format`・`usage` も返る | 一次（OpenAI） |
| 顔の保持 | Azure 表で ✅（Advanced face preservation） | Azure 表では空欄 | 一次（Azure） |

### 3.2 `quality`（xhigh / max / auto）

- 「`gpt-image-2.5-sunburst` と `gpt-image-2.5-flare` は `xhigh` と `max` の品質設定を追加する。どちらも既定は `auto`。以前の GPT Image モデルは `high` まで」[一次/OpenAI]
- **2.5 の `high` が消費するトークンは、gpt-image-2 の `medium` とほぼ同じ**（[二次] apidog）。品質名だけを見て、2.5 の `high` を gpt-image-2 の `high` と同じものとみなさないこと。
- 品質を上げても毎回良くなるとは限らない。「要件を安定して満たす最低の設定」を選ぶのがよい（[二次] Luma）。

**1 枚あたりの出力トークン・概算コスト**（[二次] apidog。画像出力 $30/1M で計算）:

| quality | 1024x1024 | 1536x1024 |
|---|---|---|
| low | 196 tok（$0.0059） | 158 tok（$0.0047） |
| medium | 439 tok（$0.0132） | 343 tok（$0.0103） |
| high | 1,756 tok（$0.0527） | 1,372 tok（$0.0412） |
| xhigh | 3,122 tok（$0.0937） | 2,459 tok（$0.0738） |
| max | 7,024 tok（$0.2107） | 5,488 tok（$0.1646） |

> 注: OpenAI は「トークン単価は同じでも 1 枚あたりのコストはモデル・品質で異なる」「GPT Image 2 の計算機は 2.5 のトークン数を見積もれない」と明言している。正確なコストはレスポンスの `usage` で確認すること。

### 3.3 `size`

- 推奨: `1024x1024`、`1536x1024`、`1024x1536`
- カスタム `WIDTHxHEIGHT` の条件 [一次/OpenAI・Azure]:
  - 両辺が 16px の倍数
  - アスペクト比 **1:3〜3:1**
  - どちらの辺も 3,840px 以下（OpenAI リファレンスでは最大 3840x2160）
  - 総ピクセル数 655,360〜8,294,400
  - **2560x1440 を超える解像度は experimental**
- 解説記事で紹介されているサイズ例（[二次]）: 2048x2048、2048x1152、3840x2160、2160x3840
- 現行スキルの `_validate_size` は「長辺/短辺 ≤ 3」で判定しており、これは 1:3〜3:1 と同じ意味なので、条件として欠けているものはない。ただし OpenAI では「最大 3840x2160」とされているため、**3840x3840 のような正方形の 4K（総ピクセル 14.7M）は総ピクセル上限で既に弾かれる**ことを確認した。

### 3.4 `complexity`（新規）

- 「画像モデルがレンダリング前にどれだけ計画するか」を制御する。レンダリング品質（`quality`）とは別の軸 [一次/OpenAI]
- 値: `low` / `medium` / `high`。**省略時は `high`**
- 追加料金なし。ただし「複雑度を上げるとレイテンシが増え、意図しない変更が入ることもある」
- SVG 出力では参照画像の生成に作用する
- ガイドでは「GPT Image 2.6」のセクションに書かれている一方、API リファレンスでは 2.5 を含むモデル共通のパラメータとして載っており、**2.5 で有効かどうかは記述が曖昧**。Azure での受け付けも未確認

### 3.5 `markup`（新規・edits のみ）

- 先頭の入力画像に、**描き込みの入った透過 PNG を重ね**、編集箇所と内容を視覚的に指示する機能 [一次/OpenAI]
- 制約:
  - **`mask` と併用不可**
  - 先頭画像と同じ寸法（向き補正後）で、透過ピクセルを含むこと
  - 先頭画像と markup はそれぞれ最大 **16,777,216 ピクセル**、注釈ファイルは **50MB 以下**
  - 2 枚目以降の入力画像は参照画像として扱われる
  - Images API のみ（Responses API では使えない）。追加料金なし
- 対象: OpenAI リファレンスでは 2.5 と 2.6 の両方に対応と記載
- Azure: **記載なし**

### 3.6 出力形式（WebP / GIF / SVG）

- OpenAI [一次]:
  - `png`（既定）/ `jpeg` / `webp`。JPEG がもっとも速い
  - 透過は `png` か `webp` が必須
  - `gif`: `frame_count` 2〜16（既定 9）、`frame_duration_ms` 最小 20（既定 200）。GIF プレビューへのアクセスが必要。ストリーミング・mask・compression は使えない
  - `svg`: `n=1` が必須。ストリーミング・partial・compression は使えない。`svg` オブジェクト（author モデル・reasoning effort）が必要で、限定アクセス。edits の SVG はガイドでは非対応、リファレンスでは enum に含まれており、記述が矛盾している
- **Azure の WebP 対応は記述が矛盾している**:
  - how-to ガイド: 「WEBP images aren't supported」
  - v1 preview REST リファレンス（2026-05 版）: `output_format` の enum に `webp` が含まれる。ただし注記は「gpt-image-1 系のみ」
  - → **2.5 では実機で確認するまで WebP は使えないものとして扱う**のが安全
- GIF / SVG は OpenAI でもプレビュー・限定アクセスで、Azure には記述がないため **対象外**とする

### 3.7 その他

- `moderation`: `auto`（既定）/ `low`。拒否時は `error.code = "moderation_blocked"` で、`moderation_details.moderation_stage`（`input` / `output` / `unknown`）が付くことがある [一次/OpenAI]
- レイテンシ: 「複雑なプロンプトでは最大 2 分かかることがある」→ **クライアントのタイムアウトは 120 秒より長くする**
- 生成による編集はピクセル単位で元画像を保たない。保持したい領域がある場合は、従来の合成のほうが安全なこともある（[二次] Luma）

---

## 4. Azure (Microsoft Foundry) 固有情報

### 4.1 提供状況 [一次/Azure]

| 項目 | 内容 |
|---|---|
| ステータス | **Generally Available** |
| バージョン | `2026-09-08`（flare / sunburst とも） |
| デプロイ種別 | リージョン可用性表では Global Standard 系の列に ✅（gpt-image-2 と同じ列）。Flare は別の表（Data Zone 系とみられる）にも ✅ がある → **リージョンとデプロイ種別は Foundry ポータルで要確認** |
| プロンプト上限 | 4,000 文字 |
| アクセス申請 | gpt-image-1 / 1.5 と違い、**limited access のリンクが付いていない**（GA 表記から推測。要確認） |
| 料金（Microsoft ブログ、1M トークンあたり） | 画像入力 $8 / キャッシュ $2 / 出力 $30、テキスト入力 $5 / キャッシュ $1.25。詳細は Foundry の価格ページで今後公開予定 |
| クォータ | how-to のクォータ表には gpt-image-1 系と gpt-image-2（5 枚/分）しかなく、**2.5 は未記載** |

### 4.2 エンドポイントと API バージョン

- 現行スキルの形式: `POST {endpoint}/openai/deployments/{deployment}/images/{generations|edits}?api-version=2025-04-01-preview`
- Azure の v1 形式: `POST {endpoint}/openai/v1/images/generations?api-version=preview`（`model` にデプロイ名を入れる）
- **2.5 で必要な api-version は Azure ドキュメントに明記がない**。既存の `2025-04-01-preview` のまま `quality=xhigh` などの新しい値を受け付けるかは不明。v1（`/openai/v1/...`）では新しいパラメータが先に入る傾向がある
- 現在公開されている Azure の REST リファレンス（v1 preview、2026-05-19 版）は 2.5 のリリースより前のもので、`quality` の enum に `xhigh`/`max` はなく、`complexity`/`markup` も載っていない

### 4.3 Azure で未確認の項目（実機検証が必要）

1. `quality=xhigh` / `max` / `auto` が `2025-04-01-preview` で通るか（通らなければ v1 への切り替えが必要）
2. `background=opaque` / `transparent` の挙動
3. `output_format=webp` の可否
4. `complexity` を受け付けるか
5. `markup` を受け付けるか（multipart のフィールド名を含めて）
6. `stream` / `partial_images` の可否
7. `user` と `safety_identifier` のどちらを使うべきか
8. 2.5 のクォータ（IPM）とリージョン

---

## 5. 既存 `gpt-image` スキルへの影響と対応方針

### 5.1 影響箇所

| ファイル | 現状 | 必要な変更 |
|---|---|---|
| [validation.py](../.claude/skills/gpt-image/scripts/validation.py) | `VALID_QUALITY = {"low","medium","high"}` | `xhigh` / `max` / `auto` を追加（モデルごとに許可値を切り替えるのが理想） |
| 同上 | `VALID_BACKGROUND = {"auto","transparent"}` | `opaque` を追加 |
| 同上 | `VALID_FORMAT = {"png","jpeg"}`、エラー文に「WEBP は Azure 非対応」 | Azure での WebP 検証後に `webp` を追加し、透過・compression の依存関係を `png`/`webp` と `jpeg`/`webp` に広げる |
| 同上 | アスペクト比の上限チェックのみ | 判定は既に対称（長辺/短辺）なので変更不要。2560x1440 超で「experimental」の警告を出すと親切 |
| [client.py](../.claude/skills/gpt-image/scripts/client.py) | deployments 形式の URL、`2025-04-01-preview` | 新しい値が通らなければ v1 形式（`/openai/v1/images/...` + `model`）への対応を検討。タイムアウトは 120 秒超にする |
| [models.py](../.claude/skills/gpt-image/scripts/models.py) | — | `complexity`、`markup`（edit）のフィールドを追加 |
| [edit_image.py](../.claude/skills/gpt-image/scripts/edit_image.py) | `--mask` | `--markup` を追加（`--mask` と排他） |
| [generate_image.py](../.claude/skills/gpt-image/scripts/generate_image.py) | — | `--complexity` を追加 |
| [SKILL.md](../.claude/skills/gpt-image/SKILL.md) | gpt-image-2 前提の説明・パラメータ表 | 2.5 の 2 モデルの使い分け、新しいパラメータ、既定値を追記 |
| `.env.example` | `AZURE_OPENAI_DEPLOYMENT=gpt-image-2` | 2.5 のデプロイ例を追加。モデルの種類を判別する設定（例: `GPT_IMAGE_MODEL_FAMILY`）を検討 |

### 5.2 設計上の論点

1. **モデルの判別方法**: Azure ではデプロイ名が任意なので、デプロイ名からモデルを確実に推測することはできない。案は次の 2 つ。
   - 案 A: 新しい環境変数（例: `GPT_IMAGE_MODEL=gpt-image-2.5-flare`）でモデルの種類を明示し、許可する値をそれに合わせて切り替える
   - 案 B: クライアント側の enum チェックを緩め（品質値の追加のみ）、未対応の値は API の 400 エラーに任せる
   - **推奨: 案 A**。gpt-image-2 のデプロイで `xhigh` を送るといった誤りを、API 呼び出し前に止められる（既存の Fail Fast 方針とも一致する）
2. **既定の quality**: 現行の既定 `high` を 2.5 でも使うと、2.5 の `high` は gpt-image-2 の `medium` 相当のトークン量になる。API 側の既定に合わせて `auto` にするか、明示的に `high` のままにするかを決める必要がある
3. **Flare と Sunburst の切り替え**: 両方をデプロイし、CLI 引数（例: `--variant sunburst`）でデプロイ先を切り替える形にすると、SKILL.md で「ラフは Flare、仕上げは Sunburst」と案内しやすい
4. **後方互換**: gpt-image-2 のデプロイでもそのまま動くよう、既定の挙動は変えない

### 5.3 推奨する進め方

1. Azure 上に 2.5-flare と 2.5-sunburst をデプロイし、**§4.3 の検証項目をスモークテストで確認する**（`2025-04-01-preview` と v1 の両方で）
2. 結果をこのレポートに追記する
3. `/kiro:spec-requirements` で 2.5 対応の要件を追加し、設計 → タスク → 実装の順で進める

---

## 6. 情報の矛盾・不確実な点

| 論点 | 内容 |
|---|---|
| Responses API 対応 | OpenAI のモデルページでは「非対応」、ガイドと二次情報では「対応」 |
| `complexity` の対象 | ガイドでは 2.6 のセクションに記載、リファレンスでは 2.5 を含む共通パラメータ |
| Azure の WebP | how-to では「非対応」、REST リファレンスでは enum に含まれる（ただし 2.5 より前の版） |
| `xhigh`/`max` の 2.6 対応 | edits のリファレンスでは 2.5 のみに記載 |
| SVG の edits | ガイドでは非対応、リファレンスでは enum に含まれる |
| 料金 | OpenRouter では入力 $8/1M と記載（画像入力の単価と混同している可能性あり） |
| リリース日 | 9/8 と 9/9 の 2 説。スナップショット名から **9/8** を採用 |

---

## 7. 参考資料

### 一次情報（OpenAI）
- [GPT-Image-2.5 Sunburst Model](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)
- [GPT-Image-2.5 Flare Model](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare)
- [Image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- [API Reference: Create image](https://developers.openai.com/api/reference/resources/images/methods/generate)
- [API Reference: Create image edit](https://developers.openai.com/api/reference/resources/images/methods/edit)
- [Introducing ChatGPT Images 2.5](https://openai.com/index/introducing-chatgpt-images-2-5/)（403 で本文を取得できず、内容は他ソース経由）

### 一次情報（Microsoft / Azure）
- [How to Use Image Generation Models from OpenAI - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/dall-e)
- [Foundry Models sold by Azure](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure)
- [Region availability for Foundry Models sold by Azure](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability)
- [Azure OpenAI image, audio, and video REST API reference (v1 preview)](https://learn.microsoft.com/en-us/azure/foundry/openai/reference-preview-latest)
- [Create multimodal applications with OpenAI models in Microsoft Foundry](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/create-multimodal-applications-with-openai-models-in-microsoft-foundry/4543593)
- [gpt-image-2.5-sunburst（Foundry カタログ）](https://ai.azure.com/catalog/models/gpt-image-2.5-sunburst)

### 二次情報
- [GPT Image 2.5 Sunburst & Flare Complete Guide - Luma AI](https://lumalabs.ai/learning-center/articles/gpt-image-2-5-sunburst-and-flare-complete-guide)
- [How to use the gpt-image-2.5 API (Flare and Sunburst) - Apidog](https://apidog.com/blog/gpt-image-2-5-api/)
- [GPT Image 2.5 API: Flare vs Sunburst, Pricing, Specs - Atlas Cloud](https://www.atlascloud.ai/models/gpt-image-2.5)
- [OpenAI: GPT Image 2.5 Flare - OpenRouter](https://openrouter.ai/openai/gpt-image-2.5-flare)
- [GPT Image 2.6 launch - API易](https://docs.apiyi.com/news/gpt-image-2-6-launch.md)
