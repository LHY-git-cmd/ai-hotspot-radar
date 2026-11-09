# 4.2.1.4-B 第二批：研究服务接入与持久化事务保护

- 项目：ai-hotspot-radar；实际目录：`E:\one\ai-hotspot-radar`。
- 日期：2026-11-04（北京时间）。
- 状态：**本批完成，等待审核；未进入报告生成改造、页面改造或真实API验证。**
- 最终全量：**545 passed，0 failed，0 errors，0 skipped**；原有365项（原284项及第一批81项）全部执行，本批新增180项。
- 原365项中受新契约影响的Mock样本及过时预期，按本次“确认”授权迁移；不宣称旧测试内容逐字未改。未删除测试、skip、xfail或保留旧证据写入旁路。
- 无Git暂存、提交、推送、reset、clean、checkout；正式数据库及6个已有备份文件哈希不变。

## 1. 当前代码结构与接入路径

开始前读取修订设计、第一批交付、现有研究服务、Store、Schema、Prompt、Guard、迁移和相关测试。实际报告位置：

1. 根目录 `REPORT_PHASE4_2_1_4_A_DESIGN.md`。
2. 根目录 `REPORT_PHASE4_2_1_4_B_BATCH1.md`。
3. `docs/plan&report/REPORT_PHASE4_2_1_3_REAL_API.md`，名称一致，移动位置已由设计报告记载。

设计文件正文仍写等待审核；第一批报告记载修订版已获确认，本次任务再次指定其为已批准依据。只读检查后交付接入计划及文件清单，用户回复“确认”后开始实施。会话默认目录曾变为C盘空目录，随后确认Git根目录仍为E盘，所有实施命令显式使用E盘；没有复制项目。

实际写入链：

```text
organize_evidence
 → 保存来源及research_source_questions → source_record / build_manifest
 → materials.select_windows → model_materials（仅可见窗口及元数据）
 → v3 Prompt + CANDIDATE_SCHEMA → 原execute_attempts / 原费用账本
 → assess_document → 公开quality.assess_batch → temporal.classify_temporal
 → 先结算实际用量
 → BEGIN IMMEDIATE
 → 检查计划/最新搜索/冻结输入与数据库快照
 → 再次公开quality.assess_batch并核对规范结果
 → research_evidence + research_evidence_sources + analysis_json + 审计事件
 → 一起COMMIT；异常一起ROLLBACK
```

失败分析、费用和脱敏诊断按既有设计独立保留。质量拒绝不触发成功持久化，也不因诊断故障放行。

## 2. 新旧研究流程对照

| 项目 | 旧v1/v2流程 | 本批新v3流程 |
| --- | --- | --- |
| 材料 | text/snippet前缀 | 按确认问题选窗；区域、原偏移、coverage冻结 |
| 模型权限 | 输出最终category | 仅分题候选kind/claim/时间建议；越权字段整批拒绝 |
| 等级 | 模型分类及两域名旧门槛 | 公开assess_batch程序判定；生产没有可信审核供给 |
| 时间 | 发布年/宽泛预测词启发式 | 原发布日期、FY/季度、实际覆盖、事件/角色分别保留 |
| 引用保存 | 全字段.find取首位置 | 保存校验后的start；期间引用角色保留在JSON |
| 写入门禁 | 服务旧校验 | 服务及事务内双重公开质量判定，冻结快照/投影复核 |
| 读取 | 按position补时间字段 | v1/v2标legacy_unreviewed；v3核对SQL/JSON/窗口 |
| 缺口 | 字符串列表 | candidate_document及structured_gaps无损保存；gaps提供旧读取方字符串投影 |

历史category/报告不改、不降级、不自动认证；本批新写入强制research-evidence-v3。相同动作沿用原幂等语义；新动作追加新analysis，不覆盖旧批次。

## 3. 新模块实际接入位置与技术选择

