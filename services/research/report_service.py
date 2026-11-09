"""报告v3编排：已保存证据→表达树→程序渲染→原子发布→单独人工确认。"""

from copy import deepcopy
import json
import logging

from database.ai_store import AIStore
from database.production_store import json_text
from models import utc_now
from services.ai.base import AIError
from services.ai.config import load_ai_settings
from services.ai.cost_tracker import reservation_units
from services.ai.deepseek_client import DeepSeekProvider, request_body
from services.ai.executor import execute_attempts
from services.research.evidence_contract import digest
from services.research.report_contract import VERSION, POLICY, RENDERER, candidate_schema
from services.research.report_evidence import read_bundle, fail
from services.research.report_validation import validate_candidate, verify_envelope, default_candidate, check_previous, attempt_state
from services.research.report_confirmation import verify_intent, commit_intent
from services.research.prompts import messages
from services.research.guards import writable, latest

logger = logging.getLogger('ai_hotspot_radar.research.report')
_MISSING = object()


def event(con, project_id, name, details):
    project = con.execute('SELECT status FROM production_projects WHERE id=?', (project_id,)).fetchone()
    con.execute('''INSERT INTO production_actions(project_id,action_type,previous_status,new_status,created_at,details_json)
                   VALUES(?,'updated',?,?,?,?)''',
                (project_id, project['status'], project['status'], utc_now(), json_text({'event': name, **details})))


def receipt(con, project_id, name, version_id):
    rows = con.execute('SELECT details_json FROM production_actions WHERE project_id=? ORDER BY id DESC', (project_id,))
    for row in rows:
        value = json.loads(row[0])
        if value.get('event') == name and value.get('report_version_id') == version_id:
            return value
    return None


def binding(report):
    return {'report_version_id': report['id'], **{k: report['content']['validation'][k]
        for k in ('report_core_hash', 'evidence_set_hash', 'policy_version')}}


def validate_saved(con, project_id, report):
    if not report or report['project_id'] != project_id:
        fail('report_scope_mismatch')
    bundle = read_bundle(con, project_id)
    verify_envelope(report['content'], bundle)
    audit = receipt(con, project_id, 'report_validated_v3', report['id'])
    if not audit or any(audit.get(k) != v for k, v in binding(report).items()):
        fail('report_binding_mismatch')
    return bundle


def require_confirmed_report(con, project_id):
    """所有后续写入共享；不以状态、孤立确认行或模型字段作为授权。"""
    report = latest(con, project_id, 'report')
    if not report:
        fail('report_confirmation_required')
    validate_saved(con, project_id, report)
    c = con.execute('SELECT * FROM research_report_confirmations WHERE project_id=? AND report_version_id=?',
                    (project_id, report['id'])).fetchone()
    if not c:
        fail('report_confirmation_required')
    basis = report['content']['basis']
    if (c['plan_confirmation_id'] != basis['plan_confirmation_id'] or
        c['run_id'] != basis['research_run_id'] or c['evidence_analysis_id'] != basis['evidence_analysis_id']):
        fail('report_confirmation_binding')
    audit = receipt(con, project_id, 'report_confirmed_v3', report['id'])
    if (not audit or any(audit.get(k) != v for k, v in binding(report).items()) or
        audit.get('confirmation_id') != c['id'] or audit.get('action_id') != c['action_id'] or
        audit.get('origin') != 'local_interactive_operator' or audit.get('purpose') != 'confirm_report'):
        fail('report_confirmation_binding')
    return binding(report)


