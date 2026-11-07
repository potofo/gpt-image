"""画像ヘッダからの寸法読み取り（image_info）のテスト。"""
import struct
import zlib

import pytest

from image_info import Dimensions, read_dimensions


def _png(width, height):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr
    chunk += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    return b"\x89PNG\r\n\x1a\n" + chunk


def _exif_app1(orientation, byte_order=b"MM"):
    fmt = ">" if byte_order == b"MM" else "<"
    tiff = byte_order + struct.pack(fmt + "HI", 42, 8)
    tiff += struct.pack(fmt + "H", 1)
    tiff += struct.pack(fmt + "HHIHH", 0x0112, 3, 1, orientation, 0)
    tiff += struct.pack(fmt + "I", 0)
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def _jpeg(width, height, *, orientation=None, sof=0xC0):
    data = b"\xff\xd8"
    # JFIF の APP0 を先頭に置き、SOF までのセグメント走査を確認する
    app0 = b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    data += b"\xff\xe0" + struct.pack(">H", len(app0) + 2) + app0
    if orientation is not None:
        data += _exif_app1(orientation)
    sof_body = struct.pack(">BHHB", 8, height, width, 3) + b"\x01\x11\x00" * 3
    data += bytes([0xFF, sof]) + struct.pack(">H", len(sof_body) + 2) + sof_body
    return data + b"\xff\xd9"


def _riff(chunk_id, chunk_body):
    chunk = chunk_id + struct.pack("<I", len(chunk_body)) + chunk_body
    return b"RIFF" + struct.pack("<I", 4 + len(chunk)) + b"WEBP" + chunk


def _webp_vp8(width, height):
    body = b"\x00\x00\x00" + b"\x9d\x01\x2a" + struct.pack("<HH", width, height) + b"\x00" * 4
    return _riff(b"VP8 ", body)


def _webp_vp8l(width, height):
    bits = (width - 1) | ((height - 1) << 14)
    return _riff(b"VP8L", b"\x2f" + struct.pack("<I", bits) + b"\x00")


def _webp_vp8x(width, height):
    w, h = width - 1, height - 1
    body = b"\x00\x00\x00\x00" + w.to_bytes(3, "little") + h.to_bytes(3, "little")
    return _riff(b"VP8X", body)


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_png(tmp_path):
    assert read_dimensions(_write(tmp_path, "a.png", _png(1536, 1024))) == Dimensions(1536, 1024)


def test_jpeg_baseline(tmp_path):
    assert read_dimensions(_write(tmp_path, "a.jpg", _jpeg(800, 600))) == Dimensions(800, 600)


def test_jpeg_progressive(tmp_path):
    path = _write(tmp_path, "a.jpg", _jpeg(800, 600, sof=0xC2))
    assert read_dimensions(path) == Dimensions(800, 600)


@pytest.mark.parametrize("orientation", [5, 6, 7, 8])
def test_jpeg_exif_rotation_swaps(tmp_path, orientation):
    path = _write(tmp_path, "a.jpg", _jpeg(800, 600, orientation=orientation))
    assert read_dimensions(path) == Dimensions(600, 800)


@pytest.mark.parametrize("orientation", [1, 3])
def test_jpeg_exif_without_rotation_keeps(tmp_path, orientation):
    path = _write(tmp_path, "a.jpg", _jpeg(800, 600, orientation=orientation))
    assert read_dimensions(path) == Dimensions(800, 600)


def test_jpeg_exif_little_endian(tmp_path):
    data = _jpeg(800, 600)
    # APP0 の直後に little endian の EXIF を差し込む
    insert_at = data.index(b"\xff\xc0")
    data = data[:insert_at] + _exif_app1(6, byte_order=b"II") + data[insert_at:]
    assert read_dimensions(_write(tmp_path, "a.jpg", data)) == Dimensions(600, 800)


@pytest.mark.parametrize("builder", [_webp_vp8, _webp_vp8l, _webp_vp8x])
def test_webp_variants(tmp_path, builder):
    assert read_dimensions(_write(tmp_path, "a.webp", builder(1024, 768))) == Dimensions(1024, 768)


@pytest.mark.parametrize("data", [
    b"",
    b"not an image at all",
    b"\x89PNG\r\n\x1a\n\x00\x00",          # IHDR が途中で切れている
    b"\xff\xd8\xff\xe0\x00",                # JPEG のセグメント長が途中で切れている
    b"RIFF\x00\x00\x00\x00WEBPVP8 ",        # WebP のチャンクが途中で切れている
])
def test_broken_or_unknown_returns_none(tmp_path, data):
    assert read_dimensions(_write(tmp_path, "x.bin", data)) is None


def test_missing_file_returns_none(tmp_path):
    assert read_dimensions(str(tmp_path / "nope.png")) is None
