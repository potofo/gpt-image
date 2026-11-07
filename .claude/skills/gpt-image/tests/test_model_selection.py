"""CLI からのモデル種別・complexity・markup の指定のテスト。"""
import io
import struct
import zlib

import pytest

import edit_image
import generate_image
from models import AuthHeader, AzureConfig

FAKE_CONFIG = AzureConfig(endpoint="https://r.openai.azure.com", deployment="dep",
                          token_scope="scope-x")
FAKE_AUTH = AuthHeader(name="api-key", value="k")
FLARE = "gpt-image-2.5-flare"


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for name in ("GPT_IMAGE_MODEL", "GPT_IMAGE_COMPLEXITY", "GPT_IMAGE_QUALITY",
                 "GPT_IMAGE_FORMAT", "GPT_IMAGE_BACKGROUND"):
        monkeypatch.delenv(name, raising=False)


class Recorder:
    """注入した依存の呼ばれ方を記録する。"""

    def __init__(self):
        self.load_config_args = None
        self.auth_kwargs = None
        self.params = None

    def load_config(self, *args):
        self.load_config_args = args
        return FAKE_CONFIG

    def resolve_auth(self, api_key, **kw):
        self.auth_kwargs = kw
        return FAKE_AUTH

    def call(self, config, auth, params, **kw):
        self.params = params
        return [b"img"] * params.n


def _run_generate(argv, tmp_path, rec):
    out, err = io.StringIO(), io.StringIO()
    code = generate_image.run(
        argv + ["--output", str(tmp_path)], out=out, err=err,
        load_config=rec.load_config, load_api_key=lambda: "k",
        resolve_auth=rec.resolve_auth, generate=rec.call,
    )
    return code, out.getvalue(), err.getvalue()


# --- 生成 CLI (1.2, 1.3, 2.5, 3.4, 6.1, 11.1) ---------------------------------

def test_generate_defaults_model_and_complexity():
    params = generate_image.parse_args(["--prompt", "犬"])
    assert params.model == "gpt-image-2"
    assert params.complexity is None
    assert params.quality == "high"


def test_generate_model_priority(monkeypatch):
    monkeypatch.setenv("GPT_IMAGE_MODEL", "gpt-image-2.5-sunburst")
    assert generate_image.parse_args(["--prompt", "x"]).model == "gpt-image-2.5-sunburst"
    assert generate_image.parse_args(["--prompt", "x", "--model", FLARE]).model == FLARE


def test_generate_complexity_from_env_and_cli(monkeypatch):
    monkeypatch.setenv("GPT_IMAGE_COMPLEXITY", "medium")
    assert generate_image.parse_args(["--prompt", "x"]).complexity == "medium"
    assert generate_image.parse_args(["--prompt", "x", "--complexity", "low"]).complexity == "low"


def test_generate_unknown_model_from_cli_is_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        generate_image.parse_args(["--prompt", "x", "--model", "gpt-image-9"])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "gpt-image-2.5-flare" in err and "--model" in err


def test_generate_unknown_model_from_env_is_usage_error(monkeypatch, capsys):
    monkeypatch.setenv("GPT_IMAGE_MODEL", "dall-e-3")
    with pytest.raises(SystemExit):
        generate_image.parse_args(["--prompt", "x"])
    assert "GPT_IMAGE_MODEL" in capsys.readouterr().err


def test_generate_xhigh_accepted_for_2_5(tmp_path):
    rec = Recorder()
    code, _, err = _run_generate(["--prompt", "x", "--model", FLARE, "--quality", "xhigh"],
                                 tmp_path, rec)
    assert code == 0, err
    assert rec.params.quality == "xhigh"
    assert rec.load_config_args == (FLARE,)


def test_generate_xhigh_rejected_for_default_model(tmp_path):
    rec = Recorder()
    code, _, err = _run_generate(["--prompt", "x", "--quality", "xhigh"], tmp_path, rec)
    assert code != 0
    assert "パラメータエラー" in err


def test_generate_default_model_calls_load_config_without_args(tmp_path):
    rec = Recorder()
    code, _, _ = _run_generate(["--prompt", "x"], tmp_path, rec)
    assert code == 0
    assert rec.load_config_args == ()


def test_generate_passes_token_scope_to_auth(tmp_path):
    rec = Recorder()
    _run_generate(["--prompt", "x"], tmp_path, rec)
    assert rec.auth_kwargs == {"scope": "scope-x"}


def test_generate_has_no_deployment_argument():
    with pytest.raises(SystemExit):
        generate_image.parse_args(["--prompt", "x", "--deployment", "d"])


# --- 編集 CLI (1.2, 1.3, 6.1, 7.1-7.3, 11.1) --------------------------------------

def _png(tmp_path, name, width=1024, height=1024):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr
    chunk += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    p = tmp_path / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk)
    return str(p)


def _run_edit(argv, tmp_path, rec):
    out, err = io.StringIO(), io.StringIO()
    code = edit_image.run(
        argv + ["--output", str(tmp_path / "out")], out=out, err=err,
        load_config=rec.load_config, load_api_key=lambda: "k",
        resolve_auth=rec.resolve_auth, edit=rec.call,
    )
    return code, out.getvalue(), err.getvalue()


def test_edit_parse_markup_model_complexity(tmp_path):
    params = edit_image.parse_args([
        "--prompt", "x", "--image", "a.png", "--markup", "m.png",
        "--model", FLARE, "--complexity", "high",
    ])
    assert params.markup == "m.png"
    assert params.model == FLARE
    assert params.complexity == "high"


def test_edit_unknown_model_is_usage_error():
    with pytest.raises(SystemExit):
        edit_image.parse_args(["--prompt", "x", "--image", "a.png", "--model", "nope"])


def test_edit_with_markup_runs(tmp_path, monkeypatch):
    import capabilities

    monkeypatch.setitem(capabilities.AZURE_ENABLED, "markup", True)
    rec = Recorder()
    base, markup = _png(tmp_path, "base.png"), _png(tmp_path, "markup.png")
    code, _, err = _run_edit(["--prompt", "x", "--image", base, "--markup", markup,
                              "--model", FLARE], tmp_path, rec)
    assert code == 0, err
    assert rec.params.markup == markup
    assert rec.load_config_args == (FLARE,)
    assert rec.auth_kwargs == {"scope": "scope-x"}


def test_edit_markup_with_mask_fails(tmp_path):
    rec = Recorder()
    base, markup, mask = (_png(tmp_path, n) for n in ("base.png", "markup.png", "mask.png"))
    code, _, err = _run_edit(["--prompt", "x", "--image", base, "--markup", markup,
                              "--mask", mask, "--model", FLARE], tmp_path, rec)
    assert code != 0
    assert "併用できません" in err


def test_edit_default_model_calls_load_config_without_args(tmp_path):
    rec = Recorder()
    code, _, _ = _run_edit(["--prompt", "x", "--image", _png(tmp_path, "b.png")], tmp_path, rec)
    assert code == 0
    assert rec.load_config_args == ()
