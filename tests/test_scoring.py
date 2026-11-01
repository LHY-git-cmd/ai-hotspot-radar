"""纯函数评分测试：时间可控，模拟指标不进入真实数据或网页。"""

from datetime import datetime, timezone
import math

import pytest

NOW = datetime(2026, 1, 3, tzinfo=timezone.utc)


def snapshot(time='2026-01-03T00:00:00+00:00', value=200, **changes):
    """生成明确来源的测试快照。"""
    return dict(collected_at=time, source='GitHub', source_key='101', stars=value,
                hn_score=None, published_at='2026-01-01T00:00:00+00:00',
                pushed_at='2026-01-03T00:00:00+00:00') | changes


def hotspot(**changes):
    """生成与快照配对的主来源信息。"""
    return dict(id=1, title='AI coding tool demo CLI tutorial', summary='automation video data',
                source='GitHub', primary_source_key='101',
                published_at='2026-01-01T00:00:00+00:00') | changes


def test_growth_uses_actual_interval_and_isolates_source_and_object():
    """忽略其他来源及对象；两天增加 100，应为日均 50。"""
    from services.trends import calculate_trend
    result = calculate_trend([
        snapshot('2026-01-01T00:00:00+00:00', 100), snapshot(),
        snapshot(value=9999, source_key='different'),
        snapshot(value=None, source='Hacker News', hn_score=9999),
    ], 'GitHub', '101', now=NOW)
    assert result['delta'] == 100
    assert result['daily_growth'] == 50
    assert result['percent_growth'] == 100
    assert result['confidence'] == '低'


@pytest.mark.parametrize('rows', [[], [snapshot()],
    [snapshot('2026-01-02T23:30:00+00:00', 100), snapshot()],
    [snapshot('2025-12-01T00:00:00+00:00', 100), snapshot()]])
def test_insufficient_history_never_invents_growth(rows):
    """零点、一点、间隔太短或窗口外都不能算趋势。"""
    from services.trends import calculate_trend
    result = calculate_trend(rows, 'GitHub', '101', now=NOW)
    assert result['status'] == '趋势数据不足'
    assert result['daily_growth'] is None


def test_missing_latest_metric_is_not_replaced_with_old_value():
    """最新指标缺失不能用旧指标冒充最新值。"""
    from services.trends import calculate_trend
    result = calculate_trend([snapshot('2026-01-01T00:00:00+00:00', 100),
                              snapshot(value=None)], 'GitHub', '101', now=NOW)
    assert result['status'] == '指标缺失'
    assert result['daily_growth'] is None


def test_zero_baseline_negative_growth_and_medium_confidence():
    """零基线不除零；下降是真实零增长分；三点覆盖一天为中等证据。"""
    from services.trends import calculate_trend
    result = calculate_trend([snapshot('2026-01-02T00:00:00+00:00', 0),
                              snapshot('2026-01-02T12:00:00+00:00', 10), snapshot(value=5)],
                             'GitHub', '101', now=NOW)
    assert result['delta'] == 5 and result['percent_growth'] is None
    assert result['confidence'] == '中等'
    negative = calculate_trend([snapshot('2026-01-02T00:00:00+00:00', 300), snapshot()],
                               'GitHub', '101', now=NOW)
    assert negative['daily_growth'] == -100


def test_stale_and_future_observations_cannot_be_current():
    """过期与未来观测不产生当前增长评分。"""
    from services.trends import calculate_trend
    old = [snapshot('2025-12-30T00:00:00+00:00', 100)]
    assert calculate_trend(old, 'GitHub', '101', now=NOW)['status'] == '趋势数据过期'
    future = [snapshot('2026-01-04T00:00:00+00:00')]
    assert calculate_trend(future, 'GitHub', '101', now=NOW)['daily_growth'] is None


