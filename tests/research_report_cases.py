"""报告22场景固定预期；I/P使用真实服务及临时SQLite，只有Provider为Mock。"""

from copy import deepcopy
import json
from unittest.mock import Mock

from services.ai.base import ProviderReply, Usage, AIError
from services.research.report_validation import default_candidate
from services.research.report_confirmation import LocalReportReviewSession
from services.production.project_service import ProjectService
from services.production.version_service import VersionService
from tests.research_service_cases import create_case

CASES = [f'R{i:02}' for i in range(1,23)]
ERRORS = {'R02':'report_evidence_not_allowed','R03':'report_evidence_not_allowed',
    'R04':'report_evidence_not_allowed','R05':'report_evidence_not_allowed','R06':'report_schema',
    'R07':'report_schema','R08':'report_schema','R09':'report_schema','R10':'report_schema',
    'R11':'report_evidence_not_allowed','R12':'report_gap_omitted','R13':'report_unsupported_conclusion',
    'R15':'report_schema','R19':'report_schema'}


def block(card, template=None, *, slot='evidence'):
    return {'block_id':'b1','template_id':template or card['template_id'], 'bindings':[
        {'slot':slot,'evidence_id':card['evidence_id'],'statement_ref':card['statement_ref'],'gap_id':None}]}


def mutate(candidate, model, case, foreign_id=999999):
    doc=deepcopy(candidate)
    section=doc['question_sections'][0]
    if case in ('R02','R03','R04','R05'):
        section['evidence_order'][0]=foreign_id
    elif case in ('R06','R07','R08','R09','R10','R19'):
        key={'R06':'value','R07':'period','R08':'verified','R09':'temporal_type','R10':'event_kind','R19':'confirmed'}[case]
        doc[key]='forged'
    elif case=='R11':section['evidence_order']=[]
    elif case=='R12':section['gap_order']=[]
    elif case=='R13':
        section['blocks']=[{'block_id':'unsupported','template_id':'limited_inference','bindings':[
            {'slot':'gap','evidence_id':None,'statement_ref':None,'gap_id':model['mandatory_gaps'][0]['gap_id']}]}]
    elif case=='R15':doc['Authorization']='Bearer synthetic-sensitive-report-token'
    return doc


def history(store,pid):
    """明确临时库历史报告；不使用生产报告新增入口冒充旧版本。"""
    with store.transaction() as con:
        oid=store.ensure_object(con,pid,'research','report','2026-01-01')
        return store.insert_version(con,pid,oid,json.dumps({'basis':{},'document':{'legacy':'old'}}),
                                    'manual','legacy','2026-01-01')


def snapshot(store):
    tables=('research_evidence','research_evidence_sources','research_sources','production_versions',
            'research_report_confirmations','ai_budget_settings')
    return {t:store.rows('SELECT * FROM '+t+' ORDER BY rowid') for t in tables}


def saved(svc,pid,change=None):
    draft=svc.reports().draft(pid)
    if change:change(draft['candidate_document'])
    return svc.save_report(pid,draft['candidate_document'],
                          expected_previous_report_version_id=draft['expected_previous_report_version_id'])


def confirm(svc,pid,report,action='confirm-fixture'):
    intent=LocalReportReviewSession().reviewed(pid,report,checked=True)
    svc.confirm_report(pid,report['id'],action,intent=intent)
    return intent


def make_scenario(production_store,monkeypatch,case):
    evidence_case={'R07':'T06','R09':'T07','R10':'T08','R11':'T19-disputed'}.get(case,'T01')
    svc,p,run,provider,_,_=create_case(production_store,monkeypatch,evidence_case)
    result=svc.organize_evidence(p['id'],run['id'],'evidence-first')
    assert result['status']=='success',result
    history(svc.store,p['id'])
    foreign_id=999999
    if case=='R03':
        # 通过真实研究服务为另一个制作项目生成证据。
        from services.research.service import ResearchService
        other=ProjectService(svc.store).create(2,'foreign report fixture')
        other_svc=ResearchService(svc.store,settings=svc.settings,provider_factory=svc.provider_factory,search_provider=svc.search_provider)
        plan=svc.current_plan(p['id'])['content']
        v=other_svc.save_plan(other['id'],plan);other_svc.confirm_plan(other['id'],v['id'],'foreign-plan')
        other_run=other_svc.search(other['id'],v['id'],'foreign-search')
        r=other_svc.organize_evidence(other['id'],other_run['id'],'foreign-evidence')
        assert r['status']=='success'
        foreign_id=other_svc.store.evidence(other['id'],r['analysis_id'])[0]['id']
    if case=='R04':
        foreign_id=svc.store.evidence(p['id'],result['analysis_id'])[0]['id']
        run=svc.search(p['id'],run['plan_version_id'],'new-run')
        r=svc.organize_evidence(p['id'],run['id'],'new-evidence')
        assert r['status']=='success'
    bundle=svc.reports().bundle(p['id']);candidate=default_candidate(bundle)
    observed={}
    def complete(messages):
        provider.calls.append(deepcopy(messages))
        model=json.loads(messages[1]['content'])['untrusted_materials'];observed['model']=model
        if case=='R14':raise AIError('timeout','synthetic',usage=Usage(20,30))
        doc=mutate(candidate,model,case,foreign_id)
        observed['candidate']=doc
        return ProviderReply(doc,Usage(20,30))
    provider.calls=[];provider.complete=complete
    return svc,p,run,provider,bundle,candidate,observed


