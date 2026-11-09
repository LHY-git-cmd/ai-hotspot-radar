"""所有页面、通用版本和制作状态共用的研究准入规则。"""

import json

from services.research.schemas import validate_plan


FORWARD_TYPES = {'script', 'storyboard', 'asset', 'editing_guide'}
FORWARD_STATES = {'scripting', 'storyboarding', 'assets', 'editing', 'completed'}


def writable(con, project_id):
    row = con.execute('SELECT * FROM production_projects WHERE id=?', (project_id,)).fetchone()
    if not row: raise ValueError('制作任务不存在')
    if row['status'] in ('paused', 'archived'):
        raise ValueError('暂停或归档任务只允许查看研究历史，请先恢复任务')
    return row


def latest(con, project_id, key):
    row = con.execute('''SELECT v.* FROM production_versions v JOIN production_objects o ON o.id=v.object_id
        WHERE v.project_id=? AND o.content_type='research' AND o.object_key=? ORDER BY v.version_number DESC LIMIT 1''',
        (project_id, key)).fetchone()
    return dict(row) | {'content': json.loads(row['content_json'])} if row else None


def confirmed_plan(con, project_id, version_id=None):
    plan = latest(con, project_id, 'plan')
    if plan is None or (version_id is not None and version_id != plan['id']):
        raise ValueError('请先保存并确认当前研究计划版本')
    confirmation = con.execute('SELECT * FROM research_plan_confirmations WHERE project_id=? AND plan_version_id=?',
                               (project_id, plan['id'])).fetchone()
    if confirmation is None: raise ValueError('当前研究计划尚未确认，禁止联网搜索')
    return plan, dict(confirmation)


def current_basis(con, project_id):
    plan, _ = confirmed_plan(con, project_id)
    run = con.execute('SELECT * FROM research_search_runs WHERE project_id=? ORDER BY id DESC LIMIT 1', (project_id,)).fetchone()
    if not run or run['plan_version_id'] != plan['id'] or run['status'] not in ('success', 'partial'):
        raise ValueError('尚无当前计划的可用搜索结果，请完成研究搜索')
    evidence = con.execute('''SELECT id FROM topic_analyses WHERE production_project_id=? AND purpose='research_evidence'
        AND status='success' AND json_extract(input_json,'$.run_id')=? ORDER BY id DESC LIMIT 1''', (project_id, run['id'])).fetchone()
    if not evidence: raise ValueError('请先完成当前搜索结果的证据整理')
    return {'plan_version_id': plan['id'], 'search_run_id': run['id'], 'evidence_analysis_id': evidence['id']}


def validate_report(con, project_id, content):
    from services.research.report_evidence import read_bundle
    from services.research.report_validation import verify_envelope
    return verify_envelope(content, read_bundle(con, project_id))


def require_report(con, project_id):
    from services.research.report_service import require_confirmed_report
    return require_confirmed_report(con, project_id)


def version_guard(con, project_id, content_type, key, content):
    if content_type in FORWARD_TYPES:
        writable(con, project_id)
        return require_report(con, project_id)
    if content_type == 'research' and key in ('plan', 'report'):
        writable(con, project_id)
        if key == 'plan': validate_plan(content)
        else:
            raise ValueError('报告必须通过ReportService校验、保存及版本冲突检查')
