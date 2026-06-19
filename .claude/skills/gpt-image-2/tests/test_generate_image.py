"""CLI オーケストレーション（generate_image）のテスト。"""
import io

import pytest

import generate_image
from models import AuthHeader, AzureConfig, GenerationParams

FAKE_CONFIG = AzureConfig(endpoint="https://r.openai.azure.com", deployment="dep")
FAKE_AUTH = AuthHeader(name="api-key", value="k")


def base_deps(**overrides):
    deps = dict(
        load_config=lambda: FAKE_CONFIG,
        load_api_key=lambda: "k",
        resolve_auth=lambda api_key, **kw: FAKE_AUTH,
        generate=lambda config, auth, params, **kw: [b"img-bytes"] * params.n,
    )
    deps.update(overrides)
    return deps


# --- 引数解析 (2.1, 2.2) ---------------------------------------------------

def test_parse_args_defaults():
    params = generate_image.parse_args(["--prompt", "犬"])
    assert params == GenerationParams(prompt="犬")


def test_parse_args_overrides():
    params = generate_image.parse_args([
        "--prompt", "猫", "--size", "1536x1024", "--quality", "low",
        "--format", "jpeg", "--background", "auto", "--compression", "80",
        "--n", "2", "--user", "u1", "--output", "/tmp/out",
    ])
    assert params.size == "1536x1024"
    assert params.quality == "low"
    assert params.output_format == "jpeg"
    assert params.output_compression == 80
    assert params.n == 2
    assert params.user == "u1"
    assert params.output_dir == "/tmp/out"


def test_prompt_is_required():
    with pytest.raises(SystemExit):
        generate_image.parse_args([])


# --- 実行フロー -----------------------------------------------------------

def test_run_prompt_only_success(tmp_path):
    out, err = io.StringIO(), io.StringIO()
    code = generate_image.run(
        ["--prompt", "夕暮れ", "--output", str(tmp_path)],
        out=out, err=err, **base_deps(),
    )
    assert code == 0
    printed = out.getvalue().strip().splitlines()
    assert len(printed) == 1
    assert printed[0].endswith(".png")
    assert tmp_path.as_posix() in printed[0].replace("\\", "/")


def test_run_multiple_images_prints_each_path(tmp_path):
    out = io.StringIO()
    code = generate_image.run(
        ["--prompt", "x", "--n", "3", "--output", str(tmp_path)],
        out=out, err=io.StringIO(), **base_deps(),
    )
    assert code == 0
    assert len(out.getvalue().strip().splitlines()) == 3


def test_run_validation_error_returns_nonzero(tmp_path):
    err = io.StringIO()
    code = generate_image.run(
        ["--prompt", "x", "--size", "1000x1000", "--output", str(tmp_path)],
        out=io.StringIO(), err=err, **base_deps(),
    )
    assert code != 0
    assert "16" in err.getvalue()


def test_run_api_error_returns_nonzero(tmp_path):
    from client import ApiError

    def boom(config, auth, params, **kw):
        raise ApiError("拒否されました", kind="moderation")

    err = io.StringIO()
    code = generate_image.run(
        ["--prompt", "x", "--output", str(tmp_path)],
        out=io.StringIO(), err=err, **base_deps(generate=boom),
    )
    assert code != 0
    assert "拒否" in err.getvalue()


def test_run_config_error_returns_nonzero(tmp_path):
    from config import ConfigError

    def missing():
        raise ConfigError("必須の環境変数が設定されていません: AZURE_OPENAI_ENDPOINT")

    err = io.StringIO()
    code = generate_image.run(
        ["--prompt", "x"], out=io.StringIO(), err=err,
        **base_deps(load_config=missing),
    )
    assert code != 0
    assert "環境変数" in err.getvalue()
