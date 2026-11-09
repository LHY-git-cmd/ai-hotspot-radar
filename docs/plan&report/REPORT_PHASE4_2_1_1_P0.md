# 第四阶段 4.2.1.1-P0：研究报告质量加固交付报告

- 项目：ai-hotspot-radar。
- 路径：`E:\one\ai-hotspot-radar`。
- 日期：2026-11-03（北京时间）。
- 状态：**P0 实施与隔离测试完成；真实数据库未迁移，未做真实 API 联调。已停止于本阶段。**
- 实施范围以本次用户要求为准。参考审查报告，不实施其成功缓存、观察表、原站抓取、多调用分批、脚本或后续制作模块。

## 1. 完成内容

### P0-1 日期规范化与输入补全

新增纯函数时间模块；支持常用 ISO 8601（年、月、日和不同时间精度）及 RFC 1123。保留数据库 published_at 原始字符串；另提供规范化值与 year/month/day/minute/second/fraction 等精度，不给只有日期的值补造午夜，也不为无时区值补造时区。

organize_evidence 和 generate_report 的每个来源均发送 published_at 和 time_context。上下文明确区分：

- `date_kind=provider_estimated_published_or_updated`：服务商估计的发布或更新日期，不是确定的首次发布日期。
- `local_saved_at`：来源行首次在本地保存的时间，不是原站抓取或服务商缓存创建时间。
- `data_period=unknown`：来源本身不能证明具体数据周期；证据可另填经原文引用核对的周期。
- `modified_at=unknown`、`provider_snapshot_at=unknown`：没有可靠依据就不填写。
- `research_as_of`：在模型输入中保存本次研究评估日期。

没有更新、规范化回写或回填任何已有来源行。

### P0-2 逐条历史来源标记与时间用途约束

证据和报告的每个来源引用旁均显示具体时间上下文。例如 2024 年来源在 2026 年研究中，显示“2024 年服务商估计发布或更新的来源，属于历史材料；数据实际所属周期尚未核实（unknown）”。不是只在末尾放一条总提醒。

新证据 Schema 增加 `time_scope` 和 `data_period`；新报告各类 claim 增加 `time_scope`。用途区分 unknown/historical/forecast/current/not_applicable。当前用途必须有与研究年份匹配、且能在实际引文中逐字核对的数据周期；不能从文章日期推断财季。

本地校验拒绝历史来源标记 current、明显把旧来源表述为本年当前数据、将带预测/估算标记的引文写成实际数据等情况；支持“并非实际数据”这样的正常预测警示。无法判定时仍保留 unknown。

时间上下文通过现有分析 JSON、来源连接和版本 JSON 保存/读取，不给来源增加伪造时间。旧证据/旧报告正文不自动修改；新生成报告追加版本。旧格式报告的人工保存、确认与恢复也执行时间用途检查，不能借旧格式绕过。

### P0-3 query 优化与确认链

新增共用 `build_query`：关键词清洗空白、按大小写无关去重后组合；不自动拼接完整问题或来源类型。`query_override` 非空时使用人工语句。400 字符单行上限在发送前本地检查。

研究计划编辑区新增自定义 query 和实际发送预览；预览与服务层调用同一个构造函数。修改后必须保存新计划、重新确认，页面按新版本分配新的 action_id，服务层拒绝旧版本或跨版本动作 ID。

`query_builder_version=keywords-v2` 保存到计划、运行参数和每题 request_json；最终 query 同时保存在运行与调用记录。历史已确认计划若没有当前构造器版本，不能直接使用旧确认执行新算法的 query；必须保存新版本、预览后重确认。

历史计划 JSON 仍可读取/恢复；新增计划字段与生成工具 Schema 分开兼容，不改写历史版本。

### P0-4 已保存快照本地变化提醒

继续用 SHA-256 和 `(project_id,url_key,content_hash)` 追加快照。新哈希纳入版本标识、标题、日期原值、正文、摘录及提取状态，修复“正文相同但摘录变化被去重丢失”。旧哈希不重算。

按同一个规范化 URL 上一次实际关联的搜索运行比较，分别标识正文、标题、日期、摘录、提取失败和恢复提取；页面显示新旧 source_id。A→B→A 正确比较 B→A，而非误用最大的 source_id。

