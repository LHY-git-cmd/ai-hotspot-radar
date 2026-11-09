# 项目架构审计报告

> 日期：2026-11-06（北京时间）。[架构总入口](ARCHITECTURE.md)。本次为只读架构审计与新增文档，不是代码修复、API 联调或全量测试任务。

## 审计范围与方法

- 实际项目：`E:\one\ai-hotspot-radar`。会话默认 `C:\Users\28565\.codex\visualizations\2026\11\05\01a1aaa5-09dc-74b1-ad9d-2f097b340e71` 不作为项目源码根目录。
- 以当前工作区为准，保留所有既有修改、未跟踪文件及旧阶段文档；不把 Git HEAD 当作唯一已实现范围。
- 审查目录、Python 源码/导入/符号、配置加载逻辑、五项依赖及发行包元数据、33 个测试入口及辅助样本、阶段设计/实施/验收报告、产品理想形态文档。
- 默认 SQLite 使用直接 `mode=ro&immutable=1`，检查无伴随日志文件后读取 schema 与聚合计数；不导入应用，不实例化 Store，不执行迁移或写库。
- 只读查询包括 sqlite_master、PRAGMA 结构/完整性/外键检查，以及按用途、版本、类别聚合；不输出研究原文、用户备注、API Key 或其他秘密。
- 中间脚本、基线与检查结果放系统临时目录，项目内只新增指定 Markdown；所有网络/API 请求次数为 0（本次未调用任何网络工具或业务客户端）。

## 实际架构总结

1. Python/Streamlit/SQLite 模块化单体，主导航三个页面，研究为制作详情内组件；同步请求，无后台持久任务系统。
2. 热点采集、规则评分和 AI 分析相互分离；AI 选题不修改 A/B 分，原始指标按来源保存。
3. 制作项目来源于 video_idea，有人工状态、追加审计、内容对象与版本；后续内容类型已有基础但业务占位。
4. 研究计划和报告复用 production_versions；模型分析和费用复用 topic_analyses/ai_analysis_runs，Tavily credits 单独记录。
5. 证据 v3 由模型提交候选、程序做引用/时间/质量判定；生产公开策略不授 verified。旧 v1/v2 保留可读，不直接授予新报告准入。
6. 报告 v3 是受限表达树与程序渲染，不是任意自由正文；发布检查当前依据和版本 CAS，人工确认需本地注册意图。
7. 后续制作状态和通用内容写入/恢复统一检查当前已确认报告；该机制不等同已经实现脚本生产或未来脚本逐句事实验证。
8. 当前库 v6，22 业务表、20 显式索引、19 触发器；本次 integrity_check=ok、foreign_key_check=0 行异常。源码声明表集合和字段顺序 22/22 一致。

## 交付文档

| 文档 | 交付内容 |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 定位、初衷、能力状态、架构与文档导航 |
| [SYSTEM_OVERVIEW.md](architecture/SYSTEM_OVERVIEW.md) | 目录树、运行结构、真实分层和依赖 |
| [MODULE_DESIGN.md](architecture/MODULE_DESIGN.md) | 17 个模块职责视图、核心符号、输入输出、依赖和测试 |
| [DATA_FLOW.md](architecture/DATA_FLOW.md) | A—F 六条链路、外部请求、事务和人工节点 |
| [DATABASE_DESIGN.md](architecture/DATABASE_DESIGN.md) | ER、22 张表实际 DDL、全部显式/自动约束索引、全部触发器及迁移 |
| [TECH_STACK.md](architecture/TECH_STACK.md) | 依赖/运行版本、使用位置、有证据的选择原因与配置边界 |
| [AI_ARCHITECTURE.md](architecture/AI_ARCHITECTURE.md) | 调用、Provider、Prompt、Schema、费用、重试、诊断和安全边界 |
| [TEST_ARCHITECTURE.md](architecture/TEST_ARCHITECTURE.md) | 测试分类、隔离、历史结果及盲区 |
| [ARCHITECTURE_AUDIT_REPORT.md](ARCHITECTURE_AUDIT_REPORT.md) | 审计事实、问题、验证边界与保护结果 |

## 已实现与愿景的区别

当前采集、评分、三个角度、制作基础、计划/搜索/证据/报告及确认门禁已落地；可信独立事实审核、完整制作链路和长期情报分析属于部分实现。后台持续监测、更多热点来源、完整脚本/分镜/素材业务、发布效果反馈、推荐校准、账号协作与订阅 API 服务仍属于计划实现。

依据详见架构入口能力矩阵和模块设计。静态代码证明实现存在，测试证明特定输入行为，真实历史报告证明某次运行；三者都不能直接证明长期稳定性或商业价值。

