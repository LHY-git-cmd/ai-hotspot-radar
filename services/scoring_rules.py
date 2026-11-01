"""第二期启发式规则集中配置；调整后点击重新计算评分即可生效。"""

RULE_VERSION = 'heuristic-v1'

# 锚点是规则选择，不是经过实证校准的行业分位数或流量预测。
HEAT_WEIGHTS = {'current': .35, 'growth': .40, 'recency': .25}
VIDEO_WEIGHTS = {'practical': .30, 'demo': .25, 'novelty': .20, 'topic': .25}
CURRENT_ANCHORS = {'GitHub': 100000, 'Hacker News': 1000}
GROWTH_ANCHORS = {'GitHub': 1000, 'Hacker News': 100}
WINDOW_DAYS = 7
MIN_INTERVAL_HOURS = 1
TARGET_INTERVAL_HOURS = 24
STALE_HOURS = 48
RECENCY_HALF_LIFE_DAYS = 7
NOVELTY_HALF_LIFE_DAYS = 30
COMPOSITE_HEAT_WEIGHT = .5

AI_WORDS = ('ai', 'llm', 'llms', 'gpt', 'chatgpt', 'openai', 'claude', 'gemini',
            'qwen', 'deepseek', 'ollama', 'llama', 'artificial intelligence', '人工智能', '大模型')
CODING_WORDS = ('coding', 'code', 'programming', 'developer', 'copilot', 'cursor', '编程', '开发', '代码')
TOOL_WORDS = ('tool', 'tools', 'app', 'application', 'cli', 'api', 'editor', 'plugin', '工具', '应用', '插件')
PRACTICAL_GROUPS = (
    CODING_WORDS,
    ('automation', 'productivity', 'workflow', 'assistant', '自动化', '效率', '工作流', '助手'),
    ('video', 'image', 'audio', 'data', 'analysis', '创作', '视频', '图片', '数据', '分析'),
)
DEMO_GROUPS = (
    (35, ('demo', 'playground', '演示')),
    (25, ('cli', 'api', 'editor', 'ui', '命令行', '界面')),
    (20, ('quickstart', 'tutorial', 'example', 'examples', '示例', '教程')),
)


def rule_parameters() -> dict:
    """把全部关键参数和词表写入评分明细，方便解释及规则版本追踪。"""
    return {
        'heat_weights': HEAT_WEIGHTS.copy(), 'video_weights': VIDEO_WEIGHTS.copy(),
        'current_anchors': CURRENT_ANCHORS.copy(), 'growth_anchors': GROWTH_ANCHORS.copy(),
        'window_days': WINDOW_DAYS, 'min_interval_hours': MIN_INTERVAL_HOURS,
        'target_interval_hours': TARGET_INTERVAL_HOURS, 'stale_hours': STALE_HOURS,
        'recency_half_life_days': RECENCY_HALF_LIFE_DAYS,
        'novelty_half_life_days': NOVELTY_HALF_LIFE_DAYS,
        'composite_heat_weight': COMPOSITE_HEAT_WEIGHT,
        'ai_words': AI_WORDS, 'coding_words': CODING_WORDS, 'tool_words': TOOL_WORDS,
        'practical_groups': PRACTICAL_GROUPS, 'demo_groups': DEMO_GROUPS,
    }
