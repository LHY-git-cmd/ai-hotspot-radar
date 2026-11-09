"""制作操作审计，与业务变更共用调用方的写事务。"""

ACTION_LABELS = {'created': '创建任务', 'updated': '修改基本信息', 'status_changed': '人工调整状态',
                 'paused': '暂停任务', 'resumed': '恢复任务', 'archived': '归档任务',
                 'version_created': '创建版本', 'version_restored': '恢复历史版本'}

RESEARCH_EVENTS = {'plan_confirmed': '确认研究计划', 'search_started': '执行研究搜索',
                   'evidence_organized': '整理研究证据', 'report_confirmed': '确认研究报告',
                   'search_interrupted': '确认研究搜索中断'}
RESEARCH_EVENTS.update({'report_validation_started': '校验研究报告候选',
    'report_validated_v3': '报告程序校验通过', 'report_confirmed_v3': '人工确认研究报告'})


def action_label(row):
    return RESEARCH_EVENTS.get(row.get('details', {}).get('event'), ACTION_LABELS[row['action_type']])


def record_action(store, connection, project_id, action_type, previous_status, new_status, now, details=None):
    """禁止另开连接提交，确保审计失败时业务变更一起回滚。"""
    store.insert_action(connection, project_id, action_type, previous_status, new_status, now, details or {})
