"""AI 持久化：原子预算预占、跨会话幂等、分析历史与选题状态。"""

from datetime import datetime
from decimal import Decimal
import json

from database.store import HotspotStore
from models import utc_now
from services.ai.base import AIError, Usage
from services.ai.config import AISettings, PROMPT_VERSION, SCHEMA_VERSION
from services.ai.cost_tracker import month_key, to_units

IDEA_STATUSES = {'new': '新建', 'favorite': '收藏', 'discarded': '淘汰', 'selected': '选中', 'to_produce': '待制作'}


def _json(value: object) -> str:
    """持久化中文结构，禁止 NaN 等非 JSON 值。"""
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class AIStore(HotspotStore):
    """复用短连接/事务，不通过 session_state 持有费用或调用锁。"""

    def __init__(self, path, settings: AISettings):
        """预算默认值只首次写入，后续配置读取不能覆盖用户调整。"""
        super().__init__(path)
        self.settings = settings
        with self._connection() as connection:
            connection.execute('INSERT OR IGNORE INTO ai_budget_settings(id,limit_units,updated_at) VALUES(1,?,?)',
                               (to_units(settings.monthly_budget_cny), utc_now()))

    @staticmethod
    def _budget(connection, month: str) -> dict:
        """一个查询区分已结算估算与未确认预占，二者不能重复计入。"""
        limit = connection.execute('SELECT limit_units FROM ai_budget_settings WHERE id=1').fetchone()[0]
        row = connection.execute('''SELECT
            COALESCE(SUM(COALESCE(manual_cost_units,estimated_cost_units,0)),0) AS estimated,
            COALESCE(SUM(CASE WHEN estimated_cost_units IS NULL AND manual_cost_units IS NULL
                THEN reserved_units ELSE 0 END),0) AS held,
            COALESCE(SUM(input_tokens),0) AS input_tokens, COALESCE(SUM(output_tokens),0) AS output_tokens,
            SUM(CASE WHEN input_tokens IS NULL OR output_tokens IS NULL THEN 1 ELSE 0 END) AS missing,
            COUNT(*) AS attempts FROM ai_analysis_runs WHERE budget_month=?''', (month,)).fetchone()
        occupied = row['estimated'] + row['held']
        warning = ('已达上限' if occupied >= limit else '高风险' if occupied * 10 >= limit * 9 else
                   '警告' if occupied * 10 >= limit * 7 else '正常')
        return dict(month=month, limit_units=limit, estimated_units=row['estimated'], held_units=row['held'],
                    occupied_units=occupied, remaining_units=max(0, limit-occupied), warning=warning,
                    input_tokens=row['input_tokens'], output_tokens=row['output_tokens'],
                    unknown_usage_runs=row['missing'] or 0, attempts=row['attempts'])

    def budget(self, *, now: datetime | None = None) -> dict:
        """只读本月预算，重启和切换页面都不会清零。"""
        with self._connection() as connection:
            return self._budget(connection, month_key(now))

    def set_budget(self, amount: Decimal) -> None:
        """用户主动保存才调整上限，允许0元暂停调用，追加审计记录。"""
        units = to_units(amount)
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM ai_budget_settings WHERE id=1').fetchone()
            audit = json.loads(row['audit_json'])
            audit.append({'at': utc_now(), 'before_units': row['limit_units'], 'after_units': units})
            connection.execute('UPDATE ai_budget_settings SET limit_units=?,updated_at=?,audit_json=? WHERE id=1',
                               (units, utc_now(), _json(audit)))

    def claim_analysis(self, hotspot_id: int, cache_key: str, action_id: str, materials: dict,
                       analysis_version: str, force: bool, *, provider: str = 'mock') -> dict:
        """获得材料的持久执行锁；成功缓存和同动作重入都不能再次调用。"""
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            previous = connection.execute('SELECT * FROM topic_analyses WHERE action_id=?', (action_id,)).fetchone()
            if previous:
                if previous['cache_key'] != cache_key or previous['hotspot_id'] != hotspot_id:
                    raise AIError('action_conflict', '此确认动作的材料已变化，请重新确认。')
                return dict(previous) | {'cache_hit': previous['status'] == 'success', 'reused_action': True}
            if not force:
                cached = connection.execute("SELECT * FROM topic_analyses WHERE cache_key=? AND status='success' ORDER BY id DESC LIMIT 1",
                                            (cache_key,)).fetchone()
                if cached:
                    return dict(cached) | {'cache_hit': True, 'reused_action': False}
            active = connection.execute("SELECT * FROM topic_analyses WHERE cache_key=? AND status IN ('running','uncertain')",
                                        (cache_key,)).fetchone()
            if active:
                raise AIError('in_progress', '相同材料的分析正在进行中或费用状态待确认，请查看调用记录，勿重复提交。')
            cursor = connection.execute('''INSERT INTO topic_analyses
                (hotspot_id,cache_key,action_id,provider,model,prompt_version,schema_version,
                 analysis_version,output_mode,input_json,status,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,'running',?)''', (hotspot_id, cache_key, action_id, provider,
                self.settings.model, PROMPT_VERSION, SCHEMA_VERSION, analysis_version,
                self.settings.output_mode, _json(materials), utc_now()))
            return {'id': cursor.lastrowid, 'status': 'running', 'cache_hit': False, 'reused_action': False}

    def reserve_attempt(self, analysis_id: int, attempt: int, units: int, price: dict,
                        *, now: datetime | None = None) -> int:
        """在同一写事务内检查并预占；这是每一次 HTTP 发送之前的必经门禁。"""
        if type(units) is not int or units <= 0:
            raise ValueError('调用预占必须为正整数金额')
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            analysis = connection.execute('SELECT * FROM topic_analyses WHERE id=?', (analysis_id,)).fetchone()
            if not analysis or analysis['status'] != 'running':
                raise AIError('state', '分析已完成或状态待确认，不能发送新的调用。')
            budget = self._budget(connection, month_key(now))
            if units > budget['remaining_units']:
                raise AIError('budget', '本月预算不足以预占本次调用，请核对费用或主动调整月预算。')
            cursor = connection.execute('''INSERT INTO ai_analysis_runs
                (analysis_id,attempt,provider,model,prompt_version,schema_version,output_mode,
                 price_version,price_json,reserved_units,status,budget_month,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,'pending',?,?)''', (analysis_id, attempt, analysis['provider'],
                analysis['model'], analysis['prompt_version'], analysis['schema_version'], analysis['output_mode'],
                price.get('price_version', self.settings.price_version), _json(price), units, month_key(now), utc_now()))
            return cursor.lastrowid

    def finish_attempt(self, run_id: int, status: str, usage: Usage, cost_units: int | None,
                       error_type: str | None, response_model: str | None = None) -> None:
        """实际 usage 与状态落库；未知费用保留原预占，后续人工核对。"""
        if status not in ('success', 'failed'):
            raise ValueError('调用终态无效')
        with self._connection() as connection:
            connection.execute('''UPDATE ai_analysis_runs SET status=?,input_tokens=?,output_tokens=?,
                cache_hit_tokens=?,cache_miss_tokens=?,estimated_cost_units=?,error_type=?,response_model=?,finished_at=?
                WHERE id=? AND status='pending' ''', (status, usage.input_tokens, usage.output_tokens,
                usage.cache_hit_tokens, usage.cache_miss_tokens, cost_units, error_type, response_model, utc_now(), run_id))

    def fail_analysis(self, analysis_id: int, error_type: str) -> None:
        """失败不是成功结果；只要有未知费用就保留材料锁，防止重启重发。"""
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            unknown = connection.execute('''SELECT 1 FROM ai_analysis_runs WHERE analysis_id=?
                AND estimated_cost_units IS NULL AND manual_cost_units IS NULL LIMIT 1''', (analysis_id,)).fetchone()
            connection.execute("UPDATE topic_analyses SET status=?,error_type=?,completed_at=? WHERE id=? AND status='running'",
                               ('uncertain' if unknown else 'failed', error_type, utc_now(), analysis_id))

    def complete_analysis(self, analysis_id: int, run_id: int, document: dict, evidence_status: str) -> None:
        """分析和三个角度在一个事务落库，失败不会留下部分成功选题。"""
        from services.ai.schemas import validate_analysis
        document = validate_analysis(document)
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute("SELECT * FROM topic_analyses WHERE id=? AND status='running'", (analysis_id,)).fetchone()
            run = connection.execute("SELECT id FROM ai_analysis_runs WHERE id=? AND analysis_id=? AND status='success'",
                                     (run_id, analysis_id)).fetchone()
            if not row or not run:
                raise ValueError('分析或调用状态无效，不能标记为成功')
            now = utc_now()
            for position, idea in enumerate(document['video_ideas'], 1):
                connection.execute('''INSERT INTO video_ideas
                    (analysis_id,position,angle_type,title,hook,outline_json,target_audience,materials_json,
                     verification_json,difficulty,recommendation_reason,idea_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (analysis_id, position, idea['angle_type'], idea['title'],
                    idea['hook'], _json(idea['outline']), idea['target_audience'], _json(idea['materials']),
                    _json(idea['verification_checklist']), idea['difficulty'], idea['recommendation_reason'],
                    _json(idea), now, now))
            connection.execute("UPDATE topic_analyses SET status='success',analysis_json=?,summary=?,evidence_status=?,success_run_id=?,completed_at=? WHERE id=?",
                (_json(document), document['summary'], evidence_status, run_id, now, analysis_id))

    def analyses(self, hotspot_id: int | None = None) -> list[dict]:
        """只返回真正成功的分析，失败尝试在调用记录中单独展示。"""
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM topic_analyses WHERE status='success'"
                + (' AND hotspot_id=?' if hotspot_id is not None else '') + ' ORDER BY id DESC',
                (hotspot_id,) if hotspot_id is not None else ()).fetchall()
        return [dict(row) | {'document': json.loads(row['analysis_json'])} for row in rows]

    def material_already_handled(self, cache_key: str) -> bool:
        """候选筛选跳过缓存、在途和费用待确认对象。"""
        with self._connection() as connection:
            return connection.execute("SELECT 1 FROM topic_analyses WHERE cache_key=? AND status IN ('success','running','uncertain') LIMIT 1",
                                      (cache_key,)).fetchone() is not None

    def ideas(self, analysis_id: int | None = None, status: str = '') -> list[dict]:
        """返回完整结构和持久状态，查看/筛选不会调用模型。"""
        where, values = [], []
        if analysis_id is not None:
            where.append('analysis_id=?')
            values.append(analysis_id)
        if status:
            where.append('status=?')
            values.append(status)
        with self._connection() as connection:
            rows = connection.execute('SELECT * FROM video_ideas'
                + (' WHERE ' + ' AND '.join(where) if where else '') + ' ORDER BY analysis_id DESC,position', values)
            return [dict(row) | {'document': json.loads(row['idea_json'])} for row in rows]

    def set_idea_status(self, idea_id: int, status: str) -> None:
        """状态及动作历史同事务保存；重复提交同一状态不重复记动作。"""
        if status not in IDEA_STATUSES:
            raise ValueError('选题状态无效')
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT status FROM video_ideas WHERE id=?', (idea_id,)).fetchone()
            if not row:
                raise ValueError('选题不存在')
            if row['status'] != status:
                connection.execute('INSERT INTO idea_actions(idea_id,action,previous_status,created_at) VALUES(?,?,?,?)',
                                   (idea_id, status, row['status'], utc_now()))
                connection.execute('UPDATE video_ideas SET status=?,updated_at=? WHERE id=?', (status, utc_now(), idea_id))

    def actions(self, idea_id: int) -> list[dict]:
        """读取选题动作审计。"""
        with self._connection() as connection:
            return [dict(row) for row in connection.execute('SELECT * FROM idea_actions WHERE idea_id=? ORDER BY id', (idea_id,))]

    def runs(self) -> list[dict]:
        """读取调用和待确认费用，不包含密钥或原始响应正文。"""
        with self._connection() as connection:
            return [dict(row) for row in connection.execute('SELECT * FROM ai_analysis_runs ORDER BY id DESC')]

    def unresolved(self) -> list[dict]:
        """包括进程中断的 running 记录，不在重启时自动重发。"""
        with self._connection() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM topic_analyses WHERE status IN ('running','uncertain') ORDER BY id DESC")]

    def resolve_cost(self, run_id: int, amount: Decimal, reason: str) -> None:
        """用户在服务商账单核对后填写金额，保留原 usage、预占和审核理由。"""
        if len(reason.strip()) < 8:
            raise ValueError('请填写至少8个字符的账单核对依据')
        units = to_units(amount)
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            run = connection.execute('SELECT * FROM ai_analysis_runs WHERE id=?', (run_id,)).fetchone()
            if not run or run['estimated_cost_units'] is not None or run['manual_cost_units'] is not None:
                raise ValueError('该调用没有待核对费用')
            # running 可能仍在网络请求中，不能在此时释放预占并允许并发重试。
            analysis = connection.execute('SELECT * FROM topic_analyses WHERE id=?', (run['analysis_id'],)).fetchone()
            if analysis['status'] == 'running':
                raise ValueError('任务仍在运行，请先确认任务已中断')
            connection.execute('UPDATE ai_analysis_runs SET manual_cost_units=?,resolution_reason=?,resolved_at=? WHERE id=?',
                               (units, reason.strip(), utc_now(), run_id))
            unknown = connection.execute('''SELECT 1 FROM ai_analysis_runs WHERE analysis_id=?
                AND estimated_cost_units IS NULL AND manual_cost_units IS NULL''', (run['analysis_id'],)).fetchone()
            if not unknown:
                connection.execute("UPDATE topic_analyses SET status='failed' WHERE id=? AND status='uncertain'", (run['analysis_id'],))

    def acknowledge_interrupted(self, analysis_id: int) -> None:
        """用户确认原任务已终止才释放运行状态；费用预占仍保留待核对。"""
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            unknown = connection.execute('''SELECT 1 FROM ai_analysis_runs WHERE analysis_id=?
                AND estimated_cost_units IS NULL AND manual_cost_units IS NULL''', (analysis_id,)).fetchone()
            connection.execute("UPDATE topic_analyses SET status=?,error_type='user_confirmed_interruption' WHERE id=? AND status='running'",
                               ('uncertain' if unknown else 'failed', analysis_id))
