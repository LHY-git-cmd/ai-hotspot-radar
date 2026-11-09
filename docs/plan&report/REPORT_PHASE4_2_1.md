# 第四阶段 4.2.1：AI 资料研究交付报告

完成日期：2026-11-02（北京时间）。按用户已确认计划增量实施；保留前三阶段及 4.1 未提交变更，没有创建 Git commit。

## 1. 修改和新增文件

本期新增业务文件：

- `database/research_migration.py`：v5 增量表、索引、外键及研究历史保护触发器。
- `database/research_store.py`：研究运行/逐次请求、来源快照、问题关联、证据和模型结果事务。
- `services/ai/executor.py`：选题与研究共用的模型预算预占、有限重试、用量保存和结果持久化。
- `services/research/__init__.py`：模块边界说明。
- `services/research/base.py`：Search Provider 协议、标准响应/错误和可空 credits。
- `services/research/tavily.py`：Tavily REST 搜索、提取、额度适配，不安装 SDK。
- `services/research/schemas.py`：计划、问题、证据、引用和报告的完整本地 Schema/语义校验。
- `services/research/prompts.py`：固定 system 规则与不可信材料隔离。
- `services/research/guards.py`：确认有效性、研究依据和后续制作准入门禁。
- `services/research/service.py`：计划→确认→搜索→证据→报告→确认的集中编排。
- `pages/research.py`：工作台四区界面。

本期必要修改：

- `database/migrations.py`：目标版本 5，保留备份及事务升级机制。
- `database/ai_store.py`：用途/制作任务关联、研究与原选题历史隔离；费用仍在同一账本汇总。
- `services/ai/deepseek_client.py`、`schemas.py`、`cost_tracker.py`：可选结果 Schema/工具名，按该次实际完整请求体预占。
- `services/ai/analyzer.py`：调用共用执行器；原选题材料、业务 Schema、预算阈值和评分规则保留。
- `services/production/project_service.py`、`version_service.py`：报告确认门禁和同事务保存版本能力。
- `services/production/action_service.py`、`pages/production.py`：研究操作名称与资料研究入口。
- `ai_page.py`：共用费用视图展示调用用途和制作任务。
- `.env.example`：新增空的 `TAVILY_API_KEY` 示例，未写实际密钥。
- `README.md`、`PLAN_PHASE4_2_1.md`：使用、配置、实际验证及限制。

新增测试文件：`tests/test_research_provider.py`、`test_research_workflow.py`、`test_research_migration.py`、`test_research_page.py`、`tests/research_support.py`。

调整原测试：`tests/test_ai_migration.py`、`test_production_store.py` 更新最新迁移目标/旧字段投影；`test_production_service.py`、`test_production_versions.py`、`test_production_page.py` 为后续制作补充真实服务执行的 Mock 报告确认前置条件，保留原去重、完整版本、恢复、并发、审计和历史保留断言。早期阶段页面测试继续检查无研究写入时旧表不变。

`app.py`、`tests/conftest.py` 以及其他 4.1 文件已有的未提交内容均保留；本报告按本期相对 4.1 的变更描述，不将它们误算为本期重新开发。

## 2. 新增表及字段

计划和报告正文继续保存在 `production_versions`，使用研究对象键 `plan` / `report`，没有第二套版本表。

| 新表 | 字段 |
| --- | --- |
| `research_plan_confirmations` | `id`、`project_id`、`plan_version_id`、`action_id`、`confirmed_at` |
| `research_report_confirmations` | `id`、`project_id`、`report_version_id`、`plan_confirmation_id`、`run_id`、`evidence_analysis_id`、`action_id`、`confirmed_at` |
| `research_search_runs` | `id`、`project_id`、`plan_version_id`、`confirmation_id`、`action_id`、`provider`、`params_json`、`status`、`started_at`、`finished_at`、`error_type` |
| `research_search_calls` | `id`、`run_id`、`operation`、`question_id`、`request_json`、`response_json`、`request_id`、`credits`、`status`、`created_at`、`finished_at`、`error_type` |
| `research_sources` | `id`、`project_id`、`title`、`url`、`url_key`、`domain`、`published_at`、`searched_at`、`provider`、`snippet`、`text`、`extraction_status`、`extraction_error`、`content_hash` |
| `research_source_questions` | `project_id`、`run_id`、`question_id`、`source_id` |
| `research_evidence` | `id`、`project_id`、`run_id`、`question_id`、`analysis_id`、`position`、`category`、`summary`、`inference`、`verification`、`created_at` |
| `research_evidence_sources` | `project_id`、`evidence_id`、`source_id`、`quote`、`field`、`quote_offset` |

