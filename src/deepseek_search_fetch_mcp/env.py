import os
import re
from ipaddress import IPv4Address

from iso639 import is_language
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from validators import domain

# 支持的环境变量名
_ENV_NAMES = (
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_API_TIMEOUT",
    "DEEPSEEK_SEARCH_COUNT",
    "DEEPSEEK_SEARCH_LOCALIZATION",
    "DEEPSEEK_SEARCH_NEED_CONTENT",
    "DEEPSEEK_SEARCH_LANG",
    "DEEPSEEK_SEARCH_EXCLUDE_WORDS",
    "DEEPSEEK_SEARCH_EXCLUDE_SITES",
)


def _split_items(value: object, separator: str) -> list[str]:
    """拆分并清理环境变量列表项"""
    if not isinstance(value, str):
        raise ValueError("must be a string")
    return [item.strip() for item in value.split(separator) if item.strip()]


class EnvConfigError(ValueError):
    """环境配置异常"""

    issues: tuple[str, ...]

    def __init__(self, issues: tuple[str, ...]) -> None:
        """初始化配置异常"""
        self.issues = issues
        super().__init__("Invalid environment configuration: " + "; ".join(issues))


class EnvConfig(BaseModel):
    """环境配置"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # API 配置
    api_key: SecretStr = Field(validation_alias="DEEPSEEK_API_KEY")
    api_timeout: float = Field(
        default=15,
        gt=0,
        allow_inf_nan=False,
        validation_alias="DEEPSEEK_API_TIMEOUT",
    )

    # Search 配置
    search_count: int | None = Field(default=None, ge=1, le=50, validation_alias="DEEPSEEK_SEARCH_COUNT")
    search_localization: IPv4Address | None = Field(
        default=None,
        validation_alias="DEEPSEEK_SEARCH_LOCALIZATION",
    )
    search_need_content: bool | None = Field(
        default=None,
        validation_alias="DEEPSEEK_SEARCH_NEED_CONTENT",
    )
    search_lang: tuple[str, ...] = Field(default=(), validation_alias="DEEPSEEK_SEARCH_LANG")
    search_exclude_words: tuple[str, ...] = Field(
        default=(),
        validation_alias="DEEPSEEK_SEARCH_EXCLUDE_WORDS",
    )
    search_exclude_sites: tuple[str, ...] = Field(
        default=(),
        validation_alias="DEEPSEEK_SEARCH_EXCLUDE_SITES",
    )

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, value: object) -> object:
        """校验 API Key 格式"""
        if not isinstance(value, str) or re.fullmatch(r"sk-[a-zA-Z0-9]+", value) is None:
            raise ValueError("must match ^sk-[a-zA-Z0-9]+$")
        return value

    @field_validator("search_localization")
    @classmethod
    def _validate_localization(cls, value: IPv4Address | None) -> IPv4Address | None:
        """校验公网 IPv4"""
        if value is not None and (not value.is_global or value.is_multicast):
            raise ValueError("must be a global IPv4 address")
        return value

    @field_validator("search_need_content", mode="before")
    @classmethod
    def _parse_need_content(cls, value: object) -> bool | None:
        """解析可选布尔值"""
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.lower()
            if normalized in {"true", "1"}:
                return True
            if normalized in {"false", "0"}:
                return False
        raise ValueError("must be true, 1, false, or 0")

    @field_validator("search_lang", mode="before")
    @classmethod
    def _parse_languages(cls, value: object) -> tuple[str, ...]:
        """解析并校验 ISO 639-1 语言码"""
        languages: list[str] = []
        for code in _split_items(value, ","):
            code = code.lower()
            if not is_language(code, "pt1"):
                raise ValueError("must contain valid ISO 639-1 language codes")
            languages.append(code)
        return tuple(dict.fromkeys(languages))

    @field_validator("search_exclude_words", mode="before")
    @classmethod
    def _parse_exclude_words(cls, value: object) -> tuple[str, ...]:
        """解析并校验排除词"""
        words = _split_items(value, "|")
        if any(char == '"' or not char.isprintable() for word in words for char in word):
            raise ValueError("must not contain double quotes or control characters")
        return tuple(dict.fromkeys(words))

    @field_validator("search_exclude_sites", mode="before")
    @classmethod
    def _parse_exclude_sites(cls, value: object) -> tuple[str, ...]:
        """解析并校验排除域名"""
        sites = _split_items(value, "|")
        if any(not domain(site) for site in sites):
            raise ValueError("must contain valid bare domains")
        return tuple(dict.fromkeys(sites))


def load_env() -> EnvConfig:
    """读取并校验当前环境配置"""
    values: dict[str, str] = {}
    for name in _ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            values[name] = value

    try:
        return EnvConfig.model_validate(values)
    except ValidationError as exc:
        issues = tuple(
            f"{error['loc'][0]}: {error['msg']}" for error in exc.errors(include_input=False, include_url=False)
        )
        raise EnvConfigError(issues) from None
