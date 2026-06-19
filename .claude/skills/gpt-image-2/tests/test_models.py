"""共通型（models）のテスト。"""
from models import AzureConfig, GenerationParams


def test_generation_params_defaults():
    params = GenerationParams(prompt="夕暮れの東京タワー")
    assert params.prompt == "夕暮れの東京タワー"
    assert params.size == "1024x1024"
    assert params.quality == "high"
    assert params.output_format == "png"
    assert params.background == "auto"
    assert params.output_compression == 100
    assert params.n == 1
    assert params.user is None
    assert params.output_dir == "./images"


def test_generation_params_is_frozen():
    params = GenerationParams(prompt="x")
    try:
        params.prompt = "y"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("GenerationParams は不変であるべき")


def test_azure_config_default_api_version():
    config = AzureConfig(endpoint="https://r.openai.azure.com", deployment="dep")
    assert config.api_version == "2025-04-01-preview"