既有 `topic_analyses` 追加三列：

- `purpose`：默认 `topic`，可取研究计划/证据/报告用途；旧记录全部保留为原用途。
- `production_project_id`：可空制作任务外键。
- `result_version_id`：可空完整输出版本外键。

原有 `ai_analysis_runs` 和 `ai_budget_settings` 未新增第二套替代表，仍负责全部 DeepSeek 费用与预算。研究动作通过现有 `production_actions.details_json.event` 记录，不重建不可变操作历史表。

复合外键保证确认版本、运行、来源和证据属于同一任务；唯一索引约束动作幂等、运行锁与来源快照去重。来源正文、证据、关联和确认记录只追加，不允许 UPDATE/DELETE。

## 3. 数据库迁移前后版本

实际正式库从 **v4→v5**。继续支持新库和 v0/v2/v3/v4 到当前版本；未知较新版本拒绝打开，重开不重复升级或备份。

先在 SQLite 一致性副本演练，重新核对正式库未发生变化，再由原迁移机制持有写锁、生成备份并事务升级。DDL 失败可整体回滚新增列及表。

## 4. 实际备份位置和完整性

- 数据库：`E:\one\ai-hotspot-radar\data\hotspots.sqlite3`。
- 正式备份：`E:\one\ai-hotspot-radar\data\hotspots.pre-v5-20261102T145733381575Z-62b052d6.sqlite3`。
- 演练副本：`E:\one\ai-hotspot-radar\logs\phase4-2-1-rehearsal-20261102T145733298120Z.sqlite3`。
- 检查记录：`logs/phase4-2-1-migration.json`。

全部 **13 张旧业务表**及 SQLite 序列表的旧字段投影、行数和完整行 SHA-256 与本次正式迁移前即时快照一致。旧列定义、旧索引及历史保护触发器保留；只为新增研究关联增加结构。

| 原数据 | 迁移前后行数 |
| --- | ---: |
| 热点 / 评分 | 61 / 61 |
| 采集任务 / 快照 | 16 / 296 |
| AI 分析 / 模型尝试 | 3 / 3 |
| 视频选题 / 选题动作 | 9 / 5 |
| 预算设置 | 1 |
| 制作任务 / 操作 / 对象 / 版本 | 各 0 |

备份、演练副本及正式库 `integrity_check=ok`，`foreign_key_check` 无错误；旧分析新增三列为 `topic`、NULL、NULL。八张研究表均为空，未写入模拟内容。真实库只读页面检查后全部表内容仍一致。

评分核对使用本次迁移前即时快照，保留当时的最新值，不拿 4.1 早期备份代替本次基线；本期没有修改评分算法或执行真实评分重算。

## 5. 研究计划功能

使用现有 DeepSeek Provider 生成目标、重点、问题、关键词、推荐来源类型、日期范围和特别核实事实。生成计划阶段不构造或调用搜索服务。

支持查看、添加/编辑/删除问题、修改关键词/来源类型/域名/日期、保存新版本、查看/恢复历史及确认当前版本。确认动作记录任务、版本、时间和审计。

计划保存、重新生成或恢复产生新版本，旧确认不沿用。过期版本不能确认或搜索；页面未保存修改会隐藏搜索入口。模型运行期间若人工保存了新计划，拒绝把过期模型输出追加为最新计划，费用仍按实际记录。

## 6. Tavily Provider

协议和标准数据定义独立于 Tavily，实现 `search()`、`extract()`，可选额度查询。使用已有 requests 调用官方 REST，不安装 SDK。

