"""Azure 画像生成 API クライアント。

デプロイ名ベースのエンドポイントへ POST し、レスポンスの b64_json をデコードして
画像バイト列を返す。HTTP エラーは種別分類し、429 は指数バックオフで再試行する。
シークレット（認証ヘッダ値）はログ・例外メッセージに含めない。
"""
from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Callable, Literal, Optional

from models import AuthHeader, AzureConfig, EditParams, GenerationParams

# 入力画像の拡張子から multipart の MIME タイプを引く
_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

ErrorKind = Literal["auth", "rate_limit", "bad_request", "moderation", "timeout", "unknown"]

# モデレーション拒否を判定するためのキーワード
_MODERATION_HINTS = ("moderation", "content_policy", "safety", "content_filter")

# モデレーション拒否時のユーザー向け文言
_MODERATION_MESSAGE = (
    "プロンプトがコンテンツモデレーションにより拒否されました。"
    "表現を見直して再度お試しください。"
)


class ApiError(Exception):
    """API 呼び出しに失敗した場合に送出する。kind でエラー種別を区別する。"""

    def __init__(self, message: str, kind: ErrorKind, status: Optional[int] = None):
        super().__init__(message)
        self.kind: ErrorKind = kind
        self.status = status


def _build_url(config: AzureConfig, operation: str = "generations") -> str:
    return (
        f"{config.endpoint}/openai/deployments/{config.deployment}"
        f"/images/{operation}?api-version={config.api_version}"
    )


def _build_body(params: GenerationParams) -> dict:
    body: dict = {
        "prompt": params.prompt,
        "size": params.size,
        "quality": params.quality,
        "n": params.n,
        "output_format": params.output_format,
        "background": params.background,
    }
    # compression は JPEG 出力時のみ意味を持つ
    if params.output_format == "jpeg":
        body["output_compression"] = params.output_compression
    if params.user:
        body["user"] = params.user
    return body


def _looks_like_moderation(response) -> bool:
    haystack = (getattr(response, "text", "") or "").lower()
    try:
        payload = response.json()
        haystack += " " + str(payload).lower()
    except Exception:
        pass
    return any(hint in haystack for hint in _MODERATION_HINTS)


def _raise_for_status(response) -> None:
    status = response.status_code
    if status in (401, 403):
        raise ApiError(
            "認証に失敗しました。資格情報（az login または AZURE_OPENAI_API_KEY）を確認してください。",
            kind="auth",
            status=status,
        )
    if status == 400:
        if _looks_like_moderation(response):
            raise ApiError(_MODERATION_MESSAGE, kind="moderation", status=status)
        raise ApiError(
            "リクエストが不正です。パラメータ（特に api-version 依存の background/compression）を確認してください。",
            kind="bad_request",
            status=status,
        )
    raise ApiError(
        f"API 呼び出しに失敗しました（HTTP {status}）。",
        kind="unknown",
        status=status,
    )


def _request_with_retry(
    do_post: Callable[[], object],
    timeout: float,
    max_retries: int,
    sleep: Callable[[float], None],
) -> list[bytes]:
    """do_post を実行し、200 ならデコード済み画像を返す共通リトライループ。

    429（レート制限）は上限 max_retries 回まで指数バックオフで再試行する。
    その他の HTTP エラー・タイムアウトは分類済みの ApiError を送出する。
    do_post はヘッダ・ボディ等を内包した引数なしの POST 呼び出し。
    """
    import requests

    attempt = 0
    while True:
        try:
            response = do_post()
        except requests.exceptions.Timeout:
            raise ApiError(
                f"API 呼び出しがタイムアウトしました（{timeout} 秒）。", kind="timeout"
            )
        except requests.exceptions.RequestException as exc:
            # 接続エラー等。例外メッセージにシークレットは含まれない（URL/本文のみ）。
            raise ApiError(f"API への接続に失敗しました: {exc}", kind="unknown")

        if response.status_code == 200:
            return _decode_images(response)

        if response.status_code == 429:
            if attempt >= max_retries:
                raise ApiError(
                    "レート制限（429）により再試行上限に達しました。時間をおいて再実行してください。",
                    kind="rate_limit",
                    status=429,
                )
            sleep(2 ** attempt)
            attempt += 1
            continue

        _raise_for_status(response)


