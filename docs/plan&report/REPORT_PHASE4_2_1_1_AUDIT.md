# 第四阶段 4.2.1.1：研究报告质量加固审查与实施方案

- 项目：ai-hotspot-radar；根目录：`E:\one\ai-hotspot-radar`。
- 审查日期：2026-11-03（北京时间）。
- 状态：**只读审查完成；本文是待确认的实施方案，未实施代码改动或迁移。**
- 写入边界：仅按本次交付要求新建本文；未修改其他文件、数据库、配置或环境变量，未暂存或提交 Git 变更。
- 未读取 `.env`，未加载项目配置，未启动应用或实例化 Store，未调用真实 DeepSeek/Tavily API。只访问了 Tavily 的公开文档页面。

## 1. 审查方法、结论与事实边界

### 1.1 直接检查的材料

检查了研究 Provider、服务、提示词、Schema、门禁、研究页面、研究存储、v5 DDL、总迁移入口、通用内容版本服务，以及共用 AI Provider、执行器、账本和费用计算代码；检查了研究测试、测试夹具和相关本地诊断产物。根目录及父级未发现实体 AGENTS.md，遵循聊天提供的规范。

真实数据库使用 Python 标准库 SQLite URI `mode=ro&immutable=1` 连接，先确认没有 `-wal` 文件，仅执行 SELECT 和读取型 PRAGMA；没有经由会创建表或触发迁移的 Store 构造函数。没有执行历史诊断脚本，其中部分脚本包含真实调用、绕过校验或更新数据库的操作。

本轮没有执行 pytest。研究测试夹具会建库、迁移并写入临时数据，页面测试会接触配置加载；为遵守本轮文件与环境限制，只做静态测试审查和内存中的离线校验。既有报告中的“233 passed”是历史结果，不是本轮测试结果。

### 1.2 审查结论

1. **日期丢失是确定的代码缺陷**：数据库有日期，证据和报告的模型输入都没有。
2. **时效判断缺少结构化依据**：当前只验证引文及引用关系，没有数据周期、财季、历史/预测用途的结构化约束；逐字引用成立不代表适用于当前议题。
3. **快照保护已有基础，更新提示缺失**：已有同 URL 重新提取、SHA-256 去重、追加版本和不可改写触发器；没有当前原文独立复核、版本差异展示或可靠的缓存快照时间。
4. **query 构造明确有问题**：直接拼接关键词、完整问题和来源类型，页面没有最终 query 编辑入口。
5. **失败类型被压缩，输出规模缺少硬限制**：语义失败统一记作 invalid_schema，解析失败统一记作 invalid_response；当前已含部分确定性纠正，不能当成尚未修复的问题重复实施。
6. **逐次 credits 主链路已实现**：本地实际 12 次 search/extract 共记录 16 credits，未知用量为 0。`/usage` 是账户额度参考，不是本次调用结算依据；本轮没有复测其更新延迟。

### 1.3 真实数据库核对结果

| 项目 | 本轮只读结果 |
| --- | --- |
| 数据库版本 | `PRAGMA user_version = 5` |
| 搜索运行 | run 1 → plan_version 2；run 2 → plan_version 3；均为 success |
| 来源快照 | 18 行、18 个不同 url_key；两轮各关联 15 个来源，复用了未变来源 |
| BBC S18 | published_at=`Fri, 30 Oct 2026 14:50:37 GMT`；searched_at=`2026-11-02T17:26:26+00:00` |
| Valuentum S7 | published_at=`Tue, 10 Dec 2024 00:00:00 GMT` |
| Cloud Wars S9 | published_at=`Tue, 12 Mar 2024 15:00:00 GMT` |
| 证据输入 | analysis 5–14 均未包含 sources[].published_at；analysis 7 起有 question_ids |
| 报告输入 | analysis 15 的 sources[] 也未包含 published_at |
| 证据正文发送范围 | analysis 6、9、14：15 个来源，每个最多正文 546 字符、摘录 273 字符 |
| 模型正式成功证据 | analysis 14，12 条；另有 analysis 6 的 18 条诊断证据残留，但其分析状态为 failed |
| 报告确认 | 0 条；没有核准进入后续制作的研究报告 |
| Tavily 每轮 credits | 5 次 search=5；1 次 extract=3；每轮合计 8，两轮合计 16 |

上述 published_at 是数据库保存的服务商原始字符串，不是本轮重新获取的原文日期。历史报告将其转为 ISO 时间展示，本轮保留真实原值以说明日期规范化的必要性。

## 2. 当前实现与 A–D 问题逐项回答

### 2.1 A：时间元数据

**A1：research_sources 当前只有两个时间字段。**

| 字段 | 当前类型及来源 | 实际语义与限制 |
| --- | --- | --- |
| published_at | nullable TEXT；Tavily 搜索结果 published_date 原样写入 | 未规范化、未记录日期来源/可信含义；可能是 RFC 1123 或 ISO 字符串 |
| searched_at | NOT NULL TEXT；save_sources 中调用 utc_now() | 是首次插入来源快照时的本地保存时间；不是搜索请求发出时间、原站抓取时间或 Tavily 缓存生成时间 |

另外，`research_search_runs` 有 started_at/finished_at；`research_search_calls` 有 created_at/finished_at；证据和内容版本有 created_at，确认有 confirmed_at。这些是本地处理时间，不能替代网页内容的时间信息。同内容去重时来源行不更新，因此 searched_at 也不是最近一次检索时间。

**A2：搜索能得到日期估计；当前提取接口没有稳定的发布/修改日期协议。**

TavilyProvider.search 已请求 include_published_date=true，并把结果中的字符串 published_date 映射到 SearchResult.published_at。官方当前说明这是“发布或最后更新日期”的最佳估计，缺失可为 null，功能仍标为 beta。因此不能将它无条件称为“原文首次发布日期”。官方 Extract 的公开返回结构及项目 ExtractResult 都没有独立 datePublished/dateModified 字段；项目只接收 URL、raw_content、状态和错误，不解析 HTML 时间元数据。正文中偶尔出现日期不等于具有可靠的元数据字段。[Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)、[Tavily Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)。

**A3：没有独立的原站抓取时间和服务商快照时间。**

没有 origin_fetched_at、provider_snapshot_at、modified_at、snapshot_saved_at、extracted_at。call.finished_at 最多证明本地调用完成的时间范围；不能证明服务商在这一刻抓取了原站。历史报告把本地保存/提取时刻称为“快照抓取时刻”过于确定。

**A4/A5：两个模型阶段均未收到 published_at。**

