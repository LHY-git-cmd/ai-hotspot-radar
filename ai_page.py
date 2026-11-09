"""独立中文 AI 选题页；只有明确的分析确认操作才触发 Provider。"""

from decimal import Decimal
from uuid import uuid4

import streamlit as st

from database.ai_store import AIStore, IDEA_STATUSES
from services.ai.analyzer import Analyzer
from services.ai.config import AISettings, load_ai_settings
from services.ai.cost_tracker import money
from services.ai.deepseek_client import DeepSeekProvider


def show_budget(store: AIStore) -> dict:
    """预算展示和主动设置均只读写数据库，不调用模型。"""
    budget = store.budget()
    st.caption(f'账期：{budget["month"]}（北京时间）· 所有费用均为配置价格下的估算，不是最终账单。')
    columns = st.columns(4)
    for column, label, value in zip(columns, ('月预算上限', '已计量/核对费用', '待确认预占', '可用预算'),
            (budget['limit_units'], budget['estimated_units'], budget['held_units'], budget['remaining_units'])):
        column.metric(label + '（元）', money(value))
    if budget['warning'] != '正常':
        st.warning(f'预算{budget["warning"]}：占用 {money(budget["occupied_units"])} 元；'
                   '达到上限后停止新 AI 调用，采集与历史功能继续可用。')
    st.caption(f'服务商已回报的输入 Token：{budget["input_tokens"]}；输出 Token：{budget["output_tokens"]}；'
               f'用量不完整的尝试：{budget["unknown_usage_runs"]} 次。未知用量未按零收费。')
    with st.expander('月预算设置'):
        with st.form('ai_budget_form'):
            value = st.text_input('月预算上限（元）', money(budget['limit_units']), key='ai_budget_input')
            if st.form_submit_button('保存月预算', key='ai_budget_save'):
                try:
                    store.set_budget(Decimal(value))
                    st.rerun()
                except (ValueError, ArithmeticError):
                    st.error('请输入有限非负金额，0 元表示暂停新调用。')
    return budget


def _reset_confirmation() -> None:
    """为主动的下一轮操作生成新确认动作；重复提交旧动作不收费。"""
    for key in ('ai_single_signature', 'ai_single_action'):
        st.session_state.pop(key, None)
    st.session_state['ai_single_confirm'] = False


def show_analysis_controls(analyzer: Analyzer, ready: bool, budget: dict) -> int | None:
    """单条和批量分别确认，动作 ID 持久到当前会话，数据库再次保证幂等。"""
    items = analyzer.store.ranked_items()
    if not items:
        st.info('暂无热点。先在热点排行页面手动采集。')
        return None
    titles = {item['id']: item['title'] for item in items}
    candidates = analyzer.candidates()
    st.write('**自动筛选候选**')
    if candidates:
        st.dataframe([{'热点 ID': item['id'], '标题': item['title'], '来源': item['source'],
                       'A 分': round(item['rating']['heat_score'], 1),
                       'B 分': round(item['rating']['video_score'], 1)} for item in candidates],
                      hide_index=True, width='stretch')
    else:
        st.info('没有新的有效候选：可能已有分析、正在处理或评分已过期。可去排行页离线重算，或手动选择热点。')

    selected = st.selectbox('手动选择热点', list(titles), format_func=lambda value: f'{value} · {titles[value]}', key='ai_hotspot')
    force = st.checkbox('主动重新分析（将产生新的 API 调用费用，保留旧分析）', key='ai_force')
    material_key = analyzer.fingerprint(analyzer.materials(selected))
    signature = (selected, force, material_key)
    if st.session_state.get('ai_single_signature') != signature:
        st.session_state['ai_single_signature'] = signature
        st.session_state['ai_single_action'] = uuid4().hex
        st.session_state['ai_single_confirm'] = False
    preview = analyzer.preview([selected])
    st.caption(f'单条：最多 {preview["max_attempts"]} 次 HTTP 尝试；最坏预占 {money(preview["max_reserved_units"])} 元。'
               '同版本成功缓存直接读取，不调用 API；仅重新确认不会自动发送。')
    confirmed = st.checkbox('我已确认本次分析可能产生费用', key='ai_single_confirm')
    if st.button('分析选中热点', key='ai_analyze', type='primary',
                 disabled=not ready or not confirmed or budget['remaining_units'] <= 0):
        with st.spinner('正在分析，请勿重复操作；这可能需要一两分钟……'):
            st.session_state['ai_last_result'] = analyzer.analyze(selected,
                st.session_state['ai_single_action'], force=force, expected_cache_key=material_key)
        # 请求结果已持久化，重跑只更新本地统计，不会重复提交同一动作。
        st.rerun()
    st.button('准备新一轮分析', key='ai_prepare', on_click=_reset_confirmation,
              help='同一确认动作不会再次付费；如确实需要再调用，请准备新动作后重新确认。')
    result = st.session_state.get('ai_last_result')
    if result:
        if result['status'] == 'success':
            st.success('已读取成功缓存，未发起新调用。' if result['cache_hit'] else '分析已保存，三个选题角度和历史均已保留。')
        else:
            st.error(result['error'])

    with st.expander('批量分析候选（需要单独确认）'):
        ids = [item['id'] for item in candidates]
        keys = {item_id: analyzer.fingerprint(analyzer.materials(item_id)) for item_id in ids}
        batch_signature = tuple(keys.items())
        if st.session_state.get('ai_batch_signature') != batch_signature:
            st.session_state['ai_batch_signature'] = batch_signature
            st.session_state['ai_batch_action'] = uuid4().hex
            st.session_state['ai_batch_confirm'] = False
        batch = analyzer.preview(ids)
        st.write(f'本批 {batch["analyses"]} 个热点，最多 {batch["max_attempts"]} 次 HTTP 尝试；'
                 f'最坏预占 {money(batch["max_reserved_units"])} 元，可用预算 {money(budget["remaining_units"])} 元。')
        confirmed_batch = st.checkbox('确认按上述候选清单和费用上界批量分析', key='ai_batch_confirm')
        if st.button('执行批量分析', key='ai_batch', disabled=not ready or not ids or not confirmed_batch
                     or budget['remaining_units'] <= 0):
            results = []
            progress = st.progress(0, text='准备分析候选')
            for position, item_id in enumerate(ids, 1):
                result = analyzer.analyze(item_id, f'{st.session_state["ai_batch_action"]}:{item_id}',
                                          expected_cache_key=keys[item_id])
                results.append({'热点': titles[item_id], '状态': result['status'],
                                '结果': result['error'] or ('读取缓存' if result['cache_hit'] else '成功保存')})
                progress.progress(position / len(ids), text=f'已处理 {position}/{len(ids)}')
            st.session_state['ai_batch_results'] = results
            st.rerun()
        if st.session_state.get('ai_batch_results'):
            st.dataframe(st.session_state['ai_batch_results'], hide_index=True, width='stretch')
    return selected


