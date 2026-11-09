"""只读输入的原文选窗；无文件/配置/网络/数据库访问，不是精确Tokenizer。

所有范围采用Python Unicode码点[start,end)。输出仅为原字段切片；
max_utf8_bytes约束windows的JSON大小，未来调用方仍须检查完整API请求。
"""

import hashlib
import json
import re

from services.research.temporal import _v3_period_label

SELECTOR_VERSION = 'related-paragraphs-v1'


def _json_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))


def _gaps(gaps, qid, sid, code, **details):
    gap = {'question_id': qid, 'source_id': sid, 'code': code, **details}
    if gap not in gaps:
        gaps.append(gap)


def _ranges(source):
    regions = source.get('regions')
    if regions is not None:
        return regions
    regions = []
    # 没有DOM，不将“已提取”视为区域已认证；可用于低等级正文候选。
    for field, kind in (('text', 'extracted_body'), ('snippet', 'search_snippet')):
        content = source.get(field, '')
        if not content:
            continue
        regions.append({'segment_id': f'{source["source_id"]}-{field}', 'region': kind,
            'storage_field': field, 'start': 0, 'end': len(content), 'boundary_confidence': 'heuristic'})
    return regions


def _paragraphs(source):
    paragraphs = []
    for region in _ranges(source):
        field = region.get('storage_field')
        content = source.get(field, '')
        start, end = region.get('start'), region.get('end')
        if field not in ('text', 'snippet') or not isinstance(content, str) or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(content):
            continue
        if region.get('region') in ('title', 'metadata'):
            continue
        if field == 'text' and source.get('extraction_status') != 'success':
            continue
        # 每个原始行是优先段落；超长行再按原始句末切分，不改空白。
        for match in re.finditer(r'[^\n]+', content[start:end]):
            left, right = start+match.start(), start+match.end()
            line = content[left:right]
            normalized = ' '.join(line.casefold().split())
            title = ' '.join(source.get('title', '').casefold().split())
            if region.get('boundary_confidence') != 'explicit' and (
                title and normalized == title or re.match(r'^(skip to|image source:|by\s+|home\s*$)', line, re.I)):
                continue
            spans = [(left, right)]
            if len(line) > 1200:
                # 单个巨大无句末段不会为数字截取“裸数值”，而是整段因预算省略。
                spans = [(left+m.start(), left+m.end()) for m in re.finditer(r'.+?(?:[。！？]|\.(?=\s|$)|$)', line)]
            for a, b in spans:
                if a < b:
                    paragraphs.append({'start': a, 'end': b, 'text': content[a:b],
                        'region': region['region'], 'storage_field': field,
                        'segment_id': region['segment_id'], 'boundary_confidence': region.get('boundary_confidence', 'unknown')})
    # 表格作为完整块选择，不能只取命中的数值行而丢掉表头/单位。
    grouped = []
    for part in paragraphs:
        if (grouped and part['text'].lstrip().startswith('|') and
            grouped[-1]['text'].lstrip().startswith('|') and
            part['segment_id'] == grouped[-1]['segment_id'] and
            part['storage_field'] == grouped[-1]['storage_field'] and
            part['start']-grouped[-1]['end'] <= 2):
            previous = grouped[-1]
            previous['end'] = part['end']
            previous['text'] = source[part['storage_field']][previous['start']:part['end']]
        else:
            grouped.append(dict(part))
    return grouped


def _merge_windows(windows, sources):
    """只合并同来源同区域的真实相邻范围，绝不拼接跨段省略文本。"""
    by_id = {s['source_id']: s for s in sources}
    merged = []
    for current in sorted(windows, key=lambda w: (w['source_id'], w['storage_field'], w['start'])):
        w = dict(current)
        w['question_ids'] = list(current['question_ids'])
        previous = merged[-1] if merged else None
        if (previous and previous['source_id'] == w['source_id'] and
            previous['storage_field'] == w['storage_field'] and
            previous['segment_id'] == w['segment_id'] and previous['region'] == w['region'] and
            w['start'] <= previous['end']+1):
            previous['end'] = max(previous['end'], w['end'])
            previous['text'] = by_id[w['source_id']][w['storage_field']][previous['start']:previous['end']]
            previous['question_ids'] = sorted(set(previous['question_ids']) | set(w['question_ids']))
            previous['window_id'] = f'w-{w["source_id"]}-{w["storage_field"]}-{previous["start"]}-{previous["end"]}'
            previous['text_hash'] = hashlib.sha256(previous['text'].encode()).hexdigest()
        else:
            merged.append(w)
    return merged


