"""区分服务商日期估计、本地保存时间与数据周期；不推断财季。"""

from datetime import date, datetime
from email.utils import parsedate_to_datetime
import re

from services.research.diagnostics import ResearchValidationError


def normalize_source_date(raw):
    if not isinstance(raw, str) or not raw.strip():
        return 'unknown', 'unknown'
    value = raw.strip()
    try:
        if re.fullmatch(r'\d{4}', value) and 1 <= int(value) <= 9999:
            return value, 'year'
        if re.fullmatch(r'\d{4}-\d{2}', value):
            date(int(value[:4]), int(value[5:]), 1)  # 仅校验月份，输出不补造日期。
            return value, 'month'
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return date.fromisoformat(value).isoformat(), 'day'
        # ISO 日期必须显式包含完整日，保留输入字面精度及原时区，不补造秒。
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?', value):
            datetime.fromisoformat(value.replace('Z', '+00:00'))
            time = value[11:]
            precision = 'fraction' if '.' in time else 'second' if re.match(r'\d{2}:\d{2}:\d{2}', time) else 'minute'
            return value, precision
        parsed = parsedate_to_datetime(value)
        # RFC 1123 明确带秒和时区；不把仅日期或其他宽松格式补成午夜。
        if parsed.tzinfo is not None and re.search(r'\d{2}:\d{2}:\d{2}', value):
            return parsed.isoformat(), 'second'
    except (ValueError, TypeError, OverflowError):
        pass
    return 'unknown', 'unknown'


def source_time_context(source, as_of):
    raw = source.get('published_at')
    normalized, precision = normalize_source_date(raw)
    year = int(normalized[:4]) if normalized != 'unknown' else None
    historical = year is not None and year < int(as_of[:4])
    label = (f'{year} 年服务商估计发布或更新的来源，属于历史材料' if historical else
             f'服务商估计发布或更新日期：{normalized}' if year else '来源日期 unknown')
    return {'published_at_raw': raw, 'published_at_normalized': normalized,
        'date_precision': precision, 'date_kind': 'provider_estimated_published_or_updated',
        'local_saved_at': source.get('searched_at', 'unknown'), 'as_of': as_of,
        'modified_at': 'unknown', 'provider_snapshot_at': 'unknown', 'data_period': 'unknown',
        'historical': historical, 'label': label+'；数据实际所属周期尚未核实（unknown），不得由文章日期推断财季。'}


def forecast_text(text):
    return bool(re.search(r'预测|预计|预期|估算|假设|if\s+.*continues|forecast|projected|estimate|expected|projection', text, re.I))


def actual_language(text):
    # 保留“并非实际数据”等必要警示，不因为其中出现“实际”而错误拒绝预测说明。
    value = re.sub(r'(?:不是|并非|而非|尚非|非|不能(?:视为|当作|代表)?|不代表)实际(?:数据|增长|达到)?', '', text)
    value = re.sub(r'\b(?:not|no)\s+actual\b', '', value, flags=re.I)
    return bool(re.search(r'实际(?:数据|增长|达到)|已实现|已经实现|\bactual\b|\brealized\b', value, re.I))


def current_language(text, contexts, scope):
    """保守拦截明显现状措辞；若研究本年回顾旧料，须明确写出旧年份。"""
    if re.search(r'当前|目前|如今|currently|\bnow\b', text, re.I):
        return True
    if scope == 'forecast':
        return False
    return any(context['historical'] and context['as_of'][:4] in text
               and context['published_at_normalized'][:4] not in text for context in contexts)


def validate_time_use(item, sources, as_of, path):
    """硬性用途约束配合人工语义审核；不声称能完整理解所有自然语言。"""
    scope, period = item['time_scope'], item['data_period']
    quotes = [link['quote'] for link in item['links']]
    forecast = forecast_text(' '.join(quotes))
    contexts = [source_time_context(sources[l['source_id']], as_of) for l in item['links']]
    historical = any(context['historical'] for context in contexts)
    if forecast and (scope not in ('forecast', 'unknown') or actual_language(item['summary'])):
        raise ResearchValidationError('forecast_as_actual', '预测引文不能当作实际数据', path+['time_scope'])
    if historical and (scope == 'current' or current_language(item['summary'], contexts, scope)):
        raise ResearchValidationError('historical_as_current', '历史来源不能作为当前数据', path+['time_scope'])
    if period != 'unknown' and not any(period in quote for quote in quotes):
        raise ResearchValidationError('unsupported_period', '数据周期须在实际引文中逐字可核对，不能由文章日期推断', path+['data_period'])
    if scope == 'current' and (period == 'unknown' or as_of[:4] not in period):
        raise ResearchValidationError('unknown_as_current', '当前数据必须有明确且匹配研究年份的原文周期', path+['data_period'])