沿用Python标准库、现有jsonschema、ResearchStore、SQLite事务和AI执行器；无新依赖、无DDL、无预算机制重设计。

| 文件/位置 | 实际职责 |
| --- | --- |
| services/research/service.py:198 organize_evidence | 从保存快照构造清单、扣除请求固定开销后选窗、冻结实际模型输入 |
| services/research/service.py:234 _validate_evidence | 必经v3质量入口；_generate对evidence强制使用该validator |
| services/research/service.py:279 _generate | evidence使用v3 Schema/Prompt/analysis版本；plan/report原流程保留 |
| services/research/evidence_contract.py | 新增最小装配模块：源区域、manifest hash、模型投影及程序结果 |
| services/research/materials.py | 通过build_manifest实际调用select_windows；本文件字节未修改 |
| services/research/quality.py | 公开assess_batch控制服务验证及事务内写入；仅补强正文署期冒充期间的漏洞 |
| services/research/temporal.py | 通过quality实际执行classify_temporal；本文件字节未修改 |
| services/research/schemas.py / prompts.py | 新证据请求固定CANDIDATE_SCHEMA及独立v3系统提示词 |
| database/research_store.py:114 / :157 / :224 | 安全批量诊断、版本读取与SQL/JSON复核、v3事务写入 |
| services/research/diagnostics.py | 扩展固定错误码及结构路径白名单；保留字符串脱敏和16KiB限制 |

没有调用quality私有审核接缝，没有向生产传审核记录/回调，没有新增审核配置、接口或UI。

## 4. Prompt和Schema实际调用证据

`test_strict_provider_request_really_uses_candidate_schema`实际经过ResearchService、DeepSeekProvider、request_body和本地校验，仅requests.post返回合成响应；无网络请求。

断言真实请求的工具名为submit_research_evidence、strict=True，parameters精确等于provider_schema(CANDIDATE_SCHEMA)，系统提示词为v3候选规则。服务工厂接收到的完整本地Schema也与CANDIDATE_SCHEMA逐值相等。

每题0–2、总计≤10、题集合完全一致；additionalProperties=False。category/final_category/verified/trusted_assessment/independence_verified/人工审核字段及伪body_hash均拒绝，不删除非法字段后继续使用。

版本实际落库为research-evidence-v3、research-evidence-prompt-v3、research-v3。模型不能自行选择旧版本。提供`test_public_policy_and_program_time_classifier_both_control_writes`，真实包装观察到公开assess_batch和时间分类分别执行两次（服务验证、事务复核）。

证据：`logs/phase4-2-1-4-b-batch2/strict-request-proof.json`、`T06-service-proof.json`、`T14-service-proof.json`及最终XML。请求证据不包含请求头或密钥。

## 5. 材料清单与模型输入一致性

input_json保存manifest和model_materials。源记录绑定project_id、run_id、question_ids、source_id、已保存content_hash对应snapshot_hash、UTF-8正文SHA-256、提取状态、原始发布日期/保存时间、原字段、region/segment及Unicode码点半开窗口。期间依据保留在可见原文、coverage的period上下文及审定结果的精确context_links中，未知不补。

标题、正文、搜索摘录、metadata不拼成一段；独占标题行包括导航/站点名之后的首次匹配标题，按具体位置隔离；后段正文中的重现句可用其真实正文坐标。纯文本区域边界标heuristic，不冒称DOM认证。独立title字段只作元信息，不硬塞成SQL业务事实引用。

模型sources中没有完整text/snippet字段；它只接收visible_windows及必要元数据。测试逐窗口比较模型实收窗口、冻结窗口、原字段[start:end]完全相等，未发送全文不能事后追认引用。标题/摘要伪装正文、错误来源、越窗、拼接不连续原句、位置歧义均覆盖。

