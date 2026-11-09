"""T01–T40中的质量/数据契约层；无服务、API或数据库持久化。"""

from copy import deepcopy
import pytest
from services.research.quality import assess_batch
from tests.research_quality_cases import source, setup, item, link, POLICY, assert_grade, assert_rejected


def test_t01_single_official():
    c, m = setup(source(domain='investor.oracle.com'))
    q = assert_grade(assess_batch(c, m), 'single_source')
    assert 'single_origin' in q['unmet_conditions']


def test_t02_shared_release():
    a = source(1, origin='oracle-release')
    b = source(2, text='另一站转载：Oracle公布收入增长20%。', domain='example.org', origin='oracle-release')
    q = assert_grade(assess_batch(*setup(a, b)), 'single_source')
    assert q['independence_status'] == 'dependent'


def test_t03_trusted_fixture_only():
    # 生产可调用的纯函数对任意JSON“可信审核”均不授予verified。
    a, b = source(), source(2, text='独立措辞：Oracle收入增长20%。', domain='example.org')
    c, m = setup(a, b)
    assert_grade(assess_batch(c, m), 'unverified')
    injected = dict(POLICY, trusted_assessments=[{'result': 'confirmed_independent', 'reviewer_id': 'fixture'}])
    assert_rejected(assess_batch(c, m, injected), 'untrusted_review_input')
    item(c)['trusted_assessments'] = injected['trusted_assessments']
    assert_rejected(assess_batch(c, m), 'schema')


def test_t04_three_per_question():
    c, m = setup()
    first = item(c)
    c['questions'][0]['items'] = [dict(deepcopy(first), candidate_id=f'c{i}') for i in range(3)]
    assert_rejected(assess_batch(c, m), 'question_limit')


def test_t05_zero_with_gap():
    c, m = setup()
    c['questions'][0].update(items=[], gaps=[{'code': 'no_support', 'detail': '无证据'}])
    r = assess_batch(c, m)
    assert r['accepted'] and not r['items']
    assert r['gaps'][0]['question_id'] == 'Q1'


def test_t11_snippet_unverified():
    assert_grade(assess_batch(*setup(source(region='search_snippet'))), 'unverified')


def test_t12_extraction_failed():
    c, m = setup(source(status='failed', region='search_snippet'))
    c['questions'][0]['gaps'] = [{'code': 'body_unavailable', 'detail': '正文不可读'}]
    assert_grade(assess_batch(c, m), 'unverified')
    c, m = setup(source(status='failed'))
    assert_rejected(assess_batch(c, m), 'extraction_unavailable')


def test_t19_region_conflict():
    s = source(text='Oracle收入增长28%。')
    snippet = 'Oracle同一期间收入增长30%。'
    s['snippet'] = snippet
    region = {'segment_id': 'sn', 'region': 'search_snippet', 'storage_field': 'snippet',
              'start': 0, 'end': len(snippet), 'boundary_confidence': 'provider'}
    s['regions'].append(region)
    s['visible_windows'].append({**region, 'window_id': 'snw', 'text': snippet})
    c, m = setup(s)
    item(c)['claim']['value'] = '28'
    assert_rejected(assess_batch(c, m), 'source_region_conflict')
    item(c).update(kind='disputed', summary='来源正文和搜索摘录的值冲突')
    item(c)['links'].append(link(s, 1))
    assert_grade(assess_batch(c, m), 'disputed')


def test_t20_same_body_new_snapshot():
    a, b = source(1), source(2)
    b['snapshot_hash'] = 'new-metadata'
    q = assert_grade(assess_batch(*setup(a, b)), 'single_source')
    assert len(q['origin_group_ids']) == 1


def test_t21_missing_question_gap():
    c, m = setup()
    c['questions'][0]['items'] = []
    assert_rejected(assess_batch(c, m), 'missing_question_gap')


