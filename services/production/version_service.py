"""通用内容版本；恢复复制完整历史并追加版本，绝不调用 Provider。"""

import json

from database.production_store import json_text
from models import utc_now
from services.production.action_service import record_action
from services.production.project_service import require_project
from services.research.guards import version_guard

CONTENT_TYPES = {'research': '资料研究', 'script': '脚本编辑', 'storyboard': '分镜设计',
                 'asset': '素材管理', 'editing_guide': '剪辑指导'}
VERSION_SOURCES = {'ai': 'AI 生成', 'manual': '人工修改', 'restore': '人工恢复'}


def object_identity(content_type, object_key):
    if content_type not in CONTENT_TYPES:
        raise ValueError('内容类型无效')
    if not isinstance(object_key, str) or not object_key.strip():
        raise ValueError('内容对象键不能为空')
    return object_key.strip()


class VersionService:
    def __init__(self, store):
        self.store = store

    def create(self, project_id, content_type, content, *, object_key='main', source='manual', note='', connection=None):
        """AI 来源仅供记录外部生成内容；此处没有任何 AI 生成逻辑。"""
        object_key = object_identity(content_type, object_key)
        if source not in ('ai', 'manual') or not isinstance(note, str):
            raise ValueError('版本来源或说明无效；恢复版本必须使用恢复操作')
        if content_type == 'research' and object_key == 'report':
            raise ValueError('报告必须通过ReportService校验及版本冲突检查后保存')
        payload = json_text(content)
        if connection is not None:
            return self._create(connection, project_id, content_type, object_key, content, payload, source, note)
        with self.store.transaction() as con:
            return self._create(con, project_id, content_type, object_key, content, payload, source, note)

    def _create(self, con, project_id, content_type, key, content, payload, source, note):
        row = require_project(self.store, con, project_id, writable=True)
        report_binding = version_guard(con, project_id, content_type, key, content)
        now = utc_now()
        object_id = self.store.ensure_object(con, project_id, content_type, key, now)
        version_id = self.store.insert_version(con, project_id, object_id, payload, source, note, now)
        self._audit(con, row, object_id, version_id, now, 'version_created', report_binding=report_binding)
        return self.store.decode_version(self.store.version_row(con, project_id, version_id))

    def history(self, project_id, content_type, *, object_key='main'):
        object_key = object_identity(content_type, object_key)
        self._exists(project_id)
        return self.store.versions(project_id, content_type, object_key)

    def details(self, project_id, version_id):
        version = self.store.version(project_id, version_id)
        if version is None:
            raise ValueError('版本不存在或不属于当前制作任务')
        return version

    def restore(self, project_id, version_id, *, object_id, note=''):
        if not isinstance(note, str):
            raise ValueError('版本说明必须为文本')
        with self.store.transaction() as con:
            row = require_project(self.store, con, project_id, writable=True)
            original = self.store.version_row(con, project_id, version_id)
            if original is None or original['object_id'] != object_id:
                raise ValueError('恢复源版本不属于当前任务的指定内容对象')
            obj = con.execute('SELECT * FROM production_objects WHERE id=?', (object_id,)).fetchone()
            if obj['content_type'] == 'research' and obj['object_key'] == 'report':
                from services.research.report_service import ReportService
                # 当前连接内委托，防止嵌套写事务；报告服务统一核验和重新发布。
                return ReportService(self.store).restore_on_connection(con, project_id, version_id, object_id=object_id)
            report_binding = version_guard(con, project_id, obj['content_type'], obj['object_key'], json.loads(original['content_json']))
            now = utc_now()
            restored_id = self.store.insert_version(con, project_id, object_id,
                original['content_json'], 'restore', note, now, version_id)
            self._audit(con, row, object_id, restored_id, now, 'version_restored', version_id, report_binding=report_binding)
            return self.store.decode_version(self.store.version_row(con, project_id, restored_id))

    def _exists(self, project_id):
        if self.store.get_project(project_id) is None:
            raise ValueError('制作任务不存在')

    def _audit(self, con, row, object_id, version_id, now, action, restored_from=None, *, report_binding=None):
        self.store.touch_project(con, row['id'], now)
        record_action(self.store, con, row['id'], action, row['status'], row['status'], now,
                      {'object_id': object_id, 'version_id': version_id, 'restored_from_version_id': restored_from,
                       **({'confirmed_report': report_binding} if report_binding else {})})
