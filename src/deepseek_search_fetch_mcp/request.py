from collections.abc import Sequence
from datetime import date
from ipaddress import IPv6Address, ip_address
from urllib.parse import urlsplit

from pydantic import ValidationError
from validators import url as validate_url

from deepseek_search_fetch_mcp.api import FetchRequest, SearchRequest
from deepseek_search_fetch_mcp.env import EnvConfig
from deepseek_search_fetch_mcp.utils import normalize_domains, normalize_languages


def build_fetch_request(url: str) -> FetchRequest:
    """构建 Fetch API 请求"""
    try:
        request = FetchRequest(url=url)
    except ValidationError:
        raise ValueError("url must be a valid HTTP/HTTPS URL") from None

    if not validate_url(request.url, private=False):
        raise ValueError("url must target a public host")

    host = urlsplit(request.url).hostname
    if host is None:
        raise ValueError("url must include a host")

    normalized_host = host.rstrip(".").lower()
    if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
        raise ValueError("url host must not be local")

    try:
        ip = ip_address(normalized_host)
    except ValueError:
        return request

    if isinstance(ip, IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if not ip.is_global or ip.is_multicast or (isinstance(ip, IPv6Address) and ip.is_site_local):
        raise ValueError("url host must be a public IP address")

    return request


def build_search_request(
    *,
    env: EnvConfig,
    query: str,
    ori_question: str | None = None,
    count: int | None = None,
    sites: Sequence[str] | None = None,
    lang: Sequence[str] | None = None,
    after: date | None = None,
    before: date | None = None,
) -> SearchRequest:
    """构建 Search API 请求"""
    base_query = query.strip()
    if not base_query:
        raise ValueError("query must not be empty")

    parts = [base_query]
    if sites:
        try:
            site_values = normalize_domains(sites)
        except ValueError:
            raise ValueError("sites must contain valid bare domains") from None
        if site_values:
            parts.append(" OR ".join(f"site:{site}" for site in site_values))

    if after is not None and before is not None and after > before:
        raise ValueError("after must be on or before before")
    if after is not None:
        parts.append(f"after:{after.isoformat()}")

    if before is not None:
        parts.append(f"before:{before.isoformat()}")

    languages = env.search_lang if lang is None else normalize_languages(lang)
    if languages:
        parts.append(f"lang:{','.join(languages)}")

    parts.extend(f'-"{word}"' for word in env.search_exclude_words)
    parts.extend(f"-site:{site}" for site in env.search_exclude_sites)

    final_query = " ".join(parts)

    normalized_question = ori_question.strip() if ori_question is not None else None
    effective_count = env.search_count if count is None else count
    return SearchRequest(
        query=final_query,
        count=effective_count,
        ori_question=normalized_question or None,
        localization=env.search_localization,
        need_content=env.search_need_content,
    )
