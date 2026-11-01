"""只从 SQLite 重算评分，失败保留历史及旧评分并标记过期。"""

from datetime import datetime, timezone
import logging

from database.store import HotspotStore
from services.scoring import score_hotspot

logger = logging.getLogger('ai_hotspot_radar.scoring')


def recalculate_scores(store: HotspotStore, *, now: datetime | None = None) -> dict:
    """先计算全部结果再原子保存；校验输入未被另一个刷新修改。"""
    now = now or datetime.now(timezone.utc)
    try:
        inputs = store.scoring_inputs()
        results = [score_hotspot(item, item['snapshots'], now=now) for item in inputs]
        store.save_scores(results, expected_inputs=inputs)
        logger.info('scoring updated=%d', len(results))
        return {'updated': len(results), 'error': None}
    except Exception as error:
        # 不记录第三方异常正文，避免把任何潜在的凭据泄漏到日志或网页。
        logger.error('scoring failed type=%s', type(error).__name__)
        try:
            store.mark_scores_stale()
        except Exception as mark_error:
            logger.error('scoring stale-marker failed type=%s', type(mark_error).__name__)
        return {'updated': 0, 'error': '评分计算或保存失败，已保留采集数据及旧评分。'
                '数据可能在计算期间更新，请点击“重新计算评分”重试；仍失败时检查运行日志和数据库权限。'}
