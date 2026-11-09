"""4.2.1.1 P0：只使用显式 Mock、临时库及固定时间样本。"""
from tests.research_support import save_report_fixture, confirm_report_fixture


import copy
import json
import sqlite3

import pytest

from tests.test_research_workflow import research, ready, evidence_document, report_document
from services.ai.base import ProviderReply, Usage
from services.research.base import SearchReply, SearchResult, ExtractReply, ExtractResult


def document(source_id):
    doc = evidence_document(source_id)
    doc['items'][0].update(time_scope='unknown', data_period='unknown')
    doc['gaps'] = ['q2: 没有可核实证据']
    return doc


@pytest.mark.parametrize('raw,normalized,precision', [
    ('2024', '2024', 'year'), ('2024-12', '2024-12', 'month'),
    ('2024-12-10', '2024-12-10', 'day'),
    ('2024-12-10T12:30Z', '2024-12-10T12:30Z', 'minute'),
    ('2024-12-10T12:30:45.120+08:00', '2024-12-10T12:30:45.120+08:00', 'fraction'),
    ('Tue, 10 Dec 2024 00:00:00 GMT', '2024-12-10T00:00:00+00:00', 'second'),
    (None, 'unknown', 'unknown'), ('bad date', 'unknown', 'unknown'),
])
def test_date_precision_and_unknown(raw, normalized, precision):
    from services.research.temporal import source_time_context
    context = source_time_context({'published_at': raw, 'searched_at': '2026-11-03T00:00:00+00:00'}, '2026-11-03')
    assert context['published_at_raw'] == raw
    assert context['published_at_normalized'] == normalized
    assert context['date_precision'] == precision
    assert context['date_kind'] == 'provider_estimated_published_or_updated'
    assert context['data_period'] == context['modified_at'] == context['provider_snapshot_at'] == 'unknown'
    if normalized != 'unknown':
        assert context['historical'] and '2024' in context['label'] and '周期' in context['label']


def test_dates_enter_both_stages_and_evidence_has_local_context(research, monkeypatch):
    svc, p, _, provider, search = research
    monkeypatch.setattr('services.research.service.utc_now', lambda: '2026-11-03T00:00:00+00:00')
    raw = 'Tue, 10 Dec 2024 00:00:00 GMT'
    search.search.return_value = SearchReply([SearchResult('旧资料', 'https://example.com/doc', '搜索摘录', raw)], 1)
    _, run = ready(research)
    source = svc.store.sources(p['id'], run['id'])[0]
    provider.replies.append(ProviderReply(document(source['id']), Usage(10, 20)))
    result = svc.organize_evidence(p['id'], run['id'], 'dated-evidence')
    assert result['status'] == 'success', result
    inputs = json.loads(provider.calls[-1][1]['content'])['untrusted_materials']
    assert inputs['sources'][0]['published_at'] == raw
    assert inputs['sources'][0]['published_at'] == raw
    assert inputs['research_context']['as_of'] == '2026-11-03'
    evidence = svc.store.evidence(p['id'], result['analysis_id'])[0]
    assert evidence['links'][0]['time_context']['data_period'] == 'unknown'
    report = report_document(evidence['id'], svc, p['id'])
    provider.replies.append(ProviderReply(report, Usage(10, 20)))
    assert svc.generate_report(p['id'], 'dated-report')['status'] == 'success'
    inputs = json.loads(provider.calls[-1][1]['content'])['untrusted_materials']
    assert inputs['evidence_catalog'][0]['temporal']['published_at_raw'] == raw
    assert inputs['evidence_catalog'][0]['temporal']['temporal_type'] == 'unknown'
    assert svc.store.sources(p['id'], run['id'])[0]['published_at'] == raw
    assert not svc.store.rows('SELECT * FROM research_report_confirmations')


