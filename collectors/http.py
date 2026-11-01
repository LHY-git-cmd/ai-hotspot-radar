"""统一公开 API 的超时、限流及响应错误处理。"""

import requests

USER_AGENT = 'ai-hotspot-radar/0.1 (personal public API reader)'


class CollectionError(Exception):
    """可安全展示给用户的采集错误，不包含 Token 或远程响应正文。"""


def get_json(url: str, *, source: str, headers: dict | None = None,
             params: dict | None = None) -> object:
    """请求单个 JSON 资源；不自动重试限流，不泄漏底层请求中的凭据。"""
    try:
        response = requests.get(
            url, params=params, headers={'User-Agent': USER_AGENT, **(headers or {})},
            # 为较慢的连接及代理握手留出余量；连接与单次读取仍各限 15 秒。
            timeout=(15, 15),
        )
    except requests.Timeout:
        raise CollectionError(f'{source} 请求超时，请稍后重试或检查网络。') from None
    except requests.RequestException:
        raise CollectionError(f'{source} 网络连接失败，请检查网络、代理或证书配置。') from None
    try:
        status = response.status_code
        if status == 401:
            raise CollectionError(f'{source} 认证失败，请检查 .env 中的 GITHUB_TOKEN，或移除无效 Token。')
        if status in (403, 429):
            wait = response.headers.get('Retry-After', '')
            suggestion = f'至少等待 {wait} 秒后重试。' if wait.isdecimal() else '请稍后重试并检查 API 配额。'
            raise CollectionError(f'{source} 访问被拒绝或触发限流（HTTP {status}），{suggestion}')
        if not 200 <= status < 300:
            raise CollectionError(f'{source} API 返回 HTTP {status}，请稍后重试。')
        try:
            return response.json()
        except ValueError:
            raise CollectionError(f'{source} 响应不是有效 JSON，可能是网络代理或 API 暂时异常。') from None
    finally:
        response.close()
