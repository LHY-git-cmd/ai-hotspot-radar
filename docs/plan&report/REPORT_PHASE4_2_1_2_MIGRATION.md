# 第四阶段 4.2.1.2：正式数据库 v5→v6 迁移报告

- 项目：ai-hotspot-radar。
- 唯一正式目标：`E:\one\ai-hotspot-radar\data\hotspots.sqlite3`。
- 工作目录：`E:\one\ai-hotspot-radar`；Git根目录也为E盘该项目。
- 报告时间：2026-11-03 15:40:07 CST（北京时间）。
- 范围：正式迁移、备份、数据保护、临时副本约束测试和无网络应用兼容性检查；没有开发新功能或进行真实API联调。

## 1. 结论分别说明

| 验收项目 | 结果 | 边界 |
| --- | --- | --- |
| 正式迁移 | **成功**，真实库 user_version=6 | 使用现有项目迁移入口；只有新v6 DDL |
| 数据保护核验 | **成功** | 22张旧表（21张业务表及sqlite_sequence）的结构、行数和全量行内容一致 |
| 应用兼容性验证 | **成功（本次验证范围内）** | 真实库只读访问通过；完整页面AppTest使用迁移后真实数据的独立副本，没有浏览器连接生产库进行写操作 |
| 真实API联调 | **尚未执行** | DeepSeek、Tavily和其他外部API均0次 |

上述四项不能相互替代。没有自动开始下一阶段。

## 2. 执行前检查

1. 当前目录、目标路径及Git根目录均确认是 `E:\one\ai-hotspot-radar`，没有对其他同名目录迁移。
2. 真实数据库文件存在；只读URI连接确认版本5、完整性ok、外键无错误。
3. 检查时没有WAL或journal旁文件。Windows Restart Manager返回数据库占用进程列表为空；另以FileAccess.Read/FileShare.None打开并立即关闭的独占只读句柄探测通过。
4. 已记录原有Git修改和未跟踪文件。迁移前状态共39行，未清理或重置。
5. 已阅读 `E:\one\ai-hotspot-radar\database\migrations.py`、`database\research_quality_migration.py` 及Store调用方式。
6. 与已验收P0的tested-code-hashes.json核对22个文件，全部一致；执行后也再次核对，未修改项目实现。
7. 已确认框架以BEGIN IMMEDIATE获取写锁；备份后在同一事务执行v6追加DDL并更新user_version；异常由连接事务上下文回滚。

前置进程检查反映检查当时的句柄状态；正式迁移期间的并发写入保护由SQLite事务写锁承担。事务内备份验证还再次核对了源文件哈希和旧数据基线。

## 3. 迁移前真实库

| 属性 | 值 |
| --- | --- |
| user_version | 5 |
| 文件大小 | 2170880 字节 |
| SHA-256 | `0206403816f12ed79fca304da4d72bcf930e367cfbf244aba4d3b07cb4085b9e` |
| integrity_check | ok |
| foreign_key_check | 0条错误 |
| 旧表数量 | 22（含sqlite_sequence） |

## 4. 独立备份与验证

使用项目既有 `_backup_database` 助手，其内部用只读源连接和SQLite Connection.backup生成一致快照，未使用文件复制替代SQLite安全备份。每个目标名均检查不存在，未覆盖旧备份。

迁移前独立备份先完成并验证，之后才调用正式迁移入口。入口依现有规则另生成一份事务内备份，也保留并验证。

| 类型 | 路径 | 大小（字节） | SHA-256 | 核验 |
| --- | --- | --- | --- | --- |
| 迁移前独立备份 | `E:\one\ai-hotspot-radar\data\hotspots.pre-v6-20261103T073159839165Z-091ccfb5.sqlite3` | 2170880 | `123408524b6c14a94c3aa1ab2dd99b8b16417b6dab406aaaa76d09e4e2392880` | v5 / ok / 无外键错误 |
| 框架事务内备份 | `E:\one\ai-hotspot-radar\data\hotspots.pre-v6-20261103T073233115218Z-a1900b41.sqlite3` | 2170880 | `123408524b6c14a94c3aa1ab2dd99b8b16417b6dab406aaaa76d09e4e2392880` | v5 / ok / 无外键错误 |

