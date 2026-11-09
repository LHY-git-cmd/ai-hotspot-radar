# 4.2.1.4-C-A：研究报告生成与确认门禁设计

- 项目：ai-hotspot-radar；审计目录：`E:\one\ai-hotspot-radar`。
- 日期：2026-11-04（北京时间）。
- 状态：**只读审计和待审核设计；未实施、未执行测试、未生成业务研究报告。**
- 依据：已验收的B两批成果，重点核对 `REPORT_PHASE4_2_1_4_B_BATCH2.md`、实际源码、现有测试及正式SQLite v6结构。
- 本次唯一文件交付为本文。没有修改生产代码、测试、数据库、配置或环境变量，没有调用任何外部API，没有Git写操作。
- 设计主张：**模型组织表达；程序绑定与验证证据；用户单独确认具体报告版本。** 报告校验通过不等于来源独立性已获认证，人工确认也不能升级证据等级。

## 1. 当前报告生成链路

以下为当前代码静态审计结论，不是本阶段运行或漏洞复现结果。文件行号为本次读取版本。

```text
pages/research.py:_report_area
 → ResearchService.generate_report(project_id, action_id)
 → basis()/guards.current_basis：当前确认计划、最新成功/部分成功搜索、该搜索最新成功证据分析
 → ResearchStore.evidence + sources：读取证据及来源元数据
 → prompts.messages('report') + SCHEMAS['report']
 → ResearchService._generate → execute_attempts → Provider.complete
 → Schema校验 → guards.validate_report
 → 原费用结算
 → BEGIN IMMEDIATE：再次检查basis → VersionService.create(research/report)
    → version_guard再次校验 → 追加production_versions/审计 → complete_model
 → 用户编辑：save_report → 同一版本服务及守卫
 → 用户确认：confirm_report → research_report_confirmations + report_confirmed审计
 → require_report → ProjectService调整后续状态 / VersionService创建、恢复后续内容
```

| 当前入口 | 位置 | 已有保护 | 仍沿用的旧契约/缺口 |
| --- | --- | --- | --- |
| 生成报告 | services/research/service.py:240 | 读取数据库证据、当前依据检查、原预算/执行器 | 报告仍为research-report-v2、research-prompt-v2、research-v2；未强制证据版本v3 |
| 报告Schema | services/research/schemas.py:47 | 重要列表项至少1个整数evidence_id；未知对象字段拒绝 | text + evidence_ids + 五类time_scope；无结构化数值/期间继承、等级/缺口覆盖契约 |
| 报告Prompt | services/research/prompts.py:SYSTEM/messages | 声明只用材料、引用证据、预测不当实绩 | report仍共用旧SYSTEM，含“当前须匹配研究年份”等旧要求；不是证据v3专用Prompt |
| 报告校验 | services/research/guards.py:50 | 项目/搜索/分析ID关联及证据ID集合、旧时间约束 | 直接拼SQL/analysis_json，未复用严格v3读取；按证据v2或字段存在猜报告格式 |
| 保存版本 | service.py:257、VersionService._create | 版本只追加，业务和审计同事务 | 人工内容也只走旧校验；生成前未绑定“预期最新报告版本”，并发人工编辑可能被后完成的AI版本置后 |
| 人工确认 | service.py:263 | 最新报告、当前basis、再次旧校验；确认只追加 | 无报告内容hash、校验策略/快照hash、确认主体或可信交互意图契约 |
| 后续准入 | guards.py:91/101、project_service.py:77 | 状态变更、恢复到后续阶段、通用内容创建/恢复均有集中门禁 | require_report只检查确认行存在和basis相等；不复核确认行全部绑定或v3校验凭据 |
| 页面 | pages/research.py:232 | 当前版本复核checkbox、dirty/stale提示、显示引用 | 页面字段仍旧格式；checkbox不是服务端身份或确认授权凭据 |

当前仓库未发现独立报告服务或实际脚本生成服务；页面“进入脚本制作”目前只调整人工状态。设计覆盖已有状态/版本入口及未来脚本生成的准入接口，不把尚未实现的脚本生成当作已有能力。

当前事实、结论、数据、差异四个列表虽校验ID，但没有检查文本中的数字是否就是对应证据的数字，也没有通用等级继承或争议/缺口保留规则。overview、objective、unverified、risks更是自由文本，可能容纳未绑定的重要陈述。这些是静态可见的校验缺口，不能以B阶段545项通过推断报告v3已实现。

## 2. 现有代码与数据库结构审计

### 2.1 v3证据可复用能力与读取边界

B阶段已将证据新增路径固定为公开 `quality.assess_batch`。input_json包含冻结manifest及实发model_materials；analysis_json包含候选、程序quality/temporal、structured_gaps、decision_log及manifest hash。SQL证据/来源引用保存程序等级、原字段及准确偏移。

`ResearchStore.evidence`（database/research_store.py:157）已按v1/v2/v3分流，检查v3 manifest hash、SQL/JSON条数、位置、类别、摘要、引用集合和可见窗口；旧数据标legacy_unreviewed。**但该方法本身不是完整报告授权读取器**：还需要报告上下文的purpose/status、项目/搜索/确认计划/当前证据批次约束、实际来源快照复核、完整审定结果一致性及同一连接快照。不能只在调用它后直接把返回字典当作报告授权凭据。

拟将B阶段Store写入中的无副作用绑定检查提取为共用连接级读取/核验内核：读报告、事务复核、确认、准入均调用它，再通过明确的v3入口，不能新增独立拼SQL的宽松报告旁路。不能用直接调用私有质量测试接缝来证明“已验证”。

### 2.2 正式v6实际结构

本次以 `mode=ro&immutable=1` 读取sqlite_master、列、外键及完整性；连接前确认无WAL/SHM/journal。未查询业务正文或运行Store初始化。

| 表/字段 | 现有能力 | 设计约束/不足 |
| --- | --- | --- |
| production_versions：project_id/object_id/version_number/content_json/source/restored_from_version_id | JSON完整快照；对象内版本号唯一；版本及审计有禁止UPDATE/DELETE触发器 | 没有报告专用版本/校验列，放在v3 JSON并由程序严格核验 |
| production_actions：action_type/details_json | 追加式结构化审计；可用updated携带报告事件、hash和确认意图元数据 | 自由JSON本身不证明身份；没有独立actor认证或事件签名 |
| topic_analyses：purpose/production_project_id/input_json/analysis_json/schema_version/result_version_id/status | 模型输入/结果、版本标签、报告版本关联、失败状态 | 通用status只允许running/success/failed/uncertain；不能把六个业务状态塞进CHECK列 |
| ai_analysis_runs | 独立Token、费用、预占、attempt状态 | 与业务验证/版本提交区分，保存失败不能抹掉调用费用 |
| research_evidence / research_evidence_sources / research_sources | 项目/搜索/批次、冻结来源和引用 | evidence.analysis_id和确认表evidence_analysis_id仅单列外键；跨项目一致性仍须应用层联合核对 |
| research_report_confirmations | project_id、report_version_id、plan_confirmation_id、run_id、evidence_analysis_id、action_id、confirmed_at；只追加 | 无actor/hash/策略列；UNIQUE(project_id,report_version_id)使同一版本不能插入第二次确认 |
| research_model_diagnostics | provider/validation/persistence阶段、固定错误、脱敏样本≤16384字节 | 必须关联真实模型attempt；不能为人工保存错误伪造费用尝试或塞原始输出 |