- organize_evidence 构造来源时只发 id、title、domain、question_ids、text、snippet、提取状态和截断标记。
- generate_report 的来源列表仅 id/title/domain；evidence() 中链接附加 url/title/domain，也没有日期。
- 页面来源展开区能显示 published_at，但这不会自动进入模型上下文。
- SYSTEM 还明确“不能新增来源或日期”；没有输入日期时不能指望模型补回数据库已知日期。

**A6：没有数据所属时间、财季、统计周期的结构化字段。**

research_evidence 只有 question/category/summary/inference/verification 等字段；REPORT_SCHEMA 的 claim 只有 text/evidence_ids。计划的 start_date/end_date 是检索筛选参数，不能等同于统计周期。文本可能包含“FY2025 Q2”等表述，但目前不能稳定查询、校验或向每条报告数据附带周期。

**A7：必须分开表达四类时间。**

| 时间 | 应回答的问题 | 可接受依据 |
| --- | --- | --- |
| 来源发布日 | 这篇文章何时首次发布？ | 原文 datePublished 或明确署期；服务商估计须明确标识 |
| 原文修改日 | 这篇页面何时更新？ | 原文 dateModified；HTTP Last-Modified 只能另标为传输层提示 |
| 数据所属周期 | 引用的是哪一财季、截至日、统计区间或预测年份？ | 对应数据附近的明确原文引句；不能用发布日代替 |
| 本地观察/保存时间 | 系统何时收到、保存这份材料？ | 本地请求日志和保存记录；不能代替上述任一时间 |

原文日期、服务商估计和未知值都应保留来源标识。FY 与自然年也必须区分；没有财年边界依据时保留原文标签，不能推算月份。

### 2.2 B：原文更新检测

**B1：支持同 URL 多次提取，但入口是主动重新搜索。**

每个新的 search action 会重新搜索，并对本轮找到的 URL 批量 extract；不会因为 URL 已入库而跳过提取。相同 action_id 重入只返回旧 run，不会联网。没有“仅重新提取某个历史 URL”的独立产品入口；重新搜索也不保证再次找到原 URL。

**B2：不同内容会保留多个来源快照。**

唯一键为 `(project_id,url_key,content_hash)`；内容变化新建来源，历史 evidence_sources 仍引用旧 source_id 和 quote_offset。触发器禁止来源、问题关联、证据和确认记录的 UPDATE/DELETE，追溯基础合理。

**B3：已有哈希，但不是纯正文哈希。**

当前计算：`sha256(json_text([title, published_at, text or snippet, extraction_status]))`。

- 正文、标题、日期或提取状态不同，可能产生新快照。
- 正文成功且不变时，snippet 变化没有参与哈希；新搜索摘录可能只保存在 call.response_json，模型仍读到复用来源行的旧 snippet。
- 只改变日期字符串格式也会产生新哈希，不能据此断言网页正文更新。
- 对同一 URL 首次取到的 item 保留 title/date，后续问题命中的新元数据不会合并；各次搜索规范化结果仍保存在调用记录。

**B4：目前不能自动识别旧快照与“当前原文”的差异。**

没有原站抓取、差异比较函数或版本提醒。哈希只比较项目已保存的服务商内容；服务商连续返回旧缓存，哈希当然不变。历史报告记录了 BBC/Yahoo 本地另抓的版本差异，本轮没有重新联网验证其当前内容，也不能从该差异确定是缓存、页面变体、地区差异还是解析路径不同。

**B5：最小方案先做已有快照之间的本地提醒，再增强观察记录。**

以同项目、同规范化 URL 的“上一轮实际关联来源”为比较基线，区分正文变化、标题/日期变化、摘录变化和本轮提取失败；不能仅取 MAX(source_id)，因为 A→B→A 时最后一次可能复用旧 ID。展示旧新 source_id、运行时间、逐段差异、受影响证据和报告，保持历史引用不变。正文不变仅表示“所比较的材料相同”，不能显示“当前原文未更新”。

任何新版只提醒并供人工选择重新研究。沿用现有“新搜索→新证据→新报告→人工确认”的流程；不自动替换旧证据，不改变制作任务状态，也不引入新的状态机。

### 2.3 C：搜索查询优化

**C1/C2：直接拼接，已从真实代码和实际 request_json 双重确认。**

`ResearchService.search` 每题构造：

```python
' '.join([*question['keywords'], question['question'], *question['source_types']])
```

真实 run 1 Q1 的关键词后附了一整段中文研究问句和“原始报道（BBC 原文） 新闻聚合/转载说明页”；run 2 把关键词和问题改为英文后命中了 BBC。能确定拼接缺陷，不能保证单凭改短就能在所有检索中命中目标。

**C3：可以改成关键词优先、问题按需补充，无须新增模型调用。**

使用同一个纯函数生成预览和执行 query：优先人工 query_override，否则合并去重后的非空关键词；完整问题和来源类型只作为研究语义材料，不自动拼入。关键词不足时提示用户在 override 中补充核心实体/年份/产品名，不自动翻译、分词扩展或执行第二轮搜索。保留显式 domains 和日期参数。

**C4：当前只能间接编辑，不能查看并编辑最终 query。**

计划编辑器有问题、关键词、来源类型和域名字段，没有最终 query 的预览或输入框。历史请求可从数据库 request_json 查到；页面调用表也没有直接展示 query。建议新增每题 query 预览和可选 override，保存到计划版本 JSON，不能只放在临时页面状态。

**C5：当前修改计划后已有正确的新运行链路，新增 query 字段必须纳入该链路。**

保存计划→新 production_versions 记录→重新确认→使用新 action_id 执行→新 research_search_runs 和 calls。当前 expected_plan 比较会拒绝未保存草稿；旧计划确认不能用于最新版本。新增 override 后继续走此路径，并把最终 query、构造器版本及参数快照写入 params_json/request_json。历史 JSON 允许缺失 override，读取为默认值；未保存修改继续禁止执行。不能重用旧动作掩盖 query 变化。

### 2.4 D：证据整理失败与费用

**D1：实际失败与代码支持的失败必须分开。**

| analysis | 实际状态/错误 | 本轮能确认的含义 |
| --- | --- | --- |
| 5、7、8、9、10、11 | failed / invalid_schema | 6 次结构或语义引用校验失败；账本没有保存每条失败路径，不能逐次还原全部原因 |
| 12、13 | failed / invalid_response | 2 次返回解析失败；没有对应原始响应，不能断言具体是 JSON 语法、工具数量、工具名还是缺字段 |
| 6 | failed / diagnostic_validation_bypass | attempt 原为 success，后将业务分析标失败；残留 18 条证据不属于正式成功依据 |
| 14 | success | 正式通过当前流程，12 条证据 |

共 10 次入账尝试，1 次正式有效成功、8 次常规失败、1 次诊断旁路排除；证据整理合计 0.453119 元，8 次常规失败合计 0.366842 元。期间代码和提示词发生过修正，不能把这个样本比例当成当前实现的稳定失败率。历史报告提到一次未入账探测，本轮只核实到探测脚本及文档产物，不能仅凭账本确认其准确实际支出。

