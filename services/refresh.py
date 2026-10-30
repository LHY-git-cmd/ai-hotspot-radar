"""独立执行每个来源的采集和保存，使故障局限在对应来源。"""

from collections.abc import Callable
import sqlite3

from collectors.http import CollectionError
from database.store import HotspotStore
from models import CollectionResult, SourceReport


def refresh_sources(store: HotspotStore,
                    collectors: dict[str, Callable[[], CollectionResult]]) -> dict[str, SourceReport]:
    """每个来源单独事务；意外异常只报告类型，无远程正文或密钥。"""
    reports = {}
    for source, collector in collectors.items():
        try:
            result = collector()
            saved = store.save(result.items)
            reports[source] = SourceReport(
                fetched=len(result.items), inserted=saved.inserted,
                updated=saved.updated, skipped=saved.skipped, warnings=result.warnings,
            )
        except CollectionError as error:
            reports[source] = SourceReport(error=str(error))
        except (sqlite3.Error, OSError):
            reports[source] = SourceReport(error=f'{source} 保存失败，请检查数据库路径、磁盘空间和写入权限。')
        except Exception as error:
            # 故障隔离的最后边界，不能把可能含凭据的异常详情直接展示。
            reports[source] = SourceReport(error=f'{source} 处理失败（{type(error).__name__}），其他来源继续处理。')
    return reports
