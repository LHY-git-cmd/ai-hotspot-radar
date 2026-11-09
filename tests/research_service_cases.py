"""T01–T40的独立场景与预期；运行真实服务，不由被测实现推导expected。"""

from copy import deepcopy
from pathlib import Path
import hashlib
import json
from unittest.mock import Mock

from services.ai.base import ProviderReply, Usage
from services.ai.config import AISettings
from services.ai.mock import MockProvider
from services.research.base import SearchReply, SearchResult, ExtractReply, ExtractResult, Quota
from services.research.service import ResearchService
from services.production.project_service import ProjectService
from tests.research_quality_cases import setup, item


CASES = [f'T{i:02}' for i in range(1, 41)]
VARIANTS = ['T03-trust', 'T08-actual', 'T09-speaker', 'T09-actual', 'T12-body', 'T14-unseen',
    'T14-budget', 'T15-unrelated', 'T16-gap', 'T17-fake', 'T18-fake', 'T19-disputed',
    'T24-missing', 'T24-unknown', 'T25-category', 'T25-trust', 'T25-independence',
    'T25-verified', 'T25-review', 'T28-unknown', 'T28-fake', 'T29-actual', 'T31-valid',
    'T32-splice', 'T35-gap', 'T36-gap', 'T39-title', 'T07-expected', 'T10-header',
    'T10-impersonate', 'T11-bodyregion', 'T12-gap', 'T14-old682']
BASE_TEXT = 'Oracle公布收入增长20%。'


