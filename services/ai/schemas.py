"""完整输出 Schema 及 strict 工具可接受的子集，额外语义约束本地执行。"""

from copy import deepcopy
from jsonschema import Draft202012Validator

from services.normalization import normalize_title


def _text(description: str) -> dict:
    """要求非空文本，并限制单字段大小。"""
    return {'type': 'string', 'minLength': 1, 'maxLength': 6000, 'pattern': r'\S', 'description': description}


def _array(item: dict, minimum: int = 1, maximum: int = 12) -> dict:
    """本地完整 Schema 包含严格的数量上限。"""
    return {'type': 'array', 'items': item, 'minItems': minimum, 'maxItems': maximum}


def _object(properties: dict) -> dict:
    """所有字段必需且禁止额外字段，包括额外的模型评分。"""
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


IDEA_SCHEMA = _object({
    'angle_type': _text('互不相同的制作类型，如实测型、教程型、对比型'),
    'title': _text('谨慎、可执行的中文视频标题'),
    'alternative_titles': _array(_text('备用标题'), 2, 2),
    'target_audience': _text('目标观众'), 'hook': _text('前3至5秒开场钩子，不宣称已亲测'),
    'outline': _array(_object({'seconds': {'type': 'integer', 'minimum': 1, 'maximum': 90},
                               'content': _text('该段准备讲述的内容；所有分段合计60至90秒')}), 3, 8),
    'materials': _array(_text('需要准备的素材')), 'verification_checklist': _array(_text('事实核验项目')),
    'difficulty': {'type': 'string', 'enum': ['低', '中', '高']},
    'recommendation_reason': _text('该制作视角的具体推荐原因'), 'risks': _array(_text('未核实或制作风险')),
})
ANALYSIS_SCHEMA = _object({
    'summary': _text('通俗解释热点，区分材料声称与事实'), 'what_happened': _text('材料说明发生了什么'),
    'why_now': _text('为什么值得关注，趋势不足时不能虚构增长'), 'target_audience': _text('目标观众'),
    'audience_value': _text('观众可能得到的价值'), 'video_suitability': {'type': 'boolean'},
    'suitability_reason': _text('适合或不适合短视频的原因'),
    'evidence_gaps': _array(_text('待补充的证据')), 'factual_risks': _array(_text('需要核实的事实风险')),
    'video_ideas': _array(IDEA_SCHEMA, 3, 3),
})


def provider_schema(schema: dict | None = None) -> dict:
    """移除 DeepSeek strict 尚不支持的长度参数，保留本地完整校验。"""
    def compatible(value):
        """递归转换副本，不修改本地用于验证的 Schema。"""
        if isinstance(value, dict):
            return {key: compatible(item) for key, item in value.items()
                    if key not in ('minLength', 'maxLength', 'minItems', 'maxItems')}
        if isinstance(value, list):
            return [compatible(item) for item in value]
        return value
    return compatible(ANALYSIS_SCHEMA if schema is None else schema)


def validate_analysis(document: object) -> dict:
    """结构和明显重复失败则拒绝成功入库，不能静默截取或补造第三个角度。"""
    if list(Draft202012Validator(ANALYSIS_SCHEMA).iter_errors(document)):
        raise ValueError('AI 输出结构无效：字段、数量、文本或时长类型不符合要求')
    ideas = document['video_ideas']
    for key in ('angle_type', 'title', 'hook'):
        if len({normalize_title(idea[key]) for idea in ideas}) != 3:
            raise ValueError('三个视频角度的类型、标题和钩子必须明显不同')
    outlines = []
    for idea in ideas:
        if not 60 <= sum(part['seconds'] for part in idea['outline']) <= 90:
            raise ValueError('视频结构必须合计 60 到 90 秒')
        if len({normalize_title(title) for title in [idea['title'], *idea['alternative_titles']]}) != 3:
            raise ValueError('主标题与两个备用标题不能完全重复')
        outlines.append(normalize_title(' '.join(part['content'] for part in idea['outline'])))
    if len(set(outlines)) != 3:
        raise ValueError('三个角度不能使用完全相同的大纲')
    return deepcopy(document)
