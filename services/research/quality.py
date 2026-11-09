"""v3候选质量判定纯函数，不依赖SQLite、Streamlit、API或配置。

公开assess_batch没有可信审核供给：普通policy/模型/manifest中的审核JSON
不能授予verified。内部策略回调仅供隔离测试模拟未来充分前提，不认证身份。
"""

from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator
from services.research.temporal import classify_temporal, normalize_source_date, _v3_period_label

CONTRACT_VERSION = 'research-evidence-v3'
POLICY_VERSION = 'quality-v3'


def _obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def _string():
    return {'type': 'string', 'minLength': 1, 'maxLength': 12000, 'pattern': r'\S'}


def _enum(*values):
    return {'type': 'string', 'enum': list(values)}


TEXT = _string()
FREE = {'type': 'string', 'maxLength': 12000}
INTEGER = {'type': 'integer', 'minimum': 0}
LINK_SCHEMA = _obj({'source_id': {'type': 'integer', 'minimum': 1}, 'window_id': TEXT,
    'segment_id': TEXT, 'region': _enum('title', 'search_snippet', 'extracted_body', 'metadata'),
    'storage_field': _enum('text', 'snippet'), 'start': INTEGER, 'end': INTEGER,
    'quote': TEXT, 'role': _enum('claim_support', 'period_context')})
PERIOD_SCHEMA = _obj({'label_raw': TEXT, 'calendar_year': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 9999},
    'fiscal_year': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 9999},
    'fiscal_quarter': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 4},
    'start': {'type': ['string', 'null']}, 'end': {'type': ['string', 'null']}})
ITEM_SCHEMA = _obj({'candidate_id': TEXT, 'kind': _enum('fact', 'opinion', 'inference', 'disputed', 'unverified'),
    'corroboration_requested': {'type': 'boolean'}, 'summary': TEXT, 'inference': FREE, 'verification': TEXT,
    'claim': _obj({key: TEXT for key in ('entity', 'metric', 'value', 'unit', 'basis', 'speaker')}),
    'temporal': _obj({'proposed_type': _enum('historical_actual', 'current_actual', 'company_guidance',
        'analyst_forecast', 'market_expectation', 'unknown'),
        'event_kind': _enum('actual_result', 'guidance', 'forecast', 'expectation', 'unknown'),
        'speaker_kind': _enum('company', 'analyst', 'market', 'media', 'unknown'),
        'period': PERIOD_SCHEMA, 'context_links': {'type': 'array', 'items': LINK_SCHEMA, 'maxItems': 10}}),
    'links': {'type': 'array', 'items': LINK_SCHEMA, 'minItems': 1, 'maxItems': 10}})
CANDIDATE_SCHEMA = _obj({'questions': {'type': 'array', 'maxItems': 10, 'items': _obj({
    'question_id': TEXT, 'items': {'type': 'array', 'items': ITEM_SCHEMA, 'maxItems': 2},
    'gaps': {'type': 'array', 'items': _obj({'code': TEXT, 'detail': TEXT}), 'maxItems': 30}})}})


def claim_signature(item):
    """命题身份不含摘要/候选ID；期间、基准、事件性质都参与绑定。"""
    value = {'claim': item['claim'], 'period': item['temporal']['period'],
             'event_kind': item['temporal']['event_kind']}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _error(code, path=(), **details):
    return {'code': code, 'path': list(path), **details}


def _visible_occurrences(source, quote, region):
    matches = {}
    for w in source.get('visible_windows', []):
        if w.get('region') != region or w.get('storage_field') not in ('text', 'snippet'):
            continue
        raw = source.get(w['storage_field'], '')
        a, b = w.get('start'), w.get('end')
        if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(raw) or raw[a:b] != w.get('text'):
            continue
        cursor = a
        while cursor < b:
            found = raw.find(quote, cursor, b)
            if found < 0:
                break
            matches[(w['storage_field'], found, found+len(quote))] = w
            cursor = found+1
    return matches