def multi_question_batch(n, total):
    c, m = setup()
    base = deepcopy(item(c))
    m['sources']['1']['question_ids'] = [f'Q{i}' for i in range(n)]
    m['questions'] = [{'id': f'Q{i}', 'question': '收入', 'keywords': []} for i in range(n)]
    c['questions'] = []
    remaining = total
    for i in range(n):
        count = min(2, remaining)
        items = []
        for j in range(count):
            v = deepcopy(base)
            v.update(candidate_id=f'{i}-{j}', kind='opinion' if j else 'fact')
            items.append(v)
        c['questions'].append({'question_id': f'Q{i}', 'items': items,
            'gaps': [] if count else [{'code': 'no_support', 'detail': '无证据'}]})
        remaining -= count
    return c, m


def test_t22_ten_valid_items():
    r = assess_batch(*multi_question_batch(5, 10))
    assert r['accepted'], r['errors']
    assert len(r['items']) == 10


def test_t23_total_eleven():
    assert_rejected(assess_batch(*multi_question_batch(6, 11)), 'total_limit')


@pytest.mark.parametrize('fault', ['duplicate', 'missing', 'unknown'])
def test_t24_question_set(fault):
    c, m = setup()
    if fault == 'duplicate':
        c['questions'].append(deepcopy(c['questions'][0]))
    elif fault == 'missing':
        c['questions'] = []
    else:
        c['questions'][0]['question_id'] = 'Q9'
    assert_rejected(assess_batch(c, m), 'question_set_mismatch')


@pytest.mark.parametrize('field', ['category', 'final_category', 'independence_status', 'trusted_assessments'])
def test_t25_forbidden_grade_field(field):
    c, m = setup()
    item(c)[field] = 'verified'
    assert_rejected(assess_batch(c, m), 'schema')


def test_t26_independence_unknown():
    a, b = source(), source(2, text='另一报道：Oracle收入增长20%。', domain='example.org')
    q = assert_grade(assess_batch(*setup(a, b)), 'unverified')
    assert q['independence_status'] == 'unknown'


def test_t30_corrected_duplicate():
    c, m = setup()
    duplicate = dict(item(c)['links'][0], storage_field='snippet')
    item(c)['links'].append(duplicate)
    original = deepcopy(c)
    assert_rejected(assess_batch(c, m), 'duplicate_link')
    assert c == original


def test_t34_speaker_role_mismatch():
    c, m = setup(source(text='Oracle CEO Safra Catz said revenue grew 20%.'))
    item(c)['claim'].update(metric='revenue', speaker='CFO Safra Catz')
    assert_rejected(assess_batch(c, m), 'claim_support_mismatch')


def test_t37_domain_suffix_unknown():
    a, b = source(domain='a.co.uk'), source(2, text='Oracle收入增长20%，另一表述。', domain='b.co.uk')
    q = assert_grade(assess_batch(*setup(a, b)), 'unverified')
    assert 'registrable_domain_unknown' in q['unmet_conditions']


def test_t40_contract_version():
    c, m = setup()
    m['contract_version'] = 'research-evidence-v2'
    assert_rejected(assess_batch(c, m), 'contract_version_mismatch')


def test_inputs_are_not_mutated_and_repeatable():
    c, m = setup()
    before = deepcopy((c, m))
    r = assess_batch(c, m)
    assert r == assess_batch(c, m)
    assert (c, m) == before


def test_expected_value_cannot_be_claimed_as_actual():
    c, m = setup(source(text='Oracle公布实际收入增长18%，低于市场预期20%。'))
    assert_rejected(assess_batch(c, m), 'claim_support_mismatch')


def test_period_context_cannot_contradict_main_quote():
    c, m = setup(source(text='Oracle公布FY2025 Q1收入增长20%。FY2025 Q2的资料待核实。'))
    item(c)['temporal']['period']['label_raw'] = 'FY2025 Q2'
    assert_rejected(assess_batch(c, m), 'unsupported_period', 'temporal_contradiction')


@pytest.mark.parametrize('fault', ['question_type', 'window_range', 'regions_type', 'source_project',
                                  'body_hash', 'window_text', 'source_run'])
