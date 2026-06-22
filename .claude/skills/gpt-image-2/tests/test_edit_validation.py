"""画像編集パラメータ検証（validate_edit_params）のテスト。"""
import pytest

from models import EditParams
from validation import MAX_INPUT_IMAGES, ValidationError, validate_edit_params


def _img(tmp_path, name="base.png"):
    """テスト用のダミー画像ファイルを作って絶対パスを返す。"""
    p = tmp_path / name
    p.write_bytes(b"fake-image-bytes")
    return str(p)


def _params(tmp_path, **kw):
    base = dict(prompt="赤い帽子に変更", images=(_img(tmp_path),))
    base.update(kw)
    return EditParams(**base)


# --- prompt / images 必須 -------------------------------------------------

def test_empty_prompt_rejected(tmp_path):
    with pytest.raises(ValidationError):
        validate_edit_params(_params(tmp_path, prompt="   "))


def test_no_images_rejected(tmp_path):
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(_params(tmp_path, images=()))
    assert "入力画像" in str(exc.value)


def test_single_image_passes(tmp_path):
    result = validate_edit_params(_params(tmp_path))
    assert len(result.images) == 1


def test_merge_multiple_images_passes(tmp_path):
    images = (_img(tmp_path, "base.png"), _img(tmp_path, "object.jpg"))
    result = validate_edit_params(_params(tmp_path, images=images))
    assert len(result.images) == 2


def test_too_many_images_rejected(tmp_path):
    images = tuple(_img(tmp_path, f"i{i}.png") for i in range(MAX_INPUT_IMAGES + 1))
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(_params(tmp_path, images=images))
    assert str(MAX_INPUT_IMAGES) in str(exc.value)


# --- 入力画像の存在・種別・拡張子 -----------------------------------------

def test_missing_image_rejected(tmp_path):
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(_params(tmp_path, images=(str(tmp_path / "nope.png"),)))
    assert "見つかりません" in str(exc.value)


def test_directory_as_image_rejected(tmp_path):
    with pytest.raises(ValidationError):
        validate_edit_params(_params(tmp_path, images=(str(tmp_path),)))


def test_unsupported_extension_rejected(tmp_path):
    bad = tmp_path / "image.gif"
    bad.write_bytes(b"x")
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(_params(tmp_path, images=(str(bad),)))
    assert "非対応" in str(exc.value)


# --- mask ------------------------------------------------------------------

def test_mask_png_passes(tmp_path):
    mask = _img(tmp_path, "mask.png")
    result = validate_edit_params(_params(tmp_path, mask=mask))
    assert result.mask == mask


def test_non_png_mask_rejected(tmp_path):
    mask = _img(tmp_path, "mask.jpg")
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(_params(tmp_path, mask=mask))
    assert "PNG" in str(exc.value)


def test_missing_mask_rejected(tmp_path):
    with pytest.raises(ValidationError):
        validate_edit_params(_params(tmp_path, mask=str(tmp_path / "nomask.png")))


# --- size ------------------------------------------------------------------

def test_auto_size_skips_size_validation(tmp_path):
    result = validate_edit_params(_params(tmp_path, size="auto"))
    assert result.size == "auto"


def test_explicit_invalid_size_rejected(tmp_path):
    with pytest.raises(ValidationError) as exc:
        validate_edit_params(_params(tmp_path, size="1000x1000"))
    assert "16" in str(exc.value)


def test_explicit_valid_size_passes(tmp_path):
    result = validate_edit_params(_params(tmp_path, size="1024x1024"))
    assert result.size == "1024x1024"


# --- 依存関係（生成と共通） -----------------------------------------------

def test_transparent_requires_png(tmp_path):
    with pytest.raises(ValidationError):
        validate_edit_params(
            _params(tmp_path, background="transparent", output_format="jpeg")
        )
