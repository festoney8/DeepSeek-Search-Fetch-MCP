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
    name="DeepSeek Search and Fetch",
    version="0.1.0",
    instructions=(
        """This MCP server provides DeepSeek-powered web search and fetch through two MCP tools: `ds_web_search` and `ds_web_fetch`.

## ds_web_search
Use `ds_web_search` to discover current web information and return ranked, structured results.
It is recommended when you need to find sources for a question, do research, search for documents, compare coverage across the web, or restrict results to specific sites or publication dates.

## ds_web_fetch
Use `ds_web_fetch` to get the agent-friendly Markdown content of a specific webpage. It is recommended when you already have a URL and need to read, summarize, quote, or extract information from that page. Only public HTTP or HTTPS URLs are supported.
If the URL suffix indicates that the content is agent-friendly, such as formats like JSON, XML, CSV, YAML, YML, MD, TXT, or programming language extensions, you can access the content directly by visiting the URL instead of use ds_web_fetch.
If the URL suffix indicates that the content is binary, such as an image, audio, video, or binary file, do not use ds_web_fetch to fetch the information.

## Combined usage
A common workflow when investigate and survey is to use `ds_web_search` to find relevant pages, then `ds_web_fetch` to inspect a selected result in detail.

## Recommendation
If need to perform large number of ds_web_search or combined use, using this MCP in a subagent to avoid consuming too much LLM context.
"""
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
        Field(description=("(Required) HTTP or HTTPS URL to fetch, up to 8192 characters.")),
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
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
        Field(
            description=(
                "(Required) Search query, up to 100 Unicode characters. "
                "To perform an exact match on certain words in this query, wrap it in double quotes. "
                "This is useful for searching for proper nouns or ensuring that search results must contain a specific word."
            )
        ),
    ],
    ori_question: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=128),
        Field(
            description=(
                "(Optional) Original user question that triggered the search, up to 128 Unicode characters. "
                "Providing it can improve query understanding; omit it when unavailable."
            )
        ),
    ] = None,
    count: Annotated[
        int | None,
        Field(
            ge=1,
            le=50,
            description=(
                "(Optional) Number of search results to request, from 1 to 50. "
                "If omitted, the server configured default count is used. "
            ),
        ),
    ] = None,
    sites: Annotated[
        list[str] | None,
        Field(
            description=(
                "(Optional) Restrict results to the given sites, for example ['github.com', 'huggingface.co']. "
                "Domains only, do not include schemes, paths or wildcards."
            )
        ),
    ] = None,
    lang: Annotated[
        list[str] | None,
        Field(
            description=(
                "(Optional) Restrict results to the given language. "
                "ISO-639-1 format, for example ['zh', 'en']. "
                "Passing an empty list means no language restriction."
                "If omitted, the server configured default language is used. "
            )
        ),
    ] = None,
    after: Annotated[
        date | None,
        Field(description=("(Optional) YYYY-MM-DD date to restrict results published after this date.")),
    ] = None,
    before: Annotated[
        date | None,
        Field(description=("(Optional) YYYY-MM-DD date to restrict results published before this date.")),
    ] = None,
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
            count=count,
            sites=sites,
            lang=lang,
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
