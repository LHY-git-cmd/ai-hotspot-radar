"""验证一个数据源失效时其他数据仍能入库。"""

from unittest.mock import Mock


def test_refresh_isolates_source_failure_and_saves_success(tmp_path):
    """真实临时 SQLite 加模拟采集器，检查成功和失败报告。"""
    from collectors.http import CollectionError
    from database.store import HotspotStore
    from models import CollectionResult, Hotspot
    from services.refresh import refresh_sources
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    item = Hotspot(title='AI discussion', url='https://news.ycombinator.com/item?id=1',
                   source='Hacker News', category='AI 讨论')
    report = refresh_sources(store, {
        'GitHub': Mock(side_effect=CollectionError('GitHub 请求限流')),
        'Hacker News': lambda: CollectionResult([item], ['部分帖子详情不可用']),
    })
    assert report['GitHub'].error == 'GitHub 请求限流'
    assert report['Hacker News'].inserted == 1
    assert report['Hacker News'].warnings == ['部分帖子详情不可用']
    assert store.count() == 1


def test_unexpected_source_failure_does_not_escape(tmp_path):
    """第三方响应引起意外错误也不能使整个刷新崩溃或泄漏异常内容。"""
    from database.store import HotspotStore
    from services.refresh import refresh_sources
    report = refresh_sources(HotspotStore(tmp_path / 'radar.sqlite3'), {
        'GitHub': Mock(side_effect=RuntimeError('test-secret')),
    })
    assert report['GitHub'].error
    assert 'test-secret' not in report['GitHub'].error
