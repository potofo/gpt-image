"""画像ファイルのヘッダから寸法（幅・高さ）を読む。

依存ライブラリを増やさないため、標準ライブラリだけで PNG・JPEG・WebP の
ヘッダを解析する。ファイル全体は読まず、必要なセグメントだけを読む。
形式を判定できない・壊れている場合は例外にせず None を返す。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import BinaryIO, Optional

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# 寸法を持つ JPEG の SOF マーカー（DHT=C4, JPG=C8, DAC=CC は除く）
_JPEG_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                     0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
# 長さフィールドを持たない JPEG マーカー（TEM, RST0-7）
_JPEG_STANDALONE_MARKERS = {0x01, *range(0xD0, 0xD8)}
_JPEG_SOS = 0xDA
_JPEG_APP1 = 0xE1
_EXIF_ORIENTATION_TAG = 0x0112
# EXIF の Orientation のうち、90 度回転を含み幅と高さが入れ替わる値
_ROTATED_ORIENTATIONS = {5, 6, 7, 8}


@dataclass(frozen=True)
class Dimensions:
    """表示上の幅と高さ（JPEG は EXIF の向き補正後）。"""

    width: int
    height: int


def read_dimensions(path: str) -> Optional[Dimensions]:
    """画像の寸法を返す。判定できない・壊れている・読めない場合は None。"""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            f.seek(0)
            if head.startswith(_PNG_SIGNATURE):
                return _read_png(f)
            if head.startswith(b"\xff\xd8"):
                return _read_jpeg(f)
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                return _read_webp(f)
    except (OSError, struct.error, ValueError):
        return None
    return None


def _read_exact(f: BinaryIO, size: int) -> bytes:
    data = f.read(size)
    if len(data) != size:
        raise ValueError("unexpected end of file")
    return data


def _read_png(f: BinaryIO) -> Optional[Dimensions]:
    # シグネチャ(8) + チャンク長(4) + "IHDR"(4) + 幅(4) + 高さ(4)
    data = _read_exact(f, 24)
    if data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return Dimensions(width, height)


def _read_jpeg(f: BinaryIO) -> Optional[Dimensions]:
    _read_exact(f, 2)  # SOI
    orientation = 1
    while True:
        byte = _read_exact(f, 1)
        if byte != b"\xff":
            return None
        marker = _read_exact(f, 1)[0]
        while marker == 0xFF:  # フィルバイト
            marker = _read_exact(f, 1)[0]
        if marker in _JPEG_STANDALONE_MARKERS:
            continue
        if marker == _JPEG_SOS:
            return None  # 画像データに入る前に SOF が見つからなかった
        length = struct.unpack(">H", _read_exact(f, 2))[0]
        if length < 2:
            return None
        if marker in _JPEG_SOF_MARKERS:
            body = _read_exact(f, 5)
            height, width = struct.unpack(">HH", body[1:5])
            if orientation in _ROTATED_ORIENTATIONS:
                width, height = height, width
            return Dimensions(width, height)
        if marker == _JPEG_APP1:
            orientation = _parse_exif_orientation(_read_exact(f, length - 2)) or orientation
            continue
        f.seek(length - 2, 1)


def _parse_exif_orientation(payload: bytes) -> Optional[int]:
    """APP1 の中身から EXIF の Orientation を取り出す。見つからなければ None。"""
    if not payload.startswith(b"Exif\x00\x00"):
        return None
    tiff = payload[6:]
    if tiff[:2] == b"MM":
        fmt = ">"
    elif tiff[:2] == b"II":
        fmt = "<"
    else:
        return None
    ifd_offset = struct.unpack(fmt + "I", tiff[4:8])[0]
    count = struct.unpack(fmt + "H", tiff[ifd_offset:ifd_offset + 2])[0]
    for i in range(count):
        start = ifd_offset + 2 + i * 12
        entry = tiff[start:start + 12]
        if len(entry) < 12:
            return None
        tag, _type, _count = struct.unpack(fmt + "HHI", entry[:8])
        if tag == _EXIF_ORIENTATION_TAG:
            return struct.unpack(fmt + "H", entry[8:10])[0]
    return None


def _read_webp(f: BinaryIO) -> Optional[Dimensions]:
    # "RIFF"(4) + サイズ(4) + "WEBP"(4) + 最初のチャンク ID(4) + チャンク長(4)
    header = _read_exact(f, 20)
    chunk_id = header[12:16]
    if chunk_id == b"VP8 ":
        body = _read_exact(f, 10)
        if body[3:6] != b"\x9d\x01\x2a":
            return None
        width, height = struct.unpack("<HH", body[6:10])
        return Dimensions(width & 0x3FFF, height & 0x3FFF)
    if chunk_id == b"VP8L":
        body = _read_exact(f, 5)
        if body[0] != 0x2F:
            return None
        bits = struct.unpack("<I", body[1:5])[0]
        return Dimensions((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    if chunk_id == b"VP8X":
        body = _read_exact(f, 10)
        width = int.from_bytes(body[4:7], "little") + 1
        height = int.from_bytes(body[7:10], "little") + 1
        return Dimensions(width, height)
    return None
