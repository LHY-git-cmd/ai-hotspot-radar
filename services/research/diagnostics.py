"""研究校验诊断协议；不保留模型自由文本、未知字段名或配置内容。"""

import json

MAX_DOCUMENT_BYTES = 16384
SAFE_KEYS = frozenset(('items', 'gaps', 'question_id', 'category', 'summary', 'inference',
    'verification', 'links', 'source_id', 'quote', 'field', 'time_scope', 'data_period',
    'overview', 'objective', 'conclusions', 'facts', 'data', 'differences', 'evidence_ids',
    'text', 'unverified', 'risks', 'questions', 'keywords', 'source_types', 'domains',
    'focus', 'start_date', 'end_date', 'verify_facts', 'query_override', 'id'))
SAFE_KEYS = SAFE_KEYS | frozenset(('candidate_id', 'kind', 'corroboration_requested', 'claim',
    'entity', 'metric', 'value', 'unit', 'basis', 'speaker', 'temporal', 'proposed_type',
    'event_kind', 'speaker_kind', 'period', 'label_raw', 'calendar_year', 'fiscal_year',
    'fiscal_quarter', 'start', 'end', 'context_links', 'window_id', 'segment_id', 'region',
    'storage_field', 'role', 'sources', 'manifest', 'body_hash', 'snapshot_hash', 'model_materials'))

V3_CODES = frozenset(('total_limit', 'question_set_mismatch', 'manifest_integrity', 'manifest_invalid',
    'contract_version_mismatch', 'window_range', 'region_mismatch', 'unsupported_region',
    'extraction_unavailable', 'claim_support_mismatch', 'unsupported_value', 'source_region_conflict',
    'temporal_mismatch', 'speaker_mismatch', 'temporal_contradiction', 'temporal_input',
    'mixed_temporal_claim', 'table_context_missing', 'policy_invalid', 'untrusted_review_input',
    'projection_mismatch'))


class ResearchValidationError(ValueError):
    def __init__(self, code, message, path=(), *, rule=None):
        super().__init__(message)
        self.diagnostic = {'code': code, 'path': list(path), 'rule': rule}


def safe_path(path):
    return [part if type(part) is int or part in SAFE_KEYS else '[unknown_field]' for part in path]


def rejected_structure(document):
    """保存有限大小的结构样本，字符串全部脱敏；此样本不能用于原文回放。"""
    incomplete = False

    def redact(value, depth=0):
        nonlocal incomplete
        if depth > 10:
            incomplete = True
            return '[depth_limit]'
        if isinstance(value, dict):
            return {key: redact(item, depth+1) for key, item in value.items() if key in SAFE_KEYS}
        if isinstance(value, list):
            if len(value) > 101:
                incomplete = True
            return [redact(item, depth+1) for item in value[:101]]
        if isinstance(value, str):
            return '[redacted]'
        if value is None or isinstance(value, bool) or type(value) is int and abs(value) < 10**12:
            return value
        return '[redacted]'
    try:
        result = json.dumps(redact(document), ensure_ascii=False, allow_nan=False)
        # 不保存半个 JSON；超过上限仅保留结构摘要并明确标记不完整。
        if len(result.encode('utf-8')) > MAX_DOCUMENT_BYTES:
            return json.dumps({'document': '[size_limit]'}), True
        return result, incomplete
    except (ValueError, TypeError, RecursionError):
        return None, True


REPORT_CODES = frozenset('report_schema report_evidence_not_allowed report_scope_mismatch report_binding_mismatch report_statement_ref_mismatch report_value_mismatch report_period_mismatch report_grade_escalation report_temporal_escalation report_dispute_omitted report_gap_omitted report_unsupported_conclusion report_basis_changed report_version_conflict report_validation_internal report_confirmation_required report_confirmation_binding report_confirmation_intent report_legacy_unreviewed'.split())
V3_CODES = V3_CODES | REPORT_CODES
SAFE_KEYS = SAFE_KEYS | frozenset('question_sections evidence_order gap_order blocks block_id template_id bindings slot evidence_id statement_ref gap_id conclusion_blocks document'.split())
