# 第四阶段 4.2.1.4-A：证据质量修复方案设计与测试用例审查

- 项目：ai-hotspot-radar；实际目录：E:\one\ai-hotspot-radar。
- 日期：2026-11-04（北京时间）；版本依据：A初稿只读确认正式库v6，本轮未重新查询数据库。
- 状态：**设计审核修订稿，等待审核；未进入4.2.1.4-B。不是修复完成报告。**
- 修订：落实四项审核意见；保留T01–T40，补充逐项可执行断言与分层验收要求。
- 初稿阶段仅新建本文；本轮仅修订同一设计报告，不创建其他文件，不修改生产代码、测试文件、配置或数据库，不调用API或执行研究流程。

## 1. 初稿检查依据、当前架构与问题定位

本节数据库查询、样本和代码检查结果来自A初稿阶段，本轮不重新查询数据库或执行研究。本轮只读取原设计和文件哈希以核对修改范围。

指定三份报告已移至 E:\one\ai-hotspot-radar\docs\plan&report，已读取REPORT_PHASE4_2_1_1_P0.md、REPORT_PHASE4_2_1_2_MIGRATION.md、REPORT_PHASE4_2_1_3_REAL_API.md。本轮不恢复或移动文件。Git已有PLAN.md、PLAN_PHASE2.md、PLAN_PHASE3.md删除及其他未提交/未跟踪内容，原样保留；未发现项目实体AGENTS.md，遵循聊天规范。

检查研究service/schemas/prompts/temporal/guards/base/tavily/diagnostics、Store、v5/v6迁移、共用执行器/Schema转换和相关测试。SQLite URI mode=ro&immutable=1读取结构和必要失败样本，事先确认无WAL；不实例化会写表/迁移的Store，不执行历史真实API驱动。库共23表；P0验收22文件SHA全部一致。报告中的历史284项测试，本轮没有重跑。

~~~text
确认计划 → 搜索/提取 → 不可变来源快照
 → 正文前缀/摘录 → 模型输出category/time_scope/period/links
 → Schema/语义引用校验 → 费用结算 → 证据与analysis_json事务保存
 → 成功证据批次 → 报告新版本 → 人工确认
~~~

input_json/analysis_json已有冻结输入与成功结果；evidence是SQL投影，links有source_id、field=text/snippet、quote/quote_offset。来源/证据/引用/确认只追加，诊断和费用独立保留。设计复用这条链，不改变预算、重试、计费、幂等或制作状态。

| 实际文件/函数（本轮行号） | 当前逻辑 | 问题 |
| --- | --- | --- |
| [service.py:197](E:/one/ai-hotspot-radar/services/research/service.py:197) organize_evidence | 按来源数分text_limit，仅正文/摘录前缀 | 后段数字/周期未发给模型 |
| [service.py:231](E:/one/ai-hotspot-radar/services/research/service.py:231) _validate_evidence | 模型category含verified；最后两段域名+field=text门槛 | 不证明转载独立或同命题支持 |
| 同函数counts/identities | 循环中查每题2条，重复身份含summary | 首错遮蔽数量错误；改摘要可能逃重复检查 |
| [schemas.py:34](E:/one/ai-hotspot-radar/services/research/schemas.py:34) CATEGORIES/EVIDENCE_SCHEMA/LINK | 平铺items总数10；text/snippet二选一 | 模型写最终等级，每题上限未结构化，区域身份丢失 |
| [temporal.py:37](E:/one/ai-hotspot-radar/services/research/temporal.py:37) source_time_context | 来源年份生成historical | 来源年代不等于数据周期 |
| [temporal.py:51](E:/one/ai-hotspot-radar/services/research/temporal.py:51) forecast_text | expected/预期等词命中 | 历史“低于预期”误判未来预测 |
| [temporal.py:72](E:/one/ai-hotspot-radar/services/research/temporal.py:72) validate_time_use | period须在数值quote内；current须含研究年份 | 无独立周期上下文；FY2027/2026误拒 |
| [temporal.py:89](E:/one/ai-hotspot-radar/services/research/temporal.py:89) validate_claim_time | 报告沿用时间启发式 | 生成/人工保存/恢复继续误拒 |
| [research_store.py:57](E:/one/ai-hotspot-radar/database/research_store.py:57) save_sources | source-v2 hash含正文/摘录/标题/日期 | 新source_id不等于正文变化或独立来源 |
| [research_store.py:147](E:/one/ai-hotspot-radar/database/research_store.py:147) evidence | JSON按position补time_scope/data_period | 新等级/区域/窗口必须同步读回 |
| [research_store.py:166](E:/one/ai-hotspot-radar/database/research_store.py:166) insert_evidence | 完整字段.find(quote)取offset | 同句多处出现时偏移未必是模型所见位置 |
| [guards.py:50](E:/one/ai-hotspot-radar/services/research/guards.py:50) validate_report | 精确v2版本或字段探测 | v3须明确版本调度，不猜格式 |
| [tavily.py:88](E:/one/ai-hotspot-radar/services/research/tavily.py:88) extract | URL/raw_content，无DOM/canonical/来源关系 | 无法恢复全部真实区域或证明独立 |
| [schemas.py:45](E:/one/ai-hotspot-radar/services/ai/schemas.py:45) provider_schema | 移除服务商不支持的长度参数 | strict不替代本地数量硬校验 |
| [diagnostics.py:23](E:/one/ai-hotspot-radar/services/research/diagnostics.py:23) rejected_structure | 字符串脱敏，16KiB上限 | 能定位结构，不能完整原文回放 |

真实样本核对：analysis17 failed、12来源、最大正文682字符，首诊断verified_sources/items[0]；S26全文4549字符，52%起点910、336%起点1105，实际发送[0,682)。本轮没有重新整理或修正旧失败批次。

## 2. 六个根因与最小决策

### 2.1 verified授予权

真实候选9条中5条verified，而其核验文字自己承认单源。新模型kind仅fact/opinion/inference/disputed/unverified，可用corroboration_requested申请交叉核验，**不能输出最终category/final_category**。程序审定最终等级与未满足条件。

合法fact申请升级但仅单一官方来源→single_source；多来源但独立性不明→unverified+independence_unknown。原始候选和决策均保存。这是事先定义的候选→审定协议，不是失败后改文档求成功。新模型伪写verified字段为Schema违例，整批拒绝；无效引用、超量、伪期间不能靠降级通过。旧v1/v2按版本读取，不将analysis17自动降级重放。

### 2.2 每题数量

平铺9条虽过总数10，Q1仍3条。按题分组、组内maxItems=2，本地先预检全题集合与数量，再验引用。总量≤min(10,2×问题数)，零条可用本题gap表达。任何超限整批拒绝，不裁剪、不选择前2条。

### 2.3 财年与日历年

来源发布日、FY/Q标签、明确覆盖日期、研究参考时间分开；去掉研究年份必须包含在period字符串里的规则。财季标签可核实，不代表起止日期已知，不能套公司常见财政日历补齐。

### 2.4 实绩与预测

按原子命题核对说话者、事件、时间、数值角色。“低于预期”属于过去结果与基准比较，不自动是未来事件；程序无法可靠解析的语义保留unknown，不用更多关键词冒充证明。

### 2.5 引用区域

text混入标题/菜单，逐字命中不够。服务器生成区域/窗口清单，模型携带segment/window和原位置；不能自己将title变成body。现有标题测试只覆盖title未在text中的简单情形，应增加重现位置测试。

### 2.6 可见窗口

改为按问题找相关段+数字/日期/周期上下文，记录实际发送范围和缺口；未发全文不能用来事后追认引用。从问题抽出的52%/336%只是检索线索，不是事实依据。

## 3. 模型、程序与人工职责

| 主体 | 负责 | 不能做 |
| --- | --- | --- |
| 模型 | ≤2候选/题、可见引句、原子命题、类型/期间建议、gaps | 授予verified、伪造受信独立性、补日期/正文、联网 |
| 程序 | 数量/精确区域偏移、关联、相依排除、受信等级规则、版本保存 | 两域名即独立、hash不同即独立、年份相等即当前 |
| 人工 | 核查独立采集过程、同一事实支持、职务/单位/期间及推理 | 用“已审”绕过无效引用、数量、预算 |

### 3.1 程序授予verified的全部条件

1. 候选为事实，非观点/推断；主体/指标/值/单位币种/增长基准/期间/实绩预测性质一致。
2. ≥2逻辑来源组、不同根域名、独立编辑控制实体；不同source_id/URL/快照不能重复计票。
3. 提取都成功，支持引文来自可靠extracted_body，非title/search_snippet/metadata。
4. 引文逐字、偏移、可见窗口、区域、快照、题/项目/运行关联全部正确；重复link不计票。
5. 共同新闻稿/财报/通讯社、转载/复制/引用链已排除；措辞不同或未发现转载不是正向独立证明。
6. 对同一原子命题的独立采集和支持关系有**受信审定**，绑定source_id、body_hash、claim_signature与审核主体/依据；模型输出不能成为受信输入。
7. 无内容冲突、期间混用、未知却称current等问题；任一unknown不升级。

输出quality含final_category、independence_status、origin_group_ids、grant_reasons、unmet_conditions、policy_version。

**信息缺口：当前代码/库没有受信来源独立性审核记录或输入通道。** 最小B不新增人工审核工作台、不开发审核入口、不联网追转载；生产组装器必须固定提供空审核集，不能由请求、配置或模型填入，因此生产不得授予verified。正向授予规则可用可信fixture测试，但不宣称现有生产能提供其前提。要实际赋verified须未来另审人工作证/持久审计。