DeepSeekProvider 还可能产生 configuration/input_limit、connect_timeout/read_timeout/network、parameters/authentication/balance/permission/rate_limit/unavailable/http_error、truncated 等类型；执行器还有 provider_failure、业务保存失败。它们是代码分支，不代表本次真实运行全部发生过。

**失败诊断缺口：**

- schemas.validate 丢掉 jsonschema 的字段路径，只抛统一错误。
- execute_attempts 捕获所有校验 ValueError，统一保存 invalid_schema，并丢掉原错误说明。
- DeepSeekProvider 把多种响应形状/JSON 错误统一为 invalid_response；finish_reason=length 才单独记 truncated。
- AI 调用表不保存失败响应或拒绝文档，因此不能不付费地完整回放历史失败。
- 当前 schema 允许最多 100 条 items，提示词仅要求最多 12；provider_schema 还会移除 minItems/maxItems 等服务商不支持的长度约束。本地仍应完整校验。

**D2：可用确定性代码处理的情况。**

已实现：来源 question_ids 进入材料；同来源另一可见字段逐字命中时纠正 field；同问题下恰好一个其他可见来源命中时纠正 source_id。当前不应重复开发这些逻辑。

可继续改进：同一句在 text/snippet 同时可见时优先归入 text；保留纠正前后记录；对于纠正后完全相同的引用可合并，但必须重新验证独立域名、逐字命中、问题关联和引用数量，不能保留伪造的“两来源”效果。减少正文在句中截断、展示字符范围、让模型直接选短引句，也是确定性的输入构造改进。

**D3：必须拒绝，不能“修成通过”。**

未知/跨任务/跨问题来源，任何可见材料都找不到的引文，只有标题中出现的句子，截断范围之外的正文，存在多个候选来源而无法唯一归属，缺 links、非法字段/类型、无依据日期/周期，只有转载或摘要却标 verified，以及空 inference 等，继续拒绝。不能模糊匹配、自动改写引文、补造时间、删掉失败证据再宣称整批成功，也不能绕过校验或自动降级事实分类来获得成功状态。

**本轮离线复核：**

在内存提取当前 Schema 和 `_validate_evidence` 函数，不导入项目服务；用只读取得的 analysis 14 输入和 run 2 关联，检查三个已保存文档。结果为：

| 文档（均位于 E:\one\ai-hotspot-radar\logs\real-run） | Schema 结果 | 当前语义校验结果 |
| --- | --- | --- |
| evidence_failed_doc.json，18 项 | 通过 | 拒绝：verified 不满足两个独立域名提取原文条件 |
| evidence_failed_doc2.json，14 项 | 通过 | 拒绝：纠正后证据引用重复 |
| probe_evidence_doc.json，19 项 | 4 个 links 数组为空，违反 minItems | 拒绝：Schema 不通过 |

这些是“用当前代码及指定保存输入回放产物”的结果，不是原历史调用逐次失败原因的完整复原。前两个文档也说明“提示词≤12”目前没有硬约束；完整正文命中但模型可见片段未命中的情况仍不能直接放行。

**D4：可以减少输出证据数量，先不拆成多次调用。**

第一步在新版本 Schema 和本地语义校验中统一“总数≤10、每题≤2，缺证据写 gaps”，保持一次调用；允许 0 项，不强迫补造。不要事后静默截断模型输出。这有望减少输出和整批拒绝概率，但可能降低覆盖度，必须以固定样本比较。把输入按问题分成多次调用属于另一步，会重复计划/Schema，可能增加总成本，并涉及单 analysis 依据合并，见 P2。

**D5：失败保留，优先离线修复和精确缓存。**

当前同 action 幂等、running/uncertain 锁和失败费用结算都有；invalid_schema/invalid_response 不在自动可重试错误内。多次费用主要来自人工新动作再次调用，不能误写成系统自动连重试十次。

_generate 当前总是 force=True，仅同 action 复用，不能跨新 action 命中成功缓存；fingerprint 也没包含真实提示词内容/版本。建议先补结构化诊断及拒绝文档，再对完全相同输入采用成功缓存。缓存不能跨搜索 run、提示词/Schema、模型或截断窗口版本复用，也不能使用 failed/uncertain 批次。不能只把 force 改为 False：当前代码还必须正确处理 claimed.cache_hit 并提前返回，否则会试图再次预占已完成分析。

**D6：credits 已按每次响应保存，未知不补零。**

_request 读取 payload.usage.credits，经 credit_value 拒绝 bool、负数、NaN/无穷等；search/extract Reply 携带 credits；服务层每次 call_finish 存入 TEXT。HTTP/结构错误带可得 credits；网络失败保留 None。search_usage 用 Decimal 汇总 search/extract，排除 usage 请求，页面显示已知合计和未知次数。