先计固定Schema/Prompt/计划/元数据开销，再分配窗口预算；完整request_body仍经过原reservation_units。体积过大只减少窗口预算；最小请求仍放不下则在预占/调用前停止，不扩大上限或追加调用。coverage保留omitted_budget/context_incomplete/table_context_missing；提取失败另保留绑定本题、本快照的body_unavailable。

固定真实S26：4549码点，SHA-256为29ae66728e0afc0e87118fb551f9c231926efcf5f090dab7a3ae50aa906c5e27；52%=[910,913)，336%=[1105,1109)。真实服务正例选中[219,1452)，同时包含Oracle、OCI/Cloud Infrastructure、GPU consumption、两个数字、second quarter fiscal 2025及Management’s commentary；SQL与JSON偏移实际读回一致。负例覆盖预算省略、全文有但未发送、以及旧[0,682)前缀作为snippet快照只选其相关片段时仍强引后段；没有扩大旧前缀追认旧失败。

## 6. 证据质量判定接入结果

生产调用quality.assess_batch(candidate, manifest)，不传policy审核数据。单官方源最多single_source；snippet为unverified；同文/同正文新快照归同一逻辑来源；不同域名且不同正文仍independence_status=unknown，不能verified。co.uk等无法可靠确定根域名时保留未知及原因。

任何Schema、数量、关联、引用、角色、期间或明确时间矛盾均拒绝整个批次，其他题也不保存部分结果。合法0条可success并保留每题缺口；硬错0条必须failed、analysis_json为空，两者明确区分。

原候选、规范条目、quality、source_dates、temporal、decision_log及manifest hash一起保存。v6引用主键对同源/字段/起点唯一：同一完整引句同时承担支持与期间角色时只保存一个物理关联，JSON保留两种角色；同起点却给不同引句的投影冲突整批拒绝，不能静默丢引用。

## 7. 时间分类接入结果

保留event_kind、speaker_kind、temporal_type、原始发布日期/精度、calendar_publication_year、明确FY/季度、coverage_start/end和research_as_of。模型时间只是建议，程序结果从已核对的可见引文计算；没有依据则unknown。

FY2027 Q1场景实际保存：publication_year=2026、fiscal_year=2027、quarter=1、event_kind=actual_result、current_relation=label_only、temporal_type=unknown、coverage_start/end=null；没有把它改成2026财年或历史实绩。speaker_kind在该引文归属不足时仍unknown。

历史实绩低于预期不误作预测，公司指引/分析师预测/市场预期分别覆盖；将指引称实绩、混合事件、补造覆盖期等硬错整批失败。

额外RED发现正文中“发布日期2026-09-10”可被模型冒充覆盖结束日。quality.py已最小补强：classify_temporal仅从明确截至/期间表达提取覆盖日期，模型日期只核对、不再作为提供给分类器的覆盖依据。该对抗测试先成功落库导致RED，修复后拒绝且实际零写入；第一批81项继续通过。

## 8. I层逐项结果（85项，全部通过）

I层文件：tests/test_research_quality_integration.py。全部使用真实服务/验证/Store，仅外部Provider替换为Mock或HTTP响应Mock。

| 用户验收项 | 实际执行场景/测试 | 状态 |
| --- | --- | --- |
| 1 新Prompt/Schema进调用 | strict_provider_request、v3_controls_real_call_chain | 通过 |
| 2 窗口与实收一致 | 所有test_case逐窗口等值断言 | 通过 |
| 3 来源/hash/offset/区域不可伪造 | v3_controls_real_call_chain、T10/T31/T39及P层绑定故障 | 通过 |
| 4 模型不能给最终等级 | T25及5变体、T03-trust | 通过 |
| 5 只能引用实发窗口 | T14/T32/T36及变体 | 通过 |
| 6 标题/摘要不能冒充正文 | T10/T11/T39及变体 | 通过 |
| 7 时间由程序执行 | public_policy_and_program_time_classifier、时间场景 | 通过 |
| 8 FY2027 Q1 | T06 | 通过 |
| 9 单源不能verified | T01/T11/T12 | 通过 |
| 10 跨域不自动独立 | T02/T03/T20/T26/T37 | 通过 |
| 11 超量整批拒绝 | T04/T23 | 通过 |
| 12 0条保留每题缺口 | T05/T21及gap变体 | 通过 |
| 13 时间矛盾整批拒绝 | T08/T09/T27/T28/T29/T33、正文署期对抗 | 通过 |
| 14 诊断脱敏 | P层v3脱敏、旧P0脱敏回归；I层诊断失败路径 | 通过 |
| 15 原费用/预算 | invalid_batch_diagnostic_failure两变体、请求过小无预占 | 通过 |
| 16 新旧版本不覆盖 | 每场景旧行快照；P层v1/v2并存及两次追加 | 通过 |