相依排除可复用normalize_url、正文等值hash、明确署名/原始稿件ID。近重复只支持dependent_suspected/unknown，不证明独立。最后两段不等于可靠根域名，如co.uk；无本地可靠公共后缀信息时registrable_domain=unknown，禁止升级，不擅自引依赖或联网取表。


### 3.2 审核修订：生产可信审核的来源与信任边界

**当前生产可信审核来源：不存在。** 当前没有部署可认证的审核记录存储、记录读取器或审核入口。B范围只保留纯函数的能力契约及隔离测试，生产服务固定提供空的受信审核集；不得新增按钮、接口、文件导入、配置开关或命令行参数来注入审核。该约束是服务层强制项，不只是默认值建议。

信任边界分为三层：

1. **不可信内容层**：模型输出、Tavily内容/网页文字、计划自由文本、普通请求字段、本地随手编辑的JSON、analysis_json里自称“已审核”的记录，全部不能成为trusted_assessments。服务端保存过一段文字，不代表来源可信或审核已发生。corroboration_requested只申请评估，无授予权。
2. **生产服务组装层**：从真实source/manifest构造输入、执行原文核验，并在本阶段将可信审核供给强制为空。模型返回审核字段按Schema拒绝；其他非受信传参必须忽略其授信意义或明确拒绝，不能透传给授予策略。只改变变量名、设result=confirmed_independent或boundary_confidence=reviewed不构成认证。
3. **隔离测试层**：T03用可信fixture注入纯函数policy，只验证“充分前提下策略可升级”；fixture-reviewer和合成记录不是生产认证机制。集成测试必须另证即使有人将同一fixture混入模型/计划/请求内容，生产组装器也不授予verified。测试夹具、测试替身及注入路径不得进入生产装配。

**未来唯一可认可的生产来源类型（本轮不实现）**：经独立方案批准、由已认证且有权限的审核主体通过受控工作流形成的服务端审核记录。记录须从受控持久存储经认证读取器取得，验证出处/权限、状态与绑定；不能把任意JSON字典当凭据。现阶段不能虚构该存储的位置、接口或“已可用”的认证方式。

未来记录至少绑定：

- review_id、project_id、审核记录/策略版本；审核主体身份、权限依据、审核时间、审定结论、原文依据和可追溯出处。
- 每个source_id及完整snapshot_hash、body_hash和hash算法/版本；原支持引句的region、field、offset/范围及内容摘要。
- 原子命题的规范身份：主体、指标、值、单位/币种、增长基准、期间、事件性质及claim_signature/规范化版本，不能只绑定摘要或candidate_id。
- 支持/独立性结论分别记录，明确原始稿件、编辑控制实体、相同事实支持依据，不能一个independent布尔值替代全部判断。
- 有效/撤回/被替代状态。审核主体不明、身份未认证、记录缺失、版本不匹配、原子命题或任一快照/hash不匹配时，不授予verified。

新快照即使正文hash相同，也不能自动继承绑定旧快照的审核；可继续读取旧审核对应旧快照，针对新快照是否重审需未来方案明确。撤回不改旧证据/报告正文，但后续新授予必须重新检查有效性。

结论：**B生产路径verified应为0，不建设审核入口**；这不是把普通单源事实拒绝，也不是以低等级掩盖无效引文。若业务以后要求生产产生verified，必须另行审核授权，不能以T03通过作为上线依据。

## 4. 建议数据结构：v3 JSON，保持v6

### 4.1 模型输入manifest

~~~text
contract_version: research-evidence-v3
research_context: {as_of, target_window:{start,end,basis:confirmed_plan}}
questions: [{id,question,keywords}]
sources: {source_id:
  source_id,snapshot_hash,body_hash,question_ids,extraction_status
  source_date:{raw,normalized,kind:provider_estimated_published_or_updated}
  local_saved_at,modified_at:unknown,provider_snapshot_at:unknown
  regions:[{segment_id,region,storage_field,start,end,boundary_confidence}]
  visible_windows:[{window_id,segment_id,region,storage_field,start,end,text}]
}
coverage_gaps:[{question_id,source_id,code,term,detail}]
selector_version,manifest_hash
~~~

完整字段仅服务器校验用；模型只见窗口与必要元数据。trusted_assessments作为服务端policy参数，不混入不可信模型材料。检索日期不限不等于研究目标时间没有边界，target_window须来自确认计划。

### 4.2 模型输出按题分组

~~~text
questions:[{
  question_id,
  items:[{
    candidate_id,kind,corroboration_requested,summary,inference,verification,
    claim:{entity,metric,value,unit,basis,speaker},
    temporal:{proposed_type,event_kind,speaker_kind,
      period:{label_raw,calendar_year,fiscal_year,fiscal_quarter,start,end},
      context_links:[引用协议]},
    links:[{source_id,window_id,segment_id,region,storage_field,
      start,end,quote,role:claim_support}]
  }],
  gaps:[{code,detail}]
}]
~~~

每题items 0–2，questions恰好等于计划题集合且每题一次，candidate_id全批唯一；对象additionalProperties=false、文本大小受限。数值/日期未知用null，标签可unknown；全局gap不顶替本题。单候选只表达单主体/指标/期间/性质，不许多指标规避上限。

period.context_links可在另一段，但同source snapshot/同题/实际可见，且有明确作用域。不同来源的日期或metadata不能硬绑到数字。

### 4.3 规范结果与SQL投影

analysis_json保存contract_version/policy_version/input_manifest_hash、candidate_document、按题序扁平items、结构化gaps、source_assessments和decision_log。items带position/candidate_id、程序quality/temporal及完整links。

- evidence.category仅写程序final_category，沿用现有枚举。
- SQL links仍field=text/snippet，quote_offset=start，end=start+len(quote)；不能用全字段.find替换明确位置。
- region/window/segment/role保存在analysis_json同position links；Store读回核对SQL/JSON，不一致不静默退回text。
- title字段与text没有同一坐标时仅展示/线索；不能硬塞到snippet满足旧CHECK，也不能作为业务事实link。
- v3显式schema_version；旧source/evidence/quote_offset/report不改。

## 5. 验证流程与整批原子保存

拟新增纯函数quality.assess_batch(candidate,manifest,policy)，返回accepted/items/gaps/errors/decisions。errors有code/path/question_id/item_index。它不读配置/数据库、不联网。

1. Schema/版本/大小，禁止模型写最终审定字段，不自动删/补字段。
2. 全批题集合、数量、唯一ID、零条题gaps预检；先稳定报数量问题。
3. project/run/source/question关联、快照hash及冻结manifest核验。
4. 引用区域/window/segment和半开区间核验，quote须等于原切片且完全位于一个实际可见窗口。
5. 保留原有确定性字段/唯一来源纠正，但仅限同题恰好唯一可见有效**来源及位置**。错区域title/unknown不能修成body；多个命中而偏移无效则ambiguous_quote。明确正确偏移可消歧。纠正留痕，重复link/原子事实整批拒绝，不合并不裁剪，不能只靠summary区分重复。
6. claim/数字角色/单位/期间上下文一致性，明确矛盾拒绝，语义不足保留unknown。
7. 事件时间和来源区域冲突校验。
8. 程序授予等级：合法未达verified记录低等级和原因；引用硬错不能靠降级补救。
9. 全批accepted才进原persist事务，分析/证据/links一起保存；拒绝items=[]，正式候选行0，失败费用和诊断保留。
10. 报告只读审定结果和真实来源，禁止重新升级verified/actual；人工保存/恢复/确认同规则。

诊断复用v6表：每阶段至多20项安全errors写details_json，首错维持原顶层展示；超出标diagnostics_truncated。同步code/path白名单，保留16KiB结构样本/脱敏，不改计费预占、结算先后或重试次数。

## 6. 财年与实绩/预测分类

| 时间/事件字段 | 依据 | 信息不足时 |
| --- | --- | --- |
| source_date与calendar_publication_year | 已保存published_at及解析 | unknown，保留精度，不复制成财年 |
| fiscal_year/quarter/label_raw | 原文明示标签与context_links | null/unknown，不按文章日期推算 |
| coverage_start/end | 明确区间/截至日 | 可仅end，不能补start |
| event_kind | actual_result/guidance/forecast/expectation及主语/谓词引句 | unknown，不只看expected |
| speaker_kind | company/analyst/market及署名/职务引句 | unknown，不能CEO改CFO |
| research_as_of/target_window | 确认计划 | 未给范围则关系unknown |
| current_relation | within_target/before_target/future/partially_overlaps/label_only/unknown | 不以来源年替代数据期间 |
| temporal_type | 六类，经事件和期间核验 | unknown，已知actual_result可独立保留 |

current_actual定义：明确已发生，覆盖区间/截至日在计划目标窗内；**不表示全球最新一期**。historical_actual为目标窗之前实绩；跨窗默认unknown+partially_overlaps。周期与数值可分段，但context_links必须可见且关联明确。

### 6.1 FY2027 Q1指定案例

as_of=2026-11-03，发布日期2026-09-10，标签FY2027 Q1、无起止日：calendar_publication_year=2026；fiscal_year=2027/quarter=1保留。事件actual_result，current_relation=label_only（可另记publication_within_target=true）；不因年份不同拒绝或判为历史/非当前。

可保存“2026年披露的FY2027 Q1实绩，覆盖日期未核实”，temporal_type=unknown，coverage_start/end=null。标签合法与“周期已证实当前”是两个结论；不能补6–8月或套Oracle财年。另有明确覆盖日期在目标窗内才可current_actual；模型强填无依据日期仍unsupported_period拒绝。

### 6.2 A–E正确分类及程序结果

缺周期/主语时不能凭空完成historical/current区分，必须区分原句能证明的性质和fixture补充条件。

