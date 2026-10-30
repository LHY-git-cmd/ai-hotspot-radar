"""保存历史热点，依靠 SQLite 唯一约束和事务执行去重更新。"""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from collections.abc import Iterable

from models import Hotspot, SaveResult
from services.normalization import normalize_title, normalize_url

FIELDS = 'id, title, url, source, summary, published_at, collected_at, score, category'


class HotspotStore:
    """短连接访问本地 SQLite，不跨 Streamlit 重运行共享连接。"""

    def __init__(self, path: str | Path):
        """创建数据库父目录及表，保留已存在的数据。"""
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS hotspots (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL CHECK(source IN ('GitHub', 'Hacker News')),
                    summary TEXT,
                    published_at TEXT,
                    collected_at TEXT NOT NULL,
                    score INTEGER CHECK(score IS NULL OR score >= 0),
                    category TEXT NOT NULL,
                    normalized_url TEXT NOT NULL UNIQUE,
                    normalized_title TEXT NOT NULL UNIQUE,
                    search_text TEXT NOT NULL
                )
            ''')
            connection.execute('CREATE INDEX IF NOT EXISTS idx_hotspots_source ON hotspots(source)')

    @contextmanager
    def _connection(self):
        """在事务结束后明确关闭连接，避免 Windows 文件句柄泄漏。"""
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, items: Iterable[Hotspot]) -> SaveResult:
        """同来源同 URL 更新，标题重复或跨来源重复保留首次记录。"""
        result = SaveResult()
        with self._connection() as connection:
            # 在查询重复键之前获取写事务，避免并发刷新在检查与插入间竞争。
            connection.execute('BEGIN IMMEDIATE')
            for item in items:
                url_key = normalize_url(item.url)
                title_key = normalize_title(item.title)
                if not title_key:
                    raise ValueError('标题不能为空')
                search_text = normalize_title(f'{item.title} {item.summary or ""} {item.url}')
                matches = connection.execute(
                    'SELECT id, source, normalized_url FROM hotspots '
                    'WHERE normalized_url = ? OR normalized_title = ?',
                    (url_key, title_key),
                ).fetchall()
                if not matches:
                    connection.execute('''
                        INSERT INTO hotspots (
                            title, url, source, summary, published_at, collected_at,
                            score, category, normalized_url, normalized_title, search_text
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (item.title, item.url, item.source, item.summary, item.published_at,
                          item.collected_at, item.score, item.category, url_key, title_key, search_text))
                    result.inserted += 1
                elif (len(matches) == 1 and matches[0]['source'] == item.source
                      and matches[0]['normalized_url'] == url_key):
                    # collected_at 始终保留首次采集时间；缺失的新指标仍保存为空。
                    connection.execute('''
                        UPDATE hotspots SET title = ?, summary = ?, published_at = ?,
                            score = ?, category = ?, normalized_title = ?, search_text = ?
                        WHERE id = ?
                    ''', (item.title, item.summary, item.published_at, item.score, item.category,
                          title_key, search_text, matches[0]['id']))
                    result.updated += 1
                else:
                    result.skipped += 1
        return result

    @staticmethod
    def _filters(query: str, source: str) -> tuple[str, list]:
        """构造参数化筛选，转义 LIKE 通配符以按字面搜索。"""
        clauses, params = [], []
        if query.strip():
            escaped = normalize_title(query).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append("search_text LIKE ? ESCAPE '\\'")
            params.append(f'%{escaped}%')
        if source:
            clauses.append('source = ?')
            params.append(source)
        return (' WHERE ' + ' AND '.join(clauses) if clauses else ''), params

    def count(self, query: str = '', source: str = '') -> int:
        """按当前搜索及来源条件统计数量。"""
        where, params = self._filters(query, source)
        with self._connection() as connection:
            return connection.execute('SELECT COUNT(*) FROM hotspots' + where, params).fetchone()[0]

    def search(self, query: str = '', source: str = '', limit: int = 20,
               offset: int = 0) -> list[dict]:
        """按发布时间倒序分页，时间缺失的记录放在最后，不比较跨来源热度。"""
        if limit < 1 or offset < 0:
            raise ValueError('分页参数无效')
        where, params = self._filters(query, source)
        with self._connection() as connection:
            rows = connection.execute(
                f'SELECT {FIELDS} FROM hotspots' + where
                + ' ORDER BY published_at DESC, collected_at DESC, id DESC LIMIT ? OFFSET ?',
                [*params, limit, offset],
            ).fetchall()
        return [dict(row) for row in rows]
