"""AI 中文页面验收；使用 Mock Provider，任何真实 HTTP 调用都会失败。"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


def prepare(tmp_path, monkeypatch, ai_document):
    """仅在临时库准备候选与模型响应。"""
    from database.store import HotspotStore
    from models import Hotspot
    from services.recalculate import recalculate_scores
    from services.ai.base import ProviderReply, Usage
    from services.ai.mock import MockProvider
    path = tmp_path / 'page.sqlite3'
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(path))
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-only-secret')
    monkeypatch.setattr('requests.post', Mock(side_effect=AssertionError('真实 API 不应调用')))
    now = datetime.now(timezone.utc).isoformat()
    store = HotspotStore(path)
    store.save([Hotspot(title='AI tool', summary='A coding tool demo', source='GitHub', source_key='1',
                       url='https://example.com/tool', category='AI 开源项目', score=100,
                       collected_at=now, published_at=now, pushed_at=now)], cycle_id='one', source='GitHub')
    recalculate_scores(store)
    provider = MockProvider([ProviderReply(ai_document, Usage(100, 200)), ProviderReply(ai_document, Usage(100, 200))])
    monkeypatch.setattr('ai_page.DeepSeekProvider', lambda settings: provider)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.sidebar.radio[0].set_value('AI 选题分析').run()
    return app, store, provider


def test_page_render_selection_and_budget_save_do_not_call_provider(tmp_path, monkeypatch, ai_document):
    app, store, provider = prepare(tmp_path, monkeypatch, ai_document)
    assert not app.exception and not provider.calls
    app.selectbox(key='ai_hotspot').select(1).run()
    app.run()
    # 表单输入应与提交按钮一次发送，不能模拟成提交前先触发整个脚本重跑。
    app.text_input(key='ai_budget_input').set_value('50')
    app.button(key='ai_budget_save').click().run()
    assert not app.exception and not provider.calls
    assert any('50.000000' in metric.value for metric in app.metric)
    assert all('test-only-secret' not in message.value for message in app.caption)


def test_single_confirm_cached_force_and_idea_status(tmp_path, monkeypatch, ai_document):
    app, store, provider = prepare(tmp_path, monkeypatch, ai_document)
    assert app.button(key='ai_analyze').disabled
    app.checkbox(key='ai_single_confirm').check().run()
    app.button(key='ai_analyze').click().run()
    assert not app.exception and len(provider.calls) == 1
    assert app.metric[1].value == '0.001800'
    assert any('测试选题' in heading.value for heading in app.subheader)
    app.button(key='idea_1_favorite').click().run()
    assert not app.exception and len(provider.calls) == 1
    from database.ai_store import AIStore
    from services.ai.config import AISettings
    assert AIStore(store.path, AISettings()).ideas()[0]['status'] == 'favorite'
    app.button(key='ai_analyze').click().run()
    assert len(provider.calls) == 1
    app.checkbox(key='ai_force').check().run()
    assert app.button(key='ai_analyze').disabled
    app.checkbox(key='ai_single_confirm').check().run()
    app.button(key='ai_analyze').click().run()
    assert len(provider.calls) == 2
    app.button(key='ai_analyze').click().run()
    assert len(provider.calls) == 2
    assert len(AIStore(store.path, AISettings()).analyses(1)) == 2


def test_batch_requires_confirmation_and_no_key_keeps_old_system_working(tmp_path, monkeypatch, ai_document):
    app, store, provider = prepare(tmp_path, monkeypatch, ai_document)
    assert app.button(key='ai_batch').disabled
    app.checkbox(key='ai_batch_confirm').check().run()
    app.button(key='ai_batch').click().run()
    assert not app.exception and len(provider.calls) == 1
    monkeypatch.delenv('DEEPSEEK_API_KEY')
    app.run()
    assert not app.exception
    assert app.button(key='ai_analyze').disabled
    assert any('密钥' in message.value for message in app.warning)
    app.sidebar.radio[0].set_value('热点排行').run()
    assert not app.exception and app.title[0].value == 'AI 热点雷达'
    assert len(provider.calls) == 1