结构共23表、20个显式索引、19个触发器，user_version=6。正式库SHA-256：`877a0c8ab26808a12f5dd284a06fe9811205549ec66215a59b7728fe7c7db4e4`；结构SHA-256：`fb0206a7f7d62b4b220dd69dddd6dddabf266c840dc4d8cd04900830e98e5cb3`；integrity_check=ok，foreign_key_check=0。与B阶段记录相同。

### 2.3 已有测试的覆盖与设计影响

已静态检查研究生成/编辑/确认/阶段门禁、报告再生成/恢复、新旧报告兼容、历史/预测时间保护、版本只追加及费用回归的相关测试。它们保护现有行为，但不能替代本设计的22项U/I/P测试。

例如 `test_old_report_and_evidence_survive_new_report_and_snapshot` 当前还允许从旧v1证据生成新报告。实施v3时应拆成“旧内容可读且原样保留”与“旧证据不得进入新v3报告”两个明确预期，不保留不安全的新生成兼容路径，也不删除历史保护断言。本阶段不改这些测试。

## 3. 报告v3数据契约与技术选择

### 3.1 技术选择及关键取舍

推荐沿用Python、现有jsonschema、SQLite v6、VersionService和execute_attempts；不引入MySQL、Redis、向量库、新模型或额外校验API。报告服务独立于Streamlit，纯校验/渲染器不访问配置、数据库或网络。

**不能把“有evidence_id + 文本数字相同”当成语义支持证明。** 相同数字可属于不同指标/主体/期间；自由文本还可添加没有数字的因果结论。也不能把证据summary直接当作已经完全核实的事实原子，B的有限规则没有证明其全部自然语言含义。

为使“模型不得创造数值/期间/重要事实”成为可执行规则，首版选择**受约束的表达树**：模型组织问题顺序、证据/缺口顺序、选择允许的陈述或结论模板及其证据槽位；程序从已验证证据填充主体、指标、数值、单位、期间、等级和引用，确定性渲染正文。所有标题、概述、结论、风险区也受相同约束，不能留下自由文本事实旁路。

替代方案“自由正文+事后关键词/数字检查”成本低、表达丰富，但无法可靠满足本次强约束，故不选。未来若需要自由推理文字，应另审支持关系与人工审稿契约；不能在本实施中悄悄开放一个不受检验的text字段。该取舍限制写作自由，属于本设计需审核的主要产品决定。

### 3.2 服务器输入：ReportEvidenceBundleV3

以下是字段契约说明，非已实现代码或执行样本：

```text
bundle_version: research-report-input-v3
basis:
  project_id == production_project_id
  plan_version_id, plan_confirmation_id
  research_run_id                 # 明确映射research_search_runs.id
  evidence_analysis_id           # 当前成功证据批次，不是模型attempt ID
  evidence_contract_version: research-evidence-v3
  evidence_policy_version: quality-v3
  input_manifest_hash, evidence_set_hash
  research_as_of, target_window
expected_previous_report_version_id: id | null
evidence_catalog: [
  evidence_id, question_id, evidence_position, candidate_id
  evidence_item_hash, assessment_hash
  quality:{final_category,independence_status,unmet_conditions,policy_version}
  temporal:{event_kind,speaker_kind,temporal_type,label_raw,fiscal_year,
            fiscal_quarter,coverage_start,coverage_end,research_as_of,...}
  claim:{entity,metric,value,unit,basis,speaker}
  source_bindings:[source_id,snapshot_hash,body_hash,region,field,
                   segment_id,window_id,start,end,quote_hash,role]
  statement_refs:[程序生成的、绑定该evidence_id的陈述原子/模板输入引用]
]
mandatory_gaps:[gap_id,question_id,source/evidence关联,code,detail,provenance]
model_materials:{固定问题、可用证据卡片、允许模板、statement_refs、gap_ids}
model_materials_hash, canonical_hash_version
```

模型只见组织表达所需的卡片，不把来源全文再次交给它提取，不允许重新创造证据。source_id、URL、原文引用等由服务器保管/渲染；模型无需返回它们。卡片只使用本次明确发送的证据原子，实际输入与后续允许引用集合逐值一致。

claim字段缺主体/指标/数值/单位等必要信息时，不创建确定数值事实模板输入；可创建“该来源的含义仍未核实”的线索卡片和必要缺口。原始summary/inference只是候选表达，不自动升级为受信事实原子。支持引文来自B已验证且持久化的具体引用范围，不能向未发送的原文全文补找证据来追认报告。

### 3.3 模型输出：ReportCandidateSchemaV3

```text
{
  question_sections:[{
    question_id: 本次题集合之一,
    evidence_order:[本题允许的evidence_id],
    gap_order:[本题mandatory_gaps中的gap_id],
    blocks:[{
      block_id: 本文内唯一短ID，不作为事实显示,
      template_id: 服务器允许的固定模板编号,
      bindings:[{slot:固定槽位名,evidence_id:允许ID或null,
                 statement_ref:该证据允许引用或null,gap_id:本题缺口ID或null}]
    }]
  }],
  conclusion_blocks:[同一blocks结构]
}
```

每层additionalProperties=false；ID类型严格区分bool/int，字符串长度/数组规模/嵌套/文档总字节数有限。每题恰好一次，evidence_order须为本题可用证据集合的一个完整排列，gap_order须为本题必需缺口的完整排列；各block槽位、引用对、重复规则按模板独立校验。问题顺序可变，题集合不能增删。

每个binding固定包含上述四个键；本地检查互斥：要么evidence_id/statement_ref均非null且gap_id=null，要么gap_id非null且前两者均null。避免依赖尚未核对的服务商复杂条件Schema能力。事实/观点/推断前提槽只能绑定证据；缺口模板可只绑定gap，不能把gap当事实前提。这样零证据报告也能组织缺口结论，但不能生成无证据事实。

建议初始上限：每题blocks≤8，conclusion_blocks≤10，总blocks≤40，每block引用1–10条且不重复、每block绑定槽位≤10，block_id≤60字符，candidate整体≤262144字节。现有研究问题≤10、证据≤10的约束不扩大。缺口不能为满足上限而裁剪；最小合法输入/输出预算放不下时本地拒绝，提示缩小研究范围。

服务商strict Schema可对当次evidence_id/statement_ref/gap_id生成枚举，实际支持范围沿用现有provider_schema转换；本地完整Schema和关联校验始终保留，不能仅依赖服务商。模型只能**选择已经提供的ID**，不允许创造或重绑定ID；一个真实ID配另一个证据的statement_ref也拒绝。

没有text、value、period、quote、source_id、URL、final_category、verified、independence_verified、validation_status、confirmed、actor等输出字段；未知/越权字段整份拒绝，不删字段后继续用。不能把用户在模型输出中写的“已核实/已确认”作为授权。

### 3.4 已保存报告：ReportEnvelopeV3

```text
contract_version: research-report-v3
basis: 冻结的完整v3依据
evidence_snapshot: 完整允许集合的ID、各项hash、source_bindings和原子引用版本
candidate_document: 严格通过的表达树
document:
  程序渲染的概述、目标、结论、分题内容
  分类区:{verified,single_source,opinion,inference,disputed,unverified,gaps}
  每个事实/数字/结论行的evidence_ids、原子引用、继承等级及时间语义
  完整必需缺口、争议提示、服务器生成的出处与原文引用
validation:
  policy_version: report-validation-v3
  renderer_version: report-render-v3
  canonical_hash_version, report_core_hash, evidence_set_hash, model_materials_hash
  checked_at, warnings                       # 服务器结果，模型不可提供
```

