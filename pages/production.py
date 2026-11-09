"""视频制作工作台；研究 API 仅由研究页面的明确操作触发。"""

import streamlit as st

from database.production_store import ProductionStore
from services.production.action_service import ACTION_LABELS, action_label
from services.production.project_service import ProjectService, STATUSES, NORMAL_STATUSES
from services.production.version_service import VersionService, CONTENT_TYPES, VERSION_SOURCES


def _perform(operation, message):
    """只在明确点击后执行写入；重跑立即展示更新后的列表与状态。"""
    try:
        operation()
    except ValueError as error:
        st.error(str(error))
        return
    st.session_state['production_flash'] = message
    st.rerun()


def _creation(store, projects):
    with st.expander('从已有选题创建制作任务', expanded=not store.projects()):
        ideas = store.ideas()
        available = {idea['id']: idea for idea in ideas if idea['active_project_id'] is None}
        if not ideas:
            st.info('暂无视频选题，请先在“AI 选题分析”中生成选题；工作台不会自动调用 AI。')
            return
        if not available:
            st.info('现有选题均已有有效制作任务，可从列表打开；原任务归档后才能新建。')
            return
        with st.form('production_create_form'):
            idea_id = st.selectbox('来源视频选题', list(available),
                format_func=lambda value: f'#{value} · {available[value]["title"]}', key='production_idea')
            name = st.text_input('任务名称', key='production_name')
            notes = st.text_area('备注', key='production_create_notes')
            submitted = st.form_submit_button('创建制作任务', key='production_create')
        if submitted:
            def create():
                project = projects.create(idea_id, name, notes)
                st.session_state['production_detail'] = project['id']
            _perform(create, '制作任务已创建。')


def _project_list(store):
    st.subheader('制作任务列表')
    view = st.selectbox('任务范围', ['有效任务', '归档历史'], key='production_archive_filter')
    rows = store.projects(archived=view == '归档历史')
    if not rows:
        st.info('暂无归档任务。' if view == '归档历史' else '暂无有效制作任务。')
        return
    st.dataframe([{'任务 ID': p['id'], '任务名称': p['name'], '来源选题': p['idea_title'],
        '当前状态': STATUSES[p['status']], '创建时间（UTC）': p['created_at'],
        '更新时间（UTC）': p['updated_at']} for p in rows], hide_index=True, width='stretch')
    indexed = {p['id']: p for p in rows}
    selected = st.selectbox('选择制作任务', list(indexed),
        format_func=lambda value: f'#{value} · {indexed[value]["name"]}', key='production_list_selection')
    if st.button('查看详情', key='production_open'):
        st.session_state['production_detail'] = selected
        st.rerun()


def _version_history(store, versions, project):
    project_id = project['id']
    archived = project['status'] == 'archived'
    with st.expander('历史版本'):
        objects = {obj['id']: obj for obj in store.objects(project_id)}
        if not objects:
            st.info('尚无内容版本。后续模块启用后可在此查看；本期不会生成内容。')
            return
        object_id = st.selectbox('内容对象', list(objects), key=f'production_object_{project_id}',
            format_func=lambda value: f'{CONTENT_TYPES[objects[value]["content_type"]]} · {objects[value]["object_key"]}')
        obj = objects[object_id]
        history = versions.history(project_id, obj['content_type'], object_key=obj['object_key'])
        if not history:
            st.info('此对象尚无已保存版本。')
            return
        indexed = {v['id']: v for v in history}
        st.dataframe([{'版本': v['version_number'], '来源': VERSION_SOURCES[v['source']],
            '说明': v['note'], '创建时间（UTC）': v['created_at'],
            '恢复源版本 ID': str(v['restored_from_version_id']) if v['restored_from_version_id'] is not None else '无'}
            for v in history], hide_index=True, width='stretch')
        selected = st.selectbox('查看版本', list(indexed), key=f'production_version_{project_id}',
            format_func=lambda value: f'v{indexed[value]["version_number"]} · {indexed[value]["created_at"]}')
        version = versions.details(project_id, selected)
        st.caption(f'版本 ID：{selected} · 来源：{VERSION_SOURCES[version["source"]]}')
        st.text(version['note'] or '无版本说明')
        if isinstance(version['content'], str):
            st.text(version['content'])
        else:
            st.json(version['content'], expanded=True)
        note = st.text_input('恢复说明', key=f'production_restore_note_{project_id}', disabled=archived)
        confirmed = st.checkbox('确认将所选历史内容追加为新版本，原有版本全部保留',
            key=f'production_restore_confirm_{project_id}', disabled=archived)
        if st.button('恢复为新版本', key=f'production_restore_{project_id}', disabled=archived or not confirmed):
            def restore():
                versions.restore(project_id, selected, object_id=object_id, note=note)
                # 新动作需要重新确认，重跑或双击不应沿用旧确认。
                st.session_state.pop(f'production_restore_confirm_{project_id}', None)
            _perform(restore, '历史内容已追加为新版本，原版本已保留。')