| 案例 | 正确分类 | 程序结果 |
| --- | --- | --- |
| A 实际收入低于市场预期 | actual_result；fixture明确2024期间→historical_actual，2026目标内→current_actual | 接受实绩；只给原句无周期→type unknown但actual_result保留，不误判预测 |
| B 公司预计下季度增长20% | company_guidance | 可作指引，不当已实现20%；缺参考日期不补季度日历 |
| C 分析师预测明年增长20% | analyst_forecast | 可作预测；无基准年不将“明年”换绝对年 |
| D 公司公布上一季增长20% | actual_result；fixture明确截至2026-09-30→current_actual；明确旧期间→historical_actual | 不因上一季已过去就当旧年度；只有相对词无锚点→unknown |
| E 市场预期20%，没有实绩 | market_expectation | 可存预期，禁止actual_value=20% |

混合句“实际18%、预期20%、下季指引22%”是不同原子命题，不能整句贴forecast/actual。一题最多2条，模型选重点并写gap；程序不拆完再裁剪。把三种值都当实际则mixed_temporal_claim拒绝。复杂句不能解析时unknown与人工审核，不宣称有限规则已证明所有语义。


### 6.3 审核修订：三个字段的独立职责与unknown边界

| 字段 | 只负责回答 | 可用值/必要依据 | 不得承担的职责 |
| --- | --- | --- | --- |
| event_kind | 该原子命题描述何种事件或陈述行为 | actual_result/guidance/forecast/expectation/unknown；需谓词、结果状态、数值角色和时间指向的关联引句 | 不仅凭expected/forecast、来源发布日期或研究年份决定性质 |
| speaker_kind | 谁对该命题负责发言/作出预测 | company/analyst/market/unknown；按归属引句/署名/引语核对 | 不把网页发布者、记者或引用站点当作实际发言者；不自动判定事件是指引 |
| temporal_type | 事件、发言者、期间与研究范围组合后可支持哪一种使用 | historical_actual/current_actual/company_guidance/analyst_forecast/market_expectation/unknown | 不覆盖已知period/发言者，不反向创造日期，不将模型proposed_type作为最终判定 |

程序的有据映射：

- actual_result + 明确目标窗之前期间 → historical_actual；actual_result + 明确目标窗内覆盖/截至日 → current_actual。speaker_kind不明仍可保留确有原文的actual_result，但不能伪造具体公司/职务。
- guidance + 明确company发言归属且为未来指引 → company_guidance；forecast + 明确analyst → analyst_forecast；expectation + 明确market且未有实际结果 → market_expectation。
- speaker_kind=company本身不证明是公司指引；记者转述分析师预测不归company，句中出现expected也不证明是forecast。
- event_kind/角色/归属/期间不足时，仅保留确有证据的各独立字段，其余unknown/null。不能可靠完成组合判定则temporal_type=unknown，不以最接近的确定类型替代。

两种不同失败处理必须区分：**证据不足**可保留unknown并明确gap；**输出与可见原文相矛盾、编造期间/归属、将已知指引称实绩**属于硬错误，仍整批拒绝，不通过改成unknown让错误批次成功。缺字段、越界引文也不能用unknown绕过。

程序先核对精确引句及关联、分清“实际结果/其比较基准/未来指引”的作用域，再做有限规则映射；无法可靠解析的剩余语义交人工复核。不建立单关键词直达最终分类的捷径，也不为样本通过而增加无依据财年映射、默认发言者或日期。

强制回归保留T06（FY2027 Q1、2026发布、日期null）、T07（历史实际低于预期）、T08（公司指引）、T09（分析师预测）、T28/T29；增加对照断言：单独一句“expected growth 20%”无角色/期间→unknown；“actual below expected”不得因expected抛forecast_as_actual；真实预测明确写成actual必须拒绝。正例与反例需成对执行。

## 7. title/search_snippet/extracted_body/metadata

服务器派生区域，保留原字段/坐标；边界不明用boundary_confidence=unknown。纯文本可按独占标题行、仅定位用规范化标题副本、页眉导航模式标注，不改引文或原offset。

按出现位置判断：标题同句在真正后段正文重现，可按该正文位置引用，不能全局删除。heuristic区域可作低等级待审核；verified须可靠边界及受信支持审定。本方案不增加HTML抓取或DOM依赖。

| 区域 | 普通事实/线索 | verified |
| --- | --- | --- |
| title | 展示标题/主题元信息，只有标题的业务事实应gap/线索，不作正式事实 | 禁止 |
| search_snippet | 可存明确“摘录声称”的unverified线索，不伪装已读正文/实绩已验证 | 禁止，即使跨域一致 |
| extracted_body | 原文/窗口/区域有效可single_source等，解释仍需核验 | 须全部独立/同命题条件 |
| metadata | 日期估计、作者/出处等上下文 | 不单独证明经济事实/财季 |

提取失败：有snippet可unverified+body_unavailable gap；无任何有效可见引句则零条+gap。不能借旧成功source正文支撑新失败快照，不能以标题替正文。

同主体/期间/指标body28%与snippet30%冲突：保留二者，不覆盖、不自动择一。描述冲突并引用两区域可disputed；仍断言唯一28%事实则source_region_conflict整批拒绝。复杂口径不能确定同一性则待核实，不假称通用语义冲突检测完成。

新快照但正文相同：body_hash与原text判等，标题/日期/摘要变化单独提醒，不增加独立票；旧引用保持source_id。

## 8. 模型可见窗口与S26硬性回归

1. 原text按段/句/表格块划分，记录Python Unicode码点半开[start,end)，不先清空白计算offset，不混UTF-8字节/UTF-16位置。
2. 问题关键词/实体/指标定位，数字/金额/日期/FY/Q辅助；问题数字只找原文，不拼入原文。
3. 确定性相关段评分，实体/指标共现优先、数字日期辅助，source_id/start稳定破平分；不引向量库/额外模型。
4. 保留前后句、说话者职务、财季上下文；表格含行列头/单位/期间，缺失则table_context_missing。
5. 合并重叠/相邻范围，不将不连续窗口拼成连续quote；每窗独立ID/区域/field/offset/question_ids/hash，切片逐字相等。
6. 两段期间/数字都可见且有明确作用域才连接；同来源多窗不增加独立票，关联题不因此扩大。manifest存input_json。

不改max_request_bytes/max_output_tokens或预算算法：扣系统提示词/Schema/计划/JSON元数据后按剩余UTF-8字节公平分题，再补相关段；最终完整request_body仍由reservation_units检查。没有精确Tokenizer，不假称字符=Token；可记录selected_utf8_bytes/现有口径保守token_upper，实际以响应Token为准。

coverage包含required_terms matched/missing/omitted_budget、omitted_ranges、missing_context/selector_version。text_truncated仍指非全文。连最小有效上下文都容不下则本地停或题零条+gap，不扩预算/输入上限/检索范围、不追加调用。

Valuentum S26：4549字符，52%=[910,913)、336%=[1105,1109)。B冻结有限真实fixture，足够预算时必须覆盖两数字、OCI/GPU与职务上下文；FY2025 Q2在前段，另送期间窗。缺数字窗时明确omitted_budget并拒绝模型引用；任何材料无数字则missing/gap，不用问题补事实。旧analysis17的[0,682)永不扩大，不能追认旧失败成功。


### 8.1 审核修订：上下文完整性是选窗目标，不是只覆盖数字

每个拟引用事实在coverage中分别记录主体entity、指标metric、数值value、单位unit、增长/币种基准basis、期间period及必要speaker/表格行列头是否**原文存在、已发送、关联明确**。matched数字只代表定位成功，不能代表该事实coverage_complete。

- 尽可能选择最小完整证据包：主体/指标/值/单位所在句，必要前后句，以及同快照期间/引语归属段；可多窗，必须保留各自坐标与作用域引用。不能仅截出“52%”“336%”两个字符串。
- 单位/增长基准影响意义时为必需；若原文没有明确基准，标unknown，不把20%推为同比。财季未知可按T18保存周期未核实的陈述，**不能**从文章日或研究年补财季，也不能称current_actual。
- 上下文已存在却未入选，标context_omitted_budget或context_not_selected；原文未提供则context_not_found；段间关系不清为context_relation_unknown；表格缺列头沿用table_context_missing。coverage gap必须绑定question_id/source_id、缺失角色、原因以及遗漏区间（存在时），不能只写“材料不足”。
- 以上可统一表示为code=context_incomplete、missing_context列表及reason子码；原有term_not_found/omitted_budget仍区分“根本没找到”和“找到但没发送”。代码命名在B固定，不能用更名替代断言。
- 若缺主体/指标/单位或关联，导致数值含义无法成立，不保存确定的数值事实；只允许明确unverified线索或零条+本题gap。缺期间时合法unknown可保存；候选若声称具体财季/current或用缺失角色支持verified，则硬拒绝。unknown不是伪造上下文的补救办法。

S26必须尽可能同时呈现OCI收入52%、GPU consumption 336%的指标及单位、相应季度/原文周期段、公司及实际引语归属（存在时）。不能只断言数字已出现在任意窗口。足够预算时遗漏原文已有关键上下文属于选择器缺陷；预算不足时保留精确gap，仍不放宽引用验证。

所有窗口严格满足quote=原字段[start:end]，引用完全在实际发送窗口内；不拼不连续句、不改空白位置、不以全文.find取代offset。问题文字中的数字仅作定位线索，绝不写入任何来源窗口，未出现在原字段的数字断言必须失败。

## 9. 测试用例表（40项）

默认固定研究日2026-11-03、确认目标窗2026-01-01至2026-11-03、Mock与内存manifest。“允许保存”指未来B实现且整批无其他硬错，A阶段没有业务写入。新错误码是待实施契约，不声称现有已实现。

