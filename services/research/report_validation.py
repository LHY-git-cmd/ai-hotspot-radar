"""报告纯校验/渲染：不接触IO、密钥、身份、模型或数据库。"""

from copy import deepcopy
import json
from jsonschema import Draft202012Validator

from services.research.evidence_contract import digest
from services.research.report_contract import (VERSION, POLICY, RENDERER, HASH_VERSION,
    REPORT_CANDIDATE_SCHEMA, CATEGORIES)
from services.research.diagnostics import ResearchValidationError


def reject(code, path=()):
    raise ResearchValidationError(code, '报告内容、引用或授权绑定无效', path)


def attempt_state(operation, diagnostic_stage=None, validation_started=False):
    if operation is None:
        return 'not_generated'
    state = operation['status']
    if state == 'failed' and diagnostic_stage is not None:
        return {'provider': 'provider_failed', 'validation': 'validation_failed',
                'persistence': 'persistence_failed'}[diagnostic_stage]
    if state == 'running' and validation_started:
        return 'generated_pending_validation'
    return state


def check_previous(actual, expected):
    if actual != expected or type(actual) is not type(expected):
        reject('report_version_conflict')


def default_candidate(bundle):
    """人工编辑的最小合法草稿；只排列已保存证据与缺口，不创造事实。"""
    return {'question_sections': [{'question_id': q['id'],
        'evidence_order': [e['evidence_id'] for e in bundle['evidence_catalog'] if e['question_id'] == q['id']],
        'gap_order': [g['gap_id'] for g in bundle['mandatory_gaps'] if g['question_id'] == q['id']],
        'blocks': []} for q in bundle['questions']], 'conclusion_blocks': []}


def atom(e):
    """不渲染模型summary；每个显示数值/期间来自本证据的程序核验字段。"""
    c, t, q = e['claim'], e['temporal'], e['quality']
    labels = {'verified': '已验证事实', 'single_source': '单一来源事实', 'opinion': '来源观点',
              'inference': 'AI推断', 'disputed': '存在争议', 'unverified': '待验证信息'}
    grade = q['final_category']
    if e['template_id'] == 'unresolved_lead':
        text = '该来源的陈述含义仍待核实，不能视为确定事实。'
    elif grade == 'inference':
        text = '该证据包含AI推断；现有材料尚不能证明因果或未来结果。'
    else:
        parts = [f'{k}={c[k]}' for k in ('entity', 'metric', 'value', 'unit', 'basis', 'speaker') if c[k] != 'unknown']
        text = '来源陈述：' + '；'.join(parts) + '。'
    return {'text': labels[grade]+'：'+text, 'evidence_ids': [e['evidence_id']],
        'statement_refs': [e['statement_ref']], 'category': grade,
        'temporal': deepcopy(t), 'claim': deepcopy(c), 'citations': deepcopy(e['source_bindings']),
        'quality': deepcopy(q)}