参考 [Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)、[Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)、[Usage](https://docs.tavily.com/documentation/api-reference/endpoint/usage) 文档。Key 从 `TAVILY_API_KEY` 读取，不写数据库/日志/页面，配置 repr 隐藏密钥；错误不输出响应正文或请求头。

没有 Key 时不请求、不伪造结果，原有功能和本地历史可用。HTTP 错误、超时和非法响应使用安全错误类型；适配器不自动重试。

## 7. 搜索与网页提取

搜索必须绑定当前已确认计划，并且用户另行点击执行按钮。服务层、运行锁和动作 ID 控制重放；同动作跨线程提交仅执行一次，重新搜索须明确准备新动作。

默认每题一次 basic search，最多 3 个结果；最多 10 个问题、20 个 URL、一次批量 extract。关闭自动参数升级和服务商答案生成。关键词及推荐来源类型用于查询，用户确认的优先域名作为限定范围；不会根据模型猜测给来源贴“已核实官方”标签。

保存逐次请求状态、实际结果、原始 URL 和问题关联。相同规范化 URL 被多个问题引用只保存一次内容快照；正文改变追加新快照，不覆盖历史报告依据。

提取逐 URL 判断成功/失败，空文本或缺失项不算成功。搜索摘录与提取文本分字段保存；提取失败只显示摘录及失败状态，不伪装成全文。保留服务商原始发布时间，未提供时为空。

每次后续网络步骤重新检查计划、任务和运行状态；计划改变或用户确认执行已中断后停止新请求。已经返回的用量、原始响应和已取得来源保留，失败不会自动重试。

## 8. 证据管理

支持已证实事实、单一来源事实、来源观点、AI 推断、存在争议、待核实六类，分别保存来源原文引文、AI 摘要、AI 推断和核验说明。

证据必须关联已保存、与问题相关的来源。引用 ID、任务归属和引文文本匹配由客户端校验；伪造来源/问题/引文会拒绝落为成功结果，已产生用量仍计入模型费用。

“已证实事实”至少要求两个不同根域名的提取原文支持，不能仅凭搜索摘录认定。该检查仅是保守门槛，**不证明语义一致或来源真实独立**；页面标注 AI 分类待人工审核。每批重新整理追加新证据，旧批次可查询。

原始来源正文不可由 AI 改写。按来源数量保守分配模型摘录长度，记录文本范围及截断标记，实际请求体仍受原输入字节上限检查；完整提取文本继续保存在数据库。

## 9. 研究报告

报告包含概述、目标、核心结论、关键事实、数据及出处、来源差异、未核实问题、事实风险和完整来源列表。

事实/结论/数据/差异逐条关联证据 ID，正文显示证据与具体来源链接；来源列表从保存的研究来源生成，不由模型发明 URL。不存在或其他批次的证据不能通过校验。

支持 AI 生成/主动重新生成、结构化人工编辑、保存新版本、查询/恢复历史和确认报告。报告绑定计划、搜索运行和证据批次，重新搜索、更新证据或新增报告版本后须重新审核确认；旧数据不删除。

只有有效报告确认后，状态服务和通用版本服务才允许进入/恢复脚本及之后阶段或保存其内容。页面提供“进入脚本制作阶段”按钮，仅调整人工状态，实际脚本功能尚未开发。

## 10. 成本统计

DeepSeek：与原选题分析共用 `ai_analysis_runs`、预占/结算、默认 100 元月预算、用户已保存上限、70%/90%/100%阈值、北京时间账期和未知费用核对规则。按本次实际 Schema 和完整请求体预占；付费结果保存失败也保留已知用量和费用。用量不明保留预占，不能当作零。

Tavily：在 `research_search_calls` 单独记录 search/extract 次数、状态和 credits，绝不混入模型 Token/人民币账本。先查额度；已知不足停止，未知默认停止，用户可明确允许在调用上限内继续。不会主动启用 pay-as-you-go 或升级搜索深度。

实际 credits 缺失为 NULL，显示未知；服务商实际返回 0 则保留 0。Extract 可能按累计成功提取计量，0 不等于保证最终免费，详见 [官方 credits 说明](https://docs.tavily.com/documentation/api-credits)。已知消耗和未知次数分开统计，失败不记成功。

## 11. 新增自动化测试

新增 **61 项实际 pytest 用例**：

| 测试模块 | 数量 |
| --- | ---: |
| 研究 Provider | 15 |
| 研究工作流 | 41 |
| 研究迁移 | 3 |
| 研究页面 | 2 |

核心第一批 21 项先观察缺失模块/接口造成的失败，页面 2 项先观察研究页面缺失失败，再实现。开发中修正了 Mock 响应顺序、空报告表格列类型以及在多对象下测试需先选择脚本对象的问题；没有删除业务断言。

覆盖计划版本/确认失效、禁止越权搜索、搜索失败/提取部分失败、用量未知、来源去重/快照、问题关联、六类证据及引用、报告编辑/重生成/确认/恢复、后续阶段门禁、共享预算、费用保存失败、Prompt Injection 材料隔离、线程动作幂等、并发修改和中断停止，以及 20 个中文来源的输入限制。

## 12. 完整测试和本地运行结果

- 修改前基线：**169 passed，0 failed，18.67 秒**。
- 最终完整套件：**230 passed，0 failed，0 skipped，36.93 秒**。
- 命令：`.\.venv\Scripts\python.exe -m pytest --junitxml=logs/phase4-2-1-full.xml`。
- 证据：`logs/phase4-2-1-full.xml`、`logs/phase4-2-1-full.log`。
- 真实 v5 库只读 AppTest：工作台可选 9 条选题，归档筛选、AI 分析历史和排行导航正常；无 Key 可查看历史，HTTP/模型调用 0，全部表内容不变。研究详情没有真实任务可供验证，其完整流程通过临时库 AppTest 验收。
- 独立本地启动：端口 59164 首页和健康接口 HTTP 200，健康正文 `ok`；只停止本次启动的验收进程。记录 `logs/phase4-2-1-startup.json`。
- Python 编译、依赖检查和补丁空白检查通过；`pip check` 返回 `No broken requirements found`。

## 13. 真实 API 联调

**未进行真实 DeepSeek、Tavily 搜索、提取或额度 API 联调。** 自动化全部使用 Mock/临时 SQLite；官方文档核对不属于选题研究执行，也未调用 Tavily 账户服务。

没有用开发计划确认代替任何具体研究计划确认。真实库没有伪造计划、确认、来源、证据或报告。

## 14. 实际联调消耗

本次实际 DeepSeek 业务 API 调用 **0 次**，Tavily 业务 API 调用 **0 次**，因此没有本次真实业务 API 消耗可报告。模拟测试中的 Token/credits 只存在临时库，不计入真实预算。

正式库原模型运行仍为 3 条；旧费用与预算设置的旧字段摘要完全保留。新增研究表为零行。

## 15. 尚未实现、风险与未验证项

- 不开发脚本生成、分镜、素材规划、剪辑指导或发布，四个入口继续占位；没有自动发布、后台调度或无限重试。
- 不实现自动浏览器登录、验证码、反爬绕过、站点爬取或替代搜索服务的适配器；仅保留可替换协议。
- **未验证**真实服务商密钥/模型 Schema 能力、网络、额度返回和真实计费；全部相应边界为 Mock 验证，不能声称已真实联调成功。
- **未验证**完整人工浏览器视觉、多屏/主题/屏幕阅读器、真实站点提取质量、来源独立性/转载关系和事实语义正确性。引用可追溯不等于事实已独立核实，仍需要人工审核。
- **未验证**真实多进程并发、硬退出/断电和磁盘损坏；已做线程并发、DDL/审计/结果保存故障注入及明确中断流程。
- 正文可能仅为服务商有效提取文本，不能保证包含网页全部元素。模型收到的长文本可能有明确标注的截断；极大计划或报告仍可能被原输入字节上限拒绝，不会静默扩大费用。
- 域名数量检查仅是“已证实事实”的必要门槛，不是来源独立性证明；保留 AI 核验说明与人工确认。
- 额度快照可能滞后或被其他客户端消耗，本地统计不替代服务商最终账单。用户自行确认“进程已停止”必须与实际一致；系统不自动清零未知消耗。
- v5 需要当前代码；旧 v4 程序会按版本保护拒绝打开。回退使用迁移前备份副本及对应代码，不调低版本号、不覆盖运行中的数据库。
- 未安装或增加依赖，`requirements.txt` 未改；未暂存、提交、重置或丢弃任何用户已有变更。
