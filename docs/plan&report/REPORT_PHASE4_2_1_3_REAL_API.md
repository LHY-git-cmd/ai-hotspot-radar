# 第四阶段 4.2.1.3：真实 API 研究质量验证报告

- 项目：ai-hotspot-radar；目录：`E:\one\ai-hotspot-radar`。
- 正式数据库：`E:\one\ai-hotspot-radar\data\hotspots.sqlite3`；v6。
- 日期：2026-11-03 19:58:37（北京时间）。
- 主题：2026年AI投资行业议题中，核查涉及2024年Oracle历史数据的资料。
- 执行结果：**计划、搜索和提取成功；证据整理被正式校验拒绝；按要求停止，未重试、未调用报告模型。**

## A. 调用统计、预算与执行边界

### A1. 前置检查

工作目录与Git根目录均为E盘项目；真实库user_version=6，integrity_check=ok，foreign_key_check无错误。22个P0验收文件的SHA-256全部一致。

执行前没有running或uncertain的模型分析，也没有running的研究搜索。旧项目#1与视频选题#9、旧计划、来源、证据、报告能正确关联；项目状态researching。

现有DeepSeek月预算100元，执行前已结算估算0.602463元，可用99.397537元，预占0，未知费用0。未重置或修改预算、阈值、价格或模型配置。DeepSeek与Tavily Key存在且本次正式请求鉴权成功，未打印Key。

凭据使用dotenv_values在内存解析、环境现值优先；未调用load_dotenv，未改.env或os.environ。驱动限定网络只可访问既有DeepSeek/Tavily端点。

### A2. DeepSeek真实尝试

模型：**deepseek-flash**；strict工具输出，thinking disabled，沿用现有价格与预算配置。每阶段最多一次真实请求；驱动仅把可重试错误的retryable权限设为false，以执行本轮“不得自动重试”的明确要求，没有修改生产代码或全局max_attempts。

| 阶段 | analysis / attempt ID | 调用 | 输入Token | 输出Token | 缓存命中/未命中 | 状态 | 本地结算费用（元） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 研究计划 | 16 / 16 | 1 | 2,181 | 906 | 0 / 2,181 | success | 0.011610 |
| 证据整理 | 17 / 17 | 1 | 8,500 | 3,621 | 256 / 8,244 | failed，invalid_schema | 0.045467 |
| 研究报告 | 未创建 | 0 | 0 | 0 | — | 前置失败，未调用 | 0（无调用） |
| 合计 | 2次真实请求 | 2 | **10,681** | **4,527** | 256 / 10,425 | — | **0.057077** |

失败调用费用：**0.045467元**。费用使用真实响应Token和现有price_json结算，属于项目账本的估算人民币费用，不是已下载的服务商最终账单；本轮未查询发票或服务商账单。没有未入账探测调用。

执行后本月已结算估算 **0.659540元**，可用 **99.340460元**；held_units=0、unknown_usage_runs=0。既有ai_budget_settings所有字段逐值保持不变。失败尝试已结算，没有把未知用量记为0。

### A3. Tavily逐次真实消耗

| call ID | 操作 | 问题 | 结果 | 响应credits |
| --- | --- | --- | --- | --- |
| 15 | usage | 整轮 | success | 不作为消耗计量 |
| 16 | search | Q1 | success | 1 |
| 17 | search | Q2 | success | 1 |
| 18 | search | Q3 | success | 1 |
| 19 | search | Q4 | success | 1 |
| 20 | extract | 整轮 | success | 2 |

实际 **search 4次、extract 1次，合计6 credits**（search=4、extract=2）；无重试、无追加搜索、无扩域、无额外付费搜索、无未知credits。

/usage仅调用1次，返回账户额度参考984。每次计费请求前检查本轮已知消耗、30 credits本地上限、初始额度参考扣减本轮消耗以及下次保守上限；search按1、12URL basic extract按最多3预留。实际extract返回2，按2入账，未替换为预估3。

