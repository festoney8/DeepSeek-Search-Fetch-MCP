import json
import re
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

from deepseek_search_fetch_mcp.api import DeepSeekAPI, DeepSeekAPIError, SearchRequest, SearchResponse
from deepseek_search_fetch_mcp.env import EnvConfig, EnvConfigError, load_env
from deepseek_search_fetch_mcp.main import SearchToolResponse, mcp
from deepseek_search_fetch_mcp.request import build_search_request

pytestmark = pytest.mark.anyio


def _load_search_env(monkeypatch: pytest.MonkeyPatch, **values: str) -> EnvConfig:
    """设置测试环境并加载配置"""
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return load_env()


def test_load_env_uses_search_defaults() -> None:
    """校验 Search 环境默认值"""
    env = load_env()

    assert env.api_key.get_secret_value().startswith("sk-")
    assert env.api_timeout == 30
    assert env.search_count is None
    assert env.search_localization is None
    assert env.search_need_content is None
    assert env.search_lang == ()
    assert env.search_exclude_words == ()
    assert env.search_exclude_sites == ()


def test_load_env_normalizes_valid_search_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验合法 Search 环境值"""
    env = _load_search_env(
        monkeypatch,
        DEEPSEEK_API_TIMEOUT="2.5",
        DEEPSEEK_SEARCH_COUNT="20",
        DEEPSEEK_SEARCH_LOCALIZATION="18.8.8.8",
        DEEPSEEK_SEARCH_NEED_CONTENT="TRUE",
        DEEPSEEK_SEARCH_LANG=" ZH, en,zh ",
        DEEPSEEK_SEARCH_EXCLUDE_WORDS=" spam | foo |spam ",
        DEEPSEEK_SEARCH_EXCLUDE_SITES=" example.org | csdn.net |example.org ",
    )

    assert env.api_timeout == 2.5
    assert env.search_count == 20
    assert str(env.search_localization) == "18.8.8.8"
    assert env.search_need_content is True
    assert env.search_lang == ("zh", "en")
    assert env.search_exclude_words == ("spam", "foo")
    assert env.search_exclude_sites == ("example.org", "csdn.net")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("true", True),
        ("TRUE", True),
        ("1", True),
    ],
)
def test_load_env_parses_need_content(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    expected: bool,
) -> None:
    """校验布尔值解析"""
    monkeypatch.setenv("DEEPSEEK_SEARCH_NEED_CONTENT", value)

    assert load_env().search_need_content is expected


def test_load_env_ignores_blank_optional_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验空白可选环境值被忽略"""
    names = (
        "DEEPSEEK_API_TIMEOUT",
        "DEEPSEEK_SEARCH_COUNT",
        "DEEPSEEK_SEARCH_LOCALIZATION",
        "DEEPSEEK_SEARCH_NEED_CONTENT",
        "DEEPSEEK_SEARCH_LANG",
        "DEEPSEEK_SEARCH_EXCLUDE_WORDS",
        "DEEPSEEK_SEARCH_EXCLUDE_SITES",
    )
    for name in names:
        monkeypatch.setenv(name, "   ")

    env = load_env()

    assert env.api_timeout == 30
    assert env.search_count is None
    assert env.search_localization is None
    assert env.search_need_content is None
    assert env.search_lang == ()
    assert env.search_exclude_words == ()
    assert env.search_exclude_sites == ()


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("DEEPSEEK_API_KEY", "invalid", "must match"),
        ("DEEPSEEK_API_TIMEOUT", "0", "greater than 0"),
        ("DEEPSEEK_SEARCH_COUNT", "51", "less than or equal to 50"),
        ("DEEPSEEK_SEARCH_LOCALIZATION", "127.0.0.1", "global IPv4"),
        ("DEEPSEEK_SEARCH_NEED_CONTENT", "yes", "must be true"),
        ("DEEPSEEK_SEARCH_LANG", "xx", "ISO 639-1"),
        ("DEEPSEEK_SEARCH_EXCLUDE_WORDS", '"spam"', "double quotes"),
        ("DEEPSEEK_SEARCH_EXCLUDE_SITES", "https://example.org", "bare domains"),
    ],
)
def test_load_env_reports_invalid_search_settings(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    expected: str,
) -> None:
    """校验非法环境值返回明确问题"""
    monkeypatch.setenv(name, value)

    with pytest.raises(EnvConfigError) as exc_info:
        load_env()

    assert expected in exc_info.value.issues[0]


def test_build_search_request_combines_all_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验参数覆盖环境配置并合并全部过滤条件"""
    env = _load_search_env(
        monkeypatch,
        DEEPSEEK_SEARCH_COUNT="7",
        DEEPSEEK_SEARCH_LOCALIZATION="18.8.8.8",
        DEEPSEEK_SEARCH_NEED_CONTENT="true",
        DEEPSEEK_SEARCH_LANG="zh,en",
        DEEPSEEK_SEARCH_EXCLUDE_WORDS="a|b|a",
        DEEPSEEK_SEARCH_EXCLUDE_SITES="x.io|y.io|x.io",
    )

    request = build_search_request(
        env=env,
        query="  q  ",
        ori_question="  original question  ",
        count=3,
        sites=[" a.io ", "a.io", "b.io"],
        lang=[" EN ", "zh", "en"],
        after=date(2025, 1, 1),
        before=date(2025, 2, 1),
    )

    assert request.query == (
        'q site:a.io OR site:b.io after:2025-01-01 before:2025-02-01 lang:en,zh -"a" -"b" -site:x.io -site:y.io'
    )
    assert request.count == 3
    assert request.ori_question == "original question"
    assert str(request.localization) == "18.8.8.8"
    assert request.need_content is True


def test_build_search_request_uses_environment_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验未传入参数时使用 Search 环境默认值"""
    env = _load_search_env(
        monkeypatch,
        DEEPSEEK_SEARCH_COUNT="2",
        DEEPSEEK_SEARCH_LANG="zh,en",
    )

    request = build_search_request(
        env=env,
        query="  query  ",
        ori_question="   ",
        sites=["   "],
    )

    assert request.query == "query lang:zh,en"
    assert request.count == 2
    assert request.ori_question is None


