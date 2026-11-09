"""工作台资料研究四区；所有外部调用只在明确按钮操作中执行。"""

from copy import deepcopy
from decimal import Decimal
import os
import json
from uuid import uuid4

import streamlit as st

from database.ai_store import AIStore
from services.ai.config import load_ai_settings
from services.ai.cost_tracker import to_units, money
from services.production.project_service import ProjectService
from services.research.guards import require_report
from services.research.schemas import CATEGORIES
from services.research.service import ResearchService
from services.research.queries import build_query, QUERY_BUILDER_VERSION
from services.research.temporal import source_time_context


def _action(operation, success):
    try:
        with st.spinner('正在执行，请等待结果；刷新不会重发已登记动作……'):
            result = operation()
        if isinstance(result, dict) and result.get('status') == 'failed':
            st.session_state['research_error_flash'] = result.get('error') or '操作未成功，请查看执行记录；不会自动重试。'
            st.rerun()
    except ValueError as error:
        st.error(str(error))
        return
    st.session_state['production_flash'] = success
    st.rerun()


def _model_button(svc, project_id, kind, operation, disabled=False):
    labels = {'plan': '生成研究计划', 'evidence': '整理证据与交叉核验', 'report': '生成研究报告'}
    slot = f'research_model_{kind}_{project_id}'
    ready, upper = False, None
    try:
        settings = svc.settings or load_ai_settings()
        ready = bool(settings.api_key) or svc.provider_factory is not None
        upper = to_units((Decimal(settings.max_request_bytes + 4096) * max(settings.input_hit_price, settings.input_miss_price)
            + Decimal(settings.max_output_tokens) * settings.output_price) / 1000000 * settings.cny_per_unit) * settings.max_attempts
    except ValueError as error:
        st.warning(str(error))
    if not ready:
        st.caption('未配置有效 DeepSeek 密钥，仍可编辑、确认和查看已有研究记录。')
    if upper is not None:
        st.caption(f'与原选题分析共用月度模型预算；本动作按输入上限及有限重试估算，预占最多 {money(upper)} 元。实际发送前逐次检查预算。')
    action_id = st.session_state.setdefault(slot, uuid4().hex)
    done_key = slot + '_done'
    confirmed = st.checkbox('确认本次模型操作可能产生费用', key=slot+'_spending', disabled=disabled or not ready)
    if st.button(labels[kind], key=slot+'_execute', disabled=disabled or not ready or not confirmed or done_key in st.session_state):
        def execute():
            result = operation(action_id)
            st.session_state[done_key] = result
            return result
        _action(execute, labels[kind] + '已完成，请人工审核。')
    if done_key in st.session_state:
        result = st.session_state[done_key]
        st.caption(f'该动作已处理：{result["status"]}；刷新不会重新调用。主动重新生成会追加历史并再次检查预算。')
        if st.button('准备新一轮' + labels[kind], key=slot+'_new', disabled=disabled):
            st.session_state[slot] = uuid4().hex
            st.session_state.pop(done_key, None)
            st.session_state.pop(slot+'_spending', None)
            st.rerun()


