"""同来源、同对象的观察区间增长计算；不以缺失值或失败补造趋势。"""

from datetime import datetime, timezone

from models import as_score, as_utc_iso
from services import scoring_rules as rules


def parse_time(value: object) -> datetime | None:
    """只接受有效带时区时间，并转换为 UTC。"""
    iso = as_utc_iso(value)
    return datetime.fromisoformat(iso) if iso else None


def primary_metric(snapshot: dict, source: str) -> int | None:
    """使用来源专属主指标，绝不把 HN 积分当 Stars。"""
    return as_score(snapshot.get('stars' if source == 'GitHub' else 'hn_score'))


def calculate_trend(snapshots: list[dict], source: str, source_key: str | None,
                    *, now: datetime | None = None) -> dict:
    """选择最接近 24 小时间隔的有效基线，输出实际增量及折算日均变化。"""
    now = now or datetime.now(timezone.utc)
    result = dict(status='趋势数据不足', confidence='低', delta=None, daily_growth=None,
                  percent_growth=None, interval_hours=None, baseline_at=None,
                  latest_at=None, latest=None, valid_points=0)
    if not source_key or source not in rules.CURRENT_ANCHORS:
        return result
    series = []
    for row in snapshots:
        date = parse_time(row.get('collected_at'))
        if (row.get('source') == source and row.get('source_key') == source_key
                and date is not None and date <= now):
            series.append((date, row))
    series.sort(key=lambda pair: pair[0])
    if not series:
        return result
    latest_date, latest = series[-1]
    result.update(latest=latest, latest_at=latest_date.isoformat())
    if (now - latest_date).total_seconds() > rules.STALE_HOURS * 3600:
        return result | {'status': '趋势数据过期'}
    current = primary_metric(latest, source)
    if current is None:
        return result | {'status': '指标缺失'}
    valid = [(date, row) for date, row in series
             if (latest_date - date).total_seconds() <= rules.WINDOW_DAYS * 86400
             and primary_metric(row, source) is not None]
    candidates = [(date, row) for date, row in valid
                  if (latest_date - date).total_seconds() >= rules.MIN_INTERVAL_HOURS * 3600]
    result['valid_points'] = len({date for date, _ in valid})
    if not candidates:
        return result
    baseline_date, baseline = min(candidates, key=lambda pair: (
        abs((latest_date - pair[0]).total_seconds() - rules.TARGET_INTERVAL_HOURS * 3600), pair[0]))
    previous = primary_metric(baseline, source)
    interval = (latest_date - baseline_date).total_seconds() / 3600
    delta = current - previous
    span = (latest_date - valid[0][0]).total_seconds() / 3600
    return result | {
        'status': '趋势可计算',
        'confidence': '中等' if result['valid_points'] >= 3 and span >= 24 else '低',
        'delta': delta, 'daily_growth': delta * 24 / interval,
        'percent_growth': delta / previous * 100 if previous > 0 else None,
        'interval_hours': interval, 'baseline_at': baseline_date.isoformat(),
    }
