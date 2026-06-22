"""Azure 画像編集 API クライアント（client.edit）のテスト。"""
import base64

import pytest

from client import ApiError, edit
from models import AuthHeader, AzureConfig, EditParams

CONFIG = AzureConfig(endpoint="https://r.openai.azure.com", deployment="dep")
AUTH = AuthHeader(name="api-key", value="secret-key")


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


# read_bytes を注入してディスク IO を回避する
FAKE_READ = lambda path: f"bytes::{path}".encode()


def _params(**kw):
    base = dict(prompt="帽子を赤くする", images=("base.png",))
    base.update(kw)
    return EditParams(**base)


def test_edit_success_returns_decoded_bytes():
    body = {"data": [{"b64_json": _b64(b"edited")}]}
    post = make_post([FakeResponse(200, body)])
    result = edit(CONFIG, AUTH, _params(), http_post=post, sleep=lambda s: None,
                  read_bytes=FAKE_READ)
    assert result == [b"edited"]


def test_edit_targets_edits_endpoint_multipart_without_content_type():
    body = {"data": [{"b64_json": _b64(b"x")}]}
    post = make_post([FakeResponse(200, body)])
    edit(CONFIG, AUTH, _params(), http_post=post, sleep=lambda s: None,
         read_bytes=FAKE_READ)
    call = post.calls[0]
    assert "/openai/deployments/dep/images/edits" in call["url"]
    assert "api-version=2025-04-01-preview" in call["url"]
    # multipart は files= で送られ、Content-Type は requests に任せる
    assert "files" in call
    assert "json" not in call
    assert call["headers"]["api-key"] == "secret-key"
    assert "Content-Type" not in call["headers"]
    # prompt は data フィールドに入る
    assert call["data"]["prompt"] == "帽子を赤くする"


def test_single_image_sent_as_image_array_field():
    body = {"data": [{"b64_json": _b64(b"x")}]}
    post = make_post([FakeResponse(200, body)])
    edit(CONFIG, AUTH, _params(images=("base.png",)), http_post=post,
         sleep=lambda s: None, read_bytes=FAKE_READ)
    files = post.calls[0]["files"]
    image_parts = [f for f in files if f[0] == "image[]"]
    assert len(image_parts) == 1
    # (field, (filename, bytes, mime))
    assert image_parts[0][1][0] == "base.png"
    assert image_parts[0][1][2] == "image/png"


def test_merge_multiple_images_sent_as_repeated_image_array():
    body = {"data": [{"b64_json": _b64(b"x")}]}
    post = make_post([FakeResponse(200, body)])
    edit(CONFIG, AUTH, _params(images=("base.png", "object.jpg")), http_post=post,
         sleep=lambda s: None, read_bytes=FAKE_READ)
    files = post.calls[0]["files"]
    image_parts = [f for f in files if f[0] == "image[]"]
    assert len(image_parts) == 2
    assert image_parts[1][1][2] == "image/jpeg"


def test_mask_sent_when_provided():
    body = {"data": [{"b64_json": _b64(b"x")}]}
    post = make_post([FakeResponse(200, body)])
    edit(CONFIG, AUTH, _params(mask="region.png"), http_post=post,
         sleep=lambda s: None, read_bytes=FAKE_READ)
    files = post.calls[0]["files"]
    mask_parts = [f for f in files if f[0] == "mask"]
    assert len(mask_parts) == 1
    assert mask_parts[0][1][0] == "region.png"


def test_no_mask_field_when_absent():
    body = {"data": [{"b64_json": _b64(b"x")}]}
    post = make_post([FakeResponse(200, body)])
    edit(CONFIG, AUTH, _params(), http_post=post, sleep=lambda s: None,
         read_bytes=FAKE_READ)
    assert all(f[0] != "mask" for f in post.calls[0]["files"])


def test_auto_size_not_sent():
    body = {"data": [{"b64_json": _b64(b"x")}]}
    post = make_post([FakeResponse(200, body)])
    edit(CONFIG, AUTH, _params(size="auto"), http_post=post, sleep=lambda s: None,
         read_bytes=FAKE_READ)
    assert "size" not in post.calls[0]["data"]


def test_explicit_size_sent():
    body = {"data": [{"b64_json": _b64(b"x")}]}
    post = make_post([FakeResponse(200, body)])
    edit(CONFIG, AUTH, _params(size="1024x1024"), http_post=post,
         sleep=lambda s: None, read_bytes=FAKE_READ)
    assert post.calls[0]["data"]["size"] == "1024x1024"


def test_compression_only_sent_for_jpeg():
    body = {"data": [{"b64_json": _b64(b"x")}]}
    post = make_post([FakeResponse(200, body)])
    edit(CONFIG, AUTH, _params(output_format="jpeg", output_compression=70),
         http_post=post, sleep=lambda s: None, read_bytes=FAKE_READ)
    assert post.calls[0]["data"]["output_compression"] == "70"

    post2 = make_post([FakeResponse(200, body)])
    edit(CONFIG, AUTH, _params(), http_post=post2, sleep=lambda s: None,
         read_bytes=FAKE_READ)
    assert "output_compression" not in post2.calls[0]["data"]


def test_429_retries_then_succeeds():
    body = {"data": [{"b64_json": _b64(b"ok")}]}
    post = make_post([FakeResponse(429), FakeResponse(200, body)])
    result = edit(CONFIG, AUTH, _params(), http_post=post, sleep=lambda s: None,
                  max_retries=3, read_bytes=FAKE_READ)
    assert result == [b"ok"]
    assert len(post.calls) == 2


def test_400_moderation_classified():
    body = {"error": {"code": "content_policy_violation", "message": "blocked by safety system"}}
    post = make_post([FakeResponse(400, body, text="content moderation")])
    with pytest.raises(ApiError) as exc:
        edit(CONFIG, AUTH, _params(), http_post=post, sleep=lambda s: None,
             read_bytes=FAKE_READ)
    assert exc.value.kind == "moderation"


def test_edit_error_does_not_leak_secret():
    post = make_post([FakeResponse(401, text="bad")])
    with pytest.raises(ApiError) as exc:
        edit(CONFIG, AUTH, _params(), http_post=post, sleep=lambda s: None,
             read_bytes=FAKE_READ)
    assert "secret-key" not in str(exc.value)
