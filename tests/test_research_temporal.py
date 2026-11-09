"""v3时间纯函数回归；原v2服务校验不是本批替换对象。"""

import pytest
from services.research.temporal import classify_temporal
from services.research.quality import assess_batch
from tests.research_quality_cases import CONTEXT, source, setup, item, assert_grade, assert_rejected


def test_t06_fy2027_label_only():
    r = classify_temporal('Oracle announced FY2027 Q1 results.', {
        'published_at': '2026-09-10', 'period_label': 'FY2027 Q1'}, CONTEXT)
    assert r['event_kind'] == 'actual_result'
    assert r['fiscal_year'] == 2027 and r['fiscal_quarter'] == 1
    assert r['calendar_publication_year'] == 2026
    assert r['temporal_type'] == 'unknown' and r['current_relation'] == 'label_only'
    assert r['coverage_start'] is None and r['coverage_end'] is None
    assert not r['errors']


def test_t07_actual_below_expectation():
    r = classify_temporal('Oracle reported revenue of 18%, lower than expected 20% in the quarter ended 2024-11-30.',
                          {}, CONTEXT)
    assert r['event_kind'] == 'actual_result' and r['temporal_type'] == 'historical_actual'
    assert not r['errors']


def test_t08_company_guidance():
    r = classify_temporal('公司预计下一季度收入增长20%。', {}, CONTEXT)
    assert (r['event_kind'], r['speaker_kind'], r['temporal_type']) == ('guidance', 'company', 'company_guidance')
    c, m = setup(source(text='公司预计下一季度收入增长20%。'))
    item(c)['claim']['entity'] = '公司'
    item(c)['temporal'].update(proposed_type='current_actual', event_kind='actual_result')
    assert_rejected(assess_batch(c, m), 'temporal_mismatch')


def test_t09_analyst_forecast():
    r = classify_temporal('分析师预测明年收入增长20%。', {}, CONTEXT)
    assert (r['event_kind'], r['speaker_kind'], r['temporal_type']) == ('forecast', 'analyst', 'analyst_forecast')
    assert r['coverage_start'] is None and r['coverage_end'] is None


def test_t17_publication_unknown():
    r = classify_temporal('公司已公布FY2025 Q2收入增长20%。', {'published_at': None}, CONTEXT)
    assert r['published_at_raw'] is None and r['published_at_normalized'] == 'unknown'
    assert r['fiscal_year'] == 2025 and r['fiscal_quarter'] == 2
    c, m = setup(source(published_at=None))
    q = assert_grade(assess_batch(c, m), 'single_source')
    assert q['source_dates']['1']['normalized'] == 'unknown'


def test_t18_period_unknown():
    r = classify_temporal('公司已公布收入增长20%。', {'published_at': '2024-12-10'}, CONTEXT)
    assert r['event_kind'] == 'actual_result' and r['temporal_type'] == 'unknown'
    assert r['coverage_start'] is None and r['coverage_end'] is None


def test_t27_mixed_event_roles():
    c, m = setup(source(text='Oracle公布实际收入增长18%，市场预期20%；公司预计下季收入增长22%。'))
    item(c)['claim']['value'] = '20'
    item(c)['temporal']['proposed_type'] = 'current_actual'
    assert_rejected(assess_batch(c, m), 'mixed_temporal_claim', 'claim_support_mismatch')


def test_t28_published_actual():
    r = classify_temporal('公司已公布上一季度收入增长20%，截至2026-09-30。', {}, CONTEXT)
    assert r['event_kind'] == 'actual_result' and r['temporal_type'] == 'current_actual'
    assert r['coverage_end'] == '2026-09-30' and r['coverage_start'] is None
    r = classify_temporal('公司已公布上一季度收入增长20%。', {}, CONTEXT)
    assert r['temporal_type'] == 'unknown' and r['coverage_end'] is None


def test_t29_market_expectation():
    r = classify_temporal('市场预期收入增长20%，尚无实际结果。', {}, CONTEXT)
    assert (r['event_kind'], r['speaker_kind'], r['temporal_type']) == ('expectation', 'market', 'market_expectation')


def test_t33_invented_dates():
    c, m = setup(source(text='Oracle已公布FY2027 Q1收入增长20%。'))
    item(c)['temporal']['period'].update(label_raw='FY2027 Q1', fiscal_year=2027, fiscal_quarter=1,
                                        start='2026-06-01', end='2026-08-31')
    assert_rejected(assess_batch(c, m), 'unsupported_period')


def test_t38_metadata_not_period():
    c, m = setup()
    s = m['sources']['1']
    date = '2024-12-10'
    s['snippet'] = date
    region = {'segment_id': 'meta', 'region': 'metadata', 'storage_field': 'snippet',
              'start': 0, 'end': len(date), 'boundary_confidence': 'provider'}
    s['regions'].append(region)
    s['visible_windows'].append({**region, 'window_id': 'mw', 'text': date})
    item(c)['temporal']['period'].update(label_raw=date, end=date)
    item(c)['temporal']['context_links'] = [{'source_id': 1, 'window_id': 'mw', 'segment_id': 'meta',
        'region': 'metadata', 'storage_field': 'snippet', 'start': 0, 'end': len(date),
        'quote': date, 'role': 'period_context'}]
    assert_rejected(assess_batch(c, m), 'unsupported_period')


@pytest.mark.parametrize('text', ['expected growth 20%', 'forecast', '预期20%', '公司说增长20%', 'media expected 20%'])
def test_single_keyword_or_unattributed_statement_is_unknown(text):
    r = classify_temporal(text, {}, CONTEXT)
    assert r['event_kind'] == r['temporal_type'] == 'unknown'


@pytest.mark.parametrize('text,expected', [
    ('管理层指引下季度收入增长20%。', 'company_guidance'),
    ('Analysts expect revenue to grow 20% next year.', 'analyst_forecast'),
    ('The company expects revenue to grow 20% next quarter.', 'company_guidance'),
    ('Market consensus expects growth of 20% next year.', 'market_expectation'),
])
def test_attributed_future_statements(text, expected):
    assert classify_temporal(text, {}, CONTEXT)['temporal_type'] == expected


def test_explicit_time_contradictions_fail():
    r = classify_temporal('公司已公布收入增长20%，截至2027-09-30。', {}, CONTEXT)
    assert any(e['code'] == 'temporal_contradiction' for e in r['errors'])
    r = classify_temporal('公司已公布收入增长20%，期间2026-10-01至2026-01-01。', {}, CONTEXT)
    assert any(e['code'] == 'temporal_contradiction' for e in r['errors'])


def test_reporting_a_future_estimate_does_not_make_it_actual():
    r = classify_temporal('The company reported expected revenue growth of 20% next quarter.', {}, CONTEXT)
    assert r['event_kind'] != 'actual_result' and r['temporal_type'] == 'unknown'