def test_malformed_or_forged_manifest_rejects_without_exception(fault):
    c, m = setup()
    s = m['sources']['1']
    if fault == 'question_type':
        m['questions'][0]['id'] = []
    elif fault == 'window_range':
        s['visible_windows'][0]['start'] = 'zero'
    elif fault == 'regions_type':
        s['regions'] = 'not-regions'
    elif fault == 'source_project':
        s['project_id'] = 9
    elif fault == 'source_run':
        s['run_id'] = 9
    elif fault == 'body_hash':
        s['body_hash'] = 'forged-hash'
    else:
        s['visible_windows'][0]['text'] = 'forged-text'
    r = assess_batch(c, m)
    assert r['accepted'] is False and r['items'] == []


@pytest.mark.parametrize('place', ['manifest', 'source'])
def test_ordinary_business_data_cannot_enable_verified(place):
    c, m = setup(source(), source(2, text='独立表述Oracle收入增长20%。', domain='example.org'))
    target = m if place == 'manifest' else m['sources']['1']
    target['trusted_assessments'] = [{'result': 'confirmed_independent', 'reviewer_id': 'pretend'}]
    target['independence_status'] = 'confirmed_independent'
    r = assess_batch(c, m)
    assert r['accepted']
    assert all(v['quality']['final_category'] != 'verified' for v in r['items'])


def test_test_only_review_gate_is_not_public_json_authority():
    # 只有测试直接调用内部策略接缝；不增加公开认证/数据导入入口。
    from services.research.quality import _assess_batch, claim_signature
    a = source(1, text='Oracle公布截至2024-11-30的收入同比增长20%。')
    b = source(2, text='独立调查证实Oracle截至2024-11-30收入同比增长20%。', domain='example.org')
    for s in (a, b):
        s['regions'][0]['boundary_confidence'] = 'reviewed'
    c, m = setup(a, b)
    candidate = item(c)
    candidate['claim'].update(basis='year_over_year', speaker='unknown')
    candidate['temporal']['period'].update(label_raw='2024-11-30', end='2024-11-30')
    signature = claim_signature(candidate)
    bindings = {s['source_id']: (s['snapshot_hash'], s['body_hash']) for s in (a, b)}

    def isolated_review_fixture(v, sources):
        return (claim_signature(v) == signature and len(sources) == 2 and
                all(bindings.get(s['source_id']) == (s['snapshot_hash'], s['body_hash']) for s in sources))

    assert_grade(_assess_batch(c, m, _review_gate=isolated_review_fixture), 'verified')
    assert_grade(assess_batch(c, m), 'unverified')
    changed = deepcopy(m)
    changed['sources']['2']['snapshot_hash'] = 'new-snapshot-same-body'
    assert_grade(_assess_batch(c, changed, _review_gate=isolated_review_fixture), 'unverified')
    changed = deepcopy(c)
    item(changed)['claim']['value'] = '99'
    assert_rejected(_assess_batch(changed, m, _review_gate=isolated_review_fixture), 'unsupported_value')


@pytest.mark.parametrize('field', ['entity', 'metric', 'unit'])
def test_missing_essential_numeric_context_cannot_be_an_ordinary_fact(field):
    c, m = setup()
    item(c)['claim'][field] = 'unknown'
    q = assert_grade(assess_batch(c, m), 'unverified')
    assert 'context_incomplete' in q['unmet_conditions']


def test_test_review_cannot_waive_unknown_period():
    from services.research.quality import _assess_batch
    c, m = setup(source(), source(2, text='Oracle收入增长20%，另一来源。', domain='example.org'))
    r = _assess_batch(c, m, _review_gate=lambda item, sources: True)
    assert r['accepted'] and r['items'][0]['quality']['final_category'] != 'verified'


def test_source_question_ids_are_not_a_substring_membership_check():
    c, m = setup()
    m['sources']['1']['question_ids'] = 'Q1Q9'
    assert_rejected(assess_batch(c, m), 'manifest_invalid')


def test_windows_selected_for_another_question_cannot_be_borrowed():
    c, m = setup()
    m['sources']['1']['visible_windows'][0]['question_ids'] = ['Q9']
    assert_rejected(assess_batch(c, m), 'source_association')