def scenario(code):
    base = code.split('-')[0]
    v = code.split('-', 1)[1] if '-' in code else ''
    cfg = {'code': code, 'base': base, 'variant': v, 'texts': [BASE_TEXT], 'titles': ['官方资料'],
           'snippets': [''], 'dates': ['2024-12-10'], 'status': 'success',
           'keywords': ['Oracle', '收入', '20%'], 'questions': 1, 'grade': 'single_source',
           'error': None, 'quote': None, 'temporal': 'unknown'}
    if base in ('T02', 'T20', 'T26', 'T37'):
        cfg['texts'] *= 2
        cfg['titles'] *= 2; cfg['snippets'] *= 2; cfg['dates'] *= 2
        if base in ('T26', 'T37'):
            cfg['texts'][1] = '另一报道：Oracle收入增长20%。'
            cfg['grade'] = 'unverified'
        if base == 'T20':
            cfg['titles'][1] = '元数据更新快照'
            cfg['dates'][1] = '2025-01-01'
    if base == 'T03':
        cfg['texts'] = ['Oracle公布收入增长20%。', '另一报道：Oracle收入增长20%。']
        cfg['titles'] *= 2; cfg['snippets'] *= 2; cfg['dates'] *= 2
        cfg['grade'] = 'unverified'; cfg['trust_in_plan'] = True
        if v: cfg['error'] = 'schema'
    if base == 'T04': cfg['error'] = 'question_limit'
    if base in ('T05', 'T21'): cfg['grade'] = None
    if base == 'T21': cfg['error'] = 'missing_question_gap'
    if base == 'T06':
        cfg.update(texts=['Oracle公布FY2027 Q1业绩，收入增长20%。'], dates=['2026-09-10'], label='FY2027 Q1')
    if base == 'T07':
        cfg.update(texts=['Oracle公布截至2024-11-30实际收入增长18%，低于市场预期20%。'],
                   value='18', end='2024-11-30', temporal='historical_actual')
        if v: cfg.update(value='20',error='claim_support_mismatch')
    if base in ('T08', 'T09', 'T29'):
        text, typ = {'T08': ('Oracle公司预计下一季度收入增长20%。', 'company_guidance'),
                     'T09': ('分析师预测明年Oracle收入增长20%。', 'analyst_forecast'),
                     'T29': ('市场预期Oracle收入增长20%，尚无实际结果。', 'market_expectation')}[base]
        cfg.update(texts=[text], temporal=typ)
        if v: cfg['error'] = 'speaker_mismatch' if v == 'speaker' else 'temporal_mismatch'
    if base == 'T10':
        cfg.update(texts=[BASE_TEXT+'\n\n仅背景。'], titles=[BASE_TEXT], error='unsupported_region')
        if v=='header': cfg['texts']=['Skip to content\nValuentum\n'+BASE_TEXT+'\n\n仅背景。']
        if v=='impersonate': cfg['error']='quote_not_visible'
    if base in ('T11', 'T12'):
        cfg.update(snippets=[BASE_TEXT], texts=['正文不可得。'], grade='unverified', keywords=['Oracle','收入'])
        if base == 'T12': cfg['status'] = 'failed'
        if v == 'body': cfg['error'] = 'extraction_unavailable'
        if v == 'bodyregion': cfg['error'] = 'region_mismatch'
        if v == 'gap': cfg['grade'] = None
    if base == 'T13':
        cfg.update(texts=['Oracle公布FY2025 Q2业绩：OCI收入同比增长52%。\n\n'+'背景。'*300],
                   keywords=['Oracle','OCI','52%','FY2025 Q2'], value='52', metric='OCI收入', label='FY2025 Q2')
    if base == 'T14':
        text = (Path(__file__).parent/'fixtures/research_quality/s26.txt').read_text(encoding='utf-8')
        assert len(text) == 4549 and text[910:913] == '52%' and text[1105:1109] == '336%'
        assert hashlib.sha256(text.encode()).hexdigest() == '29ae66728e0afc0e87118fb551f9c231926efcf5f090dab7a3ae50aa906c5e27'
        cfg.update(texts=[text], keywords=['Oracle','52%','336%','GPU','cloud','fiscal 2025'],
                   grade='unverified', label='second quarter fiscal 2025')
        if v: cfg['error']='quote_not_visible'
        if v and v!='budget': cfg['keywords']=['Valuentum']
        if v == 'budget': cfg['small_budget'] = True
        if v == 'old682': cfg['snippets']=[text[:682]]
    if base == 'T15':
        cfg.update(texts=['Oracle公布FY2025 Q2业绩。\n\n'+'无关背景。'*180+'\n\n该季度Oracle GPU消费增长336%。'],
                   keywords=['Oracle','FY2025 Q2','GPU','336%'], quote='该季度Oracle GPU消费增长336%。',
                   label='FY2025 Q2', metric='GPU消费', value='336')
        if v: cfg['error'] = 'unsupported_period'
    if base == 'T16':
        cfg.update(texts=['Oracle没有提供GPU消费数据。'], keywords=['Oracle','GPU','336%'], error='quote_not_visible')
        if v == 'gap': cfg.update(error=None, grade=None)
    if base == 'T17':
        cfg.update(dates=[None], texts=['Oracle公布FY2025 Q2收入增长20%。'], label='FY2025 Q2')
        if v: cfg['error'] = 'unsupported_period'
    if base == 'T18' and v: cfg['error'] = 'unsupported_period'
    if base == 'T19':
        cfg.update(texts=['Oracle收入增长28%。'], snippets=['Oracle同一期间收入增长30%。'],
                   keywords=['Oracle','收入','28%','30%'], value='28', error='source_region_conflict')
        if v: cfg.update(error=None, grade='disputed')
    if base in ('T22','T23'):
        cfg.update(questions=5 if base == 'T22' else 6)
        if base == 'T23': cfg['error'] = 'total_limit'
    if base == 'T24': cfg['error'] = 'question_set_mismatch'
    if base in ('T25','T40'): cfg['error'] = 'schema'
    if base == 'T27':
        cfg.update(texts=['Oracle公布实际收入增长18%，市场预期20%，公司预计下一季度收入增长22%。'],
                   value='18', error='mixed_temporal_claim')
    if base == 'T28':
        cfg.update(texts=['Oracle公司公布截至2026-09-30收入增长20%。'], end='2026-09-30', temporal='current_actual')
        if v == 'unknown': cfg.update(texts=['Oracle公司公布上一季度收入增长20%。'],end=None,temporal='unknown')
        if v == 'fake': cfg.update(end='2027-09-30', error='unsupported_period')
    if base == 'T30': cfg['error'] = 'duplicate_link'
    if base == 'T31':
        cfg.update(texts=[BASE_TEXT+'\n\n'+BASE_TEXT], error='ambiguous_quote')
        if v: cfg['error'] = None
    if base in ('T32','T36'):
        cfg.update(texts=['Oracle公布FY2025 Q2收入增长20%。\n\n'+'无关背景。'*700+'\n\n未发送的收入增长99%。'],
                   keywords=['Oracle','20%'], error='quote_not_visible')
        if base == 'T36':
            cfg.update(small_budget=True,texts=['Oracle公布FY2025 Q2业绩。\n\n'+'上下文'*4000+'Oracle GPU消费增长336%。'],
                       keywords=['Oracle','FY2025 Q2','GPU','336%'])
        if v == 'gap': cfg.update(error=None, grade=None)
    if base == 'T33': cfg.update(label='FY2027 Q1', texts=['Oracle公布FY2027 Q1收入增长20%。'], error='unsupported_period')
    if base == 'T34': cfg.update(texts=['Oracle CEO Safra Catz said revenue grew 20%.'], metric='revenue', error='claim_support_mismatch')
    if base == 'T35':
        cfg.update(texts=['Oracle收入数据\n\n| 28,499 | 55,663 |\n| 8,502 | 12,033 |'],
                   keywords=['Oracle','28,499'], error='table_context_missing')
        if v: cfg.update(error=None, grade=None)
    if base == 'T38': cfg['error'] = 'unsupported_period'
    if base == 'T39':
        cfg.update(texts=[BASE_TEXT+'\n\n正文描述：'+BASE_TEXT], titles=[BASE_TEXT])
        if v: cfg['error'] = 'unsupported_region'
    return cfg


