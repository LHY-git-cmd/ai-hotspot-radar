"""工作台交互和零网络验收；不会操作真实数据库。"""

from pathlib import Path
from unittest.mock import Mock
import sqlite3

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


def open_app(path, monkeypatch):
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(path))
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    monkeypatch.setattr('requests.get', Mock(side_effect=AssertionError('工作台禁止网络 GET')))
    monkeypatch.setattr('requests.post', Mock(side_effect=AssertionError('工作台禁止网络 POST')))
    monkeypatch.setattr('services.ai.deepseek_client.DeepSeekProvider.complete',
                        Mock(side_effect=AssertionError('工作台禁止 Provider 调用')))
    app = AppTest.from_file(str(APP), default_timeout=25).run()
    app.sidebar.radio[0].set_value('视频制作工作台').run()
    assert not app.exception
    return app


def old_data(store):
    names = ('hotspots', 'collection_runs', 'hotspot_snapshots', 'hotspot_scores', 'topic_analyses',
             'video_ideas', 'idea_actions', 'ai_analysis_runs', 'ai_budget_settings')
    with sqlite3.connect(store.path) as con:
        return {name: con.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall() for name in names}


def test_empty_workbench_does_not_initialize_budget(tmp_path, monkeypatch):
    path = tmp_path / 'empty.sqlite3'
    app = open_app(path, monkeypatch)
    assert app.title[0].value == '视频制作工作台'
    assert any('暂无视频选题' in m.value for m in app.info)
    with sqlite3.connect(path) as con:
        assert con.execute('SELECT COUNT(*) FROM ai_budget_settings').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM ai_analysis_runs').fetchone()[0] == 0


def test_project_lifecycle_page_preserves_old_data(production_store, monkeypatch):
    store = production_store
    before = old_data(store)
    app = open_app(store.path, monkeypatch)
    app.selectbox(key='production_idea').select(1)
    app.text_input(key='production_name').set_value('首个视频')
    app.button(key='production_create').click().run()
    assert not app.exception and len(store.projects()) == 1
    project_id = store.projects()[0]['id']
    app.text_input(key=f'production_edit_name_{project_id}').set_value('修改标题')
    app.text_area(key=f'production_notes_{project_id}').set_value('制作备注')
    app.button(key=f'production_save_{project_id}').click().run()
    assert store.get_project(project_id)['name'] == '修改标题'
    app.selectbox(key=f'production_status_{project_id}').select('researching')
    app.button(key=f'production_status_save_{project_id}').click().run()
    app.button(key=f'production_pause_{project_id}').click().run()
    assert store.get_project(project_id)['status'] == 'paused'
    app.button(key=f'production_resume_{project_id}').click().run()
    assert store.get_project(project_id)['status'] == 'researching'
    assert app.button(key=f'production_archive_{project_id}').disabled
    app.checkbox(key=f'production_archive_confirm_{project_id}').check().run()
    app.button(key=f'production_archive_{project_id}').click().run()
    assert not app.exception and store.projects() == []
    assert store.get_project(project_id)['status'] == 'archived'
    assert app.button(key=f'production_save_{project_id}').disabled
    app.button(key='production_back').click().run()
    app.selectbox(key='production_archive_filter').select('归档历史').run()
    app.button(key='production_open').click().run()
    assert not app.exception and any('人工管理状态' in m.value for m in app.caption)
    assert len(store.actions(project_id)) == 6
    assert old_data(store) == before
    app.sidebar.radio[0].set_value('热点排行').run()
    assert not app.exception and app.title[0].value == 'AI 热点雷达'
    app.sidebar.radio[0].set_value('AI 选题分析').run()
    assert not app.exception and app.title[0].value == 'AI 选题分析'


def test_page_versions_restore_and_five_placeholders(production_store, monkeypatch):
    from services.production.project_service import ProjectService
    from services.production.version_service import VersionService
    store = production_store
    p = ProjectService(store).create(1, '历史版本任务')
    from tests.research_support import approve_research
    approve_research(store, p['id'])
    versions = VersionService(store)
    first = versions.create(p['id'], 'script', {'全文': ['原始正文']})
    versions.create(p['id'], 'script', '修订正文')
    before = old_data(store)
    app = open_app(store.path, monkeypatch)
    app.button(key='production_open').click().run()
    app.selectbox(key=f'production_object_{p["id"]}').select(first['object_id']).run()
    app.selectbox(key=f'production_version_{p["id"]}').select(first['id']).run()
    assert app.button(key=f'production_restore_{p["id"]}').disabled
    app.checkbox(key=f'production_restore_confirm_{p["id"]}').check().run()
    app.button(key=f'production_restore_{p["id"]}').click().run()
    assert not app.exception
    history = versions.history(p['id'], 'script')
    assert len(history) == 3 and history[0]['content'] == first['content']
    assert history[0]['source'] == 'restore'
    assert sum('尚未开发' in m.value for m in app.info) == 4
    assert old_data(store) == before


def test_duplicate_name_validation_and_list_details(production_store, monkeypatch):
    app = open_app(production_store.path, monkeypatch)
    app.button(key='production_create').click().run()
    assert not app.exception and any('名称不能为空' in m.value for m in app.error)
    assert production_store.projects() == []
    app.text_input(key='production_name').set_value('有效任务')
    app.button(key='production_create').click().run()
    assert not app.exception and len(production_store.projects()) == 1
    app.button(key='production_back').click().run()
    app.button(key='production_open').click().run()
    assert not app.exception
    assert any('操作历史' == e.label for e in app.expander)


def test_services_do_not_call_ai_or_modify_budget(production_store, monkeypatch):
    from services.production.project_service import ProjectService
    from services.production.version_service import VersionService
    from services.ai.deepseek_client import DeepSeekProvider
    import requests
    for target in ('requests.get', 'requests.post', 'services.ai.deepseek_client.DeepSeekProvider.complete'):
        monkeypatch.setattr(target, Mock(side_effect=AssertionError('禁止非预期调用')))
    before = old_data(production_store)
    projects, versions = ProjectService(production_store), VersionService(production_store)
    p = projects.create(1, '离线任务')
    projects.edit(p['id'], '离线修改', '备注')
    projects.set_status(p['id'], 'researching')
    projects.pause(p['id'])
    projects.resume(p['id'])
    v = versions.create(p['id'], 'research', {'来源': '人工录入'}, source='ai')
    versions.restore(p['id'], v['id'], object_id=v['object_id'])
    projects.archive(p['id'])
    assert old_data(production_store) == before
    requests.get.assert_not_called()
    requests.post.assert_not_called()
    DeepSeekProvider.complete.assert_not_called()


def test_direct_page_entry_has_same_navigation_and_no_ai(production_store, monkeypatch):
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(production_store.path))
    monkeypatch.setattr('requests.post', Mock(side_effect=AssertionError('禁止调用 AI')))
    page = AppTest.from_file(str(APP.parent / 'pages' / 'production.py'), default_timeout=25).run()
    assert not page.exception and page.title[0].value == '视频制作工作台'
    assert page.sidebar.radio[0].value == '视频制作工作台'
    page.sidebar.radio[0].set_value('热点排行').run()
    assert not page.exception and page.title[0].value == 'AI 热点雷达'


def test_future_database_version_is_reported_on_workbench(tmp_path, monkeypatch):
    from database.production_store import ProductionStore
    path = tmp_path / 'future.sqlite3'
    ProductionStore(path)
    with sqlite3.connect(path) as con:
        con.execute('PRAGMA user_version=99')
    app = open_app(path, monkeypatch)
    assert any('99' in error.value and '版本' in error.value for error in app.error)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 99
