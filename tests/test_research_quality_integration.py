"""真实研究服务与Mock Provider；Schema、选择器、质量判定和Store均为真实实现。"""

from copy import deepcopy
import json

import pytest

from services.ai.base import ProviderReply, Usage
from services.research.quality import CANDIDATE_SCHEMA
from tests.test_research_workflow import research, ready
from tests.research_quality_cases import setup, item
from tests.research_service_cases import CASES, VARIANTS, create_case, seed_history, capture, assert_case


@pytest.mark.parametrize('case_id', CASES+VARIANTS)
def test_case(production_store, monkeypatch, case_id):
    svc,p,run,provider,seen,cfg=create_case(production_store,monkeypatch,case_id)
    legacy=seed_history(svc,p,run)
    before=capture(svc)
    result=svc.organize_evidence(p['id'],run['id'],'I-'+case_id)
    assert_case(svc,p,run,provider,seen,cfg,before,result)
    assert svc.store.evidence(p['id'],legacy)[0]['review_status']=='legacy_unreviewed'


def visible_candidate(payload):
    """模拟模型只用实际收到的窗口，不能从Store读取全文。"""
    candidate, _ = setup()
    groups = []
    for question in payload['plan']['questions']:
        windows = [(s, w) for s in payload['sources'] for w in s['visible_windows']
                   if question['id'] in w['question_ids'] and w['region'] == 'extracted_body']
        group = {'question_id': question['id'], 'items': [], 'gaps': []}
        if windows and question == payload['plan']['questions'][0]:
            s, w = windows[0]
            row = deepcopy(item(candidate))
            row.update(summary='材料声称支持本地运行', kind='unverified')
            row['claim'] = dict.fromkeys(row['claim'], 'unknown')
            row['temporal'].update(event_kind='unknown', speaker_kind='unknown')
            row['links'] = [{k: w[k] for k in ('window_id', 'segment_id', 'region', 'storage_field', 'start', 'end')} |
                            {'source_id': s['source_id'], 'quote': w['text'], 'role': 'claim_support'}]
            group['items'] = [row]
        else:
            group['gaps'] = [{'code': 'no_support', 'detail': '本题缺乏证据'}]
        groups.append(group)
    return {'questions': groups}


@pytest.mark.parametrize('fault', [None, 'final_category', 'body_hash', 'source_id', 'region', 'temporal'])
def test_v3_controls_real_call_chain(research, fault):
    svc, project, _, provider, _ = research
    _, run = ready(research)
    captured = {}
    original_factory = svc.provider_factory

    def factory(kind, schema):
        captured['schema'] = deepcopy(schema)
        return original_factory(kind, schema)

    svc.provider_factory = factory

    def complete(messages):
        provider.calls.append(deepcopy(messages))
        captured['messages'] = messages
        payload = json.loads(messages[1]['content'])['untrusted_materials']
        # 此断言必须在真实服务调用中观察到v3，不允许测试替换validator。
        assert payload['contract_version'] == 'research-evidence-v3'
        captured['payload'] = payload
        doc = visible_candidate(payload)
        row = doc['questions'][0]['items'][0]
        if fault in ('final_category', 'body_hash'):
            row[fault] = 'verified' if fault == 'final_category' else 'forged'
        elif fault == 'source_id':
            row['links'][0]['source_id'] = 999999
        elif fault == 'region':
            row['links'][0]['region'] = 'title'
        elif fault == 'temporal':
            row['temporal']['proposed_type'] = 'current_actual'
        return ProviderReply(doc, Usage(20, 30))

    provider.complete = complete
    result = svc.organize_evidence(project['id'], run['id'], 'v3-'+str(fault))
    assert captured['schema'] == CANDIDATE_SCHEMA
    assert '候选' in captured['messages'][0]['content']
    assert result['status'] == ('failed' if fault else 'success'), result
    rows = svc.store.evidence(project['id'], result['analysis_id'])
    if fault:
        assert rows == []
    else:
        assert rows[0]['category'] == 'unverified'
        assert rows[0]['quality']['final_category'] != 'verified'
        saved = json.loads(svc.store.rows('SELECT input_json FROM topic_analyses WHERE id=?', (result['analysis_id'],))[0]['input_json'])
        assert saved['model_materials'] == captured['payload']
        for source in saved['manifest']['sources'].values():
            received = next(s for s in captured['payload']['sources'] if s['source_id'] == source['source_id'])
            assert source['visible_windows'] == received['visible_windows']
            for w in received['visible_windows']:
                assert source[w['storage_field']][w['start']:w['end']] == w['text']


