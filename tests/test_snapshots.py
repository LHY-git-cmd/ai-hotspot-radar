"""第二期数据测试：使用临时库检验迁移、快照、幂等及来源隔离。"""

import sqlite3
from dataclasses import replace

import pytest

from models import Hotspot
from database.store import HotspotStore


def item(**changes):
    """构造带稳定 API ID 的测试记录，不写入真实数据库。"""
    return Hotspot(**(dict(title='AI coder', url='https://example.com/coder', source='GitHub',
                          category='AI 开源项目', source_key='101', score=0,
                          collected_at='2026-01-01T00:00:00+00:00') | changes))


def save(store, items, cycle='cycle-1', source='GitHub'):
    """一次来源任务对应一个刷新周期。"""
    return store.save(items, cycle_id=cycle, source=source)


def test_old_database_migrates_once_without_inventing_history(tmp_path):
    """用真实一期 DDL 建库，确认自动备份及迁移保留字段、主键和唯一约束。"""
    # 独立固定一期结构，测试不依赖 Git 安装或当前提交历史。
    ddl = '''CREATE TABLE hotspots (
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
        source TEXT NOT NULL CHECK(source IN ('GitHub', 'Hacker News')),
        summary TEXT, published_at TEXT, collected_at TEXT NOT NULL,
        score INTEGER CHECK(score IS NULL OR score >= 0), category TEXT NOT NULL,
        normalized_url TEXT NOT NULL UNIQUE, normalized_title TEXT NOT NULL UNIQUE,
        search_text TEXT NOT NULL
    )'''
    path = tmp_path / 'old.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute(ddl)
        connection.execute('''INSERT INTO hotspots VALUES
            (7, 'Old', 'https://example.com/old', 'GitHub', NULL, NULL,
             '2025-01-01T00:00:00+00:00', 9, 'AI 开源项目', 'old-url', 'old-title', 'old')''')
    store = HotspotStore(path)
    assert store.search()[0]['id'] == 7
    assert store.search()[0]['score'] == 9
    assert store.history(7) == []
    backups = list(tmp_path.glob('old.pre-v*-*.sqlite3'))
    assert len(backups) == 1
    HotspotStore(path)
    assert list(tmp_path.glob('old.pre-v*-*.sqlite3')) == backups
    with sqlite3.connect(path) as connection:
        from database.migrations import SCHEMA_VERSION
        assert connection.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
        assert sum(row[2] for row in connection.execute('PRAGMA index_list(hotspots)')) >= 2
    with sqlite3.connect(backups[0]) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 0
        assert connection.execute('SELECT id FROM hotspots').fetchone()[0] == 7


def test_new_hotspot_zero_missing_and_cycle_idempotence(tmp_path):
    """新纪录有快照；同周期不重复或覆盖，新周期保留零和缺失的区别。"""
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    first = item(forks=0)
    assert save(store, [first]).inserted == 1
    save(store, [replace(first, score=99)])
    assert store.count() == 1
    assert store.history(1)[0]['stars'] == 0
    assert store.search()[0]['score'] == 0
    assert len(store.history(1)) == 1
    save(store, [replace(first, score=None, collected_at='2026-01-02T00:00:00+00:00')], 'cycle-2')
    assert [row['stars'] for row in store.history(1)] == [0, None]
    assert store.history(1)[0]['hn_score'] is None
    assert store.history(1)[0]['forks'] == 0
    assert store.collection_run('cycle-1', 'GitHub')['status'] == 'success'


def test_cross_source_and_different_hn_posts_do_not_overwrite_primary(tmp_path):
    """相同外链可包含独立来源和帖子序列，排行榜主对象保持稳定。"""
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    save(store, [item(score=10)])
    save(store, [item(title='Show HN', source='Hacker News', source_key='201', score=2, comments=0)],
         source='Hacker News')
    save(store, [item(title='Another post', source='Hacker News', source_key='202', score=500)],
         'cycle-2', 'Hacker News')
    assert store.count() == 1
    assert store.search()[0]['score'] == 10
    history = store.history(1)
    assert len(history) == 3
    assert {(row['source'], row['source_key']) for row in history} == {
        ('GitHub', '101'), ('Hacker News', '201'), ('Hacker News', '202')}
    assert history[1]['comments'] == 0
    assert store.scoring_inputs()[0]['primary_source_key'] == '101'


def test_stable_identity_survives_rename_but_title_collision_is_skipped(tmp_path):
    """官方 ID 不变时更新原热点；不同链接的标题碰撞不得串用快照。"""
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    save(store, [item()])
    save(store, [item(title='Renamed', url='https://example.com/renamed', score=10)], 'cycle-2')
    assert store.count() == 1
    assert len(store.history(1)) == 2
    report = save(store, [item(title='Renamed', source_key='999', url='https://other.com/')], 'cycle-3')
    assert report.skipped == 1
    assert len(store.history(1)) == 2


def test_failed_transaction_leaves_no_hotspots_or_snapshots(tmp_path):
    """部分数据无效时整批回滚，不能留下没有对应记录的快照。"""
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    with pytest.raises(ValueError):
        save(store, [item(), item(title='', source_key='102', url='https://example.com/bad')])
    assert store.count() == 0
    assert store.collection_run('cycle-1', 'GitHub') is None


def test_source_mismatch_and_future_database_version_are_rejected(tmp_path):
    """不能将错误来源的数据写入任务，或静默打开未知新版数据库。"""
    path = tmp_path / 'radar.sqlite3'
    store = HotspotStore(path)
    with pytest.raises(ValueError):
        save(store, [item(source='Hacker News')])
    assert store.count() == 0
    with sqlite3.connect(path) as connection:
        connection.execute('PRAGMA user_version=99')
    with pytest.raises(ValueError, match='版本'):
        HotspotStore(path)
