"""可备份、可重入的 SQLite 增量迁移，保留前两期全部数据。"""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4

SCHEMA_VERSION = 3


def migrate(connection: sqlite3.Connection, path: Path, *, backup_existing: bool) -> None:
    """迁移前保存一致备份，v0→v2→v3 在同一事务完成。"""
    version = connection.execute('PRAGMA user_version').fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ValueError(f'数据库版本为 {version}，当前程序支持至 {SCHEMA_VERSION}。'
                         '如刚升级，请停止旧 Streamlit 服务并从项目虚拟环境重新启动；'
                         '否则请使用兼容版本程序。')
    if version == SCHEMA_VERSION:
        return
    if version not in (0, 2):
        raise ValueError('不支持的数据库版本，未执行迁移')
    if backup_existing:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup_path = path.with_name(f'{path.stem}.pre-v3-{stamp}-{uuid4().hex[:8]}.sqlite3')
        with sqlite3.connect(backup_path) as destination:
            connection.backup(destination)
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        current = connection.execute('PRAGMA user_version').fetchone()[0]
        if current == SCHEMA_VERSION:
            return
        if current not in (0, 2):
            raise ValueError('迁移期间数据库版本发生变化')
        if current == 0:
            _upgrade_v2(connection)
        from database.ai_migration import create_ai_tables
        create_ai_tables(connection)
        connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')


def _upgrade_v2(connection: sqlite3.Connection) -> None:
    """原第二期 DDL：只加主来源标识、快照、任务和确定性评分表。"""
    connection.execute('ALTER TABLE hotspots ADD COLUMN primary_source_key TEXT')
    connection.execute('CREATE UNIQUE INDEX idx_hotspots_identity ON hotspots(source, primary_source_key)')
    connection.execute('''CREATE TABLE collection_runs (
        cycle_id TEXT NOT NULL, source TEXT NOT NULL,
        started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('success', 'partial', 'failed')),
        fetched INTEGER NOT NULL DEFAULT 0, inserted INTEGER NOT NULL DEFAULT 0,
        updated INTEGER NOT NULL DEFAULT 0, skipped INTEGER NOT NULL DEFAULT 0,
        snapshots INTEGER NOT NULL DEFAULT 0, warnings TEXT NOT NULL DEFAULT '[]', error TEXT,
        PRIMARY KEY(cycle_id, source)
    )''')
    connection.execute('''CREATE TABLE hotspot_snapshots (
        id INTEGER PRIMARY KEY, hotspot_id INTEGER NOT NULL REFERENCES hotspots(id),
        cycle_id TEXT NOT NULL, source TEXT NOT NULL CHECK(source IN ('GitHub', 'Hacker News')),
        source_key TEXT NOT NULL, collected_at TEXT NOT NULL, url TEXT NOT NULL,
        stars INTEGER CHECK(stars IS NULL OR stars >= 0),
        forks INTEGER CHECK(forks IS NULL OR forks >= 0),
        hn_score INTEGER CHECK(hn_score IS NULL OR hn_score >= 0),
        comments INTEGER CHECK(comments IS NULL OR comments >= 0),
        published_at TEXT, pushed_at TEXT,
        UNIQUE(cycle_id, hotspot_id, source, source_key),
        FOREIGN KEY(cycle_id, source) REFERENCES collection_runs(cycle_id, source)
            DEFERRABLE INITIALLY DEFERRED
    )''')
    connection.execute('CREATE INDEX idx_snapshots_series ON hotspot_snapshots(hotspot_id, source, source_key, collected_at)')
    connection.execute('''CREATE TABLE hotspot_scores (
        hotspot_id INTEGER PRIMARY KEY REFERENCES hotspots(id),
        heat_score REAL, video_score REAL, composite_score REAL,
        calculated_at TEXT NOT NULL, rule_version TEXT NOT NULL,
        details TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0
    )''')