def citation(source, quote=None, *, field='text', role='claim_support', last=False):
    windows = [w for w in source['visible_windows'] if w['storage_field'] == field and (quote is None or quote in w['text'])]
    if quote is None:
        w = windows[0]
        quote = w['text']
    elif windows:
        w = windows[-1] if last else windows[0]
    else:
        return {'source_id': source['source_id'], 'window_id': 'unseen', 'segment_id': 'unseen',
                'region': 'extracted_body', 'storage_field': field, 'start': 0, 'end': len(quote), 'quote': quote, 'role': role}
    start = w['start']+(w['text'].rindex(quote) if last else w['text'].index(quote))
    return {k:w[k] for k in ('window_id','segment_id','region','storage_field')} | {
        'source_id':source['source_id'], 'start': start, 'end': start+len(quote), 'quote':quote, 'role':role}


def response_for(cfg, payload):
    candidate, _ = setup()
    row = deepcopy(item(candidate)); sources = payload['sources']; first = sources[0]
    base, v = cfg['base'], cfg['variant']
    row['claim'].update(value=cfg.get('value','20'), metric=cfg.get('metric','收入'))
    row['summary'] = '来源陈述，尚待审核'
    row['temporal'].update(event_kind='unknown', proposed_type=cfg['temporal'])
    row['temporal']['period'].update(label_raw=cfg.get('label','unknown'), end=cfg.get('end'))
    field = 'snippet' if base in ('T11','T12') else 'text'
    if cfg['grade'] is None:
        row['links'] = []
    elif base in ('T10',) or base == 'T39' and v:
        row['links'] = [{'source_id':first['source_id'], 'window_id':'unseen-title',
            'segment_id':'unseen-title','region':'title','storage_field':'text','start':0,
            'end':len(BASE_TEXT),'quote':BASE_TEXT,'role':'claim_support'}]
    elif base == 'T16':
        row['links'] = [citation(first,'Oracle GPU消费增长336%。')]
    elif base in ('T32','T36'):
        row['links'] = [citation(first, 'Oracle GPU消费增长336%。' if base=='T36' else '未发送的收入增长99%。')]
        if v == 'splice': row['links'][0]['quote'] = 'Oracle公布FY2025 Q2收入增长20%。未发送的收入增长99%。'
    elif base == 'T14' and v:
        row['links'] = [citation(first,'GPU consumption was up 336%')]
    else:
        row['links'] = [citation(s,cfg.get('quote'),field=field,last=base in ('T31','T39')) for s in sources]
    if cfg.get('label') and row['links'] and base not in ('T10',):
        w = next((w for w in first['visible_windows'] if cfg['label'].casefold() in w['text'].casefold()), None)
        if w: row['temporal']['context_links'] = [citation(first,w['text'],role='period_context')]
    if base == 'T03' and v: row['trusted_assessments'] = [{'reviewer_id':'fixture-reviewer','result':'confirmed_independent'}]
    if base == 'T12':
        if v=='body': row['links'] = [citation(first,'正文不可得。')]
    if base=='T10' and v=='impersonate': row['links'][0]['region']='extracted_body'
    if base=='T11' and v=='bodyregion': row['links'][0]['region']='extracted_body'
    if base == 'T14' and not v:
        row['kind']='unverified'; row['claim']=dict.fromkeys(row['claim'],'unknown')
    if base in ('T17','T18') and v: row['temporal']['period']['label_raw'] = 'FY2099 Q4'
    if base == 'T15' and v: row['temporal']['period']['label_raw'] = 'FY2099 Q4'
    if base in ('T08','T09','T29') and v:
        if v == 'speaker': row['temporal']['speaker_kind']='company'
        else: row['temporal']['proposed_type']='current_actual'
    if base == 'T19' and v:
        row['kind']='disputed';row['links'].append(citation(first,field='snippet'))
    if base == 'T25':
        row[{'category':'category','trust':'trusted_assessment','independence':'independence_verified',
             'verified':'verified','review':'human_review'}.get(v,'final_category')] = 'verified'
    if base == 'T30': row['links'].append(dict(row['links'][0],storage_field='snippet'))
    if base == 'T31':
        row['links'] = [citation(first,BASE_TEXT,last=True)]
        if not v: row['links'][0].update(start=1,end=1+len(BASE_TEXT))
    if base == 'T33': row['temporal']['period'].update(start='2026-07-01',end='2026-09-30')
    if base == 'T34': row['claim']['speaker']='CFO Safra Catz'
    if base == 'T35': row['claim'].update(value='28,499',unit='million USD')
    if base == 'T38': row['temporal']['period']['end']='2024-12-10'
    groups=[]
    for n,q in enumerate(payload['plan']['questions']):
        count=3 if base=='T04' and n==0 else 2 if base in ('T22','T23') else 1
        if base=='T23' and n==5: count=1
        if cfg['grade'] is None: count=0
        items=[]
        for j in range(count):
            r=deepcopy(row); r['candidate_id']=f'{q["id"]}-{j}'
            if base in ('T22','T23') and j: r['kind']='opinion'
            items.append(r)
        groups.append({'question_id':q['id'],'items':items,
                       'gaps': [] if count or base=='T21' else [{'code':'no_support','detail':'该题材料不足'}]})
    if base=='T24':
        if v=='missing': groups=[]
        elif v=='unknown': groups[0]['question_id']='Q9'
        else: groups.append(deepcopy(groups[0]))
    result={'questions':groups}
    if base=='T40': result['contract_version']='research-evidence-v2'
    return result