def test_strict_provider_request_really_uses_candidate_schema(research, monkeypatch):
    """服务到DeepSeek适配器走真实代码，仅HTTP响应为Mock，无网络。"""
    from services.ai.config import AISettings
    from services.ai.schemas import provider_schema
    svc,p,_,_,_=research
    _,run=ready(research)
    svc.settings=AISettings(api_key='only-synthetic-test-key')
    svc.provider_factory=None
    captured={}
    def post(url, **kwargs):
        body=kwargs['json'];captured['body']=deepcopy(body)
        payload=json.loads(body['messages'][1]['content'])['untrusted_materials']
        document=visible_candidate(payload)
        from unittest.mock import Mock
        response=Mock(status_code=200)
        response.json.return_value={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[
            {'function':{'name':'submit_research_evidence','arguments':json.dumps(document)}}]}}],
            'usage':{'prompt_tokens':20,'completion_tokens':30}}
        return response
    monkeypatch.setattr('requests.post',post)
    result=svc.organize_evidence(p['id'],run['id'],'strict-real-adapter')
    assert result['status']=='success',result
    tool=captured['body']['tools'][0]['function']
    assert tool['name']=='submit_research_evidence' and tool['strict'] is True
    assert tool['parameters']==provider_schema(CANDIDATE_SCHEMA)
    assert 'final_category' not in json.dumps(tool['parameters'])
    assert captured['body']['messages'][0]['content'].startswith('你仅整理 research-evidence-v3 候选证据')
    from pathlib import Path
    out=Path(__file__).resolve().parents[1]/'logs/phase4-2-1-4-b-batch2'
    if out.is_dir():
        (out/'strict-request-proof.json').write_text(json.dumps(captured['body'],ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('unknown_usage', [False, True])
def test_invalid_batch_diagnostic_failure_cannot_bypass_or_zero_cost(research, monkeypatch, unknown_usage):
    from database.ai_store import AIStore
    svc,p,_,provider,_=research
    _,run=ready(research)
    def complete(messages):
        payload=json.loads(messages[1]['content'])['untrusted_materials']
        doc=visible_candidate(payload)
        row=doc['questions'][0]['items'][0]
        row['summary']='Bearer synthetic-sensitive-token'
        row['Authorization']='Bearer synthetic-sensitive-token'
        return ProviderReply(doc,Usage() if unknown_usage else Usage(20,30))
    provider.complete=complete
    def fail(*args): raise RuntimeError('diagnostic unavailable')
    monkeypatch.setattr(svc.store,'save_diagnostic',fail)
    result=svc.organize_evidence(p['id'],run['id'],'diag-fail-'+str(unknown_usage))
    assert result['status']=='failed'
    assert svc.store.evidence(p['id'],result['analysis_id'])==[]
    attempt=svc.store.rows('SELECT * FROM ai_analysis_runs WHERE analysis_id=?',(result['analysis_id'],))[0]
    assert attempt['status']=='failed'
    if unknown_usage:
        assert attempt['estimated_cost_units'] is None and attempt['input_tokens'] is None
        assert AIStore(svc.store.path,svc.settings).budget()['held_units']>0
    else:
        assert attempt['estimated_cost_units']>0 and attempt['input_tokens']==20


def test_body_publication_date_cannot_become_data_coverage(production_store, monkeypatch):
    from services.research.base import ExtractReply,ExtractResult
    svc,p,run,provider,seen,cfg=create_case(production_store,monkeypatch,'T06')
    # 重新搜索形成新快照；发布日期即使在正文出现也不是覆盖截至日。
    url=svc.store.sources(p['id'],run['id'])[0]['url']
    svc.search_provider.extract.return_value=ExtractReply([ExtractResult(url,
        '发布日期2026-09-10。Oracle公布FY2027 Q1收入增长20%。')],0)
    run=svc.search(p['id'],run['plan_version_id'],'publication-body-search')
    def complete(messages):
        payload=json.loads(messages[1]['content'])['untrusted_materials']
        doc=response_for(cfg,payload)
        doc['questions'][0]['items'][0]['temporal']['period']['end']='2026-09-10'
        return ProviderReply(doc,Usage(20,30))
    from tests.research_service_cases import response_for
    provider.complete=complete
    before=capture(svc)
    result=svc.organize_evidence(p['id'],run['id'],'publication-as-coverage')
    assert result['status']=='failed'
    assert capture(svc)==before
    assert svc.store.diagnostics(p['id'],result['analysis_id'])[0]['code']=='unsupported_period'


def test_public_policy_and_program_time_classifier_both_control_writes(production_store, monkeypatch):
    import services.research.quality as quality
    svc,p,run,provider,seen,cfg=create_case(production_store,monkeypatch,'T06')
    original_assess=quality.assess_batch
    original_time=quality.classify_temporal
    observed={'assess':0,'time':0}
    def assess(candidate, manifest, policy=None):
        observed['assess']+=1
        assert policy is None
        assert 'trusted_assessments' not in manifest
        return original_assess(candidate,manifest,policy)
    def classify(*args):
        observed['time']+=1
        return original_time(*args)
    monkeypatch.setattr(quality,'assess_batch',assess)
    monkeypatch.setattr(quality,'classify_temporal',classify)
    result=svc.organize_evidence(p['id'],run['id'],'public-policy-path')
    assert result['status']=='success'
    assert observed=={'assess':2,'time':2}
    assert svc.store.evidence(p['id'],result['analysis_id'])[0]['temporal']['event_kind']=='actual_result'


def test_request_too_small_stops_before_attempt_without_expanding_budget(production_store, monkeypatch):
    from dataclasses import replace
    svc,p,run,provider,seen,cfg=create_case(production_store,monkeypatch,'T01')
    svc.settings=replace(svc.settings,max_request_bytes=4096)
    before=svc.store.rows('SELECT * FROM ai_analysis_runs')
    result=svc.organize_evidence(p['id'],run['id'],'too-small-local-stop')
    assert result['status']=='failed' and result['analysis_id'] is None
    assert not provider.calls
    assert svc.store.rows('SELECT * FROM ai_analysis_runs')==before
    assert svc.settings.max_request_bytes==4096