def _plan_editor(svc, project_id, version, disabled):
    vid = version['id']
    key = f'research_draft_{project_id}_{vid}'
    draft = deepcopy(st.session_state.get(key, version['content']))
    draft['query_builder_version'] = QUERY_BUILDER_VERSION
    draft['objective'] = st.text_area('研究目标', draft['objective'], key=f'research_objective_{project_id}_{vid}', disabled=disabled)
    draft['focus'] = st.text_area('研究重点', draft['focus'], key=f'research_focus_{project_id}_{vid}', disabled=disabled)
    dates = st.columns(2)
    draft['start_date'] = dates[0].text_input('开始日期（YYYY-MM-DD，留空不限）', draft['start_date'], key=f'research_start_{project_id}_{vid}', disabled=disabled)
    draft['end_date'] = dates[1].text_input('结束日期（YYYY-MM-DD，留空不限）', draft['end_date'], key=f'research_end_{project_id}_{vid}', disabled=disabled)
    draft['verify_facts'] = st.text_area('特别核实的事实（每行一项）', '\n'.join(draft['verify_facts']),
        key=f'research_verify_{project_id}_{vid}', disabled=disabled).splitlines()
    revision = st.session_state.get(key+'_revision', 0)
    for index, question in enumerate(draft['questions']):
        with st.container(border=True):
            prefix = f'research_q_{project_id}_{vid}_{revision}_{question["id"]}'
            st.caption('研究问题 ' + question['id'])
            question['question'] = st.text_input('问题', question['question'], key=prefix+'_text', disabled=disabled)
            question['keywords'] = st.text_area('搜索关键词（每行一项）', '\n'.join(question['keywords']), key=prefix+'_keywords', disabled=disabled).splitlines()
            override = st.text_input('自定义最终 query（留空使用关键词）', question.get('query_override', ''),
                key=prefix+'_query', disabled=disabled,
                help='修改后请保存为新计划并重新确认；不会自动拼接完整问题或来源类型。')
            if override or 'query_override' in question:
                question['query_override'] = override
            try:
                st.caption('实际发送的 query 预览')
                st.code(build_query(question), language=None)
            except ValueError as error:
                st.error(str(error))
            question['source_types'] = st.text_input('推荐来源类型（中文逗号分隔）', '，'.join(question['source_types']),
                key=prefix+'_types', disabled=disabled).replace(',', '，').split('，')
            domains = st.text_input('优先官方域名（每项以逗号分隔，可留空；确认后作为搜索范围）',
                ','.join(question['domains']), key=prefix+'_domains', disabled=disabled)
            question['domains'] = [v.strip() for v in domains.replace('，', ',').split(',') if v.strip()]
            if st.button('删除此研究问题', key=prefix+'_delete', disabled=disabled or len(draft['questions']) <= 1):
                draft['questions'].pop(index)
                st.session_state[key] = draft
                st.session_state[key+'_revision'] = revision + 1
                st.rerun()
    st.session_state[key] = draft
    if st.button('添加研究问题', key=f'research_question_add_{project_id}', disabled=disabled or len(draft['questions']) >= 10):
        draft['questions'].append({'id': 'q_'+uuid4().hex[:8], 'question': '', 'keywords': [], 'source_types': ['官方文档'], 'domains': []})
        st.session_state[key] = draft
        st.session_state[key+'_revision'] = revision + 1
        st.rerun()
    dirty = draft != version['content']
    if dirty: st.warning('研究计划有未保存修改，搜索入口已隐藏。请保存新版本并重新确认。')
    if st.button('保存研究计划为新版本', key=f'research_plan_save_{project_id}', disabled=disabled):
        _action(lambda: svc.save_plan(project_id, draft), '研究计划已保存为新版本，需重新确认。')
    if st.button('确认当前研究计划', key=f'research_plan_confirm_{project_id}', disabled=disabled or dirty):
        _action(lambda: svc.confirm_plan(project_id, vid, uuid4().hex), '当前计划版本已确认；点击执行搜索后才会联网。')
    return draft, dirty


def _history(svc, project_id, kind, disabled):
    with st.expander('研究计划历史' if kind == 'plan' else '研究报告历史'):
        history = svc.versions.history(project_id, 'research', object_key=kind)
        if not history:
            st.caption('尚无历史版本。')
            return
        indexed = {v['id']: v for v in history}
        selected = st.selectbox('选择历史版本', list(indexed), format_func=lambda value: f'v{indexed[value]["version_number"]} · {indexed[value]["created_at"]}',
            key=f'research_history_{kind}_{project_id}')
        st.json(indexed[selected]['content'], expanded=False)
        confirmed = st.checkbox('将所选内容追加为新版本，原确认不沿用', key=f'research_history_confirm_{kind}_{project_id}', disabled=disabled)
        if st.button('恢复历史内容为新版本', key=f'research_history_restore_{kind}_{project_id}', disabled=disabled or not confirmed):
            _action(lambda: svc.versions.restore(project_id, selected, object_id=indexed[selected]['object_id']), '历史内容已追加为新版本，请重新审核确认。')