I层共73项T场景（40主场景+33变体），另12项调用/诊断/预算等专项。逐NodeID状态见test-results.json；I/P完整T矩阵见下节。

## 9. P层逐项结果（95项，全部通过）

P层文件：tests/test_research_quality_persistence.py。临时SQLite真实写入、连接、触发器故障及事务；没有Mock数据库或仅检查返回值。

| 用户验收项 | 实际执行场景/测试 | 状态 |
| --- | --- | --- |
| 1 成功完整写入 | 40场景全部合法变体、transaction_and_binding[none] | 通过 |
| 2 硬错零写入 | 每个硬错场景查询全库和新analysis证据/关联 | 通过 |
| 3 关联无部分写入 | link_exception、second_link、重复引用/角色测试 | 通过 |
| 4 analysis_json无部分更新 | analysis_exception、after_analysis | 通过 |
| 5 中途异常回滚 | second_evidence/second_link/after_analysis | 通过 |
| 6 跨项目 | foreign_snapshot_source[cross_project]、绑定篡改project | 通过 |
| 7 不存在source_id | foreign_snapshot_source[missing]、绑定篡改source | 通过 |
| 8 错body_hash | 重新计算manifest hash/模型投影后仍与SQL来源不符，被拒绝 | 通过 |
| 9 重复引用 | T30硬错；支持/期间同完整引句单物理关联 | 通过 |
| 10 旧报告/证据原样 | 每场景旧行前后全值比较，legacy_unreviewed | 通过 |
| 11 新版不覆盖旧版 | v1/v2两种旧样本各追加两批v3 | 通过 |
| 12 失败诊断无敏感值 | v3敏感summary/Authorization字段脱敏及16KiB约束 | 通过 |

P层73项T场景及22项绑定、回滚、跨项目、历史、读回、并发等专项。每场景包含旧证据/引用/报告夹具，所有硬错均查询新analysis的证据与引用JOIN为0、全库旧行相等、成功JSON为空、费用保留；不是只测纯函数accepted。

下表各项均实际执行I::test_case[Tnn]和P::test_case[Tnn]，另执行所列变体。I/P完整NodeID及第一批U层实际状态在test-trace.json，545项逐条状态在test-results.json。

