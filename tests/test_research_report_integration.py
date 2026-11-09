"""报告真实服务+Mock；禁止替换报告validator/证据读取器。"""

from copy import deepcopy
import json
import pytest

from services.ai.base import ProviderReply, Usage
from tests.research_service_cases import create_case
from tests.research_report_cases import CASES,make_scenario,execute


@pytest.mark.parametrize('case_id',CASES)
def test_case(production_store,monkeypatch,case_id):
    execute(case_id,*make_scenario(production_store,monkeypatch,case_id),monkeypatch)


def prepared(production_store, monkeypatch, evidence_case='T01'):
    svc,p,run,provider,seen,cfg=create_case(production_store,monkeypatch,evidence_case)
    result=svc.organize_evidence(p['id'],run['id'],'report-evidence')
    assert result['status']=='success',result
    return svc,p,run,provider


def proposal(payload):
    sections=[]
    for q in payload['questions']:
        cards=[e for e in payload['evidence_catalog'] if e['question_id']==q['id']]
        gaps=[g for g in payload['mandatory_gaps'] if g['question_id']==q['id']]
        sections.append({'question_id':q['id'],'evidence_order':[c['evidence_id'] for c in cards],
                         'gap_order':[g['gap_id'] for g in gaps],'blocks':[]})
    return {'question_sections':sections,'conclusion_blocks':[]}


def test_new_report_schema_prompt_and_persisted_bundle(production_store,monkeypatch):
    svc,p,run,provider=prepared(production_store,monkeypatch)
    observed={}
    def complete(messages):
        provider.calls.append(deepcopy(messages))
        payload=json.loads(messages[1]['content'])['untrusted_materials']
        observed['payload']=payload
        assert payload['bundle_version']=='research-report-input-v3'
        return ProviderReply(proposal(payload),Usage(20,30))
    provider.complete=complete
    result=svc.generate_report(p['id'],'report-v3-call')
    assert result['status']=='success',result
    report=svc.current_report(p['id'])
    assert report['content']['contract_version']=='research-report-v3'
    assert report['content']['document']['categories']['verified']==[]
    operation=svc.store.rows('SELECT * FROM topic_analyses WHERE id=?',(result['analysis_id'],))[0]
    assert operation['schema_version']=='research-report-v3'
    assert operation['prompt_version']=='research-report-prompt-v3'
    assert json.loads(operation['input_json'])['model_materials']==observed['payload']
    assert svc.store.rows('SELECT * FROM research_report_confirmations')==[]


def test_old_free_text_is_not_a_new_report_write_contract(production_store,monkeypatch):
    svc,p,_,_=prepared(production_store,monkeypatch)
    from tests.test_research_workflow import report_document
    evidence=svc.store.evidence(p['id'],svc.basis(p['id'])['evidence_analysis_id'])[0]
    before=svc.store.rows('SELECT * FROM production_versions')
    with pytest.raises(ValueError):
        svc.save_report(p['id'],report_document(evidence['id']))
    assert svc.store.rows('SELECT * FROM production_versions')==before


@pytest.mark.parametrize('evidence_case,expected',[
    ('T28','current_actual'),('T07','historical_actual'),('T08','company_guidance'),
    ('T09','analyst_forecast'),('T29','market_expectation'),('T06','unknown')])
def test_all_six_time_classes_inherit_from_saved_v3_evidence(production_store,monkeypatch,evidence_case,expected):
    from tests.research_report_cases import saved
    svc,p,_,_=prepared(production_store,monkeypatch,evidence_case)
    report=saved(svc,p['id'])
    rows=[r for k,v in report['content']['document']['categories'].items() if k!='gaps' for r in v]
    assert rows[0]['temporal']['temporal_type']==expected
    if evidence_case=='T06':
        t=rows[0]['temporal']
        assert t['fiscal_year']==2027 and t['fiscal_quarter']==1 and t['calendar_publication_year']==2026
        assert t['coverage_start'] is None and t['coverage_end'] is None


@pytest.mark.parametrize('evidence_case',['T05','T11','T12','T26','T37'])
def test_zero_evidence_snippets_and_unknown_independence_do_not_gain_trust(production_store,monkeypatch,evidence_case):
    from tests.research_report_cases import saved
    svc,p,_,_=prepared(production_store,monkeypatch,evidence_case)
    report=saved(svc,p['id'])
    categories=report['content']['document']['categories']
    assert categories['verified']==[] and categories['gaps']
    if evidence_case=='T05':
        assert all(categories[k]==[] for k in categories if k!='gaps')
    else:
        assert categories['unverified'] and all(e['category']=='unverified' for e in categories['unverified'])