保留旧来源、引文、quote_offset、证据和报告引用；不会因为内容哈希变化就认定事实变化。提示明确是保存材料差异、尚未独立核验当前原文。本期没有原站抓取，也没有增加 search/extract 调用。

新哈希算法首次处理旧内容时可能追加等价快照；页面按字段差异判断，不会仅因 ID/哈希不同报告正文变化。

### P0-5 证据规模与严格校验

新版本本地 Schema、模型输出 Schema、提示词、语义校验和页面说明统一为：总数最多10条、每题最多2条、允许0条。每个没有证据的问题必须有一条以“问题ID: ”开头的 gaps，不能用一条总提醒替代所有问题缺口。

保留已有的同来源字段纠正、同问题下唯一逐字命中的来源纠正；纠正后重复 link 或整条重复证据均拒绝，不自动删除、合并或裁剪结果。新增上限不追溯否定旧证据批次。

引文不在实际发送材料、只在标题、位于未发送正文、候选来源歧义、跨问题/未知来源、verified 条件不足等继续拒绝。没有削弱独立域名和提取正文门槛。

现有 Provider 兼容转换仍会移除服务商不支持的数组长度参数；本地完整 Schema 和语义检查保留硬限制，不能把服务商 strict 当作最终验收。

### P0-6 持久失败诊断

新增 `ResearchValidationError` 与研究专用诊断表；记录阶段、固定错误代码、JSON Schema 路径、条目索引、安全规则信息、analysis_id、attempt_run_id、结构样本和截断标识。页面可查看脱敏诊断表。

Provider 解析错误区分响应结构、工具结构/工具不匹配、JSON 解析、文档类型、输出截断。保持原 invalid_schema/invalid_response/truncated 等顶层错误类型和计费行为。

拒绝文档只保存脱敏结构：所有自由文本替换为占位符，未知字段名丢弃，路径按白名单脱敏；上限16 KiB，深度/条数/大小裁剪明确标记。**保存的是安全结构样本，不是可直接逐字回放的原始模型输出。** 不保存认证头、密钥、远程异常正文或敏感配置。

诊断在原尝试用量结算后附加；诊断保存故障不会抹去原错误、费用或改变重试行为。失败文档不会进入成功证据。共用执行器只新增可选诊断回调，未改变预算预占、费用算法、重试次数或未知费用处理。

## 2. 修改文件清单

以下是相对于本轮开始时文件内容的变化，包含开始时已经未跟踪的研究代码；不是相对于 Git HEAD 的全部工作区差异。

| 文件 | 本轮变化 |
| --- | --- |
| E:\one\ai-hotspot-radar\services\research\temporal.py | 新增日期、逐条时间上下文和用途约束 |
| E:\one\ai-hotspot-radar\services\research\queries.py | 新增共用 query 构造和构造器版本 |
| E:\one\ai-hotspot-radar\services\research\diagnostics.py | 新增结构化异常、路径与结构样本脱敏 |
| E:\one\ai-hotspot-radar\services\research\schemas.py | 计划兼容、新证据上限、时间字段、Schema错误路径 |
| E:\one\ai-hotspot-radar\services\research\prompts.py | 日期含义、历史/预测约束、数量与逐题gaps |
| E:\one\ai-hotspot-radar\services\research\service.py | 输入补全、query确认、严格校验、版本与诊断回调 |
| E:\one\ai-hotspot-radar\services\research\guards.py | 新旧报告格式兼容、报告时间用途校验 |
| E:\one\ai-hotspot-radar\database\research_store.py | 新哈希、快照比较、诊断保存/查询、证据时间读取 |
| E:\one\ai-hotspot-radar\database\research_quality_migration.py | 新增v6追加DDL与诊断保护触发器 |
| E:\one\ai-hotspot-radar\database\migrations.py | v5→v6入口、旧版本链路和pre-v6备份 |
| E:\one\ai-hotspot-radar\services\ai\base.py | AIError增加可选安全诊断 |
| E:\one\ai-hotspot-radar\services\ai\deepseek_client.py | 解析失败子类型，保持用量及顶层错误 |
| E:\one\ai-hotspot-radar\services\ai\executor.py | 可选诊断回调，结算和重试规则保留 |
| E:\one\ai-hotspot-radar\pages\research.py | query编辑/预览、逐条时间标签、快照提醒、诊断、报告用途编辑 |
| E:\one\ai-hotspot-radar\tests\conftest.py | 自动隔离dotenv/环境、禁止真实网络和生产库连接 |
| E:\one\ai-hotspot-radar\tests\research_support.py | Mock证据/报告符合新Schema |
| E:\one\ai-hotspot-radar\tests\test_research_quality.py | 新增48个P0验收用例（含参数化） |
| E:\one\ai-hotspot-radar\tests\test_research_page.py | 新增2个页面验收用例 |
| E:\one\ai-hotspot-radar\tests\test_research_workflow.py | 调整显式Mock文档、逐题gaps，保留原断言 |
| E:\one\ai-hotspot-radar\tests\test_research_migration.py | 最新版本及备份文件名预期更新至v6 |
| E:\one\ai-hotspot-radar\tests\test_ai_migration.py | 最新版本及备份文件名预期更新至v6 |
| E:\one\ai-hotspot-radar\tests\test_production_store.py | 最新版本及备份文件名预期更新至v6 |

