"""研究文档本地完整校验；原始来源元数据不由模型填写。"""

from datetime import date
from copy import deepcopy
import re

from jsonschema import Draft202012Validator
from services.research.diagnostics import ResearchValidationError
from services.research.queries import build_query, QUERY_BUILDER_VERSION


def text(empty=False):
    return {'type': 'string', 'maxLength': 12000, **({} if empty else {'minLength': 1, 'pattern': r'\S'})}


def array(items, minimum=0, maximum=100):
    return {'type': 'array', 'items': items, 'minItems': minimum, 'maxItems': maximum}


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


QUESTION = obj({'id': text(), 'question': text(), 'keywords': array(text(), 1, 12),
                'source_types': array(text(), 1, 8), 'domains': array(text(), 0, 10)})
PLAN_SCHEMA = obj({'objective': text(), 'focus': text(), 'start_date': text(True), 'end_date': text(True),
                   'verify_facts': array(text(), 1, 30), 'questions': array(QUESTION, 1, 10)})
# 历史计划允许缺省；生成工具则显式要求该字段（空字符串代表关键词构造）。
QUESTION['properties']['query_override'] = text(True)
PLAN_GENERATION_SCHEMA = deepcopy(PLAN_SCHEMA)
PLAN_GENERATION_SCHEMA['properties']['questions']['items']['required'].append('query_override')
PLAN_SCHEMA['properties']['query_builder_version'] = {'type': 'string', 'enum': [QUERY_BUILDER_VERSION]}
CATEGORIES = {'verified': '已证实事实', 'single_source': '单一来源事实', 'opinion': '来源观点',
              'inference': 'AI 推断', 'disputed': '存在争议', 'unverified': '待核实'}
LINK = obj({'source_id': {'type': 'integer', 'minimum': 1}, 'quote': text(),
            'field': {'type': 'string', 'enum': ['text', 'snippet']}})
EVIDENCE_SCHEMA = obj({'items': array(obj({'question_id': text(),
    'category': {'type': 'string', 'enum': list(CATEGORIES)}, 'summary': text(),
    'inference': text(True), 'verification': text(), 'links': array(LINK, 1, 10)}), 0, 100),
    'gaps': array(text(), 1, 30)})
EVIDENCE_SCHEMA_V1 = deepcopy(EVIDENCE_SCHEMA)
EVIDENCE_SCHEMA['properties']['items']['maxItems'] = 10
TIME_SCOPE = {'type': 'string', 'enum': ['unknown', 'historical', 'forecast', 'current', 'not_applicable']}
evidence_item = EVIDENCE_SCHEMA['properties']['items']['items']
evidence_item['properties'].update(time_scope=deepcopy(TIME_SCOPE), data_period=text())
evidence_item['required'].extend(('time_scope', 'data_period'))
CLAIM = obj({'text': text(), 'evidence_ids': array({'type': 'integer', 'minimum': 1}, 1, 20)})
REPORT_SCHEMA = obj({'overview': text(), 'objective': text(), 'conclusions': array(CLAIM),
    'facts': array(CLAIM), 'data': array(CLAIM), 'differences': array(CLAIM),
    'unverified': array(text(), 1, 50), 'risks': array(text(), 1, 50)})
REPORT_SCHEMA_V1 = deepcopy(REPORT_SCHEMA)
CLAIM['properties']['time_scope'] = deepcopy(TIME_SCOPE)
CLAIM['required'].append('time_scope')
# v1/v2仅保留历史读取契约；所有新证据请求必须使用候选v3。
from services.research.quality import CANDIDATE_SCHEMA
from services.research.report_contract import REPORT_CANDIDATE_SCHEMA
SCHEMAS = {'plan': PLAN_GENERATION_SCHEMA, 'evidence': CANDIDATE_SCHEMA, 'report': REPORT_CANDIDATE_SCHEMA}


def validate(schema, document):
    error = next(Draft202012Validator(schema).iter_errors(document), None)
    if error is not None:
        raise ResearchValidationError('schema', '研究内容字段、数量或引用结构无效',
                                      error.absolute_path, rule=error.validator)
    return document


def validate_plan(document):
    validate(PLAN_SCHEMA, document)
    start, end = document['start_date'], document['end_date']
    try:
        if start: date.fromisoformat(start)
        if end: date.fromisoformat(end)
    except ValueError:
        raise ValueError('研究时间须为 YYYY-MM-DD，留空表示不限') from None
    if start and end and start > end:
        raise ValueError('研究开始日期不能晚于结束日期')
    questions = document['questions']
    if len({q['id'] for q in questions}) != len(questions):
        raise ValueError('研究问题 ID 不得重复')
    for question in questions:
        build_query(question)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', question['id']):
            raise ValueError('研究问题 ID 只能包含字母、数字、下划线和短横线')
        for domain in question['domains']:
            if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', domain) or '.' not in domain:
                raise ValueError('优先域名只能填写域名，不包含协议、路径或凭据')
    return document