def show_analysis_history(store: AIStore, hotspot_id: int) -> None:
    """展示成功历史与可执行的三个角度，所有 AI 文本以普通文本显示。"""
    analyses = store.analyses(hotspot_id)
    if not analyses:
        st.info('此热点还没有成功分析，调用失败不会显示为成功选题。')
        return
    indexed = {row['id']: row for row in analyses}
    selected = st.selectbox('历史分析', list(indexed),
        format_func=lambda value: f'#{value} · {indexed[value]["created_at"]} · {indexed[value]["model"]}', key='ai_history')
    analysis = indexed[selected]
    document = analysis['document']
    st.warning(analysis['evidence_status'])
    labels = {'summary': '通俗解读', 'what_happened': '发生了什么', 'why_now': '为什么现在关注',
              'target_audience': '目标观众', 'audience_value': '观众价值', 'suitability_reason': '短视频适用原因'}
    st.caption('适合短视频：' + ('是（模型建议）' if document['video_suitability'] else '否（模型建议）'))
    for field, label in labels.items():
        st.write(f'**{label}**')
        st.text(document[field])
    with st.expander('证据缺口与事实风险', expanded=True):
        for value in document['evidence_gaps'] + document['factual_risks']:
            st.text('• ' + value)
    st.caption(f'提示词：{analysis["prompt_version"]} · 结构：{analysis["schema_version"]} · '
               f'分析版本：{analysis["analysis_version"]} · 未自动访问材料链接或亲测产品。')
    with st.expander('本次实际提供的材料'):
        import json
        st.json(json.loads(analysis['input_json']), expanded=False)
    status_label = st.selectbox('选题状态筛选', ['全部状态', *IDEA_STATUSES.values()], key='ai_idea_filter')
    status = next((key for key, label in IDEA_STATUSES.items() if label == status_label), '')
    for idea in store.ideas(selected, status=status):
        content = idea['document']
        with st.container(border=True):
            st.subheader(idea['title'])
            st.caption(f'{idea["angle_type"]} · 难度：{idea["difficulty"]} · 当前状态：{IDEA_STATUSES[idea["status"]]}')
            st.text('备用标题：' + ' / '.join(content['alternative_titles']))
            st.text('目标观众：' + content['target_audience'])
            st.write('**开场钩子**')
            st.text(content['hook'])
            st.write(f'**结构大纲 · {sum(part["seconds"] for part in content["outline"])} 秒**')
            st.dataframe([{'时长（秒）': part['seconds'], '内容': part['content']} for part in content['outline']],
                          hide_index=True, width='stretch')
            for label, values in [('素材准备', content['materials']), ('事实核验清单', content['verification_checklist']),
                                  ('制作风险', content['risks'])]:
                st.write(f'**{label}**')
                for value in values:
                    st.text('• ' + value)
            st.text('推荐理由：' + content['recommendation_reason'])
            columns = st.columns(len(IDEA_STATUSES))
            for column, (status_value, label) in zip(columns, IDEA_STATUSES.items()):
                if column.button(label, key=f'idea_{idea["id"]}_{status_value}', disabled=idea['status'] == status_value):
                    store.set_idea_status(idea['id'], status_value)
                    st.rerun()
            with st.expander('状态操作历史'):
                actions = store.actions(idea['id'])
                if actions:
                    st.dataframe([{'时间': row['created_at'], '原状态': IDEA_STATUSES[row['previous_status']],
                                   '新状态': IDEA_STATUSES[row['action']]} for row in actions],
                                  hide_index=True, width='stretch')
                else:
                    st.caption('尚无状态变更。')


