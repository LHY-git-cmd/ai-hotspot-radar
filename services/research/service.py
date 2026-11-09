"""研究工作流；确认、幂等、版本和原始来源保护集中于服务层。"""

from dataclasses import asdict
from copy import deepcopy
import hashlib
import logging
import os

from database.ai_store import AIStore
from database.production_store import json_text
from database.research_store import ResearchStore
from models import utc_now
from services.ai.base import AIError
from services.ai.config import load_ai_settings
from services.ai.cost_tracker import reservation_units
from services.ai.deepseek_client import DeepSeekProvider, request_body
from services.ai.executor import execute_attempts
from services.production.action_service import record_action
from services.production.version_service import VersionService
from services.research.base import SearchError
from services.research.guards import (writable, latest, confirmed_plan, current_basis)
from services.research.prompts import messages
from services.research.schemas import SCHEMAS, validate, validate_plan
from services.research.quality import CONTRACT_VERSION
from services.research.evidence_contract import build_manifest, model_materials, assess_document
from services.research.tavily import TavilyProvider, public_url
from services.research.queries import build_query, QUERY_BUILDER_VERSION
from services.research.diagnostics import ResearchValidationError
from services.normalization import normalize_url

logger = logging.getLogger('ai_hotspot_radar.research')


class ResearchService:
    def __init__(self, store, *, settings=None, provider_factory=None, search_provider=None):
        self.store = ResearchStore(store.path)
        self.versions = VersionService(self.store)
        self.settings = settings
        self.provider_factory = provider_factory
        self.search_provider = search_provider

    def _writable(self, project_id):
        with self.store._connection() as con:
            return dict(writable(con, project_id))

    def current_plan(self, project_id):
        with self.store._connection() as con: return latest(con, project_id, 'plan')

    def current_report(self, project_id):
        with self.store._connection() as con: return latest(con, project_id, 'report')

    def basis(self, project_id):
        with self.store._connection() as con: return current_basis(con, project_id)

    def plan_is_confirmed(self, project_id):
        try:
            with self.store._connection() as con: confirmed_plan(con, project_id)
            return True
        except ValueError:
            return False

    def save_plan(self, project_id, document, *, source='manual', connection=None):
        document = deepcopy(document)
        document['query_builder_version'] = QUERY_BUILDER_VERSION
        validate_plan(document)
        return self.versions.create(project_id, 'research', document, object_key='plan', source=source,
                                    note='研究计划', connection=connection)

    def confirm_plan(self, project_id, version_id, action_id):
        with self.store.transaction() as con:
            row = writable(con, project_id)
            plan = latest(con, project_id, 'plan')
            if plan is None or plan['id'] != version_id:
                raise ValueError('只能确认当前最新研究计划版本')
            if plan['content'].get('query_builder_version') != QUERY_BUILDER_VERSION:
                raise ValueError('查询构造规则已变化，请保存新计划并预览 query 后重新确认')
            prior = con.execute('SELECT * FROM research_plan_confirmations WHERE project_id=? AND plan_version_id=?',
                                (project_id, version_id)).fetchone()
            if prior: return dict(prior)
            now = utc_now()
            confirmation_id = con.execute('''INSERT INTO research_plan_confirmations
                (project_id,plan_version_id,action_id,confirmed_at) VALUES(?,?,?,?)''',
                (project_id, version_id, action_id, now)).lastrowid
            self._event(con, row, 'plan_confirmed', {'version_id': version_id, 'confirmation_id': confirmation_id}, now)
            return {'id': confirmation_id, 'plan_version_id': version_id}

    def _check_plan(self, project_id, version_id):
        with self.store._connection() as con:
            writable(con, project_id)
            return confirmed_plan(con, project_id, version_id)

    def _check_search(self, project_id, version_id, run_id):
        with self.store._connection() as con:
            writable(con, project_id)
            confirmed_plan(con, project_id, version_id)
            run = con.execute('SELECT status FROM research_search_runs WHERE id=? AND project_id=?', (run_id, project_id)).fetchone()
            if run is None or run['status'] != 'running':
                raise ValueError('搜索已中断或状态已变化，停止后续网络请求')

    def search(self, project_id, version_id, action_id, *, allow_unknown_quota=False, expected_plan=None):
        plan, confirmation = self._check_plan(project_id, version_id)
        if plan['content'].get('query_builder_version') != QUERY_BUILDER_VERSION:
            raise ValueError('查询构造规则已变化，旧确认不能执行新 query；请保存新计划并重新确认')
        if expected_plan is not None and expected_plan != plan['content']:
            raise ValueError('页面计划已有未保存修改，请先保存并重新确认')
        provider = self.search_provider or TavilyProvider(os.getenv('TAVILY_API_KEY', '').strip())
        if not provider.available: raise ValueError('未配置 TAVILY_API_KEY 搜索密钥；不会发送请求')
        with self.store.transaction() as con:
            row = writable(con, project_id)
            confirmed_plan(con, project_id, version_id)
            previous = con.execute('SELECT * FROM research_search_runs WHERE action_id=?', (action_id,)).fetchone()
            if previous:
                if previous['project_id'] != project_id or previous['plan_version_id'] != version_id:
                    raise ValueError('搜索动作的任务或计划已变化，请重新确认')
                return dict(previous)
            if con.execute("SELECT 1 FROM research_search_runs WHERE project_id=? AND status='running'", (project_id,)).fetchone():
                raise ValueError('该任务已有进行中的搜索，不能重复执行')
            parameters = {'max_results_per_question': 3, 'max_urls': 20, 'depth': 'basic',
                          'allow_unknown_quota': allow_unknown_quota, 'query_builder_version': QUERY_BUILDER_VERSION,
                          'queries': {q['id']: build_query(q) for q in plan['content']['questions']}}
            run_id = con.execute('''INSERT INTO research_search_runs(project_id,plan_version_id,confirmation_id,
                action_id,provider,params_json,status,started_at) VALUES(?,?,?,?,?,?,'running',?)''',
                (project_id, version_id, confirmation['id'], action_id, provider.name, json_text(parameters), utc_now())).lastrowid
            self._event(con, row, 'search_started', {'run_id': run_id, 'plan_version_id': version_id})
        found, extracted, failures, search_success, url_aliases = {}, {}, 0, 0, {}
        try:
            self._check_search(project_id, version_id, run_id)
            quota_call = self.store.call_start(run_id, 'usage', '', {})
            try:
                quota = provider.usage()
                remaining = quota.remaining
                self.store.call_finish(quota_call, 'success', result={'remaining': str(remaining) if remaining is not None else None})
            except Exception:
                remaining = None
                self.store.call_finish(quota_call, 'failed', error='quota_unknown')
            upper = len(plan['content']['questions']) + 4
            if remaining is None and not allow_unknown_quota:
                raise ValueError('额度未知，未执行搜索；可明确选择按本次调用上限继续')
            if remaining is not None and remaining < upper:
                raise ValueError('搜索服务可用额度不足以覆盖本次调用上限')
            for question in plan['content']['questions']:
                self._check_search(project_id, version_id, run_id)
                params = {'query': build_query(question),
                    'start_date': plan['content']['start_date'], 'end_date': plan['content']['end_date'],
                    'domains': question['domains'], 'max_results': 3}
                call_id = self.store.call_start(run_id, 'search', question['id'],
                    {**params, 'query_builder_version': QUERY_BUILDER_VERSION})
                try:
                    reply = provider.search(**params)
                    self.store.call_finish(call_id, 'success', credits=reply.credits, request_id=reply.request_id,
                                           result=[asdict(result) for result in reply.results])
                    search_success += 1
                    for item in reply.results[:3]:
                        if not public_url(item.url): continue
                        # 同 URL 的不同问题只关联一次来源，保留各搜索原始摘录。
                        canonical = normalize_url(item.url)
                        original_url = url_aliases.get(canonical, item.url)
                        if original_url not in found:
                            if len(found) >= 20: continue
                            url_aliases[canonical] = item.url
                            found[original_url] = (item, [], [])
                        found[original_url][1].append(question['id'])
                        found[original_url][2].append(item.snippet)
                except Exception as error:
                    failures += 1
                    self.store.call_finish(call_id, 'failed', credits=getattr(error, 'credits', None),
                                           error=error.kind if isinstance(error, SearchError) else 'provider_failure')
            if found:
                self._check_search(project_id, version_id, run_id)
                call_id = self.store.call_start(run_id, 'extract', '', {'urls': list(found)})
                try:
                    reply = provider.extract(list(found))
                    extracted = {item.url: item for item in reply.results if item.url in found}
                    good = sum(bool(item.text) and item.status == 'success' for item in extracted.values())
                    self.store.call_finish(call_id, 'success' if good == len(found) else 'partial' if good else 'failed',
                        credits=reply.credits, request_id=reply.request_id, result=[asdict(item) for item in reply.results])
                except Exception as error:
                    self.store.call_finish(call_id, 'failed', credits=getattr(error, 'credits', None),
                        error=error.kind if isinstance(error, SearchError) else 'provider_failure')
                failures += sum(not (extracted.get(url) and extracted[url].status == 'success' and extracted[url].text) for url in found)
            self.store.save_sources(project_id, run_id, provider.name, found, extracted)
            self.store.finish_run(run_id, 'partial' if failures and search_success else 'success' if search_success else 'failed')
        except Exception as error:
            # 已得到的来源仍落库；计划过期只阻止后续调用，不丢弃已发生的费用和历史。
            self.store.save_sources(project_id, run_id, provider.name, found, extracted)
            self.store.finish_run(run_id, 'failed', 'plan_or_quota_changed' if isinstance(error, ValueError) else 'local_failure')
            logger.warning('research_run=%d failed type=%s', run_id, type(error).__name__)
        return self.store.run(project_id, run_id)

    def generate_plan(self, project_id, action_id):
        self._writable(project_id)
        materials = self.store.source_materials(project_id)
        current = self.current_plan(project_id)
        materials['base_plan_version_id'] = current['id'] if current else None
        return self._generate(project_id, 'plan', materials, action_id, validate_plan)

    def organize_evidence(self, project_id, run_id, action_id):
        self._writable(project_id)
        run = self.store.run(project_id, run_id)
        if run is None or run['status'] not in ('success', 'partial'):
            raise ValueError('请选择已完成的有效研究搜索')
        self._check_plan(project_id, run['plan_version_id'])
        newest = self.store.runs(project_id)[0]
        if newest['id'] != run_id:
            raise ValueError('历史搜索只可查看，请基于当前最新搜索结果整理证据')
        sources = self.store.sources(project_id, run_id)
        if not sources: raise ValueError('没有可整理的来源，不能虚构证据')
        plan = self.current_plan(project_id)['content']
        associations = self.store.source_questions(run_id)
        settings = self.settings or load_ai_settings()
        as_of = utc_now()[:10]
        # 先扣除固定提示词、Schema及来源元数据，再选窗；完整请求沿用既有预占检查。
        manifest = build_manifest(sources, associations, project_id, run_id, plan, as_of, 0)
        payload = model_materials(manifest, plan, run['plan_version_id'])
        def request_size(value):
            body = request_body(settings, messages('evidence', value), schema=SCHEMAS['evidence'],
                                tool_name='submit_research_evidence', description='提交可追溯的资料研究evidence')
            return len(json_text(body).encode())
        budget = max(0, settings.max_request_bytes - request_size(payload) - 2048)
        # coverage元数据也占空间；只缩小窗口预算，绝不提高请求上限。
        while True:
            manifest = build_manifest(sources, associations, project_id, run_id, plan, as_of, budget)
            payload = model_materials(manifest, plan, run['plan_version_id'])
            overflow = request_size(payload) - settings.max_request_bytes
            if overflow <= 0 or budget == 0:
                break
            budget = max(0, budget - max(overflow + 512, budget // 4))
        inputs = {'contract_version': CONTRACT_VERSION, 'run_id': run_id, 'research_as_of': as_of,
            'plan_version_id': run['plan_version_id'], 'manifest': manifest, 'model_materials': payload}
        return self._generate(project_id, 'evidence', inputs, action_id,
                              lambda doc: self._validate_evidence(project_id, run_id, doc, inputs))

    def _validate_evidence(self, project_id, run_id, doc, inputs):
        manifest = inputs['manifest']
        if manifest['project_id'] != project_id or manifest['run_id'] != run_id:
            raise ResearchValidationError('source_association', '证据批次关联无效')
        return assess_document(doc, manifest)

    def reports(self):
        from services.research.report_service import ReportService
        return ReportService(self.store, settings=self.settings, provider_factory=self.provider_factory)

    def generate_report(self, project_id, action_id):
        return self.reports().generate(project_id, action_id)

    def save_report(self, project_id, document, **kwargs):
        return self.reports().save(project_id, document, **kwargs)

    def confirm_report(self, project_id, version_id, action_id, *, intent=None):
        return self.reports().confirm(project_id, version_id, action_id, intent=intent)

    def _generate(self, project_id, kind, inputs, action_id, validator):
        if kind not in ('plan', 'evidence'):
            raise ValueError('报告必须通过ReportService v3生成')
        analysis_id = None
        previous = self.store.rows('SELECT * FROM topic_analyses WHERE action_id=?', (action_id,))
        if previous:
            if previous[0]['production_project_id'] != project_id or previous[0]['purpose'] != 'research_' + kind:
                raise ValueError('该模型操作 ID 已用于其他任务或用途')
            return {'status': previous[0]['status'], 'analysis_id': previous[0]['id'], 'error': None, 'reused': True}
        settings = self.settings or load_ai_settings()
        schema = SCHEMAS[kind]
        if kind == 'evidence':
            validator = lambda doc: self._validate_evidence(project_id, inputs['run_id'], doc, inputs)
        tool = 'submit_research_' + kind
        description = '提交可追溯的资料研究' + kind
        provider = (self.provider_factory(kind, schema) if self.provider_factory else
                    DeepSeekProvider(settings, schema=schema, tool_name=tool, description=description))
        try:
            settings.validate()
            if provider.name == 'deepseek' and not settings.api_key: raise ValueError('未配置 DeepSeek 密钥')
            ledger = AIStore(self.store.path, settings)
            prompt = messages(kind, inputs['model_materials'] if kind == 'evidence' else inputs)
            body = request_body(settings, prompt, schema=schema, tool_name=tool, description=description)
            reserved = reservation_units(prompt, settings, body=body)
            fingerprint = hashlib.sha256(json_text([project_id, kind, inputs, settings.model, settings.output_mode, provider.name, schema]).encode()).hexdigest()
            hotspot_id = self.store.source_materials(project_id)['hotspot_id']
            claimed = ledger.claim_analysis(hotspot_id, fingerprint, action_id, inputs, 'research-v3' if kind == 'evidence' else 'research-v2', True,
                provider=provider.name, purpose='research_' + kind, project_id=project_id,
                prompt_version='research-evidence-prompt-v3' if kind == 'evidence' else 'research-prompt-v2',
                schema_version=CONTRACT_VERSION if kind == 'evidence' else 'research-' + kind + '-v2')
            analysis_id = claimed['id']
            if claimed['reused_action']:
                return {'status': claimed['status'], 'analysis_id': analysis_id, 'error': None, 'reused': True}

            def before_attempt():
                self._writable(project_id)
                if kind == 'plan':
                    current = self.current_plan(project_id)
                    if (current['id'] if current else None) != inputs['base_plan_version_id']:
                        raise ValueError('生成期间研究计划已被修改，请保留人工修改并重新生成')
                if kind == 'evidence': self._check_plan(project_id, inputs['plan_version_id'])
                if kind == 'evidence' and self.store.runs(project_id)[0]['id'] != inputs['run_id']:
                    raise ValueError('证据整理期间已执行新的搜索，请使用最新研究结果')

            def persist(operation_id, run_id, doc):
                with self.store.transaction() as con:
                    row = writable(con, project_id)
                    version = None
                    if kind == 'plan':
                        current = latest(con, project_id, 'plan')
                        if (current['id'] if current else None) != inputs['base_plan_version_id']:
                            raise ValueError('计划生成期间已有人保存新版本，未覆盖人工修改')
                        version = self.save_plan(project_id, doc, source='ai', connection=con)
                    elif kind == 'evidence':
                        confirmed_plan(con, project_id, inputs['plan_version_id'])
                        newest = con.execute('SELECT id FROM research_search_runs WHERE project_id=? ORDER BY id DESC LIMIT 1', (project_id,)).fetchone()
                        if newest['id'] != inputs['run_id']: raise ValueError('搜索依据已变化，未保存过期证据批次')
                        self.store.insert_evidence(con, project_id, inputs['run_id'], operation_id, doc)
                        self._event(con, row, 'evidence_organized', {'analysis_id': operation_id, 'run_id': inputs['run_id']})
                    self.store.complete_model(con, operation_id, run_id, project_id, doc, version['id'] if version else None)
            execute_attempts(ledger, provider, settings, analysis_id, prompt, reserved, validator, persist,
                             before_attempt=before_attempt,
                             on_diagnostic=lambda run_id, stage, error, doc: self.store.save_diagnostic(
                                 project_id, analysis_id, run_id, stage, error, doc))
            return {'status': 'success', 'analysis_id': analysis_id, 'error': None}
        except Exception as error:
            if analysis_id is not None:
                try: ledger.fail_analysis(analysis_id, error.kind if isinstance(error, AIError) else type(error).__name__)
                except Exception: logger.error('research_analysis=%s failure persistence failed', analysis_id)
            logger.warning('research_analysis=%s type=%s', analysis_id, type(error).__name__)
            return {'status': 'failed', 'analysis_id': analysis_id,
                    'error': str(error) if isinstance(error, AIError) else '研究配置、预算、校验或保存失败；请检查调用记录，勿盲目重复。'}

    def interrupt_search(self, project_id, run_id):
        """用户确认原执行进程停止后解除运行锁；不重发或将未知 credits 改为零。"""
        self._writable(project_id)
        with self.store.transaction() as con:
            row = writable(con, project_id)
            changed = con.execute("UPDATE research_search_runs SET status='interrupted',finished_at=?,error_type='user_confirmed_interruption' WHERE id=? AND project_id=? AND status='running'",
                                  (utc_now(), run_id, project_id)).rowcount
            if changed: self._event(con, row, 'search_interrupted', {'run_id': run_id})

    def _event(self, con, project, event, details, now=None):
        record_action(self.store, con, project['id'], 'updated', project['status'], project['status'],
                      now or utc_now(), {'event': event, **details})