/usage不是本次消耗或实时账单。本轮最终本地上限余量24 credits；不能将984-6解释为当前服务商实时余额。未因仍有余量而继续调用。

## B. 研究计划、搜索与保存结果

### B1. 项目与计划

使用项目#1「AI 成本争议：两种解读各站什么证据（真实研究跑通）」，关联选题#9「AI 花钱太猛 vs 只是正常投入：两种解读，各站什么证据」。没有创建脚本或进入其他制作模块。

模型生成计划v4（version ID=5，source=ai）。审阅发现将52%/336%泛称为RPO数据、以及“2024财年”可能排除2024日历年末FY2025资料，进行了正常人工计划修订，保存v5（version ID=6，source=manual）；没有改动模型校验或原计划历史。

研究目标：核查2026当前议题、2024历史RPO/云业务/GPU数字的口径与实际财季；历史不能作为2026现状。

研究重点：文章日期、实际财季、当前值和预测分开；区分官方财报、二手转述、观点与推断。全局start_date/end_date留空，显式保留历史范围；问题数固定4，不追加搜索。

核实清单包括：29%/$80B、52%和336%的实际指标归属/周期；两篇二手文章需官方原文核验；2026披露是否存在及其财季/指引；行业争论是否有依据；文章日不可代替数据周期。

使用现有confirm_plan确认v5，产生confirmation ID=3。使用新的action_id前缀 `quality-p0-fd86b8fa8c6c4141a8a4077ee255bee2`，新建search run #3，绑定plan_version_id=6。未复用旧确认执行新query。

### B2. 实际问题与query

query_builder_version=`keywords-v2`，四题query_override均为空，执行关键词优先路径。没有自动拼接问题或source_types。

| 问题 | 人工确认的问题 | 实际发送query（与预览逐字一致） | 域名范围 |
| --- | --- | --- | --- |
| Q1 | Oracle 官方财报中，2026 年可对应的 RPO、云业务收入与资本开支披露有哪些？其发布日期、实际财季、当前值与公司指引（预测）是否在原文中明确区分？ | `Oracle earnings 2026 RPO cloud revenue capital expenditures` | investor.oracle.com, sec.gov |
| Q2 | Oracle在2024日历年发布的财报（可能属于FY2024或FY2025）中，RPO、云业务和GPU相关数据分别对应什么实际财季？重点核对2024年3月及12月的官方原文，不能把日历年当财年。 | `Oracle fiscal 2024 third quarter fiscal 2025 second quarter RPO GPU 336%` | investor.oracle.com, sec.gov |
| Q3 | Valuentum 2024-12-10文章中52%、336%分别属于哪项指标、实际财季和增长口径？不要预设为RPO增长；该文为二手分析，需要什么官方原文核验？ | `Oracle Remaining Performance Obligations RPO Growth Valuentum 2024` | valuentum.com |
| Q4 | Cloud Wars 2024-03-12 文中「Oracle RPO Jumps 29% to $80 Billion」对应哪个实际财季、何种口径，且数量级是否与 Oracle 官方同期披露一致？该数字不得用于描述 2026 年情况。 | `Oracle RPO Jumps 29% to $80 Billion Cloud Wars` | cloudwars.com |

四条query与query-preview.json、run.params_json、每次call.request_json逐字比对一致。使用页面同一个build_query纯函数生成预览；本轮通过服务层驱动真实调用，没有额外声称已人工浏览器点击页面。

### B3. 检索质量与提取

4题各返回3条，共12个来源URL；一次批量提取12个URL，12成功、0失败。HTTP结果与每URL正文状态分别保存；搜索摘录和服务商提取文本独立，不把摘录冒充全文。

- Q1命中3份2026年Oracle官方稿，其中2026-09-10的Q1稿实际为FY2027 Q1：日历年与财年不同。
- Q2命中2024-12-09 FY2025 Q2官方原文及其URL变体；还带回2025-03-10 FY2025 Q3，不完全符合2024日历年目标。**未命中2024年3月的FY2024 Q3官方目标原文。**
- Q3命中Valuentum目标历史文章及其URL变体，另有FY2024 Q4分析页。
- Q4命中Cloud Wars目标历史文章及URL变体，另有2025年RPO综述。
- 基本均在Oracle/RPO主题内，没有首轮旧测试那类泛化中文页面，但存在偏离年份和重复内容。不能在不同问题和范围下声称已经定量证明比旧查询更优。