operation的schema_version固定research-report-v3、prompt_version固定research-report-prompt-v3；不是由模型自报版本。报告版本的实际SQL ID和version_number由VersionService分配，在同事务审计校验回执中绑定该ID。report_core_hash计算排除自身hash、checked_at、尚未分配的SQL ID，包含契约、依据、证据快照、表达树、确定性正文、缺口及策略/渲染版本；避免自引用hash循环。

该JSON为服务器构造的规范结果，不能让普通调用者传一个自称validation.passed的完整Envelope就落库。人工编辑也只提交表达树，通过相同校验和渲染后追加；旧自由正文编辑不能获得绕过权限。

## 4. 证据绑定机制与职责边界

### 4.1 严格读取与冻结步骤

1. 在单一SQLite读事务/连接中读取项目、当前确认计划、最新搜索运行；搜索须success/partial且绑定当前计划和确认。读取内核负责关系与完整性，是否允许生成/保存/确认由入口依既有暂停/归档规则判断；历史只读不因项目不可写而受阻。
2. 选择**该搜索最新成功证据分析**，同时要求purpose=research_evidence、production_project_id正确、status=success、schema_version及JSON契约均为research-evidence-v3。不能跳过最新成功的legacy批次，偷偷挑更早的v3批次；若最新成功批次不合格，要求按当前流程重新整理证据。
3. 联合检查每条evidence的project_id/run_id/analysis_id/question_id/position，analysis的input run_id、manifest project/run/questions、SQL来源关联、source snapshot/body hash、引用区域/偏移及其B阶段可见窗口。project_id和production_project_id是同一制作项目的不同层命名，必须相等，不能当两套独立可选值。
4. 经共用严格v3读取内核核对SQL/JSON；必要的质量一致性复核只调用公开assess_batch/assess_document，绑定版本必须匹配，原结果与重算规范结果不等则拒绝，不能悄悄回写旧证据。当前公开策略不授verified，因此当前正常v3池的verified区应为空。
5. 对完整允许集合按稳定顺序计算evidence_set_hash，包含各证据ID/批次/position/程序claim、quality、temporal、缺口及引用绑定；对实际发送的卡片另算model_materials_hash。没有“只hash ID”的替代。
6. 按原reservation_units检查完整请求；模型调用期间释放数据库读/写锁。最小卡片与必需缺口不能全部容纳时，调用前停止；不静默省略争议或缺口、不扩大预算、不追加请求。
7. 保存事务重新读当前依据、预期前一报告版本和完整绑定，hash或ID任一变化均拒绝本次发布；原模型费用照常保留。

同一不可变来源快照可被不同搜索复用，但报告引用的是本次证据批次的evidence_id；共享source_id不意味着可以跨run借用另一批evidence。重新生成的两个报告可合法引用同一个未变的证据快照，各自仍绑定独立报告版本与确认；“不得跨版本”指不能混用不属于该版本冻结集合的证据/确认，不是禁止复用同一不可变证据。

### 4.2 服务职责

| 层 | 职责 | 不允许 |
| --- | --- | --- |
| ResearchService | 计划/搜索/证据；保留报告方法作为委托兼容入口 | 与ReportService各维护一套报告验证器 |
| ReportService（拟新增） | 冻结输入、组织模型调用、人工保存/恢复、事务发布、确认和状态投影 | 创建证据、升级quality、在Provider回调中自动确认 |
| 共用v3证据读取器 | 接受connection和项目/批次上下文，返回核验快照 | 页面或报告重新拼宽松SQL替代它 |
| 报告纯校验/渲染器 | Schema、模板与引用约束、等级/时间/缺口继承、规范结果/hash | 联网、读.env、授予身份或审核权限 |
| VersionService/Store | 在调用方事务里分配版本、保存JSON、记录审计 | 通用create/restore接受自带授权字段绕过报告门禁 |
| production.guards / ProjectService | 在任何后续写操作的同事务内执行报告准入 | 仅看页面按钮或project.status是否已为scripting |
| Streamlit适配层 | 显示程序结果、组织用户修改、提交明确版本的人工确认意图 | 计算证据真伪、签发最终证据等级、从checkbox布尔值直接认定确认 |

校验器不能反向导入VersionService或页面，避免现有version_guard导入链形成循环。连接级读取和纯报告规则位于底层，ReportService编排它们；守卫调用底层准入函数而非启动ReportService/Provider。

## 5. 报告程序校验规则

### 5.1 允许的表达模板

首版模板由程序注册并版本化，不能由模型添加模板正文：

- evidence_statement：呈现同一证据中已核对的原子陈述，填入该证据主体/指标/值/单位/基准/期间；等级和警示由程序带出。
- attributed_opinion：明确“某来源的观点”，不能将它渲染为已发生事实。
- limited_inference：至少一个可追溯前提，明确标AI推断及其边界；只允许注册的有限关系，例如“材料仅支持提出该研究问题，尚不能确认因果/未来结果”，不能填自由因果结论或新数字。
- compare_like_for_like：仅比较已证明相同主体/指标/单位/基准/覆盖期间/事件性质的两个原子，逐项列举，不计算新数值、不合并成更强事实；条件不足则改用单独陈列模板或拒绝。
- preserve_dispute：展示所有已保存的冲突侧、原等级和未解决项，禁止择一消除争议。
- unresolved_lead / gap_reference：呈现待验证线索、明确问题与缺口，不承诺其事实为真。

模型选择了不满足前提的模板时整份拒绝，不由程序在失败后默默换模板。合法的“推断/待验证表达”须在候选契约中明确选择，且仍不能包含捏造的前提；不支持的自由结论不因贴inference标签而被放行。

### 5.2 必经校验顺序

1. 版本、大小、完整本地Schema；未知/越权字段、隐藏文本通道、额外source/quote/URL/状态字段均拒绝。
2. 完整问题集合、唯一block_id、规模限制；每题证据/缺口排列精确覆盖允许集合，无重复、无跨题拼借。
3. evidence_id在冻结允许集合中；每个statement_ref属于该ID，槽位个数/角色符合模板；ID即使真实存在但不在当次集合内也拒绝。
4. 证据项目、run、analysis、快照、body_hash、原子hash、引用与程序审定结果一致；全套校验不能仅凭调用者传入的hash字符串。
5. 数值、单位、币种、比较基准、主体/指标、FY/季度/覆盖时间从原子填充；不执行模型建议的计算，不从另一个引用里借数字填到当前指标。
6. 依第6节继承等级/时间，拒绝升级、把争议删除、把观点或预测当实绩，以及unknown强作current。
7. 依第7节核对全部必需缺口与争议保留；只要一个问题不满足，不能保存其他问题的“部分成功报告”。
8. 确定性渲染后重新核对正文/结构化条目/出处与表达树、快照的等值映射，计算规范hash；正文概述和结论同样不能绕过这些步骤。
9. 保存、人工确认、后续准入分别在自己的事务内重读绑定并重算必要结果，不能只信analysis_json或validation对象上的passed字样。

数字错误既包括模型非法输出value/text字段，也包括内部/人工提交的规范正文值与证据不符，测试必须覆盖两种入口；不能因为候选Schema没有数值字段就只测一次additionalProperties错误。