def validate_claim_time(claim, evidence, path):
    selected = [evidence[eid] for eid in claim['evidence_ids']]
    contexts = [link['time_context'] for e in selected for link in e['links'] if 'time_context' in link]
    historical = any(context['historical'] for context in contexts)
    forecast = any(e.get('time_scope') == 'forecast' or any(forecast_text(l['quote']) for l in e['links']) for e in selected)
    scope = claim.get('time_scope', 'unknown')
    if forecast and (scope not in ('forecast', 'unknown') or actual_language(claim['text'])):
        raise ResearchValidationError('forecast_as_actual', '报告不能将预测证据写成实际数据', path)
    if historical and (scope == 'current' or current_language(claim['text'], contexts, scope)):
        raise ResearchValidationError('historical_as_current', '历史来源不能表述为当前数据，请明确历史时间', path)
    if scope == 'current' and any(e.get('time_scope', 'unknown') != 'current' for e in selected):
        raise ResearchValidationError('unknown_as_current', '缺少当前周期证据，不能标记为当前数据', path)



def _v3_period_label(text):
    """仅提取明示的FY/财季标签，不将财年映射成日历覆盖日期。"""
    patterns = (
        (r'FY\s*(\d{4})\s*Q([1-4])', False),
        (r'Q([1-4])\s+(?:FISCAL(?:\s+YEAR)?|FY)\s*(\d{4})', True),
        (r'(first|second|third|fourth)\s+quarter\s+(?:fiscal(?:\s+year)?|FY)\s*(\d{4})', True),
        (r'财年\s*(\d{4})\s*第?([1-4])季度', False),
    )
    quarters = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4}
    for pattern, reverse in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            a, b = match.groups()
            year, quarter = (b, quarters.get(a.lower(), a)) if reverse else (a, b)
            return {'label_raw': match.group(), 'fiscal_year': int(year), 'fiscal_quarter': int(quarter)}
    return {'label_raw': 'unknown', 'fiscal_year': None, 'fiscal_quarter': None}