def _validate_link(link, sources, manifest, qid, path, decisions, *, context=False):
    source = sources.get(str(link['source_id']))
    if source is None or qid not in source.get('question_ids', []) or (
        source.get('project_id', manifest.get('project_id')) != manifest.get('project_id') or
        source.get('run_id', manifest.get('run_id')) != manifest.get('run_id')):
        return None, _error('source_association', path)
    if link['end'] <= link['start']:
        return None, _error('window_range', path)
    w = next((w for w in source.get('visible_windows', []) if w.get('window_id') == link['window_id']), None)
    if w and 'question_ids' in w and qid not in w['question_ids']:
        return None, _error('source_association', path)
    if w and (w.get('region') != link['region'] or w.get('segment_id') != link['segment_id']):
        return None, _error('region_mismatch', path)
    if link['region'] in ('title', 'metadata'):
        return None, _error('unsupported_period' if context else 'unsupported_region', path)
    if link['region'] == 'extracted_body' and source.get('extraction_status') != 'success':
        return None, _error('extraction_unavailable', path)
    # 先按精确出现位置校验；标签纠正只能选同题下唯一可见区间。
    valid = False
    if w:
        field = w.get('storage_field')
        raw = source.get(field, '')
        a, b = w.get('start'), w.get('end')
        valid = (field in ('text', 'snippet') and type(a) is int and type(b) is int and
                 0 <= a <= link['start'] < link['end'] <= b <= len(raw) and
                 raw[a:b] == w.get('text') and raw[link['start']:link['end']] == link['quote'])
    fixed = deepcopy(link)
    if not valid:
        matches = []
        for candidate in sources.values():
            if qid not in candidate.get('question_ids', []):
                continue
            if link['region'] == 'extracted_body' and candidate.get('extraction_status') != 'success':
                continue
            for (field, a, b), window in _visible_occurrences(candidate, link['quote'], link['region']).items():
                if 'question_ids' in window and qid not in window['question_ids']:
                    continue
                matches.append((candidate, window, field, a, b))
        # 同源另一字段的唯一命中也属于现有可保留的字段纠正能力。
        if not matches:
            other = 'search_snippet' if link['region'] == 'extracted_body' else 'extracted_body'
            for (field, a, b), window in _visible_occurrences(source, link['quote'], other).items():
                if 'question_ids' in window and qid not in window['question_ids']:
                    continue
                if other != 'extracted_body' or source.get('extraction_status') == 'success':
                    matches.append((source, window, field, a, b))
        if len(matches) != 1:
            return None, _error('ambiguous_quote' if matches else 'quote_not_visible', path)
        source, w, field, a, b = matches[0]
        fixed.update(source_id=source['source_id'], storage_field=field, start=a, end=b,
                     window_id=w['window_id'], segment_id=w['segment_id'], region=w['region'])
    else:
        fixed['storage_field'] = w['storage_field']
    # 可见窗口须完全属于服务器登记区域，不接受模型自称body或伪造窗口文本。
    regions = [r for r in source.get('regions', []) if r.get('segment_id') == w.get('segment_id')]
    if not any(r.get('region') == fixed['region'] and r.get('storage_field') == fixed['storage_field'] and
               type(r.get('start')) is int and type(r.get('end')) is int and
               r['start'] <= w['start'] < w['end'] <= r['end'] and
               r.get('boundary_confidence') != 'unknown' for r in regions):
        return None, _error('region_mismatch', path)
    if context and fixed['region'] != 'extracted_body':
        return None, _error('unsupported_period', path)
    if fixed != link:
        decisions.append({'code': 'unique_citation_correction', 'path': list(path),
                          'before': deepcopy(link), 'after': deepcopy(fixed)})
    return fixed, None


def _number_in(value, text):
    return bool(re.search(r'(?<![\d.])'+re.escape(value)+r'(?![\d.])', text, re.I))


