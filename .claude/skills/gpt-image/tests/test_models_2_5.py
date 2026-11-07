"""2.5 系対応で追加した共通型フィールドのテスト。"""
from models import AzureConfig, EditParams, GenerationParams


def test_generation_params_new_fields_defaults():
    params = GenerationParams(prompt="x")
    assert params.model == "gpt-image-2"
    assert params.complexity is None


def test_edit_params_new_fields_defaults():
    params = EditParams(prompt="x", images=("a.png",))
    assert params.model == "gpt-image-2"
    assert params.complexity is None
    assert params.markup is None


def test_params_accept_2_5_values():
    params = GenerationParams(
        prompt="x", model="gpt-image-2.5-flare", quality="xhigh",
        background="opaque", output_format="webp", complexity="low",
    )
    assert params.model == "gpt-image-2.5-flare"
    assert params.quality == "xhigh"
    assert params.complexity == "low"


def test_azure_config_new_fields_defaults():
    config = AzureConfig(endpoint="https://r.openai.azure.com", deployment="dep")
    assert config.api_style == "deployments"
    assert config.token_scope == "https://cognitiveservices.azure.com/.default"
