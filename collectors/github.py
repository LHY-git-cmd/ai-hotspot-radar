"""从 GitHub 官方仓库搜索 API 采集近期活跃的 AI 主题项目。"""

from datetime import datetime, timedelta, timezone

from collectors.http import CollectionError, get_json
from models import CollectionResult, Hotspot, as_score, as_utc_iso
from services.normalization import normalize_url, plain_text

API_URL = 'https://api.github.com/search/repositories'


def collect(token: str = '', *, now: datetime | None = None) -> CollectionResult:
    """取最近 7 天活跃仓库的前 30 条，Stars 仅代表累计收藏数。"""
    supplied_now = now
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=7)).date().isoformat()
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    payload = get_json(API_URL, source='GitHub', headers=headers, params={
        'q': f'topic:artificial-intelligence pushed:>={since} archived:false',
        'sort': 'stars', 'order': 'desc', 'per_page': 30,
    })
    if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
        raise CollectionError('GitHub 返回的数据格式异常：缺少仓库列表。')
    observed_at = supplied_now or datetime.now(timezone.utc)
    result = CollectionResult()
    if payload.get('incomplete_results'):
        result.warnings.append('GitHub 搜索结果不完整，当前仅保存 API 返回的可用记录。')
    invalid = 0
    for item in payload['items']:
        if not isinstance(item, dict):
            invalid += 1
            continue
        title = plain_text(item.get('full_name') or item.get('name'))
        try:
            normalize_url(item.get('html_url'))
            if not title:
                raise ValueError('缺少仓库名称')
        except ValueError:
            invalid += 1
            continue
        result.items.append(Hotspot(
            title=title, url=item['html_url'], source='GitHub',
            summary=plain_text(item.get('description')) or None,
            published_at=as_utc_iso(item.get('created_at')),
            collected_at=observed_at.astimezone(timezone.utc).isoformat(timespec='seconds'),
            score=as_score(item.get('stargazers_count')), category='AI 开源项目',
            source_key=str(item['id']) if type(item.get('id')) is int and item['id'] > 0 else None,
            forks=as_score(item.get('forks_count')), pushed_at=as_utc_iso(item.get('pushed_at')),
        ))
    if invalid:
        result.warnings.append(f'GitHub 有 {invalid} 条记录缺少有效标题或链接，已跳过。')
    if any(item.source_key is None for item in result.items):
        result.warnings.append('GitHub 部分记录缺少稳定仓库 ID，可保留内容，但不建立这些记录的趋势快照。')
    if payload['items'] and not result.items:
        raise CollectionError('GitHub 返回的仓库均缺少有效标题或链接，无法保存。')
    return result
