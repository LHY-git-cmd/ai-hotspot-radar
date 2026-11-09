"""报告唯一证据池读取：同连接、当前依据、B阶段公开质量核验，无新证据。"""

from copy import deepcopy
import json

from services.research.evidence_contract import digest
from services.research.quality import CONTRACT_VERSION, POLICY_VERSION
from services.research.report_contract import INPUT_VERSION, HASH_VERSION, TEMPLATES
from services.research.diagnostics import ResearchValidationError


def fail(code, path=()):
    raise ResearchValidationError(code, '研究报告证据、内容或权限校验失败', path)


def read_bundle(con, project_id):
    # 延迟导入避免Store与通用制作守卫的模块循环。
    from services.research.guards import current_basis, confirmed_plan, latest
    from database.research_store import ResearchStore
    basis = current_basis(con, project_id)
    plan, confirmation = confirmed_plan(con, project_id, basis['plan_version_id'])
    run = con.execute('SELECT * FROM research_search_runs WHERE id=? AND project_id=?',
                      (basis['search_run_id'], project_id)).fetchone()
    if run['confirmation_id'] != confirmation['id']:
        fail('report_scope_mismatch')
    operation = con.execute('SELECT * FROM topic_analyses WHERE id=? AND production_project_id=?',
                            (basis['evidence_analysis_id'], project_id)).fetchone()
    if (operation['schema_version'] != CONTRACT_VERSION or operation['purpose'] != 'research_evidence' or
        operation['status'] != 'success'):
        fail('report_legacy_unreviewed')
    if not con.execute("SELECT 1 FROM ai_analysis_runs WHERE id=? AND analysis_id=? AND status='success'",
                       (operation['success_run_id'], operation['id'])).fetchone():
        fail('report_binding_mismatch')
    inputs = json.loads(operation['input_json'])
    document = json.loads(operation['analysis_json'])
    if document.get('policy_version') != POLICY_VERSION:
        fail('report_binding_mismatch')
    ResearchStore.verify_evidence_binding(con, project_id, run['id'], operation['id'], document, status='success')
    # 只需读取方法；不构造会初始化/迁移数据库的Store。
    reader = object.__new__(ResearchStore)
    rows = reader.evidence(project_id, operation['id'], connection=con)
    catalog = []
    for sql, raw in zip(rows, document['items'], strict=True):
        if sql['project_id'] != project_id or sql['run_id'] != run['id'] or sql['analysis_id'] != operation['id']:
            fail('report_scope_mismatch')
        sources = inputs['manifest']['sources']
        citations = []
        for link in raw['links'] + raw['temporal']['context_links']:
            source = sources[str(link['source_id'])]
            citations.append({**deepcopy(link), 'snapshot_hash': source['snapshot_hash'],
                'body_hash': source['body_hash'], 'url': source['url'], 'title': source['title']})
        claim = deepcopy(raw['claim'])
        complete = all(claim[k] != 'unknown' for k in ('entity', 'metric', 'value', 'unit'))
        template = {'opinion': 'attributed_opinion', 'inference': 'limited_inference',
                    'disputed': 'preserve_dispute', 'unverified': 'unresolved_lead'}.get(sql['category'],
                         'evidence_statement' if complete else 'unresolved_lead')
        catalog.append({'evidence_id': sql['id'], 'question_id': sql['question_id'],
            'evidence_position': sql['position'], 'candidate_id': raw['candidate_id'],
            'evidence_item_hash': digest(raw), 'assessment_hash': digest(raw['quality']),
            'quality': deepcopy(raw['quality']), 'temporal': deepcopy(raw['temporal']), 'claim': claim,
            'source_bindings': citations, 'statement_ref': f'e{sql["id"]}-{digest(raw)[:24]}',
            'template_id': template})
    gaps = []
    def gap(qid, code, detail, provenance, **bindings):
        value = {'question_id': qid, 'code': code, 'detail': detail, 'provenance': provenance, **bindings}
        value['gap_id'] = 'g-' + digest(value)
        if value not in gaps: gaps.append(value)
    for n, g in enumerate(document['structured_gaps']):
        gap(g['question_id'], g['code'], g.get('detail', '材料覆盖不足'), f'evidence-gap-{n}',
            original=deepcopy(g))
    for e in catalog:
        eid, qid = e['evidence_id'], e['question_id']
        for code in e['quality']['unmet_conditions']:
            gap(qid, code, '证据质量限制：'+code, 'quality', evidence_id=eid)
        if e['temporal']['temporal_type'] == 'unknown':
            gap(qid, 'period_unknown', '数据时间性质或覆盖期间尚未核实', 'temporal', evidence_id=eid)
        if e['quality']['final_category'] == 'disputed':
            gap(qid, 'source_conflict', '来源存在争议，尚未解决', 'quality', evidence_id=eid)
        if any(e['claim'][k] == 'unknown' for k in ('entity', 'metric', 'value', 'unit')):
            gap(qid, 'claim_incomplete', '原子陈述缺少主体、指标、数值或单位上下文', 'claim', evidence_id=eid)
    for q in plan['content']['questions']:
        if not any(e['question_id'] == q['id'] for e in catalog):
            gap(q['id'], 'no_evidence', '本题没有可用事实证据', 'question')
    pool_hash = digest({'evidence': catalog, 'gaps': gaps})
    expanded = {'project_id': project_id, 'production_project_id': project_id,
        'plan_version_id': plan['id'], 'plan_confirmation_id': confirmation['id'],
        'research_run_id': run['id'], 'evidence_analysis_id': operation['id'],
        'evidence_contract_version': CONTRACT_VERSION, 'evidence_policy_version': POLICY_VERSION,
        'input_manifest_hash': inputs['manifest']['manifest_hash'], 'evidence_set_hash': pool_hash,
        'research_as_of': inputs['research_as_of'],
        'target_window': deepcopy(inputs['manifest']['research_context']['target_window'])}
    questions = [{'id': q['id'], 'question': q['question']} for q in plan['content']['questions']]
    # 不把计划自由文本/证据候选summary当报告事实原子。
    cards = []
    for e in catalog:
        card = {k: deepcopy(e[k]) for k in ('evidence_id', 'question_id', 'claim', 'statement_ref', 'template_id')}
        card['quality'] = {k: deepcopy(e['quality'][k]) for k in
                           ('final_category', 'independence_status', 'unmet_conditions', 'policy_version')}
        card['temporal'] = {k: deepcopy(v) for k, v in e['temporal'].items() if k != 'context_links'}
        cards.append(card)
    model = {'bundle_version': INPUT_VERSION, 'questions': questions,
        'evidence_catalog': cards,
        'mandatory_gaps': [{k: g[k] for k in ('gap_id', 'question_id', 'code')} for g in gaps],
        'templates': list(TEMPLATES)}
    previous = latest(con, project_id, 'report')
    return {'bundle_version': INPUT_VERSION, 'basis': expanded, 'questions': questions,
        'evidence_catalog': catalog, 'mandatory_gaps': gaps, 'model_materials': model,
        'model_materials_hash': digest(model), 'canonical_hash_version': HASH_VERSION,
        'expected_previous_report_version_id': previous['id'] if previous else None}