def _search_area(svc, project_id, plan, draft, dirty, disabled):
    runs = svc.store.runs(project_id)
    if plan and svc.plan_is_confirmed(project_id) and not dirty:
        provider = svc.search_provider
        available = provider.available if provider is not None else bool(os.getenv('TAVILY_API_KEY', '').strip())
        if not available: st.warning('未配置 TAVILY_API_KEY。不会搜索，历史与原有功能继续可用。')
        count = len(plan['content']['questions'])
        st.caption(f'已确认计划版本 ID：{plan["id"]}。最多 {count} 次 basic 搜索、20 个 URL、1 次提取；预览上限 {count+4} credits，不计入模型人民币预算。')
        allow_unknown = st.checkbox('额度查询不可用时，仍按上述调用上限执行', key=f'research_unknown_quota_{project_id}', disabled=disabled)
        slot = f'research_search_action_{project_id}_{plan["id"]}'
        action_id = st.session_state.setdefault(slot, uuid4().hex)
        processed = any(run['action_id'] == action_id for run in runs)
        if st.button('执行已确认计划的搜索与提取', key=f'research_search_{project_id}', disabled=disabled or not available or processed):
            _action(lambda: svc.search(project_id, plan['id'], action_id, expected_plan=draft,
                allow_unknown_quota=allow_unknown), '搜索操作已结束，请查看成功、失败及提取状态。')
        if processed and st.button('准备主动重新搜索', key=f'research_search_new_{project_id}', disabled=disabled):
            st.session_state[slot] = uuid4().hex
            st.rerun()
    else:
        st.caption('只有保存并明确确认当前计划后，才显示联网搜索入口。')
    usage = svc.store.search_usage(project_id)
    st.caption(f'搜索/提取调用 {usage["calls"]} 次 · 已知 {usage["known_credits"]} credits · 用量未知 {usage["unknown_calls"]} 次。API返回0按原值展示，不代表最终账单免费。')
    if runs:
        st.dataframe([{'研究 ID': r['id'], '计划版本': r['plan_version_id'], '状态': r['status'],
            '开始（UTC）': r['started_at'], '完成（UTC）': r['finished_at'] or '尚未完成',
            '错误类型': r['error_type'] or '无'} for r in runs], hide_index=True, width='stretch')
        calls = svc.store.calls(project_id)
        st.dataframe([{'研究 ID': c['run_id'], '操作': c['operation'], '研究问题': c['question_id'] or '整轮',
            '状态': c['status'], 'credits': c['credits'] if c['credits'] is not None else '未知',
            '错误类型': c['error_type'] or '无'} for c in calls], hide_index=True, width='stretch')
        latest = runs[0]
        if latest['status'] == 'running':
            confirmed = st.checkbox('我已确认原搜索进程已停止，不会继续发送请求', key=f'research_stop_confirm_{project_id}', disabled=disabled)
            if st.button('记录搜索已中断', key=f'research_interrupt_{project_id}', disabled=disabled or not confirmed):
                _action(lambda: svc.interrupt_search(project_id, latest['id']), '中断状态已记录；未知费用和历史保留。')


def _evidence_area(svc, project_id, disabled):
    runs = svc.store.runs(project_id)
    if not runs:
        st.caption('尚无搜索结果；证据只从实际保存的来源整理。')
        return
    indexed = {r['id']: r for r in runs}
    run_id = st.selectbox('查看研究运行', list(indexed), key=f'research_run_view_{project_id}',
        format_func=lambda value: f'#{value} · {indexed[value]["status"]} · 计划 {indexed[value]["plan_version_id"]}')
    sources = svc.store.sources(project_id, run_id)
    st.caption('新证据每轮最多10条、每题最多2条；允许0条，无证据问题须逐题记录缺口。')
    dimensions = {'text': '正文变化', 'title': '标题变化', 'published_at': '日期变化',
        'snippet': '摘录变化', 'extraction_failed': '本轮提取失败', 'extraction_recovered': '本轮恢复提取'}
    for change in svc.store.source_changes(project_id, run_id):
        st.warning(f'保存的来源快照 S{change["old_source_id"]} → S{change["new_source_id"]}：'
            + '、'.join(dimensions[d] for d in change['changes'])+'。内容差异不代表事实变化；尚未独立核验当前原文。')
    st.caption(f'来源 {len(sources)} 条 · 提取成功 {sum(s["extraction_status"] == "success" for s in sources)} · 提取失败 {sum(s["extraction_status"] != "success" for s in sources)}')
    for source in sources:
        with st.expander(f'来源 S{source["id"]} · {source["domain"]}'):
            st.text(source['title'])
            context = source_time_context(source, indexed[run_id]['started_at'][:10])
            st.caption(context['label'])
            st.caption(f'来源日期原值：{source["published_at"] or "unknown"} · 本地首次保存：{source["searched_at"]}（UTC）· {source["provider"]}')
            st.caption('原文修改时间：unknown · 服务商快照时间：unknown')
            st.link_button('打开原始来源', source['url'])
            st.write('**原始搜索摘录**')
            st.text(source['snippet'])
            if source['extraction_status'] == 'success':
                st.write('**服务商提取文本（不保证包含整页全部内容）**')
                st.text(source['text'])
            else: st.warning('正文提取失败，仅有搜索摘录；未绕过访问限制。')
    _model_button(svc, project_id, 'evidence', lambda action: svc.organize_evidence(project_id, run_id, action),
        disabled=disabled or not sources or indexed[run_id]['status'] not in ('success', 'partial'))
    with st.expander('研究模型失败诊断（已脱敏）'):
        st.dataframe([{'分析': d['analysis_id'], '尝试': d['attempt_run_id'], '阶段': d['stage'],
            '错误代码': d['code'], '路径': d['path_json'], '条目': d['item_index'],
            '结构样本已截断': bool(d['document_truncated'])} for d in svc.store.diagnostics(project_id)],
            hide_index=True, width='stretch')
    batches = svc.store.rows('''SELECT id,created_at FROM topic_analyses WHERE production_project_id=?
        AND purpose='research_evidence' AND status='success' AND json_extract(input_json,'$.run_id')=? ORDER BY id DESC''', (project_id, run_id))
    if not batches: return
    analysis_id = st.selectbox('证据历史批次', [b['id'] for b in batches], key=f'research_evidence_batch_{project_id}')
    operation = svc.store.rows('SELECT analysis_json FROM topic_analyses WHERE id=?', (analysis_id,))[0]
    for gap in json.loads(operation['analysis_json'])['gaps']:
        st.caption('证据缺口：'+gap)
    for item in svc.store.evidence(project_id, analysis_id):
        with st.container(border=True):
            st.caption(f'E{item["id"]} · {item["question_id"]} · {CATEGORIES[item["category"]]}（AI 分类，待人工审核）')
            st.text('AI 摘要：' + item['summary'])
            if item['inference']: st.text('AI 推断：' + item['inference'])
            st.text('核验说明：' + item['verification'])
            st.caption(f'时间用途：{item["time_scope"]} · 数据所属周期：{item["data_period"]}')
            for link in item['links']:
                st.text(f'S{link["source_id"]} 来源原文（{"提取文本" if link["field"] == "text" else "搜索摘录"}）：{link["quote"]}')
                st.caption(f'E{item["id"]} → S{link["source_id"]}：{link["time_context"]["label"]}')
                st.link_button(f'查看 S{link["source_id"]} 原始链接', link['url'])


