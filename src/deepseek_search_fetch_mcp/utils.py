from collections.abc import Sequence

from iso639 import is_language
from validators import domain


def normalize_domains(domains: Sequence[str]) -> tuple[str, ...]:
    """规范化裸域名"""
    normalized = tuple(dict.fromkeys(value.strip() for value in domains if value.strip()))
    if any(not domain(value) for value in normalized):
        raise ValueError("must contain valid bare domains")
    return normalized


def normalize_languages(codes: Sequence[str]) -> tuple[str, ...]:
    """规范化 ISO 639-1 语言码"""
    languages: list[str] = []
    for code in codes:
        normalized = code.strip().lower()
        if not is_language(normalized, "pt1"):
            raise ValueError("must contain valid ISO 639-1 language codes")
        languages.append(normalized)
    return tuple(dict.fromkeys(languages))