建议固定错误码：report_schema、report_evidence_not_allowed、report_scope_mismatch、report_binding_mismatch、report_statement_ref_mismatch、report_value_mismatch、report_period_mismatch、report_grade_escalation、report_temporal_escalation、report_dispute_omitted、report_gap_omitted、report_unsupported_conclusion、report_basis_changed、report_version_conflict、report_validation_internal、report_confirmation_required、report_confirmation_binding、report_confirmation_intent、report_legacy_unreviewed。每条含结构path及必要的evidence/question标识，至多20项，超出明确truncated。

程序校验不是通用自然语言证明器。本方案通过限制可表达内容来获得可执行保证，不用第二个模型的“我认为有依据”替代证明。

## 6. 时间和证据等级继承规则

### 6.1 内容分类

报告必须有七类展示和可机器读取的分类；无条目时可以明确为空，不能为了凑齐分类伪造证据。

| 已保存证据final_category | 报告允许表达 | 禁止 |
| --- | --- | --- |
| verified | 在同一原子范围内继承已验证事实，且其证据策略/认证来源本身合法 | 报告自授verified；借旧v1/v2 verified；合并多个低等级升为verified |
| single_source | 单一来源事实，明确单源及未满足条件 | 在标题、概述、结论中称“已证实/独立核实” |
| opinion | 归属明确的来源观点 | 改成事实或把报道媒体当实际发言者 |
| inference | AI推断及其证据前提/限制 | 将推断结论用作实际数字或后续事实原子 |
| disputed | 存在争议，保留冲突各侧和未解决状态 | 删除一侧、按多数来源裁决、降成无争议事实 |
| unverified | 待验证线索 | 因多次引用或人工确认就升级 |
| 结构化gaps及程序派生限制 | 研究缺口，按问题明确列出 | 以一句“已补齐”关闭缺口 |

当前公开quality策略没有可信审核供给，正常生产v3集合不会包含verified。本设计支持该分类名称，但不新建可信审核入口、不生产伪造审核记录。测试中的报告分类纯fixture也不能冒充生产已经能授verified。

多证据结论不能简单取“最高等级”，也不能把质量类别当一个可任意排序的数值：观点、推断、争议是性质差异。混合类别默认分别呈现；注册推断模板可产生标明前提的推断，任何disputed相关结论必须保留争议标志。不能以一句低等级脚注掩盖正文的高等级断言。

### 6.2 时间分类

| v3 temporal_type | 报告继承 | 附加约束 |
| --- | --- | --- |
| current_actual | 当前目标窗内实际数据 | 仍绑定原research_as_of/target_window，不声称全球最新一期 |
| historical_actual | 历史实际数据 | 原覆盖期间/FY标签保留，不写当前/目前事实 |
| company_guidance | 公司指引 | 保留公司/管理层归属及预测性质 |
| analyst_forecast | 分析师预测 | 不换成公司承诺或实际结果 |
| market_expectation | 市场预期 | 不换成公司业绩或分析师独家结论 |
| unknown | 时间性质未知 | event_kind、speaker_kind、FY标签等已知独立字段仍保留，未知不补 |

来源发布日期和数据覆盖期间分开。报告不调用旧source_time_context.historical或forecast_text关键词结果重新分类v3证据，不把“低于预期”误作未来预测。重生成日不是新的数据截至日；要更换research_as_of或目标时间窗，应产生新研究依据，而非报告自行重算当前性。

FY2027 Q1于2026年发布、无覆盖起止的已保存证据，应继续actual_result + label_only + temporal_type=unknown，保留2027财年/第1季度和null覆盖日期；不得因发布日期2026改写为历史数据，也不得自行补一个季度日期区间。

## 7. 研究缺口处理规则

1. 完整继承证据批次的structured_gaps；不以兼容旧页面的字符串gaps代替完整结构，也不从模型重新生成一个更“完整”的缺口集合。
2. 程序可派生限制性缺口：无证据问题、缺数值、期间unknown、只有单源/独立性unknown、提取失败/摘录、上下文不足、争议、事件性质无法确定。派生限制只说明不足，不补造事实。
3. gap_id由程序对版本化provenance、question_id、关联证据/来源、原gap位置与code/detail生成稳定标识；同文不同归属不能错误合并。gap集合和次序身份进入快照hash。
4. 每个无证据问题必须有自己的gap，不能拿一个“全局风险”顶替；有证据但指标/期间不足也保留对应限制。
5. 模型仅可排列gap_id，不可提供resolved、替换detail、删除项或新增“已找到可靠来源”；人工报告编辑也不能关闭研究缺口。补齐须回到研究流程产生新证据/依据。
6. 争议证据全部进入本题强制证据列表和显著的争议区；正文模板、概述/结论中的相关陈述带争议标识。报告不承担裁决冲突来源的权限。
7. 允许零证据、全缺口的诚实报告通过结构与引用校验；必须明确“没有可用事实证据”，已验证/单源事实区为空。它不会被渲染成事实充分的报告，人工确认也不补出事实。是否继续制作仍由用户显式确认；未来脚本只能消费实际存在的报告内容，本阶段不额外发明制作状态阈值。

为了模板完整而缺失的字段不能由常识、其他项目数据、问题中的数字或模型记忆填补；预算不足也不能成为省略缺口/争议的理由。

## 8. 版本管理与原子发布方案

### 8.1 三个版本轴

- 报告SQL版本：production_versions.id / object_id / version_number，只追加。
- 证据版本：evidence_analysis_id + evidence_id集合 + input_manifest_hash + evidence_set_hash，冻结不可混用。
- 规则版本：报告契约/校验器/渲染器/规范hash版本，以及证据quality policy，明确注册支持集合，不按字段存在猜测。

新生成或人工保存/恢复都产生新的报告版本；只有通过程序校验的规范内容才发布到report对象。失败候选保留在失败分析状态及脱敏诊断，不创建半份正式报告，不把未经验证正文当历史正式版本。

### 8.2 发布事务

```text
模型调用之前：冻结v3 bundle + expected_previous_report_version_id，登记原模型操作
模型之后：严格校验候选 → 原执行器结算费用
BEGIN IMMEDIATE
  重读writable项目、计划确认、最新搜索/证据批次
  重读预期最新report版本，比较CAS预期
  通过严格v3读取器重算证据集合与模型允许集合的绑定
  再次纯校验、渲染并与预规范结果/hash逐值比较
  分配新report版本并保存Envelope
  追加report_validated_v3审计，绑定实际report_version_id与core/pool/policy hash
  完成topic_analyses.analysis_json/result_version_id/status
COMMIT；任一步异常全部ROLLBACK
```

不在网络调用期间持有写锁。并发人工新版本、计划变化、哪怕正文相同的新证据批次、新搜索运行、策略版本变化均可导致本次发布失败；费用保留、旧报告不删。两个独立新动作同时生成，先发布者成功，后者按expected_previous_report_version_id冲突拒绝，不无意置后人工版本；同一action沿用既有幂等规则，不重复付费或版本写入。

人工save/restore没有模型费用：同样检查预期前版本、完整bundle和表达树，追加规范版本及审计；不伪造AI analysis/attempt。通用VersionService.create/restore的research/report入口必须重新验证服务器规范结果，拒绝携带伪validation字段的字典。底层不受信输入不能通过source='manual'或'restore'逃逸。

旧报告details/history始终可读取，显示legacy_unreviewed；不回写其JSON/确认记录，不把它升级v3。不允许从legacy证据生成新v3报告，也不把历史报告复制到新版本就自动认证。恢复旧内容需使用当前v3允许集合重新构造并校验表达树，旧evidence_id不允许静默替换成新ID。