| 场景 | I实际项数/状态 | P实际项数/状态 | 额外变体 |
| --- | --- | --- | --- |
| T01 | 1 / 全通过 | 1 / 全通过 | 无 |
| T02 | 1 / 全通过 | 1 / 全通过 | 无 |
| T03 | 2 / 全通过 | 2 / 全通过 | T03-trust |
| T04 | 1 / 全通过 | 1 / 全通过 | 无 |
| T05 | 1 / 全通过 | 1 / 全通过 | 无 |
| T06 | 1 / 全通过 | 1 / 全通过 | 无 |
| T07 | 2 / 全通过 | 2 / 全通过 | T07-expected |
| T08 | 2 / 全通过 | 2 / 全通过 | T08-actual |
| T09 | 3 / 全通过 | 3 / 全通过 | T09-speaker, T09-actual |
| T10 | 3 / 全通过 | 3 / 全通过 | T10-header, T10-impersonate |
| T11 | 2 / 全通过 | 2 / 全通过 | T11-bodyregion |
| T12 | 3 / 全通过 | 3 / 全通过 | T12-body, T12-gap |
| T13 | 1 / 全通过 | 1 / 全通过 | 无 |
| T14 | 4 / 全通过 | 4 / 全通过 | T14-unseen, T14-budget, T14-old682 |
| T15 | 2 / 全通过 | 2 / 全通过 | T15-unrelated |
| T16 | 2 / 全通过 | 2 / 全通过 | T16-gap |
| T17 | 2 / 全通过 | 2 / 全通过 | T17-fake |
| T18 | 2 / 全通过 | 2 / 全通过 | T18-fake |
| T19 | 2 / 全通过 | 2 / 全通过 | T19-disputed |
| T20 | 1 / 全通过 | 1 / 全通过 | 无 |
| T21 | 1 / 全通过 | 1 / 全通过 | 无 |
| T22 | 1 / 全通过 | 1 / 全通过 | 无 |
| T23 | 1 / 全通过 | 1 / 全通过 | 无 |
| T24 | 3 / 全通过 | 3 / 全通过 | T24-missing, T24-unknown |
| T25 | 6 / 全通过 | 6 / 全通过 | T25-category, T25-trust, T25-independence, T25-verified, T25-review |
| T26 | 1 / 全通过 | 1 / 全通过 | 无 |
| T27 | 1 / 全通过 | 1 / 全通过 | 无 |
| T28 | 3 / 全通过 | 3 / 全通过 | T28-unknown, T28-fake |
| T29 | 2 / 全通过 | 2 / 全通过 | T29-actual |
| T30 | 1 / 全通过 | 1 / 全通过 | 无 |
| T31 | 2 / 全通过 | 2 / 全通过 | T31-valid |
| T32 | 2 / 全通过 | 2 / 全通过 | T32-splice |
| T33 | 1 / 全通过 | 1 / 全通过 | 无 |
| T34 | 1 / 全通过 | 1 / 全通过 | 无 |
| T35 | 2 / 全通过 | 2 / 全通过 | T35-gap |
| T36 | 2 / 全通过 | 2 / 全通过 | T36-gap |
| T37 | 1 / 全通过 | 1 / 全通过 | 无 |
| T38 | 1 / 全通过 | 1 / 全通过 | 无 |
| T39 | 2 / 全通过 | 2 / 全通过 | T39-title |
| T40 | 1 / 全通过 | 1 / 全通过 | 无 |

## 10. 事务回滚的实际数据库验证

成功调用先由原执行器结算Token/费用，再进入ResearchStore原BEGIN IMMEDIATE事务。Store读取该analysis的冻结input_json，核对项目/任务/版本、manifest hash、真实来源集合、问题关联、快照、body_hash、原字段、区域、模型投影、确认计划目标窗，再重跑公开assess_batch，要求规范结果逐值相等，最后插入。没有旧v2文档的新增证据分支。

三项中途故障由临时SQLite真实触发器RAISE(ABORT)产生：

| 故障位置 | 全库evidence 前→后 | 全库links 前→后 | production_versions 前→后 | 新analysis_json | 原用量/费用 |
| --- | --- | --- | --- | --- | --- |
| 第2条证据前，已有第1条及引用 | 1→1，旧行相等 | 1→1，旧行相等 | 2→2 | null | 20/30 Token，280微元 |
| 第2条引用前，已有证据及第1条引用 | 1→1，旧行相等 | 1→1，旧行相等 | 2→2 | null | 同上 |
| analysis_json执行UPDATE之后 | 1→1，旧行相等 | 1→1，旧行相等 | 2→2 | null，更新回滚 | 同上 |

