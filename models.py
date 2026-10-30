"""定义来源无关的数据记录、采集结果和刷新统计。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

SOURCES = ('GitHub', 'Hacker News')


def utc_now() -> str:
    """返回带时区的 UTC 时间，避免受机器时区影响。"""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def as_utc_iso(value: str | int | float | None) -> str | None:
    """解析 API 的 ISO 时间或 Unix 秒；无效或缺失时间保留为空。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            date = datetime.fromtimestamp(value, tz=timezone.utc)
        elif isinstance(value, str):
            date = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if date.tzinfo is None:
                return None
        else:
            return None
        return date.astimezone(timezone.utc).isoformat(timespec='seconds')
    except (ValueError, OverflowError, OSError):
        return None


def as_score(value: object) -> int | None:
    """仅接受 API 返回的非负整数，不以零代替缺失指标。"""
    return value if type(value) is int and value >= 0 else None


@dataclass(frozen=True)
class Hotspot:
    """统一热点格式；数据库生成 id，其余字段保留来源含义。"""

    title: str
    url: str
    source: str
    category: str
    summary: str | None = None
    published_at: str | None = None
    collected_at: str = field(default_factory=utc_now)
    score: int | None = None


@dataclass
class CollectionResult:
    """保存单来源采集结果及不会阻止其他记录处理的警告。"""

    items: list[Hotspot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SaveResult:
    """区分新增、指标更新和去重跳过的记录数量。"""

    inserted: int = 0
    updated: int = 0
    skipped: int = 0


@dataclass
class SourceReport(SaveResult):
    """向页面报告每个来源的独立状态。"""

    fetched: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
