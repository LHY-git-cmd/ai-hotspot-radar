"""独立执行每个来源的采集和保存，使故障局限在对应来源。"""

from collections.abc import Callable
import sqlite3
import logging
import json
from datetime import datetime
from uuid import uuid4

from collectors.http import CollectionError
from database.store import HotspotStore
from models import CollectionResult, SourceReport, utc_now
from services.recalculate import recalculate_scores

logger = logging.getLogger('ai_hotspot_radar.refresh')


def refresh_sources(store: HotspotStore,
                    collectors: dict[str, Callable[[], CollectionResult]], *,
                    cycle_id: str | None = None, now: datetime | None = None) -> dict[str, SourceReport]:
    """每个来源单独事务；意外异常只报告类型，无远程正文或密钥。"""
    reports = {}
    cycle_id = cycle_id or uuid4().hex
    for source, collector in collectors.items():
        started_at = utc_now()
        try:
            previous = store.collection_run(cycle_id, source)
            if previous and previous['status'] != 'failed':
                reports[source] = SourceReport(**{name: previous[name] for name in (
                    'fetched', 'inserted', 'updated', 'skipped', 'snapshots')},
                    warnings=json.loads(previous['warnings']) + ['该周期已完成，已复用原结果，未再次采集。'])
                continue
            result = collector()
            saved = store.save(result.items, cycle_id=cycle_id, source=source,
                               started_at=started_at, warnings=result.warnings)
            reports[source] = SourceReport(
                fetched=len(result.items), inserted=saved.inserted,
                updated=saved.updated, skipped=saved.skipped, snapshots=saved.snapshots,
                warnings=list(result.warnings),
            )
            logger.info('cycle=%s source=%s fetched=%d snapshots=%d', cycle_id, source,
                        len(result.items), saved.snapshots)
        except CollectionError as error:
            reports[source] = SourceReport(error=str(error))
        except (sqlite3.Error, OSError):
            reports[source] = SourceReport(error=f'{source} 保存失败，请检查数据库路径、磁盘空间和写入权限。')
        except Exception as error:
            # 故障隔离的最后边界，不能把可能含凭据的异常详情直接展示。
            reports[source] = SourceReport(error=f'{source} 处理失败（{type(error).__name__}），其他来源继续处理。')
        if reports[source].error:
            logger.warning('cycle=%s source=%s collection failed', cycle_id, source)
            try:
                store.record_failure(cycle_id, source, started_at, reports[source].error)
            except Exception as record_error:
                logger.error('cycle=%s source=%s failure-record type=%s', cycle_id, source,
                             type(record_error).__name__)
                reports[source].warnings.append('采集失败状态未能写入数据库，请检查运行日志与数据库权限。')
    scoring = recalculate_scores(store, now=now)
    if scoring['error']:
        for report in reports.values():
            report.warnings.append(scoring['error'])
    return reports
