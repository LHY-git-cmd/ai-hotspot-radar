"""完整版本、独立序列、恢复和历史保护。"""

from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest


def setup(store):
    from services.production.project_service import ProjectService
    from services.production.version_service import VersionService
    p = ProjectService(store).create(1, '版本任务')
    from tests.research_support import approve_research
    approve_research(store, p['id'])
    return p, VersionService(store)


def test_multiple_versions_and_complete_details(production_store):
    p, svc = setup(production_store)
    content = {'正文': '完整长文🌏\n' * 5000, '分段': [{'秒': 0, '值': None}]}
    one = svc.create(p['id'], 'script', content, note='初稿')
    two = svc.create(p['id'], 'script', '人工修改\n全文', source='manual', note='二稿')
    assert one['version_number'] == 1 and two['version_number'] == 2
    assert svc.details(p['id'], one['id'])['content'] == content
    assert one['created_at'] and one['note'] == '初稿'
    assert [v['id'] for v in svc.history(p['id'], 'script')] == [two['id'], one['id']]


def test_restore_appends_and_preserves_history(production_store):
    p, svc = setup(production_store)
    one = svc.create(p['id'], 'research', {'原始': ['全部内容']}, source='ai', note='外部导入记录')
    svc.create(p['id'], 'research', '修改后')
    restored = svc.restore(p['id'], one['id'], object_id=one['object_id'], note='恢复初稿')
    assert restored['version_number'] == 3 and restored['source'] == 'restore'
    assert restored['restored_from_version_id'] == one['id']
    assert restored['content'] == one['content']
    assert svc.details(p['id'], one['id']) == one
    assert len(svc.history(p['id'], 'research')) == 3
    assert production_store.actions(p['id'])[-1]['action_type'] == 'version_restored'


def test_types_objects_and_tasks_have_independent_sequences(production_store):
    from services.production.project_service import ProjectService
    p, svc = setup(production_store)
    other = ProjectService(production_store).create(2, '其他任务')
    from tests.research_support import approve_research
    approve_research(production_store, other['id'])
    versions = [svc.create(p['id'], kind, {'类型': kind}) for kind in
                ('script', 'research', 'storyboard', 'asset', 'editing_guide')]
    second = svc.create(p['id'], 'script', '第二份脚本', object_key='secondary')
    foreign = svc.create(other['id'], 'script', '其他任务的脚本')
    assert all(v['version_number'] == 1 for v in [*versions, second, foreign])
    with pytest.raises(ValueError):
        svc.details(other['id'], versions[0]['id'])
    with pytest.raises(ValueError):
        svc.restore(p['id'], foreign['id'], object_id=versions[0]['object_id'])
    with pytest.raises(ValueError):
        svc.restore(p['id'], second['id'], object_id=versions[0]['object_id'])
    assert len(svc.history(p['id'], 'script')) == 1


def test_concurrent_versions_are_unique_and_gapless(production_store):
    p, svc = setup(production_store)
    with ThreadPoolExecutor(max_workers=4) as pool:
        versions = list(pool.map(lambda n: svc.create(p['id'], 'script', {'n': n}), range(8)))
    assert sorted(v['version_number'] for v in versions) == list(range(1, 9))


@pytest.mark.parametrize('kwargs', [{'content_type': 'invalid', 'content': 'x'},
    {'content_type': 'script', 'content': float('nan')},
    {'content_type': 'script', 'content': {1, 2}},
    {'content_type': 'script', 'content': 'x', 'source': 'restore'},
    {'content_type': 'script', 'content': 'x', 'object_key': ' '}])
def test_invalid_versions_leave_no_objects(production_store, kwargs):
    p, svc = setup(production_store)
    with pytest.raises(ValueError):
        svc.create(p['id'], **kwargs)
    assert all(obj['content_type'] == 'research' for obj in production_store.objects(p['id']))


def test_archive_blocks_versions_but_keeps_read_access(production_store):
    from services.production.project_service import ProjectService
    p, svc = setup(production_store)
    v = svc.create(p['id'], 'script', '历史正文')
    ProjectService(production_store).archive(p['id'])
    with pytest.raises(ValueError):
        svc.create(p['id'], 'script', '新正文')
    with pytest.raises(ValueError):
        svc.restore(p['id'], v['id'], object_id=v['object_id'])
    assert svc.details(p['id'], v['id'])['content'] == '历史正文'


def test_database_prevents_overwrite_and_cross_object_restore(production_store):
    p, svc = setup(production_store)
    one = svc.create(p['id'], 'script', '原文')
    other = svc.create(p['id'], 'research', '研究')
    with production_store._connection() as con:
        for sql in ('UPDATE production_versions SET content_json=\'"覆盖"\'', 'DELETE FROM production_versions'):
            with pytest.raises(sqlite3.IntegrityError):
                con.execute(sql)
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('''INSERT INTO production_versions(project_id,object_id,version_number,content_json,source,note,created_at,restored_from_version_id)
                VALUES(?,?,2,'"错误"','restore','','t',?)''', (p['id'], one['object_id'], other['id']))


def test_audit_failure_rolls_back_object_and_version(production_store, monkeypatch):
    p, svc = setup(production_store)

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError('injected audit error')

    monkeypatch.setattr(production_store, 'insert_action', fail)
    with pytest.raises(sqlite3.OperationalError):
        svc.create(p['id'], 'script', '不会保存')
    assert all(obj['content_type'] == 'research' for obj in production_store.objects(p['id']))


def test_version_cannot_reference_another_projects_object(production_store):
    from services.production.project_service import ProjectService
    p, svc = setup(production_store)
    other = ProjectService(production_store).create(2, '其他任务')
    version = svc.create(p['id'], 'script', '正文')
    with production_store._connection() as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('''INSERT INTO production_versions(project_id,object_id,version_number,content_json,source,note,created_at)
                VALUES(?,?,2,'"越界"','manual','','t')''', (other['id'], version['object_id']))


def test_restore_audit_failure_preserves_all_previous_versions(production_store, monkeypatch):
    p, svc = setup(production_store)
    original = svc.create(p['id'], 'script', '原稿')
    before = svc.history(p['id'], 'script')

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError('injected restore audit error')

    monkeypatch.setattr(production_store, 'insert_action', fail)
    with pytest.raises(sqlite3.OperationalError):
        svc.restore(p['id'], original['id'], object_id=original['object_id'])
    assert svc.history(p['id'], 'script') == before
