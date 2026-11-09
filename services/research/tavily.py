"""Tavily REST 适配器；一次方法调用只发送一次请求，不自动重试。"""

from dataclasses import dataclass, field
from urllib.parse import urlsplit
from ipaddress import ip_address

import requests

from services.research.base import (SearchReply, SearchResult, ExtractReply, ExtractResult,
                                     Quota, SearchError, credit_value)


def public_url(url):
    """只提取服务商返回的公开 HTTP(S) 地址，不向本地或私网地址请求内容。"""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        if parsed.scheme not in ('http', 'https') or not host or parsed.username or parsed.password:
            return False
        if host.lower() in ('localhost',) or host.endswith(('.localhost', '.local')):
            return False
        try:
            return ip_address(host).is_global
        except ValueError:
            return '.' in host
    except (ValueError, TypeError):
        return False


@dataclass
class TavilyProvider:
    api_key: str = field(repr=False)
    name: str = field(default='tavily', init=False)

    @property
    def available(self):
        return bool(self.api_key.strip())

    def _request(self, operation, body=None):
        if not self.available:
            raise SearchError('configuration', '未配置 TAVILY_API_KEY；历史查看及原有功能仍可使用。')
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
        try:
            if operation == 'usage':
                response = requests.get('https://api.tavily.com/usage', headers=headers, timeout=(15, 30), allow_redirects=False)
            else:
                response = requests.post('https://api.tavily.com/' + operation, headers=headers,
                    json=body, timeout=(15, 65), allow_redirects=False)
        except requests.RequestException:
            raise SearchError('network', '搜索服务网络失败，实际 credits 未知；不会自动重试。') from None
        try:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            credits = credit_value(payload.get('usage', {}).get('credits')) if isinstance(payload, dict) and isinstance(payload.get('usage', {}), dict) else None
            if response.status_code != 200:
                raise SearchError('http_' + str(response.status_code),
                    f'搜索服务返回 HTTP {response.status_code}；请核对密钥、额度或访问限制。', credits=credits)
            if not isinstance(payload, dict):
                raise SearchError('invalid_response', '搜索服务返回无效 JSON，实际用量未知。')
            return payload, credits
        finally:
            response.close()

    def search(self, query, *, start_date='', end_date='', domains=None, max_results=3):
        body = {'query': query, 'search_depth': 'basic', 'auto_parameters': False,
            'include_answer': False, 'include_raw_content': False, 'include_usage': True,
            'include_published_date': True, 'max_results': max_results}
        if start_date: body['start_date'] = start_date
        if end_date: body['end_date'] = end_date
        if domains:
            body['include_domains'] = domains
            body['include_domains_mode'] = 'restrict'
        data, credits = self._request('search', body)
        if not isinstance(data.get('results'), list):
            raise SearchError('invalid_response', '搜索结果结构无效。', credits=credits)
        results = []
        for row in data['results'][:max_results]:
            if not isinstance(row, dict) or not public_url(row.get('url')):
                continue
            if not all(isinstance(row.get(key), str) for key in ('title', 'content')):
                continue
            date = row.get('published_date')
            results.append(SearchResult(row['title'], row['url'], row['content'], date if isinstance(date, str) else None))
        return SearchReply(results, credits, data.get('request_id'))

    def extract(self, urls):
        if not urls or len(urls) > 20 or not all(public_url(url) for url in urls):
            raise SearchError('parameters', '仅允许一次提取 1–20 个公开 HTTP(S) 来源。')
        data, credits = self._request('extract', {'urls': urls, 'extract_depth': 'basic',
            'format': 'text', 'include_images': False, 'include_usage': True, 'timeout': 30})
        if not isinstance(data.get('results'), list) or not isinstance(data.get('failed_results', []), list):
            raise SearchError('invalid_response', '正文提取结构无效。', credits=credits)
        mapped = {}
        for row in data['results']:
            if isinstance(row, dict) and row.get('url') in urls and isinstance(row.get('raw_content'), str) and row['raw_content'].strip():
                mapped[row['url']] = ExtractResult(row['url'], row['raw_content'])
        for url in urls:
            if url not in mapped:
                mapped[url] = ExtractResult(url, '', 'failed', '提取失败或返回空文本；未绕过访问限制')
        return ExtractReply(list(mapped.values()), credits, data.get('request_id'))

    def usage(self):
        data, _ = self._request('usage')
        balances = []
        key = data.get('key', {})
        account = data.get('account', {})
        for values, used_key, limit_key in ((key, 'usage', 'limit'), (account, 'plan_usage', 'plan_limit')):
            if not isinstance(values, dict): continue
            used, limit = credit_value(values.get(used_key)), credit_value(values.get(limit_key))
            if used is not None and limit is not None:
                balances.append(max(0, limit-used))
        # 不主动启用 pay-as-you-go；未知账户字段不会推断为免费额度。
        return Quota(min(balances) if balances else None)