def classify_temporal(claim_text, source_context, research_context):
    """v3独立纯函数：事件、发言者、日历覆盖分开；不修改旧v2调用路径。

    source_context的覆盖日期应来自调用方已验证的原文引用。此函数不认证
    上游信息；quality只会向它传入通过位置/区域校验的上下文。
    """
    raw_date = source_context.get('published_at')
    normalized, precision = normalize_source_date(raw_date)
    result = {'event_kind': 'unknown', 'speaker_kind': 'unknown', 'temporal_type': 'unknown',
        'current_relation': 'unknown', 'coverage_start': None, 'coverage_end': None,
        'published_at_raw': raw_date, 'published_at_normalized': normalized,
        'date_precision': precision, 'calendar_publication_year': int(normalized[:4]) if normalized != 'unknown' else None,
        'research_as_of': research_context.get('as_of'), 'errors': []}
    if not isinstance(claim_text, str):
        result['errors'].append({'code': 'temporal_input', 'field': 'claim_text'})
        return result
    period = _v3_period_label(claim_text)
    supplied = _v3_period_label(source_context.get('period_label', '') or '')
    if period['fiscal_year'] and supplied['fiscal_year'] and (
            period['fiscal_year'], period['fiscal_quarter']) != (supplied['fiscal_year'], supplied['fiscal_quarter']):
        result['errors'].append({'code': 'temporal_contradiction', 'field': 'period_label'})
    result.update(period if period['fiscal_year'] else supplied)

    # 每类需发言归属+行为，未来指引还需未来范围，不能以单个expected决定。
    future = bool(re.search(r'下(?:一)?季|下(?:一)?季度|明年|未来|next\s+(?:quarter|year)|guidance|指引', claim_text, re.I))
    analyst = bool(re.search(r'分析师.{0,16}(?:预测|预计|预期)|analysts?\s+(?:expect|forecast|project|predict)', claim_text, re.I))
    market = bool(re.search(r'市场(?:一致)?预期|market\s+(?:consensus\s+)?expects?|consensus\s+expects?', claim_text, re.I))
    guidance = future and bool(re.search(r'(?:公司|管理层|Oracle).{0,18}(?:预计|指引|预测)|(?:the\s+)?company\s+(?:expects?|guides?|forecasts?)', claim_text, re.I))
    actual = bool(re.search(r'(?:公布|发布|报告).{0,90}(?:业绩|收入|结果|增长)|\b(?:reported|announced|released)\b.{0,140}\b(?:revenue|results|earnings|grew)\b', claim_text, re.I))
    if re.search(r'(?:将|计划|准备).{0,5}(?:公布|发布)|\bwill\s+(?:report|announce|release)', claim_text, re.I):
        actual = False
    if actual and future and not guidance and not analyst and re.search(r'expected|forecast|预期|预测', claim_text, re.I):
        # “报道了下一季的预估”没有证明实际结果；不把reported本身当实绩。
        actual = False
    if actual and (guidance or analyst and future):
        result['errors'].append({'code': 'mixed_temporal_claim', 'field': 'event_kind'})
    if actual:
        result['event_kind'] = 'actual_result'
        if re.search(r'公司|管理层|Oracle\s+(?:reported|announced)|company\s+(?:reported|announced)', claim_text, re.I):
            result['speaker_kind'] = 'company'
    elif analyst and future:
        result.update(event_kind='forecast', speaker_kind='analyst', temporal_type='analyst_forecast')
    elif guidance:
        result.update(event_kind='guidance', speaker_kind='company', temporal_type='company_guidance')
    elif market:
        result.update(event_kind='expectation', speaker_kind='market', temporal_type='market_expectation')
    elif re.search(r'媒体|Reuters|BBC|记者|media\s+reports?', claim_text, re.I):
        result['speaker_kind'] = 'media'

    # 只有明确截至/覆盖日期才能参与日历关系，不能拿文章署期推断。
    end_match = re.search(r'(?:截至|季度结束于|quarter\s+ended|period\s+ended|as\s+of)\s*(\d{4}-\d{2}-\d{2})', claim_text, re.I)
    interval = re.search(r'(?:期间|覆盖|period)\s*(\d{4}-\d{2}-\d{2})\s*(?:至|到|to)\s*(\d{4}-\d{2}-\d{2})', claim_text, re.I)
    extracted = {'coverage_start': interval[1] if interval else None,
                 'coverage_end': interval[2] if interval else end_match[1] if end_match else None}
    dates = {}
    for field in ('coverage_start', 'coverage_end'):
        provided = source_context.get(field)
        value = extracted[field] or provided
        if provided and extracted[field] and provided != extracted[field]:
            result['errors'].append({'code': 'temporal_contradiction', 'field': field})
        if value is not None:
            try:
                dates[field] = date.fromisoformat(value)
                result[field] = value
            except (ValueError, TypeError):
                result['errors'].append({'code': 'temporal_contradiction', 'field': field})
    try:
        as_of = date.fromisoformat(research_context['as_of'])
        window = research_context.get('target_window') or {}
        start = date.fromisoformat(window['start']) if window.get('start') else None
        end = date.fromisoformat(window['end']) if window.get('end') else None
        if start and end and start > end or end and end > as_of:
            raise ValueError('invalid window')
    except (ValueError, KeyError, TypeError):
        result['errors'].append({'code': 'temporal_input', 'field': 'research_context'})
        return result
    left, right = dates.get('coverage_start'), dates.get('coverage_end')
    if left and right and left > right:
        result['errors'].append({'code': 'temporal_contradiction', 'field': 'coverage_range'})
    if result['event_kind'] == 'actual_result' and right and right > as_of:
        result['errors'].append({'code': 'temporal_contradiction', 'field': 'coverage_end'})
    if right and start and end:
        relation = ('before_target' if right < start else 'future' if right > end else
                    'partially_overlaps' if left and left < start else 'within_target')
        result['current_relation'] = relation
        if result['event_kind'] == 'actual_result' and not result['errors']:
            result['temporal_type'] = {'before_target': 'historical_actual',
                                       'within_target': 'current_actual'}.get(relation, 'unknown')
    elif result['fiscal_year']:
        result['current_relation'] = 'label_only'
    if result['errors']:
        result['temporal_type'] = 'unknown'
    return result
