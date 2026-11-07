"""モデル種別ごとのデプロイ・API 形式・トークンのスコープの解決（config）のテスト。"""
import pytest

from config import ConfigError, load_config

ENV_NAMES = [
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2",
    "AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_FLARE",
    "AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_SUNBURST",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_API_STYLE",
    "AZURE_OPENAI_TOKEN_SCOPE",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://r.openai.azure.com")


# --- デプロイ名の解決 (2.1-2.4) --------------------------------------------

def test_model_specific_deployment_preferred(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "common")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_FLARE", "flare-dep")
    assert load_config("gpt-image-2.5-flare").deployment == "flare-dep"


def test_falls_back_to_common_deployment(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "common")
    assert load_config("gpt-image-2.5-sunburst").deployment == "common"


def test_model_specific_alone_is_enough(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_SUNBURST", "sun-dep")
    assert load_config("gpt-image-2.5-sunburst").deployment == "sun-dep"


def test_default_model_reads_its_own_env_then_common(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "common")
    assert load_config().deployment == "common"
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2", "v2-dep")
    assert load_config().deployment == "v2-dep"


def test_missing_deployment_names_both_env_vars():
    with pytest.raises(ConfigError) as exc:
        load_config("gpt-image-2.5-flare")
    message = str(exc.value)
    assert "AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_FLARE" in message
    assert "AZURE_OPENAI_DEPLOYMENT" in message


def test_deployment_name_does_not_imply_model(monkeypatch):
    # デプロイ名に "sunburst" が含まれていても、モデル種別の判定には使わない
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "my-sunburst")
    cfg = load_config()
    assert cfg.deployment == "my-sunburst"
    assert cfg.api_style == "deployments"


# --- API 形式とトークンのスコープ (9.5) -------------------------------------

def test_api_style_defaults(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "d")
    cfg = load_config()
    assert cfg.api_style == "deployments"
    assert cfg.api_version == "2025-04-01-preview"
    assert cfg.token_scope == "https://cognitiveservices.azure.com/.default"


def test_v1_style_defaults_api_version_to_preview(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "d")
    monkeypatch.setenv("AZURE_OPENAI_API_STYLE", "v1")
    cfg = load_config()
    assert cfg.api_style == "v1"
    assert cfg.api_version == "preview"


def test_v1_style_respects_explicit_api_version(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "d")
    monkeypatch.setenv("AZURE_OPENAI_API_STYLE", "v1")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "v1")
    assert load_config().api_version == "v1"


def test_invalid_api_style_rejected(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "d")
    monkeypatch.setenv("AZURE_OPENAI_API_STYLE", "v2")
    with pytest.raises(ConfigError) as exc:
        load_config()
    assert "deployments" in str(exc.value) and "v1" in str(exc.value)


def test_token_scope_override(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "d")
    monkeypatch.setenv("AZURE_OPENAI_TOKEN_SCOPE", "https://ai.azure.com/.default")
    assert load_config().token_scope == "https://ai.azure.com/.default"
