"""预览与执行共用的确定性 query 构造，不调用模型或搜索服务。"""

QUERY_BUILDER_VERSION = 'keywords-v2'
MAX_QUERY_CHARACTERS = 400


def build_query(question):
    override = question.get('query_override', '')
    if not isinstance(override, str):
        raise ValueError('自定义 query 必须是文本')
    if override.strip():
        query = override.strip()
    else:
        words, seen = [], set()
        for value in question['keywords']:
            word = ' '.join(value.split())
            if word and word.casefold() not in seen:
                words.append(word)
                seen.add(word.casefold())
        query = ' '.join(words)
    if not query or len(query) > MAX_QUERY_CHARACTERS or any(ord(c) < 32 for c in query):
        raise ValueError('最终 query 须为 1–400 字符的单行文本，请修改关键词或自定义 query')
    return query
