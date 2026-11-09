"""v3服务装配契约：来源绑定、可见材料投影及程序审定结果，不提供授信入口。"""

from copy import deepcopy
import hashlib
import json
import re

from services.research import materials, quality
from services.research.diagnostics import ResearchValidationError


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def source_record(source, project_id, run_id, question_ids):
    """坐标始终基于保存的原字段；独占首部标题/导航按位置隔离，不清洗正文。"""
    row = {key: source[key] for key in ('title', 'url', 'domain', 'published_at', 'searched_at',
                                      'text', 'snippet', 'extraction_status')}
    row.update(source_id=source['id'], project_id=project_id, run_id=run_id,
               snapshot_hash=source['content_hash'], body_hash=hashlib.sha256(row['text'].encode()).hexdigest(),
               question_ids=sorted(question_ids), regions=[], visible_windows=[])
    title = ' '.join(row['title'].casefold().split())
    # 页面标题可位于站点名/导航之后；仅登记首次匹配的独占标题行，
    # 不将后续正文中的同句全局当成标题。
    title_seen = False
    for n, match in enumerate(re.finditer(r'[^\n]+', row['text'])):
        raw = match.group()
        normalized = ' '.join(raw.casefold().strip('# ').split())
        is_title = not title_seen and title and (normalized == title or title.endswith(' - '+normalized))
        navigation = bool(re.match(r'^(skip to|image source:|by\s+|home\s*$)', raw, re.I))
        if is_title:
            title_seen = True
        region = 'title' if is_title else 'metadata' if navigation else 'extracted_body'
        row['regions'].append({'segment_id': f's{source["id"]}-text-{n}', 'region': region,
            'storage_field': 'text', 'start': match.start(), 'end': match.end(),
            'boundary_confidence': 'heuristic'})
    # 连续正文行保持一个区域，便于完整表格及前后上下文选窗。
    regions = []
    for r in row['regions']:
        if regions and r['region'] == regions[-1]['region'] == 'extracted_body':
            regions[-1]['end'] = r['end']
        else:
            regions.append(r)
    row['regions'] = regions
    if row['snippet']:
        row['regions'].append({'segment_id': f's{source["id"]}-snippet', 'region': 'search_snippet',
            'storage_field': 'snippet', 'start': 0, 'end': len(row['snippet']), 'boundary_confidence': 'provider'})
    return row


def build_manifest(sources, associations, project_id, run_id, plan, as_of, window_budget):
    by_source = {}
    for association in associations:
        if association['project_id'] != project_id or association['run_id'] != run_id:
            raise ResearchValidationError('source_association', '来源关联不属于当前研究')
        by_source.setdefault(association['source_id'], []).append(association['question_id'])
    rows = [source_record(s, project_id, run_id, by_source.get(s['id'], [])) for s in sources]
    selected = materials.select_windows(rows, plan['questions'], max_utf8_bytes=window_budget)
    for row in rows:
        row['visible_windows'] = [w for w in selected['windows'] if w['source_id'] == row['source_id']]
        if row['extraction_status'] != 'success':
            selected['coverage_gaps'].extend({'question_id': qid, 'source_id': row['source_id'],
                'code': 'body_unavailable', 'detail': '本快照正文提取失败，仅可保留明确标注的搜索摘录线索'}
                for qid in row['question_ids'])
    manifest = {'contract_version': quality.CONTRACT_VERSION, 'project_id': project_id, 'run_id': run_id,
        'research_context': {'as_of': as_of, 'target_window': {
            'start': plan['start_date'] or None, 'end': plan['end_date'] or None, 'basis': 'confirmed_plan'}},
        'questions': deepcopy(plan['questions']), 'sources': {str(r['source_id']): r for r in rows},
        **{key: deepcopy(selected[key]) for key in ('coverage_gaps', 'coverage', 'selector_version', 'offset_unit')},
        'window_budget': window_budget, 'selected_utf8_bytes': selected['selected_utf8_bytes']}
    manifest['manifest_hash'] = digest(manifest)
    return manifest


def model_materials(manifest, plan, plan_version_id):
    """完整原字段仅用于服务器切片核验，不进入模型消息。"""
    return {'contract_version': quality.CONTRACT_VERSION, 'project_id': manifest['project_id'],
        'run_id': manifest['run_id'], 'plan_version_id': plan_version_id,
        'research_as_of': manifest['research_context']['as_of'], 'research_context': manifest['research_context'],
        'plan': deepcopy(plan), 'manifest_hash': manifest['manifest_hash'],
        'coverage_gaps': deepcopy(manifest['coverage_gaps']), 'selector_version': manifest['selector_version'],
        'sources': [{key: deepcopy(source[key]) for key in ('source_id', 'project_id', 'run_id', 'snapshot_hash',
            'body_hash', 'question_ids', 'title', 'url', 'domain', 'published_at', 'searched_at',
            'extraction_status', 'regions', 'visible_windows')} for source in manifest['sources'].values()]}


def assess_document(candidate, manifest):
    """生产只调用公开接口；policy固定，无审核记录或回调参数。"""
    result = quality.assess_batch(candidate, manifest)
    if not result['accepted']:
        first = result['errors'][0]
        error = ResearchValidationError(first['code'], '候选证据未通过v3质量校验', first['path'], rule=first.get('rule'))
        error.batch_errors = result['errors']
        error.diagnostics_truncated = result['diagnostics_truncated']
        raise error
    structured_gaps = result['gaps'] + deepcopy(manifest['coverage_gaps'])
    document = {'contract_version': quality.CONTRACT_VERSION, 'policy_version': quality.POLICY_VERSION,
        'input_manifest_hash': manifest['manifest_hash'], 'candidate_document': deepcopy(candidate),
        'items': result['items'], 'structured_gaps': structured_gaps,
        # 旧页面直接读取此列表；无损结构另存，不修改页面或回写旧JSON。
        'gaps': [f"{g['question_id']}: {g['code']} — {g.get('detail', g.get('reason', '材料覆盖不足'))}"
                 for g in structured_gaps],
        'decision_log': result['decisions']}
    for row in document['items']:
        row['category'] = row['quality']['final_category']
        contexts = row['temporal']['context_links']
        row['temporal'] = deepcopy(row['quality']['temporal'])
        row['temporal']['context_links'] = contexts
        row['source_dates'] = deepcopy(row['quality']['source_dates'])
        # 旧SQL/报告消费者的只读投影；模型无权提供这些字段。
        row['time_scope'] = {'historical_actual': 'historical', 'current_actual': 'current',
            'company_guidance': 'forecast', 'analyst_forecast': 'forecast', 'market_expectation': 'forecast'}.get(
                row['temporal']['temporal_type'], 'unknown')
        row['data_period'] = row['temporal'].get('label_raw') or 'unknown'
        for link in row['links']:
            link['field'] = link['storage_field']
    return document
