"""モデル種別ごとの対応表（capabilities）のテスト。"""
import pytest

import capabilities
import validation
from capabilities import (
    DEFAULT_MODEL,
    MODEL_NAMES,
    allowed_formats,
    compression_formats,
    get_capability,
    is_feature_enabled,
    transparent_formats,
)


def test_model_names_and_default():
    assert MODEL_NAMES == ("gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst")
    assert DEFAULT_MODEL == "gpt-image-2"


def test_unknown_model_raises_key_error():
    with pytest.raises(KeyError):
        get_capability("gpt-image-9")


def test_gpt_image_2_matches_existing_constants():
    cap = get_capability("gpt-image-2")
    assert cap.qualities == frozenset(validation.VALID_QUALITY)
    assert cap.backgrounds == frozenset(validation.VALID_BACKGROUND)
    assert allowed_formats(cap) == frozenset(validation.VALID_FORMAT)
    assert cap.declared_features == frozenset()
    assert cap.experimental_pixels is None
    assert (cap.timeout_generate, cap.timeout_edit) == (120.0, 180.0)


@pytest.mark.parametrize("model", ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"])
def test_2_5_values(model):
    cap = get_capability(model)
    assert cap.qualities == {"low", "medium", "high", "xhigh", "max", "auto"}
    assert cap.backgrounds == {"auto", "opaque", "transparent"}
    assert cap.declared_features == {"complexity", "markup", "webp"}
    assert cap.experimental_pixels == 2560 * 1440
    assert (cap.timeout_generate, cap.timeout_edit) == (300.0, 300.0)


def test_deployment_env_naming():
    assert get_capability("gpt-image-2").deployment_env == "AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2"
    assert (get_capability("gpt-image-2.5-flare").deployment_env
            == "AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_FLARE")
    assert (get_capability("gpt-image-2.5-sunburst").deployment_env
            == "AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_SUNBURST")


def test_initial_flags():
    # 2026-11-07 の Azure 実機確認の結果（complexity / markup は Unknown parameter で拒否）
    assert capabilities.AZURE_ENABLED == {"complexity": False, "markup": False, "webp": False}


def test_feature_requires_declaration_and_flag(monkeypatch):
    flare = get_capability("gpt-image-2.5-flare")
    v2 = get_capability("gpt-image-2")
    assert not is_feature_enabled(flare, "complexity")
    assert not is_feature_enabled(flare, "webp")

    monkeypatch.setitem(capabilities.AZURE_ENABLED, "complexity", True)
    monkeypatch.setitem(capabilities.AZURE_ENABLED, "webp", True)
    assert is_feature_enabled(flare, "complexity")
    assert is_feature_enabled(flare, "webp")
    # gpt-image-2 は宣言上対応していないため、フラグが有効でも使えない
    assert not is_feature_enabled(v2, "complexity")
    assert not is_feature_enabled(v2, "webp")


def test_format_sets_follow_webp_flag(monkeypatch):
    flare = get_capability("gpt-image-2.5-flare")
    assert allowed_formats(flare) == {"png", "jpeg"}
    assert transparent_formats(flare) == {"png"}
    assert compression_formats(flare) == {"jpeg"}

    monkeypatch.setitem(capabilities.AZURE_ENABLED, "webp", True)
    assert allowed_formats(flare) == {"png", "jpeg", "webp"}
    assert transparent_formats(flare) == {"png", "webp"}
    assert compression_formats(flare) == {"jpeg", "webp"}
