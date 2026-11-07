"""パラメータ検証（Fail Fast）。

API 呼び出し前に、size 制約・列挙値・パラメータ依存関係を検査する。
違反は具体的な原因メッセージとともに ValidationError を送出する。
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

from models import EditParams, GenerationParams

# gpt-image-2 の size 制約
SIZE_MULTIPLE = 16
MAX_LONG_EDGE = 3840
MAX_ASPECT_RATIO = 3.0
MIN_TOTAL_PIXELS = 655_360
MAX_TOTAL_PIXELS = 8_294_400

VALID_QUALITY = {"low", "medium", "high"}
VALID_FORMAT = {"png", "jpeg"}
VALID_BACKGROUND = {"auto", "transparent"}
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


def _validate_enums(params: GenerationParams) -> None:
    if not params.prompt or not params.prompt.strip():
        raise ValidationError("prompt は必須です。生成内容を指定してください。")
    if params.quality not in VALID_QUALITY:
        raise ValidationError(
            f"quality '{params.quality}' は無効です。{sorted(VALID_QUALITY)} のいずれかを指定してください。"
        )
    if params.output_format not in VALID_FORMAT:
        raise ValidationError(
            f"format '{params.output_format}' は無効です。{sorted(VALID_FORMAT)} のいずれかを指定してください"
            "（WEBP は Azure 非対応）。"
        )
    if params.background not in VALID_BACKGROUND:
        raise ValidationError(
            f"background '{params.background}' は無効です。{sorted(VALID_BACKGROUND)} のいずれかを指定してください。"
        )
    if not (MIN_N <= params.n <= MAX_N):
        raise ValidationError(f"n は {MIN_N}〜{MAX_N} の範囲で指定してください（指定値: {params.n}）。")


def _validate_dependencies(params: GenerationParams) -> GenerationParams:
    """依存関係を検証し、必要なら正規化済みパラメータを返す。"""
    if params.background == "transparent" and params.output_format != "png":
        raise ValidationError(
            "background=transparent を使う場合は format=png が必須です"
            f"（指定された format: {params.output_format}）。"
        )

    if params.output_format == "jpeg":
        if not (MIN_COMPRESSION <= params.output_compression <= MAX_COMPRESSION):
            raise ValidationError(
                f"compression は {MIN_COMPRESSION}〜{MAX_COMPRESSION} の範囲で指定してください"
                f"（指定値: {params.output_compression}）。"
            )
        return params

    # png のとき: compression は無効。明示指定があれば警告して既定値へ正規化する。
    if params.output_compression != DEFAULT_COMPRESSION:
        print(
            "警告: compression は format=jpeg のときのみ有効です。"
            "format=png のため compression を無視します。",
            file=sys.stderr,
        )
        return replace(params, output_compression=DEFAULT_COMPRESSION)
    return params


def validate_params(params: GenerationParams) -> GenerationParams:
    """すべての制約を検証し、正規化済みパラメータを返す。違反時は ValidationError。"""
    _validate_enums(params)
    _validate_size(params.size)
    return _validate_dependencies(params)


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


def validate_edit_params(params: EditParams) -> EditParams:
    """画像編集パラメータを検証し、正規化済みパラメータを返す。違反時は ValidationError。

    生成と共通の列挙値・依存関係に加え、入力画像（1〜16枚）と mask、size を検証する。
    size が "auto" の場合はサイズ制約検証をスキップする（入力画像に合わせる）。
    """
    _validate_enums(params)

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

    if params.size != AUTO_SIZE:
        _validate_size(params.size)

    return _validate_dependencies(params)
