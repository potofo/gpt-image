#!/usr/bin/env python3
"""gpt-image-2 画像生成 CLI（エントリポイント）。

必須引数は --prompt のみ。他は推奨デフォルトを持つ任意引数。
認証情報は CLI 引数では受け取らず、環境変数経由でのみ取得する。

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
from models import GenerationParams
from validation import ValidationError, validate_params

EXIT_OK = 0
EXIT_ERROR = 1

# 各パラメータの既定値を上書きできる環境変数名と、組み込み既定値。
# 優先順位: CLI 引数 > 環境変数(.env) > 組み込み既定。
ENV_DEFAULTS: dict[str, tuple[str, Optional[str]]] = {
    "size": ("GPT_IMAGE_SIZE", "1024x1024"),
    "quality": ("GPT_IMAGE_QUALITY", "high"),
    "output_format": ("GPT_IMAGE_FORMAT", "png"),
    "background": ("GPT_IMAGE_BACKGROUND", "auto"),
    "output_compression": ("GPT_IMAGE_COMPRESSION", "100"),
    "n": ("GPT_IMAGE_N", "1"),
    "output_dir": ("GPT_IMAGE_OUTPUT_DIR", "./images"),
    "user": ("GPT_IMAGE_USER", None),
}

BUILTIN_DEFAULTS = {field: builtin for field, (_, builtin) in ENV_DEFAULTS.items()}


def _env_default(field: str) -> Optional[str]:
    """環境変数があればその値、無ければ組み込み既定を返す（空文字は未設定扱い）。"""
    env_name, builtin = ENV_DEFAULTS[field]
    value = os.environ.get(env_name)
    return value if value else builtin


def parse_args(argv: Optional[list[str]] = None) -> GenerationParams:
    """CLI 引数を解析し GenerationParams を返す。--prompt 未指定なら SystemExit。"""
    parser = argparse.ArgumentParser(
        prog="generate_image.py",
        description="Azure gpt-image-2 でテキストから画像を生成し、ローカルに保存します。",
    )
    # 任意引数は default=None とし、未指定時は環境変数(.env)→組み込み既定の順で補完する。
    # 優先順位: CLI 引数 > 環境変数(.env) > 組み込み既定。
    parser.add_argument("--prompt", required=True, help="生成内容の指示（必須）")
    parser.add_argument("--size", default=None,
                        help=f"解像度 WxH（既定: {BUILTIN_DEFAULTS['size']}、環境変数 GPT_IMAGE_SIZE で変更可）")
    parser.add_argument("--quality", default=None, choices=["low", "medium", "high"],
                        help=f"画質（既定: {BUILTIN_DEFAULTS['quality']}、GPT_IMAGE_QUALITY）")
    parser.add_argument("--format", dest="output_format", default=None,
                        choices=["png", "jpeg"],
                        help=f"出力形式（既定: {BUILTIN_DEFAULTS['output_format']}、GPT_IMAGE_FORMAT）")
    parser.add_argument("--background", default=None, choices=["auto", "transparent"],
                        help=f"背景（既定: {BUILTIN_DEFAULTS['background']}、GPT_IMAGE_BACKGROUND。transparent は png 必須）")
    parser.add_argument("--compression", dest="output_compression", type=int, default=None,
                        help=f"JPEG 圧縮 0-100（既定: {BUILTIN_DEFAULTS['output_compression']}、GPT_IMAGE_COMPRESSION）")
    parser.add_argument("--n", type=int, default=None,
                        help=f"生成枚数 1-10（既定: {BUILTIN_DEFAULTS['n']}、GPT_IMAGE_N）")
    parser.add_argument("--user", default=None,
                        help="利用状況トラッキング用 ID（任意、GPT_IMAGE_USER）")
    parser.add_argument("--output", dest="output_dir", default=None,
                        help=f"保存先ディレクトリ（既定: {BUILTIN_DEFAULTS['output_dir']}、GPT_IMAGE_OUTPUT_DIR）")

    args = parser.parse_args(argv)

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

    return GenerationParams(
        prompt=args.prompt,
        size=pick_str("size", args.size),
        quality=pick_str("quality", args.quality),
        output_format=pick_str("output_format", args.output_format),
        background=pick_str("background", args.background),
        output_compression=pick_int("output_compression", args.output_compression),
        n=pick_int("n", args.n),
        user=pick_str("user", args.user),
        output_dir=pick_str("output_dir", args.output_dir),
    )


def run(
    argv: Optional[list[str]] = None,
    *,
    load_config: Callable = config_module.load_config,
    load_api_key: Callable = config_module.load_api_key,
    resolve_auth: Callable = auth_module.resolve_auth,
    generate: Callable = client_module.generate,
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
        config = load_config()
        params = validate_params(params)
        auth = resolve_auth(load_api_key())
        images = generate(config, auth, params)
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
        print(f"保存エラー: {exc}", file=err)
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
