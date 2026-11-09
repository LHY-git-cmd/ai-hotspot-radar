"""22场景的临时SQLite实际持久化与零写入/历史快照核对。"""

import pytest
import json
from copy import deepcopy
from tests.research_report_cases import CASES,make_scenario,execute
from tests.research_report_cases import saved,confirm,snapshot,block
from tests.test_research_report_integration import prepared
from services.ai.base import ProviderReply,Usage
from services.production.project_service import ProjectService
from services.production.version_service import VersionService
from services.research.report_confirmation import LocalReportReviewSession,HumanConfirmationIntent


@pytest.mark.parametrize('case_id',CASES)
def test_case(production_store,monkeypatch,case_id):
    args=make_scenario(production_store,monkeypatch,case_id)
    svc=args[0]
    before=svc.store.rows("SELECT * FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name")
    execute(case_id,*args,monkeypatch)
    after=svc.store.rows("SELECT * FROM sqlite_master WHERE sql IS NOT NULL AND name<>'fail_report' ORDER BY type,name")
    assert after==before


@pytest.mark.parametrize('fault',['after_version','validated_audit','analysis_update','confirmed_audit'])
def test_real_sqlite_fault_rolls_back_whole_report_or_confirmation(production_store,monkeypatch,fault):
    svc,p,run,provider=prepared(production_store,monkeypatch)
    old=saved(svc,p['id']);confirm(svc,p['id'],old)
    before=snapshot(svc.store)
    before_actions=svc.store.rows('SELECT * FROM production_actions')
    if fault=='confirmed_audit':
        current=saved(svc,p['id']);before=snapshot(svc.store)
        before_actions=svc.store.rows('SELECT * FROM production_actions')
    condition={
        'after_version':("AFTER INSERT",'production_versions',"WHEN json_extract(NEW.content_json,'$.contract_version')='research-report-v3'"),
        'validated_audit':('AFTER INSERT','production_actions',"WHEN json_extract(NEW.details_json,'$.event')='report_validated_v3'"),
        'analysis_update':('AFTER UPDATE OF analysis_json','topic_analyses',"WHEN NEW.purpose='research_report'"),
        'confirmed_audit':('AFTER INSERT','production_actions',"WHEN json_extract(NEW.details_json,'$.event')='report_confirmed_v3'")}[fault]
    with svc.store.transaction() as con:
        con.execute(f"CREATE TRIGGER report_fault {condition[0]} ON {condition[1]} {condition[2]} BEGIN SELECT RAISE(ABORT,'synthetic fault'); END")
    if fault=='confirmed_audit':
        with pytest.raises(Exception):confirm(svc,p['id'],current,'failed-confirm')
        assert svc.store.rows('SELECT * FROM production_actions')==before_actions
        assert svc.reports().state(p['id'])['current_report_state']=='validated_pending_confirmation'
    else:
        provider.complete=lambda messages:ProviderReply(svc.reports().draft(p['id'])['candidate_document'],Usage(20,30))
        result=svc.generate_report(p['id'],'fault-'+fault)
        assert result['status']=='failed'
        op=svc.store.rows('SELECT * FROM topic_analyses WHERE id=?',(result['analysis_id'],))[0]
        assert op['analysis_json'] is None and op['result_version_id'] is None
        attempt=svc.store.rows('SELECT * FROM ai_analysis_runs WHERE analysis_id=?',(op['id'],))[0]
        assert attempt['estimated_cost_units']==280 and attempt['status']=='success'
        assert svc.current_report(p['id'])==old
    assert snapshot(svc.store)==before
    assert svc.store.rows('PRAGMA foreign_key_check')==[]


@pytest.mark.parametrize('fault',['value','period','grade','pool','policy','renderer','quote','source_snapshot'])
def test_forged_normalized_envelope_cannot_be_published(production_store,monkeypatch,fault):
    from services.research.report_validation import validate_candidate
    svc,p,_,_=prepared(production_store,monkeypatch)
    b=svc.reports().bundle(p['id']);doc=validate_candidate(svc.reports().draft(p['id'])['candidate_document'],b,checked_at='fixed')
    e=doc['document']['categories']['single_source'][0]
    if fault=='value':e['claim']['value']='999'
    elif fault=='period':e['temporal']['coverage_end']='2099-01-01'
    elif fault=='grade':e['category']='verified'
    elif fault=='pool':doc['basis']['evidence_set_hash']='forged'
    elif fault=='policy':doc['validation']['policy_version']='forged'
    elif fault=='renderer':doc['validation']['renderer_version']='forged'
    elif fault=='quote':e['citations'][0]['quote']='forged quote'
    else:doc['evidence_snapshot']['evidence'][0]['source_bindings'][0]['snapshot_hash']='forged'
    before=snapshot(svc.store)
    with svc.store.transaction() as con:
        with pytest.raises(ValueError):svc.reports()._publish(con,p['id'],doc,None,source='manual')
    assert snapshot(svc.store)==before
    with pytest.raises(ValueError):VersionService(svc.store).create(p['id'],'research',doc,object_key='report')


