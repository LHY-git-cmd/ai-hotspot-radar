"""费用、跨重启预算、调用锁和原子结果保存的测试。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

import pytest

from database.store import HotspotStore
from models import Hotspot


def setup_ai(tmp_path, **settings_changes):
    """创建临时热点库及独立 AI 存储，不访问网络。"""
    from database.ai_store import AIStore
    from services.ai.config import AISettings
    store = HotspotStore(tmp_path / 'ai.sqlite3')
    store.save([Hotspot(title='AI tool', url='https://example.com/tool', source='GitHub', category='AI 开源项目')])
    return AIStore(store.path, AISettings(**settings_changes))


def test_exact_decimal_cost_cache_breakdown_and_unknown_usage():
    """价格使用实际 Token，缺失细分按未命中估算，未知 usage 不等于免费。"""
    from services.ai.base import Usage
    from services.ai.config import AISettings
    from services.ai.cost_tracker import estimate_units, to_units
    settings = AISettings()
    assert estimate_units(Usage(1000, 500, 400, 600), settings) == 5216
    assert estimate_units(Usage(1000, 500), settings) == 6000
    assert estimate_units(Usage(0, 0), settings) == 0
    assert estimate_units(Usage(None, 500), settings) is None
    assert to_units(Decimal('0.0000001')) == 1
    foreign = replace(settings, price_currency='USD', cny_per_unit=Decimal('7.2'))
    assert estimate_units(Usage(1000, 500), foreign) == 43200


def test_month_is_beijing_and_thresholds_persist_across_restart(tmp_path):
    """UTC 月末已进入北京时间新月；设置不能被重新加载默认值覆盖。"""
    from database.ai_store import AIStore
    from services.ai.cost_tracker import month_key
    assert month_key(datetime(2026, 1, 31, 17, tzinfo=timezone.utc)) == '2026-02'
    store = setup_ai(tmp_path)
    store.set_budget(Decimal('50'))
    restarted = AIStore(store.path, store.settings)
    assert restarted.budget()['limit_units'] == 50000000
    assert restarted.budget()['warning'] == '正常'


def test_atomic_reservation_cannot_be_bypassed_by_two_connections(tmp_path):
    """并发事务只能预占一份剩余额度。"""
    from services.ai.base import AIError
    store = setup_ai(tmp_path)
    store.set_budget(Decimal('1'))
    first = store.claim_analysis(1, 'cache-1', 'act-1', {}, 'test-version', False)
    second = store.claim_analysis(1, 'cache-2', 'act-2', {}, 'test-version', False)

    def reserve(analysis_id):
        """两个连接并发，每次预占0.7元；只有一个可成功。"""
        try:
            return store.reserve_attempt(analysis_id, 1, 700000, {})
        except AIError as error:
            return error.kind

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, [first['id'], second['id']]))
    assert results.count('budget') == 1
    assert store.budget()['occupied_units'] == 700000
    assert store.budget()['warning'] == '警告'
    store.set_budget(Decimal('0.75'))
    assert store.budget()['warning'] == '高风险'
    store.set_budget(Decimal('0.7'))
    assert store.budget()['warning'] == '已达上限'


def test_pending_analysis_and_action_are_idempotent_across_restart(tmp_path):
    """并发和重启不能重新获得同一材料或同一主动动作的付费许可。"""
    from database.ai_store import AIStore
    from services.ai.base import AIError
    store = setup_ai(tmp_path)
    first = store.claim_analysis(1, 'cache', 'action', {}, 'v1', False)
    assert store.claim_analysis(1, 'cache', 'action', {}, 'v1', True)['id'] == first['id']
    restarted = AIStore(store.path, store.settings)
    with pytest.raises(AIError, match='进行中'):
        restarted.claim_analysis(1, 'cache', 'another-action', {}, 'v1', False)


def test_usage_settlement_unknown_cost_resolution_and_audit(tmp_path):
    """未知费用持久预占；人工核对有原因及痕迹，不能删除记录清零。"""
    from services.ai.base import Usage
    store = setup_ai(tmp_path)
    analysis = store.claim_analysis(1, 'cache', 'action', {}, 'v1', False)
    first = store.reserve_attempt(analysis['id'], 1, 100000, {'price_version': 'test'})
    store.finish_attempt(first, 'failed', Usage(), None, 'read_timeout')
    store.fail_analysis(analysis['id'], 'read_timeout')
    assert store.budget()['held_units'] == 100000
    assert store.analyses(1) == []
    assert store.runs()[0]['input_tokens'] is None
    with pytest.raises(ValueError):
        store.resolve_cost(first, Decimal('0'), '')
    store.resolve_cost(first, Decimal('0.03'), '已在服务商账单核对本次费用')
    assert store.budget()['held_units'] == 0
    assert store.budget()['estimated_units'] == 30000
    assert store.runs()[0]['resolution_reason']
    assert store.claim_analysis(1, 'cache', 'retry-after-review', {}, 'v1', False)['status'] == 'running'


def test_three_ideas_saved_atomically_history_and_actions_retained(tmp_path, ai_document):
    """成功结果和三个选题保存为一组；重分析追加，状态修改不影响旧历史。"""
    from services.ai.base import Usage
    store = setup_ai(tmp_path)
    first = store.claim_analysis(1, 'cache', 'one', {}, 'v1', False)
    attempt = store.reserve_attempt(first['id'], 1, 100000, {})
    store.finish_attempt(attempt, 'success', Usage(10, 20), 180, None)
    store.complete_analysis(first['id'], attempt, ai_document, '有限材料，未独立核验')
    ideas = store.ideas(first['id'])
    assert len(ideas) == 3
    store.set_idea_status(ideas[0]['id'], 'favorite')
    store.set_idea_status(ideas[0]['id'], 'discarded')
    assert store.ideas(first['id'])[0]['status'] == 'discarded'
    assert len(store.actions(ideas[0]['id'])) == 2
    assert store.claim_analysis(1, 'cache', 'cached', {}, 'v1', False)['cache_hit'] is True
    second = store.claim_analysis(1, 'cache', 'two', {}, 'v1', True)
    attempt2 = store.reserve_attempt(second['id'], 1, 100000, {})
    store.finish_attempt(attempt2, 'success', Usage(10, 20), 180, None)
    store.complete_analysis(second['id'], attempt2, ai_document, '未独立核验')
    assert len(store.analyses(1)) == 2
    assert len(store.ideas(first['id'])) == 3
    with pytest.raises(ValueError):
        store.set_idea_status(ideas[0]['id'], 'invalid')
