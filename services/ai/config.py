"""集中 AI 配置、已核对模型能力与价格；密钥不参与 repr。"""

from dataclasses import dataclass, field
from decimal import Decimal
import os

from dotenv import load_dotenv

from config import PROJECT_ROOT

# 配置层的能力/高峰人民币价格目录；业务逻辑不写死模型或汇率。
MODEL_PRICES = {'deepseek-flash': ('0.04', '2', '8'), 'deepseek-v4-pro': ('0.30', '9', '27')}
PROMPT_VERSION = 'topic-prompt-v1'
SCHEMA_VERSION = 'topic-schema-v1'
ANALYSIS_VERSION = 'topic-analysis-v1'


@dataclass(frozen=True)
class AISettings:
    """价格均以百万 Token 为单位；外币价必须显式提供汇率。"""

    api_key: str = field(default='', repr=False)
    model: str = 'deepseek-flash'
    output_mode: str = 'strict'
    price_currency: str = 'CNY'
    input_hit_price: Decimal = Decimal('0.04')
    input_miss_price: Decimal = Decimal('2')
    output_price: Decimal = Decimal('8')
    cny_per_unit: Decimal = Decimal('1')
    price_version: str = 'deepseek-2026-11-01-peak-conservative'
    monthly_budget_cny: Decimal = Decimal('100')
    max_output_tokens: int = 6000
    max_request_bytes: int = 65536
    max_attempts: int = 3
    max_candidates: int = 10

    def validate(self) -> None:
        """配置不可信或不完整时在付费请求前失败，不影响原有排行功能。"""
        if self.model not in MODEL_PRICES or self.output_mode not in ('strict', 'json_object'):
            raise ValueError('模型能力未核对或结构输出模式无效，请检查 AI 配置')
        values = (self.input_hit_price, self.input_miss_price, self.output_price, self.cny_per_unit,
                  self.monthly_budget_cny)
        if any(not value.is_finite() or value <= 0 for value in values):
            raise ValueError('AI 价格、汇率及月预算必须为有限正数')
        if (not self.price_version.strip() or not self.price_currency.strip()
                or not 1 <= self.max_output_tokens <= 12000
                or not 4096 <= self.max_request_bytes <= 131072
                or not 1 <= self.max_attempts <= 3 or not 1 <= self.max_candidates <= 10):
            raise ValueError('AI 版本、输入/输出限制或调用数量配置无效')
        if self.price_currency == 'CNY' and self.cny_per_unit != 1:
            raise ValueError('人民币单价的换算系数必须为 1')


def load_ai_settings() -> AISettings:
    """环境变量优先；未配置密钥仍可查看历史，不能发送付费请求。"""
    load_dotenv(PROJECT_ROOT / '.env', override=False)
    model = os.getenv('DEEPSEEK_MODEL', 'deepseek-flash').strip()
    prices = MODEL_PRICES.get(model, ('0', '0', '0'))
    currency = os.getenv('AI_PRICE_CURRENCY', 'CNY').upper().strip()
    price_names = ('AI_INPUT_HIT_PRICE', 'AI_INPUT_MISS_PRICE', 'AI_OUTPUT_PRICE')
    if currency != 'CNY' and (not os.getenv('AI_CNY_PER_CURRENCY_UNIT')
                              or any(not os.getenv(name) for name in price_names)):
        raise ValueError('外币价格必须完整配置单价和人民币汇率，不能自动套用人民币价格')
    try:
        settings = AISettings(
            api_key=os.getenv('DEEPSEEK_API_KEY', '').strip(), model=model,
            output_mode=os.getenv('AI_OUTPUT_MODE', 'strict').strip(), price_currency=currency,
            input_hit_price=Decimal(os.getenv(price_names[0], prices[0])),
            input_miss_price=Decimal(os.getenv(price_names[1], prices[1])),
            output_price=Decimal(os.getenv(price_names[2], prices[2])),
            cny_per_unit=Decimal(os.getenv('AI_CNY_PER_CURRENCY_UNIT', '1') if currency == 'CNY'
                                 else os.environ['AI_CNY_PER_CURRENCY_UNIT']),
            price_version=os.getenv('AI_PRICE_VERSION', 'deepseek-2026-11-01-peak-conservative'),
            monthly_budget_cny=Decimal(os.getenv('AI_MONTHLY_BUDGET_CNY', '100')),
            max_output_tokens=int(os.getenv('AI_MAX_OUTPUT_TOKENS', '6000')),
            max_attempts=int(os.getenv('AI_MAX_ATTEMPTS', '3')),
            max_candidates=int(os.getenv('AI_MAX_CANDIDATES', '10')),
        )
        settings.validate()
        return settings
    except (ArithmeticError, ValueError):
        raise ValueError('AI 模型、单价、汇率或预算配置无效，请检查 .env / 环境变量') from None