证据更新后：旧版本及其确认仍是历史记录，状态投影为stale；不能回退挑旧依据继续进入后续阶段。新报告必须绑定新的集合，并由用户确认新报告版本。生成新报告失败但旧依据未变时，旧有效报告可继续保持其自身确认状态，同时明确展示最新尝试失败；不能把“最新尝试失败”和“旧报告无效”混成一个字段。

## 9. 人工确认门禁及状态方案

### 9.1 六类业务状态与两条状态轴

不修改topic_analyses.status的CHECK。ReportState是从版本、最新模型尝试、校验审计、确认记录和当前依据计算的结果，同时返回current_report_state和latest_attempt_state。

| 状态 | 证据/实现来源 | 准入 |
| --- | --- | --- |
| not_generated 尚未生成 | 没有可发布报告；没有成功版本 | 禁止 |
| generated_pending_validation 已生成待校验 | Provider返回后、校验器处理中的候选；不是正式报告 | 禁止 |
| validation_failed 校验失败 | 最新尝试的validation诊断或人工保存安全失败事件 | 禁止该候选；旧有效版本单独判断 |
| validated_pending_confirmation 校验通过待人工确认 | 正式v3版本及事务校验回执存在，当前依据相符，无有效人工确认 | 禁止 |
| confirmed 已确认 | 下面全部确认与准入校验成立 | 允许用户进一步操作，不自动生成脚本 |
| stale 已失效 | 依据/最新报告/策略改变、确认绑定不符、撤回事件或规则不受支持 | 禁止；新版本重新校验并确认 |

生成中、provider_failed、persistence_failed、interrupted/uncertain是latest_attempt_state补充项，不能把它们伪装成validation_failed或not_generated。generated_pending_validation至少是运行时明确阶段；可在原validator入口以固定安全元数据追加candidate_received/validation_started事件，不保存原始候选。若阶段事件保存失败，仍执行严格验证和原费用结算；状态回退为已知的running/uncertain，不虚构已通过。

进程中断且没有保存原始候选时不能声称可以重放脱敏诊断完成校验；保留未知费用/预占和中断状态，后续按既有人工恢复规则处理。本方案不新增自动重发/重试规则。

### 9.2 人工确认的信任边界

当前应用为本地单用户，没有认证用户、角色表或受认证审核主体。**不能声称当前确认表能证明真实用户身份；hash也不是身份签名。** 本设计分清两种威胁：

1. 模型、普通请求/JSON、自由文本以及普通业务状态字段均不可信，不能授予确认权限。
2. 当前本地服务进程、持有数据库写权限的代码和本机操作者是信任边界；任意SQL管理员能伪造确认行与JSON甚至删除触发器，仅靠v6或新增普通列都无法防御。若需求包含这种攻击者，须另审独立密钥签名/受认证身份/受控写入与审计，不能假装加一个actor_id就已解决。

拟新增 `HumanConfirmationIntent` 概念：由可信交互适配器在用户明确查看并确认该版本后签发的服务端对象，绑定purpose、project_id、report_version_id、report_core_hash、evidence_set_hash、policy_version、交互session/一次性action_id及有效期。**不是**可由模型JSON或请求字段构造的trusted=True字典；公开序列化接口不能接受actor/confirmed等自报授权。

本地模式的origin应诚实记录为local_interactive_operator，不伪造登录用户或实名身份；服务端对象/能力分离只隔离模型和普通内容权限，不是完整本机防攻击认证系统。未来多用户适配器必须从认证会话取得actor和项目确认权限，不能接受客户端自报actor_id；本次不实现用户系统、密钥配置或可信证据审核入口。

### 9.3 确认事务与防伪造字段

confirm必须显式传预期版本/hash及可信HumanConfirmationIntent，模型调用链没有这条能力。事务内：

1. 校验意图的签发通道、purpose、session/有效期/一次性action_id和项目授权边界；确认按钮的布尔值本身不够。
2. 重读最新report对象；项目未暂停/归档，ID及内容hash等于用户实际审核版本。
3. 严格读取当前v3依据，重算报告规范内容及hash，确认report_validated_v3回执的version/policy/pool绑定。
4. 比较确认表全部列：project/report_version/plan_confirmation/run/evidence_analysis；不能只查该版本有没有一行。
5. 原子插入research_report_confirmations及production_actions中report_confirmed_v3回执；回执绑定实际confirmation_id、action_id、version/core/pool/policy、受信意图摘要、origin和时间。
6. 重复同一意图仅在全部绑定相同且确认已成功时幂等返回；action_id用于别的项目/用途或失败重放则拒绝。确认或审计任一步失败全部回滚，不改变项目制作状态。

准入不接受report.confirmed=true、project.status=scripting、source=manual、analysis.status=success或一条孤立确认行。即使有人通过普通业务字段/测试SQL插入单独confirmation记录，没有匹配的v3验证与受控确认回执也必须拒绝。

这不能承诺阻止拥有任意SQL权限者同时伪造整套可信记录；该限制必须在交付和未来平台设计中保留，不把多表交叉检查宣传为认证。

### 9.4 脚本阶段统一准入

拟 `require_confirmed_report_v3(con, project_id, purpose)` 同时检查：最新报告契约、有效v3严格证据池、当前basis和hash、重新核对的报告规范内容、校验回执、人工确认全部绑定及撤回/失效状态。返回绑定实际report_version_id/core_hash/evidence_set_hash的准入结果，不修改研究数据。

已有ProjectService进入FORWARD_STATES、暂停恢复到后续状态、VersionService创建/恢复FORWARD_TYPES全部使用该函数，并与业务写入同事务。普通暂停/归档写入拒绝；明确的resume操作先由ProjectService验证恢复权限和目标状态，再校验报告，不被底层“暂停即不可读”的判断误伤。未来脚本模型调用入口必须在预算预占/调用前以及结果保存事务内各核对一次；不能仅凭状态已经是scripting省略校验。

已有旧状态和旧脚本不批量回退/删除，仍可读；新后续写入/生成要求新门禁。历史报告确认不能自动成为新门禁凭据。人工确认是编辑发布意愿，不能改变证据quality或独立性结论。

v6同版本唯一确认：失效后再确认采用“校验相同内容并追加一个新报告版本，再确认新版本”，不重写/删除旧确认，避免假装能够在同一版本追加第二次确认。用户可选择重新生成新版本，或对当前允许集合完全未变的表达树重新校验为新版本再确认。

确认意图的有效期只约束确认操作执行时刻；成功提交的确认不会因为临时交互意图过期或进程重启而自行消失。后续准入验证持久回执与当前版本/依据/规则的一致性，不要求长期保留内存能力对象。反之，进程重启丢失且未提交的意图不得补签成已确认。

## 10. 数据库兼容性、迁移评估与失败/费用

### 10.1 推荐方案：本地信任边界下保持v6

