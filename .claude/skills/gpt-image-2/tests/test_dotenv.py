"""`.env` 読み込み（config の dotenv 機能）のテスト。"""
import os

from config import apply_env_file, find_dotenv, parse_env_file


def test_parse_basic_pairs(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join([
            "# コメント行",
            "AZURE_OPENAI_ENDPOINT=https://r.openai.azure.com",
            "AZURE_OPENAI_DEPLOYMENT = gpt-image-2  ",
            'AZURE_OPENAI_API_KEY="quoted-key"',
            "export AZURE_OPENAI_API_VERSION='2025-04-01-preview'",
            "",
            "INVALID_LINE_NO_EQUALS",
        ]),
        encoding="utf-8",
    )
    parsed = parse_env_file(str(env))
    assert parsed["AZURE_OPENAI_ENDPOINT"] == "https://r.openai.azure.com"
    assert parsed["AZURE_OPENAI_DEPLOYMENT"] == "gpt-image-2"
    assert parsed["AZURE_OPENAI_API_KEY"] == "quoted-key"
    assert parsed["AZURE_OPENAI_API_VERSION"] == "2025-04-01-preview"
    assert "INVALID_LINE_NO_EQUALS" not in parsed


def test_apply_does_not_override_existing_os_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "os-value")
    env = tmp_path / ".env"
    env.write_text("AZURE_OPENAI_DEPLOYMENT=dotenv-value\n", encoding="utf-8")
    apply_env_file(str(env))
    # OS 環境変数が優先される
    assert os.environ["AZURE_OPENAI_DEPLOYMENT"] == "os-value"


def test_apply_sets_missing_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    env = tmp_path / ".env"
    env.write_text("AZURE_OPENAI_ENDPOINT=https://from-dotenv\n", encoding="utf-8")
    apply_env_file(str(env))
    assert os.environ["AZURE_OPENAI_ENDPOINT"] == "https://from-dotenv"


def test_apply_none_or_missing_path_is_noop():
    apply_env_file(None)  # 例外を出さない
    apply_env_file("/path/does/not/exist/.env")


def test_find_dotenv_walks_up(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    (root / ".env").write_text("X=1\n", encoding="utf-8")
    found = find_dotenv(start=str(nested))
    assert found == str((root / ".env").resolve())


def test_find_dotenv_returns_none_when_absent(tmp_path):
    assert find_dotenv(start=str(tmp_path)) is None
