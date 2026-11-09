"""制作结构、迁移、备份及历史数据保护；全部使用临时 SQLite。"""

import sqlite3

import pytest


def legacy_v3(path):
    from database.ai_migration import create_ai_tables
    from database.migrations import _upgrade_v2
    with sqlite3.connect(path) as con:
        con.execute('''CREATE TABLE hotspots (
            id INTEGER PRIMARY KEY,title TEXT NOT NULL,url TEXT NOT NULL,source TEXT NOT NULL,
            summary TEXT,published_at TEXT,collected_at TEXT NOT NULL,score INTEGER,category TEXT NOT NULL,
            normalized_url TEXT NOT NULL UNIQUE,normalized_title TEXT NOT NULL UNIQUE,search_text TEXT NOT NULL)''')
        _upgrade_v2(con)
        create_ai_tables(con)
        con.execute("INSERT INTO hotspots VALUES(7,'历史','https://e.com','GitHub',NULL,NULL,'old',3,'AI','u','t','s',NULL)")
        con.execute('PRAGMA user_version=3')


def test_initialization_has_four_tables_no_budget_or_content(tmp_path):
    from database.production_store import ProductionStore
    store = ProductionStore(tmp_path / 'new.sqlite3')
    assert store.projects() == [] and store.ideas() == []
    with store._connection() as con:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'production_%'")}
        assert tables == {'production_projects', 'production_actions', 'production_objects', 'production_versions'}
        assert con.execute('PRAGMA user_version').fetchone()[0] == 6
        assert con.execute('SELECT COUNT(*) FROM ai_budget_settings').fetchone()[0] == 0
        assert not con.execute('PRAGMA foreign_key_check').fetchall()


