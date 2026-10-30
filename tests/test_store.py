"""验证实际 SQLite 的持久化、唯一约束、更新与搜索行为。"""

import sqlite3


def make_item(**changes):
    """创建仅供测试使用的记录；不会写入应用的真实数据库。"""
    from models import Hotspot
    values = dict(title='AI Tool', url='https://example.com/tool', source='GitHub',
                  summary=None, published_at=None, collected_at='2026-01-01T00:00:00+00:00',
                  score=10, category='AI 开源项目')
    return Hotspot(**(values | changes))


def test_persistence_and_duplicate_updates(tmp_path):
    """URL 变体更新指标但不改变首次采集时间，重开数据库仍有记录。"""
    from database.store import HotspotStore
    path = tmp_path / 'radar.sqlite3'
    store = HotspotStore(path)
    assert store.save([make_item()]).inserted == 1
    result = store.save([make_item(url='https://EXAMPLE.com:443/tool?utm_source=x#readme',
                                  score=25, collected_at='2026-01-02T00:00:00+00:00')])
    assert result.updated == 1
    reopened = HotspotStore(path)
    assert reopened.count() == 1
    row = reopened.search()[0]
    assert row['score'] == 25
    assert row['collected_at'] == '2026-01-01T00:00:00+00:00'
    assert row['summary'] is None and row['published_at'] is None


def test_title_duplicates_and_cross_source_metrics(tmp_path):
    """重复标题或跨来源同一链接保留首条记录及其指标语义。"""
    from database.store import HotspotStore
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    store.save([make_item()])
    result = store.save([
        make_item(title=' ＡＩ  TOOL ', url='https://other.com/a'),
        make_item(title='Another title', source='Hacker News', score=999),
    ])
    assert result.skipped == 2
    assert store.count() == 1
    assert store.search()[0]['score'] == 10
    assert store.search()[0]['source'] == 'GitHub'


def test_conflicting_url_and_title_do_not_merge_rows(tmp_path):
    """一次更新同时命中两条记录时跳过，不能错误覆盖或破坏事务。"""
    from database.store import HotspotStore
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    store.save([make_item(), make_item(title='Other', url='https://example.com/other')])
    result = store.save([make_item(title='Other', score=99)])
    assert result.skipped == 1
    assert store.count() == 2
    assert store.search(query='AI Tool')[0]['score'] == 10


def test_literal_search_source_filter_and_pagination(tmp_path):
    """搜索参数安全绑定，百分号按字面匹配，并支持筛选和分页。"""
    from database.store import HotspotStore
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    store.save([make_item(title='AI 100% Tool', summary='中文摘要'),
                make_item(title='Claude', url='https://example.com/2', source='Hacker News')])
    assert store.count(query='%') == 1
    assert store.count(query="' OR 1=1 --") == 0
    assert store.count(query='中文') == 1
    assert store.count(query='ａｉ') == 1
    assert store.count(source='Hacker News') == 1
    assert len(store.search(limit=1, offset=1)) == 1


def test_database_has_unique_constraints(tmp_path):
    """数据库本身阻止重复写入，不能只依靠应用内存去重。"""
    from database.store import HotspotStore
    path = tmp_path / 'radar.sqlite3'
    HotspotStore(path).save([make_item()])
    with sqlite3.connect(path) as connection:
        indexes = connection.execute('PRAGMA index_list(hotspots)').fetchall()
    assert sum(index[2] == 1 for index in indexes) >= 2