def create_case(production_store, monkeypatch, code):
    cfg=scenario(code)
    monkeypatch.setattr('services.research.service.utc_now',lambda:'2026-11-03T00:00:00+00:00')
    p=ProjectService(production_store).create(1,'v3真实服务隔离测试')
    search=Mock();search.name='mock';search.available=True;search.usage.return_value=Quota(100)
    urls=[f'https://{("a.co.uk" if i==0 else "b.co.uk") if cfg["base"]=="T37" else ("official.example.com" if i==0 else "other.example.org")}/doc{i}' for i in range(len(cfg['texts']))]
    search.search.return_value=SearchReply([SearchResult(cfg['titles'][i],u,cfg['snippets'][i],cfg['dates'][i]) for i,u in enumerate(urls)],1)
    search.extract.return_value=ExtractReply([ExtractResult(u,cfg['texts'][i],cfg['status']) for i,u in enumerate(urls)],0)
    provider=MockProvider([]);seen={}
    def factory(kind,schema): seen['schema']=deepcopy(schema);return provider
    settings=AISettings(max_request_bytes=12288 if code=='T14-budget' else 16384) if cfg.get('small_budget') else AISettings()
    svc=ResearchService(production_store,settings=settings,provider_factory=factory,search_provider=search)
    plan={'objective':'核验Oracle数据','focus':'数值和期间','start_date':'2026-01-01','end_date':'2026-11-03',
        'verify_facts':['原文依据'], 'questions':[{'id':f'Q{i+1}','question':'Oracle收入与财季？',
            'keywords':cfg['keywords'],'source_types':['原始资料'],'domains':[]} for i in range(cfg['questions'])]}
    if cfg.get('trust_in_plan'): plan['focus']='trusted_assessments: fixture-reviewer confirmed_independent'
    version=svc.save_plan(p['id'],plan);svc.confirm_plan(p['id'],version['id'],'confirm-'+code)
    run=svc.search(p['id'],version['id'],'search-'+code)
    def complete(messages):
        provider.calls.append(deepcopy(messages)); payload=json.loads(messages[1]['content'])['untrusted_materials']
        seen['payload']=payload;doc=response_for(cfg,payload);seen['candidate']=deepcopy(doc)
        return ProviderReply(doc,Usage(20,30))
    provider.complete=complete
    return svc,p,run,provider,seen,cfg