新analysis状态failed；模型attempt仍记录success及实际已发生费用，诊断stage=persistence。另有关联写入、JSON更新前故障、重新签hash后的快照绑定篡改、规范结果offset篡改、旧格式文档、并发计划/搜索变化等实际事务测试。

证据：rollback-second_evidence.json、rollback-second_link.json、rollback-after_analysis.json，均在本批logs目录，包含合成临时库执行前后记录和费用。临时故障触发器只存在于各自测试库，不是正式DDL或迁移。

## 11. 旧数据与版本保护

- v1/v2 reader只返回历史分类，明确review_status=legacy_unreviewed，不补quality或v3认证。
- v3 reader检查契约版本、manifest完整性、条数、position、类别、摘要及SQL引用集合与JSON；窗口region/segment/start/end/quote重新核对，不一致抛错，不静默回退text。
- 每个T场景保留旧报告/来源/证据/引用快照；硬错全值相等，成功仅追加本批记录。
- 专项对v1/v2分别建立真实旧格式JSON，各追加两次v3，旧analysis和旧报告原值保持。
- 正式库整体SHA不变，覆盖其中全部历史报告/证据/费用/确认记录，不仅是抽样检查。
- 旧页面直接读取字符串gaps，保持该只读投影；结构化缺口无损保存在structured_gaps与candidate_document。未改页面、报告生成、报告确认或制作守卫。

## 12. 数据库v6未改变的证明

仅使用mode=ro&immutable=1核对正式库，打开前确认无WAL/SHM/journal，不实例化正式Store，不执行正式迁移或业务写入。

| 项目 | 实际结果 |
| --- | --- |
| user_version | 前后均6 |
| 正式库SHA-256 | 前后均877a0c8ab26808a12f5dd284a06fe9811205549ec66215a59b7728fe7c7db4e4，与第一批相同 |
| sqlite_master结构SHA-256 | 前后均fb0206a7f7d62b4b220dd69dddd6dddabf266c840dc4d8cd04900830e98e5cb3 |
| 表/显式索引/触发器 | 23 / 20 / 19；未新增或修改 |
| integrity_check / foreign_key_check | ok / 0错误 |
| 正式库及6个已有备份 | 7个文件逐个哈希不变 |
| 迁移源码 | migrations.py、research_migration.py、research_quality_migration.py等保护文件哈希不变 |

临时P层测试另逐场景比较sqlite_master前后相同；故障专项在临时库安装测试触发器。原有迁移回归只在临时库执行既有迁移，不是本批新增迁移。

## 13. 预算与费用逻辑未改变的证明

services/ai/config.py、cost_tracker.py、executor.py、database/ai_store.py等与实施基线字节相同；100元默认预算、价格/汇率、预占/结算规则和max_attempts没有修改。verification.json列出32项保护文件逐项哈希结果；报告生成/保存/确认、搜索/计划等原方法源码逐段相同。

候选验证失败仍按Mock已知20输入/30输出Token结算280微元（0.000280元），不记0；费用未知的失败保留null与预算占用。诊断保存失败也保留主拒绝和费用。持久化失败保留成功模型attempt的费用。完整请求超过上限在调用和预占前停止，此时没有费用尝试行。

输入/Schema变化会改变既有算法算出的预占量，费用算法本身未改。搜索credits仍与模型预算分开，原预算/重试/未知费用回归全部执行。

## 14. .env与真实API未访问的证明

测试驱动安装Python audit hook，阻断.env文件打开、外部socket.connect及正式data目录SQLite连接；conftest原隔离配置保留。配置均使用显式AISettings和合成测试Key，只有Mock Provider或Mock HTTP响应，无真实DeepSeek/Tavily请求。

最终full-final-io-guard.json：pytest_exit=0；dotenv_denied=0、network_denied=0、production_database_denied=0；仅109次标准库Windows socketpair内部唤醒连接，按调用者为socket.py/_fallback_socketpair精确放行，不放行普通回环HTTP。

