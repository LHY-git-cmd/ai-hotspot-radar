"""v6 只追加研究诊断表；不更改旧来源、费用、评分或制作状态。"""


def create_research_quality_tables(con):
    con.execute('''CREATE TABLE research_model_diagnostics (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES production_projects(id),
        analysis_id INTEGER NOT NULL REFERENCES topic_analyses(id),
        attempt_run_id INTEGER NOT NULL REFERENCES ai_analysis_runs(id),
        stage TEXT NOT NULL CHECK(stage IN ('provider','validation','persistence')),
        code TEXT NOT NULL, path_json TEXT NOT NULL CHECK(json_valid(path_json)),
        item_index INTEGER, details_json TEXT NOT NULL CHECK(json_valid(details_json)),
        rejected_document_json TEXT CHECK(rejected_document_json IS NULL OR
            (json_valid(rejected_document_json) AND length(CAST(rejected_document_json AS BLOB))<=16384)),
        document_truncated INTEGER NOT NULL CHECK(document_truncated IN (0,1)),
        created_at TEXT NOT NULL, UNIQUE(attempt_run_id,stage)
    )''')
    con.execute('''CREATE TRIGGER validate_research_diagnostic BEFORE INSERT ON research_model_diagnostics
        WHEN NOT EXISTS (SELECT 1 FROM ai_analysis_runs r JOIN topic_analyses a ON a.id=r.analysis_id
          WHERE r.id=NEW.attempt_run_id AND a.id=NEW.analysis_id
          AND a.production_project_id=NEW.project_id AND a.purpose LIKE 'research_%')
        BEGIN SELECT RAISE(ABORT, 'diagnostic research basis mismatch'); END''')
    for operation in ('UPDATE', 'DELETE'):
        con.execute(f'''CREATE TRIGGER protect_research_model_diagnostics_{operation.lower()}
            BEFORE {operation} ON research_model_diagnostics
            BEGIN SELECT RAISE(ABORT, 'research history is append-only'); END''')
