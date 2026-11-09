"""制作模块独立 SQL 存储；复用短连接，不初始化 AI 预算或 Provider。"""

from contextlib import contextmanager
import json

from database.store import HotspotStore


def json_text(value: object) -> str:
    """完整序列化内容，非法 JSON 值在打开写事务前拒绝。"""
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError('内容必须能完整保存为标准 JSON，不能包含 NaN 或 Infinity') from None


class ProductionStore(HotspotStore):
    """只访问本地制作数据和第三期选题；业务规则由服务层集中维护。"""

    @contextmanager
    def transaction(self):
        """串行化状态检查、唯一性检查、版本分配与审计写入。"""
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            yield connection

    @staticmethod
    def project_row(connection, project_id: int):
        return connection.execute('''SELECT p.*,i.title AS idea_title FROM production_projects p
            JOIN video_ideas i ON i.id=p.idea_id WHERE p.id=?''', (project_id,)).fetchone()

    def get_project(self, project_id: int) -> dict | None:
        with self._connection() as connection:
            row = self.project_row(connection, project_id)
            return dict(row) if row else None

    def projects(self, *, archived: bool | None = False) -> list[dict]:
        """默认仅有效任务；True 为归档历史，None 为全部。"""
        where = '' if archived is None else " WHERE p.status" + ("='archived'" if archived else "<>'archived'")
        with self._connection() as connection:
            return [dict(row) for row in connection.execute('''SELECT p.*,i.title AS idea_title
                FROM production_projects p JOIN video_ideas i ON i.id=p.idea_id'''
                + where + ' ORDER BY p.updated_at DESC,p.id DESC')]

    def ideas(self) -> list[dict]:
        """只读选题与有效任务关联；不经过会初始化预算的 AIStore。"""
        with self._connection() as connection:
            return [dict(row) for row in connection.execute('''SELECT i.id,i.title,i.status,
                p.id AS active_project_id FROM video_ideas i LEFT JOIN production_projects p
                ON p.idea_id=i.id AND p.status<>'archived' ORDER BY i.id DESC''')]

    @staticmethod
    def idea_exists(connection, idea_id):
        return connection.execute('SELECT 1 FROM video_ideas WHERE id=?', (idea_id,)).fetchone() is not None

    @staticmethod
    def active_project(connection, idea_id):
        return connection.execute("SELECT id FROM production_projects WHERE idea_id=? AND status<>'archived'", (idea_id,)).fetchone()

    @staticmethod
    def insert_project(connection, idea_id, name, notes, now):
        return connection.execute('''INSERT INTO production_projects
            (idea_id,name,notes,status,created_at,updated_at) VALUES(?,?,?,'pending',?,?)''',
            (idea_id, name, notes, now, now)).lastrowid

    @staticmethod
    def edit_project(connection, project_id, name, notes, now):
        connection.execute('UPDATE production_projects SET name=?,notes=?,updated_at=? WHERE id=?',
                           (name, notes, now, project_id))

    @staticmethod
    def change_status(connection, project_id, status, resume_status, now):
        connection.execute('UPDATE production_projects SET status=?,resume_status=?,updated_at=? WHERE id=?',
                           (status, resume_status, now, project_id))

    @staticmethod
    def touch_project(connection, project_id, now):
        connection.execute('UPDATE production_projects SET updated_at=? WHERE id=?', (now, project_id))

    @staticmethod
    def insert_action(connection, project_id, action_type, previous_status, new_status, now, details):
        connection.execute('''INSERT INTO production_actions
            (project_id,action_type,previous_status,new_status,created_at,details_json) VALUES(?,?,?,?,?,?)''',
            (project_id, action_type, previous_status, new_status, now, json_text(details)))

    def actions(self, project_id):
        with self._connection() as connection:
            return [dict(row) | {'details': json.loads(row['details_json'])} for row in connection.execute(
                'SELECT * FROM production_actions WHERE project_id=? ORDER BY id', (project_id,))]

    def objects(self, project_id):
        with self._connection() as connection:
            return [dict(row) for row in connection.execute(
                'SELECT * FROM production_objects WHERE project_id=? ORDER BY content_type,id', (project_id,))]

    @staticmethod
    def ensure_object(connection, project_id, content_type, object_key, now):
        connection.execute('''INSERT INTO production_objects(project_id,content_type,object_key,created_at)
            VALUES(?,?,?,?) ON CONFLICT(project_id,content_type,object_key) DO NOTHING''',
            (project_id, content_type, object_key, now))
        return connection.execute('''SELECT id FROM production_objects
            WHERE project_id=? AND content_type=? AND object_key=?''', (project_id, content_type, object_key)).fetchone()[0]

    @staticmethod
    def insert_version(connection, project_id, object_id, content_json, source, note, now, restored_from=None):
        """必须在 transaction 内调用，以独立对象序列分配版本号。"""
        number = connection.execute('SELECT COALESCE(MAX(version_number),0)+1 FROM production_versions WHERE object_id=?',
                                    (object_id,)).fetchone()[0]
        return connection.execute('''INSERT INTO production_versions
            (project_id,object_id,version_number,content_json,source,note,created_at,restored_from_version_id)
            VALUES(?,?,?,?,?,?,?,?)''', (project_id, object_id, number, content_json, source, note, now, restored_from)).lastrowid

    @staticmethod
    def version_row(connection, project_id, version_id):
        return connection.execute('SELECT * FROM production_versions WHERE id=? AND project_id=?', (version_id, project_id)).fetchone()

    @staticmethod
    def decode_version(row):
        return dict(row) | {'content': json.loads(row['content_json'])}

    def version(self, project_id, version_id):
        with self._connection() as connection:
            row = self.version_row(connection, project_id, version_id)
            return self.decode_version(row) if row else None

    def versions(self, project_id, content_type, object_key):
        with self._connection() as connection:
            return [self.decode_version(row) for row in connection.execute('''SELECT v.* FROM production_versions v
                JOIN production_objects o ON o.id=v.object_id WHERE v.project_id=?
                AND o.content_type=? AND o.object_key=? ORDER BY v.version_number DESC''',
                (project_id, content_type, object_key))]