| 新契约内容 | v6复用位置 | 安全条件 |
| --- | --- | --- |
| 模型请求版本、冻结bundle | topic_analyses各版本字段、input_json | 只允许报告服务构造，绑定purpose/project |
| 规范结果与失败状态 | analysis_json/status/error_type/result_version_id | 只有校验并提交完成才success；失败不覆盖旧版本 |
| 报告快照/验证策略/内容hash | production_versions.content_json | 所有入口重算，不信任passed字段 |
| SQL版本ID对应的校验回执 | production_actions.details_json | 与版本保存同事务，固定event/purpose/hash/version |
| 六类业务状态/失效 | 读取投影及安全阶段事件 | 不改通用status CHECK，不把UI临时状态作为授权 |
| 人工确认 | 现有confirmations + 同事务确认回执 | 全列联合验证、受控交互意图；只适用于已说明的本地信任模型 |
| 失败诊断 | research_model_diagnostics | 真实模型attempt关联、固定白名单、字符串脱敏、≤16KiB |
| 人工保存失败 | 安全错误返回及必要production_actions事件 | 无模型调用则不伪造attempt/费用；不得写未清理正文 |

当前没有必须执行Schema迁移的结构缺口。v6能存储本地报告版本绑定和状态所需信息，但安全性依赖上述程序校验与服务边界，不是数据库外键自动证明。所有JSON字段缺失/版本不受支持都失败关闭，不回退旧宽松逻辑。

### 10.2 条件性最小迁移议题（不执行、不先预建）

若后续明确要求同一不可变版本多次确认/撤回/重签，现有UNIQUE(project_id,report_version_id)确有限制。最小追加方案是新建append-only的report_confirmation_events表，以(project_id,report_version_id,action_id唯一、actor引用、event_type、core/pool/policy hash、时间、supersedes_event_id)承载多次事件，保留原表只读；按同项目/同版本复合外键约束，避免重建/回写旧确认表。

若要求认证多用户，则actor引用必须来自另审的认证主体/授权存储；当前没有可信actor表，不能新增一个自填actor_id假装认证已完成。只有有认证方案后才能确定是否需要最小principal表或外部subject映射。

若要求防任意SQL伪造，需受控写入/独立密钥签名和受保护审计，签名payload必须绑定版本、hash、actor、用途与撤回关系；单纯Schema变更不能满足。不在本次引入密钥、外部基础设施或声称v6具备该能力。

迁移风险：原追加触发器、旧确认语义、外键兼容、旧应用误读新事件、账号映射及签名密钥生命周期；未来必须备份、临时库演练、完整旧行/结构快照及回滚/前滚方案。旧确认不能自动转换成新认证确认。本轮不生成DDL、不改user_version。

### 10.3 失败与费用分阶段处理

| 阶段 | 持久化/状态 | 费用与恢复 |
| --- | --- | --- |
| 调用前：无v3池、预算/请求超限、授权不成立 | 不建成功报告；没有已发送attempt时不能虚构调用 | 无新调用费用；保留旧报告，不扩大上限 |
| Provider/解析失败 | 既有attempt失败；provider诊断；analysis失败或按既有规则uncertain | 已知usage照价结算，未知费用/预占保持未知；仅原执行器允许的有限重试 |
| 报告校验失败 | ValueError/ResearchValidationError及validation诊断；无新正式版本 | 原执行器结算已发生Token，不记0，不额外自动调用模型“修复” |
| 版本/审计/analysis保存失败 | 已发生费用先保留；业务事务整体回滚；persistence诊断 | 旧版本/确认不变，新analysis失败；attempt可能仍success，不能删费用 |
| 人工保存/恢复校验失败 | 不追加有效版本；可单独记录固定安全失败事件 | 没有模型调用则没有AI费用或假attempt |
| 人工确认保存失败 | 确认及确认回执同事务回滚；报告仍待确认 | 不涉及模型费用，不自动重生成 |

继续使用execute_attempts、reservation_units、estimate_units、price_snapshot和现有账本，100元月预算及收费/汇率/重试规则不变。报告validator适配器必须把可预期的输入错误转换为ValueError体系；对验证器内部普通异常也做固定安全错误转换后交回原执行器，使已知reply.usage能正常结算，不把诊断保存成功当成前提。中断/进程崩溃等走原未知费用保留规则，不能臆测为0。

诊断至少保留stage、固定code、结构path、必要脱敏样本；多项错误至多20条；自由文本、Authorization、密钥及未知键名不入表。诊断失败不能使候选通过。没有真实attempt的人工保存失败不能滥用模型诊断表的外键。

## 11. 22个场景测试矩阵

以下全部为**待实施测试设计，未创建测试文件、未运行、未声称通过**。U=纯Schema/表达树校验/状态策略；I=真实ReportService、真实严格v3读取与Store，仅Provider/HTTP替换Mock；P=独立临时SQLite真实事务、实际SQL查询及旧行快照。U的错误状态映射不能代替I/P故障测试。

建议稳定NodeID：

- U：tests/test_research_report_contract.py::test_case[R01] … [R22]，必要故障分派用独立函数/参数变体。
- I：tests/test_research_report_integration.py::test_case[R01] … [R22]。
- P：tests/test_research_report_persistence.py::test_case[R01] … [R22]。

每项须有固定输入/候选/程序预期；不能从实现返回值推导expected。真实v3前置证据由当前研究服务+Mock Provider写入；legacy样本只在临时库明确建历史夹具，不向生产灌可信审核记录。正常报告使用single_source/opinion/inference/disputed/unverified等真实可产生的v3证据，verified区为空；不为正例伪造生产可信审核能力。

