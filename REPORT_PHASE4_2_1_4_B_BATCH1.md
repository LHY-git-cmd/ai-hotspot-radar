# 4.2.1.4-B 第一批：三个纯函数与测试交付

- 项目：ai-hotspot-radar；实际工作目录 E:\one\ai-hotspot-radar。
- 日期：2026-11-04（北京时间）。
- 状态：**第一批完成；未接入研究服务、证据持久化、报告或页面。**
- 依据：用户已确认使用已修订的REPORT_PHASE4_2_1_4_A_DESIGN.md。指定的带(1)文件未找到，经确认后才开始写文件；没有自行假设批准版。

## 1. 本批完成范围

新增独立证据质量判定quality.py、原文窗口materials.py，在已有temporal.py尾部追加v3分类纯函数。旧temporal所有原函数文本与实施前逐字一致，现有服务仍走旧路径。

建立T01–T40纯函数/数据契约测试及额外对抗回归。新增81项：79项单元/契约测试、2项纯函数组合测试；完整套件365项全部通过。设计中的真实服务集成I层与SQLite持久化P层没有在本批实施或冒称通过。

没有新依赖、基础设施或Schema迁移，没有读取.env、调用API、写入正式数据库、改变收费/预算/评分/制作状态，未提交Git。

## 2. 修改与新增文件

以下按本批开始内容基线比较，而非把用户此前Git未提交变更都算本批成果。

| 文件（均相对于E:\one\ai-hotspot-radar） | 本批变化 |
| --- | --- |
| services/research/quality.py | 新增：候选Schema、整批校验、引用/时间数据契约、程序等级 |
| services/research/materials.py | 新增：相关段、上下文、表格、预算、窗口合并与coverage |
| services/research/temporal.py | 仅尾部追加_v3_period_label/classify_temporal；原v2函数完整保留 |
| tests/research_quality_cases.py | 新增合成fixture与整批失败/等级断言，不依赖业务Store |
| tests/test_research_quality_policy.py | 新增质量、数量、信任、恶意清单和硬错测试 |
| tests/test_research_temporal.py | 新增事件/角色/FY/日期/未知与矛盾测试 |
| tests/test_research_materials.py | 新增T01–T40相关窗口/区域/S26/表格/预算测试 |
| tests/test_research_pure_contract_integration.py | 新增材料→质量纯函数组合及无外部效果测试；不是服务集成 |
| tests/fixtures/research_quality/s26.txt | 冻结历史真实S26原文，未修改字节内容 |
| tests/fixtures/research_quality/s26.json | 固定来源快照、hash、4549字符与910/1105偏移说明 |
| REPORT_PHASE4_2_1_4_B_BATCH1.md | 本交付报告 |
| logs/phase4-2-1-4-b-batch1/ | 本批隔离测试驱动、XML/日志、哈希和追踪；Git忽略目录 |

源码/测试目录内的既有文件仅temporal.py变化；没有改既有tests/conftest.py、任何旧测试、service/Store/guards/prompts/旧Schema/页面/迁移/费用实现。

## 3. 三个纯函数的数据契约与规则

### 3.1 quality.assess_batch(candidate, manifest, policy=None)

输入为按题分组的v3候选、服务器材料清单和固定版本/上限policy。输出accepted、items、gaps、errors、decisions及diagnostics_truncated；items包含原候选、规范引用、quality.final_category、independence_status、时间结果和来源日期。

核心规则：

