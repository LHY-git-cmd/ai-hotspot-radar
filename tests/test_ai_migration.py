"""第三期迁移验收：旧版本保留、备份、事务回滚与新库支持。"""

import sqlite3
from types import ModuleType

import pytest


def test_cached_store_uses_current_migration_after_hot_reload(tmp_path, monkeypatch):
    """模拟 Streamlit 替换迁移模块后，存储模块还持有旧 from-import 函数。"""
    import database.store as storage
    path = tmp_path / 'hot-reload.sqlite3'
    storage.HotspotStore(path)
    legacy = ModuleType('legacy_migration')
    exec('''
SCHEMA_VERSION = 2
def migrate(connection, path, *, backup_existing):
    version = connection.execute('PRAGMA user_version').fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ValueError('数据库版本高于当前程序支持的版本，请使用对应版本程序')
''', legacy.__dict__)
    # sys.modules 中已是新迁移模块，但旧存储类的全局函数别名仍可能存活。
    monkeypatch.setattr(storage, 'migrate', legacy.migrate, raising=False)
    reopened = storage.HotspotStore(path)
    assert reopened.count() == 0
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 6


def test_latest_schema_is_v6_and_v2_rows_survive(tmp_path):
    """从明确的二期结构升级，不能修改评分或补造 AI 分析。"""
    from database.migrations import SCHEMA_VERSION, _upgrade_v2
    from database.store import HotspotStore
    assert SCHEMA_VERSION == 6
    path = tmp_path / 'v2.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute('''CREATE TABLE hotspots (
            id INTEGER PRIMARY KEY,title TEXT NOT NULL,url TEXT NOT NULL,source TEXT NOT NULL,
            summary TEXT,published_at TEXT,collected_at TEXT NOT NULL,score INTEGER,category TEXT NOT NULL,
            normalized_url TEXT NOT NULL UNIQUE,normalized_title TEXT NOT NULL UNIQUE,search_text TEXT NOT NULL)''')
        _upgrade_v2(connection)
        connection.execute('PRAGMA user_version=2')
        connection.execute("INSERT INTO hotspots(id,title,url,source,collected_at,category,normalized_url,normalized_title,search_text) VALUES(1,'Original','https://e.com','GitHub','2026-01-01','AI','url','title','text')")
        before = connection.execute('SELECT * FROM hotspots').fetchall()
    store = HotspotStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 6
        assert connection.execute('SELECT * FROM hotspots').fetchall() == before
        assert connection.execute('SELECT COUNT(*) FROM topic_analyses').fetchone()[0] == 0
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
    backups = list(tmp_path.glob('v2.pre-v6-*.sqlite3'))
    assert len(backups) == 1
    HotspotStore(path)
    assert list(tmp_path.glob('v2.pre-v6-*.sqlite3')) == backups


def test_ddl_failure_rolls_back_v3_and_keeps_backup(tmp_path, monkeypatch):
    """在建表途中注入故障，旧版本和表结构应完整恢复。"""
    import database.ai_migration as migration
    from database.migrations import migrate, _upgrade_v2
    path = tmp_path / 'failure.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE hotspots(id INTEGER PRIMARY KEY,source TEXT)')
        _upgrade_v2(connection)
        connection.execute('PRAGMA user_version=2')
    actual = migration.create_ai_tables

    def fail_midway(connection):
        """创建真实第三期表后故意失败，验证 DDL 没有隐式提交。"""
        actual(connection)
        raise sqlite3.OperationalError('injected migration failure')

    monkeypatch.setattr(migration, 'create_ai_tables', fail_midway)
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.OperationalError):
            migrate(connection, path, backup_existing=True)
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
        assert not connection.execute("SELECT 1 FROM sqlite_master WHERE name='topic_analyses'").fetchone()
    assert list(tmp_path.glob('failure.pre-v6-*.sqlite3'))