| ID / 场景 | U：明确断言 | I：真实服务+Mock | P：真实SQLite断言 |
| --- | --- | --- | --- |
| R01 正常生成 | 合法表达树，七分类及六时间类型按各固定fixture继承；未知不补 | 捕获实发Prompt/Schema/cards，规范正文完全由允许原子渲染，待人工确认 | 新版本/校验回执/成功analysis一起提交；evidence/links/旧报告原值不变，确认0新增 |
| R02 模型伪造evidence_id | 当前集合外ID拒绝；真ID配错误statement_ref也拒绝 | Provider返回未知/偷换ID，真实validator整份失败 | 新report版本/校验成功回执0；失败费用保留；旧行全值相等 |
| R03 跨项目 | project_id与production_project_id/引用作用域不符拒绝 | 项目B真实证据ID放入项目A候选或伪bundle | 联合查询不能写入跨项目报告/确认；普通单列FK不当成功依据 |
| R04 跨研究任务 | 同项目另一run/analysis的真实ID拒绝 | 创建旧/新两个真实搜索证据批次，旧ID放进新调用 | 新批报告0新增；旧证据及确认原样；共享source_id不造成越权 |
| R05 不存在证据 | 不存在ID、重复ID、bool冒充int分别拒绝 | 真实服务输出伪ID；读取池损坏/缺SQL行时调用前拒绝 | 无有效版本；调用前失败无attempt，已调用失败保留实际费用，两者区分 |
| R06 数值不一致 | 非法value/text字段拒绝；规范结果数字/单位/基准篡改拒绝；换atom绑定拒绝 | 同ID不同指标/数字的错误表达不能靠引用通过，人工提交同样拦截 | 保存前篡改规范结果或池值，事务拒绝；旧报告/费用不变 |
| R07 期间不一致 | 错FY/季度/覆盖日期拒绝，发布日不能作覆盖期 | FY2027 Q1/2026发布及仅标签场景不补日期；错期间/人工编辑拒绝 | JSON保留null和原标签，错误输出零版本；来源/旧证据不回填 |
| R08 单源升已验证 | 单源选择verified表达/规范grade字段篡改拒绝 | 正常single_source不能被标题/概述/结论称已核实；模型权限字段拒绝 | 无升级后的报告版本；原evidence.category不变 |
| R09 历史升当前 | historical_actual的当前模板拒绝；research_as_of不可由报告改 | 旧实绩明确截至日；即使文章新发布也不能改当前 | 失败无新版本/确认；合法历史版本原期间保持 |
| R10 预测升实绩 | guidance/analyst/market三类分别拒绝actual模板；expected比较不误判 | 六时间类型及unknown成对正反例；原事件/发言者保留 | 失败零版本；合法预测按原类型保存，不改证据时间 |
| R11 删除争议 | evidence_order漏争议、漏冲突侧或选无争议模板拒绝 | 多条含争议证据的真实池，不准挑一侧裁决 | 失败0版本；合法报告显著争议区及全部关联保留 |
| R12 自填缺口 | gap_order缺项、跨题、resolved/伪“已补齐”字段拒绝 | 0证据/缺数值/期间未知/单源/上下文/混合性质逐项 | 合法全缺口报告可保存；错误不产生假事实，原structured_gaps不改 |
| R13 结论无证据 | 空bindings、未注册自由结论、用inference掩盖无前提分别拒绝 | 真实报告validator拦概述/结论等任何文本旁路 | 0成功版本；其他合法题也不部分保存；费用照常 |
| R14 生成失败 | provider/parse/unknown费用的状态分派 | Mock Provider抛既有AIError、超时/解析错，验证原重试规则及无自动修复请求 | 旧报告/确认原样，attempt已知费用或unknown预占正确，无新成功版本 |
| R15 校验失败 | 稳定code/path及整份拒绝；内部RuntimeError适配安全失败 | Schema/语义及诊断保存失败三类；不因诊断故障绕门禁 | 无半份analysis_json/版本/成功回执；已知usage不记0，样本脱敏限长 |
| R16 保存中途异常 | 规范结果/回执不一致拒绝策略；U不冒称测试回滚 | 真实服务持久化阶段故障，无第二次模型调用 | 用SQLite触发器在版本插入后、审计/analysis更新时RAISE；版本/对象/审计/成功JSON全回滚；费用已结算 |
| R17 新报告不覆盖旧报告 | expected_previous_report_version_id冲突拒绝 | 顺序再生成功；并发AI/人工保存CAS阻止后完成版本覆盖当前人工版本 | 两动作成功时版本递增且旧JSON/hash不变；并发冲突0新增，action幂等不重复付费 |
| R18 证据更新失效 | ID/hash/policy/目标窗任一变化判stale；不降到旧池 | 新run、同run新证据批次、同正文新快照/策略变化变体 | 旧报告/确认不改但准入拒绝；新版本确认前不能继续；事务中依据变化发布回滚 |
| R19 伪造人工确认 | confirmed/actor/trusted字段、错误意图/用途/hash/重放拒绝 | 模型不能持确认能力；普通请求字典/未勾选受控意图不生确认 | 单插confirmation行、错误项目/分析绑定或缺校验/确认回执均准入拒绝；确认审计中途异常全回滚 |
| R20 未确认进脚本 | pending/failed/stale/legacy均不准入，status字段不作证据 | 真实ProjectService、VersionService create/restore、暂停恢复三个入口均拦 | 项目状态/后续版本/动作0变化；原研究数据保留；将project.status改scripting仍不能获得新写权限 |
| R21 已确认进脚本 | 完整版本/core/pool/policy/意图/确认绑定通过 | 真实用户确认适配器测试替身触发确认，继而真实状态与版本服务通过；不调用脚本模型 | 确认及回执同事务；后续写入绑定该已确认版本；确认后依据竞争变化则拒绝，项目不部分变更 |
| R22 旧报告兼容读 | v1/v2/无标记只legacy读取；未知版本失败关闭，不猜字段 | details/history仍可读；旧确认不能放行新后续操作；旧证据不生成新v3 | 旧报告/证据/确认逐字节不变；恢复不自动认证；新合法v3独立追加，无原JSON迁移 |

共同P层断言：执行前保存旧版本、对象、证据/引用、确认、操作日志及预算行快照；硬错后按实际新analysis ID查询（若调用前未创建则明确无analysis），不存在该操作的成功版本/成功回执，旧行不变。失败诊断/费用可独立追加，不能与成功结果混淆。每次检查真实数据库状态，不能只assert返回failed。

R18额外要求：当新生成失败而旧basis未变，旧已确认报告的有效性与“最新尝试失败”分开展示；当新basis已变，旧版本即使仍有确认行也不得放行。R19明确不宣称能阻止任意SQL管理员伪造全部信任记录，测试对象是模型/普通字段/孤立行和不一致回执。

除22主项外必须有参数变体：非法source/URL/quote字段、跨证据atom绑定、内容hash和规则版本篡改、所有六时间类型、FY2027 Q1、零证据、每题缺口、不同域名不能升级、same-source不同快照、确认幂等/跨用途action、暂停归档、人工保存/恢复、生成期并发人工编辑、确认与进入阶段的竞争、已知/未知usage及诊断故障。实施报告须给出全部NodeID和真实状态，不能只保留22个空壳循环。

## 12. 实施顺序、文件清单和验收标准

**本节仅为后续计划；必须先审核本文再实施。** 不因本次设计任务而开始写测试或改代码。

1. 审核本地确认信任边界、受约束表达树、v6复用、legacy只读及同版本重确认需新版本的选择；若要求自由正文或防任意SQL伪造，先修订方案，不能边实现边放松。
2. 保存实施基线，先建立固定报告输入/表达树fixture、22项U/I/P及关键变体。先确认模块能加载、夹具正常，再记录因旧契约缺失导致的业务RED；ImportError不算RED。
3. 建立共用连接级严格v3证据读取与快照hash，对照B现有545项保护证据路径；不改公开quality授信边界、不迁移旧JSON。
4. 实现报告候选Schema、专用Prompt、纯模板校验/渲染、时间/等级继承、完整缺口与争议约束；测试概述/结论等不能隐藏自由事实。
5. 实现ReportService生成、人工编辑/恢复、CAS原子发布与校验回执；继续复用原执行器和费用结算。新增报告输入/输出版本，旧Schema只保留历史读取。
6. 实现服务端确认意图、本地origin、确认事务、状态投影及统一准入；把所有通用保存/恢复/后续状态入口接到同一规则。确认不与模型生成合并。
7. 最小页面契约适配：v3结构预览、受约束编辑、缺口/分类/时间显示、绑定具体版本的确认；校验仍在服务层。不做界面美化、可信证据审核UI或脚本生成开发。
8. 临时SQLite执行所有P场景、故障触发器、并发、版本/旧行与费用核对；所有硬错验证实际零有效新版本。禁止正式库写入、.env及真实网络。
9. 相关测试通过后执行全量回归与既有545项兼容性核对；因契约变化而过时的预期必须单列审核，保留历史/事务/费用断言，不保留旧旁路。交付实施报告及真实XML/SQL证据后停止，真实API联调另行授权。