def generate(
    config: AzureConfig,
    auth: AuthHeader,
    params: GenerationParams,
    timeout: float = 120.0,
    max_retries: int = 3,
    http_post: Optional[Callable] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[bytes]:
    """画像を生成し、デコード済み画像バイト列のリストを返す。

    429（レート制限）は上限 max_retries 回まで指数バックオフで再試行する。
    その他の HTTP エラー・タイムアウトは分類済みの ApiError を送出する。
    """
    if http_post is None:
        import requests

        http_post = requests.post

    url = _build_url(config, "generations")
    headers = {"Content-Type": "application/json", auth.name: auth.value}
    body = _build_body(params)

    return _request_with_retry(
        lambda: http_post(url, headers=headers, json=body, timeout=timeout),
        timeout, max_retries, sleep,
    )


def _build_edit_data(params: EditParams) -> dict:
    """images/edits の multipart 非ファイルフィールド（data）を組み立てる。"""
    data: dict = {
        "prompt": params.prompt,
        "n": str(params.n),
        "quality": params.quality,
        "output_format": params.output_format,
        "background": params.background,
    }
    # size=auto は API 既定（入力画像に合わせる）に委ねるため送らない
    if params.size and params.size != "auto":
        data["size"] = params.size
    if params.output_format == "jpeg":
        data["output_compression"] = str(params.output_compression)
    if params.user:
        data["user"] = params.user
    return data


def _open_image_part(path: str, read_bytes: Callable[[str], bytes]):
    """multipart 用の (filename, bytes, mime) タプルを作る。"""
    p = Path(path)
    mime = _MIME_BY_EXT.get(p.suffix.lower(), "application/octet-stream")
    return (p.name, read_bytes(path), mime)


def edit(
    config: AzureConfig,
    auth: AuthHeader,
    params: EditParams,
    timeout: float = 180.0,
    max_retries: int = 3,
    http_post: Optional[Callable] = None,
    sleep: Callable[[float], None] = time.sleep,
    read_bytes: Optional[Callable[[str], bytes]] = None,
) -> list[bytes]:
    """既存画像をプロンプトで編集し、デコード済み画像バイト列のリストを返す。

    images に複数画像を渡すと参照素材として合成（マージ）できる。先頭画像が
    ベース、mask があれば mask の透過領域のみが編集対象（インペインティング）。
    multipart/form-data で送信する（Content-Type は requests が境界付きで設定）。
    """
    if http_post is None:
        import requests

        http_post = requests.post
    if read_bytes is None:
        read_bytes = lambda path: Path(path).read_bytes()

    url = _build_url(config, "edits")
    # multipart のため Content-Type は付けない（requests が boundary 付きで設定）
    headers = {auth.name: auth.value}

    # 複数画像は image[] を繰り返す（単一でも image[] で統一）
    files = [("image[]", _open_image_part(path, read_bytes)) for path in params.images]
    if params.mask is not None:
        files.append(("mask", _open_image_part(params.mask, read_bytes)))
    data = _build_edit_data(params)

    return _request_with_retry(
        lambda: http_post(url, headers=headers, files=files, data=data, timeout=timeout),
        timeout, max_retries, sleep,
    )


def _decode_images(response) -> list[bytes]:
    payload = response.json()
    data = payload.get("data") or []
    if not data:
        raise ApiError("API レスポンスに画像データが含まれていません。", kind="unknown")
    images: list[bytes] = []
    for item in data:
        b64 = item.get("b64_json")
        if not b64:
            raise ApiError("API レスポンスに b64_json が含まれていません。", kind="unknown")
        images.append(base64.b64decode(b64))
    return images
