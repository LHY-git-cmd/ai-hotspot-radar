"""临时SQLite真实写入、投影和故障回滚；禁止使用正式数据库。"""

from copy import deepcopy
import json

import pytest

from services.ai.base import ProviderReply, Usage
from tests.test_research_workflow import research, ready
from tests.test_research_quality_integration import visible_candidate
from tests.research_service_cases import CASES, VARIANTS, create_case, seed_history, capture, assert_case


@pytest.mark.parametrize('case_id', CASES+VARIANTS)
def test_case(production_store, monkeypatch, case_id):
    svc,p,run,provider,seen,cfg=create_case(production_store,monkeypatch,case_id)
    legacy=seed_history(svc,p,run)
    before=capture(svc)
    schema=svc.store.rows("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name")
    result=svc.organize_evidence(p['id'],run['id'],'P-'+case_id)
    assert_case(svc,p,run,provider,seen,cfg,before,result)
    assert svc.store.rows("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name")==schema
    assert svc.store.evidence(p['id'],legacy)[0]['category']=='verified'
    assert svc.store.evidence(p['id'],legacy)[0]['review_status']=='legacy_unreviewed'


@pytest.mark.parametrize('fault', ['none', 'offset', 'body_hash', 'snapshot', 'project', 'run', 'source',
                                 'link_exception', 'analysis_exception', 'legacy_document'])
def test_transaction_and_binding(research, fault, monkeypatch):
    svc, project, _, provider, _ = research
    _, run = ready(research)
    original = svc.store.insert_evidence
    expected = {}

    def complete(messages):
        provider.calls.append(deepcopy(messages))
        payload = json.loads(messages[1]['content'])['untrusted_materials']
        doc = visible_candidate(payload)
        expected['link'] = doc['questions'][0]['items'][0]['links'][0]
        return ProviderReply(doc, Usage(20, 30))

    provider.complete = complete

    def insert(con, pid, rid, aid, doc):
        if fault in ('body_hash', 'snapshot', 'project', 'run', 'source'):
            from services.research.evidence_contract import digest, model_materials
            inputs = json.loads(con.execute('SELECT input_json FROM topic_analyses WHERE id=?', (aid,)).fetchone()[0])
            source = next(iter(inputs['manifest']['sources'].values()))
            if fault == 'body_hash': source['body_hash'] = 'forged'
            if fault == 'snapshot': source['snapshot_hash'] = 'forged'
            if fault == 'project': source['project_id'] = pid + 1
            if fault == 'run': source['run_id'] = rid + 1
            if fault == 'source': source['source_id'] = 999999
            manifest = inputs['manifest']
            manifest['manifest_hash'] = digest({k:v for k,v in manifest.items() if k != 'manifest_hash'})
            plan = svc.current_plan(pid)['content']
            inputs['model_materials'] = model_materials(manifest, plan, inputs['plan_version_id'])
            con.execute('UPDATE topic_analyses SET input_json=? WHERE id=?', (json.dumps(inputs), aid))
        if fault == 'offset':
            doc['items'][0]['links'][0]['start'] += 1
        if fault == 'legacy_document':
            doc = {'items': [{'question_id': 'q1', 'category': 'verified', 'summary': 'forged',
                'inference': '', 'verification': 'forged', 'links': [{'source_id': expected['link']['source_id'],
                    'field': 'text', 'quote': expected['link']['quote']}]}], 'gaps': []}
        original(con, pid, rid, aid, doc)

    monkeypatch.setattr(svc.store, 'insert_evidence', insert)
    if fault in ('link_exception', 'analysis_exception'):
        # SQLite真实触发器在证据插入之后抛错，检验实际事务回滚。
        table = 'research_evidence_sources' if fault == 'link_exception' else 'topic_analyses'
        event = 'INSERT' if fault == 'link_exception' else 'UPDATE OF analysis_json'
        with svc.store.transaction() as con:
            con.execute(f"CREATE TRIGGER batch2_fault BEFORE {event} ON {table} BEGIN SELECT RAISE(ABORT, 'injected persistence fault'); END")
    before = {table: svc.store.rows('SELECT * FROM '+table) for table in
              ('research_evidence', 'research_evidence_sources', 'production_versions', 'ai_budget_settings')}
    result = svc.organize_evidence(project['id'], run['id'], 'persist-'+fault)
    operation = svc.store.rows('SELECT * FROM topic_analyses WHERE id=?', (result['analysis_id'],))[0]
    if fault == 'none':
        assert result['status'] == 'success', result
        rows = svc.store.evidence(project['id'], result['analysis_id'])
        assert len(rows) == 1
        link = rows[0]['links'][0]
        assert link['quote_offset'] == expected['link']['start']
        assert link['region'] == expected['link']['region']
        assert rows[0]['quality']['final_category'] == 'unverified'
    else:
        assert result['status'] == 'failed', result
        for table, old in before.items():
            assert svc.store.rows('SELECT * FROM '+table) == old, table
        assert operation['analysis_json'] is None
        assert operation['status'] == 'failed' and operation['success_run_id'] is None
        assert svc.store.rows('SELECT * FROM research_evidence WHERE analysis_id=?', (operation['id'],)) == []
        assert svc.store.rows('''SELECT l.* FROM research_evidence_sources l JOIN research_evidence e
            ON e.id=l.evidence_id WHERE e.analysis_id=?''', (operation['id'],)) == []
    attempt = svc.store.rows('SELECT * FROM ai_analysis_runs WHERE analysis_id=?', (operation['id'],))[0]
    assert attempt['input_tokens'] == 20 and attempt['output_tokens'] == 30
    assert attempt['estimated_cost_units'] > 0
    assert svc.store.rows('PRAGMA foreign_key_check') == []
    assert svc.store.rows('PRAGMA user_version')[0]['user_version'] == 6