## 发现的问题与建议

优先级含义：P0 影响正确性、安全性或数据完整性且需优先处理；P1 影响后续开发、使用或维护；P2 为一般优化或未来边界提醒。

**本次未确认新的现存 P0 缺陷。** 这不是不存在 P0 的保证；审计未做动态攻击、并发压力、进程崩溃或全量历史 JSON 校验。以下静态风险和维护问题均只记录，未实施修复。

| 编号 | 级别 | 问题 |
| --- | --- | --- |
| A01 | P1 | README 与阶段记录不能直接作为当前行为说明 |
| A02 | P1 | SearchProvider 协议不完整 |
| A03 | P1 | 实际分层存在反向依赖与跨层 SQL |
| A04 | P1 | Prompt 历史不能完整重放 |
| A05 | P1 | 真实研究产出对材料结构敏感 |
| A06 | P1 | 同步操作与人工中断恢复限制扩展 |
| A07 | P1 | 人工计划保存没有报告式版本 CAS |
| A08 | P1 | Store 初始化在版本门禁和迁移备份前存在 DDL |
| A09 | P1 | 报告编辑体验仍暴露契约 JSON |
| A10 | P1 | Tavily 配额没有跨项目原子预算控制 |
| A11 | P2 | 历史与 JSON 投影有存储放大和命名负担 |
| A12 | P2 | 可复现环境与持续验证声明不完整 |
| A13 | P2 | 网络与本地信任边界需要保持准确描述 |

### A01 P1 README 与阶段记录不能直接作为当前行为说明

**证据与事实：** README 的迁移章节仍写当前 v5、研究验收仍写 230 项及真实研究数据为空；当前迁移代码为 v6，实库已有研究数据，后续报告记录 674 项和真实链路。

