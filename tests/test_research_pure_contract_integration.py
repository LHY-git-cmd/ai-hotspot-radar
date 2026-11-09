"""仅纯函数间数据契约集成，不代表服务层或数据库持久化验收。"""

from copy import deepcopy
from pathlib import Path
import json
import pytest

from services.research.materials import select_windows
from services.research.quality import assess_batch
from services.research.temporal import classify_temporal
from tests.research_quality_cases import source, setup, item, link, CONTEXT, assert_grade, assert_rejected


def test_s26_windows_to_quality_and_old_window_rejection():
    fixtures = Path(__file__).parent / 'fixtures/research_quality'
    text = (fixtures/'s26.txt').read_text(encoding='utf-8')
    metadata = json.loads((fixtures/'s26.json').read_text(encoding='utf-8'))
    s = source(26, text=text)
    s['published_at'] = metadata['published_at']
    selected = select_windows([s], [{'id': 'Q1', 'keywords': ['Oracle', 'GPU', '52%', '336%', 'fiscal 2025']}],
                              max_utf8_bytes=3500)
    s['visible_windows'] = selected['windows']
    c, m = setup(s)
    metric_window = next(i for i, w in enumerate(s['visible_windows']) if '336%' in w['text'])
    period_window = next(i for i, w in enumerate(s['visible_windows']) if 'second quarter fiscal 2025' in w['text'])
    for value, metric in [('52', 'Cloud Infrastructure revenue'), ('336', 'GPU consumption')]:
        v = deepcopy(item(c))
        v['candidate_id'] = value
        v['claim'].update(value=value, metric=metric)
        v['links'] = [link(s, metric_window)]
        v['temporal']['period'].update(label_raw='second quarter fiscal 2025', fiscal_year=2025, fiscal_quarter=2)
        v['temporal']['context_links'] = [link(s, period_window, role='period_context')]
        doc = {'questions': [{'question_id': 'Q1', 'items': [v], 'gaps': []}]}
        r = assess_batch(doc, m)
        assert_grade(r, 'single_source')
        assert r['items'][0]['quality']['temporal']['fiscal_year'] == 2025
        assert r['items'][0]['quality']['temporal']['fiscal_quarter'] == 2
        assert r['items'][0]['quality']['temporal']['coverage_end'] is None
        legacy = deepcopy(m)
        legacy['sources']['26']['visible_windows'] = [{
            **s['visible_windows'][metric_window], 'start': 0, 'end': 682, 'text': text[:682]}]
        assert_rejected(assess_batch(doc, legacy), 'quote_not_visible')


def test_three_pure_modules_do_not_access_io_or_environment(monkeypatch):
    # 输入先准备，随后阻断所有外部效果；不是在运行前屏蔽被测校验函数。
    s = source()
    c, m = setup(s)

    def forbidden(*args, **kwargs):
        raise AssertionError('纯函数不得访问文件/网络/数据库/环境')

    monkeypatch.setattr('builtins.open', forbidden)
    monkeypatch.setattr('pathlib.Path.open', forbidden)
    monkeypatch.setattr('socket.socket.connect', forbidden)
    monkeypatch.setattr('sqlite3.connect', forbidden)
    monkeypatch.setattr('os.getenv', forbidden)
    assert_grade(assess_batch(c, m), 'single_source')
    assert classify_temporal('expected growth', {}, CONTEXT)['temporal_type'] == 'unknown'
    assert select_windows([s], m['questions'], max_utf8_bytes=1500)['windows']
