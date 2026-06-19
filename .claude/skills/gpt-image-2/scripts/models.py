"""gpt-image-2 スキルの共通データ型。

API 詳細やシークレットを各層に散らさないよう、生成パラメータ・Azure 設定・
認証ヘッダを型として一元化する。デフォルト値は設計（design.md）に従い型に埋め込む。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Quality = Literal["low", "medium", "high"]
OutputFormat = Literal["png", "jpeg"]
Background = Literal["auto", "transparent"]


@dataclass(frozen=True)
class GenerationParams:
    """画像生成の入力パラメータ。必須は prompt のみ、他は推奨デフォルトを持つ。"""

    prompt: str
    size: str = "1024x1024"
    quality: Quality = "high"
    output_format: OutputFormat = "png"
    background: Background = "auto"
    output_compression: int = 100
    n: int = 1
    user: Optional[str] = None
    output_dir: str = "./images"


@dataclass(frozen=True)
class AzureConfig:
    """Azure OpenAI のエンドポイント・デプロイ名・API バージョン。"""

    endpoint: str
    deployment: str
    api_version: str = "2025-04-01-preview"


@dataclass(frozen=True)
class AuthHeader:
    """認証ヘッダ。value はシークレットを含むためログ出力してはならない。"""

    name: str   # "api-key" または "Authorization"
    value: str
