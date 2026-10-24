import json
from types import TracebackType
from typing import Self, TypeVar

import aiohttp
from pydantic import BaseModel, ValidationError

from .models import APIErrorResponse, FetchRequest, FetchResponse, SearchRequest, SearchResponse

_BASE_URL = "https://api.deepseek.com"
_SEARCH_PATH = "/v1/tools/search"
_FETCH_PATH = "/v1/tools/fetch"

_ResponseT = TypeVar("_ResponseT", bound=BaseModel)


class DeepSeekAPIError(Exception):
    """DeepSeek API 调用异常"""

    status: int | None
    code: str | None
    error_type: str | None

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        error_type: str | None = None,
    ) -> None:
        """初始化 API 异常"""
        super().__init__(message)
        self.status = status
        self.code = code
        self.error_type = error_type


class DeepSeekAPI:
    """DeepSeek Search/Fetch API 客户端"""

    def __init__(self, api_key: str, timeout: float = 30) -> None:
        """初始化客户端"""
        self._api_key = api_key
        self._timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> Self:
        """创建 HTTP 会话"""
        if self._session is not None:
            raise RuntimeError("Client session is already open")
        self._session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=aiohttp.ClientTimeout(total=self._timeout),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """关闭 HTTP 会话"""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def search(self, request: SearchRequest) -> SearchResponse:
        """调用 Search API"""
        return await self._post(_SEARCH_PATH, request, SearchResponse)

    async def fetch(self, request: FetchRequest) -> FetchResponse:
        """调用 Fetch API"""
        return await self._post(_FETCH_PATH, request, FetchResponse)

    async def _post(self, path: str, request: BaseModel, response_type: type[_ResponseT]) -> _ResponseT:
        """发送 POST 请求并解析响应"""
        if self._session is None:
            raise RuntimeError("Client session is not open")

        payload = request.model_dump(mode="json", exclude_none=True)
        try:
            async with self._session.post(f"{_BASE_URL}{path}", json=payload) as response:
                status = response.status
                text = await response.text()
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise DeepSeekAPIError(f"DeepSeek API request failed: {exc}") from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DeepSeekAPIError(f"DeepSeek API returned invalid JSON, status code: {status}", status=status) from exc

        if status < 200 or status >= 300:
            try:
                error_response = APIErrorResponse.model_validate(data)
            except ValidationError as exc:
                raise DeepSeekAPIError(
                    f"DeepSeek API request failed, status code: {status}",
                    status=status,
                ) from exc
            raise DeepSeekAPIError(
                error_response.error.message,
                status=status,
                code=error_response.error.code,
                error_type=error_response.error.type,
            )

        try:
            return response_type.model_validate(data)
        except ValidationError as exc:
            raise DeepSeekAPIError(
                "DeepSeek API returned an invalid response",
                status=status,
            ) from exc
