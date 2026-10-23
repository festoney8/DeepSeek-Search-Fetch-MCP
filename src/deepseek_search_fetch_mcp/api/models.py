from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, IPvAnyAddress, StringConstraints

# 搜索文本约束
_SearchText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]

# Fetch URL 基础约束
_FetchUrl = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8192)]


def _validate_url(value: str) -> str:
    """校验 HTTP/HTTPS URL"""
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or any(char.isspace() for char in value)
    ):
        raise ValueError("must be an HTTP/HTTPS URL with a host and without credentials")
    return value


class SearchRequest(BaseModel):
    """Search API 请求"""

    model_config = ConfigDict(extra="forbid")

    query: _SearchText
    count: int | None = Field(default=None, ge=1, le=50)
    ori_question: _SearchText | None = None
    localization: IPvAnyAddress | None = None
    need_content: bool | None = None


class SearchResult(BaseModel):
    """Search API 单条结果"""

    model_config = ConfigDict(extra="allow")

    rerank_score: float = Field(ge=0, le=3)
    title: str
    url: str
    snippet: str
    summary: str
    content: str
    site_name: str | None
    site_icon: str | None
    date: str | None
    authority: int = Field(ge=-1, le=4)


class SearchResponse(BaseModel):
    """Search API 成功响应"""

    model_config = ConfigDict(extra="allow")

    results: list[SearchResult]


class FetchRequest(BaseModel):
    """Fetch API 请求"""

    model_config = ConfigDict(extra="forbid")

    url: Annotated[_FetchUrl, AfterValidator(_validate_url)]


class FetchResponse(BaseModel):
    """Fetch API 成功响应"""

    model_config = ConfigDict(extra="allow")

    title: str
    content: str


class APIErrorDetail(BaseModel):
    """DeepSeek API 错误详情"""

    model_config = ConfigDict(extra="allow")

    message: str
    type: str
    param: None = None
    code: str | None = None


class APIErrorResponse(BaseModel):
    """DeepSeek API 错误响应"""

    model_config = ConfigDict(extra="allow")

    error: APIErrorDetail