def _report_area(svc, project_id, disabled):
    from services.research.report_confirmation import LocalReportReviewSession
    reports = svc.reports()
    try:
        draft = reports.draft(project_id)
    except ValueError as error:
        draft = None
        st.caption(str(error))
    _model_button(svc, project_id, 'report', lambda action: svc.generate_report(project_id, action),
                  disabled=disabled or draft is None)
    report = svc.current_report(project_id)
    state = reports.state(project_id)
    labels = {'not_generated': '尚未生成', 'validated_pending_confirmation': '校验通过，待人工确认',
              'confirmed': '已确认', 'stale': '已失效，需要重新生成或确认'}
    st.caption('报告状态：' + labels[state['current_report_state']])
    attempt_labels = {'not_generated': '尚未生成', 'running': '生成中',
        'generated_pending_validation': '已生成，待校验', 'validation_failed': '校验失败',
        'provider_failed': '模型调用失败', 'persistence_failed': '报告保存失败',
        'uncertain': '状态待确认', 'failed': '生成失败', 'success': '生成并保存成功'}
    st.caption('最近生成尝试：' + attempt_labels[state['latest_attempt_state']])
    if report is None:
        st.caption('尚无研究报告。不会使用模拟内容填充。')
        if draft is None: return
    elif report['content'].get('contract_version') != 'research-report-v3':
        st.warning('历史报告，未按v3校验；仍可读取，不能用于新的制作准入。')
        st.json(report['content'], expanded=False)
        _history(svc, project_id, 'report', disabled)
        return
    if report:
        vid = report['id']
        st.caption(f'报告 v{report["version_number"]} · 版本 ID {vid} · {report["created_at"]}（UTC）')
        document = report['content']['document']
        st.text(document['overview'])
        st.text(document['objective'])
        for category, label in (('verified', '已验证事实'), ('single_source', '单一来源事实'),
            ('opinion', '来源观点'), ('inference', 'AI推断'), ('disputed', '存在争议'),
            ('unverified', '待验证信息'), ('gaps', '研究缺口')):
            with st.expander(label):
                rows = document['categories'][category]
                if not rows: st.caption('无条目')
                for row in rows:
                    if category == 'gaps':
                        st.text(row['question_id'] + '：' + row['detail'])
                        continue
                    st.text(row['text'])
                    temporal = row['temporal']
                    st.caption('时间性质：' + temporal['temporal_type'] + ' · 财季标签：' + temporal['label_raw'])
                    for citation in row['citations']:
                        eid = row['evidence_ids'][0]
                        st.caption(f'E{eid} → S{citation["source_id"]}：{citation["region"]} '
                                   f'[{citation["start"]},{citation["end"]})')
                        st.text(citation['quote'])
                        st.link_button(f'E{eid} → S{citation["source_id"]} 原始来源', citation['url'])
        with st.expander('程序渲染的结论'):
            for conclusion in document['conclusions']: st.text(conclusion['text'])
    else:
        vid = 'new'
    if draft is None: return
    stale = state['current_report_state'] == 'stale'
    if stale: st.warning('报告依据或校验绑定已变化。请重新生成；旧确认不能进入后续制作。')
    original = report['content']['candidate_document'] if report else draft['candidate_document']
    st.caption('可调整证据/缺口顺序及允许模板，正文、数值、时间和等级由程序生成。')
    raw = st.text_area('报告组织结构（仅引用与模板）', json.dumps(original, ensure_ascii=False, indent=2),
                       key=f'research_report_structure_{project_id}_{vid}', disabled=disabled or stale, height=220)
    candidate, invalid = None, False
    try:
        candidate = json.loads(raw)
    except (ValueError, TypeError):
        st.error('报告组织结构不是有效JSON，请先修正。')
        invalid = True
    dirty = candidate != original
    if st.button('保存报告为新版本', key=f'research_report_save_{project_id}', disabled=disabled or stale or invalid):
        _action(lambda: svc.save_report(project_id, candidate,
            expected_previous_report_version_id=report['id'] if report else None), '报告已校验并保存为新版本，请人工确认。')
    if not report: return
    review_key = f'research_report_review_{project_id}_{vid}'
    reviewed = st.checkbox('我已审核本版本的事实引用、研究缺口和争议，确认当前报告', key=review_key,
                           disabled=disabled or stale or dirty or invalid)
    if st.button('确认研究报告', key=f'research_report_confirm_{project_id}',
                 disabled=disabled or stale or dirty or invalid or not reviewed):
        def confirm():
            session = st.session_state.setdefault('local_report_review_session', LocalReportReviewSession())
            intent = session.reviewed(project_id, report, checked=reviewed)
            svc.confirm_report(project_id, vid, uuid4().hex, intent=intent)
        _action(confirm, '研究报告已确认，可以人工进入脚本阶段。')
    if state['current_report_state'] == 'confirmed' and st.button('进入脚本制作阶段（仅调整人工状态）',
        key=f'research_next_stage_{project_id}', disabled=disabled):
        _action(lambda: ProjectService(svc.store).set_status(project_id, 'scripting'), '已进入脚本制作阶段；脚本功能尚未开发。')
    _history(svc, project_id, 'report', disabled)