本批没有读取、输出或计算.env内容哈希，没有运行load_ai_settings读取真实配置。只读源码时看到配置函数定义不等于执行其密钥读取。正式库只读核对发生于测试护栏之外的明确只读URI操作，测试本身从未连接正式库。API请求证据不保存Authorization或其他请求头。

## 15. 测试记录与全量结果

| 执行记录 | 实际结果 | 说明 |
| --- | --- | --- |
| integration-red | 6失败 | 真实调用仍为旧Schema，模块/fixture正常；有效业务RED |
| integration-first | 5通过、1失败 | 剩余失败是v3读回缺quality |
| persistence-red | 2通过、8失败 | hash/快照/偏移/旧格式等绕过旧Store；有效业务RED |
| contract-first | 11通过、5失败 | 失败批次reader错误要求成功JSON，随后修复 |
| old-first | 96通过、13失败 | 旧Mock契约与时间/计数预期需迁移 |
| matrix-first | 148通过、2失败 | 同一T12-body错误码预期写错；改为真实extraction_unavailable，不降低拒绝要求 |
| old-migrated | 91通过、2失败 | 截断样本规模与历史引文相关词不足，补齐有意义输入 |
| expanded-first | 249通过 | 新场景及旧服务回归 |
| publication-red | 1失败 | 正文发布日期被当覆盖期间；有效安全RED |
| focused-final | 81通过 | 日期补强和费用/持久化/纯函数专项 |
| full-acceptance | 530通过、3失败 | 旧页面字符串gaps兼容、测试query输入变化；保留原失败日志 |
| compatibility-fixed | 165通过 | 服务兼容投影及测试准备修正；页面未改 |
| variants-added | 8通过、1失败 | 测试错要求选择器发送全部旧snippet；改为核对实际区域窗口均来自旧前缀且不含后段 |
| variants-budget | 13通过 | 补强预算省略、提取失败及标题区域变体 |
| **full-final** | **545通过，0失败/错误/跳过** | **XML 132.859秒，控制台133.05秒；最终验收** |

最终命令（E盘项目目录）：

```powershell
.\.venv\Scripts\python.exe -B logs/phase4-2-1-4-b-batch2/run_tests.py full-final
```

完整结果包含：原284项、第一批81项、本批I层85项和P层95项。所有T01–T40的U/I/P及所定义的33个I/P额外变体均有实际结果；没有skip/xfail。定向命令的deselected只是选取相关用例，最终全量545项全部执行。

旧测试迁移说明：

- tests/research_support.py新增仅测试使用的CandidateFixtureProvider，生产MockProvider及正式Provider不改。旧样本显式转为v3候选；模型verified及额外非法字段保留为非法字段送真实Schema拒绝。
- 原“两域名+模型verified成功”测试改为整批拒绝、零证据及schema诊断；这是用户确认的过时预期修正。
- 非数值材料缺少原子指标/数值上下文时，旧single_source预期改为unverified，保留原引句、SQL读回与来源不变断言。
- 时间测试使用明确公司指引、真实覆盖截至日，不能再用旧发布日期推断历史数据；新错误码改为temporal_mismatch等，不放宽失败/费用/零写入要求。
- 十条合法候选用事实/观点两个明确不同kind，避免只改summary伪装重复事实；超量/重复负例保留。
- 截断样本由3000扩为30000字符，验证真实新预算下的省略，而非继续假设旧1200字符前缀上限。
- 五个参数化NodeID因错误码更新而更名，逐条列于test-summary.json；其余旧测试均保留。测试总数没有减少。

每个最终NodeID的状态在test-results.json；T编号追踪在test-trace.json；所有阶段XML、日志及测试护栏记录均保留。真实API质量不在本批验收范围，Mock通过不冒充真实联网验证。

## 16. Git变更清单及交付证据

