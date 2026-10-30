"""验证去重键的保守规范化，避免把不同业务 URL 错误合并。"""

import pytest


@pytest.mark.parametrize(('raw', 'expected'), [
    ('HTTPS://Example.COM:443/tool?utm_source=hn&id=2#readme', 'https://example.com/tool?id=2'),
    ('http://Example.com:80', 'http://example.com/'),
    ('https://example.com/Model?b=2&a=1&fbclid=x', 'https://example.com/Model?a=1&b=2'),
    ('https://example.com/?tag=b&tag=a', 'https://example.com/?tag=b&tag=a'),
    ('https://example.com/path?ref=business', 'https://example.com/path?ref=business'),
])
def test_normalize_url(raw, expected):
    """删除跟踪参数和片段，但保留路径大小写、业务参数及重复参数顺序。"""
    from services.normalization import normalize_url
    assert normalize_url(raw) == expected


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'ftp://example.com/a', 'https://',
                                      'https://user:password@example.com', 'https://a.com:bad'])
def test_reject_invalid_url(url):
    """仅允许没有内嵌凭据的有效 HTTP(S) 链接。"""
    from services.normalization import normalize_url
    with pytest.raises(ValueError):
        normalize_url(url)


def test_title_and_html_normalization():
    """统一 Unicode、大小写、空白，并以纯文本处理外部 HTML。"""
    from services.normalization import normalize_title, plain_text
    assert normalize_title('  ＡＩ\n  Tool  ') == 'ai tool'
    assert plain_text('<p>AI &amp; tools</p><script>bad()</script><p>Next</p>') == 'AI & tools Next'


def test_preserve_url_distinctions():
    """HTTP/HTTPS、路径尾斜线和大小写不能在没有重定向依据时合并。"""
    from services.normalization import normalize_url
    assert normalize_url('http://a.com/A') != normalize_url('https://a.com/A')
    assert normalize_url('https://a.com/A') != normalize_url('https://a.com/a')
    assert normalize_url('https://a.com/a/') != normalize_url('https://a.com/a')
