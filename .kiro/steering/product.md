# プロダクト概要

Claude Code から Azure AI Foundry（Microsoft Foundry）の画像モデル（`gpt-image-2`、`gpt-image-2.5-flare`、`gpt-image-2.5-sunburst`）を呼び出して画像を生成・編集する **Agent Skill** を提供するプロジェクト。ユーザーが Claude Code 上で「画像を生成して」「この画像を編集して／合成して」と依頼すると、スキルが自動的に読み込まれ、結果画像をローカルにファイルとして保存する。

> 実装済み（`.claude/skills/gpt-image/`）。初版は生成のみだったが、その後 **画像編集（images/edits）** と **`.env`／環境変数による既定値解決** を追加した。最新要件は `.kiro/specs/gpt-image-2-skill/` を参照。2.5 系（Flare / Sunburst）への対応は `.kiro/specs/gpt-image-2-5-support/` を参照。

## コア能力

- テキストプロンプトからの画像生成（Azure OpenAI `images/generations`）
- 既存画像の編集（`images/edits`）: 単一画像のプロンプト編集、複数画像のマージ（オブジェクト置換）、`mask` によるインペインティング
- `size` / `quality` / `output_format` / `background` / `output_compression` / `n` のパラメータ制御
- モデル種別の選択（`--model` / `GPT_IMAGE_MODEL`）とモデル種別ごとのデプロイの切り替え。2.5 系では `complexity` と markup（注釈画像）による編集指示も使える
- 結果画像（Base64）のデコードとローカル保存（プロンプト由来の一意なファイル名・連番対応）
- キーレス（Entra ID）と API キーの両認証経路に対応した安全な認証情報の受け渡し
- `.env`／環境変数（`GPT_IMAGE_*`）による既定値解決（優先順位: CLI 引数 > `.env` > 組み込み既定）

## 対象ユースケース

- Claude Code での対話中に、簡易な指示だけで画像を生成・編集・保存したい開発者
- 正方形 / 横長 / 縦長、透過 PNG、JPEG 圧縮などプリセット的な出力を素早く得たいケース
- アップロード済み画像の修正や、複数素材の合成（ベース画像のオブジェクトを別画像のものに置換）をしたいケース

対象外（将来拡張）: ストリーミング、バッチ／キュー処理、Web UI。

## 価値提案

中心となる設計方針は2点。

1. **モデル（Claude）に API を手書きさせない。** 画像生成・編集ロジックは自己完結したスクリプト（`generate_image.py` / `edit_image.py`）に閉じ込め、Claude は `SKILL.md` の手順どおりスクリプトを呼び出すだけにする。これにより再現性と安全性を担保する。
2. **パラメータは CLI 引数 + 妥当なデフォルト値で渡す。** 生成は `--prompt` のみ、編集は `--prompt` と最低 1 個の `--image` が必須。その他は検証付きの名前付き引数として公開し、未指定なら推奨デフォルト（`.env`／環境変数で上書き可）を適用する。Claude は差分だけを指定すればよい。

---
_パターンと目的にフォーカスし、機能の網羅列挙は避ける_
