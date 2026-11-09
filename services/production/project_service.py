"""集中定义制作任务生命周期；状态是人工标记，不代表 AI 执行结果。"""

from models import utc_now
from services.production.action_service import record_action

STATUSES = {'pending': '待开始', 'researching': '资料研究中', 'scripting': '脚本制作中',
            'storyboarding': '分镜设计中', 'assets': '素材准备中', 'editing': '剪辑准备中',
            'completed': '制作完成', 'paused': '已暂停', 'archived': '已归档'}
NORMAL_STATUSES = {key: label for key, label in STATUSES.items() if key not in ('paused', 'archived')}


def require_project(store, connection, project_id, *, writable=False):
    row = store.project_row(connection, project_id)
    if row is None:
        raise ValueError('制作任务不存在')
    if writable and row['status'] == 'archived':
        raise ValueError('已归档任务只读，不能修改')
    return dict(row)


def project_text(name, notes):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('任务名称不能为空')
    if not isinstance(notes, str):
        raise ValueError('备注必须为文本')
    return name.strip(), notes


class ProjectService:
    """全部写操作原子提交，重复状态操作不创建虚假历史。"""

    def __init__(self, store):
        self.store = store

    def create(self, idea_id, name, notes=''):
        name, notes = project_text(name, notes)
        with self.store.transaction() as con:
            if not self.store.idea_exists(con, idea_id):
                raise ValueError('来源视频选题不存在')
            if self.store.active_project(con, idea_id):
                raise ValueError('该选题已有有效制作任务，请打开原任务；归档后才能新建')
            now = utc_now()
            project_id = self.store.insert_project(con, idea_id, name, notes, now)
            record_action(self.store, con, project_id, 'created', None, 'pending', now, {'idea_id': idea_id})
            return require_project(self.store, con, project_id)

    def edit(self, project_id, name, notes):
        name, notes = project_text(name, notes)
        with self.store.transaction() as con:
            row = require_project(self.store, con, project_id, writable=True)
            if (row['name'], row['notes']) != (name, notes):
                now = utc_now()
                self.store.edit_project(con, project_id, name, notes, now)
                record_action(self.store, con, project_id, 'updated', row['status'], row['status'], now,
                              {'before': {'name': row['name'], 'notes': row['notes']},
                               'after': {'name': name, 'notes': notes}})
            return require_project(self.store, con, project_id)

    def set_status(self, project_id, status):
        if status not in STATUSES:
            raise ValueError('制作状态无效')
        if status == 'paused':
            return self.pause(project_id)
        if status == 'archived':
            return self.archive(project_id)
        return self._transition(project_id, 'status_changed', status)

    def pause(self, project_id):
        return self._transition(project_id, 'paused', 'paused')

    def resume(self, project_id):
        return self._transition(project_id, 'resumed')

    def archive(self, project_id):
        return self._transition(project_id, 'archived', 'archived')

    def _transition(self, project_id, action, status=None):
        """暂停只记一次原状态；恢复必须走恢复操作，归档为终态。"""
        with self.store.transaction() as con:
            row = require_project(self.store, con, project_id)
            before = row['status']
            if before == 'archived':
                if action == 'archived':
                    return row
                raise ValueError('已归档任务只读，不能修改')
            if action == 'resumed':
                if before != 'paused':
                    raise ValueError('只有已暂停任务可以恢复')
                status = row['resume_status']
            elif before == 'paused' and action == 'status_changed':
                raise ValueError('请先恢复任务，再调整制作阶段')
            from services.research.guards import FORWARD_STATES, require_report
            report_binding = None
            if status in FORWARD_STATES:
                report_binding = require_report(con, project_id)
            if before != status:
                now = utc_now()
                self.store.change_status(con, project_id, status, before if action == 'paused' else None, now)
                record_action(self.store, con, project_id, action, before, status, now,
                              {'confirmed_report': report_binding} if report_binding else None)
            return require_project(self.store, con, project_id)
