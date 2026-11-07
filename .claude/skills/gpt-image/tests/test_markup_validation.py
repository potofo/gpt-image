"""markup の入力検証（validate_edit_params）のテスト。"""
import struct
import zlib

import pytest

import capabilities
import validation
from models import EditParams
from validation import ValidationError, validate_edit_params

FLARE = "gpt-image-2.5-flare"


@pytest.fixture(autouse=True)
def enable_markup(monkeypatch):
    """markup が有効な場合の検証を確かめるため、機能フラグを有効にする。"""
    monkeypatch.setitem(capabilities.AZURE_ENABLED, "markup", True)


def _png_bytes(width, height):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr
    chunk += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    return b"\x89PNG\r\n\x1a\n" + chunk


def _file(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def _params(tmp_path, *, base=(1024, 1024), markup=(1024, 1024), **kw):
    values = dict(
        prompt="赤丸の中の花瓶を青くする",
        images=(_file(tmp_path, "base.png", _png_bytes(*base)),),
        markup=_file(tmp_path, "markup.png", _png_bytes(*markup)) if markup else None,
        model=FLARE,
    )
    values.update(kw)
    return EditParams(**values)


def test_valid_markup_passes(tmp_path):
    params = validate_edit_params(_params(tmp_path))
    assert params.markup.endswith("markup.png")


def test_markup_and_mask_are_exclusive(tmp_path):
    mask = _file(tmp_path, "mask.png", _png_bytes(1024, 1024))
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(_params(tmp_path, mask=mask))
    assert "併用できません" in str(exc.value)


def test_gpt_image_2_rejects_markup(tmp_path):
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(_params(tmp_path, model="gpt-image-2"))
    assert "2.5 系モデル専用" in str(exc.value)


def test_markup_rejected_when_flag_disabled(tmp_path, monkeypatch):
    monkeypatch.setitem(capabilities.AZURE_ENABLED, "markup", False)
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(_params(tmp_path))
    assert "Azure では現在利用できません" in str(exc.value)


def test_missing_markup_file_rejected(tmp_path):
    params = _params(tmp_path, markup=None)
    params = EditParams(**{**params.__dict__, "markup": str(tmp_path / "nope.png")})
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(params)
    assert "見つかりません" in str(exc.value)


def test_non_png_markup_rejected(tmp_path):
    params = _params(tmp_path, markup=None)
    jpg = _file(tmp_path, "markup.jpg", b"\xff\xd8\xff\xd9")
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(EditParams(**{**params.__dict__, "markup": jpg}))
    assert "PNG" in str(exc.value)


def test_oversized_markup_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(validation, "MAX_MARKUP_BYTES", 10)
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(_params(tmp_path))
    assert "50MB" in str(exc.value) or "上限" in str(exc.value)


def test_dimension_mismatch_rejected(tmp_path):
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(_params(tmp_path, base=(1024, 1024), markup=(1536, 1024)))
    message = str(exc.value)
    assert "1024x1024" in message and "1536x1024" in message


def test_unreadable_dimensions_warn_and_continue(tmp_path, capsys):
    params = _params(tmp_path)
    broken = _file(tmp_path, "broken.png", b"not-really-png")
    params = EditParams(**{**params.__dict__, "images": (broken,)})
    validate_edit_params(params)
    assert "寸法" in capsys.readouterr().err
