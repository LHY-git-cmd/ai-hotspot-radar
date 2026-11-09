"""四区研究页面与确认操作；页面重跑不得调用 API。"""
from tests.research_support import save_report_fixture, confirm_report_fixture


from pathlib import Path
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from tests.test_research_workflow import research, ready, complete_evidence, report_document

APP = Path(__file__).resolve().parents[1] / 'app.py'


def open_research(research, monkeypatch):
    svc, p, _, provider, search = research
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(svc.store.path))
    monkeypatch.setattr('requests.sessions.Session.request', Mock(side_effect=AssertionError('禁止真实网络')))
    monkeypatch.setattr('pages.research.ResearchService', lambda store: svc)
    app = AppTest.from_file(str(APP), default_timeout=25).run()
    app.sidebar.radio[0].set_value('视频制作工作台').run()
    app.button(key='production_open').click().run()
    assert not app.exception
    return app


def test_page_plan_edit_confirm_search_and_refresh(research, monkeypatch):
    svc, p, plan, provider, search = research
    saved = svc.save_plan(p['id'], plan)
    app = open_research(research, monkeypatch)
    assert not any(b.key == f'research_search_{p["id"]}' for b in app.button)
    app.button(key=f'research_plan_confirm_{p["id"]}').click().run()
    assert not app.exception and svc.plan_is_confirmed(p['id'])
    app.button(key=f'research_search_{p["id"]}').click().run()
    assert not app.exception and search.search.call_count == 2
    app.run()
    app.run()
    assert search.search.call_count == 2 and not provider.calls
    app.text_area(key=f'research_focus_{p["id"]}_{saved["id"]}').set_value('修改研究重点').run()
    assert not any(b.key == f'research_search_{p["id"]}' for b in app.button)
    app.button(key=f'research_plan_save_{p["id"]}').click().run()
    assert not app.exception and not svc.plan_is_confirmed(p['id'])


def test_page_report_edit_confirm_and_navigation_are_local(research, monkeypatch):
    svc, p, _, provider, search = research
    _, evidence = complete_evidence(research)
    report = save_report_fixture(svc, p['id'], report_document(evidence['id'], svc, p['id']))
    calls = len(provider.calls)
    app = open_research(research, monkeypatch)
    import json
    edited = report['content']['candidate_document']
    edited['question_sections'].reverse()
    app.text_area(key=f'research_report_structure_{p["id"]}_{report["id"]}').set_value(json.dumps(edited)).run()
    app.button(key=f'research_report_save_{p["id"]}').click().run()
    app.checkbox(key=f'research_report_review_{p["id"]}_{svc.current_report(p["id"])["id"]}').check().run()
    app.button(key=f'research_report_confirm_{p["id"]}').click().run()
    assert not app.exception and len(provider.calls) == calls
    assert svc.current_report(p['id'])['content']['candidate_document'] == edited
    assert svc.reports().state(p['id'])['current_report_state'] == 'confirmed'
    assert sum('尚未开发' in info.value for info in app.info) == 4
    app.sidebar.radio[0].set_value('热点排行').run()
    app.sidebar.radio[0].set_value('视频制作工作台').run()
    assert not app.exception and len(provider.calls) == calls and search.search.call_count == 2


def test_final_query_preview_edit_save_confirm_matches_actual_call(research, monkeypatch):
    svc, p, plan, _, search = research
    saved = svc.save_plan(p['id'], plan)
    app = open_research(research, monkeypatch)
    assert any(code.value == '测试 能力' for code in app.code)
    app.button(key=f'research_plan_confirm_{p["id"]}').click().run()
    app.text_input(key=f'research_q_{p["id"]}_{saved["id"]}_0_q1_query').set_value('BBC report 2026').run()
    assert any(code.value == 'BBC report 2026' for code in app.code)
    assert not any(b.key == f'research_search_{p["id"]}' for b in app.button)
    search.search.assert_not_called()
    app.button(key=f'research_plan_save_{p["id"]}').click().run()
    newer = svc.current_plan(p['id'])
    assert newer['id'] != saved['id'] and not svc.plan_is_confirmed(p['id'])
    app.button(key=f'research_plan_confirm_{p["id"]}').click().run()
    app.button(key=f'research_search_{p["id"]}').click().run()
    assert not app.exception
    assert search.search.call_args_list[0].kwargs['query'] == 'BBC report 2026'
    app.run()
    assert search.search.call_count == 2


def test_history_time_labels_are_attached_to_evidence_and_report(research, monkeypatch):
    from services.research.base import SearchReply, SearchResult
    svc, p, _, provider, search = research
    search.search.return_value = SearchReply([SearchResult('历史来源', 'https://example.com/doc', '搜索摘录', '2024-12-10')], 1)
    _, evidence = complete_evidence(research)
    save_report_fixture(svc, p['id'], report_document(evidence['id'], svc, p['id']))
    calls = len(provider.calls)
    app = open_research(research, monkeypatch)
    linked = [caption.value for caption in app.caption if f'E{evidence["id"]} → S' in caption.value]
    assert linked and any('extracted_body' in label for label in linked)
    assert any('2024' in label and '历史材料' in label for label in linked)
    assert any('unknown' in caption.value for caption in app.caption)
    # 发布年代不被旧页面启发式误当成数据覆盖期间。
    assert svc.current_report(p['id'])['content']['document']['categories']['unverified'][0]['temporal']['published_at_raw']=='2024-12-10'
    assert not app.exception and len(provider.calls) == calls
