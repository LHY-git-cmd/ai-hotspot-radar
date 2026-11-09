"""资料研究 v5 增量 DDL；不重建旧表，不改变历史正文和费用。"""


def create_research_tables(con):
    statements = [
        "ALTER TABLE topic_analyses ADD COLUMN purpose TEXT NOT NULL DEFAULT 'topic' CHECK(purpose IN ('topic','research_plan','research_evidence','research_report'))",
        'ALTER TABLE topic_analyses ADD COLUMN production_project_id INTEGER REFERENCES production_projects(id)',
        'ALTER TABLE topic_analyses ADD COLUMN result_version_id INTEGER REFERENCES production_versions(id)',
        'CREATE INDEX idx_research_ai_history ON topic_analyses(production_project_id,purpose,id)',
        'CREATE UNIQUE INDEX idx_version_project_id ON production_versions(id,project_id)',
        '''CREATE TABLE research_plan_confirmations (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES production_projects(id),
            plan_version_id INTEGER NOT NULL, action_id TEXT NOT NULL UNIQUE, confirmed_at TEXT NOT NULL,
            FOREIGN KEY(plan_version_id,project_id) REFERENCES production_versions(id,project_id),
            UNIQUE(project_id,plan_version_id), UNIQUE(id,project_id)
        )''',
        '''CREATE TABLE research_search_runs (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES production_projects(id),
            plan_version_id INTEGER NOT NULL, confirmation_id INTEGER NOT NULL,
            action_id TEXT NOT NULL UNIQUE, provider TEXT NOT NULL, params_json TEXT NOT NULL CHECK(json_valid(params_json)),
            status TEXT NOT NULL CHECK(status IN ('running','success','partial','failed','interrupted')),
            started_at TEXT NOT NULL, finished_at TEXT, error_type TEXT,
            FOREIGN KEY(plan_version_id,project_id) REFERENCES production_versions(id,project_id),
            FOREIGN KEY(confirmation_id,project_id) REFERENCES research_plan_confirmations(id,project_id),
            UNIQUE(id,project_id)
        )''',
        "CREATE UNIQUE INDEX idx_research_search_active ON research_search_runs(project_id) WHERE status='running'",
        'CREATE INDEX idx_research_runs_history ON research_search_runs(project_id,id)',
        '''CREATE TABLE research_search_calls (
            id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES research_search_runs(id),
            operation TEXT NOT NULL CHECK(operation IN ('usage','search','extract')), question_id TEXT NOT NULL,
            request_json TEXT NOT NULL CHECK(json_valid(request_json)), response_json TEXT,
            request_id TEXT, credits TEXT,
            status TEXT NOT NULL CHECK(status IN ('pending','success','partial','failed')),
            created_at TEXT NOT NULL, finished_at TEXT, error_type TEXT,
            UNIQUE(run_id,operation,question_id)
        )''',
        'CREATE INDEX idx_research_calls_run ON research_search_calls(run_id,id)',
        '''CREATE TABLE research_sources (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES production_projects(id),
            title TEXT NOT NULL, url TEXT NOT NULL, url_key TEXT NOT NULL, domain TEXT NOT NULL,
            published_at TEXT, searched_at TEXT NOT NULL, provider TEXT NOT NULL,
            snippet TEXT NOT NULL, text TEXT NOT NULL,
            extraction_status TEXT NOT NULL CHECK(extraction_status IN ('success','failed')),
            extraction_error TEXT, content_hash TEXT NOT NULL,
            UNIQUE(project_id,url_key,content_hash), UNIQUE(id,project_id)
        )''',
        '''CREATE TABLE research_source_questions (
            project_id INTEGER NOT NULL, run_id INTEGER NOT NULL, question_id TEXT NOT NULL, source_id INTEGER NOT NULL,
            PRIMARY KEY(run_id,question_id,source_id),
            FOREIGN KEY(run_id,project_id) REFERENCES research_search_runs(id,project_id),
            FOREIGN KEY(source_id,project_id) REFERENCES research_sources(id,project_id)
        )''',
        'CREATE INDEX idx_research_question_source ON research_source_questions(source_id,run_id)',
        '''CREATE TABLE research_evidence (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, run_id INTEGER NOT NULL,
            question_id TEXT NOT NULL, analysis_id INTEGER NOT NULL REFERENCES topic_analyses(id),
            position INTEGER NOT NULL, category TEXT NOT NULL CHECK(category IN
                ('verified','single_source','opinion','inference','disputed','unverified')),
            summary TEXT NOT NULL, inference TEXT NOT NULL, verification TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(run_id,project_id) REFERENCES research_search_runs(id,project_id),
            UNIQUE(analysis_id,position), UNIQUE(id,project_id)
        )''',
        'CREATE INDEX idx_research_evidence_batch ON research_evidence(project_id,analysis_id,id)',
        '''CREATE TABLE research_evidence_sources (
            project_id INTEGER NOT NULL, evidence_id INTEGER NOT NULL, source_id INTEGER NOT NULL,
            quote TEXT NOT NULL, field TEXT NOT NULL CHECK(field IN ('text','snippet')), quote_offset INTEGER NOT NULL CHECK(quote_offset>=0),
            PRIMARY KEY(evidence_id,source_id,field,quote_offset),
            FOREIGN KEY(evidence_id,project_id) REFERENCES research_evidence(id,project_id),
            FOREIGN KEY(source_id,project_id) REFERENCES research_sources(id,project_id)
        )''',
        'CREATE INDEX idx_research_citation_source ON research_evidence_sources(source_id,evidence_id)',
        '''CREATE TABLE research_report_confirmations (
            id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES production_projects(id),
            report_version_id INTEGER NOT NULL, plan_confirmation_id INTEGER NOT NULL,
            run_id INTEGER NOT NULL, evidence_analysis_id INTEGER NOT NULL REFERENCES topic_analyses(id),
            action_id TEXT NOT NULL UNIQUE, confirmed_at TEXT NOT NULL,
            FOREIGN KEY(report_version_id,project_id) REFERENCES production_versions(id,project_id),
            FOREIGN KEY(plan_confirmation_id,project_id) REFERENCES research_plan_confirmations(id,project_id),
            FOREIGN KEY(run_id,project_id) REFERENCES research_search_runs(id,project_id),
            UNIQUE(project_id,report_version_id)
        )''',
    ]
    for sql in statements:
        con.execute(sql)
    # 来源和确认/证据只追加，模型或误用的 SQL 都不能改写引用依据。
    for table in ('research_sources', 'research_source_questions', 'research_evidence',
                  'research_evidence_sources', 'research_plan_confirmations', 'research_report_confirmations'):
        for operation in ('UPDATE', 'DELETE'):
            con.execute(f'''CREATE TRIGGER protect_{table}_{operation.lower()} BEFORE {operation} ON {table}
                BEGIN SELECT RAISE(ABORT, 'research history is append-only'); END''')
