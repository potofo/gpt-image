# Research & Design Decisions

## Summary
- **Feature**: `gpt-image-2-skill`
- **Discovery Scope**: New Feature（グリーンフィールド・外部 API 統合）
- **Key Findings**:
  - Azure の画像生成 API には2系統のエンドポイントがある。デプロイ名ベース（`/openai/deployments/<name>/images/generations?api-version=<version>`）と、新しい v1 プレビュー（`/openai/v1/images/generations?api-version=preview`、`model` をボディで指定）。要件書はデプロイ名ベースを採用しており、これを正とする。
  - `gpt-image-2` は任意解像度をサポートし、size 制約（両辺 16px 倍数 / 長辺 ≤3840 / 比 ≤3:1 / 総ピクセル数 655,360〜8,294,400）が公式に確認できた。`quality`(low/medium/high, 既定 high)、`n`(1〜10, 既定 1)、`output_format`(PNG/JPEG, 既定 PNG、WEBP 非対応)、`output_compression`(0〜100, 既定 100)、`background`(auto/transparent, transparent は PNG 必須) も確認。
  - レスポンスは常に `data[].b64_json`（Base64）で返る。gpt-image 系は URL 返却ではなく Base64 固定。
  - **ドキュメントの表記揺れを確認**: 公式コードコメントは `background`/`output_format` を「GPT-image-1 only」と記す一方、本文は「GPT-image-1 と gpt-image-2 の両方がサポート」と記載。実装時に使用 `api-version` で実挙動の検証が必須。

## Research Log

### Azure gpt-image-2 画像生成 API の契約
- **Context**: Claude にハードコードさせず、スクリプトに API 呼び出しを閉じ込めるため、正確なエンドポイント・パラメータ・レスポンス構造を確定する必要があった。
- **Sources Consulted**:
  - Microsoft Learn「Azure OpenAI image generation models（dall-e how-to）」 https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/dall-e （ドキュメント更新日 2026-06-05）
- **Findings**:
  - 生成エンドポイント（デプロイ名ベース）: `POST https://<resource>.openai.azure.com/openai/deployments/<deployment>/images/generations?api-version=<version>`。`Content-Type: application/json`。
  - size 制約・各パラメータの取り得る値とデフォルトは要件書 §4.3 と完全一致。
  - レスポンス: `{ "data": [ { "b64_json": "<base64>" }, ... ] }`。
  - 認証: ヘッダ `api-key: <key>`、または Entra ID の `Authorization: Bearer <token>`。
- **Implications**: スクリプトはデプロイ名ベースのエンドポイントを構築し、Base64 を必ずデコードして保存する。`background`/`output_compression` の実効性は api-version 依存のため、検証ロジックとエラーメッセージで吸収する。

### 認証方式（キーレス優先）
- **Context**: 非機能要件 §5.1 が Entra ID キーレスを推奨し、API キーを代替とする。
- **Findings**: `azure-identity` の `DefaultAzureCredential` で `https://cognitiveservices.azure.com/.default` スコープのトークンを取得し `Authorization: Bearer` に設定。API キー方式はヘッダ `api-key`。
- **Implications**: 認証戦略を抽象化し、環境に応じて自動選択する（トークン取得可能なら Entra ID、なければ `AZURE_OPENAI_API_KEY`）。シークレットはログ出力しない。

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 単一スクリプト手続き型 | `generate_image.py` に全処理を直書き | 最小・依存少 | 検証/認証/HTTP が密結合でテスト困難 | 小規模だが検証分岐が多く不利 |
| **レイヤード（関数モジュール分割・選択）** | 検証 / 認証 / API クライアント / 保存 を関数単位で分離し CLI が統括 | 各関心事を単体テスト可能、責務明確 | ファイル数が少し増える | 受け入れ基準の検証要件と相性が良い |
| OOP クラス階層 | 各責務をクラス化 | 拡張余地大 | 初版スコープに対し過剰 | 将来 edits 拡張時に再検討 |

## Design Decisions

### Decision: 認証戦略の自動選択（Entra ID 優先・API キー代替）
- **Context**: §5.1 がキーレスを推奨しつつ API キーも許容。
- **Alternatives Considered**:
  1. API キーのみ — 実装は単純だが長期キー保存のリスク。
  2. Entra ID のみ — `az login`/Managed Identity 前提が厳しすぎる。
- **Selected Approach**: トークン取得を試行し、成功すれば Bearer 認証。失敗または未構成なら `AZURE_OPENAI_API_KEY` にフォールバック。両方不可なら明確なエラー。
- **Rationale**: 両認証経路をサポートする受け入れ基準を満たし、安全側（キーレス）を既定にできる。
- **Trade-offs**: 認証選択ロジックが必要だが、責務を `auth` モジュールに隔離して吸収。
- **Follow-up**: トークンスコープと api-version の実挙動を実機で検証。

### Decision: 検証を API 呼び出し前に集約（Fail Fast）
- **Context**: §4.2/§4.3 が事前検証を要求。
- **Selected Approach**: `validation` モジュールで size 制約・列挙値・依存関係（透過 PNG、圧縮 JPEG 限定）を検査し、違反は API 前に非ゼロ終了。
- **Rationale**: 無駄な API 呼び出しとコストを回避し、エラー原因を明確化。
- **Trade-offs**: 検証ルールの保守が必要だが要件と1:1対応で管理可能。

## Risks & Mitigations
- `background`/`output_compression` の api-version 依存挙動 — スクリプトで事前検証しつつ、API 由来の 400 は原因を `stderr` に明示。SKILL.md に「使用 api-version で要検証」と明記。
- シークレット漏えい — 環境変数のみ・直書き禁止・ログ非出力を設計と実装で徹底。例外メッセージにキーを含めない。
- レート制限(429) — 上限付き指数バックオフで吸収。
- 任意解像度の誤指定 — 4条件すべてを満たすかを数値検証し、違反項目を具体的にメッセージ化。

## References
- [Azure OpenAI image generation models (how-to/dall-e)](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/dall-e) — エンドポイント・パラメータ・レスポンス・認証の一次情報
- [GPT-image 系 limited access 登録](https://aka.ms/oai/access) — デプロイ前提
- [API キーの安全な取り扱い (Key Vault)](https://learn.microsoft.com/en-us/azure/key-vault/general/apps-api-keys-secrets) — シークレット管理