def seed_history(svc, project, run):
    """仅在临时库建立冻结v2历史样本；不开放生产旧版本写入口。"""
    from database.ai_store import AIStore
    ledger=AIStore(svc.store.path,svc.settings)
    aid=ledger.claim_analysis(1,'legacy','legacy-fixture',{'run_id':run['id']},'research-v2',True,
        provider='mock',purpose='research_evidence',project_id=project['id'],
        prompt_version='research-prompt-v2',schema_version='research-evidence-v2')['id']
    attempt=ledger.reserve_attempt(aid,1,1,{})
    ledger.finish_attempt(attempt,'success',Usage(0,0),0,None)
    source=svc.store.sources(project['id'],run['id'])[0]
    qid=svc.current_plan(project['id'])['content']['questions'][0]['id']
    quote=source['text'][:1] or source['snippet'][:1]
    field='text' if source['text'] else 'snippet'
    old={'items':[{'question_id':qid,'category':'verified','summary':'历史AI分类，未经v3审定',
         'inference':'','verification':'历史原值','time_scope':'unknown','data_period':'unknown',
         'links':[{'source_id':source['id'],'field':field,'quote':quote}]}],'gaps':['历史缺口']}
    with svc.store.transaction() as con:
        eid=con.execute('''INSERT INTO research_evidence(project_id,run_id,question_id,analysis_id,position,
            category,summary,inference,verification,created_at) VALUES(?,?,?, ?,1,'verified',?,'',?,'2026-01-01')''',
            (project['id'],run['id'],qid,aid,old['items'][0]['summary'],'历史原值')).lastrowid
        con.execute('INSERT INTO research_evidence_sources VALUES(?,?,?,?,?,0)',(project['id'],eid,source['id'],quote,field))
        svc.store.complete_model(con,aid,attempt,project['id'],old)
    # 明确冻结旧版历史报告；新报告服务不再接收legacy写入契约。
    old_report = {'basis': {'plan_version_id': run['plan_version_id'], 'search_run_id': run['id'],
                           'evidence_analysis_id': aid},
        'document': {'overview': '冻结旧报告', 'objective': '旧报告兼容', 'conclusions': [], 'facts': [],
                     'data': [], 'differences': [], 'unverified': ['旧规则分类'], 'risks': ['历史报告']}}
    with svc.store.transaction() as con:
        oid = svc.store.ensure_object(con, project['id'], 'research', 'report', '2026-01-01')
        svc.store.insert_version(con, project['id'], oid, json.dumps(old_report), 'manual', '历史夹具', '2026-01-01')
    return aid


TABLES=('research_evidence','research_evidence_sources','production_versions','research_sources',
        'research_report_confirmations','research_plan_confirmations','ai_budget_settings','production_projects')


def capture(svc):
    return {t:svc.store.rows('SELECT * FROM '+t+' ORDER BY rowid') for t in TABLES}


