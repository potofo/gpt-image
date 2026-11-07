"""CLI オーケストレーション（edit_image）のテスト。"""
import io

import pytest

import edit_image
from models import AuthHeader, AzureConfig, EditParams

FAKE_CONFIG = AzureConfig(endpoint="https://r.openai.azure.com", deployment="dep")
FAKE_AUTH = AuthHeader(name="api-key", value="k")


def base_deps(**overrides):
    deps = dict(
        load_config=lambda: FAKE_CONFIG,
        load_api_key=lambda: "k",
        resolve_auth=lambda api_key, **kw: FAKE_AUTH,
        edit=lambda config, auth, params, **kw: [b"img-bytes"] * params.n,
    )
    deps.update(overrides)
    return deps


def _img(tmp_path, name="base.png"):
    p = tmp_path / name
    p.write_bytes(b"fake-image-bytes")
    return str(p)


# --- 引数解析 -------------------------------------------------------------

def test_parse_args_defaults(tmp_path):
    img = _img(tmp_path)
    params = edit_image.parse_args(["--prompt", "犬を猫に", "--image", img])
    assert params.prompt == "犬を猫に"
    assert params.images == (img,)
    assert params.size == "auto"
    assert params.mask is None


def test_parse_args_multiple_images_for_merge(tmp_path):
    a, b = _img(tmp_path, "a.png"), _img(tmp_path, "b.png")
    params = edit_image.parse_args(
        ["--prompt", "合成", "--image", a, "--image", b, "--mask", _img(tmp_path, "m.png")]
    )
    assert params.images == (a, b)
    assert params.mask.endswith("m.png")


def test_prompt_is_required(tmp_path):
    with pytest.raises(SystemExit):
        edit_image.parse_args(["--image", _img(tmp_path)])


def test_image_is_required():
    with pytest.raises(SystemExit):
        edit_image.parse_args(["--prompt", "x"])


# --- 実行フロー -----------------------------------------------------------

def test_run_single_edit_success(tmp_path):
    out, err = io.StringIO(), io.StringIO()
    code = edit_image.run(
        ["--prompt", "赤い帽子", "--image", _img(tmp_path), "--output", str(tmp_path)],
        out=out, err=err, **base_deps(),
    )
    assert code == 0
    printed = out.getvalue().strip().splitlines()
    assert len(printed) == 1
    assert printed[0].endswith(".png")


def test_run_merge_multiple_images_success(tmp_path):
    out = io.StringIO()
    code = edit_image.run(
        ["--prompt", "オブジェクト置換", "--image", _img(tmp_path, "a.png"),
         "--image", _img(tmp_path, "b.png"), "--output", str(tmp_path)],
        out=out, err=io.StringIO(), **base_deps(),
    )
    assert code == 0
    assert len(out.getvalue().strip().splitlines()) == 1


def test_run_missing_image_validation_error(tmp_path):
    err = io.StringIO()
    code = edit_image.run(
        ["--prompt", "x", "--image", str(tmp_path / "missing.png"),
         "--output", str(tmp_path)],
        out=io.StringIO(), err=err, **base_deps(),
    )
    assert code != 0
    assert "見つかりません" in err.getvalue()


def test_run_api_error_returns_nonzero(tmp_path):
    from client import ApiError

    def boom(config, auth, params, **kw):
        raise ApiError("拒否されました", kind="moderation")

    err = io.StringIO()
    code = edit_image.run(
        ["--prompt", "x", "--image", _img(tmp_path), "--output", str(tmp_path)],
        out=io.StringIO(), err=err, **base_deps(edit=boom),
    )
    assert code != 0
    assert "拒否" in err.getvalue()


def test_run_config_error_returns_nonzero(tmp_path):
    from config import ConfigError

    def missing():
        raise ConfigError("必須の環境変数が設定されていません: AZURE_OPENAI_ENDPOINT")

    err = io.StringIO()
    code = edit_image.run(
        ["--prompt", "x", "--image", _img(tmp_path)],
        out=io.StringIO(), err=err, **base_deps(load_config=missing),
    )
    assert code != 0
    assert "環境変数" in err.getvalue()
