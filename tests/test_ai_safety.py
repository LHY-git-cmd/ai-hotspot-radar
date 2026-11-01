"""预算闭环与异常恢复的补充边界测试，不调用真实服务商。"""

from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import replace
from unittest.mock import Mock
import sqlite3

from database.ai_store import AIStore
from database.store import HotspotStore
from models import Hotspot
from services.ai.base import ProviderReply, AIError, Usage
from services.ai.config import AISettings
from services.ai.analyzer import Analyzer
from services.ai.mock import MockProvider
from services.recalculate import recalculate_scores


def create(tmp_path, document, count=1, replies=None):
    """准备独立的临时热点和可控 Provider 序列。"""
    settings = AISettings()
    store = AIStore(tmp_path / 'safety.sqlite3', settings)
    now = datetime.now(timezone.utc).isoformat()
    store.save([Hotspot(title=f'AI coding tool {i}', url=f'https://example.com/{i}', source='GitHub',
        source_key=str(i), category='AI 开源项目', score=100 + i, collected_at=now,
        pushed_at=now, published_at=now) for i in range(1, count+1)], cycle_id='first', source='GitHub')
    recalculate_scores(store)
    provider = MockProvider(replies if replies is not None else [ProviderReply(document, Usage(100, 200))])
    return store, Analyzer(store, provider, settings, sleep=lambda _: None), provider


def test_candidates_are_limited_to_ten_and_material_confirmation_is_checked(tmp_path, ai_document):
    store, analyzer, provider = create(tmp_path, ai_document, count=12)
    assert len(analyzer.candidates()) == 10
    preview_key = analyzer.fingerprint(analyzer.materials(1))
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE hotspots SET summary='new facts' WHERE id=1")
    assert analyzer.analyze(1, 'changed', expected_cache_key=preview_key)['status'] == 'failed'
    assert not provider.calls


def test_retry_must_stop_when_second_reservation_would_exceed_budget(tmp_path, ai_document):
    from services.ai.cost_tracker import reservation_units
    from services.ai.prompts import build_messages
    store, analyzer, provider = create(tmp_path, ai_document, replies=[AIError('rate_limit', '限流', retryable=True)])
    reserve = reservation_units(build_messages(analyzer.materials(1)), analyzer.settings)
    store.set_budget(Decimal(reserve) / 1000000)
    result = analyzer.analyze(1, 'retry-budget')
    assert result['status'] == 'failed'
    assert len(provider.calls) == 1 and len(store.runs()) == 1
    assert store.budget()['warning'] == '已达上限'


def test_response_saved_usage_even_when_analysis_persistence_fails(tmp_path, monkeypatch, ai_document):
    store, analyzer, provider = create(tmp_path, ai_document)
    monkeypatch.setattr(store, 'complete_analysis', Mock(side_effect=sqlite3.OperationalError('secret')))
    result = analyzer.analyze(1, 'persistence-failure')
    assert result['status'] == 'failed'
    assert not store.analyses() and not store.ideas()
    assert store.runs()[0]['input_tokens'] == 100
    assert store.budget()['estimated_units'] > 0


def test_restart_pending_attempt_remains_reserved_and_cannot_replay(tmp_path, ai_document):
    store, analyzer, provider = create(tmp_path, ai_document)
    materials = analyzer.materials(1)
    analysis = store.claim_analysis(1, analyzer.fingerprint(materials), 'crashed', materials, 'test', False)
    store.reserve_attempt(analysis['id'], 1, 120000, {})
    restarted = AIStore(store.path, AISettings())
    second = Analyzer(restarted, provider, AISettings())
    assert second.analyze(1, 'new-action')['status'] == 'failed'
    assert not provider.calls
    assert restarted.budget()['held_units'] == 120000
    restarted.acknowledge_interrupted(analysis['id'])
    restarted.resolve_cost(restarted.runs()[0]['id'], Decimal('0'), '服务商账单核实未计费')
    assert restarted.budget()['held_units'] == 0


def test_unknown_usage_success_keeps_hold_and_price_snapshot(tmp_path, ai_document):
    store, analyzer, provider = create(tmp_path, ai_document, replies=[ProviderReply(ai_document, Usage())])
    assert analyzer.analyze(1, 'missing-usage')['status'] == 'success'
    assert store.budget()['held_units'] > 0
    row = store.runs()[0]
    assert row['estimated_cost_units'] is None and row['input_tokens'] is None
    updated = AIStore(store.path, replace(AISettings(), output_price=Decimal('999')))
    assert updated.runs()[0]['price_json'] == row['price_json']
    assert updated.runs()[0]['price_version'] == row['price_version']


def test_explicit_months_do_not_reassign_old_attempt_costs(tmp_path, ai_document):
    store, analyzer, provider = create(tmp_path, ai_document)
    claim = store.claim_analysis(1, 'month-cache', 'month-action', {}, 'test', False)
    january = datetime(2026, 1, 15, tzinfo=timezone.utc)
    february = datetime(2026, 2, 15, tzinfo=timezone.utc)
    store.reserve_attempt(claim['id'], 1, 100000, {}, now=january)
    assert store.budget(now=january)['held_units'] == 100000
    assert store.budget(now=february)['held_units'] == 0


def test_clock_staleness_alone_does_not_create_chargeable_new_version(tmp_path, ai_document):
    store, analyzer, provider = create(tmp_path, ai_document)
    first = analyzer.materials(1)
    second = dict(first)
    second['E3_deterministic_scores'] = dict(first['E3_deterministic_scores'], score_stale=True)
    assert analyzer.fingerprint(first) == analyzer.fingerprint(second)
