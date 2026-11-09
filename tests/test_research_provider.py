"""Tavily 适配与 DeepSeek 可选 Schema，无真实 API。"""

import json
from unittest.mock import Mock

import pytest
import requests


def response(payload, status=200):
    value = Mock(status_code=status, headers={})
    value.json.return_value = payload
    return value


def test_custom_deepseek_schema_and_exact_request_reservation(monkeypatch):
    from services.ai.config import AISettings
    from services.ai.deepseek_client import DeepSeekProvider, request_body
    from services.ai.cost_tracker import reservation_units
    schema = {'type': 'object', 'properties': {'goal': {'type': 'string'}}, 'required': ['goal'], 'additionalProperties': False}
    settings = AISettings(api_key='test-only')
    post = Mock(return_value=response({'choices': [{'finish_reason': 'tool_calls', 'message': {
        'tool_calls': [{'function': {'name': 'submit_research_plan', 'arguments': '{"goal":"测试"}'}}]}}], 'usage': {}}))
    monkeypatch.setattr('requests.post', post)
    provider = DeepSeekProvider(settings, schema=schema, tool_name='submit_research_plan')
    assert provider.complete([]).document == {'goal': '测试'}
    body = request_body(settings, [], schema=schema, tool_name='submit_research_plan')
    assert post.call_args.kwargs['json'] == body
    assert reservation_units([], settings, body=body) > 0


def test_tavily_search_extract_usage_and_secret_hiding(monkeypatch):
    from services.research.tavily import TavilyProvider
    post = Mock(side_effect=[response({'results': [{'title': '官方', 'url': 'https://example.com/doc',
        'content': '搜索摘录', 'published_date': '2026-11-01'}], 'usage': {'credits': 1}, 'request_id': 's'}),
        response({'results': [{'url': 'https://example.com/doc', 'raw_content': '正文'}],
          'failed_results': [{'url': 'https://example.com/no', 'error': 'blocked'}], 'usage': {'credits': 0}})])
    monkeypatch.setattr('requests.post', post)
    monkeypatch.setattr('requests.get', Mock(return_value=response({'key': {'usage': 3, 'limit': 10},
        'account': {'plan_usage': 10, 'plan_limit': 100, 'paygo_limit': 0, 'paygo_usage': 0}})))
    provider = TavilyProvider('test-secret')
    found = provider.search('测试', start_date='', end_date='', domains=[], max_results=3)
    assert found.credits == 1 and found.results[0].snippet == '搜索摘录'
    extracted = provider.extract(['https://example.com/doc', 'https://example.com/no'])
    assert extracted.credits == 0 and extracted.results[1].status == 'failed'
    assert provider.usage().remaining == 7
    assert post.call_args_list[0].kwargs['json']['include_usage'] is True
    assert post.call_args_list[0].kwargs['json']['auto_parameters'] is False
    assert 'test-secret' not in repr(provider)


@pytest.mark.parametrize('status', [401, 429, 432, 500])
def test_tavily_http_failures_never_leak_body_or_retry(monkeypatch, status):
    from services.research.tavily import TavilyProvider
    from services.research.base import SearchError
    post = Mock(return_value=response({'detail': 'test-secret'}, status))
    monkeypatch.setattr('requests.post', post)
    with pytest.raises(SearchError) as error:
        TavilyProvider('test-secret').search('测试', start_date='', end_date='', domains=[], max_results=3)
    assert 'test-secret' not in str(error.value)
    post.assert_called_once()


def test_missing_key_and_timeout_have_no_fabricated_usage(monkeypatch):
    from services.research.tavily import TavilyProvider
    from services.research.base import SearchError
    post = Mock(side_effect=requests.ReadTimeout('secret'))
    monkeypatch.setattr('requests.post', post)
    with pytest.raises(SearchError): TavilyProvider('').search('x')
    post.assert_not_called()
    with pytest.raises(SearchError) as error: TavilyProvider('test').search('x')
    assert error.value.credits is None
    post.assert_called_once()


@pytest.mark.parametrize('url', ['http://127.0.0.1/admin', 'http://192.168.1.1', 'http://localhost/',
    'file:///private', 'javascript:alert(1)', 'https://user:secret@example.com'])
def test_extract_rejects_nonpublic_or_credential_urls_without_network(monkeypatch, url):
    from services.research.tavily import TavilyProvider
    from services.research.base import SearchError
    post=Mock()
    monkeypatch.setattr('requests.post',post)
    with pytest.raises(SearchError): TavilyProvider('test').extract([url])
    post.assert_not_called()


def test_missing_usage_and_empty_extraction_are_not_success(monkeypatch):
    from services.research.tavily import TavilyProvider
    monkeypatch.setattr('requests.post',Mock(return_value=response({'results':[], 'failed_results':[]})))
    result=TavilyProvider('test').extract(['https://example.com/unavailable'])
    assert result.credits is None and result.results[0].status=='failed'
    assert result.results[0].text==''


def test_tavily_domains_dates_and_no_auto_escalation(monkeypatch):
    from services.research.tavily import TavilyProvider
    post=Mock(return_value=response({'results':[],'usage':{'credits':1}}))
    monkeypatch.setattr('requests.post',post)
    TavilyProvider('test').search('官方文档',start_date='2026-01-01',end_date='2026-11-02',domains=['example.com'])
    body=post.call_args.kwargs['json']
    assert body['include_domains']==['example.com'] and body['include_domains_mode']=='restrict'
    assert body['start_date']=='2026-01-01' and body['end_date']=='2026-11-02'
    assert body['search_depth']=='basic' and body['include_answer'] is False