class ReportService:
    def __init__(self, store, *, settings=None, provider_factory=None):
        self.store, self.settings, self.provider_factory = store, settings, provider_factory

    def bundle(self, project_id):
        with self.store._connection() as con:
            con.execute('BEGIN')
            return read_bundle(con, project_id)

    def draft(self, project_id):
        bundle = self.bundle(project_id)
        return {'candidate_document': default_candidate(bundle),
                'expected_previous_report_version_id': bundle['expected_previous_report_version_id']}

    def _publish(self, con, project_id, document, expected_previous, *, source, restored_from=None):
        writable(con, project_id)
        previous = latest(con, project_id, 'report')
        check_previous(previous['id'] if previous else None, expected_previous)
        bundle = read_bundle(con, project_id)
        verify_envelope(document, bundle)
        now = utc_now()
        oid = self.store.ensure_object(con, project_id, 'research', 'report', now)
        vid = self.store.insert_version(con, project_id, oid, json_text(document), source,
            '研究报告v3（待人工确认）', now, restored_from)
        report = {'id': vid, 'content': document}
        event(con, project_id, 'report_validated_v3', binding(report))
        # 与通用版本服务一致，版本/审计/项目时间一并提交。
        self.store.touch_project(con, project_id, now)
        con.execute('''INSERT INTO production_actions(project_id,action_type,previous_status,new_status,created_at,details_json)
            SELECT id,?,status,status,?,? FROM production_projects WHERE id=?''',
            ('version_restored' if restored_from else 'version_created', now,
             json_text({'object_id': oid, 'version_id': vid, 'restored_from_version_id': restored_from}), project_id))
        return self.store.decode_version(self.store.version_row(con, project_id, vid))

    def save(self, project_id, candidate, *, expected_previous_report_version_id=_MISSING):
        if expected_previous_report_version_id is _MISSING:
            fail('report_version_conflict')
        with self.store.transaction() as con:
            writable(con, project_id)
            bundle = read_bundle(con, project_id)
            document = validate_candidate(candidate, bundle, checked_at=utc_now())
            return self._publish(con, project_id, document, expected_previous_report_version_id, source='manual')

    def restore(self, project_id, version_id, *, object_id):
        with self.store.transaction() as con:
            return self.restore_on_connection(con, project_id, version_id, object_id=object_id)

    def restore_on_connection(self, con, project_id, version_id, *, object_id):
        writable(con, project_id)
        original = self.store.version_row(con, project_id, version_id)
        obj = con.execute('SELECT * FROM production_objects WHERE id=? AND project_id=?', (object_id, project_id)).fetchone()
        if (not original or original['object_id'] != object_id or not obj or
            obj['content_type'] != 'research' or obj['object_key'] != 'report'):
            fail('report_scope_mismatch')
        content = json.loads(original['content_json'])
        bundle = read_bundle(con, project_id)
        verify_envelope(content, bundle)
        document = validate_candidate(content['candidate_document'], bundle, checked_at=utc_now())
        return self._publish(con, project_id, document, bundle['expected_previous_report_version_id'],
                             source='restore', restored_from=version_id)

    def generate(self, project_id, action_id):
        analysis_id = None
        ledger = None
        try:
            with self.store._connection() as con:
                con.execute('BEGIN')
                writable(con, project_id)
                previous = con.execute('SELECT * FROM topic_analyses WHERE action_id=?', (action_id,)).fetchone()
                if previous:
                    if previous['purpose'] != 'research_report' or previous['production_project_id'] != project_id:
                        fail('report_scope_mismatch')
                    return {'status': previous['status'], 'analysis_id': previous['id'], 'error': None, 'reused': True}
                bundle = read_bundle(con, project_id)
            settings = self.settings or load_ai_settings()
            settings.validate()
            # 证据与缺口不能裁剪；在付费前确认最小完整表达树确实可通过本地契约。
            validate_candidate(default_candidate(bundle), bundle, checked_at='preflight')
            schema, tool = candidate_schema(bundle), 'submit_research_report'
            provider = (self.provider_factory('report', schema) if self.provider_factory else
                        DeepSeekProvider(settings, schema=schema, tool_name=tool, description='提交研究报告候选表达树'))
            if provider.name == 'deepseek' and not settings.api_key:
                raise ValueError('未配置DeepSeek密钥')
            prompt = messages('report', bundle['model_materials'])
            body = request_body(settings, prompt, schema=schema, tool_name=tool, description='提交研究报告候选表达树')
            reserved = reservation_units(prompt, settings, body=body)
            ledger = AIStore(self.store.path, settings)
            hotspot_id = self.store.source_materials(project_id)['hotspot_id']
            claimed = ledger.claim_analysis(hotspot_id, digest([project_id, bundle, settings.model, settings.output_mode,
                provider.name, schema]), action_id, bundle, 'research-report-v3', True, provider=provider.name,
                purpose='research_report', project_id=project_id, prompt_version='research-report-prompt-v3', schema_version=VERSION)
            analysis_id = claimed['id']
            if claimed['reused_action']:
                return {'status': claimed['status'], 'analysis_id': analysis_id, 'error': None, 'reused': True}

            def before():
                with self.store._connection() as con:
                    con.execute('BEGIN')
                    writable(con, project_id)
                    if read_bundle(con, project_id) != bundle:
                        fail('report_basis_changed')

            def validate(candidate):
                # 此安全适配保留原execute_attempts在校验异常时已知usage的结算路径。
                try:
                    with self.store.transaction() as con:
                        event(con, project_id, 'report_validation_started', {'analysis_id': analysis_id})
                except Exception:
                    logger.error('report validation stage audit unavailable')
                try:
                    return validate_candidate(candidate, bundle, checked_at=utc_now())
                except ValueError:
                    raise
                except Exception:
                    fail('report_validation_internal')

            def persist(aid, attempt, document):
                with self.store.transaction() as con:
                    frozen = con.execute('SELECT input_json FROM topic_analyses WHERE id=?', (aid,)).fetchone()
                    if json.loads(frozen[0]) != bundle:
                        fail('report_binding_mismatch')
                    version = self._publish(con, project_id, document,
                        bundle['expected_previous_report_version_id'], source='ai')
                    self.store.complete_model(con, aid, attempt, project_id, document, version['id'])

            execute_attempts(ledger, provider, settings, analysis_id, prompt, reserved, validate, persist,
                before_attempt=before, on_diagnostic=lambda rid, stage, error, doc:
                    self.store.save_diagnostic(project_id, analysis_id, rid, stage, error, doc))
            return {'status': 'success', 'analysis_id': analysis_id, 'error': None}
        except Exception as error:
            if analysis_id is not None:
                try: ledger.fail_analysis(analysis_id, error.kind if isinstance(error, AIError) else type(error).__name__)
                except Exception: logger.error('report analysis failure persistence unavailable')
            return {'status': 'failed', 'analysis_id': analysis_id,
                    'error': '研究报告生成、证据校验或保存失败；已保留可得费用，请查看诊断记录。'}

    def confirm(self, project_id, version_id, action_id, *, intent=None):
        with self.store.transaction() as con:
            writable(con, project_id)
            report = latest(con, project_id, 'report')
            if not report or report['id'] != version_id:
                fail('report_confirmation_binding')
            metadata = verify_intent(intent, project_id, report, action_id)
            validate_saved(con, project_id, report)
            existing = con.execute('SELECT * FROM research_report_confirmations WHERE action_id=? OR (project_id=? AND report_version_id=?)',
                                   (action_id, project_id, version_id)).fetchone()
            if existing:
                if (existing['action_id'] != action_id or existing['project_id'] != project_id or
                    existing['report_version_id'] != version_id):
                    fail('report_confirmation_intent')
                require_confirmed_report(con, project_id)
                audit = receipt(con, project_id, 'report_confirmed_v3', version_id)
                if audit.get('nonce') != metadata['nonce']:
                    fail('report_confirmation_intent')
            else:
                # action_id同时约束其他交互/模型用途；UUID不是权限凭据。
                if con.execute('SELECT 1 FROM topic_analyses WHERE action_id=?', (action_id,)).fetchone() or con.execute(
                    'SELECT 1 FROM research_plan_confirmations WHERE action_id=?', (action_id,)).fetchone() or con.execute(
                    'SELECT 1 FROM research_search_runs WHERE action_id=?', (action_id,)).fetchone():
                    fail('report_confirmation_intent')
                basis = report['content']['basis']
                cid = con.execute('''INSERT INTO research_report_confirmations(project_id,report_version_id,
                    plan_confirmation_id,run_id,evidence_analysis_id,action_id,confirmed_at) VALUES(?,?,?,?,?,?,?)''',
                    (project_id, version_id, basis['plan_confirmation_id'], basis['research_run_id'],
                     basis['evidence_analysis_id'], action_id, utc_now())).lastrowid
                event(con, project_id, 'report_confirmed_v3', {**metadata, **binding(report),
                                                             'confirmation_id': cid, 'action_id': action_id})
        commit_intent(intent, action_id)

    def state(self, project_id):
        with self.store._connection() as con:
            con.execute('BEGIN')
            report = latest(con, project_id, 'report')
            operation = con.execute("SELECT * FROM topic_analyses WHERE production_project_id=? AND purpose='research_report' ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
            latest_attempt = 'not_generated'
            if operation:
                diag = con.execute('SELECT stage FROM research_model_diagnostics WHERE analysis_id=? ORDER BY id DESC LIMIT 1', (operation['id'],)).fetchone()
                started = None
                if operation['status'] == 'running':
                    started = con.execute("SELECT 1 FROM production_actions WHERE project_id=? AND json_extract(details_json,'$.event')='report_validation_started' AND json_extract(details_json,'$.analysis_id')=?", (project_id, operation['id'])).fetchone()
                latest_attempt = attempt_state(operation, diag[0] if diag else None, bool(started))
            state = 'not_generated'
            if report:
                try:
                    validate_saved(con, project_id, report)
                    state = 'validated_pending_confirmation'
                    try:
                        require_confirmed_report(con, project_id)
                        state = 'confirmed'
                    except ValueError: pass
                except (ValueError, KeyError, TypeError):
                    state = 'stale'
            return {'current_report_state': state, 'latest_attempt_state': latest_attempt,
                    'report_version_id': report['id'] if report else None}
