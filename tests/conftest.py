"""AI 测试的明确模拟材料；只用于临时库，不写入生产数据。"""

import pytest


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch, tmp_path):
    """测试只读显式假配置；禁止 dotenv、真实 HTTP 和生产数据目录连接。"""
    import dotenv
    import sqlite3
    from pathlib import Path
    import config
    import services.ai.config as ai_config

    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *a, **k: False)
    monkeypatch.setattr(config, 'load_dotenv', lambda *a, **k: False)
    monkeypatch.setattr(ai_config, 'load_dotenv', lambda *a, **k: False)
    import os
    for name in tuple(os.environ):
        if name.startswith(('AI_', 'DEEPSEEK_', 'TAVILY_')) or name == 'GITHUB_TOKEN':
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('AI_RADAR_DB_PATH', str(tmp_path / 'isolated-default.sqlite3'))

    def no_network(*args, **kwargs):
        raise AssertionError('测试禁止真实网络，请使用 Mock Provider')

    monkeypatch.setattr('requests.sessions.Session.request', no_network)
    original_connect = sqlite3.connect
    production_dir = (Path(__file__).resolve().parents[1] / 'data').resolve()

    def temporary_database(database, *args, **kwargs):
        value = str(database)
        from urllib.parse import unquote, urlsplit
        path = unquote(urlsplit(value).path).lstrip('/') if value.startswith('file:') else value
        if production_dir == Path(path).resolve() or production_dir in Path(path).resolve().parents:
            raise AssertionError('测试禁止连接生产数据库')
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', temporary_database)


@pytest.fixture
def ai_document():
    """提供一个符合三角度 Schema 的测试文档，不声称来自真实模型。"""
    return {
        'summary': '测试用工具说明，能力尚待核实。', 'what_happened': '材料介绍一个项目。',
        'why_now': '需要结合真实指标核实关注原因。', 'target_audience': 'AI 编程初学者',
        'audience_value': '帮助观众规划核验步骤。', 'video_suitability': True,
        'suitability_reason': '有可规划的演示方向，尚未亲测。',
        'evidence_gaps': ['需要实际安装验证'], 'factual_risks': ['宣传描述未经独立验证'],
        'video_ideas': [
            {'angle_type': kind, 'title': f'测试选题：{kind}',
             'alternative_titles': [f'{kind}备用一', f'{kind}备用二'],
             'target_audience': 'AI 工具使用者', 'hook': f'{kind}：先看需要核实的问题。',
             'outline': [{'seconds': 5, 'content': '介绍问题'},
                         {'seconds': 55, 'content': f'计划进行{kind}，未实际执行'},
                         {'seconds': 15, 'content': '总结适用边界'}],
             'materials': ['项目链接与本地测试环境'], 'verification_checklist': ['确认安装及许可'],
             'difficulty': '中', 'recommendation_reason': f'{kind}视角提供独立制作方式',
             'risks': ['需要核实功能，不能声称已完成测试']}
            for kind in ('实测型', '教程型', '对比型')],
    }


@pytest.fixture
def production_store(tmp_path, ai_document):
    """准备真实第三期结构的临时库；只写模拟分析，不调用 Provider。"""
    from database.ai_store import AIStore
    from database.production_store import ProductionStore
    from models import Hotspot
    from services.ai.base import Usage
    from services.ai.config import AISettings

    path = tmp_path / 'production.sqlite3'
    ai = AIStore(path, AISettings())
    ai.save([Hotspot(title='测试热点', url='https://example.com/production',
                    source='GitHub', category='AI', collected_at='2026-11-01T00:00:00+00:00')])
    analysis = ai.claim_analysis(1, 'fixture', 'fixture', {}, 'test', False)
    run_id = ai.reserve_attempt(analysis['id'], 1, 1, {})
    ai.finish_attempt(run_id, 'success', Usage(1, 1), 1, None)
    ai.complete_analysis(analysis['id'], run_id, ai_document, '仅测试材料')
    return ProductionStore(path)