- 候选kind只允许fact/opinion/inference/disputed/unverified。模型不能输出category/final_category/审核字段；额外字段拒绝。
- 每题最多2、全批最多10，先做数量/题集合预检；允许0条但须本题gap。任何硬错整批accepted=False、items=[]，不静默裁剪/合并，不返回部分有效候选。
- source_id、project/run/question关联、body_hash、区域/窗口切片、start/end与实际发送内容严格匹配。偏移采用Python码点半开区间。
- 标题/metadata不能作为业务事实正文；提取failed不能引body。snippet保留区域身份，只能支持未验证线索。
- 保留同题唯一可见来源/字段/位置的确定性纠正，纠正留痕且不改输入；纠正后重复link/证据整批拒绝。title区域不能靠换标签变正文。
- 数值不能只因在同句“预期值”中出现而成为实际值；检查主体/指标/值/单位及明显职务矛盾。必要主体/指标/单位未知时仅unverified，不称确定数值事实。表格缺结构不能强归属金额。
- 同文、共同原稿/编辑控制元数据、同域名或同快照不当独立票；跨域且不同文也只能unknown，不能自动证明独立。
- Schema/manifest/关联/引用/期间/角色硬错返回明确code/path与条目索引，至多20条；本批只返回诊断数据，不写v6诊断表。

公开接口只接受固定policy版本/数量上限，不允许trusted_assessments等普通JSON赋权。没有UI、认证入口、审核数据读取或生产可信记录。

内部_assess_batch的私有策略测试接缝只供隔离fixture模拟受信审定；正例检查命题指纹、source snapshot/body hash、正文区域、实际期间等充分前提。公开assess_batch始终不给审核回调，任何公开数据路径均不能产生verified。内部测试接缝不是身份认证系统，未来不得把它当生产JSON注入入口。

### 3.2 temporal.classify_temporal(claim_text, source_context, research_context)

保留原始发布日期及ISO/RFC解析精度，输出event_kind、speaker_kind、temporal_type、current_relation、明确FY/quarter、coverage_start/end、research_as_of和errors。source_context应来自调用方已核对的原文引用；quality只将验证过的期间上下文送入分类器。

- event_kind依据主语/行为/结果与时间作用域，独立于speaker_kind；管理层指引归company，媒体身份不冒充实际发言者。
- company_guidance、analyst_forecast、market_expectation与actual_result分开；单独expected/forecast不直接分类。历史“低于预期”仍为actual_result。
- FY2027 Q1可在2026年发布。无覆盖日期则label_only、temporal_type=unknown，不自行补季度边界、不因年份不同拒绝。
- 明确覆盖/截至日才与确认目标窗判断current_actual/historical_actual；仅发布日期不能推断期间，当前也不代表全球最新。
- 反向日期范围、未来结束却声称已经实际发生、矛盾期间/候选强作实际等返回错误；quality将错误转成整批拒绝。信息不足保留unknown，不靠猜测提高分类率。

新函数未替换旧source_time_context/validate_time_use/validate_claim_time，因此没有间接改变原服务门禁。

### 3.3 materials.select_windows(sources, questions, max_utf8_bytes=...)

输入为已有原字段、服务器区域和问题关键词。返回windows、coverage_gaps、coverage角色/词项状态、selected_utf8_bytes、保守token_upper、offset_unit、selector_version与截断标记。

- 原行/段及必要句边界定位相关实体、指标、数字/FY；不是每来源固定前缀。数值仅从原字段寻找，不把问题中的数字写入正文。
- 保留数值段和明示周期段、可得管理层/发言引导行；财年关键词不当数值锚点。表格作为完整原块，保留列头/单位/期间。
- 每窗严格等于原字段[start:end]，不清空白改坐标、不伪造文本。只将同源同区域的真实相邻区间按原文合并，排序不变，不跨省略段拼句。
- context_roles分别记录主体/指标/单位/期间/基准/说话者是否存在/可见，relation未证明则unknown。数字命中不代表全部语义已证实。
- 未找到term_not_found；找到但预算省略omitted_budget；必要上下文缺失context_incomplete；缺表格结构table_context_missing。明确题/来源，不自动扩预算或检索。
- max_utf8_bytes限制窗口JSON体积，不是完整模型请求或精确Token数。未来服务接入仍须预扣提示词/Schema等并走既有reservation_units；本批不修改该预算逻辑。

## 4. T01–T40追踪

U=单元/数据契约；I=批准设计中“真实研究服务+Mock Provider”的新集成；P=临时库新持久化验收。**本批只执行U及2项纯函数组合契约，不执行I/P。** 每个编号实际pytest NodeID、参数变体及状态见logs/phase4-2-1-4-b-batch1/test-trace.json。

