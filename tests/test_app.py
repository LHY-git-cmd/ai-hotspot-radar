"""使用 Streamlit 官方 AppTest 验证中文页面和主要交互。"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


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