def show_usage_history(store: AIStore) -> None:
    """账单核对是显式用户操作；不因错误或刷新自动释放预占。"""
    with st.expander('API 用量、费用与待确认任务'):
        runs = store.runs()
        if runs:
            st.dataframe([{'调用 ID': row['id'], '分析 ID': row['analysis_id'], '尝试': row['attempt'],
                '用途': {'topic': '视频选题分析', 'research_plan': '研究计划', 'research_evidence': '研究证据', 'research_report': '研究报告'}.get(row['purpose'], row['purpose']),
                '制作任务 ID': str(row['production_project_id']) if row['production_project_id'] is not None else '无',
                '模型': row['model'], '状态': row['status'], '错误类型': row['error_type'] or '无',
                '输入 Token': str(row['input_tokens']) if row['input_tokens'] is not None else '未知',
                '输出 Token': str(row['output_tokens']) if row['output_tokens'] is not None else '未知',
                '费用（元，估算/人工核对）': money(row['manual_cost_units'] if row['manual_cost_units'] is not None
                    else row['estimated_cost_units']) if row['estimated_cost_units'] is not None
                    or row['manual_cost_units'] is not None else '待确认',
                '预占上界（元）': money(row['reserved_units']), '价格版本': row['price_version'],
                '时间': row['created_at']} for row in runs], hide_index=True, width='stretch')
        else:
            st.caption('尚无模型调用。')
        unresolved = store.unresolved()
        if unresolved:
            st.warning('存在运行中或费用待确认任务。不要在原任务仍运行时解除锁；程序重启不会自动重发。')
            task_id = st.selectbox('待确认分析任务', [row['id'] for row in unresolved], key='ai_pending_task')
            stopped = st.checkbox('我已确认原任务已停止，不再有后台请求', key='ai_stopped_confirm')
            if st.button('确认该任务已中断', key='ai_ack_interrupted', disabled=not stopped):
                store.acknowledge_interrupted(task_id)
                st.rerun()
        unknown = [row for row in runs if row['estimated_cost_units'] is None and row['manual_cost_units'] is None]
        if unknown:
            run_id = st.selectbox('已核对的调用 ID', [row['id'] for row in unknown], key='ai_unknown_run')
            amount = st.text_input('服务商账单核对金额（人民币元）', key='ai_resolve_amount')
            reason = st.text_area('账单核对依据（至少8个字符）', key='ai_resolve_reason')
            reviewed = st.checkbox('确认已核对服务商账单，此操作不会删除原始调用记录', key='ai_review_confirm')
            if st.button('保存费用核对结果', key='ai_resolve', disabled=not reviewed):
                try:
                    store.resolve_cost(run_id, Decimal(amount), reason)
                    st.rerun()
                except (ValueError, ArithmeticError) as error:
                    st.error(str(error) if isinstance(error, ValueError) else '核对金额无效。')


def show_ai_page(path) -> None:
    """无密钥或配置错误也允许本地历史和预算查看，禁止误触发模型。"""
    st.title('AI 选题分析')
    st.write('从已有热点规划三个制作角度。AI 结果未经独立核验，不修改 A/B 评分。')
    config_error = None
    try:
        settings = load_ai_settings()
    except ValueError as error:
        config_error = str(error)
        settings = AISettings()
    store = AIStore(path, settings)
    analyzer = Analyzer(store, DeepSeekProvider(settings), settings)
    ready = bool(settings.api_key) and config_error is None
    st.caption(f'模型：{settings.model} · 输出模式：{settings.output_mode} · 单价口径：{settings.price_version}')
    if config_error:
        st.error(config_error)
    if not settings.api_key:
        st.warning('未配置 AI 密钥；仍可查看已有分析、选题、成本和热点排行。')
    budget = show_budget(store)
    selected = show_analysis_controls(analyzer, ready, budget)
    if selected is not None:
        show_analysis_history(store, selected)
    show_usage_history(store)