def _claim_check(item, support, all_visible, path):
    c = item['claim']
    if item['kind'] not in ('fact', 'disputed'):
        return []
    errors = []
    for name in ('entity', 'metric'):
        if c[name] != 'unknown' and c[name].casefold() not in support.casefold():
            errors.append(_error('claim_support_mismatch', path+['claim', name]))
    if c['value'] != 'unknown' and not _number_in(c['value'], support):
        errors.append(_error('unsupported_value', path+['claim', 'value']))
    if c['unit'] != 'unknown' and c['unit'].casefold() not in support.casefold():
        errors.append(_error('claim_support_mismatch', path+['claim', 'unit']))
    # 值必须属于该指标的结果，不能因为同句出现“预期20%”就把它当实际值。
    if c['unit'] == '%' and c['metric'] != 'unknown' and item['kind'] == 'fact':
        bound = re.findall(re.escape(c['metric'])+r'[^。;；%]{0,35}?(\d+(?:\.\d+)?)\s*%', support, re.I)
        if bound and c['value'] not in bound:
            errors.append(_error('claim_support_mismatch', path+['claim', 'value']))
    role = re.search(r'\b(CEO|CFO|CTO)\b', c['speaker'], re.I)
    if role and not re.search(r'\b'+role[1]+r'\b', support, re.I):
        errors.append(_error('claim_support_mismatch', path+['claim', 'speaker']))
    if item['kind'] == 'fact' and re.search(r'同一期间|same\s+period', all_visible, re.I):
        numbers = set(re.findall(r'([\d.]+)\s*%', all_visible))
        if c['unit'] == '%' and len(numbers) > 1 and c['value'] in numbers:
            errors.append(_error('source_region_conflict', path))
    return errors


def _origins(source_rows):
    parent = list(range(len(source_rows)))

    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i

    for i, a in enumerate(source_rows):
        for j, b in enumerate(source_rows[:i]):
            equal_body = bool(a.get('text')) and a.get('text') == b.get('text')
            same_origin = any(a.get(k) and a.get(k) == b.get(k) for k in
                              ('origin_group_id', 'editorial_entity', 'citation_origin_id'))
            same_domain = a.get('domain') and a.get('domain').lower() == b.get('domain', '').lower()
            same_url = a.get('url') and a.get('url') == b.get('url')
            if equal_body or same_origin or same_domain or same_url:
                parent[find(i)] = find(j)
    return sorted({f'origin-{source_rows[find(i)]["source_id"]}' for i in range(len(source_rows))})


def _grade(item, sources, review_gate=None, temporal=None):
    rows = [sources[str(sid)] for sid in sorted({l['source_id'] for l in item['links']})]
    groups = _origins(rows)
    status = 'dependent' if len(rows) > len(groups) else 'unknown'
    reasons = []
    if item['kind'] != 'fact':
        final = {'opinion': 'opinion', 'inference': 'inference', 'disputed': 'disputed', 'unverified': 'unverified'}[item['kind']]
    elif any(l['region'] != 'extracted_body' for l in item['links']):
        final = 'unverified'
        reasons.append('snippet_only')
    elif any(item['claim'][field] == 'unknown' for field in ('entity', 'metric', 'unit', 'value')):
        final = 'unverified'
        reasons.append('context_incomplete')
    elif len(groups) == 1:
        final = 'single_source'
        reasons.append('single_origin')
    else:
        final = 'unverified'
        reasons.append('independence_unknown')
    if any(s.get('domain', '').endswith('.co.uk') and not s.get('registrable_domain') for s in rows):
        reasons.append('registrable_domain_unknown')
    # 公开入口始终不给review_gate；没有认证供给，因此生产可调用接口永不verified。
    if (review_gate is not None and item['kind'] == 'fact' and len(groups) >= 2 and
        all(l['region'] == 'extracted_body' for l in item['links']) and
        not any(item['claim'][field] == 'unknown' for field in ('entity', 'metric', 'value', 'unit', 'basis')) and
        temporal and temporal.get('temporal_type') in ('historical_actual', 'current_actual') and
        all(any(r.get('segment_id') == l['segment_id'] and r.get('boundary_confidence') in ('explicit', 'reviewed')
                for r in sources[str(l['source_id'])]['regions']) for l in item['links']) and
        all(s.get('extraction_status') == 'success' for s in rows) and review_gate(item, rows)):
        final, status, reasons = 'verified', 'confirmed_independent', []
    return {'final_category': final, 'independence_status': status, 'origin_group_ids': groups,
            'unmet_conditions': reasons, 'grant_reasons': ['reviewed_independent_support'] if final == 'verified' else [],
            'policy_version': POLICY_VERSION}