@pytest.mark.parametrize('fault',['empty_intent','plain_dict','unregistered_object','cross_project','replay','action_purpose',
                                  'isolated_confirmation','wrong_confirmation_binding','missing_validation_receipt'])
def test_confirmation_requires_intent_and_persistent_full_binding(production_store,monkeypatch,fault):
    svc,p,run,_=prepared(production_store,monkeypatch)
    report=saved(svc,p['id']);pid=p['id'];action='review-action'
    session=LocalReportReviewSession();intent=session.reviewed(pid,report,checked=True)
    if fault=='empty_intent':intent=None
    elif fault=='plain_dict':intent={'confirmed':True,'actor':'user'}
    elif fault=='unregistered_object':intent=HumanConfirmationIntent()
    elif fault=='cross_project':intent=session.reviewed(pid+1,report,checked=True)
    elif fault=='action_purpose':action='confirm-T01'
    elif fault=='replay':
        svc.confirm_report(pid,report['id'],action,intent=intent)
        svc.confirm_report(pid,report['id'],action,intent=intent)  # 精确重复幂等。
        action='other-action'
    elif fault in ('isolated_confirmation','wrong_confirmation_binding'):
        b=report['content']['basis']
        with svc.store.transaction() as con:
            con.execute('''INSERT INTO research_report_confirmations(project_id,report_version_id,plan_confirmation_id,
                run_id,evidence_analysis_id,action_id,confirmed_at) VALUES(?,?,?,?,?,?,?)''',
                (pid,report['id'],b['plan_confirmation_id'],run['id'],
                 1 if fault=='wrong_confirmation_binding' else b['evidence_analysis_id'],'injected','fixed'))
    elif fault=='missing_validation_receipt':
        # 有完整合法Envelope但没有受控发布的校验回执。
        with svc.store.transaction() as con:
            vid=svc.store.insert_version(con,pid,report['object_id'],json.dumps(report['content']),'manual','forged','fixed')
        report=svc.versions.details(pid,vid);intent=session.reviewed(pid,report,checked=True)
    before=snapshot(svc.store)
    with pytest.raises(ValueError):svc.confirm_report(pid,report['id'],action,intent=intent)
    assert snapshot(svc.store)==before
    if fault!='replay':
        with pytest.raises(ValueError):ProjectService(svc.store).set_status(pid,'scripting')


@pytest.mark.parametrize('basis_change',['search','evidence','manual_report'])
def test_change_during_model_call_aborts_publication_and_preserves_manual_work(production_store,monkeypatch,basis_change):
    svc,p,run,provider=prepared(production_store,monkeypatch)
    first=saved(svc,p['id']);candidate=svc.reports().draft(p['id'])['candidate_document']
    original=provider.complete
    changed={}
    def complete(messages):
        if basis_change=='search':svc.search(p['id'],run['plan_version_id'],'race-search')
        elif basis_change=='manual_report':changed['report']=saved(svc,p['id'])
        else:
            provider.complete=original
            result=svc.organize_evidence(p['id'],run['id'],'race-evidence');assert result['status']=='success'
            provider.complete=complete
        return ProviderReply(candidate,Usage(20,30))
    provider.complete=complete
    result=svc.generate_report(p['id'],'racing-report')
    assert result['status']=='failed'
    assert svc.current_report(p['id'])==changed.get('report',first)
    op=svc.store.rows('SELECT * FROM topic_analyses WHERE id=?',(result['analysis_id'],))[0]
    assert op['analysis_json'] is None
    assert svc.store.rows('SELECT * FROM ai_analysis_runs WHERE analysis_id=?',(op['id'],))[0]['estimated_cost_units']==280


def test_new_failed_attempt_does_not_invalidate_unchanged_confirmed_report(production_store,monkeypatch):
    svc,p,_,provider=prepared(production_store,monkeypatch)
    report=saved(svc,p['id']);confirm(svc,p['id'],report)
    provider.complete=lambda messages:ProviderReply({'confirmed':True},Usage(20,30))
    result=svc.generate_report(p['id'],'bad-later-attempt')
    assert result['status']=='failed'
    assert svc.reports().state(p['id'])['current_report_state']=='confirmed'
    assert svc.reports().state(p['id'])['latest_attempt_state']=='validation_failed'
    ProjectService(svc.store).set_status(p['id'],'scripting')