def test_v3_upgrade_keeps_all_old_rows_and_backup(tmp_path):
    from database.production_store import ProductionStore
    path = tmp_path / 'old.sqlite3'
    legacy_v3(path)
    with sqlite3.connect(path) as con:
        before = con.execute('SELECT * FROM hotspots').fetchall()
    store = ProductionStore(path)
    backups = list(tmp_path.glob('old.pre-v6-*.sqlite3'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 3
        assert con.execute('SELECT * FROM hotspots').fetchall() == before
    with store._connection() as con:
        assert [tuple(r) for r in con.execute('SELECT * FROM hotspots')] == before
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    ProductionStore(path)
    assert list(tmp_path.glob('old.pre-v6-*.sqlite3')) == backups


def test_v4_ddl_failure_rolls_back_and_keeps_backup(tmp_path, monkeypatch):
    import database.production_migration as ddl
    from database.production_store import ProductionStore
    path = tmp_path / 'failure.sqlite3'
    legacy_v3(path)
    original = ddl.create_production_tables

    def fail(con):
        original(con)
        raise sqlite3.OperationalError('injected')

    monkeypatch.setattr(ddl, 'create_production_tables', fail)
    with pytest.raises(sqlite3.OperationalError):
        ProductionStore(path)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 3
        assert con.execute('SELECT id FROM hotspots').fetchone()[0] == 7
        assert not con.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'production_%'").fetchall()
    assert len(list(tmp_path.glob('failure.pre-v6-*.sqlite3'))) == 1


def test_backup_failure_prevents_schema_change(tmp_path, monkeypatch):
    import database.migrations as migrations
    from database.production_store import ProductionStore
    path = tmp_path / 'backup.sqlite3'
    legacy_v3(path)

    def fail(*args):
        raise OSError('injected backup error')

    monkeypatch.setattr(migrations, '_backup_database', fail)
    with pytest.raises(OSError):
        ProductionStore(path)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 3
        assert not con.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'production_%'").fetchall()


def test_foreign_keys_and_duplicate_active_constraint(production_store):
    from services.production.project_service import ProjectService
    store = production_store
    project = ProjectService(store).create(1, '制作')
    with store._connection() as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO production_projects(name,idea_id,status,notes,created_at,updated_at) VALUES('bad',999,'pending','','t','t')")
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO production_projects(name,idea_id,status,notes,created_at,updated_at) VALUES('duplicate',1,'pending','','t','t')")
        assert con.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    assert store.get_project(project['id'])['idea_id'] == 1


def test_v3_upgrade_preserves_analysis_ideas_costs_budget_and_all_tables(tmp_path, monkeypatch, ai_document):
    """使用明确 v3 DDL 和现有第三期写入接口准备旧库，逐字段核对全部旧表。"""
    import database.migrations as migrations
    from database.ai_store import AIStore
    from database.production_store import ProductionStore
    from models import Hotspot
    from services.ai.base import Usage
    from services.ai.config import AISettings
    path = tmp_path / 'complete-v3.sqlite3'
    legacy_v3(path)
    # 此上下文只用于构造测试旧库，不让当前存储初始化提前升级到 v4。
    with monkeypatch.context() as patch:
        patch.setattr(migrations, 'migrate', lambda *args, **kwargs: None)
        old = AIStore(path, AISettings())
        old.save([Hotspot(title='快照测试', url='https://example.com/snapshot', source='GitHub',
            category='AI', source_key='99', score=10)], cycle_id='v3-cycle', source='GitHub')
        # 用固定旧字段准备 v3 数据，不让当前 AIStore 的新增用途字段影响旧库夹具。
        import json
        with sqlite3.connect(path) as con:
            con.execute("""INSERT INTO topic_analyses(id,hotspot_id,cache_key,action_id,provider,model,prompt_version,
                schema_version,analysis_version,output_mode,input_json,analysis_json,status,created_at)
                VALUES(1,7,'old-cache','old-action','mock','old','old','old','old','strict','{}',?,'success','old')""",
                (json.dumps(ai_document,ensure_ascii=False),))
            con.execute("""INSERT INTO ai_analysis_runs(id,analysis_id,attempt,provider,model,prompt_version,schema_version,
                output_mode,price_version,price_json,reserved_units,estimated_cost_units,status,budget_month,created_at)
                VALUES(1,1,1,'mock','old','old','old','strict','old','{}',1000,100,'success','2026-11','old')""")
            idea=ai_document['video_ideas'][0]
            con.execute("""INSERT INTO video_ideas(id,analysis_id,position,angle_type,title,hook,outline_json,target_audience,
                materials_json,verification_json,difficulty,recommendation_reason,idea_json,status,created_at,updated_at)
                VALUES(1,1,1,?,?,?,'[]',?,'[]','[]',?,?,?,'favorite','old','old')""",
                (idea['angle_type'],idea['title'],idea['hook'],idea['target_audience'],idea['difficulty'],
                 idea['recommendation_reason'],json.dumps(idea,ensure_ascii=False)))
            con.execute("INSERT INTO idea_actions(idea_id,action,previous_status,created_at) VALUES(1,'favorite','new','old')")

    with sqlite3.connect(path) as con:
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        before = {name: con.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall() for name in names}
        columns = {name: con.execute(f'PRAGMA table_info({name})').fetchall() for name in names}
    ProductionStore(path)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 6
        for name in names:
            projection = ','.join('\"'+column[1]+'\"' for column in columns[name])
            assert con.execute(f'SELECT {projection} FROM {name} ORDER BY rowid').fetchall() == before[name]
            assert con.execute(f'PRAGMA table_info({name})').fetchall()[:len(columns[name])] == columns[name]
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
    with sqlite3.connect(next(tmp_path.glob('complete-v3.pre-v6-*.sqlite3'))) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 3
        for name in names:
            assert con.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall() == before[name]


def test_database_rejects_inconsistent_pause_state(production_store):
    from services.production.project_service import ProjectService
    project = ProjectService(production_store).create(1, '任务')
    with production_store._connection() as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE production_projects SET status='paused' WHERE id=?", (project['id'],))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE production_projects SET resume_status='researching' WHERE id=?", (project['id'],))
