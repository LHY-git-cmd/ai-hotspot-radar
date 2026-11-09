"""第四阶段制作基础设施 DDL；调用方管理备份和事务。"""

import sqlite3


def create_production_tables(connection: sqlite3.Connection) -> None:
    """仅追加结构，不预填尚未生成的内容，不使用隐式提交的 executescript。"""
    statements = [
        '''CREATE TABLE production_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL CHECK(length(trim(name))>0),
            idea_id INTEGER NOT NULL REFERENCES video_ideas(id),
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN
                ('pending','researching','scripting','storyboarding','assets','editing','completed','paused','archived')),
            notes TEXT NOT NULL DEFAULT '', resume_status TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            CHECK((status='paused' AND resume_status IS NOT NULL AND resume_status IN
                ('pending','researching','scripting','storyboarding','assets','editing','completed'))
                OR (status<>'paused' AND resume_status IS NULL))
        )''',
        "CREATE UNIQUE INDEX idx_production_active_idea ON production_projects(idea_id) WHERE status<>'archived'",
        'CREATE INDEX idx_production_idea_history ON production_projects(idea_id,id)',
        'CREATE INDEX idx_production_status ON production_projects(status,updated_at,id)',
        '''CREATE TABLE production_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES production_projects(id),
            action_type TEXT NOT NULL CHECK(action_type IN
                ('created','updated','status_changed','paused','resumed','archived','version_created','version_restored')),
            previous_status TEXT, new_status TEXT NOT NULL,
            created_at TEXT NOT NULL, details_json TEXT NOT NULL CHECK(json_valid(details_json))
        )''',
        'CREATE INDEX idx_production_action_history ON production_actions(project_id,created_at,id)',
        '''CREATE TABLE production_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES production_projects(id),
            content_type TEXT NOT NULL CHECK(content_type IN ('research','script','storyboard','asset','editing_guide')),
            object_key TEXT NOT NULL CHECK(length(trim(object_key))>0),
            created_at TEXT NOT NULL,
            UNIQUE(project_id,content_type,object_key), UNIQUE(id,project_id)
        )''',
        '''CREATE TABLE production_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES production_projects(id),
            object_id INTEGER NOT NULL,
            version_number INTEGER NOT NULL CHECK(version_number>0),
            content_json TEXT NOT NULL CHECK(json_valid(content_json)),
            source TEXT NOT NULL CHECK(source IN ('ai','manual','restore')),
            note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            restored_from_version_id INTEGER,
            UNIQUE(object_id,version_number), UNIQUE(object_id,id),
            FOREIGN KEY(object_id,project_id) REFERENCES production_objects(id,project_id),
            FOREIGN KEY(object_id,restored_from_version_id) REFERENCES production_versions(object_id,id),
            CHECK((source='restore' AND restored_from_version_id IS NOT NULL)
                OR (source<>'restore' AND restored_from_version_id IS NULL))
        )''',
        'CREATE INDEX idx_production_version_project ON production_versions(project_id,object_id,version_number)',
    ]
    for statement in statements:
        connection.execute(statement)
    # 完整历史采用追加语义，即使误用 SQL 也不能重写/删除版本和审计。
    for table in ('production_versions', 'production_actions'):
        for operation in ('UPDATE', 'DELETE'):
            connection.execute(f'''CREATE TRIGGER protect_{table}_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT, 'production history is append-only'); END''')