两份备份均为530页×4096字节，大小合理；integrity_check=ok、foreign_key_check无错误、user_version=5。每张旧表的结构与所有行内容也与源库基线一致。

备份SHA与源库SHA不同，已经额外核查：文件等长，仅数据库页头3个字节不同（偏移27、43、95），逻辑Schema和全量数据一致；不是未经核验地假设字节相同。两份安全备份的SHA彼此一致。

既有4份旧备份仍存在，哈希与此前基线一致。没有删除或覆盖任何备份。

## 5. 实际迁移入口与过程

实际调用：

```python
# connection使用真实目标的mode=rw连接，避免误建文件，并启用foreign_keys。
database.migrations.migrate(connection, DB, backup_existing=True)
```

操作驱动：`E:\one\ai-hotspot-radar\logs\phase4-2-1-2-migration\migrate_driver.py`。

过程：

1. 只读检查并保存旧表结构、字段、索引、外键、触发器和所有行的基线。
2. 创建并核验独立v5备份；再次确认原文件哈希未变化。
3. 调用现有migrate；框架取得BEGIN IMMEDIATE写锁，进入原备份流程。
4. 在当前操作进程中临时包装既有备份助手：原助手成功返回后，先验证新备份的版本、完整性、外键、大小、全部旧表及源库基线；验证通过才返回给原迁移函数。这是额外验证关卡，没有改写磁盘上的迁移代码或DDL；结束后恢复原助手引用。
5. v5分支只调用create_research_quality_tables，新建诊断表和3个触发器；没有执行create_research_tables等v5或更早版本DDL。
6. 在原事务内更新user_version=6并提交。随后的完整核验全部使用只读连接。

没有手工ALTER旧表、重建数据库、导入覆盖、删除或清空数据。迁移未出现异常，因此没有执行回滚恢复或文件覆盖恢复。

## 6. 迁移后真实库与完整性

| 属性 | 结果 |
| --- | --- |
| user_version | **6** |
| integrity_check | **ok** |
| foreign_key_check | **0条错误** |
| 文件大小 | 2170880 字节 |
| SHA-256 | `8844a562948917fa7cab52b016a2429e73ceb619640aa6dae3df25dd5b44be84` |
| 新增表 | research_model_diagnostics |
| 删除表 | 无 |
| 真实诊断表行数 | 0 |

文件大小没有增加；新增对象使用了现有数据库空间。大小未变不代替版本、结构和数据核验。

## 7. 旧表全量数据保护比较

以验证通过的独立v5备份为基线，逐表比较：表名集合、CREATE TABLE SQL、table_xinfo字段定义、foreign_key_list、index_list/index_xinfo、索引SQL及触发器SQL；并读取所有列、所有行，按值类型规范编码后排序逐行比较，保留重复行数量。不是只比较行数或只比较内容哈希；每表的内容SHA也另行留档。

| 旧表 | 迁移前行数 | 迁移后行数 | 表结构/字段/原索引触发器 | 全部行内容 |
| --- | --- | --- | --- | --- |
| ai_analysis_runs | 15 | 15 | 一致 | 一致 |
| ai_budget_settings | 1 | 1 | 一致 | 一致 |
| collection_runs | 16 | 16 | 一致 | 一致 |
| hotspot_scores | 61 | 61 | 一致 | 一致 |
| hotspot_snapshots | 296 | 296 | 一致 | 一致 |
| hotspots | 61 | 61 | 一致 | 一致 |
| idea_actions | 5 | 5 | 一致 | 一致 |
| production_actions | 12 | 12 | 一致 | 一致 |
| production_objects | 2 | 2 | 一致 | 一致 |
| production_projects | 1 | 1 | 一致 | 一致 |
| production_versions | 4 | 4 | 一致 | 一致 |
| research_evidence | 30 | 30 | 一致 | 一致 |
| research_evidence_sources | 51 | 51 | 一致 | 一致 |
| research_plan_confirmations | 2 | 2 | 一致 | 一致 |
| research_report_confirmations | 0 | 0 | 一致 | 一致 |
| research_search_calls | 14 | 14 | 一致 | 一致 |
| research_search_runs | 2 | 2 | 一致 | 一致 |
| research_source_questions | 30 | 30 | 一致 | 一致 |
| research_sources | 18 | 18 | 一致 | 一致 |
| sqlite_sequence | 4 | 4 | 一致 | 一致 |
| topic_analyses | 15 | 15 | 一致 | 一致 |
| video_ideas | 9 | 9 | 一致 | 一致 |

