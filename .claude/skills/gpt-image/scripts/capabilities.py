"""モデル種別ごとの対応表。

モデル種別によって異なる「使える値」「対応する機能」「タイムアウト」
「デプロイ名の環境変数」を、このモジュールだけで宣言する。他のモジュールは
ここを参照し、モデル名で分岐しない。環境変数は読まない（副作用なし）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from models import DEFAULT_MODEL, ModelName

Feature = Literal["complexity", "markup", "webp"]

MODEL_NAMES: tuple[ModelName, ...] = (
    "gpt-image-2",
    "gpt-image-2.5-flare",
    "gpt-image-2.5-sunburst",
)

# Azure での動作に合わせて切り替える機能フラグ。宣言上の対応に加えて、
# ここが True の機能だけが使える。利用者が誤って有効にしないよう、
# 環境変数では上書きできない。変更時は research/ の検証結果を根拠にする。
AZURE_ENABLED: dict[Feature, bool] = {
    # 2026-11-07 の実機確認で、Flare の deployments / v1 形式とも
    # 400 "Unknown parameter" で拒否された（research/azure-gpt-image-2.5-verification.md）
    "complexity": False,
    "markup": False,
    "webp": False,  # 実機確認がレート制限（429）で判定できていないため、引き続き無効
}

_DEPLOYMENT_ENV_PREFIX = "AZURE_OPENAI_DEPLOYMENT_"


@dataclass(frozen=True)
class ModelCapability:
    """モデル種別 1 つ分の対応内容。"""

    name: ModelName
    qualities: frozenset[str]
    backgrounds: frozenset[str]
    base_formats: frozenset[str]            # webp は機能フラグで追加する
    declared_features: frozenset[Feature]   # 公式ドキュメント上の対応
    experimental_pixels: Optional[int]      # これを超える総ピクセル数は experimental
    timeout_generate: float
    timeout_edit: float

    @property
    def deployment_env(self) -> str:
        """モデル種別ごとのデプロイ名の環境変数名（例: ..._GPT_IMAGE_2_5_FLARE）。"""
        suffix = self.name.upper().replace("-", "_").replace(".", "_")
        return _DEPLOYMENT_ENV_PREFIX + suffix


_GPT_IMAGE_2 = ModelCapability(
    name="gpt-image-2",
    qualities=frozenset({"low", "medium", "high"}),
    backgrounds=frozenset({"auto", "transparent"}),
    base_formats=frozenset({"png", "jpeg"}),
    declared_features=frozenset(),
    experimental_pixels=None,
    timeout_generate=120.0,
    timeout_edit=180.0,
)


def _gpt_image_2_5(name: ModelName) -> ModelCapability:
    return ModelCapability(
        name=name,
        qualities=frozenset({"low", "medium", "high", "xhigh", "max", "auto"}),
        backgrounds=frozenset({"auto", "opaque", "transparent"}),
        base_formats=frozenset({"png", "jpeg"}),
        declared_features=frozenset({"complexity", "markup", "webp"}),
        experimental_pixels=2560 * 1440,
        # 複雑なプロンプトでは最大 2 分かかるとされるため余裕を持たせる
        timeout_generate=300.0,
        timeout_edit=300.0,
    )


_CAPABILITIES: dict[str, ModelCapability] = {
    cap.name: cap
    for cap in (
        _GPT_IMAGE_2,
        _gpt_image_2_5("gpt-image-2.5-flare"),
        _gpt_image_2_5("gpt-image-2.5-sunburst"),
    )
}


def get_capability(model: str) -> ModelCapability:
    """モデル種別の対応内容を返す。未知のモデル種別は KeyError。"""
    return _CAPABILITIES[model]


def is_feature_enabled(cap: ModelCapability, feature: Feature) -> bool:
    """宣言上の対応があり、かつ機能フラグが有効なときだけ True。"""
    return feature in cap.declared_features and AZURE_ENABLED.get(feature, False)


def allowed_formats(cap: ModelCapability) -> frozenset[str]:
    """使える出力形式。"""
    if is_feature_enabled(cap, "webp"):
        return cap.base_formats | {"webp"}
    return cap.base_formats


def transparent_formats(cap: ModelCapability) -> frozenset[str]:
    """background=transparent と組み合わせられる出力形式。"""
    return frozenset({"png", "webp"}) & allowed_formats(cap)


def compression_formats(cap: ModelCapability) -> frozenset[str]:
    """output_compression が有効な出力形式。"""
    return frozenset({"jpeg", "webp"}) & allowed_formats(cap)


__all__ = [
    "AZURE_ENABLED",
    "DEFAULT_MODEL",
    "Feature",
    "MODEL_NAMES",
    "ModelCapability",
    "allowed_formats",
    "compression_formats",
    "get_capability",
    "is_feature_enabled",
    "transparent_formats",
]
