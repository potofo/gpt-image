"""画像の保存。

API レスポンスから得た画像バイト列を一意なファイル名で保存し、絶対パスを返す。
ファイル名は gpt-image-2_<timestamp>_<index>.<ext> 形式で、複数枚は連番。
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from models import OutputFormat

_EXTENSION = {"png": "png", "jpeg": "jpg"}

# Windows/POSIX で使えないファイル名文字と制御文字
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
_MULTI_HYPHEN = re.compile(r"-{2,}")

DEFAULT_TITLE = "gpt-image-2"


def derive_title(prompt: str, max_len: int = 40) -> str:
    """プロンプトからファイル名に使える適切なタイトルを導出する。

    ファイルシステムで使えない文字を除去し、空白をハイフン化する。
    日本語等の文字は保持する。空になる場合は 'image' を返す。
    """
    text = (prompt or "").strip()
    text = _ILLEGAL_CHARS.sub("", text)
    text = _WHITESPACE.sub("-", text)
    text = _MULTI_HYPHEN.sub("-", text)
    text = text.strip("-. ")
    if len(text) > max_len:
        text = text[:max_len].strip("-. ")
    return text or "image"


def save_images(
    images: list[bytes],
    output_dir: str,
    output_format: OutputFormat,
    title: str = DEFAULT_TITLE,
) -> list[str]:
    """画像バイト列のリストを保存し、保存先の絶対パスのリストを返す。

    output_dir が存在しない場合は作成する。複数枚は同一 timestamp + 連番 index。
    ファイル名は <title>_<timestamp>_<index>.<ext> 形式。
    """
    out_path = Path(output_dir).expanduser()
    out_path.mkdir(parents=True, exist_ok=True)

    ext = _EXTENSION.get(output_format, output_format)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    safe_title = title or DEFAULT_TITLE

    saved: list[str] = []
    for index, data in enumerate(images):
        filename = f"{safe_title}_{timestamp}_{index}.{ext}"
        file_path = out_path / filename
        file_path.write_bytes(data)
        saved.append(str(file_path.resolve()))
    return saved
