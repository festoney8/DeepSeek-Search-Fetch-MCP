from collections.abc import AsyncIterator
from datetime import date
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.exceptions import ToolError
from fastmcp.server.lifespan import lifespan
from pydantic import Field, StringConstraints

from deepseek_search_fetch_mcp.api import DeepSeekAPI, DeepSeekAPIError, FetchResponse, SearchResponse
from deepseek_search_fetch_mcp.env import EnvConfig, load_env
from deepseek_search_fetch_mcp.request import build_fetch_request, build_search_request


@lifespan
async def app_lifespan(_: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """加载环境配置并创建共享 API 客户端"""
    env = load_env()
    async with DeepSeekAPI(env.api_key.get_secret_value(), env.api_timeout) as api:
        yield {"env": env, "api": api}


mcp = FastMCP(
    name="DeepSeek Search & Fetch",
    version="0.1.0",
    instructions=(
        "Use ds_web_search to search the web and ds_web_fetch to retrieve a public HTTP or HTTPS URL. "
        "Server-configured search options are applied automatically."
    ),
    lifespan=app_lifespan,
    mask_error_details=True,
    on_duplicate="error",
)


@mcp.tool(
    name="ds_web_fetch",
    title="DeepSeek Web Fetch",
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True},
)
async def ds_web_fetch(
    url: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=8192),
        Field(description="Public HTTP or HTTPS URL to fetch"),
    ],
    ctx: Context = CurrentContext(),  # noqa: B008
) -> FetchResponse:
    """Fetch a public HTTP or HTTPS URL through the DeepSeek Fetch API."""
    api: DeepSeekAPI = ctx.lifespan_context["api"]
    try:
        request = build_fetch_request(url)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc

    try:
        return await api.fetch(request)
    except DeepSeekAPIError as exc:
        details = ", ".join(
            f"{name}={value}"
            for name, value in (("status", exc.status), ("code", exc.code), ("type", exc.error_type))
            if value is not None
        )
        raise ToolError(f"{exc} [{details}]" if details else str(exc)) from exc


@mcp.tool(
    name="ds_web_search",
    title="DeepSeek Web Search",
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True},
)
async def ds_web_search(
    query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
        Field(description="Search query, including any exact phrases enclosed in double quotes"),
    ],
    ori_question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=128),
        Field(description="Original user question that triggered the search"),
    ]
    | None = None,
    sites: Annotated[
        list[str] | None,
        Field(description="Optional list of bare domains used to restrict the search"),
    ] = None,
    after: Annotated[date | None, Field(description="Only include results on or after this date")] = None,
    before: Annotated[date | None, Field(description="Only include results on or before this date")] = None,
    ctx: Context = CurrentContext(),  # noqa: B008
) -> SearchResponse:
    """Search the web through the DeepSeek Search API."""
    env: EnvConfig = ctx.lifespan_context["env"]
    api: DeepSeekAPI = ctx.lifespan_context["api"]
    try:
        request = build_search_request(
            env=env,
            query=query,
            ori_question=ori_question,
            sites=sites,
            after=after,
            before=before,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc

    try:
        return await api.search(request)
    except DeepSeekAPIError as exc:
        details = ", ".join(
            f"{name}={value}"
            for name, value in (("status", exc.status), ("code", exc.code), ("type", exc.error_type))
            if value is not None
        )
        raise ToolError(f"{exc} [{details}]" if details else str(exc)) from exc


def main() -> None:
    """启动 FastMCP 服务"""
    mcp.run()


if __name__ == "__main__":
    main()
