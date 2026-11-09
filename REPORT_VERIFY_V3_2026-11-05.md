# 真实链路验证报告：v3 证据池 → 报告 → 人工确认 → 制作门禁

- 日期：2026-11-05（北京时间）
- 环境：Windows 11 / Python 3.13.12；数据库 v6；真实 DeepSeek `deepseek-flash`（`deepseek-v4-pro` 仅做过失败探测）+ 真实 Tavily。
- 方式：只调用生产服务层（`ResearchService` / `ReportService` / `LocalReportReviewSession` / `ProjectService`），不使用 Mock，不绕过确认、校验与门禁。
- 结论：**6 个检查点在项目 2（claude-mem）上全部通过**；项目 1（Oracle）在第 2 步被 v3 证据契约稳定拒绝，作为失败证据单独保留。

## 0. 六步结论

| # | 检查点 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | 真实 DeepSeek + Tavily 完成一次研究 | ✅ | 项目 2：计划 analysis 37；搜索 run 6（5 问 + 1 次提取，7 credits）；证据 45；报告 48 |
| 2 | 真实证据进入 v3 证据池 | ✅（项目 2） / ❌（项目 1） | 45：`research-evidence-v3` / `quality-v3`，9 条证据、9 条引用、75 个结构化缺口；项目 1 共 33 次失败、0 条入池 |
| 3 | 报告正确生成、引用和分类 | ✅ | 报告 v10：5 题、9 条陈述、9 条引用、93 个缺口、2 条结论；0 verified / 3 opinion / 6 unverified；引用坐标+哈希+URL 逐条核验通过 |
| 4 | 研究缺口被保留 | ✅ | 证据池 75 个结构化缺口全部出现在报告，另由程序派生 18 个（temporal 9、claim 9），合计 93 个，逐题归位 |
| 5 | 人工确认报告 | ✅ | 确认 id=1；回执含 report_core_hash / evidence_set_hash / policy，origin=`local_interactive_operator`；状态 `confirmed` |
| 6 | 确认后可作为制作合法入口 | ✅ | 确认前 `report_confirmation_required`；确认后 `require_confirmed_report` 返回绑定，`set_status('scripting')` 成功，审计写入 `confirmed_report` |

## 1. 两个真实选题

| 项目 | 选题 | 结果 |
| --- | --- | --- |
| 项目 1 | idea 9：AI 成本争议 / Oracle RPO 2024 vs 2026 口径 | 真实研究完成到证据阶段；24 次真实证据调用全部被 v3 契约拒绝，未生成报告 |
| 项目 2 | idea 1：claude-mem「声称 vs 证据」 | 计划 → 搜索 → 证据 → 报告 → 确认 → 进入 `scripting`，全链路通过 |

项目 2 的选题来自真实热点：GitHub `thedotmack/claude-mem`（10 万+ Stars），视频角度是「它声称做什么，又缺哪些证据」。

## 2. 第 1 步：真实研究（项目 2）

- 研究计划：DeepSeek `deepseek-flash`，输入 1,847 / 输出 1,205 Token，0.011829 元；5 个问题，关键词为原子词。
- 计划人工修订：清空日期过滤（避免把仓库页排除）与 `site:` override，保留原子关键词；保存为 v2 并确认（confirmation 5）。
- Tavily：5 次 `basic` 搜索 + 1 次批量提取，7 credits，全部成功；来源包括 GitHub 仓库页、README、NOTICE、Issue、第三方分析页。

## 3. 第 2 步：真实证据进入 v3 证据池

### 3.1 项目 2：通过

- `topic_analyses` 45：`schema_version=research-evidence-v3`、`prompt_version=research-evidence-prompt-v3`、`status=success`、`success_run_id=45`。
- 文档契约：`contract_version=research-evidence-v3`、`policy_version=quality-v3`、`input_manifest_hash=5cbeec42…`。
- 9 条证据、9 条引用（每条 1 个引用）；分类：**0 verified、3 opinion、6 unverified**；结构化缺口 75 个。
- 引用核验全部通过：`source[field][start:end] == quote`、`end-start == len(quote)`、`body_hash == sha256(text)`、`snapshot_hash == content_hash`、窗口/区域/字段与 manifest 一致、SQL 投影与 JSON 一致。
- 证据池哈希 `ee3506ab…` 与报告 `basis.evidence_set_hash` 一致。

分类偏低的原因是可解释的：模型按「拿不准就 unknown」的策略提交，6 条事实的 claim 字段为 unknown，被程序判为 `unverified`；3 条是项目自述（self-claim），判为 `opinion`。这正是 v3 的设计意图——**不因为来源域名或模型自述就升级等级**。

