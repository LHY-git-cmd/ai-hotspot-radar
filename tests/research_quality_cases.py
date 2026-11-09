"""v3合成数据契约；不导入Store、Streamlit、配置或Provider。"""

from copy import deepcopy
import hashlib

CONTEXT = {'as_of': '2026-11-03', 'target_window': {'start': '2026-01-01', 'end': '2026-11-03'}}
POLICY = {'version': 'quality-v3', 'max_total': 10, 'max_per_question': 2}


def source(sid=1, text='Oracle公布收入增长20%。', *, region='extracted_body',
           domain='example.com', published_at='2024-12-10', status='success', origin=None):
    field = 'snippet' if region == 'search_snippet' else 'text'
    body = text if field == 'text' else ''
    return {'source_id': sid, 'project_id': 1, 'run_id': 3, 'snapshot_hash': f'snapshot-{sid}',
        'body_hash': hashlib.sha256(body.encode()).hexdigest(), 'domain': domain,
        'origin_group_id': origin, 'question_ids': ['Q1'], 'extraction_status': status,
        'published_at': published_at, 'title': '', 'text': body,
        'snippet': text if field == 'snippet' else '',
        'regions': [{'segment_id': f's{sid}', 'region': region, 'storage_field': field,
            'start': 0, 'end': len(text), 'boundary_confidence': 'heuristic'}],
        'visible_windows': [{'window_id': f'w{sid}', 'segment_id': f's{sid}', 'region': region,
            'storage_field': field, 'start': 0, 'end': len(text), 'text': text}]}


def link(s, index=0, **changes):
    w = s['visible_windows'][index]
    return {'source_id': s['source_id'], 'window_id': w['window_id'], 'segment_id': w['segment_id'],
        'region': w['region'], 'storage_field': w['storage_field'],
        'start': w['start'], 'end': w['end'], 'quote': w['text'], 'role': 'claim_support', **changes}


def setup(*ss):
    ss = list(ss) or [source()]
    manifest = {'contract_version': 'research-evidence-v3', 'project_id': 1, 'run_id': 3,
        'research_context': deepcopy(CONTEXT),
        'questions': [{'id': 'Q1', 'question': 'Oracle收入增长？', 'keywords': ['Oracle', '收入', '20%']}],
        'sources': {str(s['source_id']): s for s in ss}, 'coverage_gaps': []}
    item = {'candidate_id': 'Q1-c1', 'kind': 'fact', 'corroboration_requested': True,
        'summary': '来源声称Oracle收入增长20%，期间尚未核实', 'inference': '', 'verification': '候选',
        'claim': {'entity': 'Oracle', 'metric': '收入', 'value': '20', 'unit': '%',
                  'basis': 'unknown', 'speaker': 'unknown'},
        'temporal': {'proposed_type': 'unknown', 'event_kind': 'actual_result',
            'speaker_kind': 'unknown', 'period': {'label_raw': 'unknown', 'calendar_year': None,
                'fiscal_year': None, 'fiscal_quarter': None, 'start': None, 'end': None},
            'context_links': []},
        'links': [link(s) for s in ss]}
    return {'questions': [{'question_id': 'Q1', 'items': [item], 'gaps': []}]}, manifest


def item(c):
    return c['questions'][0]['items'][0]


def assert_rejected(result, *codes):
    assert result['accepted'] is False
    assert result['items'] == [], '硬错误不能返回部分候选'
    assert set(codes) & {e['code'] for e in result['errors']}, result


def assert_grade(result, grade):
    assert result['accepted'] is True, result['errors']
    assert result['items'][0]['quality']['final_category'] == grade
    return result['items'][0]['quality']