| ID/类型 | 输入条件 | 模型候选输出 | 程序检查 | 预期结果 | 允许保存 | 失败/未升级原因 |
| --- | --- | --- | --- | --- | --- | --- |
| T01 正常 | 单官方成功正文 | fact请求verified | 引文/逻辑来源/独立支持 | single_source，记录原因 | 是 | single_origin，官方不天然verified |
| T02 相依 | 两不同根域名转载同稿 | fact请求verified | body_hash/原稿链/来源组 | dependent、single_source，不计两票 | 是 | shared_origin |
| T03 正常 | 两根域名独立原文，同命题，有可信独立及支持审核 | fact请求verified | 编辑控制/根域名/正文/期间/可信绑定 | 程序授予verified | 是 | 无；不能只靠模型independent=true |
| T04 超量 | Q1三条、别题合法 | 3个不同候选 | Schema/每题业务预检 | 整批拒绝、零正式行 | 否 | question_limit，不裁剪 |
| T05 正常零条 | 某题无有效材料 | items=[]且本题gap | 题集合/缺口归属 | 接受零条和gap | 是，仅gap | 无 |
| T06 财年边界 | 2026-09-10发布FY2027 Q1，无覆盖日 | actual+有据标签 | 财年/来源日/覆盖分别验 | actual_result、label_only、type unknown，不因年份拒绝 | 是 | 不补日期，不伪称current_actual |
| T07 历史业绩 | 2024实绩低于市场预期 | historical_actual | 结果/比较对象/旧期间 | historical_actual | 是 | expected不等于预测 |
| T08 公司指引 | 公司预计下季20% | company_guidance | 公司主语/未来谓词/数值 | company_guidance | 是 | 写actual则temporal_mismatch |
| T09 分析师预测 | 分析师预计明年20% | analyst_forecast | 署名/预测/参考年 | analyst_forecast；缺锚点不补年份 | 是 | 假公司指引则speaker_mismatch |
| T10 伪区域 | 标题在原text内 | 报为extracted_body | 服务器区域/offset | 拒绝 | 否 | region_mismatch |
| T11 摘录 | 仅snippet声称20% | fact、snippet引句 | 精确命中/未读正文标记 | unverified线索 | 是 | snippet_only，不授verified |
| T12 提取失败 | failed但有snippet | snippet线索+gap | 状态/禁借旧正文 | unverified+body_unavailable | 是 | 强引body则extraction_unavailable |
| T13 前段数字 | 指标数字在正文前段 | 正确claim/quote | 选段/offset/可见 | 覆盖并接受 | 是 | 无 |
| T14 后段数字 | S26数字在910/1105 | 正确后段quote | 相关窗口/上下文/预算 | 足够预算覆盖52%/336% | 是 | 未发送则拒绝引用 |
| T15 跨段周期 | 数值和FY标签不同段 | 值link+period context | 两窗可见、同源作用域 | 接受标签，缺起止仍null | 是 | 无关段硬绑则unsupported_period |
| T16 无数字 | 任一来源均无336% | 伪造336% | 可见字段/数值依据 | 拒绝；正确应gap | 否 | quote_not_visible/unsupported_value |
| T17 发布日未知 | null日但正文财季明确 | fact+有据期间 | 日期unknown、期间单独核验 | 日期不补、标签可保留 | 是 | 无 |
| T18 周期未知 | 数字真但无期间 | type unknown、期间null | 值/未知关系 | 低等级允许，不称current | 是 | 强填财季则unsupported_period |
| T19 冲突错误 | 同期间body28%、snippet30% | 宣称唯一28%事实 | 区域/口径冲突 | 拒绝；另拟disputed双引可合法 | 否，该输出 | source_region_conflict |
| T20 新快照 | 新ID仅摘录/日期变、正文同 | 当两个独立源 | body_hash/来源组/旧引用 | 不增票，仅相应变化提醒 | 是，单源 | same_body_new_snapshot |
| T21 缺gap | 某题0条，仅全局gap | 无本题gap | 结构化题归属 | 整批拒绝 | 否 | missing_question_gap |
| T22 总量边界 | 5题各2条 | 合法10条 | 总量/每题/引用 | 接受10条 | 是 | 无 |
| T23 总量超 | 6题11条，每题≤2 | 合法结构 | 总量≤10 | 整批拒绝 | 否 | total_limit |
| T24 题集合 | 重复Q1/漏Q2/未知Q9 | 题组不同计划 | 集合/唯一题ID | 拒绝 | 否 | question_set_mismatch |
| T25 伪等级 | 模型写category=verified/final_category | 越权最终审定 | additionalProperties | Schema拒绝 | 否 | schema，不自动删字段 |
| T26 未知独立 | 两域不同文，无正向审核 | 请求verified | 未发现转载不证明独立 | 多源unverified/独立性unknown | 是 | independence_unknown |
| T27 混合事件 | actual18/预期20/指引22 | 都当实际一条 | 原子命题/值角色 | 拒绝 | 否 | mixed_temporal_claim |
| T28 正常实绩 | 上季已公布，明确截至2026-09-30 | current_actual | 目标窗/事件/日期 | current_actual，不称全球最新 | 是 | 只有相对季度则unknown |
| T29 市场预期 | 只预期20%，无结果 | market_expectation | market主语/无实绩 | market_expectation | 是 | 当actual则temporal_mismatch |
| T30 纠正后重复 | field纠正后同源同位置 | 重复link | 唯一纠正后重复校验 | 整批拒绝 | 否 | duplicate_link，不合并 |
| T31 位置歧义 | 同句可见两处、给错位置 | 无有效定位 | window+offset唯一性 | 拒绝；正确位置可接受 | 否，该输出 | ambiguous_quote |
| T32 越窗 | 两不连续窗口 | 拼句或引未发段 | 单可见区间包含 | 拒绝 | 否 | quote_not_visible/window_range |
| T33 伪日期 | 只有FY标签 | 补季度起止日 | context依据/精度 | 拒绝 | 否 | unsupported_period |
| T34 职务错 | 原句明确CEO | claim/摘要称CFO | 职务span/命题一致 | 显式矛盾拒绝 | 否 | claim_support_mismatch；自由摘要仍需人工 |
| T35 表格 | 数字无列头/单位/期间 | 指定某季金额 | 表格上下文完整性 | gap，强写事实拒绝 | 否，该输出 | table_context_missing |
| T36 预算不足 | 相关数字/期间超配额 | 引被省略数字 | 完整request字节/coverage | 不扩预算，拒绝引用 | 否，该输出 | coverage_omitted_budget |
| T37 根域名 | 不同组织*.co.uk、后缀未知 | 请求verified | 禁止split最后两段硬判 | unknown、不升级 | 是，低等级 | registrable_domain_unknown |
| T38 日期混用 | metadata只有发布日 | 当财季日期 | 区域用途/period关系 | 拒绝 | 否 | unsupported_period |
| T39 同字重现 | 标题句在真实后段body重现 | 正确后段offset | 具体区域而非全局黑名单 | 普通正文引句允许 | 是 | verified仍须全部条件 |
| T40 旧版本 | v1/v2/v3并存 | 读旧/新模型假报旧版 | 明确版本调度/旧行保留 | 旧可读；新请求强制v3 | 读是，伪装写否 | contract_version_mismatch |

集成附加断言：所有拒绝evidence/links/成功analysis新增0；失败Token/费用正常结算，未知预占保留，diagnostic路径/条目索引明确。允许保存也不自动确认报告或切换制作状态。

## 10. 可执行测试契约说明

附录给出可转为pytest文件的代码，A仅嵌入本文并静态核对，不创建.py、不运行SQL/API/业务测试。quality/materials接口当前不存在，B获批后先建立接口与fixture，再确认业务RED；缺模块导入失败不能当有效RED。

拟议纯函数：quality.assess_batch返回accepted/items/gaps/errors/decisions；temporal.classify_temporal返回event_kind/temporal_type/current_relation/coverage_start/end；materials.select_windows返回windows/coverage_gaps。三者不能读配置/文件/数据库/网络。


### 10.1 审核修订：测试分层、执行准入和结果证明

保留第9节T01–T40的全部输入/候选/预期，不删场景，不把“将来补测”当验收完成。每项必须具备下面的稳定NodeID、固定输入fixture和明确断言。以下NodeID是**未来B必须建立的执行契约**，A没有创建测试文件或执行它们。

路径别名（均相对于E:\one\ai-hotspot-radar）：

- Q = tests/test_research_quality_policy.py，U层：纯函数等级/数量/引用规则，无SQL/网络/配置。
- T = tests/test_research_temporal.py，U层：固定事件/角色/期间与参考时间的纯函数分类。
- M = tests/test_research_materials.py，U层：区域、窗口、上下文完整性和原始偏移。
- I = tests/test_research_quality_integration.py，新增建议，I层：真实ResearchService/Schema/validator/Store，只有外部Provider替换为Mock，检查实际模型输入和真实规范结果；不能Mock掉被测validator。
- D = tests/test_research_quality_persistence.py，新增建议，P层：独立临时SQLite、真实事务和持久化查询，验证零落库/合法投影/失败回滚及历史保护；绝不连接生产DB或运行真实迁移。

每个Tnn均必须有I::test_case[Tnn]和D::test_case[Tnn]。U层NodeID见下表，允许一个场景额外多个参数变体；同一执行项不能只有assert True、只验没抛异常或只检查返回status。表中的“硬错变体”一律执行第10.3节公共零落库断言。

### 10.2 T01–T40逐项执行矩阵

