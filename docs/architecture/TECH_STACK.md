# 技术栈与配置

> 基准：2026-11-06（北京时间）。[架构总入口](../ARCHITECTURE.md)。下表区分声明版本、本机安装结果和历史选择依据；未联网查询“最新版本”或供应商价格。

## 当前技术与使用证据

| 技术 | 当前版本或实现 | 实际用途与位置 | 选择依据 | 仍在使用 |
| --- | --- | --- | --- | --- |
| Python | 本项目 `.venv` 为 3.13.12 | 全部业务与 Streamlit 入口 | 首期计划选择 Python 3.13，并在该环境验收；未找到独立项目版本范围声明 | 是 |
| Streamlit | 固定且已安装 1.66.1 | `app.py`、`ai_page.py`、`pages/` 的本地中文界面；官方 AppTest | 首期计划明确采用；未找到与其他框架的正式对比结论 | 是 |
| SQLite / sqlite3 | 标准库；本机链接 SQLite 3.51.1；项目 Schema v6 | `database/` 的单文件持久化、事务、约束与备份 | 首期明确本地 SQLite、无 ORM/队列/额外后端框架；数据库约束用于去重 | 是 |
| requests | 固定且已安装 2.34.2 | GitHub、HN、DeepSeek、Tavily 的同步 REST 请求 | 首期计划直接使用；第三/四期沿用 REST，不增加模型或搜索 SDK | 是 |
| python-dotenv | 固定且已安装 1.2.4 | `config.load_settings`、`load_ai_settings` 加载项目根 `.env`，环境优先 | 首期与 README 明确采用环境配置、不把凭据写代码；没有独立选型比较 | 是 |
| jsonschema | 固定且已安装 4.26.0 | Draft202012Validator，校验选题、计划、证据候选与报告表达树 | README 与后续设计明确沿用环境已有包并列为直接依赖，不新增校验 API | 是 |
| pytest | 固定且已安装 9.2.0 | 测试发现、参数化、夹具、故障注入与回归 | 首期计划采用，后续验收报告沿用 | 是 |
| DeepSeek | `DeepSeekProvider` REST 实现 | 选题、研究计划、证据候选、报告组织结构 | 第三期与当前代码明确供应商实现；没有证据证明对所有替代供应商做过比较 | 是；本次未调用 |
| Tavily | `TavilyProvider` REST 实现 | `usage/search/extract`，网络搜索与正文提取 | 研究阶段计划明确接入且已有历史真实验收记录；本次未验证供应商当前能力 | 是；本次未调用 |
| 标准库 Decimal / zoneinfo | 随 Python 提供 | 精确金额单位与北京时间预算账期 | `cost_tracker` 注释明确防浮点误差和主机时区差异 | 是 |
| 标准库 ThreadPoolExecutor | 随 Python 提供 | HN 最多 6 个并发详情请求，稳定保留热门列表顺序 | 采集器注释说明控制等待及去重顺序 | 是 |
| hashlib / json / dataclasses / typing.Protocol | 随 Python 提供 | 材料指纹、快照完整性、JSON 契约、统一记录与可替换 Provider | 代码职责可证实；没有独立工具选型报告 | 是 |