def test_query_cleaning_override_and_version_confirmation(research):
    from services.research.queries import build_query, QUERY_BUILDER_VERSION
    svc, p, plan, _, search = research
    plan = copy.deepcopy(plan)
    plan['questions'][0].update(keywords=['  BBC  News ', 'BBC News', 'AI'], question='很长的完整问题', source_types=['不应拼接'])
    assert build_query(plan['questions'][0]) == 'BBC News AI'
    v = svc.save_plan(p['id'], plan)
    svc.confirm_plan(p['id'], v['id'], 'query-confirm')
    old = svc.search(p['id'], v['id'], 'old-query')
    assert search.search.call_args_list[0].kwargs['query'] == 'BBC News AI'
    edited = copy.deepcopy(plan)
    edited['questions'][0]['query_override'] = 'BBC exact report 2026'
    with pytest.raises(ValueError):
        svc.search(p['id'], v['id'], 'dirty-query', expected_plan=edited)
    newer = svc.save_plan(p['id'], edited)
    with pytest.raises(ValueError): svc.search(p['id'], newer['id'], 'unconfirmed')
    with pytest.raises(ValueError): svc.search(p['id'], v['id'], 'old-query')
    svc.confirm_plan(p['id'], newer['id'], 'new-query-confirm')
    with pytest.raises(ValueError): svc.search(p['id'], newer['id'], 'old-query')
    new = svc.search(p['id'], newer['id'], 'new-query')
    assert new['id'] != old['id']
    calls = [r for r in svc.store.calls(p['id']) if r['run_id'] == new['id'] and r['operation'] == 'search']
    recorded = json.loads(next(r['request_json'] for r in calls if r['question_id'] == 'q1'))
    assert recorded['query'] == build_query(edited['questions'][0]) == 'BBC exact report 2026'
    assert recorded['query_builder_version'] == QUERY_BUILDER_VERSION
    assert json.loads(new['params_json'])['query_builder_version'] == QUERY_BUILDER_VERSION


@pytest.mark.parametrize('changed,expected', [
    ({'text': 'B'}, ['text']), ({'title': 'B'}, ['title']),
    ({'date': '2025-01-01'}, ['published_at']), ({'snippet': 'B'}, ['snippet']),
    ({'failed': True}, ['extraction_failed']),
])
def test_snapshot_dimensions_and_old_reference(research, changed, expected):
    svc, p, _, _, search = research
    search.search.return_value = SearchReply([SearchResult('A', 'https://example.com/doc', 'A', '2024-01-01')], 1)
    search.extract.return_value = ExtractReply([ExtractResult('https://example.com/doc', 'A')], 0)
    v, run = ready(research)
    before = svc.store.sources(p['id'], run['id'])[0]
    search.search.return_value = SearchReply([SearchResult(changed.get('title', 'A'), 'https://example.com/doc',
        changed.get('snippet', 'A'), changed.get('date', '2024-01-01'))], 1)
    search.extract.return_value = ExtractReply([ExtractResult('https://example.com/doc',
        '' if changed.get('failed') else changed.get('text', 'A'), 'failed' if changed.get('failed') else 'success')], 0)
    new = svc.search(p['id'], v['id'], 'changed')
    changes = svc.store.source_changes(p['id'], new['id'])
    assert len(changes) == 1 and changes[0]['changes'] == expected
    assert changes[0]['old_source_id'] == before['id']
    assert changes[0]['new_source_id'] != before['id']
    assert svc.store.sources(p['id'], run['id'])[0] == before
    assert search.extract.call_count == 2


def test_snapshot_a_b_a_uses_previous_run_not_highest_source_id(research):
    svc, p, _, _, search = research
    v, a = ready(research)
    original = svc.store.sources(p['id'], a['id'])[0]
    search.extract.return_value = ExtractReply([ExtractResult(original['url'], 'B')], 0)
    b = svc.search(p['id'], v['id'], 'B')
    middle = svc.store.sources(p['id'], b['id'])[0]
    search.extract.return_value = ExtractReply([ExtractResult(original['url'], original['text'])], 0)
    a2 = svc.search(p['id'], v['id'], 'A-again')
    change = svc.store.source_changes(p['id'], a2['id'])[0]
    assert change['old_source_id'] == middle['id']
    assert change['new_source_id'] == original['id']
    assert change['changes'] == ['text']


@pytest.mark.parametrize('fault,code', [('per_question', 'question_limit'), ('total', 'question_limit'),
    ('missing_gap', 'missing_question_gap'), ('duplicate', 'duplicate_evidence'),
    ('invented_period', 'unsupported_period'), ('current_old', 'temporal_mismatch'),
    ('forecast_actual', 'temporal_mismatch')])
