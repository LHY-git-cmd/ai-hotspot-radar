"""材料窗口、区域与精确引用数据契约（不接服务/数据库）。"""

from pathlib import Path
from copy import deepcopy
import hashlib
import json
from services.research.materials import select_windows
from services.research.quality import assess_batch
from tests.research_quality_cases import source, setup, item, link, assert_grade, assert_rejected

FIXTURES = Path(__file__).parent / 'fixtures/research_quality'


def select(text, keywords, budget=4096):
    s = source(text=text)
    return select_windows([s], [{'id': 'Q1', 'keywords': keywords}], max_utf8_bytes=budget)


def check_windows(text, result):
    windows = result['windows']
    assert windows == sorted(windows, key=lambda w: (w['source_id'], w['storage_field'], w['start']))
    for w in windows:
        assert type(w['start']) is int and 0 <= w['start'] < w['end'] <= len(text)
        assert text[w['start']:w['end']] == w['text']
    assert result['offset_unit'] == 'unicode_codepoint'


def test_t10_title_as_body():
    c, m = setup(source(region='title'))
    item(c)['links'][0]['region'] = 'extracted_body'
    assert_rejected(assess_batch(c, m), 'region_mismatch')


def test_t13_front_context_bundle():
    text = 'Oracle公布FY2025 Q2业绩：OCI收入同比增长52%。\n\n' + '背景。' * 300
    r = select(text, ['Oracle', 'OCI', '52%', 'FY2025 Q2'])
    visible = '\n'.join(w['text'] for w in r['windows'])
    assert all(t in visible for t in ('Oracle', 'OCI', '52%', 'FY2025 Q2', '同比'))
    check_windows(text, r)


def test_t14_s26_fixed_body():
    text = (FIXTURES / 's26.txt').read_text(encoding='utf-8')
    metadata = json.loads((FIXTURES / 's26.json').read_text(encoding='utf-8'))
    assert len(text) == 4549 and hashlib.sha256(text.encode()).hexdigest() == metadata['body_sha256']
    assert text[910:913] == '52%' and text[1105:1109] == '336%'
    r = select(text, ['Oracle', '52%', '336%', 'GPU', 'cloud', 'fiscal 2025'], budget=3500)
    visible = '\n'.join(w['text'] for w in r['windows'])
    assert all(t in visible for t in ('52%', '336%', 'Cloud Infrastructure', 'GPU consumption',
                                     'second quarter fiscal 2025', 'Oracle', 'Management’s commentary'))
    assert any(w['start'] <= 910 and 913 <= w['end'] for w in r['windows'])
    assert any(w['start'] <= 1105 and 1109 <= w['end'] for w in r['windows'])
    assert sum(w['end']-w['start'] for w in r['windows']) < 2300
    assert any(w['start'] > 0 for w in r['windows']), '不能扩大开头窗口或把全文直接发送'
    assert r['selected_utf8_bytes'] <= 3500
    check_windows(text, r)


def test_t15_period_context_link():
    text = 'Oracle公布FY2025 Q2业绩。\n\n' + '无关背景。' * 180 + '\n\n该季度Oracle GPU消费增长336%。'
    r = select(text, ['Oracle', 'FY2025 Q2', 'GPU', '336%'], budget=2500)
    visible = '\n'.join(w['text'] for w in r['windows'])
    assert 'FY2025 Q2' in visible and 'GPU消费增长336%' in visible
    assert len(r['windows']) >= 2
    check_windows(text, r)


def test_t16_absent_number():
    r = select('Oracle没有提供GPU消费数据。', ['Oracle', 'GPU', '336%'])
    assert all('336%' not in w['text'] for w in r['windows'])
    assert any(g['code'] == 'term_not_found' and g['term'] == '336%' for g in r['coverage_gaps'])
    c, m = setup()
    item(c)['links'][0]['quote'] = 'GPU增长336%'
    assert_rejected(assess_batch(c, m), 'quote_not_visible')


def test_t31_ambiguous_occurrence():
    text = 'Oracle公布收入增长20%。\n\nOracle公布收入增长20%。'
    c, m = setup(source(text=text))
    q = 'Oracle公布收入增长20%。'
    item(c)['links'][0].update(start=1, end=1+len(q), quote=q)
    assert_rejected(assess_batch(c, m), 'ambiguous_quote')
    start = text.rindex(q)
    item(c)['links'][0].update(start=start, end=start+len(q))
    r = assess_batch(c, m)
    assert_grade(r, 'single_source')
    assert r['items'][0]['links'][0]['start'] == start