合计17个既有文件增量修改、5个新Python文件；另新增本交付报告及忽略目录下的测试/核对日志。没有修改审查报告、README、配置、评分规则或制作状态服务。

## 3. 数据库迁移实现与临时验证

目标版本6。来自v5时只执行新的 `create_research_quality_tables`，不重跑v5研究建表；来自0/2/3/4的升级链继续执行原相应版本步骤，再追加v6。备份文件名使用pre-v6，DDL与user_version处于同一事务。

`research_model_diagnostics` 包含 project_id、analysis_id、attempt_run_id、stage、code、path_json、item_index、details_json、rejected_document_json、document_truncated、created_at 等字段。限制JSON有效性和结构样本字节上限；同尝试同阶段唯一；插入触发器核对项目、研究分析与尝试属于同一条链；UPDATE/DELETE触发器保护只追加记录。

临时验证全部通过：

- v5→v6不调用旧v5 DDL；重复打开不重复备份/建表。
- v6 DDL后注入异常，完整回滚到v5，新增表消失，旧来源保护触发器保留。
- 完整临时v5样本保有来源、引文、证据、报告和费用；迁移前后每张旧表的所有列定义、所有行逐一比较一致。
- 跨项目诊断链被拒绝；诊断与原研究历史的保护触发器继续生效。
- v2/v3/v4及新库的原迁移回归、备份、完整性和外键检查通过。

**没有直接迁移真实数据库。** 开始与结束核对的5个SQLite文件（真实库及已有备份）哈希均一致；只读确认真实 `E:\one\ai-hotspot-radar\data\hotspots.sqlite3` 仍为v5。

后续实际启用需要获授权的v5→v6迁移。现有Store初始化会调用迁移入口；本轮没有启动真实应用或对真实路径实例化Store。测试生成的备份全部位于临时测试库目录。

## 4. 测试与实际结果

所有测试使用Mock Provider、临时库、显式隔离配置。自动夹具屏蔽dotenv加载，清除测试进程继承的相关配置，再由用例设置假配置；真实HTTP入口及生产data目录连接被阻断。没有移动、读取或改写 `.env`，没有改变用户系统环境变量。

| 验证 | 实际结果 | 记录 |
| --- | --- | --- |
| 修改业务代码前完整基线 | 234 passed；0失败/错误/跳过；45.288秒 | logs/phase4-2-1-1-p0/baseline.xml |
| 首轮P0 RED | 25项：24失败、1通过；无收集错误，失败为目标功能缺失/旧行为 | logs/phase4-2-1-1-p0/red.xml |
| 首轮研究相关回归 | 90 passed；0失败/错误/跳过 | logs/phase4-2-1-1-p0/research.xml |
| 兼容性与页面补测后的完整回归 | 273 passed；0失败/错误/跳过 | logs/phase4-2-1-1-p0/full.xml |
| 旧格式人工报告/本年措辞边界 RED | 2项均确认失败，随后修复 | logs/phase4-2-1-1-p0/edge-red.xml |
| 边界修复完整回归 | 281 passed；0失败/错误/跳过 | logs/phase4-2-1-1-p0/final.xml |
| **最终完整回归** | **284 passed；0失败、0错误、0跳过；63.786秒** | **logs/phase4-2-1-1-p0/final-all.xml** |