def test_exact_weights_normalization_video_evidence_and_composite():
    """公式按计划精确计算，视频命中规则应有逐维证据。"""
    from services.scoring import score_hotspot
    rows = [snapshot('2026-01-02T00:00:00+00:00', 100), snapshot()]
    result = score_hotspot(hotspot(), rows, now=NOW)
    current = 100 * math.log1p(200) / math.log1p(100000)
    growth = 100 * math.log1p(100) / math.log1p(1000)
    assert result['heat_score'] == pytest.approx(.35 * current + .4 * growth + .25 * 100)
    novelty = 100 * 2 ** (-2 / 30)
    assert result['video_score'] == pytest.approx(.3 * 95 + .25 * 100 + .2 * novelty + .25 * 100)
    assert result['composite_score'] == pytest.approx((result['heat_score'] + result['video_score']) / 2)
    assert result['video']['dimensions']['practical']['evidence']
    assert set(result['categories']) == {'AI 编程', 'AI 工具', '开源项目'}


def test_source_specific_anchors_and_filter_independent_scores():
    """同样原始数值按来源各自锚点归一化，不依赖其他热点或页面筛选。"""
    from services.scoring import score_hotspot
    gh = score_hotspot(hotspot(), [snapshot(value=1000)], now=NOW)
    hn = score_hotspot(hotspot(source='Hacker News'), [snapshot(
        value=None, source='Hacker News', hn_score=1000)], now=NOW)
    assert gh['heat']['dimensions']['current']['score'] < 100
    assert hn['heat']['dimensions']['current']['score'] == 100
    assert gh['heat']['coverage'] == pytest.approx(.6)
    assert gh['heat']['provisional'] is True


def test_missing_all_inputs_null_not_zero_and_legacy_metrics_not_current():
    """旧库 score 没有可信观测时间，不能作为当前热度；空文本也不当成零。"""
    from services.scoring import score_hotspot
    result = score_hotspot(hotspot(title='', summary=None, published_at=None, score=1000), [], now=NOW)
    assert result['heat_score'] is None
    assert result['video_score'] is None
    assert result['composite_score'] is None


def test_missing_growth_renormalizes_weights_and_stale_heat_is_excluded():
    """缺失趋势不被赋零；过期当前值不参与热度计算。"""
    from services.scoring import score_hotspot
    result = score_hotspot(hotspot(), [snapshot(value=0)], now=NOW)
    assert result['heat_score'] == pytest.approx(25 / .6)
    assert result['heat']['dimensions']['current']['score'] == 0
    assert result['heat']['dimensions']['growth']['score'] is None
    stale = score_hotspot(hotspot(), [snapshot('2025-12-30T00:00:00+00:00', 100)], now=NOW)
    assert stale['heat']['dimensions']['current']['score'] is None


def test_word_boundaries_and_missing_publication_date():
    """普通词中的 ai/cli 等子串不能命中；新颖性不使用推送时间补齐。"""
    from services.scoring import score_hotspot
    result = score_hotspot(hotspot(title='Email railway client', summary=None, published_at=None),
                           [snapshot(published_at=None)], now=NOW)
    assert result['video']['dimensions']['topic']['score'] == 0
    assert result['video']['dimensions']['demo']['score'] == 20
    assert result['video']['dimensions']['novelty']['score'] is None


def test_invalid_weights_fail_explicitly():
    """可调权重出错时不能静默产生错误评分。"""
    from services.scoring import weighted_score
    with pytest.raises(ValueError):
        weighted_score({'a': {'score': 10}}, {'a': -1})


def test_ascii_ai_words_can_border_chinese_text_without_matching_email():
    """中文常见的 AI工具/AI编程不依赖空格，同时保持英文词的误匹配防护。"""
    from services.scoring import score_hotspot
    result = score_hotspot(hotspot(title='AI工具：自动化编程演示', summary=None), [snapshot()], now=NOW)
    assert result['video']['dimensions']['topic']['score'] == 100
    assert set(result['categories']) == {'AI 编程', 'AI 工具', '开源项目'}
