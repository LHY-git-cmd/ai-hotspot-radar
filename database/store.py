"""保存历史热点，依靠 SQLite 唯一约束和事务执行去重更新。"""

from contextlib import contextmanager
from pathlib import Path
from importlib import import_module
import sqlite3
import json
from collections.abc import Iterable

from models import Hotspot, SaveResult, as_score, as_utc_iso, utc_now
from services.normalization import normalize_title, normalize_url

FIELDS = 'id, title, url, source, summary, published_at, collected_at, score, category, primary_source_key'


class HotspotStore:
    """短连接访问本地 SQLite，不跨 Streamlit 重运行共享连接。"""

    def __init__(self, path: str | Path):
        """创建数据库父目录及表，保留已存在的数据。"""
        self.path = Path(path)
        existing = self.path.exists()
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
        with self._connection() as connection:
            # Streamlit 热重载可能留下旧 from-import 函数引用；按需取当前模块入口。
            import_module('database.migrations').migrate(connection, self.path, backup_existing=existing)

    @contextmanager
    def _connection(self):
        """在事务结束后明确关闭连接，避免 Windows 文件句柄泄漏。"""
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute('PRAGMA foreign_keys=ON')
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, items: Iterable[Hotspot], *, cycle_id: str | None = None,
             source: str | None = None, started_at: str | None = None,
             warnings: list[str] | None = None) -> SaveResult:
        """按来源事务保存；提供周期时同时写入不可覆盖的快照及来源任务。"""
        result = SaveResult()
        items = list(items)
        if cycle_id and (not source or any(item.source != source for item in items)):
            raise ValueError('采集任务来源与记录来源不一致')
        with self._connection() as connection:
            # 在查询重复键之前获取写事务，避免并发刷新在检查与插入间竞争。
            connection.execute('BEGIN IMMEDIATE')
            if cycle_id:
                previous = connection.execute(
                    'SELECT * FROM collection_runs WHERE cycle_id=? AND source=?', (cycle_id, source)
                ).fetchone()
                if previous and previous['status'] != 'failed':
                    return SaveResult(skipped=len(items))
            for item in items:
                url_key = normalize_url(item.url)
                title_key = normalize_title(item.title)
                if not title_key:
                    raise ValueError('标题不能为空')
                search_text = normalize_title(f'{item.title} {item.summary or ""} {item.url}')
                matches = connection.execute(
                    'SELECT id, source, normalized_url, primary_source_key FROM hotspots '
                    'WHERE normalized_url = ? OR normalized_title = ? '
                    'OR (source = ? AND primary_source_key = ?)',
                    (url_key, title_key, item.source, item.source_key),
                ).fetchall()
                if cycle_id and item.source_key and len(matches) == 1:
                    existing_snapshot = connection.execute('''SELECT id FROM hotspot_snapshots
                        WHERE cycle_id=? AND hotspot_id=? AND source=? AND source_key=?''',
                        (cycle_id, matches[0]['id'], item.source, item.source_key)).fetchone()
                    if existing_snapshot:
                        result.skipped += 1
                        continue
                hotspot_id = None
                primary = False
                if not matches:
                    cursor = connection.execute('''
                        INSERT INTO hotspots (
                            title, url, source, summary, published_at, collected_at,
                            score, category, normalized_url, normalized_title, search_text, primary_source_key
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (item.title, item.url, item.source, item.summary, item.published_at,
                          item.collected_at, item.score, item.category, url_key, title_key, search_text,
                          item.source_key))
                    hotspot_id, primary = cursor.lastrowid, True
                    result.inserted += 1
                elif (len(matches) == 1 and matches[0]['source'] == item.source
                      and (matches[0]['primary_source_key'] == item.source_key
                           and item.source_key is not None
                           or matches[0]['normalized_url'] == url_key
                           and (matches[0]['primary_source_key'] is None or item.source_key is None))):
                    # collected_at 始终保留首次采集时间；缺失的新指标仍保存为空。
                    connection.execute('''
                        UPDATE hotspots SET title = ?, summary = ?, published_at = ?,
                            score = ?, category = ?, normalized_title = ?, search_text = ?,
                            primary_source_key = COALESCE(primary_source_key, ?)
                        WHERE id = ?
                    ''', (item.title, item.summary, item.published_at, item.score, item.category,
                          title_key, search_text, item.source_key, matches[0]['id']))
                    hotspot_id, primary = matches[0]['id'], True
                    result.updated += 1
                else:
                    result.skipped += 1
                    if len(matches) == 1 and matches[0]['normalized_url'] == url_key:
                        hotspot_id = matches[0]['id']
                if primary:
                    connection.execute('UPDATE hotspot_scores SET stale=1 WHERE hotspot_id=?', (hotspot_id,))
                if hotspot_id and cycle_id and item.source_key:
                    observed_at = as_utc_iso(item.collected_at)
                    if observed_at is None:
                        raise ValueError('快照必须有有效的实际采集时间')
                    connection.execute('''INSERT OR IGNORE INTO hotspot_snapshots
                        (hotspot_id, cycle_id, source, source_key, collected_at, url,
                         stars, forks, hn_score, comments, published_at, pushed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                            hotspot_id, cycle_id, item.source, item.source_key, observed_at, item.url,
                            as_score(item.score) if item.source == 'GitHub' else None,
                            as_score(item.forks) if item.source == 'GitHub' else None,
                            as_score(item.score) if item.source == 'Hacker News' else None,
                            as_score(item.comments) if item.source == 'Hacker News' else None,
                            as_utc_iso(item.published_at), as_utc_iso(item.pushed_at),
                        ))
                    result.snapshots += connection.execute('SELECT changes()').fetchone()[0]
            if cycle_id:
                connection.execute('''INSERT OR REPLACE INTO collection_runs
                    (cycle_id, source, started_at, finished_at, status, fetched,
                     inserted, updated, skipped, snapshots, warnings)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                        cycle_id, source, started_at or utc_now(), utc_now(),
                        'partial' if warnings else 'success', len(items),
                        result.inserted, result.updated, result.skipped, result.snapshots,
                        json.dumps(warnings or [], ensure_ascii=False),
                    ))
        return result

    def history(self, hotspot_id: int) -> list[dict]:
        """返回全部来源的真实历史，显示时必须按来源和对象分别解释。"""
        with self._connection() as connection:
            rows = connection.execute('SELECT * FROM hotspot_snapshots WHERE hotspot_id=? '
                                      'ORDER BY collected_at, id', (hotspot_id,)).fetchall()
        return [dict(row) for row in rows]

    def collection_run(self, cycle_id: str, source: str) -> dict | None:
        """供幂等重入和页面读取一个来源任务的状态。"""
        with self._connection() as connection:
            row = connection.execute('SELECT * FROM collection_runs WHERE cycle_id=? AND source=?',
                                     (cycle_id, source)).fetchone()
        return dict(row) if row else None

    def record_failure(self, cycle_id: str, source: str, started_at: str, error: str) -> None:
        """失败独立记录，不产生指标或覆盖已成功完成的同周期任务。"""
        with self._connection() as connection:
            connection.execute('''INSERT INTO collection_runs
                (cycle_id, source, started_at, finished_at, status, error)
                VALUES (?, ?, ?, ?, 'failed', ?)
                ON CONFLICT(cycle_id, source) DO UPDATE SET finished_at=excluded.finished_at,
                    status='failed', error=excluded.error WHERE collection_runs.status='failed'
            ''', (cycle_id, source, started_at, utc_now(), error))

    def recent_runs(self, limit: int = 10) -> list[dict]:
        """使服务重启后仍能查询最近的采集错误和采样状态。"""
        with self._connection() as connection:
            return [dict(row) for row in connection.execute(
                'SELECT * FROM collection_runs ORDER BY finished_at DESC, rowid DESC LIMIT ?', (limit,))]

    def scoring_inputs(self) -> list[dict]:
        """一次读事务批量读取热点和快照，避免逐条连接查询。"""
        with self._connection() as connection:
            connection.execute('BEGIN')
            return self._scoring_inputs(connection)

    @staticmethod
    def _scoring_inputs(connection: sqlite3.Connection) -> list[dict]:
        """在已有事务内读取一致输入，也用于防止并发刷新覆盖评分状态。"""
        items = [dict(row) for row in connection.execute(f'SELECT {FIELDS} FROM hotspots ORDER BY id')]
        grouped = {item['id']: [] for item in items}
        for row in connection.execute('SELECT * FROM hotspot_snapshots ORDER BY collected_at, id'):
            grouped[row['hotspot_id']].append(dict(row))
        return [item | {'snapshots': grouped[item['id']]} for item in items]

    def save_scores(self, results: list[dict], *, expected_inputs: list[dict] | None = None) -> None:
        """批量原子替换当前评分，保留完整规则参数、证据和计算时间。"""
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if expected_inputs is not None and self._scoring_inputs(connection) != expected_inputs:
                raise ValueError('数据已更新，请重新计算评分')
            for result in results:
                connection.execute('''INSERT INTO hotspot_scores
                    (hotspot_id, heat_score, video_score, composite_score, calculated_at,
                     rule_version, details, stale) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(hotspot_id) DO UPDATE SET heat_score=excluded.heat_score,
                        video_score=excluded.video_score, composite_score=excluded.composite_score,
                        calculated_at=excluded.calculated_at, rule_version=excluded.rule_version,
                        details=excluded.details, stale=0''', (
                            result['hotspot_id'], result['heat_score'], result['video_score'],
                            result['composite_score'], result['calculated_at'], result['rule_version'],
                            json.dumps(result, ensure_ascii=False, allow_nan=False),
                        ))

    def mark_scores_stale(self) -> None:
        """重算失败时保留旧评分，并明确标记不再代表最新计算。"""
        with self._connection() as connection:
            connection.execute('UPDATE hotspot_scores SET stale=1')

    def ranked_items(self) -> list[dict]:
        """读取已保存评分，页面筛选和排序不触发采集或重算。"""
        with self._connection() as connection:
            rows = connection.execute('''SELECT h.*, s.details, s.stale FROM hotspots h
                LEFT JOIN hotspot_scores s ON s.hotspot_id=h.id''').fetchall()
        return [dict(row) | {'rating': json.loads(row['details']) if row['details'] else None}
                for row in rows]

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