[README.md](../README.md#L1)；[database/migrations.py · migrate](../database/migrations.py#L21)；[REPORT_VERIFY_V3_2026-11-05.md](../REPORT_VERIFY_V3_2026-11-05.md#L1)；[REPORT_PHASE4_2_1_4_C_B_IMPLEMENTATION.md](../REPORT_PHASE4_2_1_4_C_B_IMPLEMENTATION.md#L1)。

**影响：** 新开发容易引用旧契约、错误判断功能缺失或已验证范围。

**建议：** 以本套架构入口记录当前事实，后续另行授权更新 README 的当前章节并保留阶段时间语境；本次不改原文。

### A02 P1 SearchProvider 协议不完整

**证据与事实：** 协议只定义 search/extract，但 ResearchService.search 无条件调用 provider.usage；现有 Tavily 和测试 Mock 另外提供此方法。

[services/research/base.py · SearchProvider](../services/research/base.py#L49)；[services/research/service.py · ResearchService.search](../services/research/service.py#L100)；[services/research/tavily.py · TavilyProvider.usage](../services/research/tavily.py#L104)。

**影响：** 一个形式上满足当前协议的替代 Provider 仍可能被判配额未知，默认无法执行搜索。

**建议：** 后续在协议补齐 usage 或明确可选能力和回退策略，并增加契约测试。

### A03 P1 实际分层存在反向依赖与跨层 SQL

**证据与事实：** ResearchStore 导入 evidence_contract/quality，报告读取器延迟导入 Store 与 guards；页面和服务直接使用 SQL/私有连接。

[database/research_store.py · ResearchStore.verify_evidence_binding](../database/research_store.py#L231)；[services/research/report_evidence.py · read_bundle](../services/research/report_evidence.py#L16)；[services/research/guards.py · require_report](../services/research/guards.py#L54)；[pages/research.py · _evidence_area](../pages/research.py#L176)；[services/research/report_service.py · ReportService._publish](../services/research/report_service.py#L95)。

**影响：** 循环依赖、导入顺序和事务边界增加维护难度，替换存储时需要同时改业务；这不是当前结果错误的证据。

**建议：** 先固化连接级查询/校验接口，后续按功能小步整理；必须保留写事务内复核，不能简单删掉重复验证。

### A04 P1 Prompt 历史不能完整重放

**证据与事实：** 分析记录保存 prompt_version、schema_version 与输入 JSON，但不保存 system Prompt 内容/hash；研究指纹主要冻结输入、模型、输出模式、Provider 和 Schema。历史真实验证报告记载修改 Prompt，当前版本标签仍为相应 v3。

[database/ai_store.py · AIStore.claim_analysis](../database/ai_store.py#L67)；[services/ai/analyzer.py · Analyzer.fingerprint](../services/ai/analyzer.py#L53)；[services/research/service.py · ResearchService._generate](../services/research/service.py#L252)；[services/research/report_service.py · ReportService.generate](../services/research/report_service.py#L142)；[services/research/prompts.py · messages](../services/research/prompts.py#L69)；[REPORT_VERIFY_V3_2026-11-05.md](../REPORT_VERIFY_V3_2026-11-05.md#L1)。

**影响：** 同版本标签可能对应不同提示文本，难精确归因输出差异或重建历史请求；不说明已经发生错误收费。

**建议：** 后续采用明确 Prompt 修订策略及内容 hash，保存非敏感请求契约快照，明确缓存语义；不保存密钥或鉴权头。

### A05 P1 真实研究产出对材料结构敏感

**证据与事实：** 既有真实验收记录一个项目跑通，另一个本轮 24 次证据调用失败；成功批次也只有 3 opinion 与 6 unverified。当前按整批拒绝，证据/报告统一默认 6000 输出 Token。

[REPORT_VERIFY_V3_2026-11-05.md](../REPORT_VERIFY_V3_2026-11-05.md#L1)；[services/research/quality.py · assess_batch](../services/research/quality.py#L463)；[services/research/service.py · ResearchService.organize_evidence](../services/research/service.py#L197)；[services/ai/config.py · AISettings](../services/ai/config.py#L19)。

**影响：** 长来源、重复引句和复杂时间口径可能产生较高人工成本与付费失败；契约正确性不能等价为研究实用性。

**建议：** 后续以固定真实材料回归集衡量有效产出、调用次数与人工修订；研究选窗/同文归组及按任务输出预算方案，保持现有验证边界。

### A06 P1 同步操作与人工中断恢复限制扩展

**证据与事实：** 页面直接同步调用分析、搜索和报告生成，只有 HN 一次性详情线程池；持久 running/uncertain 依赖用户确认中断后解除。

[ai_page.py · show_analysis_controls](../ai_page.py#L47)；[pages/research.py · _action](../pages/research.py#L22)；[services/research/service.py · ResearchService.interrupt_search](../services/research/service.py#L325)；[database/ai_store.py · AIStore.acknowledge_interrupted](../database/ai_store.py#L239)。

**影响：** 长任务等待、浏览器断开和多用户运行的体验及恢复能力有限；当前不是持久后台任务系统。

**建议：** 先记录运行耗时和恢复场景；有实际并发需求时再设计持久任务/Worker，保持动作幂等、逐次预算与快照复核。

### A07 P1 人工计划保存没有报告式版本 CAS

**证据与事实：** 计划 AI 生成保存会比较 base_plan_version_id；人工 save_plan 直接追加 VersionService.create，没有 expected_previous 参数，页面可能仍持有旧版本草稿。报告 save 则明确强制 CAS。

[services/research/service.py · ResearchService.save_plan](../services/research/service.py#L62)；[services/research/service.py · ResearchService._generate](../services/research/service.py#L252)；[pages/research.py · _plan_editor](../pages/research.py#L70)；[services/research/report_service.py · ReportService.save](../services/research/report_service.py#L115)。

**影响：** 多个浏览器/会话可能把旧计划草稿追加为最新；历史不丢失，但新编辑意图可能被旧草稿覆盖为当前版本。属于静态可见风险，本次未动态复现。

**建议：** 后续评估为人工计划保存/恢复增加预期版本检查及冲突提示，配套多会话测试。

### A08 P1 Store 初始化在版本门禁和迁移备份前存在 DDL

**证据与事实：** HotspotStore.__init__ 先执行一期 CREATE TABLE/INDEX IF NOT EXISTS，再调用 migrate 做版本拒绝、备份和事务升级。

[database/store.py · HotspotStore.__init__](../database/store.py#L19)；[database/migrations.py · migrate](../database/migrations.py#L21)。

**影响：** 实例化 Store 不能用于只读审计；未知/未来版本或不完整库可能在最终拒绝前发生基础结构写入。当前 v6 样本未观察到异常，本次没有执行该路径。

**建议：** 后续将版本检查、初始化及备份边界设计成统一流程；补充拒绝未知结构时文件不变的测试。

### A09 P1 报告编辑体验仍暴露契约 JSON

**证据与事实：** 研究页面让用户编辑“报告组织结构（仅引用与模板）”的 JSON；报告正文由程序固定模板渲染，脚本生成等后续页面占位。

[pages/research.py · _report_area](../pages/research.py#L233)；[services/research/report_validation.py · atom](../services/research/report_validation.py#L42)；[pages/production.py · _details](../pages/production.py#L103)。

**影响：** 创作者需要理解结构字段，距产品原型中的自然创作工作台仍有差距；这不是证据校验错误。

**建议：** 后续在不增加自由事实写入旁路的前提下，设计可视化排序与模板选择，独立定义脚本内容契约。

### A10 P1 Tavily 配额没有跨项目原子预算控制

**证据与事实：** 当前先 usage 读取余额，再按题目数加 4 检查单轮上界；credits 独立记录，没有共用余额预占事务或月度硬上限。

[services/research/service.py · ResearchService.search](../services/research/service.py#L100)；[database/research_store.py · ResearchStore.search_usage](../database/research_store.py#L52)；[services/research/tavily.py · TavilyProvider.usage](../services/research/tavily.py#L104)。

**影响：** 并发项目可同时通过同一余额快照；人民币模型预算不约束 Tavily credits。未知额度显式继续也不代表服务商账单上限保证。

**建议：** 在实际并发或成本需求出现时设计独立的搜索额度策略和账单核对，避免混入 Token/人民币模型账本。

### A11 P2 历史与 JSON 投影有存储放大和命名负担

**证据与事实：** video_ideas 同时存投影与 idea_json；研究输入保存完整 manifest，报告再冻结证据快照；topic_analyses 名称同时承担多类研究用途。hotspot_scores 仅保留当前分。

[database/ai_store.py · AIStore.complete_analysis](../database/ai_store.py#L137)；[services/research/evidence_contract.py · build_manifest](../services/research/evidence_contract.py#L53)；[services/research/report_validation.py · validate_candidate](../services/research/report_validation.py#L61)；[database/store.py · HotspotStore.save_scores](../database/store.py#L201)。

**影响：** 数据增长后有存储与理解成本；证据 SQL/JSON 不一致也需拒绝。冗余目前部分是有意审计设计，不宜直接删除。

**建议：** 后续实测增长、检索和复核开销，明确当前评分与历史观测区别；需要归档时先设计追溯和恢复策略。

### A12 P2 可复现环境与持续验证声明不完整

**证据与事实：** 依赖只固定直接版本，未发现项目级 Python 版本范围、完整传递依赖锁、仓库 CI 或覆盖率产物；历史支持环境主要为 Windows/Python 3.13。

[requirements.txt](../requirements.txt#L1)；[pytest.ini](../pytest.ini#L1)；[README.md](../README.md#L1)。

**影响：** 换机器、升级或新增贡献者时难判断正式支持矩阵；不能给出未经测量的覆盖率。

**建议：** 后续明确支持环境、锁定和 CI 方案，优先复用已有测试隔离，避免为文档审计引入新依赖。

### A13 P2 网络与本地信任边界需要保持准确描述

**证据与事实：** public_url 对主机名只做字符串/IP 字面量过滤，没有 DNS/重定向目标核验；应用本地只请求固定供应商端点。确认意图是本地内存对象，无用户身份认证。

[services/research/tavily.py · public_url](../services/research/tavily.py#L13)；[services/research/tavily.py · TavilyProvider._request](../services/research/tavily.py#L39)；[services/research/report_confirmation.py · LocalReportReviewSession](../services/research/report_confirmation.py#L17)。

**影响：** 不能宣传完整 SSRF 防护或多用户授权。尚未确认当前存在可利用漏洞；未来直接爬取或远程多用户部署会改变风险边界。

**建议：** 文档保留当前限定；未来改变网络/部署边界时单独设计域名解析、重定向和身份权限策略。

## 验证结果与限制

### 本次实际执行的检查

- 目录清点与 Git 只读状态检查，检查 9 个目标文档在创建前均不存在。
- 建立 132 个既有文件的内容 hash 基线，覆盖源码、测试、非秘密配置、已有文档、默认库及 6 个已有升级备份；排除 `.env*`、secrets.toml、Git、虚拟环境、缓存和 logs。
- AST 读取 98 个 Python 文件：60 个非 tests 源文件与 38 个测试/辅助文件；其中 33 个 test_ 入口、289 个模块级测试函数定义，非 pytest 参数化后的收集数。
- 读取默认实库 v6 对象，字段列表与顺序对照 22/22 通过；只读完整性和外键检查通过。
- 读取既有 `logs/phase4-2-1-4-c-b/full-acceptance.xml`：674 testcase，failures/errors/skipped 全为 0；是 2026-11-05 历史结果，本次没有重跑。
- 文档验证包括所有本地相对链接和源码行号、模块符号引用、必要章节、SQL/ER 表集合、索引/触发器清单、Mermaid 图结构静态检查及新增文件清单。
- 全部既有保护文件最终 hash、文件存在性和数据库伴随文件复核结果见本报告下方“最终保护核对”。

### 尚未验证

- 未运行任何 DeepSeek、Tavily、GitHub、HN 或其他外部请求；未核验价格目录与服务商当前信息。
- 未启动 Streamlit 或浏览器，未进行 UI 视觉/无障碍及真实人工确认交互验收。
- 未运行 pytest、测试收集、迁移或备份恢复；不将历史 674 项误报成本次测试。
- 未逐份业务内容验证现实真假，也未重新执行所有历史 JSON/envelope 的程序契约；实库完整性不代表全部语义有效。
- 未做多进程压力、断电、磁盘故障、外部身份系统或攻击复现。
- 未读取 `.env`、`.env.example` 或 secrets.toml 内容，不确认运行进程实际数据库/模型/价格配置；变量与默认值仅取自代码。
- 环境没有发现可用的本地 Mermaid 渲染/解析依赖；本次核对受支持的简单 flowchart/erDiagram 语法与节点/关系，不声称已完成引擎渲染和视觉验收。

## 安全边界核对

| 限制 | 本次执行情况 |
| --- | --- |
| 不改生产代码和测试 | 仅只读，最终与基线核对 |
| 不改配置 | 只阅读源码加载逻辑和 requirements/pytest/gitignore，最终与基线核对 |
| 不读秘密 | 未读取 `.env*` 或 secrets.toml，未对其内容计算 hash，未打印任何凭据值 |
| 不写数据库 | 直接 ro+immutable；无 Store、DDL、DML、迁移、checkpoint、VACUUM 或生产备份操作 |
| 不调用外部 API | 未使用网络请求工具，未执行客户端/应用业务入口 |
| 不覆盖旧文档 | 所有目标创建前检查不存在，以 exclusive create 写入；只修订本次新增文档 |
| 保留既有工作区 | 原未提交修改、未跟踪文件和已删除旧计划状态保留 |
| 不进行 Git 变更操作 | 仅 status/rev-parse 等只读查询；无暂存、提交、推送、reset、clean、移动或删除 |
| 中间产物不污染项目 | 临时脚本、审计元数据和校验结果均在系统临时目录 |

## 最终保护核对

- **132 个既有保护文件 SHA256 全部一致**，未发现修改、删除或丢失；其中包括默认库及 6 个历史备份，共 7 个数据库文件。
- **仅新增上述 9 份 Markdown**；Git 完整文件状态与审计前比较，原有每条状态均保留，新增项精确为这 9 个路径。
- 默认数据库在检查前后 hash 一致，未出现 WAL/SHM/journal 伴随文件；该稳定样本的 integrity_check=ok、foreign_key_check=0 行异常。
- `.env*` 和 secrets.toml 未读取或计算内容 hash；不以 hash 核对秘密文件，未对它们执行写入操作。
- 文档验证最终通过：546 个本地链接及其源码行号有效；11 个 Mermaid 图完成静态节点/关系检查；22 表、全部 20 个显式索引和 19 个触发器 SQL 与实库元数据一致。未执行 Mermaid 引擎渲染。
- 本次未执行 pytest、外部 API、应用启动、数据库迁移或 Git 提交；没有把已有验收结果写成本次运行结果。

## 修改文件清单

本次只新增以下 9 个文件，无现有文件修改：

```text
docs/ARCHITECTURE.md
docs/architecture/SYSTEM_OVERVIEW.md
docs/architecture/MODULE_DESIGN.md
docs/architecture/DATA_FLOW.md
docs/architecture/DATABASE_DESIGN.md
docs/architecture/TECH_STACK.md
docs/architecture/AI_ARCHITECTURE.md
docs/architecture/TEST_ARCHITECTURE.md
docs/ARCHITECTURE_AUDIT_REPORT.md
```

未创建 Git 提交。不存在本次代码重构、新功能或数据库变更。

## 检查文件索引与证据等级

源码符号和模块清单来自 AST，不导入生产模块；主流程、Store、迁移、Provider、校验器与核心测试另做正文阅读。下面列出全部 Python 检查文件，行数便于复查审计基准，不能代表每行均完成动态验证。

| 检查文件 | 行数 | 角色 |
| --- | --- | --- |
| [ai_page.py](../ai_page.py#L1) | 244 | 源码结构与调用边界 |
| [app.py](../app.py#L1) | 291 | 源码结构与调用边界 |
| [collectors/__init__.py](../collectors/__init__.py#L1) | 1 | 源码结构与调用边界 |
| [collectors/github.py](../collectors/github.py#L1) | 58 | 源码结构与调用边界 |
| [collectors/hacker_news.py](../collectors/hacker_news.py#L1) | 92 | 源码结构与调用边界 |
| [collectors/http.py](../collectors/http.py#L1) | 40 | 源码结构与调用边界 |
| [config.py](../config.py#L1) | 26 | 源码结构与调用边界 |
| [database/__init__.py](../database/__init__.py#L1) | 1 | 源码结构与调用边界 |
| [database/ai_migration.py](../database/ai_migration.py#L1) | 57 | 源码结构与调用边界 |
| [database/ai_store.py](../database/ai_store.py#L1) | 246 | 源码结构与调用边界 |
| [database/migrations.py](../database/migrations.py#L1) | 92 | 源码结构与调用边界 |
| [database/production_migration.py](../database/production_migration.py#L1) | 65 | 源码结构与调用边界 |
| [database/production_store.py](../database/production_store.py#L1) | 131 | 源码结构与调用边界 |
| [database/research_migration.py](../database/research_migration.py#L1) | 91 | 源码结构与调用边界 |
| [database/research_quality_migration.py](../database/research_quality_migration.py#L1) | 26 | 源码结构与调用边界 |
| [database/research_store.py](../database/research_store.py#L1) | 325 | 源码结构与调用边界 |
| [database/store.py](../database/store.py#L1) | 264 | 源码结构与调用边界 |
| [models.py](../models.py#L1) | 79 | 源码结构与调用边界 |
| [pages/production.py](../pages/production.py#L1) | 182 | 源码结构与调用边界 |
| [pages/research.py](../pages/research.py#L1) | 350 | 源码结构与调用边界 |
| [services/__init__.py](../services/__init__.py#L1) | 1 | 源码结构与调用边界 |
| [services/ai/__init__.py](../services/ai/__init__.py#L1) | 1 | 源码结构与调用边界 |
| [services/ai/analyzer.py](../services/ai/analyzer.py#L1) | 137 | 源码结构与调用边界 |
| [services/ai/base.py](../services/ai/base.py#L1) | 57 | 源码结构与调用边界 |
| [services/ai/config.py](../services/ai/config.py#L1) | 82 | 源码结构与调用边界 |
| [services/ai/cost_tracker.py](../services/ai/cost_tracker.py#L1) | 62 | 源码结构与调用边界 |
| [services/ai/deepseek_client.py](../services/ai/deepseek_client.py#L1) | 105 | 源码结构与调用边界 |
| [services/ai/executor.py](../services/ai/executor.py#L1) | 54 | 源码结构与调用边界 |
| [services/ai/mock.py](../services/ai/mock.py#L1) | 25 | 源码结构与调用边界 |
| [services/ai/prompts.py](../services/ai/prompts.py#L1) | 25 | 源码结构与调用边界 |
| [services/ai/schemas.py](../services/ai/schemas.py#L1) | 75 | 源码结构与调用边界 |
| [services/normalization.py](../services/normalization.py#L1) | 80 | 源码结构与调用边界 |
| [services/production/__init__.py](../services/production/__init__.py#L1) | 1 | 源码结构与调用边界 |
| [services/production/action_service.py](../services/production/action_service.py#L1) | 20 | 源码结构与调用边界 |
| [services/production/project_service.py](../services/production/project_service.py#L1) | 101 | 源码结构与调用边界 |
| [services/production/version_service.py](../services/production/version_service.py#L1) | 89 | 源码结构与调用边界 |
| [services/ranking.py](../services/ranking.py#L1) | 64 | 源码结构与调用边界 |
| [services/recalculate.py](../services/recalculate.py#L1) | 29 | 源码结构与调用边界 |
| [services/refresh.py](../services/refresh.py#L1) | 62 | 源码结构与调用边界 |
| [services/research/__init__.py](../services/research/__init__.py#L1) | 1 | 源码结构与调用边界 |
| [services/research/base.py](../services/research/base.py#L1) | 62 | 源码结构与调用边界 |
| [services/research/diagnostics.py](../services/research/diagnostics.py#L1) | 67 | 源码结构与调用边界 |
| [services/research/evidence_contract.py](../services/research/evidence_contract.py#L1) | 119 | 源码结构与调用边界 |
| [services/research/guards.py](../services/research/guards.py#L1) | 67 | 源码结构与调用边界 |
| [services/research/materials.py](../services/research/materials.py#L1) | 226 | 源码结构与调用边界 |
| [services/research/prompts.py](../services/research/prompts.py#L1) | 85 | 源码结构与调用边界 |
| [services/research/quality.py](../services/research/quality.py#L1) | 469 | 源码结构与调用边界 |
| [services/research/queries.py](../services/research/queries.py#L1) | 23 | 源码结构与调用边界 |
| [services/research/report_confirmation.py](../services/research/report_confirmation.py#L1) | 50 | 源码结构与调用边界 |
| [services/research/report_contract.py](../services/research/report_contract.py#L1) | 44 | 源码结构与调用边界 |
| [services/research/report_evidence.py](../services/research/report_evidence.py#L1) | 109 | 源码结构与调用边界 |
| [services/research/report_service.py](../services/research/report_service.py#L1) | 274 | 源码结构与调用边界 |
| [services/research/report_validation.py](../services/research/report_validation.py#L1) | 190 | 源码结构与调用边界 |
| [services/research/schemas.py](../services/research/schemas.py#L1) | 88 | 源码结构与调用边界 |
| [services/research/service.py](../services/research/service.py#L1) | 336 | 源码结构与调用边界 |
| [services/research/tavily.py](../services/research/tavily.py#L1) | 115 | 源码结构与调用边界 |
| [services/research/temporal.py](../services/research/temporal.py#L1) | 214 | 源码结构与调用边界 |
| [services/scoring.py](../services/scoring.py#L1) | 123 | 源码结构与调用边界 |
| [services/scoring_rules.py](../services/scoring_rules.py#L1) | 46 | 源码结构与调用边界 |
| [services/trends.py](../services/trends.py#L1) | 65 | 源码结构与调用边界 |
| [tests/conftest.py](../tests/conftest.py#L1) | 82 | 测试/夹具静态审查 |
| [tests/research_quality_cases.py](../tests/research_quality_cases.py#L1) | 63 | 测试/夹具静态审查 |
| [tests/research_report_cases.py](../tests/research_report_cases.py#L1) | 182 | 测试/夹具静态审查 |
| [tests/research_service_cases.py](../tests/research_service_cases.py#L1) | 416 | 测试/夹具静态审查 |
| [tests/research_support.py](../tests/research_support.py#L1) | 118 | 测试/夹具静态审查 |
| [tests/test_ai_analyzer.py](../tests/test_ai_analyzer.py#L1) | 124 | 测试/夹具静态审查 |
| [tests/test_ai_budget.py](../tests/test_ai_budget.py#L1) | 131 | 测试/夹具静态审查 |
| [tests/test_ai_migration.py](../tests/test_ai_migration.py#L1) | 79 | 测试/夹具静态审查 |
| [tests/test_ai_page.py](../tests/test_ai_page.py#L1) | 87 | 测试/夹具静态审查 |
| [tests/test_ai_provider.py](../tests/test_ai_provider.py#L1) | 146 | 测试/夹具静态审查 |
| [tests/test_ai_safety.py](../tests/test_ai_safety.py#L1) | 105 | 测试/夹具静态审查 |
| [tests/test_app.py](../tests/test_app.py#L1) | 130 | 测试/夹具静态审查 |
| [tests/test_collectors.py](../tests/test_collectors.py#L1) | 151 | 测试/夹具静态审查 |
| [tests/test_normalization.py](../tests/test_normalization.py#L1) | 40 | 测试/夹具静态审查 |
| [tests/test_phase2_app.py](../tests/test_phase2_app.py#L1) | 102 | 测试/夹具静态审查 |
| [tests/test_phase2_refresh.py](../tests/test_phase2_refresh.py#L1) | 138 | 测试/夹具静态审查 |
| [tests/test_production_page.py](../tests/test_production_page.py#L1) | 161 | 测试/夹具静态审查 |
| [tests/test_production_service.py](../tests/test_production_service.py#L1) | 132 | 测试/夹具静态审查 |
| [tests/test_production_store.py](../tests/test_production_store.py#L1) | 163 | 测试/夹具静态审查 |
| [tests/test_production_versions.py](../tests/test_production_versions.py#L1) | 140 | 测试/夹具静态审查 |
| [tests/test_refresh.py](../tests/test_refresh.py#L1) | 33 | 测试/夹具静态审查 |
| [tests/test_research_materials.py](../tests/test_research_materials.py#L1) | 176 | 测试/夹具静态审查 |
| [tests/test_research_migration.py](../tests/test_research_migration.py#L1) | 89 | 测试/夹具静态审查 |
| [tests/test_research_page.py](../tests/test_research_page.py#L1) | 102 | 测试/夹具静态审查 |
| [tests/test_research_provider.py](../tests/test_research_provider.py#L1) | 103 | 测试/夹具静态审查 |
| [tests/test_research_pure_contract_integration.py](../tests/test_research_pure_contract_integration.py#L1) | 60 | 测试/夹具静态审查 |
| [tests/test_research_quality.py](../tests/test_research_quality.py#L1) | 485 | 测试/夹具静态审查 |
| [tests/test_research_quality_integration.py](../tests/test_research_quality_integration.py#L1) | 213 | 测试/夹具静态审查 |
| [tests/test_research_quality_persistence.py](../tests/test_research_quality_persistence.py#L1) | 272 | 测试/夹具静态审查 |
| [tests/test_research_quality_policy.py](../tests/test_research_quality_policy.py#L1) | 276 | 测试/夹具静态审查 |
| [tests/test_research_report_contract.py](../tests/test_research_report_contract.py#L1) | 81 | 测试/夹具静态审查 |
| [tests/test_research_report_integration.py](../tests/test_research_report_integration.py#L1) | 176 | 测试/夹具静态审查 |
| [tests/test_research_report_persistence.py](../tests/test_research_report_persistence.py#L1) | 228 | 测试/夹具静态审查 |
| [tests/test_research_temporal.py](../tests/test_research_temporal.py#L1) | 125 | 测试/夹具静态审查 |
| [tests/test_research_workflow.py](../tests/test_research_workflow.py#L1) | 600 | 测试/夹具静态审查 |
| [tests/test_scoring.py](../tests/test_scoring.py#L1) | 150 | 测试/夹具静态审查 |
| [tests/test_snapshots.py](../tests/test_snapshots.py#L1) | 124 | 测试/夹具静态审查 |
| [tests/test_store.py](../tests/test_store.py#L1) | 79 | 测试/夹具静态审查 |

### 配置与已有文档

| 文件 | 用作何种证据 |
| --- | --- |
| [.gitignore](../.gitignore#L1) | 依赖/测试/忽略声明 |
| [README.md](../README.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [REPORT_PHASE4_2_1_4_A_DESIGN.md](../REPORT_PHASE4_2_1_4_A_DESIGN.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [REPORT_PHASE4_2_1_4_B_BATCH1.md](../REPORT_PHASE4_2_1_4_B_BATCH1.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [REPORT_PHASE4_2_1_4_B_BATCH2.md](../REPORT_PHASE4_2_1_4_B_BATCH2.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [REPORT_PHASE4_2_1_4_C_A_DESIGN.md](../REPORT_PHASE4_2_1_4_C_A_DESIGN.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [REPORT_PHASE4_2_1_4_C_B_IMPLEMENTATION.md](../REPORT_PHASE4_2_1_4_C_B_IMPLEMENTATION.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [REPORT_VERIFY_V3_2026-11-05.md](../REPORT_VERIFY_V3_2026-11-05.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/PLAN.md](plan%26report/PLAN.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/PLAN_PHASE2.md](plan%26report/PLAN_PHASE2.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/PLAN_PHASE3.md](plan%26report/PLAN_PHASE3.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/PLAN_PHASE4_1.md](plan%26report/PLAN_PHASE4_1.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/PLAN_PHASE4_2_1.md](plan%26report/PLAN_PHASE4_2_1.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/REPORT_PHASE4_1.md](plan%26report/REPORT_PHASE4_1.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/REPORT_PHASE4_2_1.md](plan%26report/REPORT_PHASE4_2_1.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/REPORT_PHASE4_2_1_1_AUDIT.md](plan%26report/REPORT_PHASE4_2_1_1_AUDIT.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/REPORT_PHASE4_2_1_1_P0.md](plan%26report/REPORT_PHASE4_2_1_1_P0.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/REPORT_PHASE4_2_1_2_MIGRATION.md](plan%26report/REPORT_PHASE4_2_1_2_MIGRATION.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/REPORT_PHASE4_2_1_3_REAL_API.md](plan%26report/REPORT_PHASE4_2_1_3_REAL_API.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [docs/plan&report/REPORT_REAL_RUN_2026-11-03.md](plan%26report/REPORT_REAL_RUN_2026-11-03.md#L1) | 既有计划、设计或阶段验收；保留时间语境 |
| [pytest.ini](../pytest.ini#L1) | 依赖/测试/忽略声明 |
| [requirements.txt](../requirements.txt#L1) | 依赖/测试/忽略声明 |

另读取 [产品理想形态说明](AI热点雷达产品理想形态说明.docx) 作为愿景来源，既有 JUnit XML 作为历史测试结果；数据库证据为本次默认库只读元数据与聚合统计。日志中的业务脚本未执行，原始 API 请求日志不批量输出。

## 一致性与后续维护约定

数据库定义以实际 sqlite_master 为主，源码接口以当前符号为主；历史报告只证明其记录时点，不替代当前实现。遇到无法确定的部分保留缺口，不把缺少信息补写成已经实现。

后续修改时按“入口与接口 → 流程 → 数据库/JSON 契约 → AI/确认边界 → 测试 → 总入口状态”同步更新。每个问题保留编号便于单独授权跟进；本次完成文档后停止，不进入任何重构或新功能开发。