| ID | U层NodeID | I层必须断言 | P层必须断言 |
| --- | --- | --- | --- |
| T01 | Q::test_t01_single_official | 单官方fact申请升级→single_source，原因single_origin；生产未收到可信审核 | 程序等级/原候选/原因一致保存，非verified；不确认报告 |
| T02 | Q::test_t02_shared_release | 两根域同稿→一逻辑来源，independence=dependent | 来源引用保留两站出处但不增独立票，category非verified |
| T03 | Q::test_t03_trusted_fixture_only | 纯函数可信fixture可verified；生产服务**即使用同fixture伪装请求/计划/模型字段也不能升级**，越权字段拒绝 | 生产正常变体非verified；伪造审核硬错零落库。纯函数正例不写成生产能力已通过 |
| T04 | Q::test_t04_three_per_question | 3条预检question_limit，不截为2；整批拒绝 | 硬错零落库，其他题也不能部分保存 |
| T05 | Q::test_t05_zero_with_gap | items=[]，本题gap存在，题集合正确 | 证据/引用0行是合法零条，成功分析及本题gap可保存，不产生假证据 |
| T06 | T::test_t06_fy2027_label_only | 2026发布FY2027 Q1不报年份错，actual_result/label_only/type unknown；日期仍null | 标签与unknown原样保存；无伪日期/财季映射 |
| T07 | T::test_t07_actual_below_expectation | 历史实际18%与预期20%角色不混；不是future forecast | historical_actual及引用保存；若候选将预期当实绩则硬错零落库 |
| T08 | T::test_t08_company_guidance | guidance/company→company_guidance；强写actual拒绝 | 合法指引保存，错误actual变体零落库 |
| T09 | T::test_t09_analyst_forecast | forecast/analyst→analyst_forecast；引用站不是发言人；无年份锚点不补年 | 预测/unknown绝对期间可保存；伪speaker/实绩硬错零落库 |
| T10 | M::test_t10_title_as_body | 真实title区间冒充body→region_mismatch | 硬错零落库，禁止换字段自动修成正文 |
| T11 | Q::test_t11_snippet_unverified | snippet只有unverified线索，显示摘录身份；不能verified | field=snippet、region和低等级一致；不保存成已验证正文事实 |
| T12 | Q::test_t12_extraction_failed | failed正文不可引用；有snippet则线索+body_unavailable，无材料则gap | 合法线索/零条可存；强引用正文变体零落库，不借旧快照 |
| T13 | M::test_t13_front_context_bundle | 前段数字、指标/单位/主体及存在的期间均进入可见包，不只匹配数值 | 全文offset/quote/window/角色可回读核对；缺上下文不伪造 |
| T14 | M::test_t14_s26_fixed_body | **固定真实S26**全文hash与910/1105偏移校验；数字及OCI/GPU/必要上下文可见 | 合法引用保存精确原偏移；使用旧682窗仍强引后段则零落库 |
| T15 | M::test_t15_period_context_link | 数值与期间分窗同源/同题且作用域成立；有context_links而非拼句 | 两类引用及作用域可回读，未知起止null；无关段强绑硬错零落库 |
| T16 | M::test_t16_absent_number | 任一原文无336%→term_not_found；问题数字没有进入窗口；假引句拒绝 | 硬错零落库；另拟零条+本题gap正常保存，不自动替换原失败 |
| T17 | T::test_t17_publication_unknown | published_at未知不补，正文有据财季独立保留 | 日期unknown、期间依据保存，原source不回填 |
| T18 | T::test_t18_period_unknown | 数字有据、无期间→unknown；不能由发布日期推算 | 合法unknown可存；补造财季/current变体硬错零落库 |
| T19 | Q::test_t19_region_conflict | body28/snippet30同口径不静默择一，唯一事实候选拒绝；另拟双引disputed可用 | 冲突硬错零落库；合法disputed引用两区域且禁止verified |
| T20 | Q::test_t20_same_body_new_snapshot | 新source_id但body等值，不增独立来源；提醒仅发生的元数据变化 | 旧evidence/report引用与offset不改，新低等级只指明确快照 |
| T21 | Q::test_t21_missing_question_gap | 全局/他题gap不替代本题，missing_question_gap | 硬错零落库；不能偷偷补gap转成功 |
| T22 | Q::test_t22_ten_valid_items | 5题各2、共10，规范化不改变数量/内容 | 恰10条正式候选及匹配引用，逐题计数≤2 |
| T23 | Q::test_t23_total_eleven | 6题11条即使每题≤2仍total_limit | 硬错零落库，不保留前10条 |
| T24 | Q::test_t24_question_set | 重复/漏题/未知题分别参数化，集合精确相等 | 各硬错零落库；无跨题关联写入 |
| T25 | Q::test_t25_forbidden_grade_field | 模型category/final_category/审核字段均为额外字段硬错 | 各硬错零落库；无自动删字段后通过 |
| T26 | Q::test_t26_independence_unknown | 两域不同文、未发现转载≠独立→unknown/unverified | 审定结果和未授原因保存，数据库category非verified |
| T27 | T::test_t27_mixed_event_roles | actual18/预期20/指引22不可混为单actual；不靠关键词判型 | 错误混合候选零落库；独立正确候选仍受题量限制 |
| T28 | T::test_t28_published_actual | 有截至2026-09-30实绩→current_actual；仅“上一季”无锚点→unknown | 两正常变体按依据保存，不补财季日期，不声称全球最新 |
| T29 | T::test_t29_market_expectation | 只有市场预期→market_expectation；无actual值 | 预期正常保存；强写实绩变体零落库 |
| T30 | Q::test_t30_corrected_duplicate | 唯一合法字段纠正后重复→duplicate_link；不合并 | 硬错零落库，包括所有题的其他候选 |
| T31 | M::test_t31_ambiguous_occurrence | 同句两处且位置无效→ambiguous_quote；正确位置唯一则允许 | 错误变体零落库；正确变体存指定offset，不是find首处 |
| T32 | M::test_t32_window_boundary | 全文存在但未发/跨不连续窗的quote均拒绝 | 各硬错零落库，不用完整text事后追认 |
| T33 | T::test_t33_invented_dates | 仅FY标签却补起止日→unsupported_period | 硬错零落库，原日期不修改 |
| T34 | Q::test_t34_speaker_role_mismatch | 明确CEO与候选CFO角色冲突，claim_support_mismatch | 硬错零落库，不通过改摘要/角色修成成功 |
| T35 | M::test_t35_table_context | 数值无列头/单位/期间则table_context_missing；不够就gap | 强归属事实硬错零落库；合法缺口不产生假金额记录 |
| T36 | M::test_t36_context_budget | context在全文但没入预算→omitted_budget/context_incomplete；不增加请求/预算 | 强引用省略材料零落库；无调用本地停止不产生费用行；合法gap保持独立结果 |
| T37 | Q::test_t37_domain_suffix_unknown | *.co.uk无可靠后缀依据→registrable_domain_unknown，不硬算独立 | 低等级保存，category非verified；不新建网络取表调用 |
| T38 | T::test_t38_metadata_not_period | 发布日metadata不能支撑数据财季 | 硬错零落库，不给旧source补period |
| T39 | M::test_t39_title_text_reoccurs | 标题同句在真实正文重现按**正文坐标**允许，标题坐标不能借用 | 正常存后部offset/region；错借标题硬错零落库 |
| T40 | Q::test_t40_contract_version | 新调用假报旧版拒绝；旧批次只走历史reader | 伪装写硬错零落库；旧v1/v2 evidence/report内容不改，v3 JSON/SQL投影可回读 |

每行的U/I/D NodeID必须出现在B的测试收集清单和验收结果中，不能只建一个空壳参数用例遍历40个ID。同一fixture须包含明确输入、候选、预计硬错/非硬错、期望代码/等级/事件和**独立编写的断言**；不得由被测实现反推expected。

### 10.3 所有硬错误的公共数据库断言（必须逐场景运行）

适用于上表全部硬错主场景及其负向变体，包括T03伪造信任输入、T08/T09/T12/T14/T15/T17/T18/T28/T29/T39中的错误输出；不是只挑一条代表性用例验证事务。

1. 在临时库构造已有计划/搜索/来源和历史证据；调用真实研究服务，外部只有Mock Provider。保持真实Schema、assess、事务与Store路径，禁止把persist/validator替换成总返回成功的Mock。
2. 保存执行前**全库证据及引用**计数和旧行快照。错误后断言research_evidence总数不增加、research_evidence_sources总数不增加；旧证据/引用行内容也不改变。
3. 若已建立新analysis，按其ID再断言research_evidence WHERE analysis_id=new_id 为0，通过引用JOIN新analysis的links为0；没有analysis时不得伪造ID使WHERE空集冒充零落库。
4. 不存在该动作的success分析或结果版本；attempt失败、应有diagnostic.code/path，拒绝文档不被当成功结果。只有允许的分析/尝试/诊断/费用记录变化，不能新增研究报告、确认记录或状态变更。
5. Mock提供已知usage则输入/输出Token与费用仍按原计费规则结算；usage未知时保留unknown与预占，绝不能补0。预算设置/阈值、价格、max_attempts和项目状态前后不变；不为了测试改这些机制。
6. 对“持久化途中故障”增加专门注入：候选和引用不能部分提交，原事务回滚，已发生费用保留。这是与Schema拒绝不同的事务验证。

建议D层统一夹具可复用检查，但每个场景必须实际调用它。伪代码仅在本文，未创建/执行测试文件：

~~~python
# scenario由未来B测试fixture提供：独立临时库、真实服务、Mock Provider与固定expected。
# CASE_IDS覆盖T01到T40；不是从被测实现自动生成预期。
@pytest.mark.parametrize("case_id", [f"T{i:02d}" for i in range(1, 41)])
def test_case(case_id, scenario_factory):
    s = scenario_factory(case_id)
    before = s.capture_database_state()
    result = s.execute_real_service_with_mock_provider()
    after = s.capture_database_state()
    s.assert_case_specific_result(result, before, after)
    if s.expected.hard_error:
        assert result["status"] == "failed"
        assert after.evidence_count == before.evidence_count
        assert after.link_count == before.link_count
        assert after.old_evidence_rows == before.old_evidence_rows
        assert after.old_link_rows == before.old_link_rows
        s.assert_no_evidence_or_links_for_new_analysis(result)
        s.assert_no_success_result_or_report_version(result)
        s.assert_failure_diagnostic_and_original_usage_accounting(result)
    s.assert_budget_settings_retry_rules_and_project_status_unchanged(before, after)