@pytest.mark.parametrize('stage', ['second_evidence', 'second_link', 'after_analysis'])
def test_mid_transaction_failure_preserves_old_rows_and_result(research, monkeypatch, stage):
    from tests.research_service_cases import seed_history, capture
    svc,p,_,provider,_=research
    _,run=ready(research)
    # 旧夹具问题ID为q1，历史样本仅用于数据保护，不经过新模型写入接口。
    legacy=seed_history(svc,p,run)
    def complete(messages):
        payload=json.loads(messages[1]['content'])['untrusted_materials']
        doc=visible_candidate(payload)
        first=doc['questions'][0]['items'][0]
        second=deepcopy(first);second.update(candidate_id='second',kind='opinion')
        doc['questions'][0]['items'].append(second)
        return ProviderReply(doc,Usage(20,30))
    provider.complete=complete
    condition={'second_evidence':("BEFORE INSERT",'research_evidence',
        "WHEN NEW.position=2"), 'second_link':('BEFORE INSERT','research_evidence_sources',
        "WHEN (SELECT position FROM research_evidence WHERE id=NEW.evidence_id)=2"),
        'after_analysis':('AFTER UPDATE OF analysis_json','topic_analyses',"WHEN NEW.schema_version='research-evidence-v3'")}[stage]
    with svc.store.transaction() as con:
        con.execute(f"CREATE TRIGGER mid_failure {condition[0]} ON {condition[1]} {condition[2]} BEGIN SELECT RAISE(ABORT,'mid transaction'); END")
    before=capture(svc)
    old_operations=svc.store.rows('SELECT * FROM topic_analyses ORDER BY id')
    result=svc.organize_evidence(p['id'],run['id'],'mid-'+stage)
    assert result['status']=='failed'
    assert capture(svc)==before
    assert svc.store.rows('SELECT * FROM topic_analyses ORDER BY id')[:len(old_operations)]==old_operations
    operation=svc.store.rows('SELECT * FROM topic_analyses WHERE id=?',(result['analysis_id'],))[0]
    assert operation['analysis_json'] is None and operation['status']=='failed'
    assert svc.store.evidence(p['id'],result['analysis_id'])==[]
    assert svc.store.evidence(p['id'],legacy)[0]['category']=='verified'
    diagnostic=svc.store.diagnostics(p['id'],result['analysis_id'])[0]
    assert diagnostic['stage']=='persistence'
    attempt=svc.store.rows('SELECT * FROM ai_analysis_runs WHERE analysis_id=?',(operation['id'],))[0]
    assert attempt['status']=='success' and attempt['estimated_cost_units']>0
    assert svc.store.rows('PRAGMA foreign_key_check')==[]
    from pathlib import Path
    out=Path(__file__).resolve().parents[1]/'logs/phase4-2-1-4-b-batch2'
    if out.is_dir():
        proof={'stage':stage,'before':before,'after':capture(svc),
            'analysis':operation,'attempt':{k:attempt[k] for k in ('status','input_tokens','output_tokens','estimated_cost_units')},
            'diagnostic':diagnostic}
        (out/('rollback-'+stage+'.json')).write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('kind', ['missing', 'cross_project', 'cross_run'])
