"""設定読み込み（config）のテスト。"""
import pytest

import config
from config import ConfigError, load_api_key, load_config
from models import AzureConfig


def test_load_config_success(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://r.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "my-deploy")
    cfg = load_config()
    assert isinstance(cfg, AzureConfig)
    assert cfg.endpoint == "https://r.openai.azure.com"
    assert cfg.deployment == "my-deploy"
    assert cfg.api_version == "2025-04-01-preview"


def test_load_config_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://r.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "d")
    assert load_config().endpoint == "https://r.openai.azure.com"


def test_load_config_missing_endpoint_raises(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "d")
    with pytest.raises(ConfigError):
        load_config()


def test_load_config_respects_custom_api_version(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://r.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "d")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01")
    assert load_config().api_version == "2025-04-01"


def test_missing_config_error_does_not_leak_key_value(monkeypatch):
    """必須未設定エラーに API キーの値が含まれないこと。"""
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "super-secret-key-value")
    with pytest.raises(ConfigError) as exc:
        load_config()
    assert "super-secret-key-value" not in str(exc.value)


def test_load_api_key_returns_value_or_none(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    assert load_api_key() is None
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    assert load_api_key() == "k"