### 3.2 项目 1：被稳定拒绝（失败证据）

- 本次会话 24 次真实证据调用（analysis 19–36、38–43）**全部失败**，无任何部分结果落库；项目累计 33 次失败。
- 诊断错误分布：`schema` 6、`output_truncated` 4、`json_decode` 3、`ambiguous_quote` 3、`claim_support_mismatch` 2、`quote_not_visible` 2、`unsupported_period` 2、`unsupported_value` 1、`question_limit` 1。
- 典型原因：官方新闻稿正文长且样板句重复，同一引句出现在多个来源/窗口 → `ambiguous_quote`；模型把 claim 字段规范化（如 Oracle Corporation / billion）而非逐字复制 → `claim_support_mismatch`；FY/季度标签与引文不一致 → `unsupported_period`；输出接近 6000 Token 上限 → 截断。
- 期间也用 `deepseek-v4-pro` 试过 2 次（0.48 元），同样被拒。系统在全部失败中保持 **fail-closed**：没有写入任何不完整证据，也没有生成报告。

> 结论：v3 证据契约可以接受真实证据，但对**来源结构**和**模型逐字复制能力**非常敏感。项目 1 这类“长官方新闻稿 + 多份近似转载”的材料，当前 DeepSeek 无法稳定满足；项目 2 这类“短 README/仓库页”可以。

## 4. 第 3 步：报告生成、引用与分类

- 报告：`production_versions` id 10，`research-report-v3`，`validated_pending_confirmation`。
- 规模：5 个分题、9 条陈述、9 条引用、93 个缺口、2 条结论。
- 分类汇总：`verified=0`、`single_source=0`、`opinion=3`、`inference=0`、`disputed=0`、`unverified=6`、`gaps=93`。
- 自动核验（`logs/verify-v3/verify_report.py`，failures=0）：
  1. 题目集合与计划一致，每题恰好一次；
  2. 每条证据都进入对应分题，无遗漏、无跨题；
  3. 渲染分类 == 证据 `final_category` == 质量策略结果；
  4. 每条引用的 `source[field][start:end]`、`end-start`、`body_hash`、`snapshot_hash`、`url` 与保存来源逐项一致；
  5. 用当前证据池重新渲染，结果与保存的 `envelope` 完全一致（`verify_envelope`）；
  6. 正文数字全部来自 claim 或引用原文，无模型新增数字；
  7. 生产策略下 `verified` 恒为 0。

报告正文示例（程序渲染，不是模型自由文本）：

- `待验证信息：该来源的陈述含义仍待核实，不能视为确定事实。`（S32，Apache License 2.0 的 NOTICE 片段）
- `来源观点：来源陈述：entity=claude-mem；metric=mechanism；value=Persistent Context Across Sessions for Every Agent；basis=self-claim；speaker=project。`（S35，README 标题）

## 5. 第 4 步：研究缺口保留

- 证据池 75 个结构化缺口（`term_not_found` 46、`omitted_budget` 11、`context_incomplete` 8、`table_context_missing` 5、`metadata_missing` 1、`implementation_detail_missing` 1 等）。
- 报告在 75 个之外，由程序派生 18 个：`period_unknown` 9（时间性质未知）、`claim_incomplete` 9（原子缺少主体/指标/数值），合计 93 个。
- 逐项核验：报告的 `gap_id` 集合 == 证据池 mandatory gaps 集合；每个缺口只出现在对应问题下；结论中的 `gap_id` 均来自证据池；没有任何“已补齐”字段。
- 报告结论中也直接保留了缺口，例如：`研究缺口：压缩所用模型、存储位置、注入触发机制在可见官方窗口中无逐字说明。`

## 6. 第 5 步：人工确认

- 确认前状态：`validated_pending_confirmation`；`require_confirmed_report` 拒绝（`report_confirmation_required`）；`set_status('scripting')` 同样被拒。
- 人工审阅后，由本地交互会话签发一次性 `HumanConfirmationIntent`（绑定项目、报告版本、core/pool/policy hash、用途、session、nonce、10 分钟有效），再调用 `ReportService.confirm`。
- 结果：`research_report_confirmations` id=1，绑定 plan_confirmation_id=5、run_id=6、evidence_analysis_id=45；`report_confirmed_v3` 审计回执含：
  - `report_core_hash=be2ed532…`
  - `evidence_set_hash=ee3506ab…`
  - `policy_version=report-validation-v3`
  - `origin=local_interactive_operator`、`purpose=confirm_report`
- 状态变为 `confirmed`。