| 场景 | 本批类型/状态 | 实际断言及结果 | 未执行部分 |
| --- | --- | --- | --- |
| T01 | U/数据契约：通过（1项） | 单官方仅single_source，不能因品牌升级 | I/P均后续批次 |
| T02 | U/数据契约：通过（1项） | 共同原稿/正文相依归一逻辑来源 | I/P均后续批次 |
| T03 | U/数据契约：通过（2项） | 公开接口拒绝JSON授信；私有隔离fixture条件测试，不是生产认证 | I/P均后续批次 |
| T04 | U/数据契约：通过（1项） | 单题3条整批失败、items为空 | I/P均后续批次 |
| T05 | U/数据契约：通过（1项） | 0条+本题gap正常，缺口按题保留 | I/P均后续批次 |
| T06 | U/数据契约：通过（1项） | FY2027 Q1于2026发布保留label_only和空覆盖日 | I/P均后续批次 |
| T07 | U/数据契约：通过（1项） | 历史实绩低于预期不会误作预测 | I/P均后续批次 |
| T08 | U/数据契约：通过（1项） | 公司指引独立分类；强作实绩拒绝 | I/P均后续批次 |
| T09 | U/数据契约：通过（1项） | 分析师预测独立分类、缺锚点不补日期 | I/P均后续批次 |
| T10 | U/数据契约：通过（1项） | title伪装body拒绝 | I/P均后续批次 |
| T11 | U/数据契约：通过（1项） | snippet只能未验证线索 | I/P均后续批次 |
| T12 | U/数据契约：通过（1项） | failed不能引正文，允许有标记的snippet线索 | I/P均后续批次 |
| T13 | U/数据契约：通过（1项） | 前段数字及主体/指标/期间/单位上下文可见 | I/P均后续批次 |
| T14 | U/数据契约：通过（1项） | 固定S26后段数字与前段周期/管理层上下文，原偏移精确 | I/P均后续批次 |
| T15 | U/数据契约：通过（1项） | 分段期间/数字都选中；组合测试核对period context | I/P均后续批次 |
| T16 | U/数据契约：通过（1项） | 源中无数字则gap，伪造引句整批拒绝 | I/P均后续批次 |
| T17 | U/数据契约：通过（1项） | 原发布日期未知保留unknown | I/P均后续批次 |
| T18 | U/数据契约：通过（1项） | 数据期间未知不由来源日补齐 | I/P均后续批次 |
| T19 | U/数据契约：通过（1项） | 正文/摘要同期间不同值拒绝单值事实，允许disputed双引 | I/P均后续批次 |
| T20 | U/数据契约：通过（1项） | 同正文新快照不增来源票 | I/P均后续批次 |
| T21 | U/数据契约：通过（1项） | 零条缺本题gap整批拒绝 | I/P均后续批次 |
| T22 | U/数据契约：通过（1项） | 5题各2、共10合法 | I/P均后续批次 |
| T23 | U/数据契约：通过（1项） | 6题11条整批拒绝 | I/P均后续批次 |
| T24 | U/数据契约：通过（3项） | 重复/缺题/未知题分别拒绝 | I/P均后续批次 |
| T25 | U/数据契约：通过（4项） | 候选越权category/final_category/审核字段拒绝 | I/P均后续批次 |
| T26 | U/数据契约：通过（1项） | 两个域不同文仍独立性unknown，不verified | I/P均后续批次 |
| T27 | U/数据契约：通过（1项） | 实绩/市场预期/指引混合数值拒绝 | I/P均后续批次 |
| T28 | U/数据契约：通过（1项） | 明确目标内截至日可current_actual，无锚点上一季仍unknown | I/P均后续批次 |
| T29 | U/数据契约：通过（1项） | 市场预期不是实际结果 | I/P均后续批次 |
| T30 | U/数据契约：通过（1项） | 纠正后重复link拒绝、不合并 | I/P均后续批次 |
| T31 | U/数据契约：通过（1项） | 重复原句偏移歧义拒绝，正确后部位置保留 | I/P均后续批次 |
| T32 | U/数据契约：通过（1项） | 全文有但窗口未发的引用拒绝 | I/P均后续批次 |
| T33 | U/数据契约：通过（1项） | 只有FY标签却补起止日拒绝 | I/P均后续批次 |
| T34 | U/数据契约：通过（1项） | 明确CEO与候选CFO冲突拒绝 | I/P均后续批次 |
| T35 | U/数据契约：通过（1项） | 表格缺上下文gap；确定金额候选整批失败 | I/P均后续批次 |
| T36 | U/数据契约：通过（1项） | 预算省略有gap且未发引用整批失败 | I/P均后续批次 |
| T37 | U/数据契约：通过（1项） | co.uk等根域名无可靠依据不升级 | I/P均后续批次 |
| T38 | U/数据契约：通过（1项） | 发布日metadata不能作为数据期间 | I/P均后续批次 |
| T39 | U/数据契约：通过（1项） | 同句在标题/正文重现按准确正文位置判断 | I/P均后续批次 |
| T40 | U/数据契约：通过（1项） | 新纯函数契约拒绝v2，未执行新reader接入 | I/P均后续批次 |