def validate_candidate(candidate, bundle, *, checked_at):
    try:
        size = len(json.dumps(candidate, ensure_ascii=False, allow_nan=False).encode())
    except (TypeError, ValueError, RecursionError):
        reject('report_schema')
    error = next(Draft202012Validator(REPORT_CANDIDATE_SCHEMA).iter_errors(candidate), None)
    if error is not None or size > 262144:
        reject('report_schema', error.absolute_path if error is not None else ())
    sections = candidate['question_sections']
    expected_questions = [q['id'] for q in bundle['questions']]
    if sorted(s['question_id'] for s in sections) != sorted(expected_questions):
        reject('report_scope_mismatch', ['question_sections'])
    evidence = {e['evidence_id']: e for e in bundle['evidence_catalog']}
    gaps = {g['gap_id']: g for g in bundle['mandatory_gaps']}
    ids = set()
    blocks = sum(len(s['blocks']) for s in sections) + len(candidate['conclusion_blocks'])
    if blocks > 40:
        reject('report_schema')

    def render_block(block, qid, path):
        if block['block_id'] in ids:
            reject('report_schema', path+['block_id'])
        ids.add(block['block_id'])
        selected, selected_gaps, slots = [], [], []
        for n, binding in enumerate(block['bindings']):
            eid, ref, gid, slot = (binding[k] for k in ('evidence_id', 'statement_ref', 'gap_id', 'slot'))
            slots.append(slot)
            if type(eid) is int and ref is not None and gid is None:
                if eid not in evidence:
                    reject('report_evidence_not_allowed', path+['bindings', n])
                e = evidence[eid]
                if qid is not None and e['question_id'] != qid:
                    reject('report_scope_mismatch', path+['bindings', n])
                if ref != e['statement_ref']:
                    reject('report_statement_ref_mismatch', path+['bindings', n])
                selected.append(e)
            elif eid is None and ref is None and gid in gaps:
                g = gaps[gid]
                if qid is not None and g['question_id'] != qid:
                    reject('report_scope_mismatch', path+['bindings', n])
                selected_gaps.append(g)
            else:
                reject('report_evidence_not_allowed', path+['bindings', n])
        if len({e['evidence_id'] for e in selected}) != len(selected) or len({g['gap_id'] for g in selected_gaps}) != len(selected_gaps):
            reject('report_schema', path+['bindings'])
        template = block['template_id']
        if template == 'gap_reference':
            if selected or len(selected_gaps) != 1 or slots != ['gap']:
                reject('report_unsupported_conclusion', path)
            return {'text': '研究缺口：'+selected_gaps[0]['detail'], 'evidence_ids': [],
                    'gap_ids': [selected_gaps[0]['gap_id']], 'category': 'gaps'}
        if selected_gaps or not selected:
            reject('report_unsupported_conclusion', path)
        if template == 'compare_like_for_like':
            if len(selected) != 2 or slots != ['left', 'right']:
                reject('report_unsupported_conclusion', path)
            a, b = selected
            if (a['quality']['final_category'] not in ('verified', 'single_source') or
                b['quality']['final_category'] != a['quality']['final_category'] or
                any(a['claim'][k] == 'unknown' or a['claim'][k] != b['claim'][k]
                    for k in ('entity', 'metric', 'unit', 'basis')) or
                any(a['temporal'].get(k) != b['temporal'].get(k) for k in
                    ('temporal_type', 'event_kind', 'speaker_kind', 'fiscal_year', 'fiscal_quarter',
                     'coverage_start', 'coverage_end', 'research_as_of')) or
                a['temporal']['temporal_type'] not in ('current_actual', 'historical_actual')):
                reject('report_period_mismatch', path)
            return {'text': '同口径陈列（不作独立性或因果推断）：'+atom(a)['text']+atom(b)['text'],
                    'evidence_ids': [a['evidence_id'], b['evidence_id']], 'category': a['quality']['final_category'],
                    'items': [atom(a), atom(b)]}
        if template == 'limited_inference':
            if slots != ['premise']*len(selected):
                reject('report_unsupported_conclusion', path)
            return {'text': 'AI推断：这些材料仅支持提出研究问题，尚不能确认因果或未来结果。',
                'category': 'inference', 'evidence_ids': [e['evidence_id'] for e in selected],
                'premises': [atom(e) for e in selected],
                'disputed': any(e['quality']['final_category'] == 'disputed' for e in selected)}
        if len(selected) != 1 or slots != ['evidence']:
            reject('report_unsupported_conclusion', path)
        e = selected[0]
        if template != e['template_id']:
            code = 'report_dispute_omitted' if e['quality']['final_category'] == 'disputed' else 'report_grade_escalation'
            reject(code, path)
        return atom(e)

    rendered_sections, categories = [], {k: [] for k in CATEGORIES}
    for n, section in enumerate(sections):
        qid, path = section['question_id'], ['question_sections', n]
        expected_eids = [e['evidence_id'] for e in evidence.values() if e['question_id'] == qid]
        if sorted(section['evidence_order']) != sorted(expected_eids):
            reject('report_evidence_not_allowed', path+['evidence_order'])
        expected_gids = [g['gap_id'] for g in gaps.values() if g['question_id'] == qid]
        if sorted(section['gap_order']) != sorted(expected_gids):
            reject('report_gap_omitted', path+['gap_order'])
        statements = [atom(evidence[eid]) for eid in section['evidence_order']]
        for statement in statements:
            categories[statement['category']].append(statement)
        missing = [deepcopy(gaps[gid]) for gid in section['gap_order']]
        categories['gaps'].extend(missing)
        question = next(q for q in bundle['questions'] if q['id'] == qid)
        rendered_sections.append({'question_id': qid, 'research_question': question.get('question', qid),
            'statements': statements, 'gaps': missing,
            'blocks': [render_block(b, qid, path+['blocks', i]) for i, b in enumerate(section['blocks'])]})
    conclusions = [render_block(b, None, ['conclusion_blocks', i]) for i, b in enumerate(candidate['conclusion_blocks'])]
    document = {'overview': '基于已保存研究证据的资料整理；证据不足和争议见各问题。',
        'objective': '呈现可追溯证据及研究缺口，不补充未经核实事实。',
        'question_sections': rendered_sections, 'conclusions': conclusions, 'categories': categories}
    envelope = {'contract_version': VERSION, 'basis': deepcopy(bundle['basis']),
        'evidence_snapshot': {'evidence': deepcopy(bundle['evidence_catalog']), 'gaps': deepcopy(bundle['mandatory_gaps'])},
        'candidate_document': deepcopy(candidate), 'document': document}
    policies = {'policy_version': POLICY, 'renderer_version': RENDERER, 'canonical_hash_version': HASH_VERSION,
        'evidence_set_hash': bundle['basis']['evidence_set_hash'], 'model_materials_hash': bundle['model_materials_hash']}
    envelope['validation'] = {**policies, 'report_core_hash': digest({**envelope, 'policies': policies}),
                              'checked_at': checked_at, 'warnings': []}
    return envelope


def verify_envelope(envelope, bundle):
    if not isinstance(envelope, dict) or envelope.get('contract_version') != VERSION:
        reject('report_legacy_unreviewed')
    try:
        expected = validate_candidate(envelope['candidate_document'], bundle,
                                      checked_at=envelope['validation']['checked_at'])
    except (KeyError, TypeError):
        reject('report_schema')
    if expected != envelope:
        # 无论调用方声称passed/confirmed与否，都以独立重建的规范结果核对。
        if expected['document'] != envelope.get('document'):
            reject('report_value_mismatch', ['document'])
        reject('report_binding_mismatch')
    return envelope
