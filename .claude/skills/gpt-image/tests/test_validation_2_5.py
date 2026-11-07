"""対応表に基づくパラメータ検証（2.5 系対応）のテスト。"""
import pytest

import capabilities
from models import EditParams, GenerationParams
from validation import ValidationError, validate_edit_params, validate_params

FLARE = "gpt-image-2.5-flare"
SUNBURST = "gpt-image-2.5-sunburst"


def gen(**kwargs) -> GenerationParams:
    base = dict(prompt="テスト")
    base.update(kwargs)
    return GenerationParams(**base)


def _img(tmp_path, name="base.png"):
    p = tmp_path / name
    p.write_bytes(b"fake-image-bytes")
    return str(p)


# --- quality (3.1-3.3) -----------------------------------------------------

@pytest.mark.parametrize("model", [FLARE, SUNBURST])
@pytest.mark.parametrize("quality", ["low", "medium", "high", "xhigh", "max", "auto"])
def test_2_5_accepts_all_qualities(model, quality):
    assert validate_params(gen(model=model, quality=quality)).quality == quality


@pytest.mark.parametrize("quality", ["xhigh", "max", "auto"])
def test_gpt_image_2_rejects_2_5_only_quality(quality):
    with pytest.raises(ValidationError) as exc:
        validate_params(gen(quality=quality))
    message = str(exc.value)
    assert "'high'" in message and "'low'" in message
    assert "2.5" in message  # 2.5 系なら使えることを案内する


def test_2_5_invalid_quality_message_names_model_and_values():
    with pytest.raises(ValidationError) as exc:
        validate_params(gen(model=FLARE, quality="ultra"))
    message = str(exc.value)
    assert FLARE in message
    assert "'xhigh'" in message and "'max'" in message


# --- background (4.1-4.4) ---------------------------------------------------

@pytest.mark.parametrize("background", ["auto", "opaque", "transparent"])
def test_2_5_accepts_backgrounds(background):
    assert validate_params(gen(model=FLARE, background=background)).background == background


def test_gpt_image_2_rejects_opaque():
    with pytest.raises(ValidationError) as exc:
        validate_params(gen(background="opaque"))
    assert "2.5" in str(exc.value)


def test_2_5_transparent_requires_png_while_webp_disabled():
    with pytest.raises(ValidationError) as exc:
        validate_params(gen(model=FLARE, background="transparent", output_format="jpeg"))
    assert "format=png が必須" in str(exc.value)


def test_transparent_with_webp_when_enabled(monkeypatch):
    monkeypatch.setitem(capabilities.AZURE_ENABLED, "webp", True)
    params = validate_params(gen(model=FLARE, background="transparent", output_format="webp"))
    assert params.output_format == "webp"


# --- size / experimental (5.1-5.4) ------------------------------------------

def test_2_5_experimental_warning_above_2560x1440(capsys):
    validate_params(gen(model=FLARE, size="3840x2160"))
    assert "experimental" in capsys.readouterr().err


def test_2_5_no_warning_at_exactly_2560x1440(capsys):
    validate_params(gen(model=FLARE, size="2560x1440"))
    assert "experimental" not in capsys.readouterr().err


def test_gpt_image_2_no_experimental_warning(capsys):
    validate_params(gen(size="3840x2160"))
    assert "experimental" not in capsys.readouterr().err


def test_2_5_size_constraints_still_enforced():
    with pytest.raises(ValidationError):
        validate_params(gen(model=FLARE, size="1000x1000"))
    with pytest.raises(ValidationError):
        validate_params(gen(model=FLARE, size="3200x1024"))  # 比が 3:1 超


def test_edit_auto_size_skips_warning(tmp_path, capsys):
    validate_edit_params(EditParams(prompt="x", images=(_img(tmp_path),), model=FLARE))
    assert "experimental" not in capsys.readouterr().err


def test_edit_explicit_large_size_warns(tmp_path, capsys):
    validate_edit_params(
        EditParams(prompt="x", images=(_img(tmp_path),), model=FLARE, size="3840x2160")
    )
    assert "experimental" in capsys.readouterr().err


# --- complexity (6.4, 6.5) ---------------------------------------------------

@pytest.mark.parametrize("value", ["low", "medium", "high"])
def test_2_5_accepts_complexity_when_enabled(value, monkeypatch):
    monkeypatch.setitem(capabilities.AZURE_ENABLED, "complexity", True)
    assert validate_params(gen(model=FLARE, complexity=value)).complexity == value


def test_complexity_disabled_by_default():
    with pytest.raises(ValidationError) as exc:
        validate_params(gen(model=FLARE, complexity="low"))
    assert "Azure では現在利用できません" in str(exc.value)


def test_complexity_invalid_value_rejected():
    with pytest.raises(ValidationError):
        validate_params(gen(model=FLARE, complexity="extreme"))


def test_gpt_image_2_rejects_complexity():
    with pytest.raises(ValidationError) as exc:
        validate_params(gen(complexity="low"))
    assert "2.5 系モデル専用" in str(exc.value)


def test_complexity_rejected_when_flag_disabled(monkeypatch):
    monkeypatch.setitem(capabilities.AZURE_ENABLED, "complexity", False)
    with pytest.raises(ValidationError) as exc:
        validate_params(gen(model=FLARE, complexity="low"))
    assert "Azure では現在利用できません" in str(exc.value)


# --- WebP / compression (8.1, 8.2, 8.4) ---------------------------------------

def test_webp_rejected_while_disabled():
    with pytest.raises(ValidationError) as exc:
        validate_params(gen(model=FLARE, output_format="webp"))
    message = str(exc.value)
    assert "Azure では現在利用できません" in message
    assert "'png'" in message and "'jpeg'" in message


def test_gpt_image_2_webp_keeps_existing_message(monkeypatch):
    monkeypatch.setitem(capabilities.AZURE_ENABLED, "webp", True)
    with pytest.raises(ValidationError) as exc:
        validate_params(gen(output_format="webp"))
    assert "WEBP は Azure 非対応" in str(exc.value)


def test_webp_compression_valid_when_enabled(monkeypatch):
    monkeypatch.setitem(capabilities.AZURE_ENABLED, "webp", True)
    params = validate_params(gen(model=FLARE, output_format="webp", output_compression=70))
    assert params.output_compression == 70
    with pytest.raises(ValidationError):
        validate_params(gen(model=FLARE, output_format="webp", output_compression=101))


def test_png_compression_still_warned_and_ignored(capsys):
    params = validate_params(gen(model=FLARE, output_compression=50))
    assert params.output_compression == 100
    assert "compression" in capsys.readouterr().err