最终命令：

```powershell
# 工作目录：E:\one\ai-hotspot-radar；测试夹具阻止真实网络、dotenv和生产库连接。
.\.venv\Scripts\python.exe -B -m pytest -q --junitxml=logs/phase4-2-1-1-p0/final-all.xml
```

新增测试合计50项：新质量测试文件48项、页面测试2项。覆盖日期原值/精度/unknown、双阶段输入、逐条2024历史标签、不补财季、query预览与实际一致、保存重确认及旧构造器确认拒绝、快照各维度与A→B→A、旧报告/证据追溯、0/10/11及每题2/3边界、逐题gaps、不可见/歧义/跨题引用拒绝、纠正后重复拒绝、预测与实际区分、诊断脱敏/大小/故障、Provider解析与费用、迁移完整性/回滚/幂等/跨项目与触发器。

没有通过跳过用例处理原环境问题。原先受真实dotenv影响的“删除Key后按钮应禁用”用例在隔离配置下通过；原用例及断言保留。既有测试中只调整了新Schema所需的Mock字段/gaps和v6版本/备份预期，没有降低业务断言。

## 5. 原有功能回归与受保护逻辑

最终测试涵盖原采集、快照、评分、刷新、AI分析、AI预算/费用/安全、制作任务/版本、研究工作流、Provider及页面用例。

与本轮内容基线逐文件哈希比较，评分实现/规则、AI analyzer、费用计算模块、AIStore、制作状态/动作服务等原实现没有改写。共用执行器增加的仅为可选诊断路径；预算和费用相关测试均通过。

保留100元/月默认预算及阈值、原重试次数、失败用量结算、未知费用预占、原制作状态与确认门禁。没有自动确认报告、切换制作阶段或生成后续制作内容。Tavily逐次credits和配额机制没有重写。

## 6. Git修改前后及核对证据

开始时工作区已存在第四阶段的大量修改和未跟踪文件。本轮先保存代码内容基线、哈希及Git状态，再在其上最小增量修改，没有reset、clean、覆盖还原用户工作、暂存、提交或推送。

- 修改前状态：`E:\one\ai-hotspot-radar\logs\phase4-2-1-1-p0\git-before.txt`。
- 修改后状态：`E:\one\ai-hotspot-radar\logs\phase4-2-1-1-p0\git-after.txt`。
- 本轮原内容与逐文件差异：同目录的before/及diffs/，用于区分此前未提交修改和本期增量。
- 保护与核对结果：同目录baseline-hashes.json、verification.json、tested-code-hashes.json。
- Git提交：**未暂存、未提交、未推送**。

实际工作目录为E盘。环境提供的C盘同名目录不是该项目，业务修改及验证均显式使用E盘路径。

## 7. 未完成项目、限制及后续所需事项

### 本轮范围内

六项P0代码与隔离验收已完成，无等待实施的P0代码项目。生产迁移与真实联调按用户限制未执行，不能把Mock通过说成生产验证完成。

### 实际限制

- 历史性目前按来源估计日期与研究评估年份作保守警示，不代表已独立确定文章首发时间或数据财季。
- 新用途字段、逐字周期核对、明确年份/预测措辞检查可以拒绝已覆盖的明显时间错误；不能证明任意自然语言摘要的含义都正确，不能替代人工事实审核。转载独立性也仍需人工核查。
- 本期只比较本地保存快照。服务商连续返回旧缓存时，系统不能证明当前原站没有更新；没有“原文最新”保证。
- 旧报告正文保持不变；重新生成新版本才能获得新的模型输入与输出格式。
- 诊断字符串全部脱敏，只能检查结构和固定错误路径；历史未留存的原始响应以及自由文本逐字回放不能恢复。

### 是否需要真实数据库迁移

**需要。** 真实库仍为v5，实际启用诊断持久化需要后续授权升级到v6。本轮只交付迁移实现和临时验证结果。

### 是否需要下一轮真实API联调

**建议另行授权后进行。** 需要检验DeepSeek对新Schema、逐题gaps及时间用途的实际输出稳定性，以及Tavily关键词query的命中改善和实际credits；本轮无真实API费用，也不承诺尚未实测的成功率或节费比例。

本次已结束，不自动开始P1、P2、真实库迁移或真实API联调。
