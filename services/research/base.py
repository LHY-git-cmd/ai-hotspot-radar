"""与搜索厂商无关的数据协议；未知 credits 不补零。"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    published_at: str | None = None


@dataclass(frozen=True)
class SearchReply:
    results: list[SearchResult]
    credits: Decimal | int | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class ExtractResult:
    url: str
    text: str = ''
    status: str = 'success'
    error: str | None = None


@dataclass(frozen=True)
class ExtractReply:
    results: list[ExtractResult]
    credits: Decimal | int | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class Quota:
    remaining: Decimal | int | None


class SearchError(Exception):
    def __init__(self, kind, message, *, credits=None):
        super().__init__(message)
        self.kind, self.credits = kind, credits


class SearchProvider(Protocol):
    name: str
    available: bool

    def search(self, query: str, **options) -> SearchReply: ...
    def extract(self, urls: list[str]) -> ExtractReply: ...


def credit_value(value):
    """只接受服务商有效非负计量；bool 和无穷值不是有效用量。"""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    result = Decimal(str(value))
    return result if result.is_finite() and result >= 0 else None