版本证据：[requirements.txt](../../requirements.txt#L1) 及本次 `importlib.metadata` 只读检查；实现证据：[app.py](../../app.py#L1)、[collectors/http.py](../../collectors/http.py#L1)、[services/ai/deepseek_client.py](../../services/ai/deepseek_client.py#L1)、[services/research/tavily.py](../../services/research/tavily.py#L1)、[services/research/quality.py](../../services/research/quality.py#L1)、[services/ai/cost_tracker.py](../../services/ai/cost_tracker.py#L1)。选择依据：[docs/plan&report/PLAN.md](../plan%26report/PLAN.md#L1)、[docs/plan&report/PLAN_PHASE3.md](../plan%26report/PLAN_PHASE3.md#L1)、[docs/plan&report/PLAN_PHASE4_2_1.md](../plan%26report/PLAN_PHASE4_2_1.md#L1)、[REPORT_PHASE4_2_1_4_C_A_DESIGN.md](../../REPORT_PHASE4_2_1_4_C_A_DESIGN.md#L1)。

## Python 版本要求的证据边界

本机确认为 Python 3.13.12。已安装发行包元数据中，Streamlit 1.66.1 的 `Requires-Python` 是 `>=3.11`；其余四个直接依赖为 `>=3.10`。项目没有 `pyproject.toml`、`.python-version` 或等价项目级版本范围文件。

因此可以说“固定直接依赖中存在 Python ≥3.11 的门槛，历史验收使用 3.13.12”；不能说项目正式支持任意 Python 3.11+，也不能把运行环境版本当成经过定义的最低版本。Windows 字体、时区数据和传递依赖的完整跨平台兼容性不在本次运行验收范围。

## 配置管理

以下仅根据源码列出变量名与默认值，**不代表读取了 `.env` 或实际运行值**。

| 配置名 | 代码默认值 | 用途 |
| --- | --- | --- |
| `AI_RADAR_DB_PATH` | `data/hotspots.sqlite3` | 相对路径以项目根目录解析 |
| `GITHUB_TOKEN` | 空 | 可选 GitHub 认证 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek 请求认证，不记录值 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 当前模型目录中的模型 |
| `AI_OUTPUT_MODE` | `strict` | strict 工具结果；可显式选择 `json_object` |
| `AI_PRICE_CURRENCY` | `CNY` | 价格币种 |
| `AI_INPUT_HIT_PRICE` / `AI_INPUT_MISS_PRICE` / `AI_OUTPUT_PRICE` | 按代码模型目录 | 每百万 Token 输入缓存命中/未命中/输出单价 |
| `AI_CNY_PER_CURRENCY_UNIT` | 人民币模式为 1 | 外币金额换算；外币时须显式提供 |
| `AI_PRICE_VERSION` | `deepseek-2026-11-01-peak-conservative` | 保存计价配置版本快照 |
| `AI_MONTHLY_BUDGET_CNY` | 100 | 预算首次创建值；后续数据库设置优先 |
| `AI_MAX_OUTPUT_TOKENS` | 6000 | 模型输出上限；配置校验允许 1—12000 |
| `AI_MAX_ATTEMPTS` | 3 | 单分析最大 HTTP 尝试数，允许 1—3 |
| `AI_MAX_CANDIDATES` | 10 | 自动候选上限，允许 1—10 |
| `TAVILY_API_KEY` | 空 | Tavily 认证，不记录值 |

`max_request_bytes` 是 `AISettings` 的字段，默认 65536，允许 4096—131072；当前 `load_ai_settings` **没有读取对应环境变量**，不可凭字段名补造 `AI_MAX_REQUEST_BYTES` 配置入口。测试或程序调用可显式构造不同设置。

加载器使用 `load_dotenv(PROJECT_ROOT / '.env', override=False)`。搜索服务本身通过 `os.getenv` 取 Tavily 密钥，正常页面由主应用配置加载进入；独立服务调用需要调用方提供设置/环境或注入 Provider。AISettings/TavilyProvider 的密钥字段 `repr=False`，不应打印整个环境或 HTTP 头。

依据：[config.py · load_settings](../../config.py#L20)、[services/ai/config.py · AISettings](../../services/ai/config.py#L19)、[services/ai/config.py · load_ai_settings](../../services/ai/config.py#L54)、[services/research/service.py · ResearchService.search](../../services/research/service.py#L100)。

## HTTP 行为与资源限制

| 接口角色 | 当前连接/读取超时 | 并发、重试和重定向 |
| --- | --- | --- |
| 公开采集 HTTP | 15 / 15 秒 | 不自动重试；requests 默认重定向行为；HN 单轮最多 6 详情线程 |
| DeepSeek | 15 / 120 秒 | Provider 单次请求；执行器有限重试；禁重定向 |
| Tavily usage | 15 / 30 秒 | 单次请求、不重试、禁重定向 |
| Tavily search/extract | 15 / 65 秒 | 单次请求、不重试、禁重定向；extract 请求另设服务端 30 秒 |

研究计划最多 10 问；每题搜索最多 3 个结果；单轮最多提取 20 URL；新证据每题 ≤2、总计 ≤10。报告候选局部和全局上限见 [AI 架构](AI_ARCHITECTURE.md)，不要把 Prompt 的更小建议当作本地强制上限。

## 未使用或不能确认的技术

当前源码和直接依赖中没有单独 API 框架、ORM、模型 SDK、任务队列、向量检索、账号认证或订阅支付实现。未发现仓库内 CI 工作流配置和跨平台构建声明；这不排除仓库外有人工工具或部署设置。本次没有检查外部系统，不把缺失文件解释成外部系统不存在。

依赖固定直接版本，但没有完整传递依赖锁文件；包版本和模型价格长期维护问题见 [审计报告](../ARCHITECTURE_AUDIT_REPORT.md)。