def test_evidence_hard_limits_temporal_and_diagnostics(research, fault, code):
    svc, p, _, provider, search = research
    if fault == 'current_old':
        search.search.return_value = SearchReply([SearchResult('旧资料', 'https://example.com/doc', '搜索摘录', '2024-01-01')], 1)
    if fault == 'forecast_actual':
        search.extract.return_value = ExtractReply([ExtractResult('https://example.com/doc', '公司预计下一季度收入增长50%，仅为预测。')], 0)
    _, run = ready(research)
    source = svc.store.sources(p['id'], run['id'])[0]
    doc = document(source['id'])
    if fault in ('per_question', 'total', 'duplicate'):
        doc['items'] = [dict(copy.deepcopy(doc['items'][0]), summary=f'证据{i}') for i in range(11 if fault == 'total' else 3)]
        if fault == 'duplicate': doc['items'] = [doc['items'][0], copy.deepcopy(doc['items'][0])]
    elif fault == 'missing_gap': doc['gaps'] = ['没有明确对应问题']
    elif fault == 'invented_period': doc['items'][0]['data_period'] = 'FY2026 Q4'
    elif fault == 'current_old': doc['items'][0]['time_scope'] = 'current'
    else:
        doc['items'][0]['time_scope'] = 'current'
        doc['items'][0]['links'][0]['quote'] = '公司预计下一季度收入增长50%'
    provider.replies.append(ProviderReply(doc, Usage(20, 30)))
    result = svc.organize_evidence(p['id'], run['id'], 'invalid-'+fault)
    assert result['status'] == 'failed'
    assert svc.store.evidence(p['id'], result['analysis_id']) == []
    diagnostic = svc.store.diagnostics(p['id'], result['analysis_id'])[0]
    assert diagnostic['stage'] == 'validation' and diagnostic['code'] == code
    assert diagnostic['analysis_id'] == result['analysis_id'] and diagnostic['attempt_run_id']
    attempt = svc.store.rows('SELECT * FROM ai_analysis_runs WHERE id=?', (diagnostic['attempt_run_id'],))[0]
    assert attempt['status'] == 'failed' and attempt['input_tokens'] == 20 and attempt['estimated_cost_units'] > 0


def test_schema_diagnostic_path_and_sensitive_document_redaction(research):
    svc, p, _, provider, _ = research
    _, run = ready(research)
    source = svc.store.sources(p['id'], run['id'])[0]
    doc = document(source['id'])
    doc['items'][0]['summary'] = 'Bearer test-sensitive-token'
    doc['items'][0]['Authorization'] = 'test-sensitive-token'
    doc['items'][0]['links'] = []
    provider.replies.append(ProviderReply(doc, Usage(20, 30)))
    result = svc.organize_evidence(p['id'], run['id'], 'secret-diagnostic')
    diag = svc.store.diagnostics(p['id'], result['analysis_id'])[0]
    assert diag['code'] == 'schema'
    assert json.loads(diag['path_json'])[:4] == ['questions', 0, 'items', 0] and diag['item_index'] == 0
    assert 'test-sensitive-token' not in json.dumps(diag)
    assert 'Authorization' not in json.dumps(diag)
    assert len((diag['rejected_document_json'] or '').encode()) <= 16384
    with svc.store.transaction() as con:
        with pytest.raises(sqlite3.IntegrityError): con.execute('DELETE FROM research_model_diagnostics')


def test_zero_evidence_requires_each_unanswered_question_gap(research):
    svc, p, _, provider, _ = research
    _, run = ready(research)
    provider.replies.append(ProviderReply({'items': [], 'gaps': ['q1: unknown', 'q2: unknown']}, Usage(0, 0)))
    assert svc.organize_evidence(p['id'], run['id'], 'empty')['status'] == 'success'