官方 Extract 文档说明小批次响应 credits 可能为 0，不能把它替换为估算 1；缺失也不能用 0 填补。`/usage` 返回账户和 Key 聚合信息，不能直接归因到一个研究动作。现有逻辑已区分这两个用途。[Tavily Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)、[Tavily Usage](https://docs.tavily.com/documentation/api-reference/endpoint/usage)。

目前 request_id 主要保存在成功响应；错误侧 SearchError 不携带 request_id，适合后续补诊断。call.response_json 是适配后的结果，不是完整原始 HTTP 响应，不能宣称“全部原始字段原样保存”。

## 3. 五类质量问题的根因，以及第六项用量口径

| 问题 | 已确认的直接原因 | 不能由当前证据确认的部分 |
| --- | --- | --- |
| ① BBC 旧快照 | 只信任服务商 extract 返回；没有独立原站复核、缓存年龄或更新比较；本地时间不能证明内容新鲜 | Tavily 当时为何给旧版、BBC 此刻最新内容、是否因地区/解析变体导致 |
| ② 日期“未取得” | organize_evidence 和 generate_report 同时漏传 published_at；提示词没有数据库元数据补充通道 | 模型每一句具体生成原因无法唯一证明，但信息缺口本身确定 |
| ③ 2024 Oracle 混入 2026 | 无发布日期输入、无数据周期字段、无逐条历史标签/用途约束；检索窗口不限；引用校验不检查时效 | 仅用文章日期无法可靠推断具体财季，不能自动把旧数字解释成某个新财年 |
| ④ 首轮 query 漫长 | keywords + 整段 question + source_types 无条件拼接；无法查看和覆写最终 query | 优化后能否稳定命中某目标，需要冻结样本和后续授权实测 |
| ⑤ 证据整理反复失败 | 初期缺 question_ids（现已修）；短前缀材料与长输出、逐字引用约束冲突；标签/来源错误、非法结构、泛化错误记录、失败文档不留存 | 12/13 的 exact invalid_response 原因；当前版本真实成功率和费用降幅 |
| ⑥ usage 与本次费用不对应 | usage 是服务商聚合额度参考，本地不能保证其时效；逐次响应已另有账本 | 聚合接口延迟、账户外调用和最终服务商账单的完整归因 |

## 4. 关键代码位置

以下是本次审查时的行号；计划中的新文件尚不存在。

| 文件与位置 | 函数/对象 | 与本次问题的关系 |
| --- | --- | --- |
| [service.py:91](E:/one/ai-hotspot-radar/services/research/service.py:91) | ResearchService.search | 幂等、配额、query 构造、调用保存、再次提取 |
| [service.py:184](E:/one/ai-hotspot-radar/services/research/service.py:184) | organize_evidence | 来源关联和前缀截断；漏发日期 |
| [service.py:216](E:/one/ai-hotspot-radar/services/research/service.py:216) | _validate_evidence | 逐字校验、字段/来源纠正、verified 门槛 |
| [service.py:258](E:/one/ai-hotspot-radar/services/research/service.py:258) | generate_report | 来源只发 id/title/domain |
| [service.py:294](E:/one/ai-hotspot-radar/services/research/service.py:294) | _generate | force=True、指纹、模型账本与版本保存 |
| [base.py:9](E:/one/ai-hotspot-radar/services/research/base.py:9) | SearchResult / ExtractResult | 仅搜索结果有 published_at；无修改/抓取时间 |
| [tavily.py:39](E:/one/ai-hotspot-radar/services/research/tavily.py:39) | _request | 逐次 usage.credits、HTTP 错误 |
| [tavily.py:66](E:/one/ai-hotspot-radar/services/research/tavily.py:66) | search / extract / usage | 日期映射、正文提取、聚合额度 |
| [prompts.py:5](E:/one/ai-hotspot-radar/services/research/prompts.py:5) | SYSTEM / messages | 不可信材料隔离、禁止造日期、12 项软限制 |
| [schemas.py:21](E:/one/ai-hotspot-radar/services/research/schemas.py:21) | QUESTION / EVIDENCE_SCHEMA / REPORT_SCHEMA | 无最终 query、时间语义；items 上限 100 |
| [schemas.py:40](E:/one/ai-hotspot-radar/services/research/schemas.py:40) | validate | 丢失 jsonschema 具体错误路径 |
| [guards.py:37](E:/one/ai-hotspot-radar/services/research/guards.py:37) | current_basis / validate_report | 仅选成功证据、校验报告引用批次，不校验数据时效 |
| [research_store.py:48](E:/one/ai-hotspot-radar/database/research_store.py:48) | search_usage | Decimal 汇总，usage 请求排除 |
| [research_store.py:55](E:/one/ai-hotspot-radar/database/research_store.py:55) | save_sources | 混合哈希、快照去重、searched_at 的实际含义 |
| [research_store.py:85](E:/one/ai-hotspot-radar/database/research_store.py:85) | evidence / insert_evidence | 引用连接及偏移；未返回时间语义 |
| [research_migration.py:39](E:/one/ai-hotspot-radar/database/research_migration.py:39) | research_sources DDL | 当前字段、唯一约束 |
| [research_migration.py:85](E:/one/ai-hotspot-radar/database/research_migration.py:85) | 历史保护触发器 | 旧证据和来源不能更新/删除 |
| [migrations.py:21](E:/one/ai-hotspot-radar/database/migrations.py:21) | migrate | 版本 5、备份与事务；只接受 0/2/3/4 的升级入口 |
| [store.py:22](E:/one/ai-hotspot-radar/database/store.py:22) | HotspotStore.__init__ | 构造会写表并迁移，因此本轮禁止用它查询真实库 |
| [executor.py:12](E:/one/ai-hotspot-radar/services/ai/executor.py:12) | execute_attempts | 用量先结算；校验失败统一 invalid_schema |
| [deepseek_client.py:40](E:/one/ai-hotspot-radar/services/ai/deepseek_client.py:40) | complete | 工具/JSON/截断解析与固定错误 |
| [schemas.py:45](E:/one/ai-hotspot-radar/services/ai/schemas.py:45) | provider_schema | 移除服务商不支持的长度约束，本地约束仍须保留 |
| [ai_store.py:67](E:/one/ai-hotspot-radar/database/ai_store.py:67) | claim_analysis / finish_attempt | 成功缓存、动作锁、费用及失败记录 |
| [research.py:67](E:/one/ai-hotspot-radar/pages/research.py:67) | _plan_editor / _search_area | 计划版本确认、草稿门禁、缺 query 预览 |
| [research.py:162](E:/one/ai-hotspot-radar/pages/research.py:162) | _evidence_area / _report_area | 日期显示仅在来源区；报告逐条引文无时间上下文 |
| [version_service.py:28](E:/one/ai-hotspot-radar/services/production/version_service.py:28) | create / restore | 新 JSON 必须兼容保存、历史恢复和共用门禁 |
| [test_research_workflow.py:115](E:/one/ai-hotspot-radar/tests/test_research_workflow.py:115) | 关联/字段/标题/来源纠正测试 | 现已覆盖的修正，不应回退 |
| [test_research_workflow.py:360](E:/one/ai-hotspot-radar/tests/test_research_workflow.py:360) | 快照变化测试 | 已断言新旧 source_id 和旧快照保留 |

## 5. 技术选型与最小改动策略

继续使用现有 Python、SQLite、Streamlit、requests、jsonschema、pytest；本期不引入 SDK、数据库框架、向量库、浏览器抓取框架或新模型。优先确定性本地处理，复用现有计划/报告 JSON 版本、research_sources、研究调用记录与统一 AI 费用账本。

推荐把实施拆成 P0 可验收质量修复、P1 时效/复用增强、P2 独立抓取和多调用编排。确认方案后才允许执行；本轮不因为完成本文而自动实施。

### 5.1 P0：必须修复

#### P0-1 日期规范化、透传和保守历史标记

- 文件：`E:\one\ai-hotspot-radar\services\research\service.py`、`prompts.py`、`schemas.py`；`E:\one\ai-hotspot-radar\database\research_store.py`；`E:\one\ai-hotspot-radar\pages\research.py`；相应研究测试。可新增仅含纯函数的 `E:\one\ai-hotspot-radar\services\research\temporal.py`。
- 方案：两阶段都发送 published_at 原值及解析结果、date_kind=`provider_estimated_published_or_updated`、本地保存时间、绑定本轮的调用完成时间/运行 ID，并显式发送 modified_at/provider_snapshot_at=`unknown`。解析 ISO 与 RFC 1123；保留无时区或只有日期的精度，不编造时分秒。材料带固定的研究评估时点，写入 input_json；不要把计划检索日期当统计周期。
- 对每条证据/报告引用，由本地代码附来源时间标签；S7/S9 必须逐条显示“2024 年来源，历史材料；数据所属财季/周期尚未核实”，不能只在总风险段泛泛提示。提示词区分历史、估计、预测、当前情况；没有数据周期支持，不宣称是 2026 年统计值。
- 数据库迁移：不需要。旧原值不改写，派生时间在模型输入/页面计算；旧报告正文不自动改动。
- 现有数据：全部保留；旧版本可增加只读附注，说明其原始模型未接收日期。重新生成报告会追加新版本。
- API/费用：调用次数不增加；输入多出少量元数据，Token 成本可能略增，原预算门禁仍负责拒绝过大请求。
- 流程影响：没有新状态；仍需人工审核与确认。此项提供可靠的来源年代警示，不能仅靠它自动识别具体财季或保证自然语言结论正确。
- 测试：RFC/ISO/null/无效日期；两个模型输入都有日期；2024 来源在 2026 议题逐条显示历史标签；未知日期不能显示“本次发布时间”；保存、恢复和历史查看不联网。

#### P0-2 关键词优先 query，并让用户确认实际发送内容

- 文件：`E:\one\ai-hotspot-radar\services\research\service.py`、`schemas.py`、`prompts.py`；`E:\one\ai-hotspot-radar\pages\research.py`；研究流程/页面/Provider 测试。可新增纯函数文件 `E:\one\ai-hotspot-radar\services\research\queries.py`。
- 方案：共用 build_query，默认仅关键词去空白/去重合并；新增可选 query_override。来源类型不自动拼接，完整问题通过人工 override 按需补充。预览包含 query、domains、日期，执行与预览逐字一致。写入计划 JSON，新版本保存、重确认后才能发送；记录 query_builder_version 与实际参数。
- 兼容：历史计划允许缺 query_override，读取空默认；新生成计划使用新 Schema，不能让 strict 工具要求可选字段与本地历史兼容规则相互冲突。可采用“生成版字段必需、旧版读取字段可缺”的两份明确 Schema。历史来源类型字段仍保留。
- 数据库迁移：不需要；复用 content_json/params_json/request_json。
- 现有数据：旧计划/旧 run 不变；旧版恢复追加新版本后按新构造规则预览，再由用户确认，不静默重跑。
- API/费用：不增加调用，query 通常变短；不自动执行关键词翻译或兜底第二次搜索。
- 流程影响：增加研究区每题的实际 query 编辑/预览；沿用已有 session_state、确认与动作幂等机制。
- 测试：长中文问题不进入默认 query；完整英文标题保留；override 生效；空/超长 query 本地拒绝；草稿修改不联网；改 query 新建计划、确认和 run；旧动作只读取旧结果；最终 request_json 与预览一致。

#### P0-3 修正快照内容身份，提供诚实的更新提示

- 文件：`E:\one\ai-hotspot-radar\database\research_store.py`；`E:\one\ai-hotspot-radar\services\research\service.py`；`E:\one\ai-hotspot-radar\pages\research.py`；快照相关测试。
- 方案：新快照哈希显式含 title、published_at 原值、text、snippet、status，以及哈希算法版本；修复成功正文不变而 snippet 丢失的问题。旧哈希保持不动；新规则第一次可能追加等价快照，允许并明确标注算法变化。只在真实收到新结果时写新快照。
- 对已有运行按 URL 比较上一轮关联快照，正文、摘录、标题/日期、提取状态分别展示；失败不解释为“原文删除”；本地附加“尚未独立核验当前原文”提示。差异使用保存文本计算，不调用模型。
- 数据库迁移：不需要；继续使用现有 source_id、call 记录和关联表。
- 现有数据：不重算旧哈希、不改旧引文/offset、不自动修报告；保留所有触发器。
- API/费用：无额外调用或 API 费用；主动重新搜索的成本仍与现有流程相同。存储可能少量增加。
- 流程影响：研究区多出变化提醒；不改变确认与制作状态。只能承诺“保存内容变化提醒”，不能承诺“已检测当前原文所有更新”。
- 测试：正文/日期/标题/仅 snippet 变化；重复内容去重；A→B→A；元数据变化不称正文变化；提取失败不覆盖旧正文；旧报告始终引用旧 source_id。

#### P0-4 持久失败诊断，保留拒绝标准和已发生费用

- 文件：`E:\one\ai-hotspot-radar\services\research\schemas.py`、`service.py`；`E:\one\ai-hotspot-radar\services\ai\base.py`、`deepseek_client.py`、`executor.py`；`E:\one\ai-hotspot-radar\database\research_store.py`、`migrations.py`；新增 `E:\one\ai-hotspot-radar\database\research_quality_migration.py`；研究与 AI Provider 回归测试。
- 方案：保留 invalid_schema/invalid_response 等现有顶层错误，追加研究专用安全诊断：stage、固定 code、JSON path、索引、预期工具是否匹配、finish_reason、响应形状、解析位置。对已解析但拒绝的研究文档保存有大小上限的 JSON 和是否截断的标识，以便和 input_json 离线复核；不保存鉴权头、密钥、完整远程 HTTP 错误正文。
- 校验异常继承 ValueError 携带 code/path；共用执行器只增加可选诊断回调，原选题默认行为保持。Provider 解析错误可携带安全细分信息，不增加重试，不把不符合工具协议的 content 当成成功替代结果。
- 数据库迁移：**需要一次追加式迁移**，建议从 v5 升级至 v6，新建 research_model_diagnostics，关联 ai_analysis_runs；详见第 6 节。若暂不批准迁移，只能做安全日志细分，不能宣称已具备持久回放能力。
- 现有数据：旧错误保留泛化状态，不猜测补回；不修复 analysis 6 的诊断残留行，继续由 failed 状态隔离。
- API/费用：不增加调用或 API 费用；只有小量本地存储。诊断保存失败不能丢掉原费用和主错误，也不能把失败改成成功。
- 流程影响：研究失败后能看到具体原因和本地复核结果；失败历史、Token、费用、未知费用锁都保留。没有模型校验失败自动重试。
- 测试：缺字段、错误工具名/数量、非法 JSON、truncated、逐字引文不符、关联错误分别有诊断；顶层错误/结算保持；诊断持久化故障不掩盖主失败；选题调用回归；日志和记录不含鉴权内容；迁移备份、回滚、幂等与旧库内容保留。

#### P0-5 约束单次输出规模并补齐确定性归一化

- 文件：`E:\one\ai-hotspot-radar\services\research\service.py`、`schemas.py`、`prompts.py`；研究流程测试。
- 方案：新证据 Schema 总数≤10、每题≤2，与提示词和本地验证一致；仍允许 items=[] 并要求 gaps。第一轮继续一次模型调用，避免编排改造。同文句在两个可见字段时优先 text；只合并归一化后完全相同的 link，再完整验证，不删除有问题的证据、不改摘要语义、不弱化 verified。
- 数据库迁移：不需要；新 Schema/提示词版本进入分析记录。旧分析结果按其历史版本读取，不拿新数量上限否定旧历史。
- 现有数据：不改旧证据；失败文档与归一化变化交由 P0-4 留痕。
- API/费用：调用次数不增加；输出通常减少，但不预先承诺成功率或固定节费比例。
- 流程影响：覆盖度和 gaps 更清楚；不是把失败结果截成 10 条后成功。已有逐字校验和多域名约束继续执行。
- 测试：10/11 条边界、每题 2/3 条边界、0 条及 gaps、重复纠正、同文句双字段、纠正后域名不足仍拒绝、多个候选匹配仍拒绝、标题/截断外引文仍拒绝、失败仍结算。

#### P0-6 固定 credits 口径并补回归，保留配额机制

- 文件：`E:\one\ai-hotspot-radar\tests\test_research_provider.py`、`test_research_workflow.py`；`E:\one\ai-hotspot-radar\pages\research.py` 仅在需要时补清楚说明；Provider/Store 主链路已有功能原则上不重写。
- 方案：将“本次响应 credits 汇总”作为研究用量，把 `/usage` 明确标为查询时的账户额度参考；保留现有 quota 门禁、上限估算及未知配额人工选项。显示单 run 和项目合计；pending/partial 的统计不要被误认为全部成功或计量为零。
- 数据库迁移：不需要。
- 现有数据：不更正、不补零、不根据 usage 差额回填，也不把 credits 自动换算进人民币模型预算。
- API/费用：无额外调用和费用，不额外轮询 usage。
- 流程影响：说明和回归保证；不改变用户禁止变动的预算与评分机制。
- 测试：usage 值不变但 search/extract 返回 credits 时仍累计；0、None、小数、非法数；partial、HTTP 错误带 credits、结果结构错误带 credits、网络未知、同动作重入不重复累计；usage 本身不进入研究消耗合计。

### 5.2 P1：建议修复

| 项目 | 涉及文件 | 迁移/已有数据 | API/费用 | 流程影响与测试 |
| --- | --- | --- | --- | --- |
| P1-1 结构化数据周期与报告用途 | 研究 schemas/service/prompts/temporal、research_store、研究页面与 guards 的报告校验；对应测试，均在上述项目根目录下 | 无须改表：新 evidence 的 time_context 放 analysis_json，按 position 与 evidence 对齐读取；报告 claim 的 temporal_usage 放版本 JSON；旧数据缺失为 unknown，不能伪造回填 | 无新增调用；多出少量 Token | time_context 至少含 period_label、actual/forecast/unknown、原文时间引用 links；已知周期必须逐字命中模型可见材料。报告逐项 current/historical/forecast/unknown，禁止未知/明确历史周期作为当前值；人工编辑同样校验。测试财年与自然年、预测年份、文章日≠财季、跨年区间、未知值、旧版恢复兼容；自然语言语义仍需人工审核 |
| P1-2 逐次来源观察记录 | research_quality_migration、research_store、research service/页面 | 需要新增 research_source_observations；若与 P0-4 一起获批可合并一次 v6，否则再递增版本。旧快照不改，历史观察时间缺失保持未知 | 无新增调用，仅现有请求完成时记录；增加本地存储 | 每次提取即使内容相同也留观察记录，关联 run/call/source；解决去重后丢失最近观察时间及 A→B→A 顺序。测成功/失败/重复观察、跨项目外键、旧快照不可变和历史推断标识 |
| P1-3 完全相同输入的成功缓存 | research service._generate、prompts；流程测试。尽量复用 AIStore，不改预算算法 | 无迁移；保留所有旧分析和失败费用 | 命中不调用、不新增费用；主动强制生成仍计费 | 指纹含实际 prompt 或其哈希、Schema/材料窗口/查询版本、完整输入、run/basis、模型与模式；正确处理 cache_hit 提前返回。默认复用成功结果，明确主动重新生成可绕过；failed/uncertain 不复用。测试版本改变失效、失败留痕、并发锁、命中不预占、最新依据可正常引用 |
| P1-4 以段落/句边界选证据窗口 | research service；可新增纯函数材料选择模块；流程测试 | 无迁移；原正文和 offsets 保留，input_json 保存实际窗口及范围 | 不增加调用；相同字节预算内调整，Token 可能有变化 | 优先含关键词、数字及相邻时间上下文的有限原文段，不拼成伪造连续引句；跨段引用须各自独立。完整 request_body 仍过 reservation_units。测试句中截断、日期邻近段、窗口间拼接不得引用、中文20来源及超限拒绝 |
| P1-5 可选择的服务商搜索新鲜度 | TavilyProvider.search、计划 Schema/研究页面、参数记录与 Provider 测试 | 无数据库迁移；新参数进入确认计划和实际请求；旧 run 保留 | 不新增 search 次数；官方当前称 max_age_hours 不额外加 credits，但有更高延迟/更少结果/容量拒绝风险；以响应计量为准 | 作为显式研究参数，不默认升级/重试。官方 max_age_hours=0 可要求搜索抓实时内容，但其契约不适用于当前独立 extract 请求，不能据此声称两阶段正文必为最新。测试参数透传、少结果、434 等失败不悄悄回退缓存；实施时再核对服务商契约 |

P1-1 不应根据“文章发表于 2024”推导“统计周期一定为 2024”。文章年代警示由 P0 完成，数据周期必须有单独依据；研究参考时间也需明确保存，机器无法可靠解析目标周期时保持 unknown。

Tavily Search 当前公开说明了 max_age_hours 的缓存策略；项目尚未使用该参数。本轮仅核对文档，没有验证账户是否支持或实际返回是否达到目标。[Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)。

### 5.3 P2：可以延后

| 项目 | 涉及文件 | 迁移/已有数据 | API/费用 | 流程影响与测试 |
| --- | --- | --- | --- | --- |
| P2-1 独立原站版本复核 | 新研究网页复核 Provider/服务、base、store、页面和迁移；不复用危险诊断脚本 | 需要独立检查/原站快照记录，不能把 HTML 的哈希直接与 Tavily 纯文本哈希比较；旧证据保留原类型 | 每个选择复核 URL 增加 HTTP 请求；若用 Tavily 补提取还产生 credits；本地 HTML 解析本身无模型费 | 用户显式复核，保存最终 URL、HTTP 状态、原始时间元数据、解析器版本和正文摘要，区分403/失败/未变/变化。遵守域名、DNS/IP和每次重定向验证、响应大小/超时等边界；现有 public_url 只适合已有用途，不能直接视为完整直连抓取防护。固定 HTML、重定向、私网解析、无日期、304、页面变体及限流测试；不自动改变工作台状态 |
| P2-2 按问题拆模型调用与局部重做 | research service/Schema/store/current_basis 与共用执行器的研究适配；新增批次编排测试 | 需要显式父批次/子调用和聚合完成依据，可能迁移；不能简单为每题建立独立成功 analysis 后只取最新一题 | 一轮由1次变N次，重复计划/Schema可能更贵；失败只重做一题有潜在节约，必须实测 | 全部子批次通过后形成单一有效依据，已成功子结果可复用、失败账本完整、逐次预算照旧。测部分失败/中断/并发、只重做失败部分、合并引用、计划变更与费用未知锁 |
| P2-3 更精细来源独立性和转载版本关联 | 研究 validator、来源元数据及测试 | 简单域名解析可无迁移，转载关系若持久保存需迁移；旧证据不重分类 | 本地规则无调用；自动追索原始转载链可能增加搜索费，需另定范围 | 现有最后两段域名启发式不能证明编辑独立，也可能误判公共后缀。此项超出本次主要时效修复，保持现有门槛并明确人工核验；用公共后缀、转载同稿、同集团样本验证，不能偷偷调整评分机制 |

## 6. 数据库字段与迁移建议

### 6.1 P0 无迁移部分

- 不给 research_sources 的旧行回填修改日期、原站抓取时间或数据周期。
- 保留 published_at 原始值；规范化结果和日期含义在新的 input_json 保存，页面可即时派生。
- query_override、构造器版本放计划版本/运行参数 JSON，最终 query 仍进入每次请求记录。
- P1 新周期结构先放现有 analysis_json；research_store.evidence 需要按 analysis_id/position 读取该结构，不能只扩 Schema 却在数据库读出时丢掉。
- 历史 v1 和新 Schema 分开识别。新增格式/版本标识及可选字段后，通用 version_guard、人工保存和历史恢复都要有明确兼容分支，不能因为 additionalProperties=False 把全部旧版本变成无效数据。

### 6.2 建议 v5→v6：research_model_diagnostics（P0-4）

建议最小字段：

| 字段 | 用途 |
| --- | --- |
| id、project_id、analysis_id、attempt_run_id | 关联既有研究分析和费用尝试；不复制预算/价格字段 |
| stage、code | 固定枚举，例如 provider_parse/json_decode、validation/quote_not_visible |
| details_json | 安全 JSON path、条目索引、命中情况、长度/截断信息；CHECK(json_valid) |
| rejected_document_json | 可空、有限大小的已解析拒绝文档；专用于离线诊断，不是成功 analysis_json |
| document_truncated | 是否完整保留，禁止把截断诊断当完整可回放样本 |
| created_at | 本地诊断保存时间 |

建议 `(attempt_run_id,stage)` 唯一，防重复保存；通过复合外键或写入校验保证 project/analysis/attempt 同属一条研究链，不能只验证每个 ID 各自存在。只追加保护覆盖诊断表。原错误、尝试状态和费用仍在原表；诊断表不是第二套账本。

### 6.3 P1 增强：research_source_observations

建议字段：id、project_id、run_id、call_id、source_id（失败可空）、url_key、provider、observed_at、status、published_at_raw、published_at_normalized、date_kind、origin_published_at、origin_modified_at、origin_fetched_at、provider_snapshot_at、body_hash、snippet_hash、metadata_json。

- observed_at 是本地收到结果的时间；source_id 表示哪份保存内容被观察到。即使同内容复用 source_id 也追加观察。
- origin_* 只有独立原站复核或可信原文元数据依据时才填写；在 P2 之前通常为空。provider_snapshot_at 只能接受服务商明确提供的真实时刻。
- 元数据出处及原始字面值进入 metadata_json。HTTP Last-Modified 单独保存，不能覆盖 origin_modified_at。
- 旧数据若仅从 call.finished_at 推导，必须标 inferred_from_call；不能伪装为当时精确观测，最小实现可以完全不补历史观察。
- 提取失败的观察不产生空正文“新版”覆盖成功快照；保存失败状态并关联请求。
- 检索上一版本按观察/运行顺序，不能用 source_id 排序替代时间线。

### 6.4 迁移实施约束

不得直接把现有 v5 create_research_tables 重跑。当前 migrate 对 version=5 直接返回、合法升级源仅 0/2/3/4；升至 v6 时必须显式加入 5→6，旧版本升级链也要接上新的追加 DDL，并调整备份命名，保持同一事务、失败回滚、备份与幂等。

保留全部旧列值、source/evidence/version/confirmation ID、费用、评分、预算设置和制作状态。不能为新增字段临时撤销旧表 UPDATE/DELETE 触发器做无依据回填。本轮未执行此迁移，也未建立备份文件。

## 7. 风险及不能仅靠当前代码可靠解决的问题

1. **最新网页内容不可由旧快照推知。** 没有新增且可靠的原站/服务商实时读取，不能保证 BBC 已更新内容被获取；再跑同一 extract 可能仍拿到旧缓存。
2. **published_date 的语义不等于 datePublished。** 当前官方契约允许发布或更新估计；P0 必须以估计日期标识，不能“修复传日期”后又制造另一种精确性假象。
3. **数据周期无法从文章时间机械推断。** 发布于 2026 的文章可能引用 2024 财季，也可能预测 2027；P0 的来源年代标记不能替代 P1 的数据周期引文。
4. **自然语言是否把历史值暗示为现状不能完全自动证明。** 结构化用途与确定性标签可约束，仍需要人工事实审核；逐字引文校验不验证摘要是否被正确解释。
5. **2026 年最新季度财报和原始数字本轮没有外部核实。** 不给出投资判断，不替换 Oracle 数值。403、页面动态渲染和地域变体也不能通过数据库设计解决。
6. **历史解析失败不可完整还原。** analysis 12/13 没有原始响应；新诊断只能改善未来记录，不能声称已定位某个确定 JSON 字符或工具名错误。
7. **缩小证据规模可能减少覆盖。** 单题上限和总数上限要通过 gaps 清楚反映；不得用少列证据掩饰关键问题未回答。多个调用的总费用不必然更低。
8. **缓存可能误复用。** 必须包含实际提示词、Schema、run/basis 和材料窗口；研究日期、query 或来源变化都可能需要重新生成。仅复用成功且依据完全匹配的结果。
9. **哈希差异不等于事实被更正。** 标题、广告、格式和摘录变化都会影响保存内容；只有正文/数据上下文比较和人工判断才能解释数字是否改变。不得把 Tavily 文本和原站 HTML 的原始 SHA 直接等同比较。
10. **额度快照不等于账单。** 逐次 credits 对本项目已记录请求可追溯，不能补足未入账探测、其他进程/账户调用或未知请求费用；官方账单仍是最终核对来源。
11. **当前工作区有大量既有修改及未跟踪开发文件。** 本轮基于它们审查，未尝试重置、清理或重新构建。实施必须保留并在确认后的基线上继续；不能把全部工作区变化算作本期提交。
12. **共享 AI 模块修改存在回归面。** 诊断接口必须可选，只服务于研究时启用；不改价格、预算预占、重试次数或未知费用结算。任何涉及状态门禁的改动仅限新 JSON 格式校验，不能改变制作阶段管理。

## 8. 实施顺序、测试与验收标准

### 8.1 建议实施顺序

1. 确认本方案中 P0 范围及唯一必要诊断迁移；P1/P2 单独选择，不默认全部实施。
2. 在保护现有未提交修改的基线上，补离线失败样本与日期/query/快照回归测试，确保 RED 来自目标缺陷而非环境错误。
3. 完成 P0-1/2/3：日期链路、query 和快照提醒；不触发网络验收。
4. 完成 P0-4：安全诊断及 v6 迁移代码，仅在临时库演练。
5. 完成 P0-5/6：输出边界、确定性归一化、credits 口径回归；更新研究 prompt/schema/算法版本。
6. 运行相关测试和必要的共用模块回归，核对实际差异；提交可审阅结果。真实库迁移与真实 API 测试必须另获明确授权，不因方案获批就自动执行。

### 8.2 计划中的自动化测试

未来实施时，测试隔离必须使用显式假 Provider/AISettings 和临时数据库；网络入口失败即终止测试，并避免 app 配置在测试时加载真实 `.env`。只对临时测试进程做隔离，不移动/改写用户 `.env`，不改变真实环境或预算设置。

| 测试组 | 现有文件/建议位置 | 必须覆盖 |
| --- | --- | --- |
| 日期与历史性 | E:\one\ai-hotspot-radar\tests\test_research_workflow.py；可新增 test_research_temporal.py | RFC/ISO/日期精度、unknown、两阶段透传、2024来源逐项标签、周期与发布日分离 |
| query | E:\one\ai-hotspot-radar\tests\test_research_workflow.py、test_research_page.py、test_research_provider.py | 关键词优先、override、预览等于发送、保存确认、新 run、草稿与旧 action |
| 快照/版本 | E:\one\ai-hotspot-radar\tests\test_research_workflow.py、test_research_migration.py | 仅 snippet变化、A→B→A、同URL多次提取、失败、不改旧引文和报告 |
| 严格引用 | E:\one\ai-hotspot-radar\tests\test_research_workflow.py | 原有4项修正测试继续通过；双字段、唯一来源、歧义拒绝、标题与不可见原文拒绝、verified约束 |
| 输出规模 | E:\one\ai-hotspot-radar\tests\test_research_workflow.py | 总数与单题边界、空证据、gaps、本地与Provider Schema差异、失败不静默裁剪 |
| 失败诊断/计费 | E:\one\ai-hotspot-radar\tests\test_research_provider.py、test_ai_provider.py、test_ai_budget.py | 解析子类型、错误path、文档上限与保密、诊断存储失败、失败先结算、未知费用仍保留 |
| 迁移 | E:\one\ai-hotspot-radar\tests\test_research_migration.py 或新增质量迁移测试 | v5→v6、旧版链路、一次备份、重复启动幂等、故障回滚、外键、触发器和原字段不变 |
| credits | E:\one\ai-hotspot-radar\tests\test_research_provider.py、test_research_workflow.py | 聚合usage不动但逐次累计正确；0/None/小数/非法计量；partial/HTTP错误/网络异常/重入 |
| 制作状态与旧功能 | E:\one\ai-hotspot-radar\tests\test_research_page.py、test_production_service.py、test_production_versions.py；AI相关测试 | 确认仍为本地操作、刷新不联网、暂停/归档只读、旧依据门禁、共用预算和评分规则不变 |

相关测试全部通过后，仅当共用模块变化或失败迹象需要时执行更广回归；不要无意义重复有效结果。测试通过不证明真实服务商响应、最新原文和生产费用一定符合预期，不能虚构线上验收。

### 8.3 P0 验收标准

- [ ] 两阶段模型输入含来源日期原值、规范化值和语义标识；不存在“库有日期、上下文没有”的情况。
- [ ] S7/S9 类历史来源逐条显示具体年份；数据周期未核实时明确未知，不能以文章日期补造财季。
- [ ] 最终 query 可见可改；默认无整段中文问题/来源类型拼接；改后经过新版本、确认和新 run，旧调用历史保持。
- [ ] 正文相同但新摘录不同不会丢失；旧证据/报告仍能解析到原快照和 quote_offset。
- [ ] 更新提醒区分保存内容变化、元数据变化和无法核验；无新抓取不能显示“已确认当前原文最新”。
- [ ] 新研究失败有可定位的固定代码/path和可得拒绝文档；失败记录、Token、费用和未知用量均保留。
- [ ] 新证据总数≤10、每题≤2；结构不符整批拒绝，不通过删条目或模糊匹配换取成功。
- [ ] 引文必须位于实际发送材料；标题、歧义来源、未发正文、缺链接及不合格 verified 继续拒绝。
- [ ] credits 取每次响应；已知合计、0和未知分开；usage不参与本次消耗计算，不额外轮询。
- [ ] 临时库迁移验证通过，生产库未自动迁移；评分、预算、制作状态管理及用户已有文件/改动未被改写。
- [ ] 实际测试结果与未验证项如实记录；只有获授权的本期文件进入后续提交。

## 9. 本轮执行结果与交付

- 完成真实代码、Schema、迁移、调用链及测试静态审查；使用只读连接核对真实 Schema、研究输入、错误类型、证据批次和逐次 credits。
- 对三个保存的证据文档执行了内存离线校验，结果均被当前校验规则拒绝，具体原因见 2.4；没有调用模型或网络 API。
- 未运行 pytest、未启动应用、未执行迁移、未修改数据库/配置/环境变量，未读取 `.env`，未清理任何已有文件。
- 唯一新建交付文件：`E:\one\ai-hotspot-radar\REPORT_PHASE4_2_1_1_AUDIT.md`。
- Git：没有暂存或提交；本轮之前已存在的修改和未跟踪文件保留。
- 待确认：P0 实施范围及诊断迁移；P1/P2 是否另行安排。本文不表示代码已经修复，也不表示已独立验证当前 BBC 或 Oracle 原文。
