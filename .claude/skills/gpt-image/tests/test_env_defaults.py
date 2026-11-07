"""パラメータ既定値の .env / 環境変数オーバーライドのテスト。

優先順位: CLI 引数 > 環境変数(.env) > 組み込み既定。
"""
import pytest

import generate_image
from models import GenerationParams

PARAM_ENV_VARS = [
    "GPT_IMAGE_SIZE", "GPT_IMAGE_QUALITY", "GPT_IMAGE_FORMAT",
    "GPT_IMAGE_BACKGROUND", "GPT_IMAGE_COMPRESSION", "GPT_IMAGE_N",
    "GPT_IMAGE_OUTPUT_DIR", "GPT_IMAGE_USER",
]


@pytest.fixture(autouse=True)
def clear_param_env(monkeypatch):
    for name in PARAM_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_builtin_defaults_when_no_env():
    assert generate_image.parse_args(["--prompt", "犬"]) == GenerationParams(prompt="犬")


def test_env_overrides_builtin_defaults(monkeypatch):
    monkeypatch.setenv("GPT_IMAGE_SIZE", "1536x1024")
    monkeypatch.setenv("GPT_IMAGE_QUALITY", "low")
    monkeypatch.setenv("GPT_IMAGE_FORMAT", "jpeg")
    monkeypatch.setenv("GPT_IMAGE_BACKGROUND", "auto")
    monkeypatch.setenv("GPT_IMAGE_COMPRESSION", "70")
    monkeypatch.setenv("GPT_IMAGE_N", "2")
    monkeypatch.setenv("GPT_IMAGE_OUTPUT_DIR", "./pics")
    monkeypatch.setenv("GPT_IMAGE_USER", "team-a")

    params = generate_image.parse_args(["--prompt", "猫"])
    assert params.size == "1536x1024"
    assert params.quality == "low"
    assert params.output_format == "jpeg"
    assert params.output_compression == 70
    assert params.n == 2
    assert params.output_dir == "./pics"
    assert params.user == "team-a"


def test_cli_overrides_env(monkeypatch):
    monkeypatch.setenv("GPT_IMAGE_SIZE", "1536x1024")
    monkeypatch.setenv("GPT_IMAGE_N", "5")
    params = generate_image.parse_args(["--prompt", "x", "--size", "1024x1536", "--n", "1"])
    assert params.size == "1024x1536"   # CLI が環境変数より優先
    assert params.n == 1


def test_empty_env_value_falls_back_to_builtin(monkeypatch):
    monkeypatch.setenv("GPT_IMAGE_SIZE", "")
    assert generate_image.parse_args(["--prompt", "x"]).size == "1024x1024"


def test_invalid_int_env_is_usage_error(monkeypatch):
    monkeypatch.setenv("GPT_IMAGE_N", "abc")
    with pytest.raises(SystemExit):
        generate_image.parse_args(["--prompt", "x"])
