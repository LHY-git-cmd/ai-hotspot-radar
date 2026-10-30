"""以保守规则规范化去重键，并清理外部 HTML 文本。"""

from html.parser import HTMLParser
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_KEYS = {'fbclid', 'gclid', 'mc_cid', 'mc_eid'}


def normalize_title(title: str) -> str:
    """统一全半角、大小写及连续空白，用于标题去重和关键词搜索。"""
    return ' '.join(unicodedata.normalize('NFKC', title).casefold().split())


def normalize_url(url: str) -> str:
    """只合并有把握的 URL 变体，保留协议、路径及业务参数差异。"""
    if not isinstance(url, str) or not url.strip():
        raise ValueError('原始链接为空')
    url = url.strip()
    if any(char.isspace() or ord(char) < 32 for char in url) or '\\' in url:
        raise ValueError('原始链接包含无效字符')
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() not in ('http', 'https') or not parts.hostname:
            raise ValueError('只允许 HTTP(S) 原始链接')
        if parts.username is not None or parts.password is not None:
            raise ValueError('原始链接不能包含登录凭据')
        scheme = parts.scheme.lower()
        host = parts.hostname.encode('idna').decode('ascii').lower()
        if ':' in host:  # IPv6 主机需要保留方括号。
            host = f'[{host}]'
        port = parts.port
        if port is not None and (scheme, port) not in (('http', 80), ('https', 443)):
            host += f':{port}'
        # 只按参数名稳定排序，同名参数的相对顺序可能有业务含义。
        query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                 if not key.lower().startswith('utm_') and key.lower() not in TRACKING_KEYS]
        query.sort(key=lambda pair: pair[0])
        return urlunsplit((scheme, host, parts.path or '/', urlencode(query), ''))
    except (UnicodeError, ValueError) as error:
        raise ValueError('原始链接格式无效或不支持') from error


class _TextParser(HTMLParser):
    """提取可见文字，排除脚本和样式内容。"""

    def __init__(self):
        """启用实体解码，初始化纯文本缓冲区。"""
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        """隐藏脚本和样式；用空格保留段落边界。"""
        if tag in ('script', 'style'):
            self.hidden += 1
        elif tag in ('p', 'br', 'div', 'li') and not self.hidden:
            self.parts.append(' ')

    def handle_endtag(self, tag):
        """结束隐藏区域并保留块级标签的文本间隔。"""
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        elif tag in ('p', 'div', 'li') and not self.hidden:
            self.parts.append(' ')

    def handle_data(self, data):
        """仅收集可展示文字，避免将远程 HTML 直接传入页面。"""
        if not self.hidden:
            self.parts.append(data)


def plain_text(value: object) -> str:
    """将可选 HTML 字段转换成单行纯文本，缺失时返回空串。"""
    if not isinstance(value, str):
        return ''
    parser = _TextParser()
    parser.feed(value)
    parser.close()
    return ' '.join(''.join(parser.parts).split())
