"""AI 测试的明确模拟材料；只用于临时库，不写入生产数据。"""

import pytest


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