def test_manual_edit_cas_restore_and_pause_resume_use_same_gate(production_store,monkeypatch):
    svc,p,_,_=prepared(production_store,monkeypatch)
    first=saved(svc,p['id']);confirm(svc,p['id'],first)
    frozen=svc.reports().draft(p['id'])
    second=saved(svc,p['id'])
    with pytest.raises(ValueError):
        svc.save_report(p['id'],frozen['candidate_document'],expected_previous_report_version_id=first['id'])
    restored=svc.versions.restore(p['id'],first['id'],object_id=first['object_id'])
    assert restored['source']=='restore' and restored['restored_from_version_id']==first['id']
    assert svc.versions.details(p['id'],first['id'])==first
    assert restored['id']!=second['id']
    with pytest.raises(ValueError):ProjectService(svc.store).set_status(p['id'],'scripting')
    confirm(svc,p['id'],restored,'restored-confirm')
    projects=ProjectService(svc.store);projects.set_status(p['id'],'scripting');projects.pause(p['id'])
    with pytest.raises(ValueError):saved(svc,p['id'])
    with pytest.raises(ValueError):svc.versions.create(p['id'],'script','paused write blocked')
    projects.resume(p['id'])
    assert svc.store.get_project(p['id'])['status']=='scripting'
    script=svc.versions.create(p['id'],'script','allowed')
    third=saved(svc,p['id'])
    with pytest.raises(ValueError):svc.versions.restore(p['id'],script['id'],object_id=script['object_id'])
    assert svc.reports().state(p['id'])['current_report_state']=='validated_pending_confirmation'


def test_confirmation_expiry_idempotence_and_no_implicit_transfer(production_store,monkeypatch):
    import services.research.report_confirmation as boundary
    svc,p,_,_=prepared(production_store,monkeypatch)
    report=saved(svc,p['id']);session=LocalReportReviewSession()
    t=boundary.monotonic()
    monkeypatch.setattr(boundary,'monotonic',lambda:t)
    expired=session.reviewed(p['id'],report,checked=True)
    monkeypatch.setattr(boundary,'monotonic',lambda:t+601)
    with pytest.raises(ValueError):svc.confirm_report(p['id'],report['id'],'expired',intent=expired)
    valid=session.reviewed(p['id'],report,checked=True)
    svc.confirm_report(p['id'],report['id'],'valid-confirm',intent=valid)
    monkeypatch.setattr(boundary,'monotonic',lambda:t+2000)
    svc.confirm_report(p['id'],report['id'],'valid-confirm',intent=valid)
    assert svc.reports().state(p['id'])['current_report_state']=='confirmed'
    other=saved(svc,p['id'])
    with pytest.raises(ValueError):svc.confirm_report(p['id'],other['id'],'transferred',intent=valid)
    assert len(svc.store.rows('SELECT * FROM research_report_confirmations'))==1


def test_report_operation_is_idempotent_and_action_cannot_cross_purpose(production_store,monkeypatch):
    svc,p,_,provider=prepared(production_store,monkeypatch)
    c=svc.reports().draft(p['id'])['candidate_document'];calls=[]
    def complete(messages):calls.append(messages);return ProviderReply(c,Usage(20,30))
    provider.complete=complete
    one=svc.generate_report(p['id'],'once');two=svc.generate_report(p['id'],'once')
    assert one['status']=='success' and two['reused'] is True and one['analysis_id']==two['analysis_id']
    assert len(calls)==1
    before=snapshot(svc.store)
    result=svc.generate_report(p['id'],'report-evidence')
    assert result['status']=='failed' and result['analysis_id'] is None
    assert len(calls)==1 and snapshot(svc.store)==before


@pytest.mark.parametrize('corruption',['assessment','input_snapshot','sql_scope','legacy','attempt'])
def test_evidence_integrity_rechecked_before_report_call(production_store,monkeypatch,corruption):
    from services.research.evidence_contract import digest
    svc,p,run,provider=prepared(production_store,monkeypatch)
    aid=svc.basis(p['id'])['evidence_analysis_id']
    before=svc.store.rows('SELECT * FROM ai_analysis_runs')
    with svc.store.transaction() as con:
        row=con.execute('SELECT * FROM topic_analyses WHERE id=?',(aid,)).fetchone()
        doc=json.loads(row['analysis_json']);inputs=json.loads(row['input_json'])
        if corruption=='assessment':
            doc['items'][0]['quality']['independence_status']='confirmed_independent'
            con.execute('UPDATE topic_analyses SET analysis_json=? WHERE id=?',(json.dumps(doc),aid))
        elif corruption=='input_snapshot':
            next(iter(inputs['manifest']['sources'].values()))['snapshot_hash']='forged'
            inputs['manifest']['manifest_hash']=digest({k:v for k,v in inputs['manifest'].items() if k!='manifest_hash'})
            con.execute('UPDATE topic_analyses SET input_json=? WHERE id=?',(json.dumps(inputs),aid))
        elif corruption=='sql_scope':
            inputs['run_id']=run['id']+1
            con.execute('UPDATE topic_analyses SET input_json=? WHERE id=?',(json.dumps(inputs),aid))
        elif corruption=='legacy':con.execute("UPDATE topic_analyses SET schema_version='research-evidence-v2' WHERE id=?",(aid,))
        else:con.execute('UPDATE topic_analyses SET success_run_id=NULL WHERE id=?',(aid,))
    provider.calls=[]
    result=svc.generate_report(p['id'],'corrupted-'+corruption)
    assert result['status']=='failed' and result['analysis_id'] is None
    assert provider.calls==[] and svc.store.rows('SELECT * FROM ai_analysis_runs')==before
