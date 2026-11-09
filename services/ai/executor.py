"""选题和研究共用的逐次预算调用流程；Provider 内不隐式重试。"""

import logging
import time

from services.ai.base import AIError, Usage
from services.ai.cost_tracker import estimate_units, price_snapshot

logger = logging.getLogger('ai_hotspot_radar.ai')


def execute_attempts(store, provider, settings, analysis_id, messages, reserved, validate, persist,
                     *, sleep=time.sleep, before_attempt=None, on_diagnostic=None):
    """先预占再发送；用量落库先于业务结果，业务保存失败也不能抹掉费用。"""
    def diagnose(run_id, stage, error, document=None):
        if on_diagnostic is not None:
            try:
                on_diagnostic(run_id, stage, error, document)
            except Exception:
                # 诊断是附属记录，失败不能改写主错误、结算或重试决策。
                logger.error('analysis=%d diagnostic persistence failed', analysis_id)

    for attempt in range(1, settings.max_attempts + 1):
        if before_attempt is not None:
            before_attempt()
        run_id = store.reserve_attempt(analysis_id, attempt, reserved, price_snapshot(settings))
        try:
            reply = provider.complete(messages)
        except AIError as error:
            store.finish_attempt(run_id, 'failed', error.usage, estimate_units(error.usage, settings), error.kind)
            diagnose(run_id, 'provider', error)
            logger.warning('analysis=%d attempt=%d failed type=%s', analysis_id, attempt, error.kind)
            if error.retryable and attempt < settings.max_attempts:
                sleep(max(error.retry_after or 0, min(2 ** (attempt - 1), 8)))
                continue
            raise
        except Exception as error:
            store.finish_attempt(run_id, 'failed', Usage(), None, type(error).__name__)
            diagnose(run_id, 'provider', error)
            raise AIError('provider_failure', 'AI 调用异常，费用待确认，请查看调用记录。') from None
        cost = estimate_units(reply.usage, settings)
        try:
            document = validate(reply.document)
        except ValueError as error:
            store.finish_attempt(run_id, 'failed', reply.usage, cost, 'invalid_schema', reply.response_model)
            diagnose(run_id, 'validation', error, reply.document)
            raise AIError('invalid_schema', 'AI 内容或引用未通过校验；已保存可得用量，未保存成功结果。') from None
        store.finish_attempt(run_id, 'success', reply.usage, cost, None, reply.response_model)
        try:
            persist(analysis_id, run_id, document)
        except Exception as error:
            diagnose(run_id, 'persistence', error)
            raise
        return