| 后续建议文件 | 范围 |
| --- | --- |
| services/research/report_service.py（新增） | 报告生成/编辑/恢复/确认编排、CAS、状态投影；与研究搜索服务分离 |
| services/research/report_contract.py（新增） | v3候选/Envelope/Bundle Schema、模板与明确版本常量 |
| services/research/report_validation.py（新增） | 无IO校验、继承、缺口覆盖及规范渲染/hash；如过大再拆renderer，避免无关重构 |
| services/research/report_evidence.py（新增） | 连接级严格v3证据池与冻结快照，复用B绑定核验内核 |
| services/research/service.py | 既有报告入口委托ReportService；不改计划/搜索/证据业务规则 |
| services/research/schemas.py / prompts.py | 显式报告版本注册、专用Prompt；旧契约只读兼容 |
| database/research_store.py | 共用连接级核验、报告原子发布/回执读写、确认联合绑定；无DDL |
| services/research/guards.py | v3报告校验/准入分流；移除新报告字段嗅探与旧时间规则回退 |
| services/research/diagnostics.py | 固定report错误/path白名单及安全样本，不扩大长度 |
| services/production/version_service.py | 通用create/restore不得绕过报告规范化与CAS；历史读取仍开放 |
| services/production/project_service.py | 继续集中准入，必要时仅调整调用的新守卫接口 |
| services/production/action_service.py | 固定报告校验/确认/失效事件标签，使用既有updated事件类型 |
| pages/research.py | 仅v3报告消费/编辑/明确确认意图适配，不承担权限判断 |
| tests/test_research_report_contract.py（新增） | U层22场景及纯契约变体 |
| tests/test_research_report_integration.py（新增） | I层真实服务及实发请求、确认通道/准入 |
| tests/test_research_report_persistence.py（新增） | P层临时SQLite原子性、旧行、并发、费用 |
| tests/research_report_cases.py、fixtures（新增） | 独立预期和真实v3服务夹具；不伪造生产可信审核 |
| tests/research_support.py及现有研究/生产测试 | 按v3报告重建准入前置样本；保留旧报告只读专项 |

保护文件：数据库迁移、价格/预算/计费、热点评分、采集和其他页面；不新增依赖或基础设施，不改变制作状态枚举。若实施中发现v6确实无法安全表达已批准的需求，停止相关实施，提交最小迁移修订，不能自行升v7。

验收：模型只能选择冻结许可集合；每个重要陈述可回到具体evidence_id和原子/期间/来源快照；报告不能升级等级/时间；争议/缺口不丢；生成/验证/保存失败不覆盖旧版本且费用保留；任何后续新写操作必须使用当前有效v3报告和受控人工确认；U/I/P全部场景及完整回归有实际结果。

## 13. 回滚方案

本次只有设计文档，没有业务回滚操作。本节是未来实施/发布时的策略：

- 实施未写v3数据前，若需撤销代码，只按本批内容基线逐文件恢复本批增量，先保护用户其他未提交变更；不使用git reset/clean/checkout覆盖工作区。
- 一旦已有v3报告/确认，应优先停止新生成并向前修复，保留v3只读或明确不支持提示；不能删除v3版本、改schema_version降级或把旧宽松守卫重新用于新写入。
- 正式版本/证据/确认/审计均只追加；失效用状态投影或新事件，不UPDATE旧报告/确认。不能恢复旧数据库备份覆盖后续合法数据来“回滚”。
- 事务内错误依赖SQLite回滚；已发生模型费用、失败分析及脱敏诊断不回滚为0或删除。人工确认失败只回滚该确认事务。
- 保留旧可读能力与新写入关闭能力，避免旧应用把v3 JSON按v2字段猜格式。若未来真的执行迁移，其回滚/兼容策略必须在迁移方案中另审，不把本节当作迁移授权。

## 14. 已知限制和待审核决定

1. 受约束表达树牺牲自由写作能力，但避免声称通用自然语言支持关系已经被程序证明。复杂因果、数值计算、未注册结论不在首版能力内；不得以inference标签放宽。
2. 报告继承B证据质量上限，无法修复来源本身错误、复杂指代或未识别的冲突，也不能认证转载独立性。verified当前应为空，不因报告或人工确认增加。
3. 纯文本区域启发式、未知财年日历边界和原始期间歧义仍保留；报告不扩大原证据窗口或借文章发布日期补时间。
4. 当前没有多用户认证。local_interactive_operator只代表受控本地交互来源；无法抵御拥有任意SQL/进程权限的人伪造全部持久记录。若要求强身份或防DB管理员伪造，必须先另审认证与独立信任根，不能把v6 JSON视为凭据。
5. v6一个版本只能有一条确认，失效后采用新版本再确认；若业务一定要同版本多轮确认/撤回历史，需审第10.2节最小事件表方案。
6. generated_pending_validation是暂态候选阶段，不把未验证正文存成正式报告；重启后没有原候选不能从脱敏诊断恢复内容。业务状态与费用状态不同步时应显示真实信息，不捏造成功。
7. 当前成功证据池规模有限，但证据卡片和全部缺口仍可能超过请求上限；默认本地停止，不扩预算、不静默遗漏风险。后续缩小研究范围由用户决定。
8. legacy报告继续可读，旧确认不再自动放行新的v3后续操作；这会改变部分旧测试/使用预期，需在实施验收中明确，不回写历史。
9. 现有代码中本次发现的报告旧逻辑均未修改。本阶段不能宣称门禁修复完成、报告v3可用或22项测试已经通过。

需审核的核心方案选择已明确写在本文：v6本地复用及信任范围、受约束表达而非任意正文、旧报告只读不认证、新版本再确认。审核后才进入C-B实施；没有因信息不足而擅自开始代码改造。

## 15. 本次只读范围证明

本阶段只读取指定报告、实际源码/测试与既有B阶段测试摘要；没有执行pytest、业务研究服务、Store构造、Provider或模型请求。B的545通过仅为已交付历史记录，本轮未重跑。

工作前在内存保存121个已有项目/数据库/备份/Git索引与HEAD文件哈希及Git只读状态，排除.env及.env.example等环境文件；未创建基线脚本、日志或临时测试文件。正式库仅使用只读immutable URI查询结构/完整性，未读取业务正文；未设置journal mode、执行DDL、迁移或任何业务写入。

| 范围 | 本阶段操作 |
| --- | --- |
| 生产代码、测试、配置、旧报告 | 只读；交付前与内存基线比较 |
| 正式库及6个已有备份 | 只读哈希；正式库额外只读结构检查；交付前核对 |
| .env、真实Key | 未读取、未计算内容hash、未输出 |
| DeepSeek/Tavily/其他外部API | 0次；未使用网络工具 |
| Python导入/执行 | 仅标准库审计/哈希脚本，使用-B避免写pyc；未导入业务模块运行流程 |
| 测试执行 | 无；22场景只有设计，原545没有重跑 |
| 配置/环境变量 | 未修改；未运行dotenv加载 |
| Git | 只用--no-optional-locks status及ls-files读取；未暂存、提交、切分支、清理、重置或推送 |
| 唯一文件输出 | REPORT_PHASE4_2_1_4_C_A_DESIGN.md |

“不得改变Git状态”按本任务的交付例外解释为不执行Git写操作、不改已有文件及索引/HEAD；唯一授权新增的本文会显示为一个新未跟踪文件，这是交付文档本身，不是代码或提交变更。既有未提交/未跟踪内容和删除状态全部保留。

交付前实际核对结果：121个已有文件全部哈希相等，新增文件仅本文；Git索引和HEAD哈希相等，原status记录逐项保留。正式库仍为v6、结构hash不变、integrity_check=ok、外键错误0，正式库及6个备份文件哈希均未改变。文档静态结构检查确认15个交付章节和R01–R22共22行测试矩阵；这只是文档核对，不是执行测试或实现验收。

**本设计完成即停止，等待审核。未进入报告生成实施、页面改造、数据库迁移、脚本开发或真实API验证。**