计划和报告正文位于production_versions，证据输入/输出位于topic_analyses；这些JSON与旧source_id、引文、偏移、关联、费用、预算和制作状态均逐值一致。sqlite_sequence作为内部序列表也纳入比较。

没有把原本已存在的诊断旁路历史证据当成迁移新增异常，没有清理任何旧记录。详细结构、逐表行数和内容哈希见before-tables.json及migration-result.json。

## 8. v6新增对象、索引、触发器与约束

表research_model_diagnostics有12列：id、project_id、analysis_id、attempt_run_id、stage、code、path_json、item_index、details_json、rejected_document_json、document_truncated、created_at。

已核对：

- 主键id；项目/分析/调用尝试的3个外键与NOT NULL定义。
- 自动唯一索引 `sqlite_autoindex_research_model_diagnostics_1`，约束 `(attempt_run_id,stage)`。
- stage仅允许provider/validation/persistence。
- path_json、details_json及可选rejected_document_json的JSON有效性约束。
- 拒绝文档最多16384字节，document_truncated只能为0/1。
- `validate_research_diagnostic`：核对project、analysis、attempt属于同一研究链。
- `protect_research_model_diagnostics_update`、`protect_research_model_diagnostics_delete`：只追加保护。

没有新增未预期的其他表，没有改变任何旧表结构或旧保护触发器。

## 9. 诊断写入保护验证：仅临时副本

测试库：`E:\one\ai-hotspot-radar\logs\phase4-2-1-2-migration\verification-xbvzdkvf\diagnostics-copy.sqlite3`。

正常诊断通过项目ResearchStore.save_diagnostic写入成功，固定代码及条目索引可读；随后10项负向检查全部按预期拒绝：跨项目关联、UPDATE、DELETE、重复attempt/stage、非法stage、无效path JSON、无效details JSON、无效拒绝文档JSON、超大拒绝文档、非法截断标识。

跨项目测试使用临时副本中新建的另一项目，错误明确来自研究链不匹配触发器；不是只用不存在项目碰巧触发外键错误。测试结束真实诊断表仍是0行。

## 10. 应用兼容性检查

实际真实库已通过只读连接打开，并全量读取所有旧表。完整应用和服务读取另使用迁移后真实数据的独立一致副本，不把AppTest指向生产数据库。

应用测试库：`E:\one\ai-hotspot-radar\logs\phase4-2-1-2-migration\verification-xbvzdkvf\application-copy.sqlite3`。

| 检查 | 实际结果 |
| --- | --- |
| 热点排行 | 正常渲染，当前页20条存量热点 |
| AI选题分析 | 正常渲染，没有点击模型调用按钮 |
| 制作工作台 | 正常渲染；1个原有制作项目、9个原有视频选题正常读取 |
| 制作任务详情/资料研究 | 正常渲染，原有研究报告可见，没有点击搜索、模型、保存或确认操作 |
| 页面刷新 | 正常，无AppTest异常 |
| 页面浏览前后副本数据 | 全部表结构与行内容一致 |
| 页面测试后真实库 | SHA仍等于迁移后核验值；诊断表0行 |

