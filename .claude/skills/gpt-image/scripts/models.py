"""gpt-image スキルの共通データ型。

API 詳細やシークレットを各層に散らさないよう、生成パラメータ・Azure 設定・
認証ヘッダを型として一元化する。デフォルト値は設計（design.md）に従い型に埋め込む。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

# モデル種別ごとに実際に使える値は capabilities.py の対応表が決める。
# ここでは全モデル種別の値の和集合を型として表す。
ModelName = Literal["gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]
Quality = Literal["low", "medium", "high", "xhigh", "max", "auto"]
OutputFormat = Literal["png", "jpeg", "webp"]
Background = Literal["auto", "opaque", "transparent"]
Complexity = Literal["low", "medium", "high"]
ApiStyle = Literal["deployments", "v1"]

DEFAULT_MODEL: ModelName = "gpt-image-2"
DEFAULT_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"


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
    model: ModelName = DEFAULT_MODEL
    complexity: Optional[Complexity] = None


@dataclass(frozen=True)
class EditParams:
    """画像編集（images/edits）の入力パラメータ。

    既存画像をプロンプトで修正する。images に複数画像を渡すと、それらを
    参照素材として合成（マージ）できる。先頭画像をベースとして扱い、mask を
    与えると mask の透過領域のみが編集対象となる（インペインティング）。
    size の既定は "auto"（入力画像に合わせる）。
    markup は注釈を描いた透過 PNG（2.5 系のみ、mask とは併用不可）。
    """

    prompt: str
    images: tuple[str, ...] = field(default_factory=tuple)  # 1枚以上の入力画像パス
    mask: Optional[str] = None                              # 任意: 編集領域を示す PNG マスク
    size: str = "auto"
    quality: Quality = "high"
    output_format: OutputFormat = "png"
    background: Background = "auto"
    output_compression: int = 100
    n: int = 1
    user: Optional[str] = None
    output_dir: str = "./images"
    model: ModelName = DEFAULT_MODEL
    complexity: Optional[Complexity] = None
    markup: Optional[str] = None                            # 任意: 注釈を描いた透過 PNG


@dataclass(frozen=True)
class AzureConfig:
    """Azure OpenAI のエンドポイント・デプロイ名・API バージョン・API 形式。"""

    endpoint: str
    deployment: str
    api_version: str = "2025-04-01-preview"
    api_style: ApiStyle = "deployments"
    token_scope: str = DEFAULT_TOKEN_SCOPE


@dataclass(frozen=True)
class AuthHeader:
    """認証ヘッダ。value はシークレットを含むためログ出力してはならない。"""

    name: str   # "api-key" または "Authorization"
    value: str