相对于本批开始的内容哈希基线，而非相对于用户此前Git HEAD：

| 文件 | 本批变化 |
| --- | --- |
| services/research/evidence_contract.py | 新增服务装配、可信来源绑定、模型投影及规范结果 |
| services/research/service.py | 接入选窗/公开质量门禁及v3调用版本，移除旧新增证据验证路径 |
| services/research/schemas.py | 新证据调用使用候选Schema；旧Schema仍留作历史契约 |
| services/research/prompts.py | 独立v3证据Prompt；计划/报告原Prompt保留 |
| services/research/quality.py | 最小补强正文署期不能冒充覆盖日期 |
| services/research/diagnostics.py | 固定v3错误码和安全路径 |
| database/research_store.py | 冻结输入/SQL绑定复核、双重公开质量判断、准确偏移、版本读取及安全诊断 |
| tests/research_service_cases.py | 新增40场景及33变体，真实服务夹具/旧历史/SQL断言 |
| tests/test_research_quality_integration.py | 新增85项I层测试 |
| tests/test_research_quality_persistence.py | 新增95项P层测试 |
| tests/research_support.py | 仅旧回归测试的v3 Mock候选适配 |
| tests/test_research_workflow.py | 迁移旧Mock、相关词准备、过时verified预期及真实预算截断样本 |
| tests/test_research_quality.py | 新诊断路径/错误码、明确覆盖/指引样本、合法十条不同候选 |
| REPORT_PHASE4_2_1_4_B_BATCH2.md | 本交付报告 |

原有9个文件修改、4个代码/测试文件新增及本报告新增。用户此前.env.example、README、app、AI模块、删除的PLAN文件及其他未提交/未跟踪内容全部保留，未归入本批成果。materials.py、temporal.py、guards.py、pages、预算/费用、迁移、评分和制作状态等32个保护文件哈希核对未变。

证据目录：logs/phase4-2-1-4-b-batch2（Git忽略目录）。主要文件：

- baseline.json及baseline/：92个已有文件的哈希及源码/测试基线副本；未包含.env。
- verification.json、git-before.txt、git-after.txt、tested-hashes.json：范围与保护核对。
- full-final.xml / full-final.log / full-final-io-guard.json：最终执行记录。
- test-results.json / test-summary.json / test-trace.json：逐项结果、分类统计、U/I/P追踪。
- strict-request-proof.json、T06-service-proof.json、T14-service-proof.json：实际Mock调用、冻结窗口及SQL/JSON结果。
- rollback-*.json：真实临时SQLite故障前后记录。
- run_tests.py：用途为本批pytest护栏及日志驱动；不加载真实配置、不提供生产功能。

没有暂存或提交；交付后等待审核。

## 17. 未解决问题、限制与停止边界

1. 生产仍无正式可信独立性审核入口，v3不会自动授予verified；未创建伪造可信审核记录。旧verified只保留为legacy_unreviewed历史分类。
2. 来源为保存的纯文本快照，区域定位为启发式，缺DOM不能保证通用正文边界恢复；转载链/编辑控制缺乏正向证明时保持unknown。
3. 复杂语义、跨段作用域、财年具体日历边界、全球最新财季不能由有限规则自动证明；不足保留unknown，不使用模型常识填补。
4. 本批保留旧页面需要的字符串缺口投影，未开发v3审定信息展示、审核UI或报告生成新规则。原有报告Mock回归继续执行，但没有正式研究报告生成、真实API请求或页面改造。
5. v6字段/JSON足以承载本批契约；物理引用投影冲突整批拒绝，不改DDL或丢关联。后续若要增加独立title事实、DOM或持久可信审核记录，须另行设计授权。
6. 日志证据在Git忽略目录，未加入暂存；审核时应同时查看本报告及该目录。

本批范围内无未通过测试或待完成实施项。**到此停止，等待审核；不继续报告生成、页面改造或真实API测试。**