def show_research(store, project):
    svc = ResearchService(store)
    pid = project['id']
    disabled = project['status'] in ('paused', 'archived')
    st.subheader('资料研究')
    st.caption('模型结果和证据分类均需人工审核。确认计划不会自动搜索；页面刷新不会调用 API。')
    if 'research_error_flash' in st.session_state:
        st.error(st.session_state.pop('research_error_flash'))
    with svc.store._connection() as con:
        if con.execute('SELECT 1 FROM ai_budget_settings WHERE id=1').fetchone():
            from services.ai.cost_tracker import month_key
            budget = AIStore._budget(con, month_key())
            st.caption(f'共用模型月预算：{money(budget["limit_units"])} 元 · 可用：{money(budget["remaining_units"])} 元 · {budget["warning"]}；预算修改仍在 AI 选题分析页。')
    plan, draft, dirty = svc.current_plan(pid), None, False
    with st.expander('1. 研究计划', expanded=True):
        _model_button(svc, pid, 'plan', lambda action: svc.generate_plan(pid, action), disabled)
        if plan:
            st.caption(f'计划 v{plan["version_number"]} · 版本 ID {plan["id"]} · {"已确认" if svc.plan_is_confirmed(pid) else "待确认"}')
            draft, dirty = _plan_editor(svc, pid, plan, disabled)
        else: st.caption('先生成或保存研究计划；本区不调用 Tavily。')
        _history(svc, pid, 'plan', disabled)
    with st.expander('2. 搜索执行', expanded=True):
        _search_area(svc, pid, plan, draft, dirty, disabled)
    with st.expander('3. 证据整理'):
        _evidence_area(svc, pid, disabled)
    with st.expander('4. 研究报告', expanded=True):
        _report_area(svc, pid, disabled)