## 5. S26专项结果

固定真实来源来自已保存的logs/phase4-2-1-3-real-api/new-sources.json中S26，不联网、不在测试运行中读取生产库。冻结原text至s26.txt，未修改原文来迎合测试。

| 项目 | 实际结果 |
| --- | --- |
| 原文长度 | 4549 Python Unicode字符 |
| 原text UTF-8 SHA-256 | 29ae66728e0afc0e87118fb551f9c231926efcf5f090dab7a3ae50aa906c5e27 |
| 原快照标识 | 0a71fb7ed9e243d1f18223fd679820fbf964d7cf32a333356a214a59c8cd0b7c |
| 数字原始范围 | 52%=[910,913)；336%=[1105,1109) |
| 最终选窗 | **[219,1452)**，精确为原text切片 |
| 选中字符 | 1233，少于全文4549；起点219，不是扩容[0,N) |
| 窗口JSON字节 | 1530（本测试预算3500） |
| 可见上下文 | Oracle、OCI/Cloud Infrastructure revenue、GPU consumption、52%、336%、second quarter fiscal 2025及Management’s commentary |
| 偏移/内容 | 全部精确匹配原文，按Python码点、左闭右开 |
| 期间/财季关联 | 纯函数组合核对period context，保留FY2025 Q2；未知起止日仍None |
| coverage | 本固定例必需词项全部matched、关键角色可见，coverage gap为空；角色的语义关系仍unknown，不冒充人工认证 |

负向测试包括：只保留旧[0,682)窗口时52%/336%引用失败；源中不存在数字时term_not_found，不能从问题插入；预算不足/指标或主体缺失时产生coverage gap；表头缺失不能强归属金额。另有不同段期间/数字场景，保留两个独立窗、不拼成伪连续句。

S26最初还遗漏了数值段之前的管理层引导行，新增原文上下文断言确认RED后修正数值锚点（FY年份不算指标数字），最终包含管理层行。本轮没有补造具体CEO身份或季度起止日。

## 6. 生产可信审核边界验证

1. 当前没有可信审核存储、认证读取器或已授权入口；本批不开发这些能力。
2. 公开assess_batch固定不给内部审核回调，普通policy中trusted_assessments拒绝，模型写最终等级/审核字段也拒绝。manifest/source普通业务数据自称independent不获得任何授信意义。
3. 正向T03只在测试中直接调用内部策略接缝，以RAM fixture模拟命题指纹/快照/正文hash绑定。换快照、换命题、期间未知等不能升级；公开入口相同输入仍不是verified。
4. 没有创建任何生产审核记录、UI、CLI导入或配置开关。测试接缝不是身份认证，不对恶意Python调用者提供安全隔离；未来生产接线只可使用公开接口，不能用私有测试回调伪造认证。
5. **本批未接入生产服务。旧service仍保留P0的模型category规则**，不能声称整个现有研究链已经全局禁用旧verified路径或完成真实质量修复。后续服务接入需强制空审核供给并专项验证，不在本批偷改服务。