def execute(case,svc,p,run,provider,bundle,candidate,observed,monkeypatch):
    pid=p['id'];before=snapshot(svc.store)
    if case=='R16':
        with svc.store.transaction() as con:
            con.execute("CREATE TRIGGER fail_report AFTER INSERT ON production_versions WHEN json_extract(NEW.content_json,'$.contract_version')='research-report-v3' BEGIN SELECT RAISE(ABORT,'injected'); END")
    result=svc.generate_report(pid,'report-'+case)
    expected_fail=set(ERRORS)|{'R14','R16'}
    assert result['status']==('failed' if case in expected_fail else 'success'),result
    aid=result['analysis_id'];assert aid is not None
    operation=svc.store.rows('SELECT * FROM topic_analyses WHERE id=?',(aid,))[0]
    assert operation['schema_version']=='research-report-v3'
    attempt=svc.store.rows('SELECT * FROM ai_analysis_runs WHERE analysis_id=?',(aid,))[0]
    assert attempt['input_tokens']==20 and attempt['output_tokens']==30 and attempt['estimated_cost_units']==280
    if case in expected_fail:
        assert snapshot(svc.store)==before
        assert operation['status']=='failed' and operation['analysis_json'] is None and operation['result_version_id'] is None
        diagnostic=svc.store.diagnostics(pid,aid)[0]
        assert diagnostic['stage']==('provider' if case=='R14' else 'persistence' if case=='R16' else 'validation')
        if case in ERRORS:assert diagnostic['code']==ERRORS[case],diagnostic
        assert 'synthetic-sensitive' not in json.dumps(diagnostic)
        assert len((diagnostic['rejected_document_json'] or '').encode())<=16384
    else:
        report=svc.current_report(pid)
        assert report['id']==operation['result_version_id']
        assert report['content']['basis']==bundle['basis']
        assert json.loads(operation['input_json'])['model_materials']==observed['model']
        assert report['content']['document']['categories']['verified']==[]
        assert svc.reports().state(pid)['current_report_state']=='validated_pending_confirmation'
        if case=='R17':
            old=deepcopy(report)
            again=svc.generate_report(pid,'report-second')
            assert again['status']=='success'
            assert svc.current_report(pid)['version_number']==old['version_number']+1
            assert svc.versions.details(pid,old['id'])==old
        if case=='R18':
            confirm(svc,pid,report)
            svc.search(pid,run['plan_version_id'],'changed-search')
            assert svc.reports().state(pid)['current_report_state']=='stale'
            with pytest_raises():ProjectService(svc.store).set_status(pid,'scripting')
        if case=='R20':
            with pytest_raises():ProjectService(svc.store).set_status(pid,'scripting')
            with pytest_raises():VersionService(svc.store).create(pid,'script',{'text':'blocked'})
        if case=='R21':
            confirm(svc,pid,report)
            ProjectService(svc.store).set_status(pid,'scripting')
            assert svc.reports().state(pid)['current_report_state']=='confirmed'
            script=VersionService(svc.store).create(pid,'script',{'text':'local fixture'})
            assert script['content']=={'text':'local fixture'}
            audit=svc.store.actions(pid)[-1]['details']['confirmed_report']
            assert audit['report_version_id']==report['id']
            assert audit['report_core_hash']==report['content']['validation']['report_core_hash']
        if case=='R22':
            legacy=before['production_versions'][-1]
            assert svc.versions.details(pid,legacy['id'])['content']==json.loads(legacy['content_json'])
            with pytest_raises():svc.versions.restore(pid,legacy['id'],object_id=legacy['object_id'])
    after=snapshot(svc.store)
    for t in ('research_evidence','research_evidence_sources','research_sources','ai_budget_settings'):
        assert after[t]==before[t]
    assert after['production_versions'][:len(before['production_versions'])]==before['production_versions']
    assert svc.store.rows('PRAGMA user_version')[0]['user_version']==6
    assert svc.store.rows('PRAGMA foreign_key_check')==[]
    if case in ('R01','R16','R21'):
        from pathlib import Path
        out=Path(__file__).resolve().parents[1]/'logs/phase4-2-1-4-c-b'
        if out.is_dir():
            proof={'case':case,'before':before,'after':after,'operation':operation,
                'attempt':{k:attempt[k] for k in ('status','input_tokens','output_tokens','estimated_cost_units')},
                'messages':provider.calls,'actions':svc.store.rows('SELECT * FROM production_actions'),
                'report':svc.current_report(pid)}
            (out/(case+'-proof.json')).write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def pytest_raises():
    import pytest
    return pytest.raises(ValueError)
