#!/usr/bin/env python3
"""gpt-image 画像編集 CLI（エントリポイント）。

アップロードした既存画像をプロンプトで修正する。単一画像の編集に加え、
複数画像を渡してマージ（合成）もできる。マージとは、ベース画像の一部の
オブジェクトを別画像のオブジェクトに置き換える編集で、置換領域を限定したい
場合は --mask（透過 PNG）を併用する。

必須引数は --prompt と最低 1 枚の --image。認証情報は CLI 引数では受け取らず、
環境変数経由でのみ取得する（generate_image.py と同一の方針）。

フロー: 引数解析 -> 設定読み込み -> 検証 -> 認証解決 -> API 呼び出し -> 保存。
成功時は保存先の絶対パスを stdout に出力し、終了コード 0。
異常時は原因を stderr に出力し、非ゼロ終了。
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Callable, Optional

import config as config_module
import auth as auth_module
import client as client_module
import storage as storage_module
from capabilities import DEFAULT_MODEL, MODEL_NAMES
from models import EditParams
from validation import ValidationError, validate_edit_params

EXIT_OK = 0
EXIT_ERROR = 1

# 各パラメータの既定値を上書きできる環境変数名と、組み込み既定値。
# 優先順位: CLI 引数 > 環境変数(.env) > 組み込み既定。
# size の既定は "auto"（入力画像に合わせる）。
ENV_DEFAULTS: dict[str, tuple[str, Optional[str]]] = {
    "size": ("GPT_IMAGE_EDIT_SIZE", "auto"),
    "quality": ("GPT_IMAGE_QUALITY", "high"),
    "output_format": ("GPT_IMAGE_FORMAT", "png"),
    "background": ("GPT_IMAGE_BACKGROUND", "auto"),
    "output_compression": ("GPT_IMAGE_COMPRESSION", "100"),
    "n": ("GPT_IMAGE_N", "1"),
    "output_dir": ("GPT_IMAGE_OUTPUT_DIR", "./images"),
    "user": ("GPT_IMAGE_USER", None),
    "model": ("GPT_IMAGE_MODEL", DEFAULT_MODEL),
    "complexity": ("GPT_IMAGE_COMPLEXITY", None),
}

BUILTIN_DEFAULTS = {field: builtin for field, (_, builtin) in ENV_DEFAULTS.items()}


def _env_default(field: str) -> Optional[str]:
    """環境変数があればその値、無ければ組み込み既定を返す（空文字は未設定扱い）。"""
    env_name, builtin = ENV_DEFAULTS[field]
    value = os.environ.get(env_name)
    return value if value else builtin


def parse_args(argv: Optional[list[str]] = None) -> EditParams:
    """CLI 引数を解析し EditParams を返す。--prompt/--image 未指定なら SystemExit。"""
    parser = argparse.ArgumentParser(
        prog="edit_image.py",
        description=(
            "Azure の gpt-image-2 / gpt-image-2.5 系で既存画像をプロンプト編集・マージし、ローカルに保存します。"
        ),
    )
    parser.add_argument("--prompt", required=True, help="編集内容の指示（必須）")
    parser.add_argument(
        "--image", dest="images", action="append", metavar="PATH",
        help="入力画像パス（必須。複数指定で合成/マージ。先頭がベース画像）",
    )
    parser.add_argument(
        "--mask", default=None, metavar="PATH",
        help="編集領域を示す透過 PNG マスク（任意。透過部分のみ編集される）",
    )
    parser.add_argument(
        "--markup", default=None, metavar="PATH",
        help="編集箇所を描き込んだ透過 PNG（任意。2.5 系のみ。先頭画像と同じ寸法、--mask と併用不可）",
    )
    parser.add_argument("--size", default=None,
                        help=f"解像度 WxH または auto（既定: {BUILTIN_DEFAULTS['size']}、GPT_IMAGE_EDIT_SIZE）")
    parser.add_argument("--quality", default=None,
                        help=f"画質 low/medium/high（2.5 系は xhigh/max/auto も可。既定: {BUILTIN_DEFAULTS['quality']}、GPT_IMAGE_QUALITY）")
    parser.add_argument("--format", dest="output_format", default=None,
                        help=f"出力形式 png/jpeg（既定: {BUILTIN_DEFAULTS['output_format']}、GPT_IMAGE_FORMAT）")
    parser.add_argument("--background", default=None,
                        help=f"背景 auto/transparent（2.5 系は opaque も可。既定: {BUILTIN_DEFAULTS['background']}、GPT_IMAGE_BACKGROUND。transparent は png 必須）")
    parser.add_argument("--compression", dest="output_compression", type=int, default=None,
                        help=f"JPEG 圧縮 0-100（既定: {BUILTIN_DEFAULTS['output_compression']}、GPT_IMAGE_COMPRESSION）")
    parser.add_argument("--n", type=int, default=None,
                        help=f"生成枚数 1-10（既定: {BUILTIN_DEFAULTS['n']}、GPT_IMAGE_N）")
    parser.add_argument("--user", default=None,
                        help="利用状況トラッキング用 ID（任意、GPT_IMAGE_USER）")
    parser.add_argument("--model", default=None,
                        help=f"モデル種別 {'/'.join(MODEL_NAMES)}（既定: {BUILTIN_DEFAULTS['model']}、GPT_IMAGE_MODEL）")
    parser.add_argument("--complexity", default=None,
                        help="描画前の計画量 low/medium/high（2.5 系のみ。既定: 未指定、GPT_IMAGE_COMPLEXITY）")
    parser.add_argument("--output", dest="output_dir", default=None,
                        help=f"保存先ディレクトリ（既定: {BUILTIN_DEFAULTS['output_dir']}、GPT_IMAGE_OUTPUT_DIR）")

    args = parser.parse_args(argv)

    if not args.images:
        parser.error("--image を最低 1 枚指定してください。")

    def pick_str(field: str, cli_value):
        return cli_value if cli_value is not None else _env_default(field)

    def pick_int(field: str, cli_value):
        if cli_value is not None:
            return cli_value
        raw = _env_default(field)
        try:
            return int(raw)
        except (TypeError, ValueError):
            parser.error(
                f"環境変数 {ENV_DEFAULTS[field][0]} の値が整数ではありません: {raw!r}"
            )

    model = pick_str("model", args.model)
    if model not in MODEL_NAMES:
        source = "--model" if args.model is not None else ENV_DEFAULTS["model"][0]
        parser.error(
            f"{source} のモデル種別 '{model}' は無効です。"
            f"{' / '.join(MODEL_NAMES)} のいずれかを指定してください。"
        )

    return EditParams(
        prompt=args.prompt,
        images=tuple(args.images),
        mask=args.mask,
        size=pick_str("size", args.size),
        quality=pick_str("quality", args.quality),
        output_format=pick_str("output_format", args.output_format),
        background=pick_str("background", args.background),
        output_compression=pick_int("output_compression", args.output_compression),
        n=pick_int("n", args.n),
        user=pick_str("user", args.user),
        output_dir=pick_str("output_dir", args.output_dir),
        model=model,
        complexity=pick_str("complexity", args.complexity),
        markup=args.markup,
    )


def run(
    argv: Optional[list[str]] = None,
    *,
    load_config: Callable = config_module.load_config,
    load_api_key: Callable = config_module.load_api_key,
    resolve_auth: Callable = auth_module.resolve_auth,
    edit: Callable = client_module.edit,
    save_images: Callable = storage_module.save_images,
    out=sys.stdout,
    err=sys.stderr,
) -> int:
    """全体オーケストレーション。終了コードを返す（0=成功、1=失敗）。"""
    try:
        params = parse_args(argv)
    except SystemExit as exc:  # argparse の引数エラー
        return exc.code if isinstance(exc.code, int) else EXIT_ERROR

    try:
        # 既定モデルは従来どおり引数なしで読み込む（既定モデルでは同じ意味になる）
        config = load_config() if params.model == DEFAULT_MODEL else load_config(params.model)
        params = validate_edit_params(params)
        auth = resolve_auth(load_api_key(), scope=config.token_scope)
        images = edit(config, auth, params)
        title = storage_module.derive_title(params.prompt)
        paths = save_images(images, params.output_dir, params.output_format, title=title)
    except ValidationError as exc:
        print(f"パラメータエラー: {exc}", file=err)
        return EXIT_ERROR
    except config_module.ConfigError as exc:
        print(f"設定エラー: {exc}", file=err)
        return EXIT_ERROR
    except auth_module.AuthError as exc:
        print(f"認証エラー: {exc}", file=err)
        return EXIT_ERROR
    except client_module.ApiError as exc:
        print(f"API エラー[{exc.kind}]: {exc}", file=err)
        return EXIT_ERROR
    except OSError as exc:
        print(f"ファイルエラー: {exc}", file=err)
        return EXIT_ERROR

    for path in paths:
        print(path, file=out)
    return EXIT_OK


def main() -> None:
    # プロジェクトの .env を読み込む（OS 環境変数が優先）。
    config_module.load_project_dotenv()
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