def test_v5_upgrade_is_additive_idempotent_and_does_not_replay_v5(tmp_path, monkeypatch):
    from tests.test_research_migration import v4_database
    import database.research_migration as v5
    from database.research_store import ResearchStore
    path = tmp_path / 'old-v5.sqlite3'
    v4_database(path)
    with sqlite3.connect(path) as con:
        v5.create_research_tables(con)
        con.execute('PRAGMA user_version=5')
        before = con.execute('SELECT * FROM production_versions').fetchall()
    monkeypatch.setattr(v5, 'create_research_tables', lambda con: pytest.fail('v5 DDL must not run again'))
    ResearchStore(path)
    ResearchStore(path)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 6
        assert con.execute('SELECT * FROM production_versions').fetchall() == before
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name='research_model_diagnostics'").fetchone()
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
    assert len(list(tmp_path.glob('old-v5.pre-v6-*.sqlite3'))) == 1


def test_v6_migration_failure_rolls_back(tmp_path, monkeypatch):
    from tests.test_research_migration import v4_database
    from database.research_migration import create_research_tables
    import database.research_quality_migration as ddl
    from database.research_store import ResearchStore
    path = tmp_path / 'fail-v5.sqlite3'
    v4_database(path)
    with sqlite3.connect(path) as con:
        create_research_tables(con)
        con.execute('PRAGMA user_version=5')
    original = ddl.create_research_quality_tables

    def fail(con):
        original(con)
        raise sqlite3.OperationalError('injected v6 failure')

    monkeypatch.setattr(ddl, 'create_research_quality_tables', fail)
    with pytest.raises(sqlite3.OperationalError): ResearchStore(path)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 5
        assert not con.execute("SELECT 1 FROM sqlite_master WHERE name='research_model_diagnostics'").fetchone()
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name='protect_research_sources_update'").fetchone()
    assert len(list(tmp_path.glob('fail-v5.pre-v6-*.sqlite3'))) == 1


def test_forecast_warning_is_not_rejected_as_actual(research):
    svc, p, _, provider, search = research
    search.extract.return_value = ExtractReply([ExtractResult('https://example.com/doc', '公司预计下一季度收入增长50%')], 0)
    _, run = ready(research)
    source = svc.store.sources(p['id'], run['id'])[0]
    doc = document(source['id'])
    doc['items'][0].update(time_scope='forecast', summary='预测增长50%，并非实际数据')
    doc['items'][0]['links'][0]['quote'] = '公司预计下一季度收入增长50%'
    provider.replies.append(ProviderReply(doc, Usage(10, 10)))
    result = svc.organize_evidence(p['id'], run['id'], 'valid-forecast')
    assert result['status'] == 'success', result
    evidence = svc.store.evidence(p['id'], result['analysis_id'])[0]
    report = report_document(evidence['id'], svc, p['id'])
    saved = save_report_fixture(svc, p['id'], report)
    assert saved['id']
    statement = saved['content']['document']['categories']['unverified'][0]
    assert statement['temporal']['temporal_type'] == 'company_guidance'
    assert statement['temporal']['event_kind'] == 'guidance'


def test_legacy_confirmation_cannot_execute_new_query_builder(research):
    svc, p, plan, _, search = research
    legacy = svc.versions.create(p['id'], 'research', plan, object_key='plan')
    with svc.store.transaction() as con:
        con.execute('''INSERT INTO research_plan_confirmations(project_id,plan_version_id,action_id,confirmed_at)
            VALUES(?,?,?,?)''', (p['id'], legacy['id'], 'legacy-confirmation', '2026-01-01'))
    with pytest.raises(ValueError, match='旧确认'):
        svc.search(p['id'], legacy['id'], 'new-query-with-old-confirmation')
    search.search.assert_not_called()
    assert svc.store.runs(p['id']) == []


def test_ten_evidence_items_across_five_questions_are_valid(research):
    svc, p, plan, provider, _ = research
    plan = copy.deepcopy(plan)
    plan['questions'] = [dict(plan['questions'][0], id=f'q{i}') for i in range(5)]
    v = svc.save_plan(p['id'], plan)
    svc.confirm_plan(p['id'], v['id'], 'ten-confirm')
    run = svc.search(p['id'], v['id'], 'ten-search')
    source = svc.store.sources(p['id'], run['id'])[0]
    doc = document(source['id'])
    doc['items'] = [dict(copy.deepcopy(doc['items'][0]), question_id=f'q{i}', summary=f'不同事实{i}-{j}', category='opinion' if j else 'single_source')
                    for i in range(5) for j in range(2)]
    provider.replies.append(ProviderReply(doc, Usage(10, 10)))
    result = svc.organize_evidence(p['id'], run['id'], 'ten-evidence')
    assert result['status'] == 'success', result
    assert len(svc.store.evidence(p['id'], result['analysis_id'])) == 10


