"""パラメータ検証（Fail Fast）。

API 呼び出し前に、size 制約・列挙値・パラメータ依存関係を検査する。
違反は具体的な原因メッセージとともに ValidationError を送出する。
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Union

from capabilities import (
    MODEL_NAMES,
    ModelCapability,
    allowed_formats,
    compression_formats,
    get_capability,
    is_feature_enabled,
    transparent_formats,
)
from image_info import read_dimensions
from models import DEFAULT_MODEL, EditParams, GenerationParams

Params = Union[GenerationParams, EditParams]

# gpt-image-2 / 2.5 系共通の size 制約
SIZE_MULTIPLE = 16
MAX_LONG_EDGE = 3840
MAX_ASPECT_RATIO = 3.0
MIN_TOTAL_PIXELS = 655_360
MAX_TOTAL_PIXELS = 8_294_400

# gpt-image-2 の許可値（モデル種別ごとの許可値は capabilities.py の対応表を参照）
VALID_QUALITY = {"low", "medium", "high"}
VALID_FORMAT = {"png", "jpeg"}
VALID_BACKGROUND = {"auto", "transparent"}
VALID_COMPLEXITY = {"low", "medium", "high"}
MIN_N = 1
MAX_N = 10
MIN_COMPRESSION = 0
MAX_COMPRESSION = 100
DEFAULT_COMPRESSION = 100

# 画像編集（images/edits）の制約
MIN_INPUT_IMAGES = 1
MAX_INPUT_IMAGES = 16
# 入力画像として受け付ける拡張子（API が受け付ける形式）
VALID_INPUT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
# size に "auto"（入力画像に合わせる）を許可する
AUTO_SIZE = "auto"
# markup（注釈画像）のファイルサイズ上限
MAX_MARKUP_BYTES = 50 * 1024 * 1024


class ValidationError(Exception):
    """パラメータが制約に違反している場合に送出する。"""


def _parse_size(size: str) -> tuple[int, int]:
    parts = size.lower().split("x")
    if len(parts) != 2:
        raise ValidationError(
            f"size '{size}' は 'WxH' 形式で指定してください（例: 1024x1024）。"
        )
    try:
        width, height = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValidationError(
            f"size '{size}' の幅・高さは整数で指定してください（例: 1536x1024）。"
        )
    if width <= 0 or height <= 0:
        raise ValidationError(f"size '{size}' の幅・高さは正の整数である必要があります。")
    return width, height


def _validate_size(size: str) -> None:
    width, height = _parse_size(size)

    if width % SIZE_MULTIPLE or height % SIZE_MULTIPLE:
        raise ValidationError(
            f"size '{size}' の両辺は {SIZE_MULTIPLE}px の倍数である必要があります。"
        )

    long_edge = max(width, height)
    if long_edge > MAX_LONG_EDGE:
        raise ValidationError(
            f"size '{size}' の長辺 {long_edge}px は上限 {MAX_LONG_EDGE}px を超えています。"
        )

    aspect = long_edge / min(width, height)
    if aspect > MAX_ASPECT_RATIO + 1e-9:
        raise ValidationError(
            f"size '{size}' のアスペクト比 {aspect:.2f} は上限 3:1 を超えています。"
        )

    total = width * height
    if total < MIN_TOTAL_PIXELS or total > MAX_TOTAL_PIXELS:
        raise ValidationError(
            f"size '{size}' の総ピクセル数 {total:,} は許容範囲 "
            f"{MIN_TOTAL_PIXELS:,}〜{MAX_TOTAL_PIXELS:,} 外です。"
        )


def _capability(params: Params) -> ModelCapability:
    try:
        return get_capability(params.model)
    except KeyError:
        raise ValidationError(
            f"モデル種別 '{params.model}' は無効です。{list(MODEL_NAMES)} のいずれかを指定してください。"
        )


def _is_2_5_only(field: str, value: str) -> bool:
    """value が gpt-image-2 では使えず、2.5 系でのみ使える値かどうか。"""
    allowed_in_2_5 = getattr(get_capability("gpt-image-2.5-flare"), field)
    return value in allowed_in_2_5


def _invalid_value_message(cap: ModelCapability, label: str, value: str,
                           allowed: frozenset[str], field: str) -> str:
    """許可値外の値のエラー文。gpt-image-2 では既存の文言を保ち、2.5 系専用値なら案内を足す。"""
    if cap.name == DEFAULT_MODEL:
        message = f"{label} '{value}' は無効です。{sorted(allowed)} のいずれかを指定してください。"
        if _is_2_5_only(field, value):
            message += f"（'{value}' は 2.5 系モデルでのみ使えます。--model で指定してください）"
        return message
    return (
        f"{label} '{value}' はモデル種別 {cap.name} では無効です。"
        f"{sorted(allowed)} のいずれかを指定してください。"
    )


def _unavailable_message(label: str) -> str:
    return (
        f"{label} は Azure では現在利用できません（Azure での動作を確認できていないため無効化しています。"
        "SKILL.md の「使える機能」を参照してください）。"
    )


def _validate_format(cap: ModelCapability, output_format: str) -> None:
    allowed = allowed_formats(cap)
    if output_format in allowed:
        return
    if output_format == "webp" and "webp" in cap.declared_features:
        raise ValidationError(
            _unavailable_message("format 'webp'")
            + f" {sorted(allowed)} のいずれかを指定してください。"
        )
    if cap.name == DEFAULT_MODEL:
        raise ValidationError(
            f"format '{output_format}' は無効です。{sorted(allowed)} のいずれかを指定してください"
            "（WEBP は Azure 非対応）。"
        )
    raise ValidationError(
        f"format '{output_format}' はモデル種別 {cap.name} では無効です。"
        f"{sorted(allowed)} のいずれかを指定してください。"
    )


def _validate_complexity(cap: ModelCapability, complexity) -> None:
    if complexity is None:
        return
    if complexity not in VALID_COMPLEXITY:
        raise ValidationError(
            f"complexity '{complexity}' は無効です。{sorted(VALID_COMPLEXITY)} のいずれかを指定してください。"
        )
    if "complexity" not in cap.declared_features:
        raise ValidationError(
            f"complexity は 2.5 系モデル専用のパラメータです（モデル種別: {cap.name}）。"
            "--model で 2.5 系モデルを指定してください。"
        )
    if not is_feature_enabled(cap, "complexity"):
        raise ValidationError(_unavailable_message("complexity"))


def _validate_enums(params: Params) -> ModelCapability:
    """列挙値・範囲を検証し、モデル種別の対応内容を返す。"""
    if not params.prompt or not params.prompt.strip():
        raise ValidationError("prompt は必須です。生成内容を指定してください。")
    cap = _capability(params)
    if params.quality not in cap.qualities:
        raise ValidationError(
            _invalid_value_message(cap, "quality", params.quality, cap.qualities, "qualities")
        )
    _validate_format(cap, params.output_format)
    if params.background not in cap.backgrounds:
        raise ValidationError(
            _invalid_value_message(cap, "background", params.background, cap.backgrounds, "backgrounds")
        )
    if not (MIN_N <= params.n <= MAX_N):
        raise ValidationError(f"n は {MIN_N}〜{MAX_N} の範囲で指定してください（指定値: {params.n}）。")
    _validate_complexity(cap, params.complexity)
    return cap


def _validate_dependencies(params: Params, cap: ModelCapability) -> Params:
    """依存関係を検証し、必要なら正規化済みパラメータを返す。"""
    transparent_ok = transparent_formats(cap)
    if params.background == "transparent" and params.output_format not in transparent_ok:
        raise ValidationError(
            f"background=transparent を使う場合は format={'/'.join(sorted(transparent_ok))} が必須です"
            f"（指定された format: {params.output_format}）。"
        )

    compressible = compression_formats(cap)
    if params.output_format in compressible:
        if not (MIN_COMPRESSION <= params.output_compression <= MAX_COMPRESSION):
            raise ValidationError(
                f"compression は {MIN_COMPRESSION}〜{MAX_COMPRESSION} の範囲で指定してください"
                f"（指定値: {params.output_compression}）。"
            )
        return params

    # 圧縮に対応しない形式のとき: compression は無効。明示指定があれば警告して既定値へ正規化する。
    if params.output_compression != DEFAULT_COMPRESSION:
        print(
            f"警告: compression は format={'/'.join(sorted(compressible))} のときのみ有効です。"
            f"format={params.output_format} のため compression を無視します。",
            file=sys.stderr,
        )
        return replace(params, output_compression=DEFAULT_COMPRESSION)
    return params


def _warn_if_experimental(size: str, cap: ModelCapability) -> None:
    """2.5 系で experimental とされる解像度なら警告する（処理は続ける）。"""
    if cap.experimental_pixels is None:
        return
    width, height = _parse_size(size)
    if width * height > cap.experimental_pixels:
        print(
            f"警告: size '{size}' は 2560x1440 を超えるため、{cap.name} では experimental な解像度です。"
            "仕上がりが安定しない場合があります。",
            file=sys.stderr,
        )


def validate_params(params: GenerationParams) -> GenerationParams:
    """すべての制約を検証し、正規化済みパラメータを返す。違反時は ValidationError。"""
    cap = _validate_enums(params)
    _validate_size(params.size)
    _warn_if_experimental(params.size, cap)
    return _validate_dependencies(params, cap)


def _validate_input_image(path: str, *, role: str = "画像") -> None:
    """入力画像（または mask）パスの存在・種別・拡張子を検証する。"""
    if not path or not path.strip():
        raise ValidationError(f"{role}のパスが空です。")
    p = Path(path).expanduser()
    if not p.exists():
        raise ValidationError(f"{role}が見つかりません: {path}")
    if not p.is_file():
        raise ValidationError(f"{role}はファイルである必要があります: {path}")
    if p.suffix.lower() not in VALID_INPUT_EXTENSIONS:
        raise ValidationError(
            f"{role}の形式 '{p.suffix}' は非対応です。"
            f"{sorted(VALID_INPUT_EXTENSIONS)} のいずれかを指定してください: {path}"
        )


def _validate_markup(params: EditParams, cap: ModelCapability) -> None:
    """markup の排他・対応・ファイル・寸法を検証する。寸法が読めない場合は警告して続行。"""
    if params.markup is None:
        return
    if params.mask is not None:
        raise ValidationError("markup と mask は併用できません。どちらか一方を指定してください。")
    if "markup" not in cap.declared_features:
        raise ValidationError(
            f"markup は 2.5 系モデル専用のパラメータです（モデル種別: {cap.name}）。"
            "--model で 2.5 系モデルを指定してください。"
        )
    if not is_feature_enabled(cap, "markup"):
        raise ValidationError(_unavailable_message("markup"))

    _validate_input_image(params.markup, role="markup 画像")
    markup_path = Path(params.markup).expanduser()
    if markup_path.suffix.lower() != ".png":
        raise ValidationError(f"markup 画像は透過 PNG である必要があります: {params.markup}")
    if markup_path.stat().st_size > MAX_MARKUP_BYTES:
        raise ValidationError(
            f"markup 画像が上限（50MB）を超えています: {params.markup}"
        )

    base_dims = read_dimensions(str(Path(params.images[0]).expanduser()))
    markup_dims = read_dimensions(str(markup_path))
    if base_dims is None or markup_dims is None:
        print(
            "警告: 入力画像または markup 画像の寸法を読み取れなかったため、寸法の一致確認を省きます。",
            file=sys.stderr,
        )
        return
    if base_dims != markup_dims:
        raise ValidationError(
            "markup 画像の寸法は先頭の入力画像と一致している必要があります"
            f"（入力画像: {base_dims.width}x{base_dims.height}、"
            f"markup: {markup_dims.width}x{markup_dims.height}）。"
        )


def validate_edit_params(params: EditParams) -> EditParams:
    """画像編集パラメータを検証し、正規化済みパラメータを返す。違反時は ValidationError。

    生成と共通の列挙値・依存関係に加え、入力画像（1〜16枚）と mask、markup、size を検証する。
    size が "auto" の場合はサイズ制約検証をスキップする（入力画像に合わせる）。
    """
    cap = _validate_enums(params)

    if not params.images:
        raise ValidationError(
            "編集には最低 1 枚の入力画像が必要です（--image を指定してください）。"
        )
    if len(params.images) > MAX_INPUT_IMAGES:
        raise ValidationError(
            f"入力画像は最大 {MAX_INPUT_IMAGES} 枚までです（指定枚数: {len(params.images)}）。"
        )
    for image_path in params.images:
        _validate_input_image(image_path, role="入力画像")

    if params.mask is not None:
        _validate_input_image(params.mask, role="マスク画像")
        if Path(params.mask).suffix.lower() != ".png":
            raise ValidationError(
                f"マスク画像は PNG 形式である必要があります: {params.mask}"
            )

    _validate_markup(params, cap)

    if params.size != AUTO_SIZE:
        _validate_size(params.size)
        _warn_if_experimental(params.size, cap)

    return _validate_dependencies(params, cap)
