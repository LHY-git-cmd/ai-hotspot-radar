"""精确费用估算和北京时间月份；费用未知时返回空而非零。"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from zoneinfo import ZoneInfo
import json

from services.ai.base import Usage
from services.ai.config import AISettings

UNITS_PER_CNY = 1000000


def to_units(value: Decimal) -> int:
    """货币以百万分之一元入库并向上取整，不能用浮点误差绕过预算。"""
    if not value.is_finite() or value < 0:
        raise ValueError('金额必须为有限非负数')
    return int((value * UNITS_PER_CNY).to_integral_value(rounding=ROUND_CEILING))


def money(units: int) -> str:
    """以人民币展示存储单位，保留小额调用的精度。"""
    return f'{Decimal(units) / UNITS_PER_CNY:.6f}'


def month_key(now: datetime | None = None) -> str:
    """统一以北京时间归属账期，不依赖执行主机时区。"""
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m')


def estimate_units(usage: Usage, settings: AISettings) -> int | None:
    """缓存细分不完整或不一致时按全部未命中保守估算，Token 本身不伪造。"""
    if usage.input_tokens is None or usage.output_tokens is None:
        return None
    hit, miss = usage.cache_hit_tokens, usage.cache_miss_tokens
    if hit is None or miss is None or hit + miss != usage.input_tokens:
        hit, miss = 0, usage.input_tokens
    amount = (Decimal(hit) * settings.input_hit_price + Decimal(miss) * settings.input_miss_price
              + Decimal(usage.output_tokens) * settings.output_price) / 1000000 * settings.cny_per_unit
    return to_units(amount)


def reservation_units(messages: list[dict], settings: AISettings, *, body: dict | None = None) -> int:
    """按完整请求 UTF-8 字节数及输出上限预占，给包装计量留保守余量。"""
    from services.ai.deepseek_client import request_body
    size = len(json.dumps(request_body(settings, messages) if body is None else body,
                          ensure_ascii=False).encode('utf-8'))
    if size > settings.max_request_bytes:
        raise ValueError('分析材料超过输入体积上限')
    # 将每个输入字节都按一个 Token 计费，并额外留4096 Token余量；不是实际 Token 数。
    upper_input = size + 4096
    input_price = max(settings.input_hit_price, settings.input_miss_price)
    amount = (Decimal(upper_input) * input_price + Decimal(settings.max_output_tokens)
              * settings.output_price) / 1000000 * settings.cny_per_unit
    return to_units(amount)


def price_snapshot(settings: AISettings) -> dict:
    """冻结单价及汇率，后续配置变化不能重写旧估算；不包含密钥。"""
    return {name: str(getattr(settings, name)) for name in (
        'price_currency', 'input_hit_price', 'input_miss_price', 'output_price',
        'cny_per_unit', 'price_version')}