本轮12个来源不等于12个独立证据来源：Oracle官方同文异URL、Valuentum同文异URL、Cloud Wars同文异路径均存在。

| 来源 | 数据库真实标题与URL | 服务商日期原值 | 提取 |
| --- | --- | --- | --- |
| S19 | [Oracle - Oracle Announces Record Q4 and FY 2026 Results Driven by Cloud Infrastructure & Cloud Applications](https://investor.oracle.com/investor-news/news-details/2026/Oracle-Announces-Record-Q4-and-FY-2026-Results-Driven-by-Cloud-Infrastructure--Cloud-Applications/default.aspx) | Wed, 10 Jun 2026 00:00:00 GMT | 成功 |
| S20 | [Oracle - Oracle Announces Fiscal Year 2026 Third Quarter Financial Results](https://investor.oracle.com/investor-news/news-details/2026/Oracle-Announces-Fiscal-Year-2026-Third-Quarter-Financial-Results/default.aspx) | Tue, 10 Mar 2026 00:00:00 GMT | 成功 |
| S21 | [Oracle - Oracle Announces Q1 Results Driven by Triple Digit Growth in Cloud Infrastructure Revenues](https://investor.oracle.com/investor-news/news-details/2026/Oracle-Announces-Q1-Results-Driven-by-Triple-Digit-Growth-in-Cloud-Infrastructure-Revenues/default.aspx) | Thu, 10 Sep 2026 00:00:00 GMT | 成功 |
| S22 | [Oracle - Oracle Announces Fiscal 2025 Second Quarter Financial Results](https://investor.oracle.com/investor-news/news-details/2024/Oracle-Announces-Fiscal-2025-Second-Quarter-Financial-Results/default.aspx) | Mon, 09 Dec 2024 00:00:00 GMT | 成功 |
| S23 | [Oracle - Oracle Announces Fiscal 2025 Second Quarter Financial Results](https://investor.oracle.com/investor-news/news-details/2024/Oracle-Announces-Fiscal-2025-Second-Quarter-Financial-Results) | unknown | 成功 |
| S24 | [Oracle - Oracle Announces Fiscal 2025 Third Quarter Financial Results](https://investor.oracle.com/investor-news/news-details/2025/Oracle-Announces-Fiscal-2025-Third-Quarter-Financial-Results/default.aspx) | Mon, 10 Mar 2025 00:00:00 GMT | 成功 |
| S25 | [Oracle Misses in Q4 But Bookings Performance and Outlook Strong – Valuentum](https://valuentum.com/oracle-misses-q4-bookings-performance-and-outlook) | unknown | 成功 |
| S26 | [Oracle’s Remaining Performance Obligations (RPO) Growth Speaks to Accelerated Expansion – Valuentum](https://valuentum.com/oracles-remaining-performance-obligations-rpo-growth) | Tue, 10 Dec 2024 00:00:00 GMT | 成功 |
| S27 | [Oracle’s Remaining Performance Obligations (RPO) Growth Speaks to Accelerated Expansion – Valuentum](https://www.valuentum.com/articles/oracles-remaining-performance-obligations-rpo-growth) | unknown | 成功 |
| S28 | [Oracle RPO Jumps 29% to $80 Billion, but Capacity Constraints Persist](https://cloudwars.com/cloud/oracle-rpo-jumps-29-to-80-billion-but-capacity-constraints-persist) | Tue, 12 Mar 2024 15:00:00 GMT | 成功 |
| S29 | [Oracle RPO Jumps 29% to $80 Billion, but Capacity Constraints Persist](https://cloudwars.com/cloud-wars/oracle-rpo-jumps-29-to-80-billion-but-capacity-constraints-persist) | Tue, 12 Mar 2024 15:00:00 GMT | 成功 |
| S30 | [RPO/Backlog Wars! - Cloud Wars](https://cloudwars.com/cloud-wars-minute/rpo-backlog-wars) | Tue, 06 May 2025 11:30:00 GMT | 成功 |

9个来源有日期、3个日期unknown；没有伪造日期补齐。所有新来源保存URL、provider、published_at原值、本地searched_at（字段实际表示首次本地保存）及正文/摘录；search call与run保存开始/完成时间。

### B4. 模型可见材料与候选证据

证据模型实际收到12个来源，正文每来源最多682字符、摘录最多341字符，并有实际窗口与截断标识；完整提取文本保留在数据库，没有把完整内容全部送给模型。

模型返回 **9条候选、6项gaps**。本地JSON Schema通过总数≤10及结构校验，但语义校验在items[0]就拒绝。每题Q1=3、Q2=2、Q3=2、Q4=2，因此Q1超过每题2条；4题最多8条的业务上限没有被模型遵守。

以下均为**拒绝文档中的候选**，不是有效证据，也没有分配成功证据ID：

| 0-based条目 | 问题 | 模型分类 | time_scope | data_period | 引用来源 |
| --- | --- | --- | --- | --- | --- |
| 0 | Q1 | verified | current | Q4 and FY 2026 | S19 |
| 1 | Q1 | verified | current | Q3 fiscal 2026 | S20 |
| 2 | Q1 | verified | current | Q1 FISCAL 2027 | S21 |
| 3 | Q2 | verified | historical | fiscal 2025 Q2 | S22, S23 |
| 4 | Q2 | single_source | historical | fiscal 2025 Q3 | S24 |
| 5 | Q3 | unverified | historical | unknown | S25, S26 |
| 6 | Q3 | opinion | forecast | unknown | S26 |
| 7 | Q4 | single_source | historical | unknown | S28, S29 |
| 8 | Q4 | verified | historical | unknown | S30 |

分类分布：verified 5、single_source 2、unverified 1、opinion 1。5条verified全部只有单一域名支持，部分只有snippet；输出甚至在verification自称“单一来源”，与verified标签冲突。没有把两个不同域名直接认定为独立；本次根本没有达到那一步。

23条links均逐字出现在实际发送的对应来源text/snippet内，且来源属于相应问题。**这只证明逐字可追溯，不代表解释和分类正确。** 其中3条是页面标题式文本（items[0]/[3]/[7]）；因为标题混入了提取正文，仍能命中text。精确等于数据库title的1条，其余2条等于去掉数据库标题前缀的页面标题。这是当前“拒绝标题引用”的实现边界，整批失败使其未作为有效证据落库。

本轮有效新增research_evidence行数：**0**；证据阶段状态：failed。报告模型调用：**0**；新报告版本：**0**。旧报告v1（version ID=4）仍保留，未确认。

### B5. 候选gaps（未作为成功证据保存）

1. Q1: 材料中三篇 2026 年官方稿均为截断摘要，未出现 FY2026 Q4/Q3 的 RPO 具体数值或原文 RPO 表述；同时未有材料证明原文是否在同一句中明确区分『当前值』与『公司指引/展望』，该区分待查原文（含 SEC 10-K/10-Q）核实。
2. Q2: 2024 日历年发布的官方稿中，仅见 FY2025 Q2（52%/336%，2024-12-09）与 FY2025 Q3（RPO $130B，2025-03-10 发布）两稿；2024 年 3 月发布的 Oracle FY2024 Q3 官方新闻稿不在材料内，因此『2024 年 3 月官方原文』对 RPO $80B 的表述无法核对。
3. Q3: 计划所指『Valuentum 2024-12-10 文章中的 52%/336%』在材料中未出现该两个数字的原文片段；id 26 发布日为服务商估计的 2024-12-10，但可见片段不含 52%/336%，无法确认该文是否引用了这两项指标及其口径（RPO 还是 GPU/OCI），需要人工查阅文章全文。
4. Q4: Cloud Wars 文中『Q3』未在材料片段内出现财年标识（FY2024 vs 其他），$80B/29% 与 Oracle 官方同期 RPO 披露的数量级一致性缺少官方原文证据；id 28、29 为同域重复，不构成独立证实。
5. Q4: 『需求仍在增长』『AI 投入回报未证』类辩论论断：本批材料中无机构研究报告或分析师观点原文支持任一方，且 2026 年现值的回报指标未在材料中出现，相关论断仍待补充来源。
6. 全部问题：来源日期均为服务商估计的发布/更新时间，不是确定的首发日期；modified_at 与 provider_snapshot_at 均为 unknown；所有材料为搜索摘录或截断文本，未见完整财报或 SEC 文件正文，AI 分类与结论均待人工审核。

四个问题均有单独缺口，允许发现未覆盖事实；本次没有出现“无证据问题被一条总提醒替代”的情况。但第2项gaps把2025-03-10稿放在“2024日历年发布”的句子里，文字本身仍不严谨。第5项将全局行业观点缺口放在Q4下，可改进问题归属。

## C. P0逐项验收

| P0项目 | 真实验证结果 | 说明 |
| --- | --- | --- |
| 日期规范化与模型输入 | **证据阶段通过；报告阶段未验证** | 12条来源的原值、解析值、精度和服务商估计语义进入analysis17.input_json；9有值/3unknown；modified_at/provider_snapshot_at均unknown。报告未调用，不能以离线或此前Mock结果冒充真实通过 |
| 历史材料逐条标记 | **部分通过** | 来源22/24/26/28/29/30共6个已知历史日期逐条有historical标签；缺失日期仍unknown。候选Oracle2024/2025事实未被写成2026现状，但仍有未经引文证明的财年推断/周期字段和校验误拒 |
| query优化及重确认 | **通过本次范围** | 关键词路径、预览与实发一致、4题、新计划确认/新run均成立；未追加调用。未实测query_override手动非空分支，不宣称其已真实验收 |
| 快照变化提醒 | **通过本次范围** | 原Valuentum S7→S26、Cloud Wars S9→S28都识别为snippet变化；正文相同。旧ID不变，未把哈希/ID变化说成事实更新。未观察到真实正文变化或A→B→A，不能冒称本轮验证该分支 |
| 证据规模及引用校验 | **质量不通过，拒绝门禁有效** | 模型每题数量违规、verified单来源；本地拒绝整批，0条成功证据，不裁剪/降级让它通过。逐字/问题关联有效，但标题混在text仍可过逐字匹配 |
| 结构化失败诊断 | **通过** | 保存diagnostic #1：stage=validation，code=verified_sources，path=[items,0]，item_index=0，analysis_id=17，attempt_run_id=17；结构样本已脱敏、document_truncated=0，未包含密钥/认证配置。费用正常结算 |

诊断采用首次失败即停；它足以定位第一处失败，不代表收集了整批所有错误。后述其他错误来自本轮离线逐项检查，不是数据库已记录的多个诊断，也没有通过回调绕过正式校验。

## D. 质量审核、剩余缺陷与不确定项

### D1. 已确认的模型输出问题

1. **单一官方来源被标为verified。** items[0]/[1]/[2]/[3]仅Oracle域名，item[8]仅Cloud Wars，均不满足独立来源提取原文要求。系统在首条拒绝，未放行。
2. **每题限制未被模型遵守。** Q1输出3条；总数9虽不超Schema的10，但四题每题≤2只允许最多8。需要提升真实输出稳定性；本轮无重试样本，不能估算成功率。
3. **周期字段不在所引用句子内。** items[1]的Q3 fiscal 2026、item[3]的fiscal 2025 Q2、item[4]的fiscal 2025 Q3都不能在自身links.quote中逐字匹配。完整材料中可能有对应文字，不能代替本条周期引文的明确依据。
4. **历史财季推断超出可见引文。** Cloud Wars项把只有Q3的引文进一步推成FY2024 Q3，自己也承认未见财年标识；虽放在inference，仍需避免看似已核实的具体财季。完整保存正文在约1365字符处有“Q3 ended 2/29/24”，但模型只见前682字符，这不能事后算作模型已读。
5. **事实与人物职务不匹配。** item[3]摘要把52%/336%引语称为CFO引语，实际搜索摘录标明CEO Safra Catz；逐字数字正确并不能保证摘要准确。
6. **标题式引用边界仍存在。** items[0]/[3]/[7]引用提取text中的页面标题；由于它确实在发送窗口内，逐字匹配不能区分标题与正文。这没有本次成功落库，但仍是下一轮需设计解决的引用质量问题。

### D2. 本地时间校验的误拒与材料选择问题

在不写库、不改文档、不重新调用模型的离线核验中，直接按当前temporal.validate_time_use逐条检查：

- item[2]的“Q1 FISCAL 2027”是2026年9月发布的合法财年口径；time_scope=current却因当前代码强制data_period包含研究日历年2026而产生unknown_as_current。**财年与日历年不能简单要求年份相同。** 这是代码规则误拒，不能通过把FY2027改成2026来迎合校验。
- item[5]引文“reported lower than expected…consensus forecasts”描述过去业绩相对预期的比较；宽泛预测关键词把它判断为预测，引发forecast_as_actual。**“低于预期”的已发生业绩与“预测未来业绩”应区别。**
- 实际完整Valuentum正文有52%（约910字符）和336%（约1105字符），但前682字符窗口没包含；snippet又是未来指引，模型只能报告本问题缺口。不能假定“搜索和提取拿到”就等于“模型已收到”。
- Oracle官方大篇幅财报被截为开头682字符；数字表的snippet缺列标签，候选输出虽对部分表格归属保持谨慎，仍无法完成全部口径核验。

上述诊断均为后续修复建议的证据，本轮严格不修改生产代码、不放宽校验、不重发失败调用。

### D3. 来源时效、命中与独立性

2024/2025来源仍然存在，是本次有意检索的历史材料；不应只因旧而删除。目标是明确标记用途。缺日期的相同页面变体仍为unknown，没有从文章文字/URL擅自回填。

两篇二手目标原文与2024-12官方原文命中；2024-03官方原文未命中，不能宣称29%/$80B已被同期官方原文独立证实。所有材料本轮仅经Tavily提取，未对原站另外HTTP抓取；不能保证Tavily返回的是原站此刻最新内容。BBC更新案例不在本轮四题范围内，本轮没有验证其当前版本。

本轮没有生成新研究报告，因此无法检查“新报告的每项结论/数据引用、报告时间上下文、生成的数据库来源列表”的真实效果。既有旧报告只做保留检查，没有拿旧报告代替新版本。

## E. 数据保护与新记录

执行前对所有表保存列定义与全部旧行；执行后逐主键比较旧行，核对追加记录。同时与已验证v6结构核对表/字段/索引/外键/触发器均未变化。

| 表 | 原行数 | 本轮后行数 | 旧行保护 |
| --- | --- | --- | --- |
| ai_analysis_runs | 15 | 17 | 旧行完全一致 |
| ai_budget_settings | 1 | 1 | 旧行完全一致 |
| collection_runs | 16 | 16 | 旧行完全一致 |
| hotspot_scores | 61 | 61 | 旧行完全一致 |
| hotspot_snapshots | 296 | 296 | 旧行完全一致 |
| hotspots | 61 | 61 | 旧行完全一致 |
| idea_actions | 5 | 5 | 旧行完全一致 |
| production_actions | 12 | 16 | 旧行完全一致 |
| production_objects | 2 | 2 | 旧行完全一致 |
| production_projects | 1 | 1 | 仅预期元数据变更，见下文 |
| production_versions | 4 | 6 | 旧行完全一致 |
| research_evidence | 30 | 30 | 旧行完全一致 |
| research_evidence_sources | 51 | 51 | 旧行完全一致 |
| research_model_diagnostics | 0 | 1 | 旧行完全一致 |
| research_plan_confirmations | 2 | 3 | 旧行完全一致 |
| research_report_confirmations | 0 | 0 | 旧行完全一致 |
| research_search_calls | 14 | 20 | 旧行完全一致 |
| research_search_runs | 2 | 3 | 旧行完全一致 |
| research_source_questions | 30 | 42 | 旧行完全一致 |
| research_sources | 18 | 30 | 旧行完全一致 |
| sqlite_sequence | 4 | 4 | 仅预期元数据变更，见下文 |
| topic_analyses | 15 | 17 | 旧行完全一致 |
| video_ideas | 9 | 9 | 旧行完全一致 |

关键解释：

- 旧计划、报告、来源、证据、引文、分析/费用与预算行均原值保留；新分析#16/#17、新计划v4/v5、新确认#3、新搜索run#3、新调用6条（含一次usage）、新来源S19–S30与12条关联、新诊断#1均追加。
- 生产项目#1只有updated_at被既有VersionService正常更新（由2026-11-02T17:37:10+00:00变为2026-11-03T11:53:01+00:00）；名称、备注、idea_id、status=researching等未变。
- sqlite_sequence里production_actions/objects/versions的seq随既有追加/INSERT ON CONFLICT路径正常前进；不是覆盖业务历史。旧业务行没有丢失。
- 旧报告version ID=4、v1保留，无新报告、无任何报告确认；新证据analysis17没有插入research_evidence或引文。
- hotspots、hotspot_snapshots、hotspot_scores、video_ideas、预算设置均逐值保持不变。没有触发采集、重算评分、制作状态切换或脚本模块。
- 最终user_version=6；integrity_check=ok；foreign_key_check无错误；无running或uncertain分析/搜索；未结算预占0，未知模型费用0。
- 22个P0验收文件哈希仍一致；没有修改生产代码、迁移逻辑、.env或系统环境变量。无Git暂存/提交/推送。

## F. 最终结论

**不通过：仍存在关键事实、引用、日期或数据安全问题，需要修复。**

本次具体不通过原因是候选证据分类/数量不合格、标题式引用及摘要事实错误，另有财年与预测识别的校验误拒；**没有发现数据保护失败或预算越界**。严格门禁和失败诊断工作正常，阻止了不合格证据进入报告，但这不等于真实研究质量已经达到目标。

已完成计划→人工修订确认→搜索→提取→证据尝试及失败留痕。报告生成与其真实质量验收因证据失败未执行，不能称为端到端报告验证通过。未自动重试、未降低标准、未确认报告、不进入脚本阶段。

后续如需修复，应单独授权处理：verified输出稳定性、每题上限、财年/日历年关系、历史“低于预期”的预测误识别、正文标题边界和携带数字/周期的可见材料窗口；不能在本轮偷偷改动后重跑。

## G. 复核产物与未执行项目

本轮本地产物位于 `E:\one\ai-hotspot-radar\logs\phase4-2-1-3-real-api`：

- run.py：本次操作驱动与一次性/30credits护栏；不是生产代码补丁。
- state.json、events.jsonl：动作ID、逐阶段请求及实际用量。
- generated-plan.json、reviewed-plan.json、query-preview.json、search-calls.json：计划和实际query证据。
- new-sources.json、snapshot-changes.json：来源与真实快照差异。
- evidence-returned-document.json：Provider返回但正式拒绝的候选文档，仅诊断产物，不能当成功证据。
- evidence-diagnostics.json、offline-audit.json、audit.py：正式失败诊断及只读离线核查。
- before-data.json、before-budget.json、public-settings.json、git-before.txt、git-after.txt：原数据保护、非敏感配置和Git基线。

未执行：失败后报告模型调用、报告确认、脚本/后续制作、补充搜索、模型重试、原站独立最新版本复抓、真实网页手工点击流程、失败输出修正重跑。未下载服务商最终账单，所以费用应理解为真实Token按既有价格的本地估算结算。

执行完成后停止，不自动进入下一阶段。