def test_old_report_and_evidence_survive_new_report_and_snapshot(research):
    from tests.test_research_workflow import complete_evidence
    svc, p, _, provider, search = research
    run, evidence = complete_evidence(research)
    operation = svc.store.rows('SELECT * FROM topic_analyses WHERE id=?', (evidence['analysis_id'],))[0]
    legacy_doc = json.loads(operation['analysis_json'])
    for item in legacy_doc['items']:
        item.pop('time_scope'); item.pop('data_period')
    with svc.store.transaction() as con:
        con.execute('UPDATE topic_analyses SET schema_version=?,analysis_json=? WHERE id=?',
            ('research-evidence-v1', json.dumps(legacy_doc), evidence['analysis_id']))
    old_document = report_document(evidence['id'])
    for key in ('conclusions', 'facts', 'data', 'differences'):
        for claim in old_document[key]: claim.pop('time_scope', None)
    with svc.store.transaction() as con:
        oid = svc.store.ensure_object(con,p['id'],'research','report','2026-01-01')
        vid = svc.store.insert_version(con,p['id'],oid,json.dumps({'basis':{},'document':old_document}),
                                       'manual','历史兼容夹具','2026-01-01')
    old = svc.versions.details(p['id'],vid)
    assert svc.generate_report(p['id'], 'new-report-from-old-evidence')['status'] == 'failed'
    assert svc.current_report(p['id']) == old
    assert svc.versions.details(p['id'], old['id'])['content']['document'] == old_document
    source_id = evidence['links'][0]['source_id']
    search.extract.return_value = ExtractReply([ExtractResult('https://example.com/doc', '新版正文')], 0)
    svc.search(p['id'], run['plan_version_id'], 'new-snapshot')
    assert svc.store.evidence(p['id'], evidence['analysis_id'])[0]['links'][0]['source_id'] == source_id
    assert svc.store.sources(p['id'], run['id'])[0]['id'] == source_id
    assert not svc.store.rows('SELECT * FROM research_report_confirmations')


@pytest.mark.parametrize('scope,text', [('current', '2026 年当前增长50%'),
    ('unknown', '目前增长50%')])
def test_report_rejects_historical_as_current_even_manual_edit(research, scope, text):
    svc, p, _, provider, search = research
    search.search.return_value = SearchReply([SearchResult('历史来源', 'https://example.com/doc', '摘录', '2024-01-01')], 1)
    _, run = ready(research)
    source = svc.store.sources(p['id'], run['id'])[0]
    provider.replies.append(ProviderReply(document(source['id']), Usage(10, 10)))
    result = svc.organize_evidence(p['id'], run['id'], 'history-evidence')
    evidence = svc.store.evidence(p['id'], result['analysis_id'])[0]
    report = report_document(evidence['id'], svc, p['id'])
    report['conclusion_blocks'] = [{'block_id':'forged','template_id':'evidence_statement',
        'bindings':[], 'text':text,'time_scope':scope}]
    with pytest.raises(ValueError, match='报告'):
        save_report_fixture(svc, p['id'], report)


def test_diagnostic_storage_failure_does_not_lose_original_fee(research, monkeypatch):
    svc, p, _, provider, _ = research
    _, run = ready(research)
    provider.replies.append(ProviderReply({'items': [{}], 'gaps': []}, Usage(12, 34)))

    def fail(*args): raise sqlite3.OperationalError('injected diagnostic failure')

    monkeypatch.setattr(svc.store, 'save_diagnostic', fail)
    result = svc.organize_evidence(p['id'], run['id'], 'diagnostic-failure')
    assert result['status'] == 'failed'
    attempt = svc.store.rows('SELECT * FROM ai_analysis_runs WHERE analysis_id=?', (result['analysis_id'],))[0]
    assert attempt['error_type'] == 'invalid_schema' and attempt['estimated_cost_units'] > 0
    assert attempt['input_tokens'] == 12 and attempt['output_tokens'] == 34