~~~

合法零条T05与硬错零落库必须区分：前者可以是success+gaps、证据0行，后者必须failed且不能保存成功结果。只看count=0不足以区分两者。

### 10.4 固定S26 fixture、业务RED与执行证据

S26不能只用附录A的合成后段句子验收。B阶段的fixture应从已保存S26原始text只读取材，冻结为测试资源并记录source_id=26、对应快照标识、完整4549字符、UTF-8 SHA-256、offset语义（Python码点）与固定预期位置。**不得重新抓站点或每次从当前生产库加载，以免测试随数据漂移。** 本轮不导出或新建fixture文件。

必须先断言固定原text[910:913]为52%、text[1105:1109]为336%，再验证窗口精确切片、数字与OCI/GPU/主体/单位/可得期间及必要引语上下文；数字以外上下文不可用时须有准确coverage gap。正向充足预算、负向预算不足、只用旧[0,682)仍试图引用后文这三类都要测，禁止通过修改固定文本/偏移让测试通过。

后段窗口覆盖≠期间已证实：集成必须验证period context_links同快照、可见且关联正确；持久化必须读回SQL quote_offset和JSON region/window，二者与原文切片一致。不能只assert数字在拼接后的所有窗口中出现过。

B执行要求：

- 测试模块/接口先能收集并加载，fixture准备正常，再观察业务断言因目标缺陷失败，才是有效RED。ImportError、语法错误、环境故障不计有效RED，不用skip/xfail掩盖。
- 至少一次基于真实失败样本的RED→GREEN记录；Mock与临时库防护确认禁止网络、.env及生产库写入。T03生产路径另验证没有测试注入渠道。
- 测试报告列每个Tnn对应的U/I/D NodeID、参数变体、实际执行状态及失败原因；仅AST语法通过、收集到40项或返回值测试通过，都不能宣称持久化验收通过。
- 40项主场景及全部定义的硬错变体未执行/失败，B必须列未完成项，不得标整体验收通过。本A修订仍只交付设计，不执行上述测试。

## 11. v6兼容性与迁移决策

**建议B保持user_version=6，无迁移，不加表/列。** 现有input_json/analysis_json与schema_version足以持久候选/程序审定/材料区域/窗口/期间；现有category枚举和field=text/snippet+offset能存规范投影。JSON新版本明确，不重建引用表、不撤销只追加触发器。

| 内容 | 复用位置 | 必须同步 |
| --- | --- | --- |
| 候选/最终等级 | analysis_json及evidence.category | 只写程序等级，保存candidate和决策 |
| 时间/支持/相依 | analysis_json.items.temporal/quality/source_assessments | 不回填旧行，不信模型独立性 |
| 区域/窗口/selector | input_json manifest | 原text/snippet不改，窗口坐标固定 |
| region/window/role | analysis_json.items.links，SQL field/offset投影 | 读回核对position/candidate_id与SQL |
| 多项安全诊断 | v6 details_json | 扩研究白名单，保留脱敏/上限 |
| 人工独立性评估 | 目前没有生产供给 | 默认空；新入口未来另审，不虚构已有能力 |

历史v1/v2保留原分类，展示“历史AI分类，未按v3独立性审定”；旧category/source_id/quote_offset/报告/确认不变，不自动升级。新调用强制v3，禁止模型自报v2逃逸。guards需明确版本注册，不通过time_scope存在猜版本；新报告从审定数据读，旧依据legacy_unreviewed不能当新verified支持。

若要持久DOM区域、跨批次编辑审核、让独立title字段成为正式事实link，现有投影可能不足，应回设计审核再议追加v7；本方案没有这个要求，也不预建表。

## 12. 下一阶段文件与测试清单

以下相对路径均基于E:\one\ai-hotspot-radar，是B待审核清单，A未修改。

| 文件 | 下一阶段职责 |
| --- | --- |
| services/research/quality.py（建议新增） | 整批纯验证、等级授予/相依、原子命题支持 |
| services/research/materials.py（建议新增） | 区域派生/相关窗口/coverage，纯函数不联网 |
| services/research/temporal.py | 去错误年份/关键词规则，期间与事件分离 |
| services/research/schemas.py、prompts.py | 分题v3、候选权限、结构化gaps |
| services/research/service.py | manifest、统一assess、空可信审核供给、保持调用/费用 |
| database/research_store.py | 程序等级/准确offset保存与JSON回读，不改DDL |
| services/research/guards.py | 明确版本调度、报告统一时间/等级约束 |
| services/research/diagnostics.py与Store白名单 | 固定code/path/多项安全错误，保留脱敏和上限 |
| pages/research.py | 候选/程序等级、引用区域/缺口/原因显示，不改状态 |
| tests/test_research_quality_policy.py（建议新增） | T01–T05/T19–T26/T30/T37，等级/数量/保存 |
| tests/test_research_temporal.py（建议新增） | T06–T09/T17–T18/T27–T29/T33/T34/T38 |
| tests/test_research_materials.py（建议新增） | T10–T16/T31–T32/T35–T36/T39，S26 fixture |
| tests/test_research_quality_integration.py（建议新增） | T01–T40真实服务+Mock Provider集成，检查实际材料和审定结果 |
| tests/test_research_quality_persistence.py（建议新增） | T01–T40临时库投影/零落库/历史保护；硬错变体逐项执行 |
| tests/fixtures/research_quality（建议新增） | 合成及有限真实片段/manifest/期待，无Key/生产DB依赖 |
| tests/test_research_workflow.py、test_research_quality.py、test_research_page.py | 原保护回归与v3集成，不删旧测试掩盖失败 |

不改migration、价格/预算、评分/采集或制作状态服务，不升级依赖/模型，不扩输入上限、不新增调用。

## 13. 实施顺序、测试策略和验收

1. 审核A：确认无可信独立性评估不产verified、FY标签只有label_only可存unknown、v6零迁移；A完成即停。
2. B若获批先保存文件基线，锁纯函数协议/错误优先级，建立合成fixture；接口导入失败不计业务RED。
3. 先分题Schema/数量/gaps，再区域/窗口/准确offset/唯一纠正/重复拒绝。
4. 实现事件/期间规则，以A–E与FY2027反例验证不能凭expected/年份相等判断。
5. 实现程序等级与纯函数受信参数契约；生产装配强制空审核供给，不开发审核入口。正向隔离fixture与生产伪造审核负向同时覆盖。
6. 接入Store/诊断/报告/页面，显式schema/prompt/selector/policy版本，费用结算与原事务保持。
7. 临时库测旧版本只读、v3投影、失败无partial证据、保存故障回滚、动作幂等/依据变更；不连真实库。
8. 相关测试通过后按共享影响完整回归；284是历史基线，本轮没跑。环境异常用隔离配置/Mock/临时库解决，不跳过测试。
9. 单独交付B报告，真实API复测和真实库操作须另行授权；Mock通过不等于真实质量通过。

B最低验收：40表格场景都有可执行断言和实际结果；硬错无正式候选落库；正常unknown不误拒；S26窗口含数字/周期或明确缺口；模型不能写最终等级，无独立性正向依据不升级；旧数据、预算、费用、评分、状态不改。

## 14. 回滚方案与风险

A仅本文，无业务回滚。B实施前保存本期文件基线；真正需要回退时按基线逐文件还原本期内容，不git reset/checkout覆盖用户其他改动。

无迁移不等于旧程序能理解v3。若已存v3后需退旧应用，优先向前修复/停止生成，保留v3只读适配或明确拒绝访问该批次；不能删v3历史、降schema_version、改category迎合旧程序。失败诊断/费用保留。写入异常沿用事务回滚，不覆盖数据库；恢复旧备份会丢后续数据，超本方案授权。

风险/未解决项：

1. 纯文本无DOM不能完美恢复区域；heuristic不等于证明，unknown必须显示。
2. 正向独立性/同命题支持无可信输入，B可能0条verified，是保守结果而非降门槛理由。
3. FY具体起止与全球最新财报未知，不能套公司常见财政日历。
4. 复杂句、表格口径、条件预测、人物职务与摘要因果不能被有限规则全部证明，需unknown/人工审核。
5. 多窗口/JSON增加体积，须在原字节预算内控制，缺上下文就gap，不增检索或模型调用。
6. 同句多处、同文跨域、同源多快照易误归属；正确坐标、来源链/绑定不可省。
7. 新诊断code/path忘同步白名单会丢信息；不能以存未脱敏原始响应补救。
8. 只改Schema不改Store/guards/report会丢审定上下文，须验证SQL/JSON一致。
9. 服务商缓存是否原站最新、dateModified/转载链缺失，不能由代码推知。
10. 脱敏诊断不能完整回放；本次有本地拒绝产物不等于未来每次都有。

## 15. 本阶段执行边界检查

| 检查 | 实际 |
| --- | --- |
| 生产代码修改 | 否 |
| 数据库结构/数据修改或迁移 | 否；初稿曾只读URI核对，本轮仅文件哈希保护核对 |
| DeepSeek/Tavily/其他API、外部网页调用 | 否，0次 |
| .env读取/修改、Key输出 | 否 |
| 预算/模型配置/系统环境修改 | 否 |
| 真实搜索/提取/证据/研究报告/脚本生成 | 否 |
| Git提交/推送/历史/清理 | 否，已有改动和删除保留 |
| 实际业务测试执行 | 否；仅测试设计与文档代码静态核对 |
| 本轮修改文件 | 仅原REPORT_PHASE4_2_1_4_A_DESIGN.md；不新建其他文件 |

