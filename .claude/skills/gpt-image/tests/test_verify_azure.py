"""Azure 実機確認ツール（tests/live/verify_azure.py）のテスト。

実際の API は呼ばず、偽の送信処理で、送る項目・結果の表・シークレットを含まないことを確認する。
"""
import io
import os
import sys
import zlib

import pytest

LIVE_DIR = os.path.join(os.path.dirname(__file__), "live")
if LIVE_DIR not in sys.path:
    sys.path.insert(0, LIVE_DIR)

import verify_azure  # noqa: E402
from client import RawResponse  # noqa: E402
from image_info import read_dimensions  # noqa: E402
from models import AuthHeader, AzureConfig  # noqa: E402

CONFIG = AzureConfig(endpoint="https://secret-resource.openai.azure.com",
                     deployment="secret-deployment")
FLARE = "gpt-image-2.5-flare"


class FakePost:
    """項目ごとの送信内容を記録し、complexity だけ拒否する偽の post_raw。"""

    def __init__(self):
        self.calls = []

    def __call__(self, config, auth, operation, *, json_body=None, form=None, files=None,
                 timeout, http_post=None):
        self.calls.append(dict(api_style=config.api_style, auth=auth, operation=operation,
                               json_body=json_body, form=form, files=files))
        body = json_body or form or {}
        if "complexity" in body:
            return RawResponse(status=400, body={"error": {
                "code": "unknown_parameter", "message": "Unrecognized | param\ncomplexity"}})
        return RawResponse(status=200, body={"data": [{"b64_json": "AAAA"}]})


def fake_resolve(api_key, *, scope, **kw):
    return AuthHeader(name="Authorization", value=f"Bearer token-for-{scope}")


def _run(api_styles=("deployments", "v1")):
    post = FakePost()
    results = verify_azure.run_probes(
        CONFIG, FLARE, api_key=None, api_styles=api_styles,
        post=post, resolve=fake_resolve,
    )
    return post, results


def test_probe_items_cover_required_checks():
    items = {p.item for p in verify_azure.build_probes()}
    assert items == {
        "quality=xhigh", "quality=max", "quality=auto",
        "background=opaque", "background=transparent",
        "output_format=webp", "complexity=low", "edits markup",
    }


def test_each_probe_sent_per_style_and_v1_tries_both_scopes():
    post, results = _run()
    probes = len(verify_azure.build_probes())
    deployments = [c for c in post.calls if c["api_style"] == "deployments"]
    v1 = [c for c in post.calls if c["api_style"] == "v1"]
    assert len(deployments) == probes
    assert len(v1) == probes * 2
    v1_scopes = {r.token_scope for r in results if r.api_style == "v1"}
    assert v1_scopes == {"https://cognitiveservices.azure.com/.default",
                         "https://ai.azure.com/.default"}


def test_api_key_auth_does_not_repeat_scopes():
    post = FakePost()
    results = verify_azure.run_probes(
        CONFIG, FLARE, api_key="k", api_styles=("v1",), post=post,
        resolve=lambda api_key, *, scope, **kw: AuthHeader(name="api-key", value=api_key),
    )
    assert len(post.calls) == len(verify_azure.build_probes())
    assert {r.token_scope for r in results} == {"(api-key)"}


def test_cost_saving_defaults_and_checked_value():
    post, _ = _run(api_styles=("deployments",))
    gen_calls = [c for c in post.calls if c["operation"] == "generations"]
    for call in gen_calls:
        body = call["json_body"]
        assert body["size"] == "1024x1024" and body["n"] == 1
    xhigh = [c for c in gen_calls if c["json_body"]["quality"] == "xhigh"]
    assert len(xhigh) == 1
    others = [c for c in gen_calls if c["json_body"]["quality"] not in ("xhigh", "max", "auto")]
    assert all(c["json_body"]["quality"] == "low" for c in others)