@pytest.mark.parametrize('choice,code', [
    ({'finish_reason': 'tool_calls', 'message': {'tool_calls': []}}, 'tool_mismatch'),
    ({'finish_reason': 'stop', 'message': {'content': '{}'}}, 'tool_shape'),
    ({'finish_reason': 'tool_calls', 'message': {'tool_calls': [{'function': {'name': 'submit_research_evidence', 'arguments': '{bad'}}]}}, 'json_decode'),
    ({'finish_reason': 'length', 'message': {}}, 'output_truncated'),
])
def test_provider_parse_diagnostics_preserve_usage_without_raw_payload(research, monkeypatch, choice, code):
    from unittest.mock import Mock
    from services.ai.config import AISettings
    svc, p, _, _, _ = research
    _, run = ready(research)
    svc.settings = AISettings(api_key='never-real-test-key', max_attempts=1)
    svc.provider_factory = None
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [choice], 'usage': {'prompt_tokens': 25, 'completion_tokens': 13},
                                'Authorization': 'Bearer unsafe-provider-payload'}
    monkeypatch.setattr('requests.post', Mock(return_value=response))
    result = svc.organize_evidence(p['id'], run['id'], 'parser-'+code)
    assert result['status'] == 'failed'
    diag = svc.store.diagnostics(p['id'], result['analysis_id'])[0]
    assert diag['stage'] == 'provider' and diag['code'] == code
    assert 'unsafe-provider-payload' not in json.dumps(diag)
    attempt = svc.store.rows('SELECT * FROM ai_analysis_runs WHERE id=?', (diag['attempt_run_id'],))[0]
    assert attempt['input_tokens'] == 25 and attempt['estimated_cost_units'] > 0


def test_diagnostic_rejects_cross_project_chain(research):
    from services.production.project_service import ProjectService
    svc, p, _, provider, _ = research
    _, run = ready(research)
    provider.replies.append(ProviderReply({}, Usage(10, 10)))
    result = svc.organize_evidence(p['id'], run['id'], 'diagnostic-chain')
    diag = svc.store.diagnostics(p['id'], result['analysis_id'])[0]
    other = ProjectService(svc.store).create(2, '另一任务')
    columns = [key for key in diag if key != 'id']
    with svc.store.transaction() as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('INSERT INTO research_model_diagnostics('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',
                tuple(other['id'] if key == 'project_id' else diag[key] for key in columns))


def test_diagnostic_size_limit_is_explicit():
    from services.research.diagnostics import rejected_structure
    doc, truncated = rejected_structure({'items': [{'summary': 'secret'}]*1000})
    assert truncated and len(doc.encode()) <= 16384 and 'secret' not in doc


@pytest.mark.parametrize('fault,code', [('unseen', 'quote_not_visible'), ('ambiguous', 'ambiguous_quote'),
    ('cross_question', 'source_association'), ('corrected_duplicate', 'duplicate_link'),
    ('historical_year', 'temporal_mismatch'), ('forecast_prose', 'temporal_mismatch')])
