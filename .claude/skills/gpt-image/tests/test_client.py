"""Azure 画像生成 API クライアント（client）のテスト。"""
import base64

import pytest

from client import ApiError, generate
from models import AuthHeader, AzureConfig, GenerationParams

CONFIG = AzureConfig(endpoint="https://r.openai.azure.com", deployment="dep")
AUTH = AuthHeader(name="api-key", value="secret-key")
PARAMS = GenerationParams(prompt="猫")


class FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text

    def json(self):
        return self._json


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def make_post(responses):
    """呼び出しごとに responses を順に返すフェイク post。呼び出し記録を保持。"""
    calls = []
    iterator = iter(responses)

    def _post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return next(iterator)

    _post.calls = calls
    return _post


def test_success_returns_decoded_bytes():
    body = {"data": [{"b64_json": _b64(b"img-bytes")}]}
    post = make_post([FakeResponse(200, body)])
    result = generate(CONFIG, AUTH, PARAMS, http_post=post, sleep=lambda s: None)
    assert result == [b"img-bytes"]


def test_request_targets_deployment_endpoint_with_auth_header():
    body = {"data": [{"b64_json": _b64(b"x")}]}
    post = make_post([FakeResponse(200, body)])
    generate(CONFIG, AUTH, PARAMS, http_post=post, sleep=lambda s: None)
    call = post.calls[0]
    assert "/openai/deployments/dep/images/generations" in call["url"]
    assert "api-version=2025-04-01-preview" in call["url"]
    assert call["headers"]["api-key"] == "secret-key"
    assert call["json"]["prompt"] == "猫"


def test_compression_only_sent_for_jpeg():
    body = {"data": [{"b64_json": _b64(b"x")}]}
    jpeg_params = GenerationParams(prompt="x", output_format="jpeg", output_compression=70)
    post = make_post([FakeResponse(200, body)])
    generate(CONFIG, AUTH, jpeg_params, http_post=post, sleep=lambda s: None)
    assert post.calls[0]["json"]["output_compression"] == 70

    post2 = make_post([FakeResponse(200, body)])
    generate(CONFIG, AUTH, GenerationParams(prompt="x"), http_post=post2, sleep=lambda s: None)
    assert "output_compression" not in post2.calls[0]["json"]


def test_429_retries_then_succeeds():
    body = {"data": [{"b64_json": _b64(b"ok")}]}
    post = make_post([FakeResponse(429), FakeResponse(429), FakeResponse(200, body)])
    result = generate(CONFIG, AUTH, PARAMS, http_post=post, sleep=lambda s: None, max_retries=3)
    assert result == [b"ok"]
    assert len(post.calls) == 3


def test_429_exhausted_raises_rate_limit():
    post = make_post([FakeResponse(429)] * 5)
    with pytest.raises(ApiError) as exc:
        generate(CONFIG, AUTH, PARAMS, http_post=post, sleep=lambda s: None, max_retries=2)
    assert exc.value.kind == "rate_limit"


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "auth")])
def test_auth_errors_classified(status, kind):
    post = make_post([FakeResponse(status, text="unauthorized")])
    with pytest.raises(ApiError) as exc:
        generate(CONFIG, AUTH, PARAMS, http_post=post, sleep=lambda s: None)
    assert exc.value.kind == kind


def test_400_moderation_classified():
    body = {"error": {"code": "content_policy_violation", "message": "blocked by safety system"}}
    post = make_post([FakeResponse(400, body, text="content moderation")])
    with pytest.raises(ApiError) as exc:
        generate(CONFIG, AUTH, PARAMS, http_post=post, sleep=lambda s: None)
    assert exc.value.kind == "moderation"


def test_400_generic_bad_request():
    body = {"error": {"code": "invalid_request", "message": "bad param"}}
    post = make_post([FakeResponse(400, body)])
    with pytest.raises(ApiError) as exc:
        generate(CONFIG, AUTH, PARAMS, http_post=post, sleep=lambda s: None)
    assert exc.value.kind == "bad_request"


def test_timeout_classified():
    import requests

    def _post(url, **kwargs):
        raise requests.exceptions.Timeout("timed out")

    with pytest.raises(ApiError) as exc:
        generate(CONFIG, AUTH, PARAMS, http_post=_post, sleep=lambda s: None)
    assert exc.value.kind == "timeout"


def test_error_does_not_leak_secret():
    post = make_post([FakeResponse(401, text="bad")])
    with pytest.raises(ApiError) as exc:
        generate(CONFIG, AUTH, PARAMS, http_post=post, sleep=lambda s: None)
    assert "secret-key" not in str(exc.value)
