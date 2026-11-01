"""第三期新增表的事务 DDL，供版本迁移及旧库副本演练共用。"""

import sqlite3


def create_ai_tables(connection: sqlite3.Connection) -> None:
    """调用者管理事务；不修改前两期表，不使用会隐式提交的 executescript。"""
    statements = [
        '''CREATE TABLE topic_analyses (
            id INTEGER PRIMARY KEY, hotspot_id INTEGER NOT NULL REFERENCES hotspots(id),
            cache_key TEXT NOT NULL, action_id TEXT NOT NULL UNIQUE,
            provider TEXT NOT NULL, model TEXT NOT NULL, prompt_version TEXT NOT NULL,
            schema_version TEXT NOT NULL, analysis_version TEXT NOT NULL, output_mode TEXT NOT NULL,
            input_json TEXT NOT NULL, analysis_json TEXT, summary TEXT, evidence_status TEXT,
            status TEXT NOT NULL CHECK(status IN ('running','success','failed','uncertain')),
            error_type TEXT, success_run_id INTEGER REFERENCES ai_analysis_runs(id),
            created_at TEXT NOT NULL, completed_at TEXT
        )''',
        "CREATE UNIQUE INDEX idx_ai_active_material ON topic_analyses(cache_key) WHERE status IN ('running','uncertain')",
        'CREATE INDEX idx_ai_analysis_history ON topic_analyses(hotspot_id, created_at)',
        '''CREATE TABLE ai_analysis_runs (
            id INTEGER PRIMARY KEY, analysis_id INTEGER NOT NULL REFERENCES topic_analyses(id),
            attempt INTEGER NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
            prompt_version TEXT NOT NULL, schema_version TEXT NOT NULL, output_mode TEXT NOT NULL,
            response_model TEXT, price_version TEXT NOT NULL, price_json TEXT NOT NULL,
            input_tokens INTEGER, output_tokens INTEGER, cache_hit_tokens INTEGER, cache_miss_tokens INTEGER,
            estimated_cost_units INTEGER CHECK(estimated_cost_units IS NULL OR estimated_cost_units>=0),
            reserved_units INTEGER NOT NULL CHECK(reserved_units>=0),
            manual_cost_units INTEGER CHECK(manual_cost_units IS NULL OR manual_cost_units>=0),
            resolution_reason TEXT, resolved_at TEXT,
            status TEXT NOT NULL CHECK(status IN ('pending','success','failed')),
            error_type TEXT, budget_month TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT,
            UNIQUE(analysis_id, attempt)
        )''',
        'CREATE INDEX idx_ai_runs_month ON ai_analysis_runs(budget_month)',
        '''CREATE TABLE video_ideas (
            id INTEGER PRIMARY KEY, analysis_id INTEGER NOT NULL REFERENCES topic_analyses(id),
            position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 3),
            angle_type TEXT NOT NULL, title TEXT NOT NULL, hook TEXT NOT NULL,
            outline_json TEXT NOT NULL, target_audience TEXT NOT NULL, materials_json TEXT NOT NULL,
            verification_json TEXT NOT NULL, difficulty TEXT NOT NULL, recommendation_reason TEXT NOT NULL,
            idea_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','favorite','discarded','selected','to_produce')),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(analysis_id, position)
        )''',
        'CREATE INDEX idx_ideas_status ON video_ideas(status)',
        '''CREATE TABLE idea_actions (
            id INTEGER PRIMARY KEY, idea_id INTEGER NOT NULL REFERENCES video_ideas(id),
            action TEXT NOT NULL, previous_status TEXT NOT NULL, created_at TEXT NOT NULL
        )''',
        '''CREATE TABLE ai_budget_settings (
            id INTEGER PRIMARY KEY CHECK(id=1), limit_units INTEGER NOT NULL CHECK(limit_units>=0),
            updated_at TEXT NOT NULL, audit_json TEXT NOT NULL DEFAULT '[]'
        )''',
    ]
    for statement in statements:
        connection.execute(statement)
