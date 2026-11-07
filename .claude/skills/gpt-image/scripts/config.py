"""環境変数からの設定読み込み。

エンドポイント・デプロイ名・API キーは環境変数からのみ取得する。
シークレット値は例外メッセージ・ログに一切含めない。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from capabilities import get_capability
from models import DEFAULT_MODEL, DEFAULT_TOKEN_SCOPE, AzureConfig, ModelName

ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
DEPLOYMENT_ENV = "AZURE_OPENAI_DEPLOYMENT"
API_KEY_ENV = "AZURE_OPENAI_API_KEY"
API_VERSION_ENV = "AZURE_OPENAI_API_VERSION"
API_STYLE_ENV = "AZURE_OPENAI_API_STYLE"
TOKEN_SCOPE_ENV = "AZURE_OPENAI_TOKEN_SCOPE"

DEFAULT_API_VERSION = "2025-04-01-preview"
# v1 形式（/openai/v1/...）で api-version 未指定時に使う値
DEFAULT_V1_API_VERSION = "preview"
VALID_API_STYLES = ("deployments", "v1")

DOTENV_FILENAME = ".env"
# スキルフォルダ（scripts/ の親）。グローバルインストール時も .env を置けるようにする
SKILL_DIR = str(Path(__file__).resolve().parent.parent)


class ConfigError(Exception):
    """必須の環境変数が欠けている等、設定が不正な場合に送出する。"""


# --- .env サポート --------------------------------------------------------
# OS 環境変数が常に優先され、.env は未設定の変数を補完する役割のみを持つ。

def parse_env_file(path: str) -> dict[str, str]:
    """単純な .env ファイルを解析して dict を返す。

    対応: `KEY=VALUE`、`export KEY=VALUE`、行頭 `#` コメント、空行、
    値を囲む single/double quote。`=` を含まない行は無視する。
    値の中に `#` があっても（クオートの有無に関わらず）そのまま値として扱う。
    """
    result: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, TypeError):
        return result

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            result[key] = value
    return result


def apply_env_file(path: Optional[str], override: bool = False) -> None:
    """.env を os.environ に適用する。

    既定では既存の OS 環境変数を上書きしない（OS 環境変数が優先）。
    path が None または存在しない場合は何もしない。
    """
    if not path:
        return
    for key, value in parse_env_file(path).items():
        if override or key not in os.environ:
            os.environ[key] = value


def find_dotenv(start: Optional[str] = None) -> Optional[str]:
    """start（既定: カレントディレクトリ）から上位へ辿り、最初の .env の絶対パスを返す。"""
    current = Path(start) if start else Path.cwd()
    current = current.resolve()
    for directory in (current, *current.parents):
        candidate = directory / DOTENV_FILENAME
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def load_dotenv_files(start: Optional[str] = None,
                      skill_dir: Optional[str] = None) -> list[str]:
    """プロジェクトの .env とスキルフォルダの .env を順に適用し、適用したパスを返す。

    1. start（既定: カレント）から上位へ探して最初に見つかった .env
    2. スキルフォルダ（既定: SKILL_DIR）直下の .env
    どちらも既存の値を上書きしないため、優先順位は
    「OS 環境変数 > プロジェクトの .env > スキルフォルダの .env」になる。
    同じファイルを指す場合は 1 回だけ適用する。
    """
    candidates = [find_dotenv(start)]
    skill_env = Path(skill_dir or SKILL_DIR) / DOTENV_FILENAME
    if skill_env.is_file():
        candidates.append(str(skill_env.resolve()))

    applied: list[str] = []
    for path in candidates:
        if path and path not in applied:
            apply_env_file(path)
            applied.append(path)
    return applied


def load_project_dotenv() -> Optional[str]:
    """プロジェクトとスキルフォルダの .env を適用し、最初に適用したパスを返す。"""
    applied = load_dotenv_files()
    return applied[0] if applied else None


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def load_config(model: ModelName = DEFAULT_MODEL) -> AzureConfig:
    """環境変数から AzureConfig を構築する。

    デプロイ名は「モデル種別ごとの環境変数 → AZURE_OPENAI_DEPLOYMENT」の順に探す。
    デプロイ名からモデル種別を推測することはしない。
    必須（ENDPOINT / デプロイ名）が欠けている場合は ConfigError。
    エラーメッセージには変数名のみを含め、値（特にキー）は含めない。
    """
    endpoint = _env(ENDPOINT_ENV)
    model_deployment_env = get_capability(model).deployment_env
    deployment = _env(model_deployment_env) or _env(DEPLOYMENT_ENV)

    missing = []
    if not endpoint:
        missing.append(ENDPOINT_ENV)
    if not deployment:
        missing.append(f"{model_deployment_env} または {DEPLOYMENT_ENV}")
    if missing:
        raise ConfigError(
            "必須の環境変数が設定されていません: "
            + ", ".join(missing)
            + "。設定後に再実行してください。"
        )

    api_style = _env(API_STYLE_ENV) or "deployments"
    if api_style not in VALID_API_STYLES:
        raise ConfigError(
            f"{API_STYLE_ENV} の値が不正です。"
            f"{' / '.join(VALID_API_STYLES)} のいずれかを指定してください。"
        )
    default_version = DEFAULT_V1_API_VERSION if api_style == "v1" else DEFAULT_API_VERSION
    api_version = _env(API_VERSION_ENV) or default_version

    return AzureConfig(
        endpoint=endpoint.rstrip("/"),
        deployment=deployment,
        api_version=api_version,
        api_style=api_style,  # type: ignore[arg-type]  # VALID_API_STYLES で検証済み
        token_scope=_env(TOKEN_SCOPE_ENV) or DEFAULT_TOKEN_SCOPE,
    )


def load_api_key() -> Optional[str]:
    """API キーを環境変数から取得する。未設定なら None。返り値はログ出力しない。"""
    key = os.environ.get(API_KEY_ENV)
    return key or None
