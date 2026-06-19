"""環境変数からの設定読み込み。

エンドポイント・デプロイ名・API キーは環境変数からのみ取得する。
シークレット値は例外メッセージ・ログに一切含めない。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from models import AzureConfig

ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
DEPLOYMENT_ENV = "AZURE_OPENAI_DEPLOYMENT"
API_KEY_ENV = "AZURE_OPENAI_API_KEY"
API_VERSION_ENV = "AZURE_OPENAI_API_VERSION"

DEFAULT_API_VERSION = "2025-04-01-preview"

DOTENV_FILENAME = ".env"


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


def load_project_dotenv() -> Optional[str]:
    """カレントディレクトリから上位の .env を探して適用し、適用したパスを返す。"""
    path = find_dotenv()
    apply_env_file(path)
    return path


def load_config() -> AzureConfig:
    """環境変数から AzureConfig を構築する。

    必須（ENDPOINT / DEPLOYMENT）が欠けている場合は ConfigError。
    エラーメッセージには変数名のみを含め、値（特にキー）は含めない。
    """
    endpoint = (os.environ.get(ENDPOINT_ENV) or "").strip()
    deployment = (os.environ.get(DEPLOYMENT_ENV) or "").strip()

    missing = [
        name
        for name, value in ((ENDPOINT_ENV, endpoint), (DEPLOYMENT_ENV, deployment))
        if not value
    ]
    if missing:
        raise ConfigError(
            "必須の環境変数が設定されていません: "
            + ", ".join(missing)
            + "。設定後に再実行してください。"
        )

    api_version = (os.environ.get(API_VERSION_ENV) or "").strip() or DEFAULT_API_VERSION
    return AzureConfig(
        endpoint=endpoint.rstrip("/"),
        deployment=deployment,
        api_version=api_version,
    )


def load_api_key() -> Optional[str]:
    """API キーを環境変数から取得する。未設定なら None。返り値はログ出力しない。"""
    key = os.environ.get(API_KEY_ENV)
    return key or None