已有源码/测试/数据库及备份/文档建立只读SHA基线，交付前核对；本轮不称未来接口已实现、测试已通过或独立性已证明。

**完成本设计后停止，等待审核，不进入4.2.1.4-B。**

## 附录A：可转存pytest的离线验收代码（未执行）

以下为未来B的部分纯函数示例，代码只嵌入本文，未写入tests目录；完整验收以第10.1–10.4节的T01–T40单元/集成/持久化执行矩阵为准，不能只运行本附录就宣布全部通过。测试合成句子不冒充站点原文；T14另需冻结真实S26作集成fixture。接口输入中的区域/审核只在服务器可信侧构造，不让生产模型传入。

约定：题级maxItems对应question_limit、全局超限total_limit，其余结构错误schema，便于稳定诊断。assess_batch任何硬错返回accepted=False、items=[]；合法结果items有quality.final_category/independence_status/temporal/source_dates。select_windows返回windows/coverage_gaps，每窗严格为原字段切片。

~~~python
import copy
import hashlib
import json
import pytest
from services.research.quality import assess_batch
from services.research.temporal import classify_temporal
from services.research.materials import select_windows

AS_OF = "2026-11-03"
RESEARCH = {"as_of": AS_OF, "target_window": {"start": "2026-01-01", "end": AS_OF}}
POLICY = {"version": "quality-v3", "max_total": 10, "max_per_question": 2,
          "trusted_assessments": []}
TEXT = "公司报告收入增长20%。"


def source(sid=1, region="extracted_body", text=TEXT, status="success", domain="a.example.com"):
    field = "snippet" if region == "search_snippet" else "text"
    body = text if field == "text" else ""
    return {"source_id": sid, "project_id": 1, "run_id": 3,
            "snapshot_hash": f"snapshot-{sid}",
            "body_hash": hashlib.sha256(body.encode()).hexdigest(),
            "domain": domain, "question_ids": ["Q1"], "extraction_status": status,
            "published_at": "2024-12-10", "text": body,
            "snippet": text if field == "snippet" else "",
            "origin_group_id": f"origin-{sid}",
            "regions": [{"segment_id": f"s{sid}", "region": region, "storage_field": field,
                         "start": 0, "end": len(text), "boundary_confidence": "heuristic"}],
            "visible_windows": [{"window_id": f"w{sid}", "segment_id": f"s{sid}",
                         "region": region, "storage_field": field,
                         "start": 0, "end": len(text), "text": text}]}


def link(s, region=None):
    w = s["visible_windows"][0]
    return {"source_id": s["source_id"], "window_id": w["window_id"],
            "segment_id": w["segment_id"], "region": region or w["region"],
            "storage_field": w["storage_field"], "start": w["start"], "end": w["end"],
            "quote": w["text"], "role": "claim_support"}


def setup(*ss):
    ss = list(ss) or [source()]
    manifest = {"contract_version": "research-evidence-v3", "project_id": 1, "run_id": 3,
                "research_context": copy.deepcopy(RESEARCH),
                "questions": [{"id": "Q1", "question": "实际收入？", "keywords": ["收入", "20%"]}],
                "sources": {str(s["source_id"]): s for s in ss}, "coverage_gaps": []}
    item = {"candidate_id": "Q1-c1", "kind": "fact", "corroboration_requested": True,
            "summary": "来源声称收入增长20%，周期尚未核实", "inference": "", "verification": "候选",
            "claim": {"entity": "公司", "metric": "收入", "value": "20", "unit": "%",
                      "basis": "unknown", "speaker": "unknown"},
            "temporal": {"proposed_type": "unknown", "event_kind": "actual_result",
                         "speaker_kind": "unknown", "period": {"label_raw": "unknown",
                         "calendar_year": None, "fiscal_year": None, "fiscal_quarter": None,
                         "start": None, "end": None}, "context_links": []},
            "links": [link(s) for s in ss]}
    return {"questions": [{"question_id": "Q1", "items": [item], "gaps": []}]}, manifest


def rejected(c, m, *codes):
    result = assess_batch(c, m, copy.deepcopy(POLICY))
    assert result["accepted"] is False
    assert result["items"] == []
    assert set(codes) & {e["code"] for e in result["errors"]}


def grade(c, m, expected):
    result = assess_batch(c, m, copy.deepcopy(POLICY))
    assert result["accepted"] is True, result["errors"]
    assert result["items"][0]["quality"]["final_category"] == expected
    return result


def test_T01_single_official_source():
    c, m = setup(source(domain="investor.oracle.com"))
    grade(c, m, "single_source")


def test_T02_reprinted_release_is_one_origin():
    a, b = source(1), source(2, domain="b.example.org")
    b["origin_group_id"] = a["origin_group_id"]
    result = grade(*setup(a, b), "single_source")
    assert result["items"][0]["quality"]["independence_status"] == "dependent"


def claim_signature(item):
    # 未来契约的稳定命题指纹，不能用摘要或候选ID代替同一命题身份。
    identity = {"claim": item["claim"], "period": item["temporal"]["period"],
                "event_kind": item["temporal"]["event_kind"]}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def test_T03_verified_requires_trusted_independence_and_support():
    a = source(1, text="公司报告截至2024-11-30收入同比增长20%。")
    b = source(2, domain="b.example.org", text="独立调查：公司截至2024-11-30的收入同比增幅20%。")
    c, m = setup(a, b)
    item = c["questions"][0]["items"][0]
    item["summary"] = "截至2024-11-30收入同比增长20%。"
    item["claim"].update(basis="year_over_year", speaker="company")
    item["temporal"].update(proposed_type="historical_actual", speaker_kind="company")
    item["temporal"]["period"].update(label_raw="2024-11-30", end="2024-11-30")
    item["temporal"]["context_links"] = [dict(link(a), role="period_context")]
    for s in (a, b):
        s["regions"][0]["boundary_confidence"] = "reviewed"
    policy = copy.deepcopy(POLICY)
    policy["trusted_assessments"] = [{
        "claim_signature": claim_signature(item), "reviewer_id": "fixture-reviewer",
        "reviewed_at": "2026-11-03T00:00:00+00:00", "result": "confirmed_independent",
        "sources": [{"source_id": s["source_id"], "body_hash": s["body_hash"],
                     "snapshot_hash": s["snapshot_hash"], "editorial_entity": str(s["source_id"]),
                     "origin_group_id": s["origin_group_id"], "support": "confirmed",
                     "support_links": [link(s)]} for s in (a, b)],
        "basis": "fixture人工审定各自采集同一事实；无共同原稿；不是模型输出"}]
    result = assess_batch(c, m, policy)
    assert result["accepted"] is True, result["errors"]
    assert result["items"][0]["quality"]["final_category"] == "verified"
    # 去掉可信记录即不可升级，不能只用不同域名或不同正文。
    assert assess_batch(c, m, POLICY)["items"][0]["quality"]["final_category"] != "verified"


def test_T04_three_candidates_reject_whole_batch():
    c, m = setup()
    first = c["questions"][0]["items"][0]
    c["questions"][0]["items"] = [dict(copy.deepcopy(first), candidate_id=f"c{i}",
                                      summary=f"different-{i}") for i in range(3)]
    rejected(c, m, "question_limit")


def test_T05_zero_candidates_with_gap():
    c, m = setup()
    c["questions"][0].update(items=[], gaps=[{"code": "no_support", "detail": "无证据"}])
    result = assess_batch(c, m, POLICY)
    assert result["accepted"] and result["items"] == []
    assert result["gaps"][0]["question_id"] == "Q1"


def test_T06_FY2027_Q1_published_in_2026():
    result = classify_temporal("公司公布FY2027 Q1业绩。", {
        "published_at": "2026-09-10", "period_label": "FY2027 Q1",
        "coverage_start": None, "coverage_end": None}, RESEARCH)
    assert result["event_kind"] == "actual_result"
    assert result["current_relation"] == "label_only"
    assert result["temporal_type"] == "unknown"
    assert result["coverage_start"] is None and result["coverage_end"] is None


@pytest.mark.parametrize("text,context,expected", [
    ("公司公布实际收入增长18%，低于市场预期20%。", {"coverage_end": "2024-11-30"}, "historical_actual"),
    ("公司预计下一季度收入增长20%。", {}, "company_guidance"),
    ("分析师预测明年收入增长20%。", {}, "analyst_forecast"),
    ("公司已公布上一季度收入增长20%，截至2026-09-30。", {"coverage_end": "2026-09-30"}, "current_actual"),
    ("市场预期收入增长20%，尚无实际结果。", {}, "market_expectation"),
])
def test_T07_T08_T09_T28_T29_events(text, context, expected):
    result = classify_temporal(text, context, RESEARCH)
    assert result["temporal_type"] == expected


def test_T10_title_cannot_impersonate_body():
    c, m = setup(source(region="title"))
    c["questions"][0]["items"][0]["links"][0]["region"] = "extracted_body"
    rejected(c, m, "region_mismatch")


def test_T11_snippet_is_only_unverified():
    grade(*setup(source(region="search_snippet")), "unverified")


def test_T12_failed_body_can_only_keep_snippet_lead():
    c, m = setup(source(region="search_snippet", status="failed"))
    c["questions"][0]["gaps"] = [{"code": "body_unavailable", "detail": "正文不可读"}]
    grade(c, m, "unverified")


def window_case(text, keywords):
    s = source(text=text)
    # 选窗接口读取完整原字段，不依赖fixture预置窗口。
    s.pop("visible_windows")
    return select_windows([s], [{"id": "Q1", "keywords": keywords}], max_utf8_bytes=4096)