## 7. 第 6 步：确认后的制作准入

| 检查 | 结果 |
| --- | --- |
| 确认前 `require_confirmed_report` | 拒绝，代码 `report_confirmation_required` |
| 确认前 `set_status('scripting')` | 拒绝，代码 `report_confirmation_required` |
| 确认后 `require_confirmed_report` | 通过，返回 `{report_version_id:10, report_core_hash, evidence_set_hash, policy_version}` |
| 确认后 `set_status('scripting')` | 成功，项目状态 `scripting` |
| 状态变更审计 | `confirmed_report` 绑定报告版本 10、core hash、evidence set hash、policy |

门禁不是只看 `project.status` 或孤立确认行：它联合核对最新报告、严格 v3 证据池、规范正文、校验回执与确认回执。把项目状态直接改成 `scripting`、或伪造确认行，都不足以通过。

## 8. 费用与 credits

### 项目 2（成功链路）

| 阶段 | 尝试 | 失败 | 费用（元） |
| --- | --- | --- | --- |
| 研究计划 | 1 | 0 | 0.011829 |
| 证据整理 | 2 | 1（invalid JSON） | 0.067831 + 0.035427 |
| 研究报告 | 3 | 2（schema / truncated） | 0.130174 + 0.059094 |
| **合计** | **6** | **3** | **0.304355** |

Tavily：5 次搜索 + 1 次提取 = **7 credits**。

### 项目 1（失败证据）

- 本次会话 24 次证据调用全部失败：**1.769632 元**；Tavily run 4/5 共 **13 credits**。
- 项目历史累计模型费 2.368630 元（含上一轮 0.510557 元与 11-03 的计划/证据尝试）。

### 合计

- 本次会话模型费：0.304355 + 1.769632 = **2.073987 元**；Tavily **20 credits**（20 次计费调用）。
- 11 月（北京时间）累计 **2.764891 元 / 100 元**，剩余约 97.24 元；无“费用未知”记录，预占已全部结算。

## 9. 本次改动与测试

为让真实模型能稳定输出，本次修改了生产提示词（不改契约、不放宽校验）：

| 文件 | 改动 |
| --- | --- |
| `services/research/prompts.py` | `EVIDENCE_SYSTEM_V3`：期间上下文只能用正文窗口、字段完整性清单、摘要 ≤100 字、claim 必须逐字来自引文、优先整窗复制、拿不准用 unknown/`unverified`；`REPORT_SYSTEM_V3`：block_id 全报告唯一、blocks ≤4/结论 ≤2 |

- 全量测试：**674 passed，exit 0**（`logs/verify-v3/pytest-full.log`）。
- 数据库：`integrity_check=ok`、外键无错误、`user_version=6`。

## 10. 局限与建议

1. **证据质量偏保守**：成功的 9 条证据里 6 条是 unverified（claim 字段 unknown），报告只能写“待验证信息”。这是因为模型选择了保守输出；若要提升，需要让模型在不猜的前提下，把引文中确实存在的 entity/metric/value/unit 逐字填入 claim。
2. **结构敏感**：长官方新闻稿 + 多份近似转载会触发 `ambiguous_quote` 与 `claim_support_mismatch`。建议在来源层做“同文去重/主副来源标记”，或在选窗时避免把样板句同时暴露给多个问题。
3. **输出上限**：证据与报告都接近 6000 Token 上限；本次通过缩短摘要和限制 block 数规避。长期建议按任务配置 `AI_MAX_OUTPUT_TOKENS`。
4. **未验证**：页面人工点击的视觉检查、真实浏览器确认流程、以及项目 1 的报告/确认/门禁（因证据未入池而无法进入）。
5. **本地信任边界**：确认能力是本地单用户机制，不防任意 Python/SQL 管理员；本次未改变这一点。

## 11. 产物

| 路径 | 内容 |
| --- | --- |
| `logs/verify-v3/run.py` | 驱动脚本（真实服务层，支持 --project / --model） |
| `logs/verify-v3/run-log.jsonl` | 各步骤真实调用记录 |
| `logs/verify-v3/verify_evidence.py` | v3 证据池坐标/哈希/缺口核验 |
| `logs/verify-v3/verify_report.py` | 报告引用/分类/缺口核验 |
| `logs/verify-v3/report-v3.json` | 报告 v10 完整内容（basis/candidate/document/validation） |
| `logs/verify-v3/pytest-full.log` | 674 项全量测试 |
| `data/hotspots.sqlite3` | 项目 2：报告 10 已确认、状态 `scripting`；项目 1：研究仍停在证据阶段 |
