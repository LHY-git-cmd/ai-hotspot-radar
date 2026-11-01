"""使用 Streamlit 官方 AppTest 验证中文页面和主要交互。"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


@pytest.mark.parametrize('page', ['热点排行', 'AI 选题分析'])
def test_database_version_error_is_visible_without_traceback(tmp_path, monkeypatch, page):
    """真正不兼容的数据库仍拒绝打开，两页都显示版本原因而非崩溃或权限误报。"""
    import sqlite3
    from database.store import HotspotStore
    path = tmp_path / 'future-version.sqlite3'
    HotspotStore(path)
    with sqlite3.connect(path) as connection:
        connection.execute('PRAGMA user_version=99')
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(path))
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    if page != '热点排行':
        app.sidebar.radio[0].set_value(page).run()
    assert not app.exception
    assert any('99' in message.value and '版本' in message.value for message in app.error)
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 99


@pytest.mark.parametrize('legacy', [True, False], ids=['legacy-report', 'current-report'])
def test_cached_refresh_report_survives_schema_change(tmp_path, monkeypatch, legacy):
    """模拟升级前的会话对象无 snapshots；新版仍展示真实数量，筛选后不崩溃。"""
    from models import SourceReport
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(tmp_path / 'cached-report.sqlite3'))

    def unexpected_request(*args, **kwargs):
        """展示旧报告不应通过联网刷新来修复。"""
        raise AssertionError('展示已有报告不应请求网络')

    monkeypatch.setattr('requests.get', unexpected_request)
    values = dict(fetched=2, inserted=1, updated=1, skipped=0,
                  error=None, warnings=['已保留的采集警告'])
    # 使用确实没有字段的旧结构；删除新版实例字段仍会读到 dataclass 类默认值。
    report = SimpleNamespace(**values) if legacy else SourceReport(**values, snapshots=3)
    app = AppTest.from_file(str(APP))
    app.session_state['refresh_reports'] = {'GitHub': report}
    app.session_state['refresh_time'] = '2026-10-31T00:00:00+00:00'
    app.run()
    assert not app.exception
    assert any('快照暂无' in message.value if legacy else '快照 3 条' in message.value
               for message in app.success)
    assert any('获取 2 条，新增 1 条，更新 1 条，去重跳过 0 条' in message.value
               for message in app.success)
    assert any('已保留的采集警告' in message.value for message in app.warning)
    app.text_input[0].set_value('AI').run()
    assert not app.exception


def test_empty_page_never_collects_automatically(tmp_path, monkeypatch):
    """首次进入只读本地数据，用户点击刷新前不得请求外网。"""
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(tmp_path / 'empty.sqlite3'))

    def unexpected_request(*args, **kwargs):
        """自动联网会使测试立即失败。"""
        raise AssertionError('页面不应自动请求网络')

    monkeypatch.setattr('requests.get', unexpected_request)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.title[0].value == 'AI 热点雷达'
    assert app.button[0].label == '手动刷新'
    assert any('暂无数据' in message.value for message in app.info)


def test_search_filter_links_and_missing_fields(tmp_path, monkeypatch):
    """使用临时数据检查标题、空值、原始链接及搜索筛选。"""
    from database.store import HotspotStore
    from models import Hotspot
    path = tmp_path / 'ui.sqlite3'
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(path))
    HotspotStore(path).save([
        Hotspot(title='Alpha AI', url='https://example.com/alpha', source='GitHub',
                score=42, category='AI 开源项目'),
        Hotspot(title='Beta LLM', url='https://example.com/beta', source='Hacker News',
                category='AI 讨论'),
    ])
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert {heading.value for heading in app.subheader} == {'Alpha AI', 'Beta LLM'}
    urls = {button.proto.url for button in app.get('link_button')}
    assert urls == {'https://example.com/alpha', 'https://example.com/beta'}
    assert any('暂无' in caption.value for caption in app.caption)
    app.text_input[0].set_value('alpha').run()
    assert [heading.value for heading in app.subheader] == ['Alpha AI']
    app.selectbox[0].select('Hacker News').run()
    assert not app.subheader
    app.text_input[0].set_value('').run()
    assert [heading.value for heading in app.subheader] == ['Beta LLM']
    assert not app.exception


def test_manual_refresh_displays_failure_and_new_data(tmp_path, monkeypatch):
    """点击刷新后展示新记录，来源错误不会中断页面。"""
    from models import Hotspot, SourceReport
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(tmp_path / 'refresh.sqlite3'))

    def fake_refresh(store, collectors):
        """替代网络刷新，仅验证界面与刷新服务的连接。"""
        store.save([Hotspot(title='Fresh AI', url='https://example.com/fresh',
                            source='Hacker News', category='AI 讨论')])
        return {'GitHub': SourceReport(error='GitHub 请求限流，请稍后重试'),
                'Hacker News': SourceReport(fetched=1, inserted=1)}

    monkeypatch.setattr('services.refresh.refresh_sources', fake_refresh)
    app = AppTest.from_file(str(APP)).run()
    app.button[0].click().run()
    assert not app.exception
    assert any('限流' in message.value for message in app.error)
    assert [heading.value for heading in app.subheader] == ['Fresh AI']


def test_database_error_has_clear_message(tmp_path, monkeypatch):
    """不可用数据库路径得到明确错误提示。"""
    path = tmp_path / 'not-a-directory'
    path.write_text('occupied', encoding='utf-8')
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(path / 'radar.sqlite3'))
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert any('数据库' in message.value for message in app.error)