def test_T13_front_number_is_visible():
    text = "Oracle公布FY2025 Q2业绩，OCI收入同比增长52%。\n\n" + "背景。" * 300
    result = window_case(text, ["Oracle", "OCI", "52%", "FY2025 Q2"])
    visible = "\n".join(w["text"] for w in result["windows"])
    assert all(term in visible for term in ("Oracle", "OCI", "52%", "FY2025 Q2", "同比"))
    assert all(text[w["start"]:w["end"]] == w["text"] for w in result["windows"])


def test_T14_back_numbers_are_visible_with_original_offsets():
    text = "背景。" * 300 + "\n\nOracle公布FY2025 Q2业绩：OCI收入增长52%，GPU消费增长336%。\n\n结尾。"
    result = window_case(text, ["Oracle", "OCI", "GPU", "52%", "336%", "FY2025 Q2"])
    visible = "\n".join(w["text"] for w in result["windows"])
    assert all(term in visible for term in ("Oracle", "OCI", "GPU", "52%", "336%", "FY2025 Q2"))
    assert not any(g["code"] == "context_incomplete" for g in result["coverage_gaps"])
    for w in result["windows"]:
        assert text[w["start"]:w["end"]] == w["text"]


def test_T15_period_and_metric_in_separate_paragraphs():
    text = "Oracle公布FY2025 Q2业绩。\n\n" + "背景。" * 300 + "\n\n该季度GPU消费增长336%。"
    result = window_case(text, ["Oracle", "FY2025 Q2", "GPU", "336%"])
    assert any("FY2025 Q2" in w["text"] for w in result["windows"])
    assert any("336%" in w["text"] for w in result["windows"])
    assert all(text[w["start"]:w["end"]] == w["text"] for w in result["windows"])


def test_T16_absent_number_is_never_inserted():
    result = window_case("来源只有收入数据，未说明GPU增速。", ["GPU", "336%"])
    assert all("336%" not in w["text"] for w in result["windows"])
    assert any(g["code"] == "term_not_found" and g["term"] == "336%"
               for g in result["coverage_gaps"])
    c, m = setup()
    c["questions"][0]["items"][0]["links"][0]["quote"] = "GPU增长336%"
    rejected(c, m, "quote_not_visible", "unsupported_value")


def test_T17_unknown_publication_date_remains_unknown():
    s = source()
    s["published_at"] = None
    result = grade(*setup(s), "single_source")
    assert result["items"][0]["quality"]["source_dates"]["1"]["normalized"] == "unknown"


def test_T18_unknown_period_is_not_filled_from_publication():
    result = grade(*setup(), "single_source")
    t = result["items"][0]["quality"]["temporal"]
    assert t["temporal_type"] == "unknown"
    assert t["coverage_start"] is None and t["coverage_end"] is None


def test_T19_body_snippet_conflict_cannot_be_silently_resolved():
    s = source(text="公司公布收入增长28%。")
    snippet = "公司公布同一期间收入增长30%。"
    s["snippet"] = snippet
    s["regions"].append({"segment_id": "sn1", "region": "search_snippet", "storage_field": "snippet",
                         "start": 0, "end": len(snippet), "boundary_confidence": "provider"})
    s["visible_windows"].append({"window_id": "snw1", "segment_id": "sn1", "region": "search_snippet",
                "storage_field": "snippet", "start": 0, "end": len(snippet), "text": snippet})
    c, m = setup(s)
    c["questions"][0]["items"][0]["claim"]["value"] = "28"
    c["questions"][0]["items"][0]["summary"] = "唯一实际增长为28%"
    rejected(c, m, "source_region_conflict")


def test_T20_same_body_new_snapshot_is_not_two_votes():
    a, b = source(1), source(2)
    b["snapshot_hash"] = "new-metadata-snapshot"
    grade(*setup(a, b), "single_source")


def test_T21_gap_cannot_be_omitted():
    c, m = setup()
    c["questions"][0]["items"] = []
    rejected(c, m, "missing_question_gap")


def test_T25_model_cannot_write_final_category():
    c, m = setup()
    c["questions"][0]["items"][0]["final_category"] = "verified"
    rejected(c, m, "schema")


def test_T26_different_domains_and_text_are_insufficient():
    a = source(1)
    b = source(2, domain="b.example.org", text="独立措辞称公司收入增长20%。")
    result = grade(*setup(a, b), "unverified")
    assert result["items"][0]["quality"]["independence_status"] == "unknown"


def test_T32_full_document_match_outside_window_is_invalid():
    s = source(text="开头。\n\n后文包含20%。")
    s["visible_windows"][0].update(end=3, text=s["text"][:3])
    c, m = setup(s)
    quote = "后文包含20%。"
    start = s["text"].index(quote)
    c["questions"][0]["items"][0]["links"][0].update(start=start, end=start+len(quote), quote=quote)
    rejected(c, m, "quote_not_visible")
~~~

T03测试中的可信审核fixture来自测试服务端，不是模型参数。实现时核验审核作用域/版本/绑定，不能把任意调用者提供的JSON当可信；生产无供给就不得verified。其正例也不能替代真实独立性人工审核。

T19只要求检测这个简单可确定冲突fixture，复杂语句不可据此宣称已有通用语义支持。T15选窗单测还须在集成补“期间context_link与数字link关联正确”的断言；真实S26必须用固定原text和910/1105坐标，不能只用合成句替代验收。T01–T40全部按第10.1–10.4节逐项执行契约实现；附录代码只是部分纯函数示例，不能替代完整单元、集成及持久化验收。B报告必须逐项提供NodeID与实际结果。

附录实现细则：模型Schema分组的maxItems在服务商转换后可能被移除，须保留本地完整Schema；题级maxItems错误映射question_limit。数量校验只统计正式items，不能把多指标claim隐式拆开后裁剪。普通fact未满足升级门槛可存single_source，意味着有据单源陈述，不等于程序已证明摘要语义正确。

去根域名化假设：来源归组/受信评估记录属于服务器manifest/policy，不接受模型携带；其当前正式供给仅可生成duplicate/dependent/unknown。T03注入的trusted fixture只能证明授予规则在充分前提下工作，不能将这种fixture机制作为实际审核入口。

## 初稿交付核对记录（历史，非本轮执行结果）

- 本轮只读基线包含100个既有文件（源码、测试、数据库/备份、现有文档等，不读取.env），再次计算SHA全部一致；唯一新增为本文。
- Git与开始状态相比仅多出本文的未跟踪条目；原有修改、删除和未跟踪文件都保留。
- 测试表T01–T40完整且不重复，每行均含输入、候选、程序检查、结果、保存许可和失败/未升级原因。
- 附录22个测试函数，含5组事件分类参数，共26项未来接口验收用例；完成AST语法检查，未执行任何业务测试。其余场景已有明确表格断言及下一阶段测试文件映射，B实施验收时必须补齐可执行用例，不得冒称A已执行40项测试。
- 生产代码修改：否；数据库修改：否；真实API：否；.env读取或修改：否。

**4.2.1.4-A交付结束，等待审核；不进入4.2.1.4-B。**

## 本轮设计审核修订交付（2026-11-04）

本节为本次修订结果；前面的“初稿交付核对记录”只保留历史事实，不代表本轮重新执行数据库检查。

| 审核意见 | 本轮修订 | 设计状态 |
| --- | --- | --- |
| verified可信边界 | 第3.2节明确当前无生产审核来源；生产强制空供给，不开发入口；测试注入仅纯函数fixture；未来审核绑定来源快照、正文hash、原子命题和认证审核主体 | 边界已明确；实际审核能力仍不在B范围，不能以T03替代 |
| 时间分类边界 | 第6.3节分别定义event_kind/speaker_kind/temporal_type及有据组合；禁止单词直判；证据不足unknown、明确矛盾硬拒；保留FY2027和实绩/预期/指引回归 | 不以放宽日期/角色/原文标准换通过；复杂语义未知是明确结果 |
| 窗口上下文 | 第8.1节将数字/主体/指标/单位/期间/基准/必要引语上下文纳入coverage，区分未提供/未发送/预算省略/关联未知；同步加强附录选窗示例 | 不能只assert数字出现；问题数字不得写入原文，offset/逐字校验保留 |
| T01–T40执行 | 第10.1–10.4节给出40项U NodeID与逐项I/P要求、统一硬错误零落库断言及S26冻结真实fixture契约 | 全场景执行契约齐备；本轮未创建测试文件、未实施或运行测试 |

仍有的信息/能力缺口：可信审核记录与认证供给尚不存在；复杂时间语言、纯文本区域边界和实际覆盖日期不总能可靠判断。处理策略已确定为不授予verified、unknown/低等级或明确coverage gap；若未来要求解决这些缺口，须独立方案审核，不能假设已有能力。本轮没有待补的四项审核边界，下一阶段实现仍须按完整测试契约验收。

本轮边界复核：

- 唯一修改文件：E:\one\ai-hotspot-radar\REPORT_PHASE4_2_1_4_A_DESIGN.md；未新增/删除其他文件。
- 其余100个已纳入基线的源码、测试、数据库/备份和既有文档SHA不变；Git状态列表与修订前一致，原有修改/删除/未跟踪项全部保留。
- 未修改或执行任何Python生产代码、测试文件、数据库/迁移；未调用真实API，未访问.env，未修改预算、模型、重试、计费或制作状态。
- 静态检查：原40场景与40项执行映射完整且唯一，两段文档内Python代码AST语法有效。仅语法/设计一致性核对，不是测试运行或业务RED/GREEN结果。
- 没有Git历史变更、清理、暂存、提交或推送。

**修订完成，停止并等待审核；不进入4.2.1.4-B。**