def _temporal_check(item, sources, research, path):
    support = '\n'.join(l['quote'] for l in item['links'])
    contexts = item['temporal']['context_links']
    text = support+'\n'+'\n'.join(l['quote'] for l in contexts)
    supplied = item['temporal']['period']
    errors = []
    label = supplied['label_raw']
    actual_label = _v3_period_label(text)
    normalized_label = _v3_period_label(label)
    if label != 'unknown' and label.casefold() not in text.casefold() and not (
        normalized_label['fiscal_year'] and (normalized_label['fiscal_year'], normalized_label['fiscal_quarter']) ==
        (actual_label['fiscal_year'], actual_label['fiscal_quarter'])):
        errors.append(_error('unsupported_period', path+['temporal', 'period', 'label_raw']))
    for key in ('fiscal_year', 'fiscal_quarter'):
        if supplied[key] is not None and supplied[key] != actual_label[key]:
            errors.append(_error('unsupported_period', path+['temporal', 'period', key]))
    for key in ('start', 'end'):
        if supplied[key] is not None and supplied[key] not in text:
            errors.append(_error('unsupported_period', path+['temporal', 'period', key]))
    # 期间上下文不能借同题的另一篇来源拼接成这个数字的期间。
    supported_sources = {l['source_id'] for l in item['links']}
    if any(l['source_id'] not in supported_sources for l in contexts):
        errors.append(_error('unsupported_period', path+['temporal', 'context_links']))
    if errors:
        return {}, errors
    first = sources[str(item['links'][0]['source_id'])]
    # 精确出现只证明引句含该日期，不证明它是数据期间（可能是正文署期）。
    # 覆盖日期必须由分类器从明确截至/期间表达提取，不能由模型日期赋予含义。
    result = classify_temporal(text, {'published_at': first.get('published_at'),
        'period_label': label if label != 'unknown' else None}, research)
    for key, field in (('start', 'coverage_start'), ('end', 'coverage_end')):
        if supplied[key] is not None and supplied[key] != result[field]:
            errors.append(_error('unsupported_period', path+['temporal', 'period', key]))
    for error in result['errors']:
        errors.append(_error(error['code'], path+['temporal', error.get('field', 'event_kind')]))
    proposed = item['temporal']['proposed_type']
    suggested_event = item['temporal']['event_kind']
    suggested_speaker = item['temporal']['speaker_kind']
    if suggested_event != 'unknown' and result['event_kind'] != 'unknown' and suggested_event != result['event_kind']:
        errors.append(_error('temporal_mismatch', path+['temporal', 'event_kind']))
    if suggested_speaker != 'unknown' and result['speaker_kind'] != 'unknown' and suggested_speaker != result['speaker_kind']:
        errors.append(_error('speaker_mismatch', path+['temporal', 'speaker_kind']))
    if proposed != 'unknown' and proposed != result['temporal_type']:
        errors.append(_error('temporal_mismatch', path+['temporal', 'proposed_type']))
    # 自由摘要不能与已验证的事件性质出现明显矛盾。
    if result['event_kind'] in ('guidance', 'forecast', 'expectation') and re.search(r'已经实现|实际增长|actual\s+growth', item['summary'], re.I):
        errors.append(_error('temporal_mismatch', path+['summary']))
    return result, errors


