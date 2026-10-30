"""模拟官方 HTTP 响应，验证字段映射和失败提示；不访问网络。"""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)


def response(payload, status=200, headers=None):
    """构造 requests 风格响应，便于断言请求和异常处理。"""
    result = Mock(status_code=status, headers=headers or {})
    result.json.return_value = payload
    return result


def test_github_maps_real_fields_and_request(monkeypatch):
    """Stars 映射为来源指标，创建时间不能伪装成最近活跃时间。"""
    from collectors.github import collect
    get = Mock(return_value=response({'items': [
        {'full_name': 'owner/AI', 'html_url': 'https://github.com/owner/AI',
         'description': 'An AI tool', 'created_at': '2025-12-01T01:02:03Z',
         'stargazers_count': 42},
        {'full_name': 'owner/unknown', 'html_url': 'https://github.com/owner/unknown'},
        {'full_name': 'bad', 'html_url': 'javascript:bad()'},
    ], 'incomplete_results': False}))
    monkeypatch.setattr('collectors.http.requests.get', get)
    result = collect(token='test-only-token', now=NOW)
    assert len(result.items) == 2
    assert result.items[0].score == 42
    assert result.items[0].published_at == '2025-12-01T01:02:03+00:00'
    assert result.items[1].score is None and result.items[1].published_at is None
    assert result.warnings
    kwargs = get.call_args.kwargs
    assert 'pushed:>=2026-01-03' in kwargs['params']['q']
    assert kwargs['headers']['Authorization'] == 'Bearer test-only-token'
    assert kwargs['timeout'] == (5, 15)


@pytest.mark.parametrize(('status', 'message'), [(401, '认证'), (403, '限流'),
                                                (429, '限流'), (503, '503')])
def test_http_errors_are_clear_and_do_not_expose_token(monkeypatch, status, message):
    """限流和认证错误包含操作建议，响应正文和 Token 不出现在错误中。"""
    from collectors.github import collect
    from collectors.http import CollectionError
    monkeypatch.setattr('collectors.http.requests.get', Mock(return_value=response(
        {'message': 'test-only-secret'}, status, {'Retry-After': '60'})))
    with pytest.raises(CollectionError, match=message) as error:
        collect(token='test-only-secret', now=NOW)
    assert 'test-only-secret' not in str(error.value)


@pytest.mark.parametrize('failure', [requests.Timeout('secret'),
                                     requests.ConnectionError('secret'), ValueError('secret')])
def test_network_and_json_errors(monkeypatch, failure):
    """超时、连接错误和无效 JSON 转换成可展示的中文异常。"""
    from collectors.github import collect
    from collectors.http import CollectionError
    fake = response({})
    if isinstance(failure, ValueError):
        fake.json.side_effect = failure
        get = Mock(return_value=fake)
    else:
        get = Mock(side_effect=failure)
    monkeypatch.setattr('collectors.http.requests.get', get)
    with pytest.raises(CollectionError) as error:
        collect(now=NOW)
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('payload', [[], {}, {'items': None}, {'items': 'invalid'}])
def test_github_rejects_invalid_envelope(monkeypatch, payload):
    """响应结构变更时不能当成成功且没有数据。"""
    from collectors.github import collect
    from collectors.http import CollectionError
    monkeypatch.setattr('collectors.http.requests.get', Mock(return_value=response(payload)))
    with pytest.raises(CollectionError, match='格式'):
        collect(now=NOW)


def test_hn_filters_sample_handles_missing_and_partial_failure(monkeypatch):
    """样本限制、关键词边界、旧帖过滤、讨论回退链接及单帖容错。"""
    from collectors.hacker_news import collect
    from collectors.http import CollectionError
    stamp = int(NOW.timestamp())
    payloads = {
        'topstories': [1, 2, 3, 4, 5, 6, 7, 8],
        '1': {'id': 1, 'type': 'story', 'title': 'AI &amp; LLM tool', 'time': stamp, 'score': 8},
        '2': {'id': 2, 'type': 'story', 'title': 'Email and railway', 'time': stamp},
        '3': {'id': 3, 'type': 'story', 'title': 'AI old', 'time': stamp - 9 * 86400},
        '4': {'id': 4, 'type': 'story', 'title': 'Claude', 'time': stamp, 'dead': True},
        '5': {'id': 5, 'type': 'story', 'title': 'LLM discussion', 'text': '<p>Open models</p>'},
        '6': None,
    }

    def fake_json(url, **kwargs):
        """按官方路径返回固定测试数据，并让一条详情请求失败。"""
        key = url.rsplit('/', 1)[-1].removesuffix('.json')
        if key == '7':
            raise CollectionError('请求超时')
        assert key != '8', '超出样本上限的帖子不应请求'
        return payloads[key]

    monkeypatch.setattr('collectors.hacker_news.get_json', fake_json)
    result = collect(now=NOW, sample_size=7)
    assert [item.title for item in result.items] == ['AI & LLM tool', 'LLM discussion']
    assert result.items[0].url == 'https://news.ycombinator.com/item?id=1'
    assert result.items[0].score == 8
    assert result.items[1].published_at is None and result.items[1].score is None
    assert result.items[1].summary == 'Open models'
    assert result.warnings


def test_hn_total_detail_failure_is_not_empty_success(monkeypatch):
    """列表可访问而全部详情失败时，必须明确报告数据源失败。"""
    from collectors.hacker_news import collect
    from collectors.http import CollectionError

    def fail_details(url, **kwargs):
        """仅返回列表，使所有详情请求失败。"""
        if 'topstories' in url:
            return [1, 2]
        raise CollectionError('请求超时')

    monkeypatch.setattr('collectors.hacker_news.get_json', fail_details)
    with pytest.raises(CollectionError, match='详情'):
        collect(now=NOW)