配置加载使用验证进程内的显式配置函数替身，不读取.env，也不改系统环境变量。HTTP入口、DeepSeek.complete和Tavily请求入口均有拒绝护栏；计数：network=0、DeepSeek=0、Tavily=0、dotenv=0。

没有在真实浏览器中启动生产应用进行人工写操作；因此此处成功指受控AppTest及数据读取兼容性，不宣称已完成现场浏览器端联调。

## 11. 异常与处理情况

- 正式迁移、备份验证、旧数据比较、完整性和外键核验：**无异常**。
- 辅助脚本准备有两次工具错误：首次路径断言的字符串转义误报，以及首次生成临时验证脚本时的字符串定界SyntaxError。均在各自脚本执行数据库操作前终止；经检查修正后重跑，没有修改项目实现或数据库内容，也没有绕过停止条件。
- AppTest出现一次bare mode的missing ScriptRunContext警告；没有AppTest异常，页面和全量数据一致性检查通过。原日志保留。
- 没有通过修改/删除数据让检查通过，没有删除数据库、覆盖恢复或清理异常现场。

## 12. 证据文件与最终Git状态

所有操作记录位于 `E:\one\ai-hotspot-radar\logs\phase4-2-1-2-migration`：preflight.json、backup-verified.json、framework-backup-verified.json、backup-byte-comparison.json、before-tables.json、migration-result.json、compatibility-result.json、compatibility.log、migrate_driver.py、verify_temp.py及Git前后状态记录。临时副本保留在该目录下的verification-*目录中，与真实库和正式备份隔离。

P0已验收22个代码/测试文件的哈希在迁移前后全部一致。本轮不修改评分、采集、预算、制作状态或其他业务逻辑，不读取/修改.env，不执行git reset/clean/checkout/commit/push。

生成本报告前，Git状态与迁移前39行完全一致；最终仅多出本报告这一未跟踪条目，备份和操作日志位于原有忽略路径。完整最终状态如下：

```text
 M .env.example
 M README.md
 M ai_page.py
 M app.py
 M database/ai_store.py
 M database/migrations.py
 M services/ai/analyzer.py
 M services/ai/base.py
 M services/ai/cost_tracker.py
 M services/ai/deepseek_client.py
 M services/ai/schemas.py
 M tests/conftest.py
 M tests/test_ai_migration.py
?? PLAN_PHASE4_1.md
?? PLAN_PHASE4_2_1.md
?? REPORT_PHASE4_1.md
?? REPORT_PHASE4_2_1.md
?? REPORT_PHASE4_2_1_1_AUDIT.md
?? REPORT_PHASE4_2_1_1_P0.md
?? REPORT_PHASE4_2_1_2_MIGRATION.md
?? REPORT_REAL_RUN_2026-11-03.md
?? database/production_migration.py
?? database/production_store.py
?? database/research_migration.py
?? database/research_quality_migration.py
?? database/research_store.py
?? pages/
?? services/ai/executor.py
?? services/production/
?? services/research/
?? tests/research_support.py
?? tests/test_production_page.py
?? tests/test_production_service.py
?? tests/test_production_store.py
?? tests/test_production_versions.py
?? tests/test_research_migration.py
?? tests/test_research_page.py
?? tests/test_research_provider.py
?? tests/test_research_quality.py
?? tests/test_research_workflow.py
```

## 13. 未完成或未执行的验证项目

- 真实DeepSeek/Tavily及其他外部API联调：未执行，按本次范围保留为下一次独立授权事项。
- 真实浏览器连接生产库的人工交互、写入及部署/服务重启验证：未执行；本次采用真实数据副本的AppTest。
- 本轮未重新运行此前284项开发测试：迁移代码哈希与验收版本一致，本次执行的是正式库全量核验、临时约束测试和存量数据页面兼容性检查。

本次明确要求的正式迁移、备份验证、全部旧表比较、诊断保护临时测试及无网络应用兼容性检查均已完成，没有待处理的迁移故障。**真实API联调尚未执行，不能称为已完成。**

本阶段结束，不自动进入下一阶段。
