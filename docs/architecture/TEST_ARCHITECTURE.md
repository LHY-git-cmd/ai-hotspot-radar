# 测试与质量保障架构

> 审计基准：2026-11-06（北京时间），当前工作区源码与默认数据库 v6。[架构总入口](../ARCHITECTURE.md)。已实现不等于已完成生产稳定性验证。

## 发现与分层

`pytest.ini` 设置 `testpaths=tests`、`addopts=-q`。本次静态 AST 清点：33 个 `test_*.py` 模块，289 个模块级 `test_` 函数定义；参数化会展开为更多测试项，不能把函数数量当作 pytest 收集项数。

测试使用真实临时 SQLite、Mock Provider/HTTP、monkeypatch、故障注入和 Streamlit AppTest。仓库没有单独的 unit/integration 目录或对应 marker 分组，以下按实际责任划分，部分文件跨层覆盖。

| 分层 | 测试文件 | 主要覆盖 |
| --- | --- | --- |
| 规范化与采集 | [tests/test_normalization.py](../../tests/test_normalization.py#L1)<br>[tests/test_collectors.py](../../tests/test_collectors.py#L1)<br>[tests/test_refresh.py](../../tests/test_refresh.py#L1) | URL/标题、HTML、字段缺失、超时/认证/限流、有限样本、来源隔离 |
| 热点持久化与评分 | [tests/test_store.py](../../tests/test_store.py#L1)<br>[tests/test_snapshots.py](../../tests/test_snapshots.py#L1)<br>[tests/test_scoring.py](../../tests/test_scoring.py#L1)<br>[tests/test_phase2_refresh.py](../../tests/test_phase2_refresh.py#L1) | 唯一约束、跨来源指标隔离、周期幂等、快照、增长、缺失降级、评分并发输入检查 |
| 基础与 AI 页面 | [tests/test_app.py](../../tests/test_app.py#L1)<br>[tests/test_phase2_app.py](../../tests/test_phase2_app.py#L1)<br>[tests/test_ai_page.py](../../tests/test_ai_page.py#L1) | AppTest 导航、筛选、分页、重算、费用确认、单条/批量与零调用 |
| AI 适配与账本 | [tests/test_ai_provider.py](../../tests/test_ai_provider.py#L1)<br>[tests/test_ai_analyzer.py](../../tests/test_ai_analyzer.py#L1)<br>[tests/test_ai_budget.py](../../tests/test_ai_budget.py#L1)<br>[tests/test_ai_safety.py](../../tests/test_ai_safety.py#L1) | 结构输出、请求体、材料缓存、有限重试、Decimal、北京时间账期、并发预占、未知费用和重启 |
| 迁移 | [tests/test_ai_migration.py](../../tests/test_ai_migration.py#L1)<br>[tests/test_production_store.py](../../tests/test_production_store.py#L1)<br>[tests/test_research_migration.py](../../tests/test_research_migration.py#L1) | 版本升级、旧行保留、备份失败、DDL 故障回滚、跨项目外键；另有 snapshots/quality 的 v2/v6 场景 |
| 制作任务与版本 | [tests/test_production_service.py](../../tests/test_production_service.py#L1)<br>[tests/test_production_versions.py](../../tests/test_production_versions.py#L1)<br>[tests/test_production_page.py](../../tests/test_production_page.py#L1) | 任务唯一、人工状态、暂停归档、并发版本、恢复追加、审计失败回滚和页面无 API |
| 研究 Provider 与流程 | [tests/test_research_provider.py](../../tests/test_research_provider.py#L1)<br>[tests/test_research_workflow.py](../../tests/test_research_workflow.py#L1)<br>[tests/test_research_page.py](../../tests/test_research_page.py#L1)<br>[tests/test_research_quality.py](../../tests/test_research_quality.py#L1) | Tavily 参数、配额未知、搜索/提取、来源快照、计划变更、报告门禁、诊断与页面 |
| 纯材料与质量契约 | [tests/test_research_materials.py](../../tests/test_research_materials.py#L1)<br>[tests/test_research_temporal.py](../../tests/test_research_temporal.py#L1)<br>[tests/test_research_quality_policy.py](../../tests/test_research_quality_policy.py#L1)<br>[tests/test_research_pure_contract_integration.py](../../tests/test_research_pure_contract_integration.py#L1) | 相关段落、Unicode 位置、表格上下文、时间性质、来源依赖、拒绝越权、无 IO 纯函数集成 |
| 证据服务与持久化 | [tests/test_research_quality_integration.py](../../tests/test_research_quality_integration.py#L1)<br>[tests/test_research_quality_persistence.py](../../tests/test_research_quality_persistence.py#L1) | 真实服务调用链与 Mock HTTP、v3 Schema、冻结输入、SQL/JSON 投影、事务回滚、失败仍结算 |
| 报告契约与集成 | [tests/test_research_report_contract.py](../../tests/test_research_report_contract.py#L1)<br>[tests/test_research_report_integration.py](../../tests/test_research_report_integration.py#L1)<br>[tests/test_research_report_persistence.py](../../tests/test_research_report_persistence.py#L1) | 受限表达树、等级时间继承、缺口保留、版本 CAS、意图权限、伪造阻断、发布/确认原子性 |

## 测试隔离

`tests/conftest.py::isolated_configuration` 为 autouse fixture：

1. 替换 dotenv 及两个配置模块的 `load_dotenv`，避免测试读取真实配置。
2. 清理 AI/DeepSeek/Tavily/GitHub 相关环境覆盖值，设置临时数据库默认路径。
3. 阻断 `requests.sessions.Session.request`，外部调用必须显式 Mock。
4. 包装 sqlite3.connect，拒绝连接项目 `data/`，支持对 file URI 路径检查。

这些保护作用于 fixture 执行期间，不是对测试收集阶段、任意新网络库或外部脚本的全局沙箱。部分旧回归夹具将明确 Mock 的 legacy 输入适配为 v3；只在 `tests/research_support.py` 使用，不是生产兼容旁路。测试中的私有审核接缝也不构成生产 verified 入口。

依据：[tests/conftest.py · isolated_configuration](../../tests/conftest.py#L7)、[tests/research_support.py · candidate_from_legacy_fixture](../../tests/research_support.py#L40)、[tests/test_research_quality_policy.py · test_test_only_review_gate_is_not_public_json_authority](../../tests/test_research_quality_policy.py#L224)。

## 单元与纯函数测试

规范化、评分、趋势、query、费用、选窗、时间、质量及报告表达树分别有边界断言；覆盖缺失值不是零、不同来源不混算、观察时间限制、字节预算与 Unicode 坐标、错误日期/未来预测等。纯函数契约集成用阻断文件、socket、数据库和环境读取的方法证明该路径无 IO。

证据策略包含“单官方来源仍单源”“同文转载不算独立”“生产输入不能授 verified”；报告契约包含禁止任意 text/value/source/actor/confirmed 字段、证据与缺口全覆盖、跨题与跨级模板拒绝。这些程序断言不代表现实语义与来源真实性已获人工验证。

依据：[tests/test_scoring.py](../../tests/test_scoring.py#L1)、[tests/test_research_materials.py](../../tests/test_research_materials.py#L1)、[tests/test_research_temporal.py](../../tests/test_research_temporal.py#L1)、[tests/test_research_pure_contract_integration.py · test_three_pure_modules_do_not_access_io_or_environment](../../tests/test_research_pure_contract_integration.py#L45)、[tests/test_research_report_contract.py](../../tests/test_research_report_contract.py#L1)。

## 集成、迁移与故障注入

服务测试通过真实 Store/SQLite 事务连接研究、质量、报告及门禁；Provider 或 HTTP 响应由 Mock 提供。覆盖材料在模型请求期间变化、跨项目来源/版本、SQL/JSON 被破坏、未知费用、数据库错误、审计写入失败等路径。

并发测试主要使用线程和多连接验证预算、任务唯一及版本编号；不是高负载、多主机或真实进程崩溃测试。迁移测试构造临时旧库，验证备份、回滚、旧 ID/行内容保留与重复打开幂等；本次没有重跑这些迁移，也没有在正式库执行。

依据：[tests/test_ai_budget.py · test_atomic_reservation_cannot_be_bypassed_by_two_connections](../../tests/test_ai_budget.py#L51)、[tests/test_production_versions.py · test_concurrent_versions_are_unique_and_gapless](../../tests/test_production_versions.py#L62)、[tests/test_research_quality_persistence.py · test_mid_transaction_failure_preserves_old_rows_and_result](../../tests/test_research_quality_persistence.py#L103)、[tests/test_research_report_persistence.py · test_real_sqlite_fault_rolls_back_whole_report_or_confirmation](../../tests/test_research_report_persistence.py#L26)、[tests/test_research_quality.py · test_v6_migration_failure_rolls_back](../../tests/test_research_quality.py#L218)。

## 页面测试

AppTest 覆盖主导航、查询分页、状态、分析费用确认、计划编辑/保存/确认、query 预览与实际调用一致性、报告确认及进入脚本状态。页面重跑/查看历史不应重复调用 API。

AppTest 不能替代真实浏览器下的布局、响应式、可访问性、长任务等待和交互确认体验验收。历史真实验证报告明确尚未完成完整浏览器确认及视觉检查。

## 历史结果与本次检查

| 证据 | 实际能说明的内容 | 不能说明的内容 |
| --- | --- | --- |
| 2026-11-05 `full-acceptance.xml` | 本次读取既有 JUnit XML：674 项、失败 0、错误 0、跳过 0，含 674 条 testcase；原报告为北京时间 14:22:34 开始 | 本次没有重新运行 674 项，不能当成本次测试结果或后续改动的保证 |
| `REPORT_VERIFY_V3_2026-11-05.md` | 历史真实 DeepSeek/Tavily 服务层成功案例，以及另一个材料结构敏感失败案例 | 不是本次 API 验收，也不是任意题材的成功率统计 |
| 本次只读 PRAGMA | 默认库 integrity_check=ok、foreign_key_check 无行；v6 表结构核对 | 不证明所有 JSON 语义、所有历史版本绑定或 UI 行为均正确 |
| 本次文档检查 | 链接、源码行号、文档结构、Mermaid 静态检查、实库对象清单、文件保护校验 | 不等于业务测试或真实浏览器/图形渲染验收 |

既有 XML 路径：[logs/phase4-2-1-4-c-b/full-acceptance.xml](../../logs/phase4-2-1-4-c-b/full-acceptance.xml#L1)；验收说明：[REPORT_PHASE4_2_1_4_C_B_IMPLEMENTATION.md](../../REPORT_PHASE4_2_1_4_C_B_IMPLEMENTATION.md#L1)。较早 230/365/545 等数字保留其阶段语境，不能覆盖最终历史记录。

## 仍未覆盖或不能确认的风险

- 不同真实来源结构下的提取、引用和事实字段填充稳定性；历史 Oracle 案例连续失败，不被 Mock 通过抵消。
- 现实事实真假、来源实际独立性、商业潜力与视频传播效果；自动化契约只证明规定范围的程序行为。
- 完整浏览器交互、长内容布局、移动屏、键盘/屏幕阅读器。
- 多进程并发、硬断电、磁盘损坏、系统级文件权限与备份恢复演练。
- 模型/搜索接口的未来变化、模型价格和 credits 计价变化。
- 多用户认证、租户隔离、支付与发布效果等未实现业务，没有对应生产能力测试。
- 未找到覆盖率报告或仓库内 CI 工作流；不提供未经测量的覆盖率百分比。
- autouse 请求阻断不是进程级网络隔离，新增客户端或收集阶段 IO 需要另外保护。

本次按文档审计范围不启动应用、不收集或重跑全套测试，避免触发导入副作用、真实配置读取、日志写入及重复验证。未来代码修改应优先选择相关用例，再依变更风险执行回归。