def select_windows(sources, questions, *, max_utf8_bytes):
    """最多3个相关/上下文段每题每源；只在原段边界选取，不扩大前缀发送全文。"""
    if type(max_utf8_bytes) is not int or max_utf8_bytes < 0:
        raise ValueError('窗口预算须为非负整数字节数')
    windows, gaps, coverage = [], [], []
    options = []
    sources = sorted(sources, key=lambda s: s['source_id'])
    for question in questions:
        qid = question['id']
        terms = list(dict.fromkeys(t.strip() for t in question.get('keywords', []) if isinstance(t, str) and t.strip()))
        for source in sources:
            if qid not in source.get('question_ids', []):
                continue
            sid = source['source_id']
            parts = _paragraphs(source)
            numbers = [t for t in terms if re.search(r'\d', t)]
            scored = []
            for part in parts:
                hits = [t for t in terms if t.casefold() in part['text'].casefold()]
                score = sum(8 if t in numbers else 2 for t in hits)
                if score:
                    scored.append((score, part))
            scored.sort(key=lambda pair: (-pair[0], pair[1]['start']))
            chosen = [p for _, p in scored[:2]]
            # 数字命中段本身无完整财季时，另找明确期间，而非从文章日期推断。
            if chosen and not any(_v3_period_label(p['text'])['fiscal_year'] for p in chosen):
                period_part = next((p for p in parts if _v3_period_label(p['text'])['fiscal_year']), None)
                if period_part and period_part not in chosen:
                    chosen = chosen[:2]+[period_part]
            # 相关数值段之前的管理层/引语引导行是必要归属上下文。
            if chosen:
                # FY2025等期间关键词不是数值命中点，否则会漏掉真正数值段前的发言归属。
                numeric_terms = [t for t in numbers if re.fullmatch(r'[$€]?\d[\d,.]*%?', t)]
                anchors = [p['start'] for p in chosen if any(t.casefold() in p['text'].casefold() for t in numeric_terms)]
                first = min(anchors) if anchors else chosen[0]['start']
                previous = next((p for p in reversed(parts) if p['end'] < first and first-p['end'] <= 5), None)
                if previous and re.search(r'commentary|management|said|指引|表示|管理层', previous['text'], re.I) and previous not in chosen:
                    chosen.append(previous)
            for rank, part in enumerate(chosen):
                options.append((rank, qid, sid, part))
            coverage.append({'question_id': qid, 'source_id': sid, 'terms': terms,
                             'parts': parts, 'source': source})
    # 轮转题/源的首段优先，然后补上下文，避免一个长来源用完预算。
    options.sort(key=lambda value: (value[0], value[1], value[2], value[3]['start']))
    for _, qid, sid, part in options:
        same = next((w for w in windows if w['source_id'] == sid and w['storage_field'] == part['storage_field'] and
                     w['start'] == part['start'] and w['end'] == part['end']), None)
        if same:
            merged = {**same, 'question_ids': sorted(set(same['question_ids']) | {qid})}
            proposal = [merged if w is same else w for w in windows]
        else:
            window = {**part, 'source_id': sid, 'question_ids': [qid],
                'window_id': f'w-{sid}-{part["storage_field"]}-{part["start"]}-{part["end"]}',
                'text_hash': hashlib.sha256(part['text'].encode('utf-8')).hexdigest()}
            proposal = windows+[window]
        merged = _merge_windows(proposal, sources)
        if _json_bytes(merged) <= max_utf8_bytes:
            windows = merged
        else:
            _gaps(gaps, qid, sid, 'omitted_budget', omitted_range=[part['start'], part['end']],
                  reason='完整段落和位置元数据无法容纳；未截成裸数字')
    for entry in coverage:
        qid, sid, source, parts, terms = (entry[k] for k in ('question_id', 'source_id', 'source', 'parts', 'terms'))
        visible = '\n'.join(w['text'] for w in windows if w['source_id'] == sid and qid in w['question_ids'])
        available = '\n'.join(p['text'] for p in parts)
        statuses = {}
        for term in terms:
            if term.casefold() not in available.casefold():
                statuses[term] = 'missing'
                _gaps(gaps, qid, sid, 'term_not_found', term=term)
            elif term.casefold() not in visible.casefold():
                statuses[term] = 'omitted_budget'
                _gaps(gaps, qid, sid, 'omitted_budget', term=term)
            else:
                statuses[term] = 'matched'
        missing = []
        checks = {'metric': r'收入|消费|营收|revenue|consumption|capex|capital expenditure|RPO',
                  'unit': r'%|\$|billion|million|USD|亿元|万亿|百万美元',
                  'period': r'FY\s*\d{4}|fiscal\s+(?:year\s+)?\d{4}|截至\s*\d{4}-\d{2}-\d{2}',
                  'entity': r'Oracle|公司|微软|Microsoft|Google|Amazon',
                  'basis': r'同比|环比|year.over.year|constant.currency|USD|in the quarter',
                  'speaker': r'CEO|CFO|said|management|commentary|管理层|表示'}
        roles = {role: {'available': bool(re.search(pattern, available, re.I)),
                        'sent': bool(re.search(pattern, visible, re.I)),
                        'relation': 'unknown'} for role, pattern in checks.items()}
        if re.search(r'\d', visible):
            # 可知的最小数值角色；未知不猜，不声称通用语义完整性。
            for role in ('metric', 'unit', 'period', 'entity'):
                pattern = checks[role]
                if not re.search(pattern, visible, re.I):
                    missing.append(role)
            # 题目显式要求基准/发言者时，它们也属于必要上下文。
            for role in ('basis', 'speaker'):
                if re.search(checks[role], ' '.join(terms), re.I) and not roles[role]['sent']:
                    missing.append(role)
            if missing:
                _gaps(gaps, qid, sid, 'context_incomplete', missing_context=missing,
                      reason='context_not_selected' if any(re.search(checks[r], available, re.I) for r in missing) else 'context_not_found')
        if '|' in available:
            table_lines = [line for line in visible.splitlines() if '|' in line]
            table_text = '\n'.join(table_lines)
            if table_lines and not (
                re.search(r'FY|fiscal|Q[1-4]|季度|期间|Period|Year', table_text, re.I) and
                re.search(checks['unit'], table_text, re.I) and
                re.search(r'指标|收入|Revenue|Capex|Expenditure', table_text, re.I)):
                _gaps(gaps, qid, sid, 'table_context_missing', missing_context=['table_headers', 'unit', 'period'])
        if source.get('extraction_status') != 'success':
            _gaps(gaps, qid, sid, 'body_unavailable')
        entry['required_terms'] = statuses
        entry['missing_context'] = missing
        entry['context_roles'] = roles
    windows.sort(key=lambda w: (w['source_id'], w['storage_field'], w['start']))
    return {'windows': windows, 'coverage_gaps': gaps,
        'coverage': [{k: c[k] for k in ('question_id', 'source_id', 'required_terms', 'missing_context', 'context_roles')} for c in coverage],
        'selected_utf8_bytes': _json_bytes(windows) if windows else 0,
        'conservative_token_upper': _json_bytes(windows) if windows else 0,
        'offset_unit': 'unicode_codepoint', 'selector_version': SELECTOR_VERSION,
        'text_truncated': any(sum(w['end']-w['start'] for w in windows if w['source_id'] == s['source_id'] and w['storage_field'] == 'text') < len(s.get('text', '')) for s in sources)}