def test_markup_probe_sends_matching_png_parts():
    post, _ = _run(api_styles=("deployments",))
    edit_call = next(c for c in post.calls if c["operation"] == "edits")
    parts = dict(edit_call["files"])
    assert set(parts) == {"image[]", "markup"}
    for name in ("image[]", "markup"):
        filename, data, mime = parts[name]
        assert mime == "image/png"
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert edit_call["form"]["quality"] == "low"


def test_results_record_acceptance_and_errors():
    _, results = _run(api_styles=("deployments",))
    by_item = {r.item: r for r in results}
    assert by_item["quality=xhigh"].accepted is True
    assert by_item["complexity=low"].accepted is False
    assert by_item["complexity=low"].status == 400
    assert by_item["complexity=low"].error_code == "unknown_parameter"


def test_markdown_table_has_no_secrets_and_escapes_cells():
    _, results = _run()
    md = verify_azure.to_markdown(FLARE, results)
    assert md.count("\n|") >= len(results) + 1
    assert "complexity=low" in md
    for secret in ("secret-resource", "secret-deployment", "Bearer", "token-for"):
        assert secret not in md
    row = next(line for line in md.splitlines() if line.startswith("| complexity=low"))
    assert "Unrecognized \\| param complexity" in row


def test_main_without_env_exits_without_calling_api(monkeypatch, capsys):
    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT",
                 "AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_FLARE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(verify_azure.config_module, "load_project_dotenv", lambda: None)
    called = []
    monkeypatch.setattr(verify_azure, "run_probes", lambda *a, **k: called.append(1))
    code = verify_azure.main(["--model", FLARE])
    assert code != 0
    assert called == []
    assert "AZURE_OPENAI_ENDPOINT" in capsys.readouterr().err


def test_items_filter_limits_probes():
    post = FakePost()
    results = verify_azure.run_probes(
        CONFIG, FLARE, api_key=None, api_styles=("deployments",), post=post,
        resolve=fake_resolve, items=["background=transparent", "output_format=webp"],
    )
    assert [r.item for r in results] == ["background=transparent", "output_format=webp"]


def test_unknown_item_rejected():
    with pytest.raises(ValueError):
        verify_azure.run_probes(CONFIG, FLARE, api_key=None, post=FakePost(),
                                resolve=fake_resolve, items=["quality=ultra"])


def test_rate_limit_backoff_is_long_enough():
    responses = iter([RawResponse(429, {}), RawResponse(429, {}),
                      RawResponse(200, {"data": []})])
    slept = []

    def post(*args, **kwargs):
        return next(responses)

    results = verify_azure.run_probes(
        CONFIG, FLARE, api_key=None, api_styles=("deployments",), post=post,
        resolve=fake_resolve, items=["quality=xhigh"], sleep=slept.append,
    )
    assert results[0].accepted is True
    assert slept == list(verify_azure.RATE_LIMIT_BACKOFF[:2])
    assert sum(verify_azure.RATE_LIMIT_BACKOFF) >= 60


def test_delay_between_probes():
    slept = []
    verify_azure.run_probes(
        CONFIG, FLARE, api_key=None, api_styles=("deployments",), post=FakePost(),
        resolve=fake_resolve, items=["quality=xhigh", "quality=max", "quality=auto"],
        sleep=slept.append, delay=12,
    )
    assert slept == [12, 12]  # 最初の項目の前には待たない


def test_generated_png_is_valid(tmp_path):
    data = verify_azure.make_png(1024, 1024, (255, 0, 0, 0))
    path = tmp_path / "x.png"
    path.write_bytes(data)
    dims = read_dimensions(str(path))
    assert (dims.width, dims.height) == (1024, 1024)
    # IDAT が zlib で展開できる（正しい PNG）
    idat_start = data.index(b"IDAT") + 4
    length = int.from_bytes(data[idat_start - 8:idat_start - 4], "big")
    raw = zlib.decompress(data[idat_start:idat_start + length])
    assert len(raw) == 1024 * (1 + 1024 * 4)


def test_not_collected_by_pytest():
    assert not os.path.basename(verify_azure.__file__).startswith("test_")
