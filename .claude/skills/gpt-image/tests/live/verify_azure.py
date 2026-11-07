#!/usr/bin/env python3
"""Azure 実機で gpt-image-2.5 系の機能の可否を確かめる確認ツール（手動実行）。

実際に API を呼ぶため費用がかかる。pytest には収集されない（ファイル名が test_ で始まらない）。
項目ごとに 1 回ずつ、検証を通さずに client.post_raw で送り、受け付けられたかどうかを
Markdown の表で出力する。結果は research/azure-gpt-image-2.5-verification.md に記録し、
capabilities.AZURE_ENABLED と SKILL.md を見直す根拠にする。

使い方（.claude/skills/gpt-image で実行）:
    python tests/live/verify_azure.py --model gpt-image-2.5-flare [--out <path>]

キー・トークン・エンドポイント・デプロイ名は出力しない。
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
import time
import zlib
from dataclasses import dataclass, replace
from typing import Callable, Optional, Sequence

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import auth as auth_module  # noqa: E402
import client as client_module  # noqa: E402
import config as config_module  # noqa: E402
from capabilities import MODEL_NAMES  # noqa: E402
from models import DEFAULT_MODEL, DEFAULT_TOKEN_SCOPE, AzureConfig  # noqa: E402

# v1 形式で試すトークンのスコープ（Microsoft のドキュメントの v1 の例は ai.azure.com を使う）
V1_SCOPES = (DEFAULT_TOKEN_SCOPE, "https://ai.azure.com/.default")
API_KEY_SCOPE_LABEL = "(api-key)"
PROBE_TIMEOUT = 300.0
# 429（レート制限）時の待ち時間（秒）。S0 プランは 1 分あたりの上限が低いため長めにとる
RATE_LIMIT_BACKOFF = (15.0, 30.0, 60.0)
# 費用を抑えるための共通設定（確認対象の項目以外）
BASE_BODY = {"prompt": "A small red apple on a white table", "size": "1024x1024",
             "quality": "low", "n": 1}
IMAGE_SIZE = 1024
_PNG_SIGNATURE = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])
_FILTER_NONE = bytes([0])


@dataclass(frozen=True)
class Probe:
    """確認項目 1 つ分。generations は json_body、edits は form と files を送る。"""

    item: str
    operation: str
    json_body: Optional[dict] = None
    form: Optional[dict] = None
    files: Optional[list] = None


@dataclass(frozen=True)
class ProbeResult:
    item: str
    api_style: str
    token_scope: str
    accepted: bool
    status: Optional[int]
    error_code: Optional[str]
    message: str


def _png_from_rows(width: int, height: int, raw_rows: bytes) -> bytes:
    """フィルタ付きの RGBA 行データから PNG を作る（標準ライブラリのみ）。"""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (_PNG_SIGNATURE + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw_rows, 9)) + chunk(b"IEND", b""))


def make_png(width: int, height: int, rgba: tuple[int, int, int, int]) -> bytes:
    """単色の RGBA PNG を作る。"""
    return _png_from_rows(width, height, (_FILTER_NONE + bytes(rgba) * width) * height)


def _markup_png() -> bytes:
    """透過の下地の中央に赤い四角を描いた注釈画像。"""
    width = height = IMAGE_SIZE
    transparent, red = bytes((0, 0, 0, 0)), bytes((255, 0, 0, 255))
    lo, hi = width // 3, width * 2 // 3
    plain = _FILTER_NONE + transparent * width
    marked = _FILTER_NONE + transparent * lo + red * (hi - lo) + transparent * (width - hi)
    return _png_from_rows(width, height,
                          b"".join(marked if lo <= y < hi else plain for y in range(height)))


def build_probes() -> list[Probe]:
    """確認項目の一覧を返す。"""
    probes = [Probe(f"quality={q}", "generations", json_body={**BASE_BODY, "quality": q})
              for q in ("xhigh", "max", "auto")]
    probes += [Probe(f"background={b}", "generations",
                     json_body={**BASE_BODY, "background": b, "output_format": "png"})
               for b in ("opaque", "transparent")]
    probes.append(Probe("output_format=webp", "generations",
                        json_body={**BASE_BODY, "output_format": "webp"}))
    probes.append(Probe("complexity=low", "generations",
                        json_body={**BASE_BODY, "complexity": "low"}))
    base_png = make_png(IMAGE_SIZE, IMAGE_SIZE, (200, 200, 200, 255))
    probes.append(Probe(
        "edits markup", "edits",
        form={"prompt": "Paint the area inside the red square blue. Remove the red square.",
              "quality": "low", "n": "1"},
        files=[("image[]", ("base.png", base_png, "image/png")),
               ("markup", ("markup.png", _markup_png(), "image/png"))],
    ))
    return probes


def _error_code(body) -> Optional[str]:
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return error.get("code") or error.get("type")
    return None


def _error_message(body) -> str:
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or "")
    return str(body.get("raw_text", "")) if isinstance(body, dict) else ""


def _send_probe(probe: Probe, config: AzureConfig, auth, post: Callable,
                sleep: Callable[[float], None]):
    """1 項目を送る。429 は RATE_LIMIT_BACKOFF の間隔で再試行する。"""
    for wait in (*RATE_LIMIT_BACKOFF, None):
        raw = post(config, auth, probe.operation, json_body=probe.json_body, form=probe.form,
                   files=probe.files, timeout=PROBE_TIMEOUT)
        if raw.status != 429 or wait is None:
            return raw
        sleep(wait)
    return raw


def _config_for_style(config: AzureConfig, style: str) -> AzureConfig:
    """API 形式を差し替えた設定を返す。形式を変えるときは api-version もその形式の既定にする。"""
    if style == config.api_style:
        return config
    version = (config_module.DEFAULT_V1_API_VERSION if style == "v1"
               else config_module.DEFAULT_API_VERSION)
    return replace(config, api_style=style, api_version=version)


def run_probes(
    config: AzureConfig,
    model: str,
    *,
    api_key: Optional[str],
    api_styles: Sequence[str] = ("deployments", "v1"),
    post: Callable = client_module.post_raw,
    resolve: Callable = auth_module.resolve_auth,
    sleep: Callable[[float], None] = time.sleep,
    items: Optional[Sequence[str]] = None,
    delay: float = 0.0,
) -> list[ProbeResult]:
    """各 API 形式（v1 はスコープも）× 各項目を 1 回ずつ送り、結果を返す。途中で失敗しても続ける。

    items で確認する項目を絞り込める（未知の項目名は ValueError）。delay 秒ずつ間隔を空けて送る。
    """
    results: list[ProbeResult] = []
    probes = build_probes()
    if items is not None:
        known = {p.item for p in probes}
        unknown = [i for i in items if i not in known]
        if unknown:
            raise ValueError(f"未知の項目です: {unknown}。使える項目: {sorted(known)}")
        probes = [p for p in probes if p.item in items]
    first = True
    for style in api_styles:
        styled = _config_for_style(config, style)
        scopes = V1_SCOPES if style == "v1" else (config.token_scope,)
        for scope in scopes:
            auth = resolve(api_key, scope=scope)
            scope_label = API_KEY_SCOPE_LABEL if auth.name == "api-key" else scope
            for probe in probes:
                if delay and not first:
                    sleep(delay)
                first = False
                try:
                    raw = _send_probe(probe, styled, auth, post, sleep)
                except client_module.ApiError as exc:
                    results.append(ProbeResult(probe.item, style, scope_label, False,
                                               exc.status, exc.kind, str(exc)))
                    continue
                accepted = raw.status == 200
                results.append(ProbeResult(
                    item=probe.item, api_style=style, token_scope=scope_label,
                    accepted=accepted, status=raw.status,
                    error_code=None if accepted else _error_code(raw.body),
                    message="" if accepted else _error_message(raw.body),
                ))
            if auth.name == "api-key":
                break  # API キー認証ではスコープを変えても結果は同じ
    return results


def _cell(value: Optional[object]) -> str:
    text = "" if value is None else " ".join(str(value).split())  # 改行をまとめる
    return text.replace("|", "\\|")[:200]


def to_markdown(model: str, results: Sequence[ProbeResult]) -> str:
    """結果を Markdown の表にする。エンドポイント・デプロイ名・認証情報は含めない。"""
    lines = [
        f"## {model}",
        "",
        "| 項目 | API 形式 | トークンのスコープ | 結果 | ステータス | エラーコード | メッセージ |",
        "|------|----------|--------------------|------|------------|--------------|------------|",
    ]
    for r in results:
        lines.append("| " + " | ".join([
            _cell(r.item), _cell(r.api_style), _cell(r.token_scope),
            "受け付けられた" if r.accepted else "拒否された",
            _cell(r.status), _cell(r.error_code), _cell(r.message),
        ]) + " |")
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_azure.py",
                                     description="Azure 実機で gpt-image-2.5 系の機能の可否を確かめる")
    parser.add_argument("--model", required=True,
                        choices=[m for m in MODEL_NAMES if m != DEFAULT_MODEL])
    parser.add_argument("--styles", default="deployments,v1",
                        help="試す API 形式（カンマ区切り。既定: deployments,v1）")
    parser.add_argument("--items", default=None,
                        help="確認する項目（カンマ区切り。例: background=transparent,output_format=webp）")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="項目ごとに空ける秒数（レート制限対策。例: 15）")
    parser.add_argument("--out", default=None, help="結果の Markdown を追記するファイル（既定: 標準出力）")
    args = parser.parse_args(argv)
    items = [i.strip() for i in args.items.split(",") if i.strip()] if args.items else None
    if items is not None:
        known = {p.item for p in build_probes()}
        unknown = [i for i in items if i not in known]
        if unknown:
            parser.error(f"未知の項目です: {unknown}。使える項目: {', '.join(sorted(known))}")

    config_module.load_project_dotenv()
    try:
        config = config_module.load_config(args.model)
    except config_module.ConfigError as exc:
        print(f"設定エラー: {exc}（API は呼び出していません）", file=sys.stderr)
        return 1

    styles = [s.strip() for s in args.styles.split(",") if s.strip()]
    results = run_probes(config, args.model, api_key=config_module.load_api_key(),
                         api_styles=styles, items=items, delay=args.delay)
    markdown = to_markdown(args.model, results)
    if args.out:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")
        print(f"結果を追記しました: {os.path.abspath(args.out)}", file=sys.stderr)
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
