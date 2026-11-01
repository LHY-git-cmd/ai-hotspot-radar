"""第二期网页测试：排行、分类、依据、历史和手动重算的交互。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from database.store import HotspotStore
from models import Hotspot
from services.recalculate import recalculate_scores

APP = Path(__file__).resolve().parents[1] / 'app.py'


def prepared(tmp_path, monkeypatch, *, with_scores=True):
    """创建两条模拟热点以及其中一条的两日真实结构快照。"""
    path = tmp_path / 'ui.sqlite3'
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(path))
    store = HotspotStore(path)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for day, score in [(1, 100), (0, 200)]:
        store.save([Hotspot(title='AI coding tool demo CLI tutorial', source='GitHub',
            url='https://example.com/coder', category='AI 开源项目', source_key='1',
            collected_at=(now - timedelta(days=day)).isoformat(), score=score,
            forks=0, published_at=now.isoformat(), pushed_at=now.isoformat())],
            cycle_id=f'day-{day}', source='GitHub')
    store.save([Hotspot(title='AI discussion', source='Hacker News',
        url='https://example.com/discussion', category='AI 讨论', source_key='2',
        collected_at=now.isoformat(), score=0, comments=None, published_at=now.isoformat())],
        cycle_id='day-0', source='Hacker News')
    if with_scores:
        assert recalculate_scores(store, now=now)['error'] is None
    return store


def test_rankings_details_history_category_and_sort(tmp_path, monkeypatch):
    """网页展示双评分、低置信、真实历史，分类与排序可以交互。"""
    prepared(tmp_path, monkeypatch)
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception
    assert any('综合' in caption.value for caption in app.caption)
    assert any('趋势数据不足' in caption.value for caption in app.caption)
    assert len(app.get('dataframe')) >= 4
    labels = [widget.label for widget in app.selectbox]
    assert labels == ['来源筛选', '类别筛选', '排序方式']
    app.selectbox[1].select('AI 编程').run()
    assert [heading.value for heading in app.subheader] == ['AI coding tool demo CLI tutorial']
    app.selectbox[2].select('近期增长分').run()
    assert not app.exception
    assert any('日均' in caption.value for caption in app.caption)
    urls = {button.proto.url for button in app.get('link_button')}
    assert urls == {'https://example.com/coder'}


def test_recompute_button_is_offline_and_does_not_add_history(tmp_path, monkeypatch):
    """旧记录待计算；点击重新评分只更新结果，筛选与重跑不反复计算。"""
    store = prepared(tmp_path, monkeypatch, with_scores=False)
    monkeypatch.setattr('requests.get', Mock(side_effect=AssertionError('不应联网')))
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception
    assert any('待计算' in caption.value for caption in app.caption)
    app.button[1].click().run()
    assert not app.exception
    assert any('评分已更新' in success.value for success in app.success)
    assert all(row['rating'] for row in store.ranked_items())
    assert len(store.history(1)) == 2
    monkeypatch.setattr('services.recalculate.recalculate_scores', Mock(side_effect=AssertionError('不应重复评分')))
    app.text_input[0].set_value('coding').run()
    assert not app.exception


def test_score_error_has_visible_message_and_preserves_data(tmp_path, monkeypatch):
    """评分失败后页面继续展示旧结果，并提示旧分过期。"""
    store = prepared(tmp_path, monkeypatch)
    monkeypatch.setattr('services.recalculate.score_hotspot', Mock(side_effect=RuntimeError('test-secret')))
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    app.button[1].click().run()
    assert not app.exception
    assert any('评分' in message.value for message in app.error)
    assert any('过期' in message.value for message in app.warning)
    assert len(store.history(1)) == 2
    assert all('test-secret' not in message.value for message in app.error)


def test_page_refresh_persists_real_structure_snapshots_and_scores(tmp_path, monkeypatch):
    """页面按钮连接实际服务；只替代 API 采集器，验证全流程落库。"""
    from models import CollectionResult
    path = tmp_path / 'refresh.sqlite3'
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(path))
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr('collectors.github.collect', lambda **kw: CollectionResult([
        Hotspot(title='Fresh AI tool', url='https://example.com/fresh', source='GitHub',
                source_key='101', category='AI 开源项目', score=0, pushed_at=now)]))
    monkeypatch.setattr('collectors.hacker_news.collect', lambda: CollectionResult())
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    app.button[0].click().run()
    assert not app.exception
    store = HotspotStore(path)
    assert len(store.history(1)) == 1
    assert store.ranked_items()[0]['rating']['heat_score'] is not None
    assert any('快照 1' in message.value for message in app.success)
