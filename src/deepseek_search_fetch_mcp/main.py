import logging
from collections.abc import AsyncIterator
from datetime import date
from importlib.metadata import version as get_version
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.exceptions import ToolError
from fastmcp.server.lifespan import lifespan
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from deepseek_search_fetch_mcp.api import DeepSeekAPI, DeepSeekAPIError
from deepseek_search_fetch_mcp.env import EnvConfig, EnvConfigError, load_env
from deepseek_search_fetch_mcp.request import build_fetch_request, build_search_request

logger = logging.getLogger(__name__)


class SearchToolResult(BaseModel):
    """MCP 搜索单条结果"""

    model_config = ConfigDict(extra="allow")

    rerank_score: float = Field(
        ge=0,
        le=3,
        description=(
            "Relevance score from 0 to 3 that combines relevance, authority, and freshness. "
            "Scores of 1.5 or higher are considered high-quality results."
        ),
    )
    title: str = Field(description="The title of the webpage.")
    url: str = Field(description="The URL of the webpage.")
    summary: str = Field(description="The summary of the webpage content.")
    content: str = Field(description="The full page content, or an empty string if showing content is disabled.")
    site_name: str | None = Field(description="The name of the site, or null when unavailable.")
    date: str | None = Field(description="The publication date, null when unknown.")
    authority: int = Field(
        ge=-1,
        le=4,
        description=(
            "The source-authority tier, from 0 to 4. A value of -1 indicates that the tier is unknown. "
            "Values of 3 or higher indicate highly authoritative sources."
        ),
    )


class SearchToolResponse(BaseModel):
    """MCP 搜索成功响应"""

    model_config = ConfigDict(extra="allow")

    results: list[SearchToolResult] = Field(description="A ranked list of search results.")


class FetchToolResponse(BaseModel):
    """MCP Fetch 成功响应"""

    model_config = ConfigDict(extra="allow")

    title: str = Field(description="The page title, or an empty string if unavailable.")
    content: str = Field(description="The fetched page content in Markdown format.")


@lifespan
async def app_lifespan(_: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """加载环境配置并创建共享 API 客户端"""
    env = load_env()
    async with DeepSeekAPI(env.api_key.get_secret_value(), env.api_timeout) as api:
        yield {"env": env, "api": api}


mcp = FastMCP(
    name="DeepSeek Search and Fetch",
    version=get_version("deepseek-search-fetch-mcp"),
    instructions=(
        """This MCP server provides web search and page fetching powered by DeepSeek through two MCP tools: `ds_web_search` and `ds_web_fetch`.

## ds_web_search
Use `ds_web_search` to discover current web information and return ranked, structured results.
Use it to find sources, conduct research, discover documents, compare information across sites, or filter results by site, language or publication date.

## ds_web_fetch
Use `ds_web_fetch` to fetch the page content as agent-friendly Markdown of a specific webpage. It is recommended when you already have a URL and need to read, summarize, quote, or extract information from that page. Only public HTTP or HTTPS URLs are supported.
If the URL suffix indicates that the content is agent-friendly, such as formats like JSON, XML, CSV, YAML, YML, MD, TXT, or programming language extensions, you can access the content directly by visiting the URL instead of using ds_web_fetch.
If the URL suffix indicates that the content is binary, such as an image, audio, video, or binary file, do not use ds_web_fetch to fetch the information.

## Combined usage
A common workflow when investigate and survey is to use `ds_web_search` to find relevant pages, then `ds_web_fetch` to inspect a selected result in detail.

## Recommendation
For tasks that require many searches, delegate the research to a subagent to avoid consuming too much LLM context.
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
) -> FetchToolResponse:
    """Fetch a public HTTP or HTTPS URL through the DeepSeek Fetch API."""
    api: DeepSeekAPI = ctx.lifespan_context["api"]
    try:
        request = build_fetch_request(url)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc

    try:
        response = await api.fetch(request)
    except DeepSeekAPIError as exc:
        details = ", ".join(
            f"{name}={value}"
            for name, value in (("status", exc.status), ("code", exc.code), ("type", exc.error_type))
            if value is not None
        )
        raise ToolError(f"{exc} [{details}]" if details else str(exc)) from exc

    return FetchToolResponse.model_validate(response.model_dump())


@mcp.tool(
    name="ds_web_search",
    title="DeepSeek Web Search",
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True},
)
async def ds_web_search(
    query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
        Field(
            description=(
                "(Required) Search query. Consisting of keywords, phrases, or a sentence. "
                "To search for an exact word or phrase, enclose it in double quotation marks "
                "whih is useful for proper names or phrases that should appear exactly in the results. "
                "Before sending the API request, this tool combines params `query, lang, sites, after, before` "
                "into the final search expression, which must not exceed 128 Unicode characters. "
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
                "(Optional) Number of search results to request, from 1 to 50. Usually 10~30 is used. "
                "If omitted, the server uses the default count configured by the user."
            ),
        ),
    ] = None,
    sites: Annotated[
        list[str] | None,
        Field(
            description=(
                "(Optional) Restrict results to specific website domains or subdomains, "
                'for example ["test.example1.com", "example2.net"]. '
                "Use bare domain names only, do not include URL schemes, paths, or wildcards. "
                "Prefer no more than three domains, as each domain adds to the final search expression "
                "which must not exceed 128 Unicode characters."
            )
        ),
    ] = None,
    lang: Annotated[
        list[str] | None,
        Field(
            description=(
                "(Optional) Restrict results to the specified languages using "
                'ISO 639-1 language codes, for example ["zh", "en"] or ["ja"]. '
                "Usually omit this parameter unless a specific language restriction is needed."
                "If omitted, the server uses the default language configured by the user. "
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
) -> SearchToolResponse:
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
        response = await api.search(request)
    except DeepSeekAPIError as exc:
        details = ", ".join(
            f"{name}={value}"
            for name, value in (("status", exc.status), ("code", exc.code), ("type", exc.error_type))
            if value is not None
        )
        raise ToolError(f"{exc} [{details}]" if details else str(exc)) from exc

    return SearchToolResponse.model_validate(
        response.model_dump(exclude={"results": {"__all__": {"snippet", "site_icon"}}})
    )


def main() -> None:
    """启动 FastMCP 服务"""
    try:
        mcp.run()
    except EnvConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
