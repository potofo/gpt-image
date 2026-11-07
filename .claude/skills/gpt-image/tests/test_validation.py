"""パラメータ検証（validation）のテスト。"""
import pytest

from models import GenerationParams
from validation import ValidationError, validate_params


def make(**kwargs) -> GenerationParams:
    base = dict(prompt="テストプロンプト")
    base.update(kwargs)
    return GenerationParams(**base)


# --- prompt ---------------------------------------------------------------

def test_empty_prompt_rejected():
    with pytest.raises(ValidationError):
        validate_params(make(prompt="   "))


# --- size 制約 (3.1-3.4) --------------------------------------------------

def test_valid_default_size_passes():
    result = validate_params(make())
    assert result.size == "1024x1024"


@pytest.mark.parametrize("size", ["1000x1024", "1024x1000", "1024", "axb", "1024x"])
def test_size_must_be_multiple_of_16_or_wellformed(size):
    with pytest.raises(ValidationError):
        validate_params(make(size=size))


def test_size_long_edge_over_4k_rejected():
    # 3856 は 16 の倍数で比・ピクセル数は妥当だが、長辺が 3840 超
    with pytest.raises(ValidationError):
        validate_params(make(size="3856x1296"))


def test_size_aspect_ratio_over_3to1_rejected():
    # 3072x1024 = 3:1 ちょうどは許容、3088x1024 は超過
    with pytest.raises(ValidationError):
        validate_params(make(size="3088x1024"))


def test_size_aspect_ratio_exactly_3to1_passes():
    validate_params(make(size="3072x1024"))


def test_size_total_pixels_below_min_rejected():
    # 640x1008 = 645,120 < 655,360
    with pytest.raises(ValidationError):
        validate_params(make(size="640x1008"))


def test_size_total_pixels_above_max_rejected():
    # 3840x2176 = 8,355,840 > 8,294,400
    with pytest.raises(ValidationError):
        validate_params(make(size="3840x2176"))


# --- 列挙値 (3.5) ---------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("quality", "ultra"),
    ("output_format", "webp"),
    ("background", "blur"),
    ("n", 0),
    ("n", 11),
])
def test_enum_and_range_validation(field, value):
    with pytest.raises(ValidationError):
        validate_params(make(**{field: value}))


# --- 依存関係 (4.1-4.4) ---------------------------------------------------

def test_transparent_requires_png():
    with pytest.raises(ValidationError):
        validate_params(make(background="transparent", output_format="jpeg"))


def test_transparent_with_png_passes():
    result = validate_params(make(background="transparent", output_format="png"))
    assert result.background == "transparent"


def test_compression_with_png_warns_and_ignored(capsys):
    result = validate_params(make(output_format="png", output_compression=50))
    captured = capsys.readouterr()
    assert "compression" in captured.err.lower() or "圧縮" in captured.err
    # png のときは既定値(100)に正規化され、リクエストに影響しない
    assert result.output_compression == 100


def test_compression_with_jpeg_preserved():
    result = validate_params(make(output_format="jpeg", output_compression=50))
    assert result.output_compression == 50


@pytest.mark.parametrize("value", [-1, 101])
def test_compression_out_of_range_rejected(value):
    with pytest.raises(ValidationError):
        validate_params(make(output_format="jpeg", output_compression=value))
