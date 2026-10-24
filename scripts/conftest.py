import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """注册真实 API Key 参数"""
    parser.addoption("--api-key", action="store", required=True, help="DeepSeek API key for live tests")


def pytest_configure(config: pytest.Config) -> None:
    """注册真实请求标记"""
    config.addinivalue_line("markers", "live: requires a real DeepSeek API key and network access")


@pytest.fixture
def anyio_backend() -> str:
    """限定 AnyIO 使用 asyncio 后端"""
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated_deepseek_env(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """清理 DeepSeek 环境并注入 API Key"""
    for name in tuple(os.environ):
        if name.startswith("DEEPSEEK_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", request.config.getoption("api_key"))