def test_foreign_snapshot_source_cannot_be_saved(research, monkeypatch, kind):
    from tests.research_service_cases import seed_history, capture
    from services.research.base import SearchReply, SearchResult, ExtractReply, ExtractResult
    from services.production.project_service import ProjectService
    svc,p,plan,provider,search=research
    version,run=ready(research)
    bad_id=999999
    if kind=='cross_project':
        other=ProjectService(svc.store).create(2,'另一个真实临时项目')
        v=svc.save_plan(other['id'],plan)
        svc.confirm_plan(other['id'],v['id'],'foreign-confirm')
        foreign=svc.search(other['id'],v['id'],'foreign-search')
        bad_id=svc.store.sources(other['id'],foreign['id'])[0]['id']
    elif kind=='cross_run':
        bad_id=svc.store.sources(p['id'],run['id'])[0]['id']
        search.search.return_value=SearchReply([SearchResult('新资料','https://example.com/new','新摘录')],1)
        search.extract.return_value=ExtractReply([ExtractResult('https://example.com/new','测试：支持本地运行。')],0)
        run=svc.search(p['id'],version['id'],'new-search')
    legacy=seed_history(svc,p,run)
    before=capture(svc)
    def complete(messages):
        payload=json.loads(messages[1]['content'])['untrusted_materials']
        doc=visible_candidate(payload)
        doc['questions'][0]['items'][0]['links'][0]['source_id']=bad_id
        return ProviderReply(doc,Usage(20,30))
    provider.complete=complete
    result=svc.organize_evidence(p['id'],run['id'],'foreign-'+kind)
    assert result['status']=='failed'
    assert capture(svc)==before
    assert svc.store.evidence(p['id'],result['analysis_id'])==[]
    assert svc.store.diagnostics(p['id'],result['analysis_id'])[0]['code']=='source_association'
    assert svc.store.evidence(p['id'],legacy)[0]['review_status']=='legacy_unreviewed'


def test_v3_diagnostic_redacts_sensitive_values_and_unknown_keys(research):
    svc,p,_,provider,_=research
    _,run=ready(research)
    secret='synthetic-key-never-from-env'
    def complete(messages):
        payload=json.loads(messages[1]['content'])['untrusted_materials']
        doc=visible_candidate(payload)
        doc['questions'][0]['items'][0].update(summary='Bearer '+secret,Authorization='Bearer '+secret)
        return ProviderReply(doc,Usage(20,30))
    provider.complete=complete
    result=svc.organize_evidence(p['id'],run['id'],'sensitive-v3')
    assert result['status']=='failed'
    diagnostic=svc.store.diagnostics(p['id'],result['analysis_id'])[0]
    assert diagnostic['code']=='schema' and diagnostic['item_index']==0
    assert json.loads(diagnostic['path_json'])==['questions',0,'items',0]
    assert secret not in json.dumps(diagnostic) and 'Authorization' not in json.dumps(diagnostic)
    assert 'Bearer' not in json.dumps(diagnostic)
    assert len(diagnostic['rejected_document_json'].encode())<=16384
    assert json.loads(diagnostic['details_json'])['free_text_redacted'] is True


