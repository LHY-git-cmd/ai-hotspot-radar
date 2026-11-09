"""可替换 Provider 的结果、用量、错误与协议。"""

from dataclasses import dataclass, field
from typing import Protocol


def token_count(value: object) -> int | None:
    """服务商缺失或无效计量保留未知，不能补成零。"""
    return value if type(value) is int and value >= 0 else None


@dataclass(frozen=True)
class Usage:
    """保存服务商实际返回的计量；缓存细分可缺失。"""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_hit_tokens: int | None = None
    cache_miss_tokens: int | None = None

    @classmethod
    def from_payload(cls, payload: object) -> 'Usage':
        """只接受明确的整数 usage，后续价格计算再校验缓存总数。"""
        values = payload if isinstance(payload, dict) else {}
        return cls(*(token_count(values.get(key)) for key in (
            'prompt_tokens', 'completion_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')))


@dataclass(frozen=True)
class ProviderReply:
    """标准化输出，不把原始 HTTP 响应或鉴权头交给页面。"""

    document: dict
    usage: Usage = field(default_factory=Usage)
    response_model: str | None = None


class AIError(Exception):
    """可展示的固定错误信息，记录费用信息但不携带远程异常正文。"""

    def __init__(self, kind: str, message: str, *, retryable: bool = False,
                 usage: Usage | None = None, retry_after: float | None = None, diagnostic=None):
        """重试由预算编排层控制，Provider 内不得隐式重试。"""
        super().__init__(message)
        self.kind, self.retryable = kind, retryable
        self.usage, self.retry_after = usage or Usage(), retry_after
        self.diagnostic = diagnostic


class Provider(Protocol):
    """一次 complete 对应一次可计量的 HTTP 尝试。"""

    name: str

    def complete(self, messages: list[dict]) -> ProviderReply:
        """输出结构化文档或带实际可得 usage 的 AIError。"""
        ...
