"""2.5 系のリクエスト内容とモデル別タイムアウト（client）のテスト。"""
import base64

import pytest

import capabilities
from client import ApiError, edit, generate
from models import AuthHeader, AzureConfig, EditParams, GenerationParams

CONFIG = AzureConfig(endpoint="https://r.openai.azure.com", deployment="dep")
AUTH = AuthHeader(name="api-key", value="secret-key")
FLARE = "gpt-image-2.5-flare"
OK_BODY = {"data": [{"b64_json": base64.b64encode(b"img").decode()}]}
FAKE_READ = lambda path: f"bytes::{path}".encode()


class FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text

    def json(self):
        return self._json


def make_post(responses):
    calls = []
    iterator = iter(responses)

    def _post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return next(iterator)

    _post.calls = calls
    return _post


def _gen(params, **kw):
    post = make_post([FakeResponse(200, OK_BODY)])
    generate(CONFIG, AUTH, params, http_post=post, sleep=lambda s: None, **kw)
    return post.calls[0]


def _edit(params, **kw):
    post = make_post([FakeResponse(200, OK_BODY)])
    edit(CONFIG, AUTH, params, http_post=post, sleep=lambda s: None, read_bytes=FAKE_READ, **kw)
    return post.calls[0]


# --- complexity (6.2, 6.3) ---------------------------------------------------

def test_generate_includes_complexity_when_set():
    call = _gen(GenerationParams(prompt="x", model=FLARE, quality="xhigh", complexity="low"))
    assert call["json"]["complexity"] == "low"
    assert call["json"]["quality"] == "xhigh"


def test_generate_omits_complexity_when_unset():
    assert "complexity" not in _gen(GenerationParams(prompt="x", model=FLARE))["json"]


def test_edit_includes_complexity_when_set():
    call = _edit(EditParams(prompt="x", images=("a.png",), model=FLARE, complexity="medium"))
    assert call["data"]["complexity"] == "medium"


# --- compression (8.2) -----------------------------------------------------

def test_webp_compression_sent_when_enabled(monkeypatch):
    monkeypatch.setitem(capabilities.AZURE_ENABLED, "webp", True)
    call = _gen(GenerationParams(prompt="x", model=FLARE, output_format="webp",
                                 output_compression=70))
    assert call["json"]["output_compression"] == 70


def test_png_compression_not_sent():
    assert "output_compression" not in _gen(GenerationParams(prompt="x", model=FLARE))["json"]


# --- markup (7.2) ----------------------------------------------------------

def test_edit_sends_markup_part_as_png():
    call = _edit(EditParams(prompt="x", images=("a.png",), model=FLARE, markup="m.png"))
    names = [name for name, _ in call["files"]]
    assert names == ["image[]", "markup"]
    filename, data, mime = dict(call["files"])["markup"]
    assert (filename, data, mime) == ("m.png", b"bytes::m.png", "image/png")
    assert "mask" not in names


# --- gpt-image-2 は新パラメータを送らない (11.2) ---------------------------------

def test_gpt_image_2_request_has_no_new_fields():
    call = _gen(GenerationParams(prompt="x"))
    assert set(call["json"]) == {"prompt", "size", "quality", "n", "output_format", "background"}


# --- タイムアウト (10.1-10.3) --------------------------------------------------

def test_timeouts_follow_model():
    assert _gen(GenerationParams(prompt="x"))["timeout"] == 120.0
    assert _gen(GenerationParams(prompt="x", model=FLARE))["timeout"] == 300.0
    assert _edit(EditParams(prompt="x", images=("a.png",)))["timeout"] == 180.0
    assert _edit(EditParams(prompt="x", images=("a.png",), model=FLARE))["timeout"] == 300.0


def test_explicit_timeout_wins():
    assert _gen(GenerationParams(prompt="x", model=FLARE), timeout=10)["timeout"] == 10


# --- 400 エラーの文言 ---------------------------------------------------------

def test_bad_request_message_mentions_model_and_deployment():
    post = make_post([FakeResponse(400, {"error": {"code": "invalid_value"}})])
    with pytest.raises(ApiError) as exc:
        generate(CONFIG, AUTH, GenerationParams(prompt="x", model=FLARE), http_post=post,
                 sleep=lambda s: None)
    assert exc.value.kind == "bad_request"
    assert "--model" in str(exc.value) and "デプロイ" in str(exc.value)
