"""DeepSeek 官方非流式客户端；一次调用只进行一次 HTTP 请求。"""

import json

import requests

from services.ai.base import AIError, ProviderReply, Usage
from services.ai.config import AISettings
from services.ai.schemas import provider_schema

TOOL_NAME = 'submit_topic_analysis'


def request_body(settings: AISettings, messages: list[dict]) -> dict:
    """仅注册一个结果提交工具，不向模型暴露执行、网络或文件工具。"""
    body = {'model': settings.model, 'messages': messages, 'stream': False,
            'thinking': {'type': 'disabled'}, 'max_tokens': settings.max_output_tokens}
    if settings.output_mode == 'strict':
        body['tools'] = [{'type': 'function', 'function': {'name': TOOL_NAME,
            'description': '提交完整的热点解读与恰好三个不同的视频角度',
            'strict': True, 'parameters': provider_schema()}}]
        body['tool_choice'] = {'type': 'function', 'function': {'name': TOOL_NAME}}
    else:
        body['response_format'] = {'type': 'json_object'}
    return body


class DeepSeekProvider:
    """可替换 Provider 实现；价格/预算及重试由上层负责。"""

    name = 'deepseek'

    def __init__(self, settings: AISettings):
        """冻结该请求的模型配置，不记录密钥。"""
        self.settings = settings

    def complete(self, messages: list[dict]) -> ProviderReply:
        """保存可得 usage，即使内容截断、JSON 错误或返回 HTTP 错误。"""
        self.settings.validate()
        if not self.settings.api_key:
            raise AIError('configuration', '未配置 DEEPSEEK_API_KEY，原有功能和 AI 历史仍可使用。')
        body = request_body(self.settings, messages)
        if len(json.dumps(body, ensure_ascii=False).encode('utf-8')) > self.settings.max_request_bytes:
            raise AIError('input_limit', '分析材料超过输入限制，请缩短材料或调整配置。')
        endpoint = 'https://api.deepseek.com/' + ('beta/' if self.settings.output_mode == 'strict' else '')
        try:
            response = requests.post(endpoint + 'chat/completions', json=body,
                headers={'Authorization': f'Bearer {self.settings.api_key}', 'Content-Type': 'application/json'},
                timeout=(15, 120), allow_redirects=False)
        except requests.ConnectTimeout:
            raise AIError('connect_timeout', 'AI 连接超时；重试仍受预算与次数限制。', retryable=True) from None
        except requests.ReadTimeout:
            raise AIError('read_timeout', 'AI 读取超时，是否计费未知，已保留预算预占。') from None
        except requests.RequestException:
            raise AIError('network', 'AI 网络请求失败，发送状态可能不明，已保留预算预占。') from None
        try:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            usage = Usage.from_payload(payload.get('usage') if isinstance(payload, dict) else None)
            if response.status_code != 200:
                errors = {400: ('parameters', 'AI 参数或结构输出能力不支持，请检查配置。', False),
                          401: ('authentication', 'AI 密钥认证失败，请检查配置。', False),
                          402: ('balance', 'AI 服务商余额不足，请在服务商平台核对。', False),
                          403: ('permission', 'AI 模型或账户权限不足。', False),
                          422: ('parameters', 'AI 参数不被接受，请检查模型能力与配置。', False),
                          429: ('rate_limit', 'AI 服务限流，将按有限次数和预算重试。', True),
                          500: ('unavailable', 'AI 服务异常，请稍后重试。', True),
                          503: ('unavailable', 'AI 服务暂时不可用。', True)}
                kind, message, retryable = errors.get(response.status_code,
                    ('http_error', f'AI 接口返回 HTTP {response.status_code}。', False))
                wait = response.headers.get('Retry-After', '')
                raise AIError(kind, message, retryable=retryable, usage=usage,
                              retry_after=min(float(wait), 30) if wait.isdecimal() else None)
            try:
                choice = payload['choices'][0]
                if choice['finish_reason'] == 'length':
                    raise AIError('truncated', 'AI 输出被截断，未保存成功分析；已有 Token 仍计入估算。', usage=usage)
                if self.settings.output_mode == 'strict':
                    calls = choice['message']['tool_calls']
                    if len(calls) != 1 or calls[0]['function']['name'] != TOOL_NAME:
                        raise ValueError('无效工具结果')
                    content = calls[0]['function']['arguments']
                else:
                    content = choice['message']['content']
                document = json.loads(content)
                if not isinstance(document, dict):
                    raise ValueError('不是 JSON 对象')
                return ProviderReply(document, usage, payload.get('model'))
            except (KeyError, IndexError, TypeError, ValueError):
                raise AIError('invalid_response', 'AI 返回空内容或无效 JSON，未保存成功分析。', usage=usage) from None
        finally:
            response.close()