@pytest.mark.parametrize('unknown_usage',[False,True])
def test_validation_or_diagnostic_internal_failure_keeps_usage(production_store,monkeypatch,unknown_usage):
    from database.ai_store import AIStore
    svc,p,_,provider=prepared(production_store,monkeypatch)
    candidate=svc.reports().draft(p['id'])['candidate_document']
    provider.complete=lambda messages:ProviderReply(candidate,Usage() if unknown_usage else Usage(20,30))
    from services.research.report_service import validate_candidate as original
    def unavailable(*args,**kwargs):raise RuntimeError('synthetic internal sensitive error')
    def broken_validator(*args,**kwargs):
        if kwargs.get('checked_at')=='preflight':return original(*args,**kwargs)
        return unavailable()
    monkeypatch.setattr('services.research.report_service.validate_candidate',broken_validator)
    monkeypatch.setattr(svc.store,'save_diagnostic',unavailable)
    before=svc.store.rows('SELECT * FROM production_versions')
    result=svc.generate_report(p['id'],'internal-failure-'+str(unknown_usage))
    assert result['status']=='failed'
    assert svc.store.rows('SELECT * FROM production_versions')==before
    attempt=svc.store.rows('SELECT * FROM ai_analysis_runs WHERE analysis_id=?',(result['analysis_id'],))[0]
    if unknown_usage:
        assert attempt['estimated_cost_units'] is None and attempt['input_tokens'] is None
        assert AIStore(svc.store.path,svc.settings).budget()['held_units']>0
    else:assert attempt['estimated_cost_units']==280 and attempt['input_tokens']==20


def test_request_too_small_does_not_send_or_reserve(production_store,monkeypatch):
    from dataclasses import replace
    svc,p,_,provider=prepared(production_store,monkeypatch)
    svc.settings=replace(svc.settings,max_request_bytes=4096)
    before=svc.store.rows('SELECT * FROM ai_analysis_runs')
    provider.calls=[]
    result=svc.generate_report(p['id'],'small-request')
    # 若最小合法池可容纳，此测试应显式扩展输入，而不能假设固定提示词体积。
    assert result['status']=='failed' and result['analysis_id'] is None
    assert provider.calls==[]
    assert svc.store.rows('SELECT * FROM ai_analysis_runs')==before


def test_strict_report_schema_enters_real_provider_adapter(production_store,monkeypatch):
    from unittest.mock import Mock
    from services.ai.config import AISettings
    from services.ai.schemas import provider_schema
    from services.research.report_contract import candidate_schema
    svc,p,_,_=prepared(production_store,monkeypatch)
    svc.provider_factory=None;svc.settings=AISettings(api_key='synthetic-only-key')
    captured={}
    def post(url,**kwargs):
        captured['body']=kwargs['json']
        doc=proposal(json.loads(kwargs['json']['messages'][1]['content'])['untrusted_materials'])
        response=Mock(status_code=200)
        response.json.return_value={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[
            {'function':{'name':'submit_research_report','arguments':json.dumps(doc)}}]}}],
            'usage':{'prompt_tokens':20,'completion_tokens':30}}
        return response
    monkeypatch.setattr('requests.post',post)
    bundle=svc.reports().bundle(p['id'])
    result=svc.generate_report(p['id'],'strict-adapter-report')
    assert result['status']=='success'
    tool=captured['body']['tools'][0]['function']
    assert tool['strict'] is True and tool['name']=='submit_research_report'
    assert tool['parameters']==provider_schema(candidate_schema(bundle))
    assert '研究证据' in captured['body']['messages'][0]['content']
    assert 'source_id' not in json.dumps(bundle['model_materials'])
    assert 'quote' not in json.dumps(bundle['model_materials'])
    assert 'url' not in json.dumps(bundle['model_materials'])


def test_runtime_validation_stage_is_distinct_from_published_report(production_store,monkeypatch):
    svc,p,_,provider=prepared(production_store,monkeypatch)
    from services.research.report_service import validate_candidate as original
    candidate=svc.reports().draft(p['id'])['candidate_document']
    provider.complete=lambda messages:ProviderReply(candidate,Usage(20,30))
    observed=[]
    def validator(*args,**kwargs):
        if kwargs.get('checked_at')!='preflight':
            state=svc.reports().state(p['id'])
            observed.append(state)
            assert svc.current_report(p['id']) is None
        return original(*args,**kwargs)
    monkeypatch.setattr('services.research.report_service.validate_candidate',validator)
    assert svc.generate_report(p['id'],'stage-observation')['status']=='success'
    assert observed[0]['current_report_state']=='not_generated'
    assert observed[0]['latest_attempt_state']=='generated_pending_validation'
    assert svc.reports().state(p['id'])['current_report_state']=='validated_pending_confirmation'