## 7. 测试执行及实际结果

| 执行范围 | 实际结果 | 证据 |
| --- | --- | --- |
| 首轮业务RED | 57项中50失败、7通过，0收集错误；接口存在后因未实现业务失败 | red.xml/red.log |
| 首轮实现 | 57通过 | first.xml |
| 对抗清单/预期值回归RED | 39项中3失败；修复后并入后续套件 | adversarial-red.xml |
| 表格/角色/合窗RED | 3项均失败；随后修复 | context-red.xml |
| 最终安全边界RED | 7项均失败；随后修复未知角色/跨题/未来预估等 | final-safety-red.xml |
| S26管理层上下文RED | 1项失败；修复后通过 | speaker-context-red.xml |
| 表格硬错原因/预算未发引用 | 1失败、1通过，修复后通过 | hard-context-red.xml |
| 最终完整套件 | **365 passed，0失败、0错误、0跳过；XML耗时58.464秒** | **full-acceptance.xml/full-acceptance.log** |

最终完整套件包括原有284项及新增81项：79个单元/数据契约用例、2个纯函数组合用例；T01–T40每项均有实际执行NodeID，参数化使总数多于40。附加对抗用例也计入81，不将场景数和测试数混淆。

所有硬错纯函数用例断言accepted=False且items=[]，不是保留其他题的“部分有效结果”。**这是返回契约验证，不是SQLite零落库验证。** 新v3服务I层和持久化P层本批均未执行，报告逐项标后续；没有用skip/xfail制造通过率。完整旧套件里的原服务/临时库回归不能替代新v3 I/P验收。

首次完整回归曾有25个页面失败、333个通过：本批操作驱动误将Windows asyncio标准库_fallback_socketpair的127.0.0.1内部唤醒连接当外部网络。检查完整堆栈后仅放行来自标准库socket.py该函数的本机socketpair，其余socket.connect仍阻断，保留初次日志full.xml/full.log和io-guard.json，未修改/跳过页面测试。之后358项完整回归及后续最终365项全部通过。此环境护栏错误没有当作有效业务RED。

最终命令（E盘工作目录）：

~~~powershell
.\.venv\Scripts\python.exe -B logs\phase4-2-1-4-b-batch1\run_tests.py full-acceptance
~~~

没有为配置问题读取/临时移动.env；沿用测试进程内monkeypatch隔离，测试结束恢复，不改系统/用户环境设置。

## 8. 兼容性与修改范围核验

- temporal.py原v2函数文本前缀SHA与实施前完全相同，仅追加v3纯函数。
- 没有已有service、database、pages模块导入新quality/materials；没有将v3接入生成/确认/报告流程。
- 原预算、模型、重试、计费、评分、制作状态实现与基线哈希均不变；旧284项测试全部实际执行并通过。
- 新候选Schema仅属于独立quality模块，没有更改现有研究Schema或数据库CHECK；不会让已有报告/证据被新Schema回溯否定。
- 三个纯函数经过禁止open/Path.open/socket.connect/sqlite3.connect/os.getenv的测试；输入不变、重复执行输出稳定。

## 9. 正式数据库v6未变证明

仅用只读URI做实施前后版本/完整性核对，未实例化真实Store；没有执行迁移、备份覆盖、SQL写入或测试数据插入。

| 项目 | 实际结果 |
| --- | --- |
| 正式路径 | E:\one\ai-hotspot-radar\data\hotspots.sqlite3 |
| user_version | 前后均6 |
| 正式库SHA-256（前后相同） | 877a0c8ab26808a12f5dd284a06fe9811205549ec66215a59b7728fe7c7db4e4 |
| 已有SQLite文件保护 | 真实库和6个既有备份，共7个文件哈希均不变 |
| integrity_check | ok |
| foreign_key_check | 0错误 |