def test_strict_citation_and_temporal_edge_cases(research, fault, code):
    svc, p, _, provider, search = research
    if fault == 'unseen':
        search.extract.return_value = ExtractReply([ExtractResult('https://example.com/doc', '开头'*2000+'不可见尾段')], 0)
    elif fault == 'ambiguous':
        search.search.return_value = SearchReply([SearchResult('资料', f'https://example.com/{i}', '摘录') for i in range(3)], 1)
        search.extract.return_value = ExtractReply([ExtractResult(f'https://example.com/{i}', '唯一正文' if i == 0 else '共同引句') for i in range(3)], 0)
    elif fault == 'cross_question':
        search.search.side_effect = [SearchReply([SearchResult('A', 'https://example.com/a', 'A')], 1),
                                     SearchReply([SearchResult('B', 'https://example.com/b', 'B')], 1)]
        search.extract.return_value = ExtractReply([ExtractResult('https://example.com/a', '支持本地运行'),
                                                    ExtractResult('https://example.com/b', '支持本地运行')], 0)
    elif fault == 'historical_year':
        search.extract.return_value = ExtractReply([ExtractResult('https://example.com/doc', 'Oracle公司公布截至2024-11-30收入增长29%。')], 0)
        search.search.return_value = SearchReply([SearchResult('旧资料', 'https://example.com/doc', '摘录', '2024-01-01')], 1)
    elif fault == 'forecast_prose':
        search.extract.return_value = ExtractReply([ExtractResult('https://example.com/doc', '公司预计下一季度收入增长50%')], 0)
    _, run = ready(research)
    sources = svc.store.sources(p['id'], run['id'])
    doc = document(sources[0]['id'])
    link = doc['items'][0]['links'][0]
    if fault == 'unseen': link['quote'] = '不可见尾段'
    elif fault == 'ambiguous': link['quote'] = '共同引句'
    elif fault == 'cross_question': link['source_id'] = sources[1]['id']
    elif fault == 'corrected_duplicate':
        doc['items'][0]['links'].append(dict(link, field='snippet'))
    elif fault == 'historical_year':
        link['quote'] = 'Oracle公司公布截至2024-11-30收入增长29%。'
        doc['items'][0].update(summary='2026年Oracle收入增长29%', time_scope='current')
    else:
        link['quote'] = '公司预计下一季度收入增长50%'
        doc['items'][0]['summary'] = '实际增长50%'
    provider.replies.append(ProviderReply(doc, Usage(10, 10)))
    result = svc.organize_evidence(p['id'], run['id'], 'strict-'+fault)
    assert result['status'] == 'failed'
    assert svc.store.diagnostics(p['id'], result['analysis_id'])[0]['code'] == code


def test_legacy_report_manual_edit_still_enforces_time(research):
    svc, p, _, provider, search = research
    search.search.return_value = SearchReply([SearchResult('旧资料', 'https://example.com/doc', '搜索摘录', '2024-01-01')], 1)
    _, run = ready(research)
    source = svc.store.sources(p['id'], run['id'])[0]
    provider.replies.append(ProviderReply(document(source['id']), Usage(10, 10)))
    result = svc.organize_evidence(p['id'], run['id'], 'legacy-time')
    evidence = svc.store.evidence(p['id'], result['analysis_id'])[0]
    with svc.store.transaction() as con:
        con.execute("UPDATE topic_analyses SET schema_version='research-evidence-v1' WHERE id=?", (result['analysis_id'],))
    # legacy证据仍可读；任何旧正文新增/编辑都不能成为新v3报告。
    report = report_document(evidence['id'])
    report['conclusions'][0]['text'] = '目前增长29%'
    before = svc.store.rows('SELECT * FROM production_versions')
    with pytest.raises(ValueError):
        save_report_fixture(svc, p['id'], report)
    assert svc.store.rows('SELECT * FROM production_versions') == before
    assert svc.store.evidence(p['id'],result['analysis_id'])[0]['review_status']=='legacy_unreviewed'


def test_populated_v5_migration_preserves_every_existing_table(research, monkeypatch):
    from tests.test_research_workflow import complete_evidence
    from database.research_store import ResearchStore
    import database.research_migration as v5
    svc, p, _, _, _ = research
    _, evidence = complete_evidence(research)
    save_report_fixture(svc, p['id'], report_document(evidence['id'], svc, p['id']))
    with sqlite3.connect(svc.store.path) as con:
        # 临时样本去掉唯一v6表，得到拥有来源/引文/报告/费用的完整v5结构。
        con.execute('DROP TABLE research_model_diagnostics')
        con.execute('PRAGMA user_version=5')
        names = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before = {name: con.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall() for name in names}
        columns = {name: con.execute(f'PRAGMA table_info({name})').fetchall() for name in names}
    monkeypatch.setattr(v5, 'create_research_tables', lambda con: pytest.fail('cannot replay v5'))
    ResearchStore(svc.store.path)
    with sqlite3.connect(svc.store.path) as con:
        for name in names:
            assert con.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall() == before[name]
            assert con.execute(f'PRAGMA table_info({name})').fetchall() == columns[name]
        for sql in ("UPDATE research_sources SET title='changed'", 'DELETE FROM research_evidence'):
            with pytest.raises(sqlite3.IntegrityError): con.execute(sql)
        assert con.execute('PRAGMA user_version').fetchone()[0] == 6
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
