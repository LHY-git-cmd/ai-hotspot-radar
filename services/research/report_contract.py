"""报告v3模型仅选择表达树；Schema不授予事实、时间或确认权限。"""

from copy import deepcopy

VERSION = 'research-report-v3'
INPUT_VERSION = 'research-report-input-v3'
POLICY = 'report-validation-v3'
RENDERER = 'report-render-v3'
HASH_VERSION = 'canonical-json-sha256-v1'
TEMPLATES = ('evidence_statement', 'attributed_opinion', 'limited_inference',
             'compare_like_for_like', 'preserve_dispute', 'unresolved_lead', 'gap_reference')
CATEGORIES = ('verified', 'single_source', 'opinion', 'inference', 'disputed', 'unverified', 'gaps')


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def arr(items, maximum, minimum=0):
    return {'type': 'array', 'items': items, 'maxItems': maximum, 'minItems': minimum}


ID = {'type': 'string', 'minLength': 1, 'maxLength': 60, 'pattern': r'^[A-Za-z0-9_-]+$'}
BINDING = obj({'slot': {'type': 'string', 'enum': ['evidence', 'premise', 'left', 'right', 'gap']},
    'evidence_id': {'type': ['integer', 'null'], 'minimum': 1},
    'statement_ref': {'type': ['string', 'null'], 'maxLength': 100},
    'gap_id': {'type': ['string', 'null'], 'maxLength': 100}})
BLOCK = obj({'block_id': ID, 'template_id': {'type': 'string', 'enum': list(TEMPLATES)},
             'bindings': arr(BINDING, 10, 1)})
REPORT_CANDIDATE_SCHEMA = obj({'question_sections': arr(obj({'question_id': ID,
    'evidence_order': arr({'type': 'integer', 'minimum': 1}, 10),
    'gap_order': arr({'type': 'string', 'maxLength': 100}, 200), 'blocks': arr(BLOCK, 8)}), 10, 1),
    'conclusion_blocks': arr(BLOCK, 10)})


def candidate_schema(bundle):
    """枚举限制模型当前可选集合；完整本地关联规则仍在纯validator。"""
    schema = deepcopy(REPORT_CANDIDATE_SCHEMA)
    # 不依赖Provider对复杂oneOf的支持；nullable条件与关系本地校验。
    sections = schema['properties']['question_sections']['items']['properties']
    sections['question_id']['enum'] = [q['id'] for q in bundle['questions']]
    if bundle['evidence_catalog']:
        sections['evidence_order']['items']['enum'] = [e['evidence_id'] for e in bundle['evidence_catalog']]
    return schema