def test_t32_window_boundary():
    text = '开头。\n\nOracle收入增长20%。'
    s = source(text=text)
    s['visible_windows'][0].update(end=3, text=text[:3])
    c, m = setup(s)
    quote = 'Oracle收入增长20%。'
    start = text.index(quote)
    item(c)['links'][0].update(start=start, end=start+len(quote), quote=quote)
    assert_rejected(assess_batch(c, m), 'quote_not_visible')


def test_t35_table_context():
    text = 'Oracle收入数据\n\n| 28,499 | 55,663 |\n| 8,502 | 12,033 |'
    r = select(text, ['Oracle', '28,499'])
    assert any(g['code'] == 'table_context_missing' for g in r['coverage_gaps'])
    c, m = setup(source(text=text))
    m['coverage_gaps'] = r['coverage_gaps']
    item(c)['claim'].update(value='28,499', unit='million USD')
    assert_rejected(assess_batch(c, m), 'table_context_missing')


def test_t36_context_budget():
    text = 'Oracle公布FY2025 Q2业绩。\n\n' + '上下文' * 400 + 'Oracle GPU消费增长336%。'
    r = select(text, ['Oracle', 'GPU', '336%', 'FY2025 Q2'], budget=100)
    assert r['selected_utf8_bytes'] <= 100
    assert any(g['code'] in ('omitted_budget', 'context_incomplete') for g in r['coverage_gaps'])
    assert all(w['text'] == text[w['start']:w['end']] for w in r['windows'])
    s = source(text=text)
    c, m = setup(s)
    s['visible_windows'] = r['windows']
    m['coverage_gaps'] = r['coverage_gaps']
    assert_rejected(assess_batch(c, m), 'quote_not_visible')


def test_t39_title_text_reoccurs():
    q = 'Oracle收入增长20%。'
    text = q + '\n\n正文描述：' + q
    s = source(text=text)
    start = text.rindex(q)
    s['regions'] = [
        {'segment_id': 'title', 'region': 'title', 'storage_field': 'text', 'start': 0,
         'end': len(q), 'boundary_confidence': 'explicit'},
        {'segment_id': 'body', 'region': 'extracted_body', 'storage_field': 'text', 'start': start,
         'end': len(text), 'boundary_confidence': 'explicit'}]
    s['visible_windows'] = [{**v, 'window_id': v['segment_id'], 'text': text[v['start']:v['end']]}
                            for v in s['regions']]
    c, m = setup(s)
    item(c)['links'] = [link(s, 1)]
    r = assess_batch(c, m)
    assert_grade(r, 'single_source')
    assert r['items'][0]['links'][0]['start'] == start
    item(c)['links'] = [link(s, 0, region='extracted_body')]
    assert_rejected(assess_batch(c, m), 'region_mismatch')


def test_unicode_offsets_and_determinism():
    text = '🧪 Oracle报告收入增长52%。\n\n其他文字。'
    a = select(text, ['Oracle', '52%'])
    assert a == select(text, ['Oracle', '52%'])
    check_windows(text, a)


def test_required_context_has_individual_roles_and_gaps():
    r = select('336%', ['336%'])
    assert any(g['code'] == 'context_incomplete' and 'metric' in g['missing_context']
               and 'entity' in g['missing_context'] for g in r['coverage_gaps'])
    roles = r['coverage'][0]['context_roles']
    assert roles['unit']['sent'] is True
    assert roles['metric']['sent'] is False
    assert roles['basis']['relation'] == 'unknown'


def test_table_headers_units_and_period_stay_with_numeric_row():
    text = ('Oracle披露财报。\n\n| 指标 | FY2025 Q2（百万美元） |\n'
            '| Revenue | 28499 |\n| Capex | 55663 |\n\n无关文字。')
    r = select(text, ['Oracle', '28499'])
    table = next(w['text'] for w in r['windows'] if '28499' in w['text'])
    assert '百万美元' in table and 'FY2025 Q2' in table and 'Revenue' in table
    check_windows(text, r)


def test_adjacent_windows_merge_only_by_real_original_coordinates():
    text = 'Oracle公布FY2025 Q2收入增长52%。\nOracle公布GPU消费增长336%。'
    r = select(text, ['Oracle', '52%', '336%', 'FY2025 Q2'])
    assert len(r['windows']) == 1
    assert r['windows'][0]['text'] == text
    check_windows(text, r)