def _assess_batch(candidate, manifest, policy=None, *, _review_gate=None):
    """内部策略测试接缝。生产公开入口不透传任何审核回调/普通JSON审核记录。"""
    errors, decisions, items, gaps = [], [], [], []
    def failure():
        for error in errors:
            path = error['path']
            if len(path) >= 2 and path[0] == 'questions' and type(path[1]) is int:
                error['question_index'] = path[1]
                if len(path) >= 4 and path[2] == 'items' and type(path[3]) is int:
                    error['item_index'] = path[3]
        return {'accepted': False, 'items': [], 'gaps': [], 'errors': errors[:20],
                'diagnostics_truncated': len(errors) > 20, 'decisions': decisions}
    if not isinstance(policy, (dict, type(None))):
        errors.append(_error('policy_invalid'))
        return failure()
    policy = policy or {}
    if set(policy)-{'version', 'max_total', 'max_per_question'}:
        errors.append(_error('untrusted_review_input', ['policy']))
        return failure()
    if (policy.get('version', POLICY_VERSION) != POLICY_VERSION or
        policy.get('max_total', 10) != 10 or policy.get('max_per_question', 2) != 2):
        errors.append(_error('policy_invalid', ['policy']))
        return failure()
    if not isinstance(manifest, dict) or manifest.get('contract_version') != CONTRACT_VERSION:
        errors.append(_error('contract_version_mismatch', ['manifest']))
        return failure()
    # 业务预检先于逐项语义判断，稳定报告上限；不裁剪模型输出。
    if isinstance(candidate, dict) and isinstance(candidate.get('questions'), list):
        groups = candidate['questions']
        if all(isinstance(g, dict) and isinstance(g.get('items'), list) for g in groups):
            for i, g in enumerate(groups):
                if len(g['items']) > 2:
                    errors.append(_error('question_limit', ['questions', i, 'items']))
            if sum(len(g['items']) for g in groups) > 10:
                errors.append(_error('total_limit', ['questions']))
    if errors:
        return failure()
    try:
        if len(json.dumps(candidate, ensure_ascii=False, allow_nan=False).encode()) > 262144:
            errors.append(_error('schema', [], rule='document_size'))
        else:
            for error in Draft202012Validator(CANDIDATE_SCHEMA).iter_errors(candidate):
                errors.append(_error('schema', error.absolute_path, rule=error.validator))
                if len(errors) >= 20:
                    break
    except (TypeError, ValueError, RecursionError):
        errors.append(_error('schema'))
    if errors:
        return failure()
    questions = manifest.get('questions')
    sources = manifest.get('sources')
    research = manifest.get('research_context')
    if not isinstance(questions, list) or not isinstance(sources, dict) or not isinstance(research, dict):
        errors.append(_error('manifest_invalid'))
        return failure()
    expected = [q.get('id') for q in questions if isinstance(q, dict)]
    actual = [q['question_id'] for q in candidate['questions']]
    if not all(isinstance(q, str) and q.strip() for q in expected):
        errors.append(_error('manifest_invalid', ['questions']))
        return failure()
    if len(expected) != len(questions) or len(set(expected)) != len(expected) or sorted(expected) != sorted(actual):
        errors.append(_error('question_set_mismatch', ['questions']))
        return failure()
    for key, source in sources.items():
        if not isinstance(source, dict) or str(source.get('source_id')) != key or not isinstance(source.get('text'), str):
            errors.append(_error('manifest_invalid', ['sources', key]))
            continue
        if source.get('body_hash') != hashlib.sha256(source['text'].encode('utf-8')).hexdigest():
            errors.append(_error('manifest_integrity', ['sources', key, 'body_hash']))
        association_ids = source.get('question_ids')
        if not isinstance(association_ids, list) or not all(isinstance(q, str) and q in expected for q in association_ids):
            errors.append(_error('manifest_invalid', ['sources', key, 'question_ids']))
        if (source.get('project_id', manifest.get('project_id')) != manifest.get('project_id') or
            source.get('run_id', manifest.get('run_id')) != manifest.get('run_id')):
            errors.append(_error('source_association', ['sources', key]))
        for collection in ('regions', 'visible_windows'):
            values = source.get(collection)
            if not isinstance(values, list):
                errors.append(_error('manifest_invalid', ['sources', key, collection]))
                continue
            for n, value in enumerate(values):
                if not isinstance(value, dict):
                    errors.append(_error('manifest_invalid', ['sources', key, collection, n]))
                    continue
                field = value.get('storage_field')
                content = source.get(field, '') if isinstance(field, str) else ''
                start, end = value.get('start'), value.get('end')
                if (field not in ('text', 'snippet') or not isinstance(content, str) or
                    type(start) is not int or type(end) is not int or
                    not 0 <= start < end <= len(content) or
                    value.get('region') not in ('title', 'search_snippet', 'extracted_body', 'metadata')):
                    errors.append(_error('manifest_invalid', ['sources', key, collection, n]))
                elif collection == 'visible_windows' and value.get('text') != content[start:end]:
                    errors.append(_error('manifest_integrity', ['sources', key, collection, n]))
    if errors:
        return failure()
    candidate_ids, seen_evidence = set(), set()
    by_question = {g['question_id']: g for g in candidate['questions']}
    for qid in expected:
        group = by_question[qid]
        group_index = actual.index(qid)
        if not group['items'] and not group['gaps']:
            errors.append(_error('missing_question_gap', ['questions', group_index, 'gaps']))
        gaps.extend({'question_id': qid, **deepcopy(g)} for g in group['gaps'])
        for index, raw in enumerate(group['items']):
            path = ['questions', group_index, 'items', index]
            row = deepcopy(raw)
            if row['candidate_id'] in candidate_ids:
                errors.append(_error('duplicate_evidence', path+['candidate_id']))
            candidate_ids.add(row['candidate_id'])
            fixed = []
            for n, cited in enumerate(row['links']):
                if cited['role'] != 'claim_support':
                    errors.append(_error('schema', path+['links', n, 'role']))
                    continue
                validated, error = _validate_link(cited, sources, manifest, qid, path+['links', n], decisions)
                if error:
                    errors.append(error)
                else:
                    fixed.append(validated)
            context_fixed = []
            for n, cited in enumerate(row['temporal']['context_links']):
                if cited['role'] != 'period_context':
                    errors.append(_error('unsupported_period', path+['temporal', 'context_links', n]))
                    continue
                validated, error = _validate_link(cited, sources, manifest, qid,
                    path+['temporal', 'context_links', n], decisions, context=True)
                if error:
                    errors.append(error)
                else:
                    context_fixed.append(validated)
            if len(fixed) != len(row['links']) or len(context_fixed) != len(row['temporal']['context_links']):
                continue
            row['links'] = fixed
            row['temporal']['context_links'] = context_fixed
            identities = [(l['source_id'], l['storage_field'], l['start'], l['end']) for l in fixed]
            if len(identities) != len(set(identities)):
                errors.append(_error('duplicate_link', path+['links']))
            signature = (qid, row['kind'], json.dumps(row['claim'], sort_keys=True, ensure_ascii=False), tuple(sorted(identities)))
            if signature in seen_evidence:
                errors.append(_error('duplicate_evidence', path))
            seen_evidence.add(signature)
            support = '\n'.join(l['quote'] for l in fixed+context_fixed)
            visible = '\n'.join(w.get('text', '') for sid in {l['source_id'] for l in fixed}
                for w in sources[str(sid)].get('visible_windows', []))
            errors.extend(_claim_check(row, support, visible, path))
            # 选择器已明确缺失表格结构时，不能仅凭原文出现数字就确定金额归属。
            # 此元数据只能阻止过强结论，绝不作为授予高等级的可信凭据。
            if row['kind'] == 'fact':
                linked_ids = {l['source_id'] for l in fixed}
                for gap in manifest.get('coverage_gaps', []):
                    if (isinstance(gap, dict) and gap.get('question_id') == qid and
                        gap.get('source_id') in linked_ids and gap.get('code') == 'table_context_missing'):
                        errors.append(_error('table_context_missing', path))
            temporal, time_errors = _temporal_check(row, sources, research, path)
            errors.extend(time_errors)
            if row['kind'] == 'inference' and not row['inference'].strip():
                errors.append(_error('missing_inference', path+['inference']))
            quality = _grade(row, sources, _review_gate, temporal)
            quality['temporal'] = temporal
            quality['source_dates'] = {str(sid): {'raw': sources[str(sid)].get('published_at'),
                'normalized': normalize_source_date(sources[str(sid)].get('published_at'))[0],
                'kind': 'provider_estimated_published_or_updated'} for sid in {l['source_id'] for l in fixed}}
            row.update(question_id=qid, position=len(items)+1, quality=quality)
            items.append(row)
    if errors:
        return failure()
    return {'accepted': True, 'items': items, 'gaps': gaps, 'errors': [],
            'diagnostics_truncated': False, 'decisions': decisions}


def assess_batch(candidate, manifest, policy=None):
    """公开数据契约：没有受信审核供给，永不授予verified，无副作用。

    policy只有固定版本/上限；即使普通数据自称trusted_assessments也会拒绝，
    不存在从JSON、配置、请求或环境开启可信审核的入口。
    """
    return _assess_batch(candidate, manifest, policy, _review_gate=None)
