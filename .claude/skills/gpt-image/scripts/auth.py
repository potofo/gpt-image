"""認証ヘッダの解決。

Entra ID（キーレス）認証を優先し、利用できない場合は API キーへフォールバックする。
トークン・キーは stdout/stderr/ログ・例外メッセージに一切出力しない。
"""
from __future__ import annotations

from typing import Optional, Protocol

from models import AuthHeader

# Azure Cognitive Services / OpenAI 向けトークンスコープ
TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"


class AuthError(Exception):
    """有効な認証情報が一つも得られない場合に送出する。"""


class TokenCredential(Protocol):
    """azure-identity の get_token インターフェースの最小プロトコル。"""

    def get_token(self, *scopes: str):  # pragma: no cover - 型注釈用
        ...


def _default_credential() -> Optional[TokenCredential]:
    """DefaultAzureCredential を生成する。azure-identity 未導入なら None。"""
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError:
        return None
    try:
        return DefaultAzureCredential()
    except Exception:
        return None


def resolve_auth(
    api_key: Optional[str],
    credential: Optional[TokenCredential] = None,
) -> AuthHeader:
    """認証ヘッダを解決する。

    1. Entra ID トークン取得を試行（成功すれば Bearer）。
    2. 失敗・未構成なら api_key を使用（api-key ヘッダ）。
    3. どちらも不可なら AuthError（シークレット値は含めない）。
    """
    if credential is None:
        credential = _default_credential()

    if credential is not None:
        try:
            token = credential.get_token(TOKEN_SCOPE)
            return AuthHeader(name="Authorization", value=f"Bearer {token.token}")
        except Exception:
            # Entra ID が利用できない場合は API キーへフォールバックする
            pass

    if api_key:
        return AuthHeader(name="api-key", value=api_key)

    raise AuthError(
        "有効な認証情報が見つかりません。'az login' を実行して Entra ID 認証を有効にするか、"
        "環境変数 AZURE_OPENAI_API_KEY を設定してください。"
    )
