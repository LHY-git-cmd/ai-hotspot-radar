"""确定性且可解释的双评分纯函数；所有未知维度保留缺失原因。"""

from datetime import datetime, timezone
import math
import re

from services import scoring_rules as rules
from services.normalization import normalize_title
from services.trends import calculate_trend, parse_time, primary_metric


def weighted_score(dimensions: dict, weights: dict) -> dict:
    """仅按可用维度重分配权重；同时保留原覆盖率，不能将缺失赋零。"""
    if (set(dimensions) != set(weights) or not weights
            or any(not math.isfinite(weight) or weight < 0 for weight in weights.values())
            or not math.isclose(sum(weights.values()), 1)):
        raise ValueError('评分权重必须与维度一致、非负且总和为 1')
    coverage = sum(weights[name] for name, value in dimensions.items() if value['score'] is not None)
    for name, value in dimensions.items():
        score = value['score']
        if score is not None and (not math.isfinite(score) or not 0 <= score <= 100):
            raise ValueError('维度分必须在 0 到 100 之间')
        value['weight'] = weights[name]
        value['effective_weight'] = weights[name] / coverage if score is not None and coverage else 0
    total = sum(value['score'] * value['effective_weight']
                for value in dimensions.values() if value['score'] is not None) if coverage else None
    return dict(score=total, dimensions=dimensions, coverage=coverage, provisional=coverage < .999999)


def _dimension(score: float | None, reason: str, evidence: object = None) -> dict:
    """统一展示计算结果、原因和可核查的输入证据。"""
    return dict(score=score, reason=reason, evidence=evidence)


def _log_score(value: float, anchor: float) -> float:
    """在各自来源锚点下归一化；负增长按规则给零，原增量不被修改。"""
    if anchor <= 0:
        raise ValueError('评分锚点必须大于 0')
    return 100 * min(1, math.log1p(max(0, value)) / math.log1p(anchor))


def _age_score(value: object, half_life: float, now: datetime) -> float | None:
    """以真实 API 时间衰减，未来或缺失日期不能自动获得满分。"""
    date = parse_time(value)
    if date is None or date > now:
        return None
    if half_life <= 0:
        raise ValueError('时间半衰期必须大于 0')
    return 100 * 2 ** (-(now - date).total_seconds() / 86400 / half_life)


def _hits(text: str, words: tuple) -> list[str]:
    """ASCII 词使用 ASCII 字母数字边界，兼容“AI工具”，又不误命中 email。"""
    return [word for word in words if re.search(
        rf'(?<![a-z0-9_]){re.escape(word)}(?![a-z0-9_])' if word.isascii() else re.escape(word), text)]


def score_hotspot(item: dict, snapshots: list[dict], *, now: datetime | None = None) -> dict:
    """为单热点输出 A/B 分、综合分、分类及完整证据，不访问网络或数据库。"""
    now = now or datetime.now(timezone.utc)
    source = item['source']
    trend = calculate_trend(snapshots, source, item.get('primary_source_key'), now=now)
    latest = trend['latest']
    current = primary_metric(latest, source) if latest else None
    stale = trend['status'] == '趋势数据过期'
    current_score = _log_score(current, rules.CURRENT_ANCHORS[source]) if current is not None and not stale else None
    growth = trend['daily_growth']
    growth_score = _log_score(growth, rules.GROWTH_ANCHORS[source]) if growth is not None else None
    recency_date = (latest.get('pushed_at') if latest else None) if source == 'GitHub' else (
        latest.get('published_at') if latest else item.get('published_at'))
    recency = _age_score(recency_date, rules.RECENCY_HALF_LIFE_DAYS, now)
    heat = weighted_score({
        'current': _dimension(current_score, '来源对数锚点归一化' if current_score is not None else
                              '当前指标过期' if stale else '缺少带有效采集时间的当前指标',
                              {'value': current, 'anchor': rules.CURRENT_ANCHORS[source],
                               'observed_at': trend['latest_at'], 'source': source}),
        'growth': _dimension(growth_score, '按实际间隔折算日均变化后使用来源锚点' if growth_score is not None
                             else trend['status'], {'daily_growth': growth, 'anchor': rules.GROWTH_ANCHORS[source]}),
        'recency': _dimension(recency, 'GitHub 推送时间 / HN 发布时间的 7 天半衰期'
                              if recency is not None else '缺少有效的来源时效时间', recency_date),
    }, rules.HEAT_WEIGHTS)
    heat['provisional'] = heat['provisional'] or trend['confidence'] == '低'

    text = normalize_title(f'{item.get("title") or ""} {item.get("summary") or ""}')
    practical_hits = [_hits(text, group) for group in rules.PRACTICAL_GROUPS]
    demo_hits = [(points, _hits(text, words)) for points, words in rules.DEMO_GROUPS]
    ai, tools, coding = _hits(text, rules.AI_WORDS), _hits(text, rules.TOOL_WORDS), _hits(text, rules.CODING_WORDS)
    novelty_date = latest.get('published_at') if latest else item.get('published_at')
    novelty = _age_score(novelty_date, rules.NOVELTY_HALF_LIFE_DAYS, now)
    video = weighted_score({
        'practical': _dimension(min(95, 20 + 25 * sum(bool(group) for group in practical_hits)) if text else None,
                                '基础 20；编程、效率、创作/数据场景各加 25；仅为文本线索' if text else
                                '标题与摘要均缺失，无法分析实用场景', practical_hits),
        'demo': _dimension(min(100, 20 + sum(points for points, hits in demo_hits if hits)) if text else None,
                           '基础 20；演示 +35、接口/界面 +25、教程 +20；未亲测产品' if text else
                           '标题与摘要均缺失，无法分析可演示性', demo_hits),
        'novelty': _dimension(novelty, '新发布程度代理：真实创建/发布时间按 30 天半衰期衰减；不代表原创性'
                              if novelty is not None else '缺少有效的创建/发布时间', novelty_date),
        'topic': _dimension((40 * bool(ai) + 30 * bool(tools) + 30 * bool(coding)) if text else None,
                            'AI 词 40、工具词 30、编程词 30；无命中为规则证据不足' if text else
                            '标题与摘要均缺失，无法分析主题',
                            {'ai': ai, 'tools': tools, 'coding': coding}),
    }, rules.VIDEO_WEIGHTS)
    categories = []
    if coding:
        categories.append('AI 编程')
    if ai and tools:
        categories.append('AI 工具')
    if source == 'GitHub':
        categories.append('开源项目')
    if not categories:
        categories.append('AI 讨论/其他')
    if not 0 <= rules.COMPOSITE_HEAT_WEIGHT <= 1:
        raise ValueError('综合评分权重应在 0 到 1 之间')
    composite = (rules.COMPOSITE_HEAT_WEIGHT * heat['score']
                 + (1 - rules.COMPOSITE_HEAT_WEIGHT) * video['score']) if (
                     heat['score'] is not None and video['score'] is not None) else None
    return dict(hotspot_id=item['id'], heat_score=heat['score'], video_score=video['score'],
                composite_score=composite, heat=heat, video=video, trend=trend,
                categories=categories, category_evidence={'ai': ai, 'tools': tools, 'coding': coding,
                                                         'repository_source': source == 'GitHub'},
                calculated_at=now.astimezone(timezone.utc).isoformat(timespec='seconds'),
                rule_version=rules.RULE_VERSION, parameters=rules.rule_parameters())