def test_build_search_request_empty_lang_disables_environment_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验空语言列表禁用环境语言限制"""
    env = _load_search_env(monkeypatch, DEEPSEEK_SEARCH_LANG="zh,en")

    request = build_search_request(env=env, query="query", lang=[])

    assert request.query == "query"


@pytest.mark.parametrize(
    ("after", "before", "expected"),
    [
        (date(2025, 2, 1), None, "after:2025-02-01"),
        (None, date(2025, 2, 1), "before:2025-02-01"),
    ],
)
def test_build_search_request_supports_single_date_bound(
    after: date | None,
    before: date | None,
    expected: str,
) -> None:
    """校验单边日期过滤"""
    request = build_search_request(env=load_env(), query="query", after=after, before=before)

    assert expected in request.query


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"query": "   "}, "query must not be empty"),
        ({"query": "query", "sites": ["https://example.org"]}, "valid bare domains"),
        (
            {"query": "query", "after": date(2025, 2, 1), "before": date(2025, 1, 1)},
            "after must be on or before before",
        ),
        ({"query": "query", "lang": ["xx"]}, "ISO 639-1"),
    ],
)
def test_build_search_request_rejects_invalid_arguments(kwargs: dict[str, Any], expected: str) -> None:
    """校验非法 Search 请求参数"""
    with pytest.raises(ValueError, match=expected):
        build_search_request(env=load_env(), **kwargs)


@pytest.mark.parametrize("count", [0, 51])
def test_build_search_request_rejects_invalid_count(count: int) -> None:
    """校验 Search 数量边界"""
    with pytest.raises(ValidationError):
        build_search_request(env=load_env(), query="query", count=count)


def test_build_search_request_rejects_query_over_limit() -> None:
    """校验拼接后的 query 超长"""
    with pytest.raises(ValidationError):
        build_search_request(
            env=load_env(),
            query="x" * 100,
            sites=["github.com"],
            after=date(2025, 1, 1),
            before=date(2025, 2, 1),
        )


async def test_search_api_delegates_to_post(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验 Search 客户端传递正确的路径和响应类型"""
    request = SearchRequest(query="query")
    response = SearchResponse(results=[])
    post = AsyncMock(return_value=response)
    monkeypatch.setattr(DeepSeekAPI, "_post", post)

    async with DeepSeekAPI("sk-test") as api:
        result = await api.search(request)

    assert result is response
    post.assert_awaited_once_with("/v1/tools/search", request, SearchResponse)


@pytest.mark.live
async def test_search_tool_live_success() -> None:
    """校验真实 Search 成功响应"""
    async with Client(mcp) as client:
        result = await client.call_tool("ds_web_search", {"query": "DeepSeek API", "count": 1})

    assert result.is_error is False
    assert result.structured_content is not None
    response = SearchToolResponse.model_validate(result.structured_content)
    assert isinstance(response.results, list)
    assert response.results
    first_result = response.results[0].model_dump()
    assert "snippet" not in first_result
    assert "site_icon" not in first_result


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": ""},
        {"query": "query", "count": 0},
        {"query": "query", "ori_question": "x" * 129},
        {"query": "query", "sites": ["https://github.com"]},
        {"query": "query", "lang": ["xx"]},
        {"query": "query", "after": "2025-02-01", "before": "2025-01-01"},
        {
            "query": "x" * 100,
            "sites": ["github.com"],
            "after": "2025-01-01",
            "before": "2025-02-01",
        },
    ],
)
async def test_search_tool_rejects_invalid_arguments_without_api_call(
    monkeypatch: pytest.MonkeyPatch,
    arguments: dict[str, Any],
) -> None:
    """校验非法工具参数不会请求 API"""
    search = AsyncMock()
    monkeypatch.setattr(DeepSeekAPI, "search", search)

    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("ds_web_search", arguments)

    search.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            DeepSeekAPIError("denied", status=401, code="auth", error_type="invalid_request"),
            "denied [status=401, code=auth, type=invalid_request]",
        ),
        (DeepSeekAPIError("network down"), "network down"),
        (DeepSeekAPIError("invalid response", status=200), "invalid response [status=200]"),
    ],
)
async def test_search_tool_wraps_api_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: DeepSeekAPIError,
    expected: str,
) -> None:
    """校验 Search 上游错误转换为 ToolError"""
    monkeypatch.setattr(DeepSeekAPI, "search", AsyncMock(side_effect=error))

    async with Client(mcp) as client:
        with pytest.raises(ToolError, match=re.escape(expected)):
            await client.call_tool("ds_web_search", {"query": "query"})


def test_search_response_rejects_invalid_result() -> None:
    """校验非法 Search 成功响应结构"""
    with pytest.raises(ValidationError):
        SearchResponse.model_validate({"results": [{"title": "missing required fields"}]})


def test_search_request_serializes_for_api() -> None:
    """校验 Search 请求按 JSON 模式序列化"""
    request = build_search_request(
        env=load_env(),
        query="query",
        count=3,
        after=date(2025, 1, 1),
    )

    assert json.loads(request.model_dump_json(exclude_none=True)) == {
        "query": "query after:2025-01-01",
        "count": 3,
    }
