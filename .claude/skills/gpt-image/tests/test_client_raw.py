"""URL 組み立て（build_url）と検証を通さない送信（post_raw）のテスト。"""
import base64
from dataclasses import replace

import pytest

from client import ApiError, RawResponse, build_url, generate, post_raw
from models import AuthHeader, AzureConfig, GenerationParams

CONFIG = AzureConfig(endpoint="https://r.openai.azure.com", deployment="dep")
V1_CONFIG = replace(CONFIG, api_style="v1", api_version="preview")
AUTH = AuthHeader(name="api-key", value="secret-key")


class FakeResponse:
    def __init__(self, status_code, json_body=None, text="", json_error=False):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._json


def make_post(responses):
    calls = []
    iterator = iter(responses)

    def _post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return next(iterator)

    _post.calls = calls
    return _post


# --- build_url (9.5) --------------------------------------------------------

def test_build_url_deployments_style():
    assert build_url(CONFIG, "generations") == (
        "https://r.openai.azure.com/openai/deployments/dep/images/generations"
        "?api-version=2025-04-01-preview"
    )


def test_build_url_v1_style():
    assert build_url(V1_CONFIG, "edits") == (
        "https://r.openai.azure.com/openai/v1/images/edits?api-version=preview"
    )


# --- post_raw (9.1) ---------------------------------------------------------

def test_post_raw_returns_error_status_without_raising():
    post = make_post([FakeResponse(400, {"error": {"code": "invalid_value"}})])
    result = post_raw(CONFIG, AUTH, "generations", json_body={"prompt": "x"},
                      timeout=5, http_post=post)
    assert result == RawResponse(status=400, body={"error": {"code": "invalid_value"}})


def test_post_raw_non_json_body_kept_as_text():
    post = make_post([FakeResponse(500, text="boom", json_error=True)])
    result = post_raw(CONFIG, AUTH, "generations", json_body={"prompt": "x"},
                      timeout=5, http_post=post)
    assert result.status == 500
    assert result.body == {"raw_text": "boom"}


def test_post_raw_json_sets_content_type_and_auth_header():
    post = make_post([FakeResponse(200, {"data": []})])
    post_raw(CONFIG, AUTH, "generations", json_body={"prompt": "x"}, timeout=7, http_post=post)
    call = post.calls[0]
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["headers"]["api-key"] == "secret-key"
    assert call["json"] == {"prompt": "x"}
    assert call["timeout"] == 7


def test_post_raw_v1_adds_model_to_json():
    post = make_post([FakeResponse(200, {})])
    post_raw(V1_CONFIG, AUTH, "generations", json_body={"prompt": "x"}, timeout=5, http_post=post)
    assert post.calls[0]["json"] == {"prompt": "x", "model": "dep"}


def test_post_raw_v1_adds_model_to_form():
    post = make_post([FakeResponse(200, {})])
    files = [("image[]", ("a.png", b"png", "image/png"))]
    post_raw(V1_CONFIG, AUTH, "edits", form={"prompt": "x"}, files=files, timeout=5,
             http_post=post)
    call = post.calls[0]
    assert call["data"] == {"prompt": "x", "model": "dep"}
    assert call["files"] == files
    assert "Content-Type" not in call["headers"]


def test_post_raw_deployments_does_not_add_model():
    post = make_post([FakeResponse(200, {})])
    post_raw(CONFIG, AUTH, "generations", json_body={"prompt": "x"}, timeout=5, http_post=post)
    assert "model" not in post.calls[0]["json"]


def test_post_raw_requires_exactly_one_body_kind():
    with pytest.raises(ValueError):
        post_raw(CONFIG, AUTH, "generations", timeout=5, http_post=make_post([]))
    with pytest.raises(ValueError):
        post_raw(CONFIG, AUTH, "edits", json_body={"a": 1}, form={"b": "2"}, timeout=5,
                 http_post=make_post([]))


def test_post_raw_timeout_raises_api_error():
    import requests

    def post(url, **kwargs):
        raise requests.exceptions.Timeout()

    with pytest.raises(ApiError) as exc:
        post_raw(CONFIG, AUTH, "generations", json_body={}, timeout=3, http_post=post)
    assert exc.value.kind == "timeout"


def test_generate_uses_v1_url_and_model():
    body = {"data": [{"b64_json": base64.b64encode(b"img").decode()}]}
    post = make_post([FakeResponse(200, body)])
    result = generate(V1_CONFIG, AUTH, GenerationParams(prompt="猫"), http_post=post,
                      sleep=lambda s: None)
    assert result == [b"img"]
    assert post.calls[0]["url"].endswith("/openai/v1/images/generations?api-version=preview")
    assert post.calls[0]["json"]["model"] == "dep"
