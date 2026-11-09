"""明确的研究确认夹具：通过真实服务流程和 Mock 建立后续制作的前置条件。"""

from unittest.mock import Mock


def approve_research(store, project_id):
    from services.ai.base import ProviderReply, Usage
    from services.ai.config import AISettings
    from tests.research_support import CandidateFixtureProvider as MockProvider
    from services.research.base import SearchReply, SearchResult, ExtractReply, ExtractResult, Quota
    from services.research.service import ResearchService

    search = Mock()
    search.name, search.available = 'mock', True
    search.usage.return_value = Quota(100)
    search.search.return_value = SearchReply([SearchResult('测试资料', 'https://example.com/fixture', '测试摘录')], 1)
    search.extract.return_value = ExtractReply([ExtractResult('https://example.com/fixture', '仅测试夹具正文')], 0)
    provider = MockProvider([])
    svc = ResearchService(store, settings=AISettings(), provider_factory=lambda kind, schema: provider,
                          search_provider=search)
    plan = {'objective': '测试研究前置条件', 'focus': '仅测试', 'start_date': '', 'end_date': '',
        'verify_facts': ['测试证据'], 'questions': [{'id': 'q1', 'question': '测试问题',
            'keywords': ['测试'], 'source_types': ['测试来源'], 'domains': []}]}
    v = svc.save_plan(project_id, plan)
    svc.confirm_plan(project_id, v['id'], f'fixture-plan-{project_id}')
    run = svc.search(project_id, v['id'], f'fixture-search-{project_id}')
    source = svc.store.sources(project_id, run['id'])[0]
    provider.replies.append(ProviderReply({'items': [{'question_id': 'q1', 'category': 'single_source',
        'summary': '测试材料', 'inference': '', 'verification': '只用于测试', 'time_scope': 'unknown', 'data_period': 'unknown',
        'links': [{'source_id': source['id'], 'quote': '夹具正文', 'field': 'text'}]}], 'gaps': ['测试限制']}, Usage(0, 0)))
    result = svc.organize_evidence(project_id, run['id'], f'fixture-evidence-{project_id}')
    assert result['status'] == 'success', result
    evidence = svc.store.evidence(project_id, result['analysis_id'])[0]
    from tests.research_report_cases import saved, confirm
    report = saved(svc, project_id)
    confirm(svc, project_id, report, f'fixture-report-{project_id}')
    return svc


def candidate_from_legacy_fixture(document, payload):
    """仅测试迁移器：把旧Mock样本显式转为新候选，绝不用于生产。

    旧测试仍可在旧样本上构造故障；模型实际返回的是v3，越权等级保留为
    非法字段，不能因测试适配被静默删掉。位置只取模型可见窗口。
    """
    import copy
    from tests.research_quality_cases import setup, item
    template, _ = setup()
    groups = {q['id']: {'question_id': q['id'], 'items': [], 'gaps': []} for q in payload['plan']['questions']}
    for n, old in enumerate(document.get('items', [])):
        if not all(k in old for k in ('question_id', 'category', 'links', 'summary')):
            return document
        qid = old['question_id']
        group = groups.setdefault(qid, {'question_id': qid, 'items': [], 'gaps': []})
        row = copy.deepcopy(item(template))
        row.update(candidate_id=f'{qid}-{n}', summary=old['summary'], inference=old['inference'],
                   verification=old['verification'], kind={'single_source': 'fact'}.get(old['category'], old['category']))
        if old['category'] == 'verified':
            row['kind'] = 'fact'
            row['category'] = 'verified'  # 明确越权必须交由真实Schema拒绝。
        row['claim'] = dict.fromkeys(row['claim'], 'unknown')
        row['temporal'].update(event_kind='unknown', speaker_kind='unknown', proposed_type={
            'current': 'current_actual', 'historical': 'historical_actual', 'forecast': 'company_guidance'}.get(old.get('time_scope'), 'unknown'))
        if old.get('data_period', 'unknown') != 'unknown':
            row['temporal']['period']['label_raw'] = old['data_period']
        row['links'] = []
        for old_link in old['links']:
            source = next((s for s in payload['sources'] if s['source_id'] == old_link['source_id']), None)
            field = old_link['field']
            w = next((w for w in source['visible_windows'] if w['storage_field'] == field and old_link['quote'] in w['text']), None) if source else None
            if not w and source:
                w = next((w for w in source['visible_windows'] if old_link['quote'] in w['text']), None)
            if w:
                start = w['start'] + w['text'].index(old_link['quote'])
                link = {k: w[k] for k in ('window_id', 'segment_id', 'region', 'storage_field')}
            else:
                start = 0
                link = {'window_id': 'not-visible', 'segment_id': 'not-visible',
                        'region': 'search_snippet' if field == 'snippet' else 'extracted_body', 'storage_field': field}
            row['links'].append({**link, 'source_id': old_link['source_id'], 'quote': old_link['quote'],
                                'start': start, 'end': start+len(old_link['quote']), 'role': 'claim_support'})
        for key, value in old.items():
            if key not in ('question_id','category','summary','inference','verification','time_scope','data_period','links'):
                row[key] = value
        group['items'].append(row)
    for gap in document.get('gaps', []):
        qid = gap.split(':', 1)[0] if isinstance(gap, str) else ''
        if qid in groups:
            groups[qid]['gaps'].append({'code': 'fixture_gap', 'detail': gap})
    return {'questions': list(groups.values())}


from services.ai.mock import MockProvider


class CandidateFixtureProvider(MockProvider):
    """仅旧回归测试使用的显式Mock契约适配，不修改通用Mock或生产Provider。"""
    def complete(self, messages):
        import json
        from services.ai.base import ProviderReply
        reply = super().complete(messages)
        payload = json.loads(messages[1]['content'])['untrusted_materials']
        if payload.get('contract_version') == 'research-evidence-v3' and 'questions' not in reply.document:
            return ProviderReply(candidate_from_legacy_fixture(reply.document, payload), reply.usage)
        return reply


def save_report_fixture(svc, project_id, document):
    """旧回归显式提交v3表达树及当前CAS；不接受旧正文或修改生产validator。"""
    draft = svc.reports().draft(project_id)
    return svc.save_report(project_id, document,
                          expected_previous_report_version_id=draft['expected_previous_report_version_id'])


def confirm_report_fixture(svc, project_id, version_id, action_id):
    from tests.research_report_cases import confirm
    report = svc.versions.details(project_id, version_id)
    return confirm(svc, project_id, report, action_id)
