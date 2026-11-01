"""第二期服务集成测试：只用模拟采集器和临时 SQLite。"""

from datetime import datetime, timezone
from unittest.mock import Mock
from database.store import HotspotStore
from models import CollectionResult, Hotspot
from services.refresh import refresh_sources

NOW = datetime(2026, 1, 3, tzinfo=timezone.utc)


def collected(**changes):
    """模拟 GitHub 官方采集结果，明确区分 API ID 和指标。"""
    return Hotspot(**(dict(title='AI coding tool', url='https://example.com/tool',
                          source='GitHub', source_key='101', category='AI 开源项目',
                          score=100, forks=0, collected_at=NOW.isoformat(),
                          published_at=NOW.isoformat(), pushed_at=NOW.isoformat()) | changes))


def test_refresh_saves_snapshots_scores_and_completed_cycle_is_not_recollected(tmp_path):
    """一个来源失败时另一个写入快照和评分；同周期重入不再调用成功采集器。"""
    from collectors.http import CollectionError
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    github = Mock(return_value=CollectionResult([collected()]))
    hn = Mock(side_effect=CollectionError('Hacker News 请求超时'))
    report = refresh_sources(store, {'GitHub': github, 'Hacker News': hn}, cycle_id='one', now=NOW)
    assert report['GitHub'].snapshots == 1
    assert report['Hacker News'].error
    assert store.collection_run('one', 'Hacker News')['status'] == 'failed'
    assert len(store.history(1)) == 1
    assert store.ranked_items()[0]['rating']['heat_score'] is not None
    refresh_sources(store, {'GitHub': github}, cycle_id='one', now=NOW)
    github.assert_called_once()
    assert len(store.history(1)) == 1


def test_recalculation_is_local_and_does_not_add_snapshots(tmp_path, monkeypatch):
    """重新评分不调用 requests，也不修改采集任务和历史行数。"""
    from services.recalculate import recalculate_scores
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    store.save([collected()], cycle_id='one', source='GitHub')
    monkeypatch.setattr('requests.get', Mock(side_effect=AssertionError('不应联网')))
    assert recalculate_scores(store, now=NOW) == {'updated': 1, 'error': None}
    assert recalculate_scores(store, now=NOW)['updated'] == 1
    assert len(store.history(1)) == 1
    assert len(store.recent_runs()) == 1
    assert store.ranked_items()[0]['stale'] == 0


def test_scoring_failure_keeps_old_scores_and_new_snapshots(tmp_path, monkeypatch, caplog):
    """评分故障和采集事务隔离，旧评分保留并标记过期，错误不泄漏秘密。"""
    from services.recalculate import recalculate_scores
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    refresh_sources(store, {'GitHub': lambda: CollectionResult([collected()])}, cycle_id='one', now=NOW)
    before = store.ranked_items()[0]['rating']
    monkeypatch.setattr('services.recalculate.score_hotspot', Mock(side_effect=RuntimeError('test-secret')))
    result = recalculate_scores(store, now=NOW)
    assert result['error'] and 'test-secret' not in result['error']
    assert store.ranked_items()[0]['rating'] == before
    assert store.ranked_items()[0]['stale'] == 1
    report = refresh_sources(store, {'GitHub': lambda: CollectionResult([collected(score=150)])},
                             cycle_id='two', now=NOW)
    assert not report['GitHub'].error
    assert any('评分' in warning for warning in report['GitHub'].warnings)
    assert len(store.history(1)) == 2
    assert 'test-secret' not in caplog.text


def test_duplicate_in_one_batch_cannot_replace_first_snapshot_or_current_value(tmp_path):
    """一个来源响应内同对象重复时，快照和当前值保持一致且只采纳首条。"""
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    store.save([collected(score=1), collected(score=9)], cycle_id='one', source='GitHub')
    assert len(store.history(1)) == 1
    assert store.history(1)[0]['stars'] == 1
    assert store.search()[0]['score'] == 1


def test_failed_batch_rolls_back_and_records_failure(tmp_path):
    """一条无效记录造成整批回滚，但仍有失败任务记录。"""
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    report = refresh_sources(store, {'GitHub': lambda: CollectionResult([
        collected(), collected(title='', url='https://example.com/bad', source_key='102')])},
        cycle_id='one', now=NOW)
    assert report['GitHub'].error
    assert store.count() == 0
    assert store.collection_run('one', 'GitHub')['status'] == 'failed'


def test_inputs_changed_while_scoring_does_not_mark_old_results_current(tmp_path, monkeypatch):
    """另一个刷新在计算期间写入时，旧输入不能覆盖新数据的过期标记。"""
    import services.recalculate as service
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    store.save([collected()], cycle_id='one', source='GitHub')
    actual = service.score_hotspot

    def concurrent_update(item, snapshots, **kwargs):
        """在输入读取和评分保存之间插入真实的模拟新周期。"""
        store.save([collected(score=999)], cycle_id='two', source='GitHub')
        return actual(item, snapshots, **kwargs)

    monkeypatch.setattr(service, 'score_hotspot', concurrent_update)
    result = service.recalculate_scores(store, now=NOW)
    assert result['error']
    assert store.ranked_items()[0]['rating'] is None


def test_ranking_source_category_sort_and_missing_scores(tmp_path):
    """排名使用已归一化的评分，空分靠后，搜索筛选不改变评分。"""
    from services.recalculate import recalculate_scores
    from services.ranking import rank_items
    store = HotspotStore(tmp_path / 'radar.sqlite3')
    store.save([collected(), collected(title='Unrelated', source_key='102',
        url='https://example.com/other', score=0)], cycle_id='one', source='GitHub')
    recalculate_scores(store, now=NOW)
    rows = store.ranked_items()
    ranked = rank_items(rows, category='AI 编程', sort_by='video_score')
    assert [row['title'] for row in ranked] == ['AI coding tool']
    assert rank_items(rows, source='Hacker News') == []
    assert rank_items(rows, query='ａｉ')[0]['rating'] == ranked[0]['rating']
    assert rank_items(rows, sort_by='video_score')[0]['title'] == 'AI coding tool'


def test_collectors_preserve_actual_public_secondary_metrics(monkeypatch):
    """ID、零 Forks/评论数以及真实时间按官方字段映射，不互换指标。"""
    from collectors.github import collect as github
    from collectors.hacker_news import collect as hn
    monkeypatch.setattr('collectors.github.get_json', lambda *a, **kw: {'items': [{
        'id': 123, 'full_name': 'owner/AI', 'html_url': 'https://github.com/owner/AI',
        'stargazers_count': 0, 'forks_count': 0, 'pushed_at': NOW.isoformat()}]})
    gh = github(now=NOW).items[0]
    assert gh.source_key == '123' and gh.score == 0 and gh.forks == 0
    assert gh.pushed_at == NOW.isoformat()
    monkeypatch.setattr('collectors.hacker_news.get_json', lambda url, **kw:
        [321] if 'topstories' in url else {'id': 321, 'type': 'story', 'title': 'AI coding tool',
                                         'time': int(NOW.timestamp()), 'score': 0, 'descendants': 0})
    news = hn(now=NOW).items[0]
    assert news.source_key == '321' and news.score == 0 and news.comments == 0
    assert news.forks is None
