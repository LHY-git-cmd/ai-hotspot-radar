# 模块设计

> 审计基准：2026-11-06（北京时间），当前工作区源码与默认数据库 v6。[架构总入口](../ARCHITECTURE.md)。已实现不等于已完成生产稳定性验证。

## 模块地图

| 模块 | 位置 | 实现状态 |
| --- | --- | --- |
| 页面与导航 | app.py / ai_page.py / pages/ | 已实现；后续制作区占位 |
| 统一模型与规范化 | models.py / services/normalization.py | 已实现 |
| 公开采集适配 | collectors/ | 已实现；仅两个来源 |
| 刷新与热点持久化 | services/refresh.py / database/store.py | 已实现 |
| 评分与排行 | services/scoring*.py / trends.py / recalculate.py / ranking.py | 已实现；启发式且未经发布效果校准 |
| AI 选题分析 | services/ai/analyzer.py / schemas.py / prompts.py | 已实现；无自动网页研究 |
| AI 执行与费用 | services/ai/base.py / config.py / executor.py / cost_tracker.py / database/ai_store.py | 已实现；非最终账单核验服务 |
| 制作任务与审计 | services/production/project_service.py / action_service.py | 已实现；状态不生成内容 |
| 通用内容版本 | services/production/version_service.py / database/production_store.py | 已实现；完整制作业务部分实现 |
| 研究计划与查询 | services/research/service.py / schemas.py / queries.py | 已实现；确认与联网分离 |
| 搜索与来源快照 | services/research/base.py / tavily.py / service.py / database/research_store.py | 已实现；无自动重试或持续采集 |
| 材料选窗与时间判定 | services/research/materials.py / temporal.py / evidence_contract.py | 已实现；区域与时间识别含启发式限制 |
| 证据校验与存储 | services/research/quality.py / evidence_contract.py / database/research_store.py | 已实现；生产不授 verified，真实性审核部分实现 |
| 研究报告 | services/research/report_*.py | 已实现；非自由写作式研究报告 |
| 人工确认与制作门禁 | services/research/report_confirmation.py / report_service.py / guards.py | 已实现；不是多用户身份认证 |
| 失败诊断 | services/research/diagnostics.py / database/research_store.py | 已实现；诊断失败不改变主调用结算 |
| 迁移与数据库基础 | database/*migration*.py / store.py | 已实现；审计未执行迁移 |

## 接口与依赖

### 1 页面与导航

目录：`app.py / ai_page.py / pages/`。状态：**已实现；后续制作区占位**。

- 输入：用户表单、按钮、侧栏选择及 Store 查询结果。
- 输出：页面展示、确认动作 ID、对服务的显式请求。
- 依赖：Store、各应用服务、Streamlit。

- 核心接口：[app.py · main](../../app.py#L235)；[app.py · show_dashboard](../../app.py#L161)；[ai_page.py · show_ai_page](../../ai_page.py#L222)；[pages/production.py · show_production_page](../../pages/production.py#L160)；[pages/research.py · show_research](../../pages/research.py#L324)。

- 相关测试：[tests/test_app.py](../../tests/test_app.py#L1)；[tests/test_phase2_app.py](../../tests/test_phase2_app.py#L1)；[tests/test_ai_page.py](../../tests/test_ai_page.py#L1)；[tests/test_production_page.py](../../tests/test_production_page.py#L1)；[tests/test_research_page.py](../../tests/test_research_page.py#L1)。

### 2 统一模型与规范化

目录：`models.py / services/normalization.py`。状态：**已实现**。

- 输入：API 字段、URL、标题、HTML 与时间。
- 输出：Hotspot、UTC 时间、可空指标、保守去重键与纯文本。
- 依赖：Python 标准库。

- 核心接口：[models.py · Hotspot](../../models.py#L38)；[models.py · CollectionResult](../../models.py#L56)；[services/normalization.py · normalize_url](../../services/normalization.py#L15)；[services/normalization.py · normalize_title](../../services/normalization.py#L10)；[services/normalization.py · plain_text](../../services/normalization.py#L73)。

- 相关测试：[tests/test_normalization.py](../../tests/test_normalization.py#L1)；[tests/test_collectors.py](../../tests/test_collectors.py#L1)；[tests/test_store.py](../../tests/test_store.py#L1)。

### 3 公开采集适配

目录：`collectors/`。状态：**已实现；仅两个来源**。

- 输入：可选 GitHub Token、采集时间及 HN 样本大小。
- 输出：CollectionResult，含 Hotspot 列表及 warnings。
- 依赖：requests、统一模型、规范化。

- 核心接口：[collectors/http.py · get_json](../../collectors/http.py#L12)；[collectors/github.py · collect](../../collectors/github.py#L12)；[collectors/hacker_news.py · collect](../../collectors/hacker_news.py#L31)。

- 相关测试：[tests/test_collectors.py](../../tests/test_collectors.py#L1)；[tests/test_phase2_refresh.py](../../tests/test_phase2_refresh.py#L1)。

### 4 刷新与热点持久化

目录：`services/refresh.py / database/store.py`。状态：**已实现**。

- 输入：来源到采集函数映射、周期 ID、统一记录。
- 输出：热点、来源快照、采集运行与逐来源统计。
- 依赖：采集器、HotspotStore、评分重算。

- 核心接口：[services/refresh.py · refresh_sources](../../services/refresh.py#L18)；[database/store.py · HotspotStore.save](../../database/store.py#L58)；[database/store.py · HotspotStore.record_failure](../../database/store.py#L170)。

- 相关测试：[tests/test_refresh.py](../../tests/test_refresh.py#L1)；[tests/test_store.py](../../tests/test_store.py#L1)；[tests/test_snapshots.py](../../tests/test_snapshots.py#L1)；[tests/test_phase2_refresh.py](../../tests/test_phase2_refresh.py#L1)。

### 5 评分与排行

目录：`services/scoring*.py / trends.py / recalculate.py / ranking.py`。状态：**已实现；启发式且未经发布效果校准**。

- 输入：热点、同来源对象快照、时间和评分规则。
- 输出：双评分、综合分、维度依据、趋势、分类和排序。
- 依赖：HotspotStore、规范化、scoring_rules。

- 核心接口：[services/trends.py · calculate_trend](../../services/trends.py#L20)；[services/scoring.py · score_hotspot](../../services/scoring.py#L58)；[services/recalculate.py · recalculate_scores](../../services/recalculate.py#L12)；[services/ranking.py · rank_items](../../services/ranking.py#L34)；[services/ranking.py · score_needs_refresh](../../services/ranking.py#L19)。

- 相关测试：[tests/test_scoring.py](../../tests/test_scoring.py#L1)；[tests/test_phase2_refresh.py](../../tests/test_phase2_refresh.py#L1)；[tests/test_phase2_app.py](../../tests/test_phase2_app.py#L1)。

### 6 AI 选题分析

目录：`services/ai/analyzer.py / schemas.py / prompts.py`。状态：**已实现；无自动网页研究**。

- 输入：本地热点标题摘要、真实观测、已存评分、动作 ID 和费用确认。
- 输出：结构化解读、恰好三个角度、analysis 与 video_ideas。
- 依赖：AIStore、Provider、共用执行器、Schema。

- 核心接口：[services/ai/analyzer.py · Analyzer.materials](../../services/ai/analyzer.py#L28)；[services/ai/analyzer.py · Analyzer.fingerprint](../../services/ai/analyzer.py#L53)；[services/ai/analyzer.py · Analyzer.candidates](../../services/ai/analyzer.py#L63)；[services/ai/analyzer.py · Analyzer.analyze](../../services/ai/analyzer.py#L85)。

- 相关测试：[tests/test_ai_analyzer.py](../../tests/test_ai_analyzer.py#L1)；[tests/test_ai_provider.py](../../tests/test_ai_provider.py#L1)；[tests/test_ai_page.py](../../tests/test_ai_page.py#L1)；[tests/test_ai_safety.py](../../tests/test_ai_safety.py#L1)。

### 7 AI 执行与费用

目录：`services/ai/base.py / config.py / executor.py / cost_tracker.py / database/ai_store.py`。状态：**已实现；非最终账单核验服务**。

- 输入：消息、配置、预算、单次请求及 Provider 用量。
- 输出：逐次调用账本、估算费用、未知预占、分析状态。
- 依赖：DeepSeek REST、SQLite、Decimal。

- 核心接口：[services/ai/base.py · Provider](../../services/ai/base.py#L50)；[services/ai/deepseek_client.py · DeepSeekProvider.complete](../../services/ai/deepseek_client.py#L40)；[services/ai/executor.py · execute_attempts](../../services/ai/executor.py#L12)；[services/ai/cost_tracker.py · reservation_units](../../services/ai/cost_tracker.py#L43)；[database/ai_store.py · AIStore.reserve_attempt](../../database/ai_store.py#L96)。

- 相关测试：[tests/test_ai_provider.py](../../tests/test_ai_provider.py#L1)；[tests/test_ai_budget.py](../../tests/test_ai_budget.py#L1)；[tests/test_ai_safety.py](../../tests/test_ai_safety.py#L1)。

### 8 制作任务与审计

目录：`services/production/project_service.py / action_service.py`。状态：**已实现；状态不生成内容**。

- 输入：选题 ID、任务名、备注、人工目标状态。
- 输出：制作任务、状态及同事务操作审计。
- 依赖：ProductionStore、research.guards。

- 核心接口：[services/production/project_service.py · ProjectService.create](../../services/production/project_service.py#L35)；[services/production/project_service.py · ProjectService._transition](../../services/production/project_service.py#L77)；[services/production/action_service.py · record_action](../../services/production/action_service.py#L18)。

- 相关测试：[tests/test_production_service.py](../../tests/test_production_service.py#L1)；[tests/test_production_store.py](../../tests/test_production_store.py#L1)；[tests/test_production_page.py](../../tests/test_production_page.py#L1)。

### 9 通用内容版本

目录：`services/production/version_service.py / database/production_store.py`。状态：**已实现；完整制作业务部分实现**。

- 输入：project、content_type、object_key、JSON 内容、来源与恢复目标。
- 输出：独立对象版本序列、恢复追加与审计。
- 依赖：制作事务、研究门禁、报告专用服务。

- 核心接口：[services/production/version_service.py · VersionService.create](../../services/production/version_service.py#L28)；[services/production/version_service.py · VersionService.restore](../../services/production/version_service.py#L61)；[database/production_store.py · ProductionStore.insert_version](../../database/production_store.py#L105)。

- 相关测试：[tests/test_production_versions.py](../../tests/test_production_versions.py#L1)；[tests/test_research_workflow.py](../../tests/test_research_workflow.py#L1)；[tests/test_research_report_persistence.py](../../tests/test_research_report_persistence.py#L1)。

### 10 研究计划与查询

目录：`services/research/service.py / schemas.py / queries.py`。状态：**已实现；确认与联网分离**。

- 输入：制作选题背景、研究目标、问题、日期、关键词、可选 query override。
- 输出：计划版本、版本确认和最终 query。
- 依赖：VersionService、计划 Schema、AI 执行器。

- 核心接口：[services/research/service.py · ResearchService.generate_plan](../../services/research/service.py#L190)；[services/research/service.py · ResearchService.save_plan](../../services/research/service.py#L62)；[services/research/service.py · ResearchService.confirm_plan](../../services/research/service.py#L69)；[services/research/queries.py · build_query](../../services/research/queries.py#L7)。

- 相关测试：[tests/test_research_workflow.py](../../tests/test_research_workflow.py#L1)；[tests/test_research_page.py](../../tests/test_research_page.py#L1)；[tests/test_research_quality.py](../../tests/test_research_quality.py#L1)。

### 11 搜索与来源快照

目录：`services/research/base.py / tavily.py / service.py / database/research_store.py`。状态：**已实现；无自动重试或持续采集**。

- 输入：当前已确认计划、搜索动作 ID、配额继续选项。
- 输出：搜索运行/请求、credits、来源快照与问题关联。
- 依赖：Tavily REST、query 构造、ResearchStore。

- 核心接口：[services/research/base.py · SearchProvider](../../services/research/base.py#L49)；[services/research/tavily.py · TavilyProvider](../../services/research/tavily.py#L31)；[services/research/service.py · ResearchService.search](../../services/research/service.py#L100)；[database/research_store.py · ResearchStore.save_sources](../../database/research_store.py#L59)。

- 相关测试：[tests/test_research_provider.py](../../tests/test_research_provider.py#L1)；[tests/test_research_workflow.py](../../tests/test_research_workflow.py#L1)；[tests/test_research_quality.py](../../tests/test_research_quality.py#L1)。

### 12 材料选窗与时间判定

目录：`services/research/materials.py / temporal.py / evidence_contract.py`。状态：**已实现；区域与时间识别含启发式限制**。

- 输入：原始来源 text/snippet、问题关键词、研究日期与输入预算。
- 输出：可见窗口、覆盖缺口、来源 manifest/hash、时间性质。
- 依赖：纯 Python、规范化及质量契约。

- 核心接口：[services/research/materials.py · select_windows](../../services/research/materials.py#L109)；[services/research/temporal.py · classify_temporal](../../services/research/temporal.py#L122)；[services/research/evidence_contract.py · build_manifest](../../services/research/evidence_contract.py#L53)；[services/research/evidence_contract.py · model_materials](../../services/research/evidence_contract.py#L77)。

- 相关测试：[tests/test_research_materials.py](../../tests/test_research_materials.py#L1)；[tests/test_research_temporal.py](../../tests/test_research_temporal.py#L1)；[tests/test_research_pure_contract_integration.py](../../tests/test_research_pure_contract_integration.py#L1)。

### 13 证据校验与存储

目录：`services/research/quality.py / evidence_contract.py / database/research_store.py`。状态：**已实现；生产不授 verified，真实性审核部分实现**。

- 输入：最新搜索、冻结可见窗口、模型候选及逐字引用。
- 输出：程序分类、时间与缺口、证据和物理引用、analysis JSON。
- 依赖：共用执行器、选窗、时间、SQLite 事务。

- 核心接口：[services/research/service.py · ResearchService.organize_evidence](../../services/research/service.py#L197)；[services/research/quality.py · assess_batch](../../services/research/quality.py#L463)；[database/research_store.py · ResearchStore.verify_evidence_binding](../../database/research_store.py#L231)；[database/research_store.py · ResearchStore.insert_evidence](../../database/research_store.py#L281)；[database/research_store.py · ResearchStore.evidence](../../database/research_store.py#L157)。

- 相关测试：[tests/test_research_quality_policy.py](../../tests/test_research_quality_policy.py#L1)；[tests/test_research_quality_integration.py](../../tests/test_research_quality_integration.py#L1)；[tests/test_research_quality_persistence.py](../../tests/test_research_quality_persistence.py#L1)。

### 14 研究报告

目录：`services/research/report_*.py`。状态：**已实现；非自由写作式研究报告**。

- 输入：当前确认计划、最新搜索与成功 v3 证据池，表达树和预期前版本。
- 输出：程序渲染的 ReportEnvelopeV3、追加版本、校验回执。
- 依赖：ResearchStore、纯报告校验器、AIStore、执行器。

- 核心接口：[services/research/report_evidence.py · read_bundle](../../services/research/report_evidence.py#L16)；[services/research/report_contract.py · candidate_schema](../../services/research/report_contract.py#L36)；[services/research/report_validation.py · validate_candidate](../../services/research/report_validation.py#L61)；[services/research/report_service.py · ReportService.generate](../../services/research/report_service.py#L142)；[services/research/report_service.py · ReportService.save](../../services/research/report_service.py#L115)。

- 相关测试：[tests/test_research_report_contract.py](../../tests/test_research_report_contract.py#L1)；[tests/test_research_report_integration.py](../../tests/test_research_report_integration.py#L1)；[tests/test_research_report_persistence.py](../../tests/test_research_report_persistence.py#L1)。

### 15 人工确认与制作门禁

目录：`services/research/report_confirmation.py / report_service.py / guards.py`。状态：**已实现；不是多用户身份认证**。

- 输入：本地交互审核、具体报告版本、hash、动作 ID。
- 输出：报告确认行、审计回执与后续制作绑定。
- 依赖：本地内存能力、当前证据池、制作事务。

- 核心接口：[services/research/report_confirmation.py · LocalReportReviewSession.reviewed](../../services/research/report_confirmation.py#L22)；[services/research/report_service.py · ReportService.confirm](../../services/research/report_service.py#L217)；[services/research/report_service.py · require_confirmed_report](../../services/research/report_service.py#L59)；[services/research/guards.py · version_guard](../../services/research/guards.py#L59)。

- 相关测试：[tests/test_research_report_persistence.py](../../tests/test_research_report_persistence.py#L1)；[tests/test_research_workflow.py](../../tests/test_research_workflow.py#L1)；[tests/test_research_page.py](../../tests/test_research_page.py#L1)。

### 16 失败诊断

目录：`services/research/diagnostics.py / database/research_store.py`。状态：**已实现；诊断失败不改变主调用结算**。

- 输入：固定错误码、结构路径、候选结构与尝试 ID。
- 输出：脱敏且受限大小的诊断，不保留自由文本回放。
- 依赖：执行器回调、v6 诊断表。

- 核心接口：[services/research/diagnostics.py · ResearchValidationError](../../services/research/diagnostics.py#L25)；[services/research/diagnostics.py · rejected_structure](../../services/research/diagnostics.py#L35)；[database/research_store.py · ResearchStore.save_diagnostic](../../database/research_store.py#L114)。

- 相关测试：[tests/test_research_quality.py](../../tests/test_research_quality.py#L1)；[tests/test_research_quality_persistence.py](../../tests/test_research_quality_persistence.py#L1)；[tests/test_research_report_integration.py](../../tests/test_research_report_integration.py#L1)。

### 17 迁移与数据库基础

目录：`database/*migration*.py / store.py`。状态：**已实现；审计未执行迁移**。

- 输入：文件路径、PRAGMA user_version 与旧结构。
- 输出：备份、事务升级、短连接和外键启用。
- 依赖：sqlite3、文件系统。

- 核心接口：[database/migrations.py · migrate](../../database/migrations.py#L21)；[database/store.py · HotspotStore._connection](../../database/store.py#L47)；[database/production_store.py · ProductionStore.transaction](../../database/production_store.py#L21)。

- 相关测试：[tests/test_snapshots.py](../../tests/test_snapshots.py#L1)；[tests/test_ai_migration.py](../../tests/test_ai_migration.py#L1)；[tests/test_production_store.py](../../tests/test_production_store.py#L1)；[tests/test_research_migration.py](../../tests/test_research_migration.py#L1)；[tests/test_research_quality.py](../../tests/test_research_quality.py#L1)。

## 核心接口的语义限制

- `refresh_sources(store, collectors, cycle_id, now)` 逐来源隔离；同周期完成结果可重用，评分失败不回滚来源快照。
- `Analyzer.analyze(hotspot_id, action_id, force, spending_cap_units, expected_cache_key)` 支持材料确认和费用上界；自动候选最多 10 条，人工仍可选择已有热点。
- `ProjectService.create(idea_id, name, notes)` 仅要求选题存在且没有未归档任务，不要求选题状态必须是 `to_produce`。同选题的 `completed` 项目仍算有效任务；归档后才可新建。
- 制作状态允许人工选择多个正常阶段，不是只能逐级推进的严格线性状态机；进入 `scripting/storyboarding/assets/editing/completed` 都要求有效已确认报告。
- `VersionService.create(..., content_type='research', object_key='report')` 明确拒绝；报告创建必须通过专用服务。`restore` 对报告会在原连接中委托报告服务重新核验和发布。
- 研究写入统一禁止暂停/归档状态；制作基本信息的普通编辑仅禁止归档，暂停时仍可修改名称和备注。两者边界不可混写。
- `ResearchService.save_plan` 可由服务调用者保存人工计划；当前页面需要已有计划后才能编辑。计划生成使用 AI，但本地计划保存/确认不需要调用 AI。
- `ResearchService.search(..., allow_unknown_quota, expected_plan)` 要求最新计划已确认，支持检查页面未保存修改。读取配额本身也是 Tavily 外部请求。
- `organize_evidence` 只允许最新有效搜索；候选总数 ≤10、每题 ≤2，允许 0 条但无证据题必须有缺口；整批不合格时不会留下部分成功证据。
- `ReportService.save(..., expected_previous_report_version_id)` 必须显式携带预期前版本，发布执行 CAS；人工修改只编辑引用/模板组织树，不直接编辑正文数值或最终等级。
- `ReportService.confirm(..., intent)` 需要本地交互签发的注册对象，普通字典或 `confirmed=true` 不具备确认权限；确认只说明接受当前报告，不能提升证据等级。

依据分别为上述模块核心接口；更细的事务顺序见 [数据流](DATA_FLOW.md)，约束与状态枚举见 [数据库设计](DATABASE_DESIGN.md)。

## 部分实现与规划边界

`CONTENT_TYPES` 已定义 `research/script/storyboard/asset/editing_guide`；通用版本表能保存这些对象，但不代表已实现脚本生成、分镜编辑、素材资产管理或剪辑指导。页面后四类明确显示“尚未开发”，不得把类型枚举和准入门禁当作完整业务能力。

历史热点快照、来源差异与报告版本已经实现；跨领域机会分析、发布记录、实际传播指标和推荐反馈尚无完整业务服务及数据库表。持续后台监测、Product Hunt/Reddit/社交来源、团队协作及 SaaS 收费仅属于产品愿景。

## 后续维护时的依赖注意事项

页面直读 Store、研究服务直写 SQL、ResearchStore 依赖质量规则，属于当前事实。报告读取、保存、确认与准入都复核当前依据；不得新增一个只查确认行或只看项目状态的旁路。重复校验中的服务层验证与写事务内验证是有意的竞争与完整性保护，不应直接当成可删除的重复代码。

缓存/幂等、错误结算、版本历史和人工确认属于跨模块协议；改动时应同步维护 AI、数据库、流程与测试文档。具体问题与建议见 [审计报告](../ARCHITECTURE_AUDIT_REPORT.md)。
