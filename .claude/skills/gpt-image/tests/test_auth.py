"""認証ヘッダ解決（auth）のテスト。"""
import pytest

from auth import AuthError, resolve_auth
from models import AuthHeader


class FakeToken:
    def __init__(self, token):
        self.token = token


class FakeCredential:
    """get_token が成功する DefaultAzureCredential の代役。"""

    def __init__(self, token="entra-token-xyz"):
        self._token = token

    def get_token(self, *scopes):
        return FakeToken(self._token)


class FailingCredential:
    """トークン取得に失敗する代役（az login 未実施などを模す）。"""

    def get_token(self, *scopes):
        raise RuntimeError("no credential available")


def test_entra_id_preferred_returns_bearer():
    header = resolve_auth(api_key="some-key", credential=FakeCredential("tok"))
    assert isinstance(header, AuthHeader)
    assert header.name == "Authorization"
    assert header.value == "Bearer tok"


def test_falls_back_to_api_key_when_entra_unavailable():
    header = resolve_auth(api_key="my-api-key", credential=FailingCredential())
    assert header.name == "api-key"
    assert header.value == "my-api-key"


def test_raises_when_neither_available():
    with pytest.raises(AuthError):
        resolve_auth(api_key=None, credential=FailingCredential())


def test_error_does_not_leak_api_key(monkeypatch):
    # Entra も使えず、api_key も None のとき、メッセージにシークレットを含めない
    with pytest.raises(AuthError) as exc:
        resolve_auth(api_key=None, credential=FailingCredential())
    assert "my-api-key" not in str(exc.value)