@pytest.mark.parametrize('version',['research-evidence-v1','research-evidence-v2'])
def test_old_version_is_readable_and_new_version_is_append_only(production_store, monkeypatch, version):
    from tests.research_service_cases import create_case,seed_history,capture
    svc,p,run,provider,seen,cfg=create_case(production_store,monkeypatch,'T01')
    legacy=seed_history(svc,p,run)
    if version.endswith('v1'):
        with svc.store.transaction() as con:
            row=con.execute('SELECT analysis_json FROM topic_analyses WHERE id=?',(legacy,)).fetchone()
            doc=json.loads(row[0])
            for item in doc['items']:
                item.pop('time_scope');item.pop('data_period')
            con.execute('UPDATE topic_analyses SET schema_version=?,analysis_json=? WHERE id=?',
                        (version,json.dumps(doc),legacy))
    old=svc.store.rows('SELECT * FROM topic_analyses WHERE id=?',(legacy,))[0]
    before=capture(svc)
    for action in ('new-first','new-second'):
        result=svc.organize_evidence(p['id'],run['id'],action)
        assert result['status']=='success'
        assert result['analysis_id']!=legacy
        assert svc.store.evidence(p['id'],result['analysis_id'])[0]['category']=='single_source'
        assert svc.store.rows('SELECT * FROM topic_analyses WHERE id=?',(legacy,))[0]==old
    after=capture(svc)
    assert after['research_evidence'][:len(before['research_evidence'])]==before['research_evidence']
    assert len(after['research_evidence'])==len(before['research_evidence'])+2
    assert after['production_versions']==before['production_versions']
    old_read=svc.store.evidence(p['id'],legacy)[0]
    assert old_read['category']=='verified' and old_read['review_status']=='legacy_unreviewed'
    assert 'quality' not in old_read


def test_reader_fails_closed_on_projection_corruption(research):
    svc,p,_,provider,_=research
    _,run=ready(research)
    def complete(messages):
        return ProviderReply(visible_candidate(json.loads(messages[1]['content'])['untrusted_materials']),Usage(20,30))
    provider.complete=complete
    result=svc.organize_evidence(p['id'],run['id'],'reader-projection')
    assert result['status']=='success'
    with svc.store.transaction() as con:
        row=con.execute('SELECT analysis_json FROM topic_analyses WHERE id=?',(result['analysis_id'],)).fetchone()
        doc=json.loads(row[0]);doc['items'][0]['links'][0]['start']+=1
        con.execute('UPDATE topic_analyses SET analysis_json=? WHERE id=?',(json.dumps(doc),result['analysis_id']))
    with pytest.raises(ValueError,match='引用SQL与JSON'):
        svc.store.evidence(p['id'],result['analysis_id'])


@pytest.mark.parametrize('changed_basis',['plan','search'])
def test_basis_changes_during_model_call_refuse_commit_and_preserve_fee(research,changed_basis):
    svc,p,plan,provider,_=research
    version,run=ready(research)
    before_evidence=svc.store.rows('SELECT * FROM research_evidence')
    before_links=svc.store.rows('SELECT * FROM research_evidence_sources')
    def complete(messages):
        doc=visible_candidate(json.loads(messages[1]['content'])['untrusted_materials'])
        if changed_basis=='plan':
            svc.save_plan(p['id'],dict(plan,focus='人工并发修改，应保留'))
        else:
            svc.search(p['id'],version['id'],'concurrent-new-search')
        return ProviderReply(doc,Usage(20,30))
    provider.complete=complete
    result=svc.organize_evidence(p['id'],run['id'],'basis-race-'+changed_basis)
    assert result['status']=='failed'
    assert svc.store.rows('SELECT * FROM research_evidence')==before_evidence
    assert svc.store.rows('SELECT * FROM research_evidence_sources')==before_links
    operation=svc.store.rows('SELECT * FROM topic_analyses WHERE id=?',(result['analysis_id'],))[0]
    assert operation['analysis_json'] is None and operation['status']=='failed'
    attempt=svc.store.rows('SELECT * FROM ai_analysis_runs WHERE analysis_id=?',(operation['id'],))[0]
    assert attempt['input_tokens']==20 and attempt['estimated_cost_units']>0
    if changed_basis=='plan': assert svc.current_plan(p['id'])['content']['focus']=='人工并发修改，应保留'
    else: assert svc.store.runs(p['id'])[0]['id']!=run['id']