def _details(store, projects, versions, project_id):
    project = store.get_project(project_id)
    if project is None:
        st.warning('制作任务不存在，请返回列表重新选择。')
        return
    archived, paused = project['status'] == 'archived', project['status'] == 'paused'
    st.subheader('制作任务详情')
    st.text(project['name'])
    st.caption(f'任务 ID：{project_id} · 人工管理状态：{STATUSES[project["status"]]}')
    st.text(f'来源选题 #{project["idea_id"]}：{project["idea_title"]}')
    st.caption(f'创建：{project["created_at"]} · 更新：{project["updated_at"]}（UTC）')
    if archived:
        st.info('此任务已归档，仅保留历史查看；原选题可以创建新的制作任务。')
    with st.form(f'production_edit_form_{project_id}'):
        name = st.text_input('任务名称', value=project['name'], key=f'production_edit_name_{project_id}', disabled=archived)
        notes = st.text_area('备注', value=project['notes'], key=f'production_notes_{project_id}', disabled=archived)
        if st.form_submit_button('保存基本信息', key=f'production_save_{project_id}', disabled=archived):
            _perform(lambda: projects.edit(project_id, name, notes), '任务基本信息已保存。')
    st.write('**状态管理**')
    st.caption('阶段由你人工标记，不表示 AI 已执行或内容已生成。')
    with st.form(f'production_status_form_{project_id}'):
        normal = list(NORMAL_STATUSES)
        current = project['resume_status'] if paused else project['status']
        selected = st.selectbox('制作阶段', normal, index=normal.index(current) if current in normal else 0,
            format_func=NORMAL_STATUSES.get, key=f'production_status_{project_id}', disabled=archived or paused)
        if st.form_submit_button('保存制作状态', key=f'production_status_save_{project_id}', disabled=archived or paused):
            _perform(lambda: projects.set_status(project_id, selected), '制作状态已保存。')
    if paused:
        st.caption('恢复后回到：' + STATUSES[project['resume_status']])
    pause_column, resume_column = st.columns(2)
    if pause_column.button('暂停任务', key=f'production_pause_{project_id}', disabled=archived or paused):
        _perform(lambda: projects.pause(project_id), '任务已暂停，原制作阶段已保留。')
    if resume_column.button('恢复任务', key=f'production_resume_{project_id}', disabled=not paused):
        _perform(lambda: projects.resume(project_id), '任务已恢复到暂停前的制作阶段。')
    confirmed = st.checkbox('确认归档：任务将只读保留历史，本期不提供取消归档',
        key=f'production_archive_confirm_{project_id}', disabled=archived)
    if st.button('归档任务', key=f'production_archive_{project_id}', disabled=archived or not confirmed):
        _perform(lambda: projects.archive(project_id), '任务已归档，历史内容已保留。')
    with st.expander('操作历史'):
        actions = store.actions(project_id)
        st.dataframe([{'操作': action_label(a),
            '原状态': STATUSES.get(a['previous_status'], '无'), '新状态': STATUSES[a['new_status']],
            '时间（UTC）': a['created_at']} for a in actions], hide_index=True, width='stretch')
        with st.expander('操作详情'):
            st.json([{'操作 ID': a['id'], '操作': action_label(a), '详情': a['details']}
                     for a in actions], expanded=False)
    _version_history(store, versions, project)
    from pages.research import show_research
    show_research(store, project)
    st.write('**后续制作模块**')
    for kind, label in CONTENT_TYPES.items():
        if kind == 'research':
            continue
        with st.expander(label):
            st.info(f'{label}尚未开发。本期只提供任务和版本基础设施，不调用 AI API。')


def show_production_page(path):
    """从现有应用导航进入；所有初始化和日常交互都只访问 SQLite。"""
    st.title('视频制作工作台')
    st.write('从已有视频选题建立制作任务，记录人工制作进度与内容历史。')
    if 'production_flash' in st.session_state:
        st.success(st.session_state.pop('production_flash'))
    store = ProductionStore(path)
    projects, versions = ProjectService(store), VersionService(store)
    _creation(store, projects)
    project_id = st.session_state.get('production_detail')
    if project_id is not None:
        if st.button('返回任务列表', key='production_back'):
            st.session_state.pop('production_detail', None)
            st.rerun()
        _details(store, projects, versions, project_id)
    else:
        _project_list(store)


if __name__ == '__main__':
    # 兼容 Streamlit pages 路由直接访问，同时继续使用主应用的统一导航。
    from app import main
    main(initial_page='视频制作工作台')
