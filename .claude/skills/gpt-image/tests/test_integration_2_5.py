"""統合テスト（2.5 系）: CLI → 設定 → 検証 → 実クライアント → 保存（HTTP のみ偽物）。

設定は実際の load_config で環境変数から読み、URL・リクエスト本文・タイムアウトまでを確認する。
"""
import base64
import io

import pytest

from client import generate as real_generate
from models import AuthHeader

FAKE_AUTH = AuthHeader(name="api-key", value="k")
FLARE = "gpt-image-2.5-flare"


class FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text

    def json(self):
        return self._json


@pytest.fixture(autouse=True)
def azure_env(monkeypatch):
    for name in ("GPT_IMAGE_MODEL", "GPT_IMAGE_COMPLEXITY", "GPT_IMAGE_QUALITY",
                 "GPT_IMAGE_SIZE", "GPT_IMAGE_FORMAT", "GPT_IMAGE_BACKGROUND",
                 "GPT_IMAGE_COMPRESSION", "GPT_IMAGE_N", "GPT_IMAGE_USER",
                 "AZURE_OPENAI_API_VERSION", "AZURE_OPENAI_API_STYLE",
                 "AZURE_OPENAI_TOKEN_SCOPE", "AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2",
                 "AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_FLARE",
                 "AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_SUNBURST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://r.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "common-dep")


def _run(argv, tmp_path):
    import generate_image

    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse(200, {"data": [{"b64_json": base64.b64encode(b"img").decode()}]})

    def generate_via_real_client(config, auth, params):
        return real_generate(config, auth, params, http_post=fake_post, sleep=lambda s: None)

    out, err = io.StringIO(), io.StringIO()
    code = generate_image.run(
        argv + ["--output", str(tmp_path)], out=out, err=err,
        load_api_key=lambda: "k",
        resolve_auth=lambda api_key, **kw: FAKE_AUTH,
        generate=generate_via_real_client,
    )
    return code, out.getvalue(), err.getvalue(), calls


def test_flare_full_request(tmp_path, monkeypatch):
    import capabilities

    monkeypatch.setitem(capabilities.AZURE_ENABLED, "complexity", True)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_FLARE", "flare-dep")
    code, out, err, calls = _run(
        ["--prompt", "猫", "--model", FLARE, "--quality", "xhigh",
         "--background", "opaque", "--complexity", "low"], tmp_path)
    assert code == 0, err
    call = calls[0]
    assert call["url"] == (
        "https://r.openai.azure.com/openai/deployments/flare-dep/images/generations"
        "?api-version=2025-04-01-preview"
    )
    assert call["json"]["quality"] == "xhigh"
    assert call["json"]["background"] == "opaque"
    assert call["json"]["complexity"] == "low"
    assert call["timeout"] == 300.0
    assert len(out.strip().splitlines()) == 1


def test_model_from_env_uses_model_deployment(tmp_path, monkeypatch):
    monkeypatch.setenv("GPT_IMAGE_MODEL", "gpt-image-2.5-sunburst")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_SUNBURST", "sun-dep")
    code, _, err, calls = _run(["--prompt", "猫"], tmp_path)
    assert code == 0, err
    assert "/deployments/sun-dep/" in calls[0]["url"]


def test_v1_style_request(tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_STYLE", "v1")
    code, _, err, calls = _run(["--prompt", "猫", "--model", FLARE], tmp_path)
    assert code == 0, err
    assert calls[0]["url"] == (
        "https://r.openai.azure.com/openai/v1/images/generations?api-version=preview"
    )
    assert calls[0]["json"]["model"] == "common-dep"


def test_default_model_request_is_unchanged(tmp_path):
    code, out, err, calls = _run(["--prompt", "猫"], tmp_path)
    assert code == 0, err
    call = calls[0]
    assert call["url"] == (
        "https://r.openai.azure.com/openai/deployments/common-dep/images/generations"
        "?api-version=2025-04-01-preview"
    )
    assert call["json"] == {
        "prompt": "猫", "size": "1024x1024", "quality": "high", "n": 1,
        "output_format": "png", "background": "auto",
    }
    assert call["timeout"] == 120.0
    assert err == ""
    assert len(out.strip().splitlines()) == 1


def test_disabled_complexity_rejected_before_api(tmp_path):
    code, _, err, calls = _run(["--prompt", "猫", "--model", FLARE, "--complexity", "low"],
                               tmp_path)
    assert code != 0
    assert calls == []
    assert "Azure では現在利用できません" in err


def test_default_model_rejects_2_5_only_value_before_api(tmp_path):
    code, _, err, calls = _run(["--prompt", "猫", "--quality", "max"], tmp_path)
    assert code != 0
    assert calls == []
    assert "パラメータエラー" in err
