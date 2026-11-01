"""在持久化分数上执行轻量筛选排序，结果不受筛选集合的原始热度影响。"""

from datetime import datetime, timezone
import json

from services.normalization import normalize_title
from services.trends import parse_time
from services import scoring_rules as rules

CATEGORIES = ('AI 工具', 'AI 编程', '开源项目', 'AI 讨论/其他')
SORT_OPTIONS = {
    '综合分': 'composite_score', '热度与趋势分': 'heat_score', '视频选题价值分': 'video_score',
    '当前热度分': 'heat.current', '近期增长分': 'heat.growth', '时效性分': 'heat.recency',
    '实用价值分': 'video.practical', '可演示性分': 'video.demo',
    '新颖性代理分': 'video.novelty', '主题匹配分': 'video.topic',
}


def score_needs_refresh(item: dict, *, now: datetime | None = None) -> bool:
    """只判断缓存是否过时，不在网页渲染时重新评分或替换保存结果。"""
    now = now or datetime.now(timezone.utc)
    rating = item.get('rating')
    if not rating:
        return False
    calculated = parse_time(rating['calculated_at'])
    latest = parse_time(rating['trend'].get('latest_at'))
    return (bool(item.get('stale')) or rating['rule_version'] != rules.RULE_VERSION
            or rating['parameters'] != json.loads(json.dumps(rules.rule_parameters()))
            or calculated is None or (now - calculated).total_seconds() > 3600
            or latest is not None and (now - latest).total_seconds() > rules.STALE_HOURS * 3600
            and rating['trend']['status'] != '趋势数据过期')


def rank_items(items: list[dict], *, query: str = '', source: str = '', category: str = '',
               sort_by: str = 'composite_score') -> list[dict]:
    """缺失分排最后，同分按最近主来源采集时间和热点 ID 稳定排序。"""
    if sort_by not in SORT_OPTIONS.values():
        raise ValueError('不支持的评分排序维度')
    matched = []
    for item in items:
        rating = item.get('rating')
        text = item.get('search_text') or normalize_title(
            f'{item["title"]} {item.get("summary") or ""} {item["url"]}')
        if query.strip() and normalize_title(query) not in text:
            continue
        if source and source != item['source']:
            continue
        if category and (not rating or category not in rating['categories']):
            continue
        matched.append(item)

    def sort_key(item):
        """用评分而不是 Stars/积分混排；旧时间无效时使用稳定 ID。"""
        rating = item.get('rating') or {}
        if '.' in sort_by:
            group, name = sort_by.split('.')
            value = rating.get(group, {}).get('dimensions', {}).get(name, {}).get('score')
        else:
            value = rating.get(sort_by)
        latest = parse_time(rating.get('trend', {}).get('latest_at'))
        return (value is not None, value if value is not None else 0,
                latest.timestamp() if latest else 0, item['id'])

    return sorted(matched, key=sort_key, reverse=True)
