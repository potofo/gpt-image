"""トークンのスコープ指定（auth.resolve_auth の scope 引数）のテスト。"""
from auth import TOKEN_SCOPE, resolve_auth


class RecordingCredential:
    """要求されたスコープを記録する DefaultAzureCredential の代役。"""

    def __init__(self):
        self.scopes = []

    def get_token(self, *scopes):
        self.scopes.append(scopes)

        class _Token:
            token = "tok"

        return _Token()


def test_default_scope_is_cognitive_services():
    cred = RecordingCredential()
    resolve_auth(api_key=None, credential=cred)
    assert cred.scopes == [("https://cognitiveservices.azure.com/.default",)]
    assert TOKEN_SCOPE == "https://cognitiveservices.azure.com/.default"


def test_explicit_scope_is_requested():
    cred = RecordingCredential()
    header = resolve_auth(api_key=None, credential=cred, scope="https://ai.azure.com/.default")
    assert cred.scopes == [("https://ai.azure.com/.default",)]
    assert header.value == "Bearer tok"
