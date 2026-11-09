"""本地交互确认能力。隔离模型/JSON；不声称能防御任意Python或SQL管理员。"""

from time import monotonic
from weakref import WeakKeyDictionary
from uuid import uuid4

from services.research.report_evidence import fail

_issued = WeakKeyDictionary()


class HumanConfirmationIntent:
    """只有注册于可信本地交互会话的实例有效；普通构造或字典没有权限。"""
    pass


class LocalReportReviewSession:
    """由本地交互适配器持有，模型执行器不持有此会话/能力。"""
    def __init__(self):
        self.session_id = uuid4().hex

    def reviewed(self, project_id, report, *, checked):
        if checked is not True or report['content'].get('contract_version') != 'research-report-v3':
            fail('report_confirmation_intent')
        validation = report['content']['validation']
        intent = HumanConfirmationIntent()
        _issued[intent] = {'project_id': project_id, 'report_version_id': report['id'],
            'report_core_hash': validation['report_core_hash'], 'evidence_set_hash': validation['evidence_set_hash'],
            'policy_version': validation['policy_version'], 'purpose': 'confirm_report',
            'origin': 'local_interactive_operator', 'session_id': self.session_id,
            'nonce': uuid4().hex, 'expires': monotonic()+600, 'committed_action': None}
        return intent


def verify_intent(intent, project_id, report, action_id):
    if not isinstance(intent, HumanConfirmationIntent) or intent not in _issued:
        fail('report_confirmation_intent')
    value = _issued[intent]
    expected = {'project_id': project_id, 'report_version_id': report['id'],
        **{k: report['content']['validation'][k] for k in ('report_core_hash', 'evidence_set_hash', 'policy_version')}}
    if (any(value[k] != v for k, v in expected.items()) or
        value['committed_action'] not in (None, action_id) or
        value['committed_action'] is None and monotonic() > value['expires'] or
        not isinstance(action_id, str) or not action_id.strip()):
        fail('report_confirmation_intent')
    return {k: v for k, v in value.items() if k not in ('expires', 'committed_action')}


def commit_intent(intent, action_id):
    _issued[intent]['committed_action'] = action_id
