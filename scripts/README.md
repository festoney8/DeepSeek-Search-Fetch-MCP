# 测试脚本

本目录使用 Pytest 验证 DeepSeek Search 和 Fetch 的成功与失败路径

- `test_search.py`：Search 环境配置、请求拼装、MCP 工具参数校验和错误映射
- `test_fetch.py`：Fetch URL 安全校验、API 会话、传输异常、响应解析和错误映射
- `conftest.py`：提供 `--api-key`，隔离当前进程中的全部 `DEEPSEEK_*` 环境变量

## 安全要求

不要在测试文件、命令历史、日志或版本控制中保存真实 API Key。建议先交互式读入临时变量：

```bash
read -rs DEEPSEEK_TEST_API_KEY
```

然后按文件分别运行测试。两个文件各含一条真实 API 请求，网络、鉴权、配额或响应结构异常都会直接导致测试失败：

```bash
uv run pytest scripts/test_search.py --api-key "$DEEPSEEK_TEST_API_KEY"
uv run pytest scripts/test_fetch.py --api-key "$DEEPSEEK_TEST_API_KEY"
```

命令行参数可能短暂出现在进程列表中，不要使用长期共享环境中的生产密钥运行本地测试

## 离线测试

使用符合格式的占位 Key 并排除 `live` 标记，可验证全部 mock 分支，不访问 DeepSeek API：

```bash
uv run pytest scripts/test_search.py --api-key sk-offline -m "not live"
uv run pytest scripts/test_fetch.py --api-key sk-offline -m "not live"
```

## 环境变量

- Pytest 每次启动都会清除当前进程的 `DEEPSEEK_*` 环境变量
- `DEEPSEEK_API_KEY` 只由 `--api-key` 注入
- 其余 Search 环境变量由测试用例通过 `monkeypatch` 显式设置，不读取本地 `.env`
- `live` 用例没有跳过策略，失败时保留原始错误用于排查

## 代码检查

```bash
uvx ruff format .
uvx ruff check --fix .
uvx ty check --fix .
```