文件内容哈希一致也覆盖全部旧业务数据、结构与状态；本批没有变更研究来源/证据/旧报告。完整证据见before-hashes.json、verification.json。

## 10. .env与真实API未访问的证据

最终测试操作驱动注册Python审计护栏：.env文件open拒绝、外部socket.connect拒绝、正式data路径的sqlite3.connect拒绝。最终记录：

| 护栏指标 | 计数 |
| --- | --- |
| .env访问尝试 | 0 |
| 被拦截外部网络尝试 | 0 |
| 正式数据库测试连接尝试 | 0 |
| 允许的标准库内部socketpair | 109 |
| pytest退出码 | 0 |

测试现有HTTP/Provider均由Mock隔离，新增模块不导入API客户端、SQLite、Streamlit或配置。最终护栏无外部连接尝试，也无真实DeepSeek/Tavily/其他API调用；内部socketpair不是外部API或放行任意回环HTTP。构建fixture仅读取既有本地公开来源产物；哈希基线刻意不读取.env/.env.example内容。

这些是本批可审阅的执行证据，不宣称已执行网络联调。未读取/修改/输出.env密钥，未修改预算和模型配置。

## 11. Git范围与交付证据

本批基线记录101个既有文件。除temporal.py追加外其余100个基线文件不变；旧用户修改、删除和未跟踪文件保留，不重置/清理/还原。Git未暂存、提交、推送或改历史。

源码/测试新增和修改清单见第2节。Git前后完整状态保存在本批logs目录的git-before.txt、git-after.txt；基于内容哈希区分本轮增量，避免把整个此前未跟踪的services/research目录误算为本批新建。

其他证据：test-trace.json（40场景NodeID）、test-summary.json、s26-verification.json、tested-hashes.json、verification.json、full-acceptance-io-guard.json及各阶段XML/日志。测试护栏驱动在logs目录，仅服务本轮验证，不是生产脚本或新增业务入口。

## 12. 未解决问题与后续依赖

本批范围内三个独立纯函数和T01–T40适用的单元/契约部分完成；以下不能称已完成：

1. v3新研究服务接线、候选Schema/prompt真正用于模型、diagnostics落库、引用/程序等级SQL投影、报告守卫和Streamlit展示：**未开发/未验收**。
2. 设计I层40场景真实服务+Mock Provider、P层40场景临时SQLite零落库/回滚/旧行保护：**后续批次**。本批只证明硬错误items为空和纯函数无IO，不用这些代替真实事务验收。
3. 真实审核记录和认证供给：不存在；公开函数不产生verified，不能用私有测试接缝当生产认证入口。
4. 财年具体日历覆盖/所有自然语言语义/全部说话者关系不能由有限规则可靠确定；当前明确格式可分类，其余unknown。不会从文章发布时间补覆盖日；不声称通用财务NLP完成。
5. 区域标注依赖调用方清单及纯文本启发式，缺DOM无法完美恢复标题/正文；未知不能作为高等级证明。未来服务组装manifest仍需可靠边界与原source绑定，本批没有创建该上游认证。
6. context_roles记录存在/可见，relation仍unknown，不等于已经证明“同比”等基准属于每个数值。期间/值上下文不充分时必须保留缺口，复杂跨段关系仍需审核。
7. 窗口预算只约束选窗JSON，不是整个模型请求或精确Tokenizer；后续接线仍须原完整请求字节/预占检查。没有新增精准Tokenizer或调大上限。
8. 转载/编辑控制关系只有已提供原稿/同文等排除依据，未发现依赖不证明独立；没有新增公共后缀库或联网追索。

与设计全阶段目标的范围冲突已采取保守策略：保留旧服务行为、本批不越权接线，也不声称生产质量已完全修复。后续批次需要单独批准，才能实施服务/持久化/报告/页面改造及其验收。真实API复测仍需独立授权。

**第一批结束，停止并等待审核；不进入第二批或真实API验证。**
