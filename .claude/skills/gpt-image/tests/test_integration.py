"""統合テスト: CLI → 検証 → 認証 → 実クライアント → 実保存（API のみモック）。

run() に対し、実 client.generate を fake な http_post で駆動する generate 関数を注入し、
b64 デコード・保存・stdout 出力までの一連を検証する。
"""
import base64
import io

from client import generate as real_generate
from models import AuthHeader, AzureConfig

FAKE_CONFIG = AzureConfig(endpoint="https://r.openai.azure.com", deployment="dep")
FAKE_AUTH = AuthHeader(name="api-key", value="k")


class FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text

    def json(self):
        return self._json


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _ok_body(n: int):
    return {"data": [{"b64_json": _b64(f"img-{i}".encode())} for i in range(n)]}


def _make_run_deps(responses):
    """実 client.generate を fake post で動かす generate を注入するための deps。"""
    iterator = iter(responses)

    def fake_post(url, **kwargs):
        return next(iterator)

    def generate_via_real_client(config, auth, params):
        return real_generate(
            config, auth, params, http_post=fake_post, sleep=lambda s: None
        )

    return dict(
        load_config=lambda: FAKE_CONFIG,
        load_api_key=lambda: "k",
        resolve_auth=lambda api_key, **kw: FAKE_AUTH,
        generate=generate_via_real_client,
    )


def _run(argv, responses):
    import generate_image

    out, err = io.StringIO(), io.StringIO()
    code = generate_image.run(argv, out=out, err=err, **_make_run_deps(responses))
    return code, out.getvalue(), err.getvalue()


def test_prompt_only_default_full_stack(tmp_path):
    code, out, err = _run(
        ["--prompt", "夕暮れの東京タワー", "--output", str(tmp_path)],
        [FakeResponse(200, _ok_body(1))],
    )
    assert code == 0, err
    paths = out.strip().splitlines()
    assert len(paths) == 1
    with open(paths[0], "rb") as f:
        assert f.read() == b"img-0"


def test_n3_sequential_full_stack(tmp_path):
    code, out, err = _run(
        ["--prompt", "x", "--n", "3", "--output", str(tmp_path)],
        [FakeResponse(200, _ok_body(3))],
    )
    assert code == 0, err
    paths = out.strip().splitlines()
    assert len(paths) == 3
    assert [p[-5] for p in paths] == ["0", "1", "2"]  # 連番 index


def test_429_retry_then_success_full_stack(tmp_path):
    code, out, err = _run(
        ["--prompt", "x", "--output", str(tmp_path)],
        [FakeResponse(429), FakeResponse(200, _ok_body(1))],
    )
    assert code == 0, err
    assert len(out.strip().splitlines()) == 1


def test_moderation_400_reports_user_message(tmp_path):
    body = {"error": {"code": "content_policy_violation", "message": "blocked"}}
    code, out, err = _run(
        ["--prompt", "危険な内容", "--output", str(tmp_path)],
        [FakeResponse(400, body, text="content moderation")],
    )
    assert code != 0
    assert "モデレーション" in err
    assert out.strip() == ""  # 失敗時は stdout にパスを出さない
