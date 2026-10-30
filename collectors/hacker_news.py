"""从 Hacker News 官方 API 的有限热门样本中发现 AI 相关讨论。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import re

from collectors.http import CollectionError, get_json
from models import CollectionResult, Hotspot, as_score, as_utc_iso
from services.normalization import normalize_url, plain_text

BASE_URL = 'https://hacker-news.firebaseio.com/v0'
# 英文缩写使用单词边界，避免把 railway、email 等普通词误判为 AI。
AI_TERMS = re.compile(
    r'\b(?:ai|llms?|gpt(?:-?\d[\w.-]*)?|chatgpt|openai|anthropic|claude|gemini|'
    r'deepseek|qwen|llama|mistral|ollama|diffusers|comfyui|midjourney)\b'
    r'|\b(?:artificial intelligence|machine learning|deep learning|neural network|'
    r'generative ai|stable diffusion|hugging face|language models?)\b|人工智能|大模型',
    re.IGNORECASE,
)


def _fetch_item(item_id: int) -> tuple[object, str | None]:
    """将单条请求错误作为结果返回，保留其他帖子处理机会。"""
    try:
        return get_json(f'{BASE_URL}/item/{item_id}.json', source='Hacker News'), None
    except CollectionError as error:
        return None, str(error)


def collect(*, now: datetime | None = None, sample_size: int = 60) -> CollectionResult:
    """最多读取 60 条热门帖详情，用 6 个并发请求控制刷新等待时间。"""
    if not 1 <= sample_size <= 60:
        raise ValueError('Hacker News 样本数量应在 1 到 60 之间')
    now = now or datetime.now(timezone.utc)
    ids = get_json(f'{BASE_URL}/topstories.json', source='Hacker News')
    if not isinstance(ids, list) or any(type(item) is not int or item <= 0 for item in ids):
        raise CollectionError('Hacker News 返回的数据格式异常：热门列表无效。')
    result = CollectionResult()
    if not ids:
        return result
    errors, invalid, unknown_time = [], 0, 0
    # executor.map 保留热门列表顺序，避免并发完成顺序影响首次去重保留对象。
    with ThreadPoolExecutor(max_workers=6) as executor:
        details = list(executor.map(_fetch_item, ids[:sample_size]))
    for payload, error in details:
        if error:
            errors.append(error)
            continue
        if not isinstance(payload, dict):
            invalid += 1
            continue
        if payload.get('deleted') or payload.get('dead') or payload.get('type') != 'story':
            continue
        title, text = plain_text(payload.get('title')), plain_text(payload.get('text'))
        if not title or not AI_TERMS.search(f'{title} {text}'):
            continue
        published = as_utc_iso(payload.get('time'))
        if published:
            date = datetime.fromisoformat(published)
            if date < now - timedelta(days=7) or date > now + timedelta(minutes=5):
                continue
        else:
            unknown_time += 1
        item_id = payload.get('id')
        if type(item_id) is not int or item_id <= 0:
            invalid += 1
            continue
        # 自问自答类帖子没有外链时，提供真实的 HN 原讨论链接。
        url = payload.get('url') or f'https://news.ycombinator.com/item?id={item_id}'
        try:
            normalize_url(url)
        except ValueError:
            invalid += 1
            continue
        result.items.append(Hotspot(
            title=title, url=url, source='Hacker News', summary=text or None,
            published_at=published, collected_at=now.astimezone(timezone.utc).isoformat(timespec='seconds'),
            score=as_score(payload.get('score')), category='AI 讨论',
        ))
    if len(errors) == len(details):
        raise CollectionError(f'Hacker News 热门帖详情全部请求失败：{errors[0]}')
    if errors:
        result.warnings.append(f'Hacker News 有 {len(errors)} 条详情请求失败；{errors[0]} 其他记录已继续处理。')
    if invalid:
        result.warnings.append(f'Hacker News 有 {invalid} 条详情为空或字段无效，已跳过。')
    if unknown_time:
        result.warnings.append(f'Hacker News 有 {unknown_time} 条 AI 帖子缺少有效时间，保留为空，无法确认是否在最近 7 天内。')
    return result
