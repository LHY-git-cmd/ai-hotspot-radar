"""仅供自动化测试注入的 Provider，不提供生产页面中的虚构分析。"""

from copy import deepcopy

from services.ai.base import ProviderReply


class MockProvider:
    """使用显式给定的响应/错误序列，可检查调用次数和输入边界。"""

    name = 'mock'

    def __init__(self, replies: list[ProviderReply | Exception]):
        """没有默认伪造内容；测试必须明确提供所需材料。"""
        self.replies, self.calls = list(replies), []

    def complete(self, messages: list[dict]) -> ProviderReply:
        """记录一次尝试，再返回测试响应或抛出明确的模拟错误。"""
        self.calls.append(deepcopy(messages))
        if not self.replies:
            raise AssertionError('Mock Provider 响应已耗尽，可能发生重复调用')
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return deepcopy(reply)
