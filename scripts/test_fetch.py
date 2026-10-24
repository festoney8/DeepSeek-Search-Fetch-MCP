import json
import re
from types import TracebackType
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from deepseek_search_fetch_mcp.api import DeepSeekAPI, DeepSeekAPIError, FetchRequest, FetchResponse
from deepseek_search_fetch_mcp.main import FetchToolResponse, mcp
from deepseek_search_fetch_mcp.request import build_fetch_request

pytestmark = pytest.mark.anyio


class _FakeResponse:
    """模拟 aiohttp 响应"""

    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:
        """读取响应文本"""
        return self._text


class _FakePostContext:
    """模拟 aiohttp 请求上下文"""

    def __init__(self, result: _FakeResponse | Exception) -> None:
        self._result = result

    async def __aenter__(self) -> _FakeResponse:
        """进入请求上下文"""
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出请求上下文"""


def _install_post(
    monkeypatch: pytest.MonkeyPatch,
    result: _FakeResponse | Exception,
) -> Mock:
    """替换 aiohttp POST 请求"""
    post = Mock(return_value=_FakePostContext(result))
    monkeypatch.setattr(aiohttp.ClientSession, "post", post)
    return post


async def _fetch_example() -> FetchResponse:
    """通过客户端抓取示例页"""
    async with DeepSeekAPI("sk-test") as api:
        return await api.fetch(FetchRequest(url="https://example.com"))


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://8.8.8.8",
        "https://[2606:4700:4700::1111]",
        "https://[::ffff:8.8.8.8]",
    ],
)
def test_build_fetch_request_accepts_public_urls(url: str) -> None:
    """校验合法公网 URL"""
    assert build_fetch_request(url).url == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.com",
        "https://user:pass@example.com",
        "https://example.com/a b",
        "http://127.0.0.1",
        "https://localhost",
        "https://foo.localhost",
        "https://[::1]",
        "https://[fe80::1]",
        "https://[fec0::1]",
        f"https://{'a' * 8192}",
    ],
)
def test_build_fetch_request_rejects_invalid_or_private_urls(url: str) -> None:
    """校验非法或不安全 URL"""
    with pytest.raises(ValueError):
        build_fetch_request(url)


async def test_fetch_api_context_manager_lifecycle() -> None:
    """校验 API 会话创建和关闭"""
    api = DeepSeekAPI("sk-test", timeout=3)

    await api.__aexit__(None, None, None)
    await api.__aenter__()
    assert api._session is not None
    assert api._session.headers["Authorization"] == "Bearer sk-test"
    assert api._session.timeout.total == 3
    with pytest.raises(RuntimeError, match="already open"):
        await api.__aenter__()
    await api.__aexit__(None, None, None)
    assert api._session is None


async def test_fetch_api_requires_open_session() -> None:
    """校验未打开会话拒绝请求"""
    api = DeepSeekAPI("sk-test")
    request = FetchRequest(url="https://example.com")

    with pytest.raises(RuntimeError, match="not open"):
        await api.fetch(request)


async def test_fetch_api_posts_payload_and_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验 Fetch 请求路径、负载和成功响应"""
    response = _FakeResponse(200, json.dumps({"title": "Example", "content": "Body", "extra": "kept"}))
    post = _install_post(monkeypatch, response)

    result = await _fetch_example()

    post.assert_called_once_with(
        "https://api.deepseek.com/v1/tools/fetch",
        json={"url": "https://example.com"},
    )
    assert result.title == "Example"
    assert result.content == "Body"
    assert result.model_extra == {"extra": "kept"}


@pytest.mark.parametrize(
    "error",
    [
        aiohttp.ClientError("connection failed"),
        TimeoutError("request timed out"),
    ],
)
async def test_fetch_api_wraps_transport_errors(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    """校验网络和超时异常包装"""
    _install_post(monkeypatch, error)

    with pytest.raises(DeepSeekAPIError) as exc_info:
        await _fetch_example()

    assert str(exc_info.value) == f"DeepSeek API request failed: {error}"
    assert exc_info.value.status is None


async def test_fetch_api_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验非 JSON 响应"""
    _install_post(monkeypatch, _FakeResponse(502, "not-json"))

    with pytest.raises(DeepSeekAPIError) as exc_info:
        await _fetch_example()

    assert str(exc_info.value) == "DeepSeek API returned invalid JSON, status code: 502"
    assert exc_info.value.status == 502


async def test_fetch_api_maps_structured_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验结构化上游错误"""
    payload = {"error": {"message": "rate limited", "type": "rate_limit", "code": "slow_down"}}
    _install_post(monkeypatch, _FakeResponse(429, json.dumps(payload)))

    with pytest.raises(DeepSeekAPIError) as exc_info:
        await _fetch_example()

    assert str(exc_info.value) == "rate limited"
    assert exc_info.value.status == 429
    assert exc_info.value.code == "slow_down"
    assert exc_info.value.error_type == "rate_limit"


async def test_fetch_api_handles_unstructured_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验无法解析的上游错误"""
    _install_post(monkeypatch, _FakeResponse(500, json.dumps({"error": {"message": "missing type"}})))

    with pytest.raises(DeepSeekAPIError) as exc_info:
        await _fetch_example()

    assert str(exc_info.value) == "DeepSeek API request failed, status code: 500"
    assert exc_info.value.status == 500


async def test_fetch_api_rejects_invalid_success_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验非法成功响应结构"""
    _install_post(monkeypatch, _FakeResponse(200, json.dumps({"title": "missing content"})))

    with pytest.raises(DeepSeekAPIError) as exc_info:
        await _fetch_example()

    assert str(exc_info.value) == "DeepSeek API returned an invalid response"
    assert exc_info.value.status == 200


@pytest.mark.live
async def test_fetch_tool_live_success() -> None:
    """校验真实 Fetch 成功响应"""
    async with Client(mcp) as client:
        result = await client.call_tool("ds_web_fetch", {"url": "https://example.com"})

    assert result.is_error is False
    assert result.structured_content is not None
    response = FetchToolResponse.model_validate(result.structured_content)
    assert response.title
    assert response.content


async def test_mcp_startup_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验缺少 API Key 时服务启动失败"""
    monkeypatch.delenv("DEEPSEEK_API_KEY")

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY: Field required"):
        async with Client(mcp):
            pass


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.com",
        "https://user:pass@example.com",
        "http://127.0.0.1",
        "https://foo.localhost",
        "https://[::1]",
    ],
)
async def test_fetch_tool_rejects_invalid_url_without_api_call(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    """校验非法 URL 不会请求 Fetch API"""
    fetch = AsyncMock()
    monkeypatch.setattr(DeepSeekAPI, "fetch", fetch)

    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("ds_web_fetch", {"url": url})

    fetch.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            DeepSeekAPIError("denied", status=403, code="forbidden", error_type="permission"),
            "denied [status=403, code=forbidden, type=permission]",
        ),
        (DeepSeekAPIError("network down"), "network down"),
        (DeepSeekAPIError("invalid response", status=200), "invalid response [status=200]"),
    ],
)
async def test_fetch_tool_wraps_api_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: DeepSeekAPIError,
    expected: str,
) -> None:
    """校验 Fetch 上游错误转换为 ToolError"""
    monkeypatch.setattr(DeepSeekAPI, "fetch", AsyncMock(side_effect=error))

    async with Client(mcp) as client:
        with pytest.raises(ToolError, match=re.escape(expected)):
            await client.call_tool("ds_web_fetch", {"url": "https://example.com"})
