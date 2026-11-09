"""任务生命周期与审计原子性；不连接 AI。"""

from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest


def service(store):
    from services.production.project_service import ProjectService
    return ProjectService(store)


def test_create_query_and_edit(production_store):
    svc = service(production_store)
    p = svc.create(1, '  初始名称  ', '备注')
    assert p['name'] == '初始名称' and p['status'] == 'pending'
    assert p['idea_id'] == 1 and p['created_at'] == p['updated_at']
    assert production_store.projects()[0]['idea_title'].startswith('测试选题')
    svc.edit(p['id'], '新名称', '新备注')
    assert production_store.get_project(p['id'])['notes'] == '新备注'
    actions = production_store.actions(p['id'])
    assert [a['action_type'] for a in actions] == ['created', 'updated']
    assert actions[-1]['details']['before']['name'] == '初始名称'
    assert actions[-1]['details']['after']['name'] == '新名称'


@pytest.mark.parametrize('idea_id,name', [(999, '任务'), (1, ''), (1, '  ')])
def test_invalid_creation(production_store, idea_id, name):
    with pytest.raises(ValueError):
        service(production_store).create(idea_id, name)
    assert not production_store.projects()


@pytest.mark.parametrize('status', ['pending', 'researching', 'scripting', 'storyboarding', 'assets', 'editing', 'completed'])
def test_manual_states_pause_and_restore(production_store, status):
    svc = service(production_store)
    p = svc.create(1, '任务')
    from tests.research_support import approve_research
    if status not in ('pending', 'researching'):
        approve_research(production_store, p['id'])
    svc.set_status(p['id'], status)
    count = len(production_store.actions(p['id']))
    svc.set_status(p['id'], status)
    assert len(production_store.actions(p['id'])) == count
    svc.pause(p['id'])
    paused = production_store.get_project(p['id'])
    assert paused['status'] == 'paused' and paused['resume_status'] == status
    with pytest.raises(ValueError):
        svc.create(1, '重复暂停任务')
    svc.pause(p['id'])
    with pytest.raises(ValueError):
        svc.set_status(p['id'], 'editing')
    svc.resume(p['id'])
    resumed = production_store.get_project(p['id'])
    assert resumed['status'] == status and resumed['resume_status'] is None
    history = production_store.actions(p['id'])
    assert [a['action_type'] for a in history[-2:]] == ['paused', 'resumed']
    assert history[-2]['previous_status'] == status and history[-2]['new_status'] == 'paused'
    assert history[-1]['previous_status'] == 'paused' and history[-1]['new_status'] == status
    assert all(a['created_at'] for a in history)


def test_archive_history_and_recreate(production_store):
    svc = service(production_store)
    p = svc.create(1, '旧任务')
    svc.pause(p['id'])
    svc.archive(p['id'])
    svc.archive(p['id'])
    assert not production_store.projects()
    assert production_store.projects(archived=True)[0]['id'] == p['id']
    assert len(production_store.projects(archived=None)) == 1
    for action in (lambda: svc.edit(p['id'], '改', ''), lambda: svc.resume(p['id']),
                   lambda: svc.set_status(p['id'], 'pending'), lambda: svc.pause(p['id'])):
        with pytest.raises(ValueError):
            action()
    assert svc.create(1, '新任务')['id'] != p['id']
    assert [a['action_type'] for a in production_store.actions(p['id'])] == ['created', 'paused', 'archived']


def test_duplicate_completed_and_concurrent_creation(production_store):
    svc = service(production_store)

    def create(_):
        try:
            return svc.create(1, '任务')['id']
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(create, range(4)))
    assert sum(result is not None for result in results) == 1
    from tests.research_support import approve_research
    project_id = next(r for r in results if r is not None)
    approve_research(production_store, project_id)
    svc.set_status(project_id, 'completed')
    with pytest.raises(ValueError):
        svc.create(1, '完成也占用有效名额')


def test_invalid_operations(production_store):
    svc = service(production_store)
    p = svc.create(1, '任务')
    for action in (lambda: svc.set_status(p['id'], 'invalid'), lambda: svc.resume(p['id']),
                   lambda: svc.edit(999, '任务', ''), lambda: svc.pause(999)):
        with pytest.raises(ValueError):
            action()


def test_action_failure_rolls_back_create_and_status(production_store, monkeypatch):
    svc = service(production_store)
    p = svc.create(1, '任务')

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError('injected audit error')

    monkeypatch.setattr(production_store, 'insert_action', fail)
    with pytest.raises(sqlite3.OperationalError):
        svc.set_status(p['id'], 'researching')
    with pytest.raises(sqlite3.OperationalError):
        svc.create(2, '不会残留')
    assert production_store.get_project(p['id'])['status'] == 'pending'
    assert len(production_store.projects()) == 1


def test_actions_cannot_be_rewritten(production_store):
    p = service(production_store).create(1, '任务')
    with production_store._connection() as con:
        for sql in ('UPDATE production_actions SET new_status=\'completed\'', 'DELETE FROM production_actions'):
            with pytest.raises(sqlite3.IntegrityError):
                con.execute(sql)
    assert len(production_store.actions(p['id'])) == 1