def assert_case(svc,p,run,provider,seen,cfg,before,result):
    from services.research.quality import CANDIDATE_SCHEMA
    assert seen['schema']==CANDIDATE_SCHEMA
    assert len(provider.calls)==1
    assert '候选' in provider.calls[0][0]['content'] and 'verified' in provider.calls[0][0]['content']
    operation=svc.store.rows('SELECT * FROM topic_analyses WHERE id=?',(result['analysis_id'],))[0]
    assert operation['schema_version']=='research-evidence-v3'
    assert operation['prompt_version']=='research-evidence-prompt-v3'
    inputs=json.loads(operation['input_json'])
    assert inputs['model_materials']==seen['payload']
    for source in seen['payload']['sources']:
        frozen=inputs['manifest']['sources'][str(source['source_id'])]
        assert 'text' not in source and 'snippet' not in source
        assert source['body_hash']==hashlib.sha256(frozen['text'].encode()).hexdigest()
        assert source['visible_windows']==frozen['visible_windows']
        for w in source['visible_windows']:
            assert frozen[w['storage_field']][w['start']:w['end']]==w['text']
    if cfg['base']=='T10':
        frozen=next(iter(inputs['manifest']['sources'].values()))
        start=cfg['texts'][0].index(BASE_TEXT)
        assert any(r['region']=='title' and r['start']==start and r['end']==start+len(BASE_TEXT) for r in frozen['regions'])
    if cfg['code']=='T14-old682':
        frozen=next(iter(inputs['manifest']['sources'].values()))
        assert len(frozen['text'])==4549 and frozen['snippet']==frozen['text'][:682]
        windows=frozen['visible_windows']
        snippets=[w for w in windows if w['storage_field']=='snippet']
        assert snippets and all(0<=w['start']<w['end']<=682 for w in snippets)
        assert not any(w['storage_field']=='text' and w['start']<=910< w['end'] for w in windows)
        assert not any(w['storage_field']=='text' and w['start']<=1105< w['end'] for w in windows)
    if cfg['base']=='T36':
        assert any(g['code']=='omitted_budget' for g in inputs['manifest']['coverage_gaps'])
        assert inputs['manifest']['selected_utf8_bytes']<=inputs['manifest']['window_budget']
    if cfg['code']=='T14-budget':
        assert any(g['code']=='omitted_budget' for g in inputs['manifest']['coverage_gaps'])
        assert inputs['manifest']['selected_utf8_bytes']<=inputs['manifest']['window_budget']
    if cfg['base']=='T12':
        assert any(g['code']=='body_unavailable' and g['question_id']=='Q1' for g in inputs['manifest']['coverage_gaps'])
    after=capture(svc)
    for table in TABLES:
        assert after[table][:len(before[table])]==before[table], table
        if table not in ('research_evidence','research_evidence_sources','production_projects'):
            assert after[table]==before[table], table
    assert after['production_projects']==before['production_projects']
    rows=svc.store.rows('SELECT * FROM research_evidence WHERE analysis_id=?',(operation['id'],))
    links=svc.store.rows('''SELECT l.* FROM research_evidence_sources l JOIN research_evidence e
                           ON e.id=l.evidence_id WHERE e.analysis_id=?''',(operation['id'],))
    if cfg['error']:
        assert result['status']=='failed',result
        assert operation['status']=='failed' and operation['analysis_json'] is None and operation['success_run_id'] is None
        assert rows==[] and links==[]
        assert after['research_evidence']==before['research_evidence']
        assert after['research_evidence_sources']==before['research_evidence_sources']
        diagnostic=svc.store.diagnostics(p['id'],operation['id'])[0]
        details=json.loads(diagnostic['details_json'])
        assert cfg['error'] in {diagnostic['code']} | {e['code'] for e in details.get('errors',[])}, diagnostic
        assert len((diagnostic['rejected_document_json'] or '').encode())<=16384
        assert 'fixture-reviewer' not in json.dumps(diagnostic)
        assert diagnostic['stage']=='validation'
        assert isinstance(json.loads(diagnostic['path_json']),list)
    else:
        assert result['status']=='success',result
        doc=json.loads(operation['analysis_json'])
        assert doc['candidate_document']==seen['candidate']
        read=svc.store.evidence(p['id'],operation['id'])
        assert len(read)==(0 if cfg['grade'] is None else 10 if cfg['base']=='T22' else 1)
        assert all(r['category']!='verified' for r in read)
        for row in read:
            if cfg['base']!='T22': assert row['category']==cfg['grade']
            assert row['quality']['final_category']==row['category']
            assert row['temporal']['temporal_type']==cfg['temporal']
            for l in row['links']+row['period_context_links']:
                frozen=inputs['manifest']['sources'][str(l['source_id'])]
                assert l['quote']==frozen[l['storage_field']][l['quote_offset']:l['end']]
                assert l['quote_offset']==l['start']
        if cfg['grade'] is None:
            assert any(g['question_id']=='Q1' for g in doc['structured_gaps'])
        if cfg['base'] in ('T02','T20'):
            assert len(read[0]['quality']['origin_group_ids'])==1
            assert read[0]['quality']['independence_status']=='dependent'
            if cfg['base']=='T20':
                a,b=seen['payload']['sources']
                assert a['body_hash']==b['body_hash'] and a['snapshot_hash']!=b['snapshot_hash']
        if cfg['base'] in ('T03','T26','T37'):
            assert read[0]['quality']['independence_status']=='unknown'
        if cfg['base']=='T06':
            t=read[0]['temporal']
            assert (t['fiscal_year'],t['fiscal_quarter'],t['calendar_publication_year'])==(2027,1,2026)
            assert t['event_kind']=='actual_result' and t['current_relation']=='label_only'
            assert t['coverage_start'] is None and t['coverage_end'] is None
        if cfg['base']=='T14':
            visible='\n'.join(w['text'] for s in seen['payload']['sources'] for w in s['visible_windows'])
            assert all(term in visible for term in ('52%','336%','Oracle','GPU consumption',
                       'Cloud Infrastructure','second quarter fiscal 2025','Management’s commentary'))
            assert any(l['quote_offset']>0 for l in links)
        if cfg['base']=='T15':
            assert read[0]['period_context_links'] and read[0]['temporal']['fiscal_year']==2025
            assert read[0]['links'][0]['start']>500
        if cfg['base']=='T17': assert read[0]['temporal']['published_at_raw'] is None
        if cfg['base']=='T18':
            assert read[0]['temporal']['coverage_end'] is None
            assert read[0]['temporal']['fiscal_year'] is None
        if cfg['base']=='T39' or cfg['code']=='T31-valid':
            assert read[0]['links'][0]['quote_offset']>=len(BASE_TEXT)+2
        if cfg['base']=='T37': assert 'registrable_domain_unknown' in read[0]['quality']['unmet_conditions']
    attempt=svc.store.rows('SELECT * FROM ai_analysis_runs WHERE analysis_id=?',(operation['id'],))[0]
    from services.ai.cost_tracker import estimate_units
    assert attempt['input_tokens']==20 and attempt['output_tokens']==30
    assert attempt['estimated_cost_units']==estimate_units(Usage(20,30),svc.settings)>0
    assert attempt['status']==('failed' if cfg['error'] else 'success')
    assert svc.store.rows('PRAGMA foreign_key_check')==[]
    assert svc.store.rows('PRAGMA integrity_check')[0]['integrity_check']=='ok'
    assert svc.store.rows('PRAGMA user_version')[0]['user_version']==6
    if cfg['code'] in ('T06','T14'):
        # 仅公开/合成fixture的验收证据，不导出配置、请求头或正式数据库。
        out=Path(__file__).resolve().parents[1]/'logs/phase4-2-1-4-b-batch2'
        if out.is_dir():
            proof={'case':cfg['code'],'schema_version':operation['schema_version'],
                'prompt_version':operation['prompt_version'],'schema':seen['schema'],
                'messages':provider.calls[0],'manifest':inputs['manifest'],
                'document':json.loads(operation['analysis_json']), 'sql_evidence':rows,'sql_links':links,
                'usage':{'input_tokens':attempt['input_tokens'],'output_tokens':attempt['output_tokens'],
                         'cost_units':attempt['estimated_cost_units']}}
            (out/(cfg['code']+'-service-proof.json')).write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
