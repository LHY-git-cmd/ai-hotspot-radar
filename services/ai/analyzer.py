"""基于已有热点编排 AI 分析，预算门禁与失败记录在每次尝试之前/之后执行。"""

import hashlib
import json
import logging
import time
from copy import deepcopy

from database.ai_store import AIStore
from services.ai.base import AIError, Provider, Usage
from services.ai.config import AISettings, ANALYSIS_VERSION, PROMPT_VERSION, SCHEMA_VERSION
from services.ai.cost_tracker import estimate_units, reservation_units, price_snapshot
from services.ai.prompts import build_messages
from services.ai.schemas import validate_analysis
from services.ranking import rank_items, score_needs_refresh

logger = logging.getLogger('ai_hotspot_radar.ai')


class Analyzer:
    """独立于采集和 A/B 评分，读取确定性结果，不执行外部指令。"""

    def __init__(self, store: AIStore, provider: Provider, settings: AISettings, *,
                 sleep=time.sleep):
        """重试等待可注入测试；Provider 不允许隐藏内部重试。"""
        self.store, self.provider, self.settings, self.sleep = store, provider, settings, sleep

    def materials(self, hotspot_id: int) -> dict:
        """限制外部文本长度并标记截断；只读本地已有事实，不访问链接。"""
        item = next((row for row in self.store.ranked_items() if row['id'] == hotspot_id), None)
        if item is None:
            raise AIError('not_found', '热点不存在，无法分析。')
        rating = item['rating']
        history = [row for row in self.store.history(hotspot_id)
                   if row['source'] == item['source'] and row['source_key'] == item['primary_source_key']]
        latest = history[-1] if history else None
        summary, title = item['summary'] or '', item['title'] or ''
        source_material = {'title': title[:500], 'summary': summary[:4000] or None,
                           'source': item['source'], 'url': item['url'],
                           'text_truncated': len(title) > 500 or len(summary) > 4000}
        metrics = {key: latest.get(key) for key in (
            'source', 'source_key', 'collected_at', 'stars', 'forks', 'hn_score', 'comments',
            'published_at', 'pushed_at')} if latest else None
        trend = {key: rating['trend'].get(key) for key in (
            'status', 'confidence', 'delta', 'daily_growth', 'percent_growth', 'interval_hours',
            'baseline_at', 'latest_at')} if rating else {'status': '趋势数据不足'}
        return {'hotspot_id': hotspot_id, 'E1_source_text': source_material, 'E2_observations': metrics,
                'E3_deterministic_scores': {'heat_score': rating['heat_score'] if rating else None,
                    'video_score': rating['video_score'] if rating else None,
                    'score_stale': score_needs_refresh(item) if rating else True, 'trend': trend},
                'material_limits': '仅限提供的材料；没有访问链接或亲测产品，未知指标不能补零。'}

    def fingerprint(self, materials: dict) -> str:
        """版本和实际材料共同构成缓存键，不包含密钥或后台记录时间。"""
        stable = deepcopy(materials)
        # 页面时间推移导致的“评分已旧”不应单独产生一个收费版本。
        stable.get('E3_deterministic_scores', {}).pop('score_stale', None)
        content = {'materials': stable, 'provider': self.provider.name, 'model': self.settings.model,
                   'mode': self.settings.output_mode, 'analysis_version': ANALYSIS_VERSION,
                   'prompt_version': PROMPT_VERSION, 'schema_version': SCHEMA_VERSION}
        return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()

    def candidates(self) -> list[dict]:
        """每批最多10条，优先有效新鲜 A/B 评分；筛选本身不收费。"""
        results = []
        for item in rank_items(self.store.ranked_items()):
            rating = item['rating']
            if (not rating or rating['heat_score'] is None or rating['video_score'] is None
                    or score_needs_refresh(item)):
                continue
            materials = self.materials(item['id'])
            if not self.store.material_already_handled(self.fingerprint(materials)):
                results.append(item)
                if len(results) >= self.settings.max_candidates:
                    break
        return results

    def preview(self, hotspot_ids: list[int]) -> dict:
        """费用上界仅作预览，真正发送仍必须通过数据库事务门禁。"""
        upper = sum(reservation_units(build_messages(self.materials(item_id)), self.settings)
                    * self.settings.max_attempts for item_id in hotspot_ids)
        return {'analyses': len(hotspot_ids), 'max_attempts': len(hotspot_ids) * self.settings.max_attempts,
                'max_reserved_units': upper}

    def analyze(self, hotspot_id: int, action_id: str, force: bool = False, *,
                spending_cap_units: int | None = None, expected_cache_key: str | None = None) -> dict:
        """一次逻辑分析可有限重试；任何费用不明的尝试始终保留预算预占。"""
        analysis_id, run_id = None, None
        try:
            self.settings.validate()
            if self.provider.name == 'deepseek' and not self.settings.api_key:
                raise AIError('configuration', '未配置 DEEPSEEK_API_KEY，不能发起付费分析。')
            materials = self.materials(hotspot_id)
            cache_key = self.fingerprint(materials)
            if expected_cache_key is not None and cache_key != expected_cache_key:
                raise AIError('material_changed', '确认后材料发生变化，请重新预览并确认，不会发送本次请求。')
            messages = build_messages(materials)
            reserved = reservation_units(messages, self.settings)
            if spending_cap_units is not None and reserved * self.settings.max_attempts > spending_cap_units:
                raise AIError('spending_cap', '本次最坏预占超过受控联调上限，未发送请求。')
            claimed = self.store.claim_analysis(hotspot_id, cache_key, action_id,
                materials, ANALYSIS_VERSION, force, provider=self.provider.name)
            analysis_id = claimed['id']
            if claimed['cache_hit']:
                return dict(status='success', analysis_id=analysis_id, cache_hit=True, error=None)
            if claimed.get('reused_action'):
                return dict(status='pending' if claimed['status'] == 'running' else 'failed',
                            analysis_id=analysis_id, cache_hit=False, error='该确认动作已处理，不会重复调用；请查看历史或费用待确认记录。')
            for attempt in range(1, self.settings.max_attempts + 1):
                run_id = self.store.reserve_attempt(analysis_id, attempt, reserved, price_snapshot(self.settings))
                try:
                    reply = self.provider.complete(messages)
                except AIError as error:
                    self.store.finish_attempt(run_id, 'failed', error.usage,
                                              estimate_units(error.usage, self.settings), error.kind)
                    logger.warning('analysis=%d attempt=%d failed type=%s', analysis_id, attempt, error.kind)
                    if error.retryable and attempt < self.settings.max_attempts:
                        self.sleep(max(error.retry_after or 0, min(2 ** (attempt - 1), 8)))
                        continue
                    raise
                except Exception as error:
                    self.store.finish_attempt(run_id, 'failed', Usage(), None, type(error).__name__)
                    raise AIError('provider_failure', 'AI 调用遇到异常，费用待确认，请查看运行记录。') from None
                cost = estimate_units(reply.usage, self.settings)
                try:
                    document = validate_analysis(reply.document)
                except ValueError:
                    self.store.finish_attempt(run_id, 'failed', reply.usage, cost, 'invalid_schema', reply.response_model)
                    raise AIError('invalid_schema', 'AI 内容未通过三角度结构校验，未保存成功分析；已记录可得用量。') from None
                self.store.finish_attempt(run_id, 'success', reply.usage, cost, None, reply.response_model)
                sparse = not materials['E1_source_text']['summary']
                evidence = '有限材料：仅有标题，未独立核验' if sparse else '基于所提供材料，未经独立核验'
                if sparse and len(document['evidence_gaps']) < 12:
                    document['evidence_gaps'].append('客户端提示：仅有标题及公开指标，关键能力和宣传内容都待实际核验。')
                self.store.complete_analysis(analysis_id, run_id, document, evidence)
                logger.info('analysis=%d attempt=%d success usage_known=%s', analysis_id, attempt, cost is not None)
                return dict(status='success', analysis_id=analysis_id, cache_hit=False, error=None)
        except AIError as error:
            if analysis_id is not None:
                self._record_failure(analysis_id, error.kind)
            return dict(status='failed', analysis_id=analysis_id, cache_hit=False, error=str(error))
        except Exception as error:
            logger.error('analysis=%s processing failed type=%s', analysis_id, type(error).__name__)
            if analysis_id is not None:
                self._record_failure(analysis_id, type(error).__name__)
            return dict(status='failed', analysis_id=analysis_id, cache_hit=False,
                        error='分析配置、校验或本地记录保存失败，请检查日志。已保留可能的费用预占，请勿盲目重复调用。')

    def _record_failure(self, analysis_id: int, kind: str) -> None:
        """记录失败也失败时保留原运行锁和预占，只记录安全异常类型。"""
        try:
            self.store.fail_analysis(analysis_id, kind)
        except Exception as error:
            logger.error('analysis=%d failure-state persist failed type=%s', analysis_id, type(error).__name__)
