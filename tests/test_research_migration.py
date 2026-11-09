"""v4→v5 迁移含完整制作历史，验证备份、回滚及幂等。"""

import sqlite3

import pytest

from tests.test_production_store import legacy_v3


def v4_database(path):
    from database.production_migration import create_production_tables
    legacy_v3(path)
    with sqlite3.connect(path) as con:
        create_production_tables(con)
        con.execute("""INSERT INTO topic_analyses(id,hotspot_id,cache_key,action_id,provider,model,prompt_version,
            schema_version,analysis_version,output_mode,input_json,status,created_at)
            VALUES(1,7,'cache','action','mock','test','v1','v1','v1','strict','{}','success','old')""")
        con.execute("""INSERT INTO video_ideas(id,analysis_id,position,angle_type,title,hook,outline_json,target_audience,
            materials_json,verification_json,difficulty,recommendation_reason,idea_json,created_at,updated_at)
            VALUES(1,1,1,'test','历史选题','hook','[]','test','[]','[]','中','test','{}','old','old')""")
        con.execute("INSERT INTO production_projects(id,name,idea_id,status,notes,created_at,updated_at) VALUES(1,'历史制作',1,'pending','保留备注','old','old')")
        con.execute("INSERT INTO production_actions(project_id,action_type,new_status,created_at,details_json) VALUES(1,'created','pending','old','{}')")
        con.execute("INSERT INTO production_objects(id,project_id,content_type,object_key,created_at) VALUES(1,1,'research','main','old')")
        con.execute("INSERT INTO production_versions(project_id,object_id,version_number,content_json,source,note,created_at) VALUES(1,1,1,'\"旧完整正文\"','manual','原版','old')")
        con.execute('PRAGMA user_version=4')


def test_v4_migration_preserves_all_legacy_columns_and_history(tmp_path):
    from database.research_store import ResearchStore
    path = tmp_path / 'v4.sqlite3'
    v4_database(path)
    with sqlite3.connect(path) as con:
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before = {name: (con.execute(f'PRAGMA table_info({name})').fetchall(),
                         con.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall()) for name in names}
    ResearchStore(path)
    with sqlite3.connect(path) as con:
        for name, (columns, rows) in before.items():
            fields = ','.join('"'+column[1]+'"' for column in columns)
            assert con.execute(f'SELECT {fields} FROM {name} ORDER BY rowid').fetchall() == rows
        assert con.execute("SELECT purpose,production_project_id,result_version_id FROM topic_analyses").fetchall() == [('topic', None, None)]
        assert con.execute('PRAGMA user_version').fetchone()[0] == 6
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
        for sql in ('UPDATE production_versions SET note=\'改写\'', 'DELETE FROM production_actions'):
            with pytest.raises(sqlite3.IntegrityError): con.execute(sql)
    backups = list(tmp_path.glob('v4.pre-v6-*.sqlite3'))
    assert len(backups) == 1
    ResearchStore(path)
    assert list(tmp_path.glob('v4.pre-v6-*.sqlite3')) == backups
    with sqlite3.connect(backups[0]) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 4
        assert con.execute('SELECT content_json FROM production_versions').fetchone()[0] == '"旧完整正文"'


def test_v5_ddl_failure_rolls_back_added_columns_and_tables(tmp_path, monkeypatch):
    import database.research_migration as ddl
    from database.research_store import ResearchStore
    path = tmp_path / 'failure-v4.sqlite3'
    v4_database(path)
    original = ddl.create_research_tables

    def fail(con):
        original(con)
        raise sqlite3.OperationalError('injected v5 DDL failure')

    monkeypatch.setattr(ddl, 'create_research_tables', fail)
    with pytest.raises(sqlite3.OperationalError): ResearchStore(path)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 4
        assert 'purpose' not in [r[1] for r in con.execute('PRAGMA table_info(topic_analyses)')]
        assert not con.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'research_%'").fetchall()
        assert con.execute('SELECT COUNT(*) FROM production_versions').fetchone()[0] == 1
    assert len(list(tmp_path.glob('failure-v4.pre-v6-*.sqlite3'))) == 1


def test_confirmations_reject_cross_project_versions_and_sources_are_immutable(production_store):
    from services.production.project_service import ProjectService
    from database.research_store import ResearchStore
    from tests.research_support import approve_research
    p = ProjectService(production_store).create(1, '任务一')
    other = ProjectService(production_store).create(2, '任务二')
    svc = approve_research(production_store, p['id'])
    version = svc.current_plan(p['id'])
    with production_store._connection() as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO research_plan_confirmations(project_id,plan_version_id,action_id,confirmed_at) VALUES(?,?, 'bad','now')", (other['id'], version['id']))
        for sql in ('UPDATE research_sources SET text=\'伪造\'', 'DELETE FROM research_evidence', 'DELETE FROM research_plan_confirmations'):
            with pytest.raises(sqlite3.IntegrityError): con.execute(sql)
