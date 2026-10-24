# DeepSeek Search Fetch MCP

**English** | [简体中文](https://github.com/festoney8/DeepSeek-Search-Fetch-MCP/blob/main/README_zh.md)

An MCP server that exposes DeepSeek Search API and Fetch API as two tools for AI agents. AI agents can fetch the latest information from the web, filter results by site, language, and date, and then get content from specified websites in Markdown format, all without leaving the MCP workflow.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyPI](https://img.shields.io/badge/PyPI-deepseek--search--fetch--mcp-3775A9?logo=pypi&logoColor=white)](https://pypi.org/project/deepseek-search-fetch-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Features

- **Safe inputs**: validate parameters before sending upstream requests
- **MCP over stdio**: run directly with `uvx` and integrate with any MCP-compatible client
- **`ds_web_search`**: search the current web through the DeepSeek Search API
- **`ds_web_fetch`**: fetch public HTTP/HTTPS pages through the DeepSeek Fetch API

## Quick Start

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python 3.11 or later
- A DeepSeek API key

### Run the server

```bash
DEEPSEEK_API_KEY="sk-**********" uvx deepseek-search-fetch-mcp
```

The server communicates over stdio. In normal use, your MCP client starts it with the configuration shown below.

## MCP Client Configuration

Require the uvx command in uv.

Add one of the following templates to the `mcpServers` section of your MCP client configuration. Replace the placeholder API key before use.

### Minimal configuration

This template uses the API key only. The timeout and all Search env fall back to their defaults.

```json
{
  "mcpServers": {
    "deepseek-search-fetch": {
      "command": "uvx",
      "args": ["deepseek-search-fetch-mcp"],
      "env": {
        "DEEPSEEK_API_KEY": "sk-**********"
      }
    }
  }
}
```

### Full configuration

This template includes every supported environment variable. Optional values can be removed or changed for your search policy.

```json
{
  "mcpServers": {
    "deepseek-search-fetch": {
      "command": "uvx",
      "args": ["deepseek-search-fetch-mcp"],
      "env": {
        "DEEPSEEK_API_KEY": "sk-**********",
        "DEEPSEEK_API_TIMEOUT": "30",
        "DEEPSEEK_SEARCH_COUNT": "20",
        "DEEPSEEK_SEARCH_LOCALIZATION": "18.8.8.8",
        "DEEPSEEK_SEARCH_NEED_CONTENT": "false",
        "DEEPSEEK_SEARCH_LANG": "zh,en",
        "DEEPSEEK_SEARCH_EXCLUDE_WORDS": "word1|word2",
        "DEEPSEEK_SEARCH_EXCLUDE_SITES": "csdn.net|baijiahao.baidu.com"
      }
    }
  }
}
```

> [!IMPORTANT]
> Keep the API key in the MCP client's environment configuration. Do not commit a configuration file containing a real key.

## Environment Variables

| Variable                        | Required | Default | Description                                                                                                                              |
| ------------------------------- | -------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `DEEPSEEK_API_KEY`              | Yes      | -       | DeepSeek API key. It must match `^sk-[a-zA-Z0-9]+$`                                                                                      |
| `DEEPSEEK_API_TIMEOUT`          | No       | `30`    | Request timeout in seconds. Must be greater than 0. Requests are not retried                                                             |
| `DEEPSEEK_SEARCH_COUNT`         | No       | `10`    | Default result count for `ds_web_search`, from 1 to 50. The tool parameter takes precedence                                              |
| `DEEPSEEK_SEARCH_LOCALIZATION`  | No       | -       | Globally routable unicast IPv4 address passed to the Search API for result localization. Usually unnecessary                            |
| `DEEPSEEK_SEARCH_NEED_CONTENT`  | No       | -       | Whether the Search API should include page content in results. Accepts `true`, `1`, `false`, or `0`, case-insensitively. Not recommended because it can consume substantial context |
| `DEEPSEEK_SEARCH_LANG`          | No       | -       | Default language restriction as comma-separated ISO 639-1 codes, such as `zh,en`. The `lang` tool parameter takes precedence             |
| `DEEPSEEK_SEARCH_EXCLUDE_WORDS` | No       | -       | Global word blacklist separated by `\|`. Each word is added as an excluded phrase and cannot contain double quotes or control characters. Not commonly used; use no more than 3 words because they consume the 128-character query limit |
| `DEEPSEEK_SEARCH_EXCLUDE_SITES` | No       | -       | Global domain blacklist separated by `\|`. Each entry must be a valid bare domain and is added as an excluded site. Use no more than 3 sites because they consume the 128-character query limit |

Empty optional variables are ignored. A non-empty value is validated when the server starts, and invalid configuration causes the server to exit instead of accepting requests.

## Tools

| Tool            | Purpose                                                                          |
| --------------- | -------------------------------------------------------------------------------- |
| `ds_web_search` | Find relevant pages with optional site, language, date, and result-count filters |
| `ds_web_fetch`  | Read a known public URL as agent-friendly content                                |

### `ds_web_search`

| Parameter      | Required | Type     | Description                                                                                                                |
| -------------- | -------- | -------- | -------------------------------------------------------------------------------------------------------------------------- |
| `query`        | Yes      | string   | Search terms. Up to 100 characters. Wrap a phrase in double quotes for an exact match                                      |
| `ori_question` | No       | string   | Original user question, up to 128 characters, used to clarify search intent                                                |
| `count`        | No       | integer  | Number of results, from 1 to 50. Overrides `DEEPSEEK_SEARCH_COUNT`; otherwise the API default is 10                        |
| `sites`        | No       | string[] | Restrict results to bare domains such as `github.com`. Do not include schemes, paths, or wildcards                         |
| `lang`         | No       | string[] | Restrict results with ISO 639-1 codes such as `["zh", "en"]`. An empty list disables the environment default for that call |
| `after`        | No       | date     | Include results after this `YYYY-MM-DD` date                                                                               |
| `before`       | No       | date     | Include results before this `YYYY-MM-DD` date. `after` must not be later than `before`                                     |

The server converts `sites`, `lang`, `after`, `before`, and the configured exclusions into DeepSeek search syntax. The final query, including generated filters, must be no longer than 128 characters.

### `ds_web_fetch`

| Parameter | Required | Type   | Description                                     |
| --------- | -------- | ------ | ----------------------------------------------- |
| `url`     | Yes      | string | Public HTTP or HTTPS URL, up to 8192 characters |

The URL must have a host, must not contain credentials or whitespace, and must not target `localhost`, a private address, or another non-public IP address.

## Usage

Ask your MCP client to search for current information:

```text
Search GitHub and Hugging Face for recent MCP server examples, then fetch the most relevant page.
```

The client may call `ds_web_search` with:

```json
{
  "query": "MCP server Python",
  "sites": ["github.com", "huggingface.co"],
  "lang": ["en"],
  "count": 15,
  "after": "2026-01-01"
}
```

It can then call `ds_web_fetch` with a selected result:

```json
{
  "url": "https://github.com/modelcontextprotocol/python-sdk"
}
```

`ds_web_search` returns a `results` array containing fields such as `title`, `url`, `summary`, `content`, `site_name`, `date`, `authority`, and `rerank_score`. `ds_web_fetch` returns the page `title` and `content`.

## Behavior and Validation

- Tool parameters are validated before any DeepSeek API request is made
- `count` and `lang` tool parameters override their server-level environment defaults
- Passing `lang: []` disables the configured language restriction for that search
- Site, language, date, and exclusion filters are converted to DeepSeek search syntax
- Only public HTTP/HTTPS URLs are accepted by `ds_web_fetch`
- Upstream error status, code, and type are included in MCP tool errors when available

> [!TIP]
> Use `ds_web_search` first to discover sources, then call `ds_web_fetch` only for the pages that need detailed reading. This keeps client context smaller and avoids fetching irrelevant pages.

## Development

Clone the repository and install the project environment:

```bash
git clone https://github.com/festoney8/DeepSeek-Search-Fetch-MCP.git
cd DeepSeek-Search-Fetch-MCP
uv sync
```

Run the local server:

```bash
DEEPSEEK_API_KEY="sk-**********" uv run deepseek-search-fetch-mcp
```

Run the project checks:

```bash
uvx ruff format .
uvx ruff check --fix .
uvx ty check --fix .
```

### Project layout

```text
src/deepseek_search_fetch_mcp/
├── main.py        # FastMCP server and tools
├── env.py         # Environment loading and validation
├── request.py     # Request validation and search syntax construction
├── utils.py       # Domain and language normalization
└── api/
    ├── api.py     # DeepSeek HTTP client
    └── models.py  # Request and response models
scripts/           # Testing scripts
```

## Tech Stack

- [FastMCP](https://gofastmcp.com/) for the MCP server and tool schemas
- [aiohttp](https://docs.aiohttp.org/) for asynchronous DeepSeek API requests
- [Pydantic](https://docs.pydantic.dev/) for typed configuration and validation
- [validators](https://github.com/python-validators/validators) for URL and domain checks
- [iso639-lang](https://pypi.org/project/iso639-lang/) for ISO 639-1 language validation

## Documentation

- [Design](docs/design/)
- [Testing](/scripts/README.md)
- [DeepSeek Search & Fetch](https://api-docs.deepseek.com/guides/search)
- [DeepSeek Search API](https://api-docs.deepseek.com/api/search/)
- [DeepSeek Fetch API](https://api-docs.deepseek.com/api/fetch/)
