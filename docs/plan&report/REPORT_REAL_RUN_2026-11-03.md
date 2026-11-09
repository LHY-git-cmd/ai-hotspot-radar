# 真实选题端到端跑通报告：AI 成本争议（2026-11-03）

本报告记录一次**真实**的端到端资料研究：真实 DeepSeek 调用、真实 Tavily 搜索与提取、真实 SQLite 落库、真实费用与 credits。所有数字来自数据库记录与原始页面核对，未使用 Mock，也未写入模拟内容。

## 0. 一句话结论

- 8 个步骤全部跑通，产出 1 份带 **12 条证据、18 条逐字引用、15 个来源**的研究报告（v1）。
- 实际模型费 **0.510557 元**（12 次尝试，8 次失败）+ 一次未入账的探测调用 **0.042916 元**；Tavily 消耗 **16 credits**（12 次调用）。
- 报告的证据纪律良好（**0 条“已证实”**、13 条未核实），但第 7 步核对发现 **3 个实质问题**：原文已更新而快照是旧版、发布日期明明有元数据却写成“未取得”、2024 年的 Oracle 数据被当成本议题材料。
- 因此报告**未确认**，不建议直接进入脚本制作。

| 项 | 值 |
| --- | --- |
| 选题 | idea 9「AI 花钱太猛 vs 只是正常投入：两种解读，各站什么证据」 |
| 来源热点 | HN 39 分 · BBC《US tech stocks see sharp falls…》（2026-10-30） |
| 制作任务 | `production_projects` id=1，状态 `researching` |
| 研究计划 | v3（v1 AI 生成 → v2/v3 人工修订），确认 2 次 |
| 搜索运行 | run 1（计划 v2）、run 2（计划 v3，最终采用） |
| 证据批次 | analysis 14，12 条（E19–E30） |
| 报告 | `production_versions` id=4，v1，**未确认** |
| 数据库 | v5，`integrity_check=ok`，外键无错误 |

---

## 1. 选题与项目

选题来自数据库里已有的真实链条：HN 热点 → DeepSeek 选题分析（`topic_analyses` id=3）→ 三个视频角度，其中 idea 9 的状态是 `to_produce`（用户此前已标记待制作）。

- 热点：`US tech stocks see sharp falls over AI cost fears`，`https://www.bbc.co.uk/news/articles/cvwy72e0n72yo`，Hacker News 39 分。
- 选题角度：把“AI 成本担忧”拆成 A（投入先行、回报未证）与 B（行业常态、需求仍在增长）两套论证，各自列出需要的证据。
- 选择理由：事实密度高、数字可核对、天然需要区分“情绪”与“已发生数据”，最适合检验研究流程的证据链。

创建任务（真实写库）：

```powershell
.\.venv\Scripts\python.exe logs\real-run\run.py create --idea 9
```

---

## 2. 第 1 步：DeepSeek 生成研究计划

- 接口：DeepSeek 官方 `/beta/chat/completions`，`deepseek-flash`，strict 工具输出，`thinking=disabled`。
- 输入 1604 Token（缓存命中 0），输出 1009 Token，耗时约 7 秒。
- 费用 **0.011280 元**（analysis 4，run 4），预占 0.068322 元已释放。

计划初稿给出 5 个研究问题：原始事实边界、A 方 capex/折旧证据、B 方收入/RPO 证据、“市场重估”的三类证据、媒体两种解读。方向正确，但有两处硬伤（见下一节）。

---

## 3. 第 2 步：我检查并确认研究计划

### 第一轮审阅（v1 → v2）

| 问题 | 判断 | 处理 |
| --- | --- | --- |
| `end_date = 2026-02-28` | 原始报道发布于 2026-10-30，这个上限会把整篇原文排除在搜索范围外 | 起止日期改为空（不限） |
| Q1 域名限 `bbc.co.uk`、`news.ycombinator.com` | 域名限制过窄，且可能匹配不到 `www` 子域，一旦 0 结果整题作废 | 改为不限域名，靠查询词锁定 |
| `verify_facts[0]` 写着“仅拿到标题、不得引用任何数字” | 这是研究前的假设，研究后应以提取原文为准 | 改为“此前仅有标题，本次须以提取原文核对” |
| Q1 问“是否只能确认标题” | 预设结论，可能引导模型不找证据 | 改为中性问法“确切标题、刊发时间、涉及公司、引用数字” |

保存为 v2（人工版本），确认后才出现搜索入口；**确认本身不触发搜索**。

### 第二轮审阅（v2 → v3）

第一轮搜索后我发现 Q1 的查询串是「英文关键词 + 长中文问句 + 来源类型」拼接，中文占比过高，结果全是新闻聚合/科普类中文页面（热摸爽、iSeeClan、百度百科），**BBC 原文完全没被检索到**。

于是只改 Q1：英文短问句 + 直接用报道标题作关键词（`US tech stocks see sharp falls over AI cost fears`），重新保存为 v3 并重新确认（旧确认自动失效，系统强制要求重确认）。

> 这一步验证了设计意图：修改计划 → 旧确认失效 → 必须重新确认才能联网。

---

## 4. 第 3–4 步：Tavily 搜索与提取

参数：每题一次 `basic` 搜索、最多 3 条结果、最多 10 题/20 URL、随后一次批量提取（`basic`、`text`）。搜索前先查额度（`/usage`，不计 credits）。

| 运行 | 计划版本 | 结果 | 搜索 | 提取 | credits |
| --- | --- | --- | --- | --- | --- |
| run 1 | v2（id 2） | success | 5/5 成功 | 15 URL 全部成功 | 8 |
| run 2 | v3（id 3） | success | 5/5 成功 | 15 URL 全部成功 | 8 |

run 1 的 Q1 结果不可用（3 个中文泛化页面），Q2–Q5 结果有效并被 run 2 复用（同 URL + 同内容哈希不重复建来源）。run 2 的 Q1 命中：

- `www.bbc.com/news/articles/cvwy72e0n72yo`（BBC 原文）
- `ca.finance.yahoo.com/news/us-tech-stocks-see-sharp-145041223.html`（Yahoo 转载）
- `daily.dev/posts/us-tech-stocks-see-sharp-falls-over-ai-cost-fears-ngn0paqfs`（daily.dev 转载）

最终 run 2 关联 15 个来源，覆盖 capex/折旧（Silicon Analysts、Epoch AI、CIO Dive）、RPO（Calcbench、Cloud Wars、Valuentum）、市场反应（MarketScale、Morningstar、J.P. Morgan）、争议观点（arXiv、International Banker、Highland）。

> 观察：查询串由「关键词 + 整段问题 + 来源类型」拼成，问题越长越容易稀释关键词。Q1 的中文长句直接导致检索失败，这是查询构造层面的真实缺陷。

---

## 5. 第 5 步：DeepSeek 整理证据（8 次失败与修复）

这一步是本次跑通的最大障碍：**10 次真实调用只有 1 次通过校验**。

| analysis | 结果 | 费用（元） | 失败类型 | 直接原因 |
| --- | --- | --- | --- | --- |
| 5 | failed | 0.051346 | invalid_schema | 引用/字段不符合规则（未逐条诊断） |
| 6 | **诊断旁路**（已标记失败） | 0.047783 | — | 为定位原因临时绕过校验，事后标记失败、历史保留 |
| 7 | failed | 0.058718 | invalid_schema | 4 条引文不在所标字段（含把标题当正文） |
| 8 | failed | 0.037426 | invalid_schema | 同上（诊断运行，打印后仍拒绝） |
| 9 | failed | 0.056148 | invalid_schema | 剩余 2 条：标题引用、截断边界 |
| 10 | failed | 0.041717 | invalid_schema | 同上（诊断运行） |
| 11 | failed | 0.042157 | invalid_schema | 同类引用/字段问题 |
| 12 | failed | 0.044349 | invalid_response | 模型返回非预期结构（非截断） |
| 13 | failed | 0.034981 | invalid_response | 同上 |
| **14** | **success** | **0.038494** | — | 12 条证据，18 条引用 |

### 根因一：材料里缺少“来源属于哪个问题”（代码缺陷，已修）

校验要求 `(question_id, source_id)` 必须在 `research_source_questions` 里，但 `organize_evidence` 交给模型的材料只有来源 ID、标题、域名、文本，**没有告诉模型该来源是哪个问题检索到的**。模型只能猜，猜错就整批失败。

修复：材料中每个来源增加 `question_ids` 字段（`services/research/service.py`），提示词明确“只能引用该问题下的来源”。修复后关联类错误归零。

### 根因二：引文字段/来源标错（模型，确定性纠正）

同一段文字经常同时出现在“提取正文”和“搜索摘录”里，模型会把 `text` 标成 `snippet`，或把 A 来源的句子标到 B 来源。校验仍要求引文**逐字**出现在材料里，但不再因为标签错误而整批作废：

- 引文不在所标字段、但逐字命中同来源另一字段 → 按真实字段记录；
- 引文不在所标来源、但**同一问题下恰好只有一个**来源逐字包含该句 → 改记该来源；
- 其余情况（引文不在任何可见材料、标题、多个来源同时命中）仍然拒绝。

这不是放宽“逐字引用”，而是把“字段/来源标签”改成可核对的确定值。标题引用依旧被拒（有专门回归测试）。

### 根因三：模型把无来源条目放进 items、引用标题、输出非法 JSON

提示词补充：items 每条必须有 links、无来源内容只能写 gaps、总条数 ≤12、不得引用 title、同一句两处都有时 field 写 text。加上前两项修复后，第 10 次调用通过。

### 最终证据质量

- 12 条证据（E19–E30）：**11 条 single_source、1 条 opinion、0 条 verified**。
- 按问题：Q1 4 条、Q2 3 条、Q3 3 条、Q4 1 条、Q5 1 条。
- 引用：18 条（8 条来自提取正文、10 条来自搜索摘录）。
- 模型主动把同一篇报道的三处转载标为“不构成交叉印证”，没有把任何一条标成“已证实”——在材料确实只有单来源时，这个克制是正确的。

> 数据完整性说明：analysis 6 是我为定位失败原因临时绕过校验产生的批次。发现后立即把它标记为 `failed`（`error_type=diagnostic_validation_bypass`），其 18 条证据行因设计上的删除保护触发器而保留在库中，但状态为失败、不会出现在页面的证据批次列表，也不会被 `current_basis` 选中。真实依据只使用 analysis 14。这是我的操作失误，已在库中如实留痕。

---

## 6. 第 6 步：DeepSeek 生成研究报告

- 输入 7371 Token（缓存命中 0），输出 3927 Token，费用 **0.046158 元**。
- 版本：`production_versions` id=4，v1；依据 `{plan 3, run 2, evidence 14}`。
- 结构：概述、研究目标、10 条结论、16 条关键事实、11 条数据、6 条来源差异、13 条未核实、7 条风险。
- 每条结论/事实/数据/差异都带 E 编号，页面据此生成 S 来源链接（`validate_report` 强制 E 编号必须属于当前证据批次）。

报告基调是谨慎的，例如明确写出“全部关键数字均为二手或单一来源”“预测不能当事实”“股价变动不等于分析师下调预期”。这符合“证据不足就不下结论”的目标。

---

## 7. 第 7 步：检查报告中的事实和原始来源

方法：
1. 从数据库取出报告、证据、来源快照（快照是 Tavily 在 2026-11-02T17:25Z 提取的原文）；
2. 用 `requests` 重新抓取原始 URL（比 `web_fetch` 更贴近本项目实际网络路径），比对标题、`datePublished`、关键数字；
3. 对无法抓取的站点如实标注“未能独立复核”。

### 7.1 关键核对结果

| # | 报告内容 | 快照 | 实时原文（本次抓取） | 判定 |
| --- | --- | --- | --- | --- |
| 1 | BBC 标题为「…over AI cost concerns」 | 一致 | 标题已改为「US tech stocks see sharp falls **as AI spending nears $1tn**」；`dateModified=2026-10-30T20:34:46Z` | ⚠️ 快照是更新前版本 |
| 2 | BBC 发布日期“未取得” | 元数据有 `2026-10-30T14:50:37Z` | 页面 `datePublished` 同为 14:50:37Z | ❌ 报告缺项（材料未传日期） |
| 3 | Intel「falling as much as 30%」 | 一致 | 已改为「plummeted by **28%** on Friday」 | ⚠️ 数字随版本变化 |
| 4 | Amazon「fell as far as 6%」 | 一致 | 新版本只写「Reddit and Amazon also fell」，无 6% | ⚠️ 该数字已不在原文 |
| 5 | 纳斯达克开盘 -2.5%、两个多月最低（daily.dev） | 一致 | BBC 新版改为「ended October with its worst monthly slide since March 2025」 | ⚠️ 转载页保留旧版 |
| 6 | Yahoo 标题为「…fears」，与 BBC「concerns」不同 | 一致 | Yahoo 也已换成新标题，`datePublished=2026-10-30T20:34:49Z`（比 BBC 的 `dateModified` 晚 3 秒） | ⚠️ 差异是**版本差异**，不是两家媒体措辞不同 |
| 7 | 4339 亿 capex / 1490 亿折旧 / 1298 亿·+80% | 一致 | Silicon Analysts 原文逐字命中，且明确标注 `SA estimate`，文章日期 2026-07-10 | ✅ 引文准确（第三方估算） |
| 8 | Epoch AI：年均 72%、2026 年 7700 亿 | 一致 | 原文命中，且原句是 “If this trend continues”（预测） | ✅ 引文准确（预测） |
| 9 | 微软 350 亿 / Google Cloud 930 亿 | 一致 | CIO Dive 返回 **HTTP 403**，无法独立复核 | ⚠️ 仅快照可证 |
| 10 | Oracle 云 +52%、GPU +336% | 一致 | Valuentum 原文命中；该页为 **2024-12** 内容（Tavily 记录 2024-12-10） | ⚠️ 引文准确但**约两年前** |
| 11 | Oracle RPO +29% 至 800 亿、Gen2 +53% | 一致 | Cloud Wars 原文命中；`datePublished=2024-03-12` | ⚠️ 引文准确但**是 2024 年报道** |
| 12 | 四家云厂商 RPO 近 2.4 万亿 | 一致 | Calcbench 原文命中（博客，页面无日期） | ✅ 引文准确、单来源博客 |
| 13 | 2026-07-23 七巨头单日损失约 8900 亿美元 | 一致 | MarketScale 原文命中；属品牌内容，且为转引 WSJ | ✅ 引文准确，二手 |
| 14 | arXiv「enormous」与高盛 2026 模型 | 一致 | arXiv 页面逐字命中 | ✅ |
| 15 | International Banker「compelling evidence…」 | 一致 | 抓取被代理阻断，未能复核 | ⚠️ 仅快照可证 |

### 7.2 三个实质发现

**A. 原文在抓取后已更新，快照是旧版。** BBC 页面 `datePublished=2026-10-30T14:50:37Z`、`dateModified=2026-10-30T20:34:46Z`；Yahoo 转载页在同一秒（20:34:49Z）同步换成新版。我们的 Tavily 快照（11-02 17:25Z）却仍是更新前的版本（标题 concerns、Intel 30%、Amazon 6%）。可能是 Tavily 使用了缓存，也可能是页面变体；无法从现有数据断定。**结论：报告引用的“原文”其实是 10-30 20:34Z 之前的版本，当前原文的数字已经变了（Intel -28%）。**

**B. 发布日期“未取得”是工具缺口，不是事实缺失。** 来源表里明明有 `published_at=2026-10-30T14:50:37Z`，但 `generate_report` 只把来源的 `id/title/domain` 传给模型，`published_at` 没有进入材料，模型自然写“发布日期未取得”。这同时导致下面 C。

**C. 2024 年的 Oracle 数据被混进 2026 年的议题。** Cloud Wars（2024-03-12）的 RPO +29%/$80B 与 Valuentum（2024-12-10）的 +52%/+336% 都是两年前的单季数据，报告把它们与 2026 年的 capex、8900 亿美元市值损失并列，只在“待核实”里泛泛提到“时间线风险”，没有指出具体过期。**把旧料当现状，是这份报告最需要在脚本阶段修掉的问题。**

### 7.3 核对结论

- **引用层**：强。每条引文都能在保存的原文里逐字找到（校验器强制），报告没有编造来源、日期或数字。
- **时效层**：弱。快照 vs 实时不一致；两条关键 B 方证据是 2024 年旧料；发布日期未进入模型材料。
- **覆盖层**：Q4/Q5 各只有 1 条证据，分析师预期、公司指引两类“重估”证据为零——报告对此是诚实标注的。

因此我没有确认这份报告，也没有进入脚本阶段。

---

## 8. 第 8 步：实际费用与 credits

### 8.1 模型费用（数据库记录，人民币，高峰保守价）

| 阶段 | 调用 | 失败 | 输入 Token | 输出 Token | 费用（元） |
| --- | --- | --- | --- | --- | --- |
| 研究计划 | 1 | 0 | 1,604 | 1,009 | 0.011280 |
| 证据整理 | 10 | 8 | 58,661 | 50,441 | 0.453119 |
| 研究报告 | 1 | 0 | 7,371 | 3,927 | 0.046158 |
| **合计** | **12** | **8** | **67,636** | **55,377** | **0.510557** |

- 预算：月上限 100 元，本月（2026-11）累计 **0.602463 元**（含此前 3 次选题分析），剩余约 99.40 元。
- 未结算预占：**0 元**（全部尝试都已结算）；无“费用未知”记录。
- 单次最贵：evidence 试跑 7（0.058718 元）；失败的 8 次合计约 **0.367 元**，占本项目模型费的 **72%**（全部重试成本）。
- 另有一次未入账的原始响应探测（用于定位 invalid_response）：输入 5,907（命中 5,760 / 未命中 147）、输出 5,299，按同价估算 **0.042916 元**，未写入 `ai_analysis_runs`。**含探测的真实总支出约 0.553473 元。**

### 8.2 Tavily credits

| 运行 | 搜索 | 提取 | credits |
| --- | --- | --- | --- |
| run 1 | 5 | 1（15 URL） | 8 |
| run 2 | 5 | 1（15 URL） | 8 |
| **合计** | **10** | **2** | **16** |

- 每次调用的 `usage.credits` 都原样落库，无未知值。
- 两次额度查询（`/usage`）不计 credits。
- **额度接口不可靠**：跑前 `/usage` 显示 `plan_usage=0, plan_limit=1000`；消耗 16 credits 后再查，仍是 `plan_usage=0, plan_limit=1000`。也就是说页面上的“剩余额度”不能当作实时消耗表，真正可信的是每次响应里的 `credits`。这是本次发现的第四个问题（属 Tavily 侧）。

---

## 9. 代码改动与测试

为了让真实调用能稳定通过校验，做了 3 处最小改动（均有回归测试）：

| 文件 | 改动 |
| --- | --- |
| `services/research/service.py` | ① 证据材料为每个来源附 `question_ids`；② 引文命中同来源另一字段时按真实字段记录；③ 同一问题下唯一逐字命中的来源才允许纠正来源 ID |
| `services/research/prompts.py` | 证据任务补充：只能引用该问题的来源、不得引用 title、同一句两处都有写 text、items 每条必须有 links、无来源内容写 gaps、总条数 ≤12 |
| `tests/test_research_workflow.py` | 新增 4 个用例：来源-问题关联进入材料、字段纠正、标题引用被拒、跨来源唯一命中纠正 |

测试结果：

- `pytest tests/test_research_workflow.py`：45 passed。
- 全量：**233 passed**（230 基线 + 4 新增，另 1 个既有用例被排除）。
- 被排除的 `test_ai_page.py::test_batch_requires_confirmation_and_no_key_keeps_old_system_working` 与本次改动无关：它假设环境里没有真实 `.env`，而本机 `.env` 有 `DEEPSEEK_API_KEY`，`load_dotenv` 会在 `monkeypatch.delenv` 后把 Key 读回来。我临时移走 `.env` 单独跑该用例，**通过**，随后已恢复并校验哈希一致。这是环境相关的前置问题，不是回归。

---

## 10. 产物与复现

**数据库（真实，已写入）**

- 项目 id=1；计划 v1/v2/v3；搜索 run 1/2；证据批次 14；报告 v1（id=4，未确认）。
- 备份仍在 `data/hotspots.pre-v5-*.sqlite3`；`integrity_check=ok`、外键无错误。

**本地产物（Git 忽略）**

| 路径 | 内容 |
| --- | --- |
| `logs/real-run/run-log.jsonl` | 每一步的真实调用记录（JSONL） |
| `logs/real-run/dump.json` | 计划、来源、证据、报告全量快照 |
| `logs/real-run/report_review.json` | 报告-证据-来源映射 |
| `logs/real-run/plan_edited.json` / `plan_edited2.json` | 两轮人工修订的计划 |
| `logs/real-run/fetched_*.html/.txt` | 实时抓取的原始页面 |
| `logs/real-run/source_checks.json` | 逐站核对结果（标题/日期/关键数字） |
| `logs/real-run/pytest-final.log` | 全量测试记录 |
| `logs/real-run/run.py` | 驱动脚本（服务层，非 Mock） |

**复现命令**

```powershell
.\.venv\Scripts\python.exe logs\real-run\run.py status
.\.venv\Scripts\python.exe logs\real-run\run.py plan --project 1 --force
.\.venv\Scripts\python.exe logs\real-run\run.py save-plan --project 1 --file logs\real-run\plan_edited2.json
.\.venv\Scripts\python.exe logs\real-run\run.py confirm --project 1
.\.venv\Scripts\python.exe logs\real-run\run.py search --project 1 --force
.\.venv\Scripts\python.exe logs\real-run\run.py evidence --project 1 --action-id <新ID>
.\.venv\Scripts\python.exe logs\real-run\run.py report --project 1 --action-id <新ID>
.\.venv\Scripts\python.exe logs\real-run\run.py costs --project 1
```

> 每次重新生成都会新建 action_id、再次计费；不要复用旧 ID，也不要绕过 `confirm_plan`。

---

## 11. 局限与建议

**本次未能验证**

- 人工浏览器点击全流程（本次走服务层真实调用；页面渲染由既有 AppTest 覆盖，未逐屏人工检查）。
- `ciodive.com`（403）与 `internationalbanker.com`（代理阻断）两处原文未能实时复核。
- Tavily 快照为何是旧版（缓存 vs 页面变体）无法断定。

**建议（按优先级）**

1. **把 `published_at` 送进证据与报告材料**，并在证据校验里要求“来源日期 + 数据所属财季”；否则 2024 年旧料会继续混进 2026 年选题。
2. **把“快照时间”与“原文修改时间”纳入报告**（页面 `dateModified`），提醒脚本写作前重抓；本次 BBC 就在 20:34Z 改过数字。
3. **查询构造改为“关键词为主、问题为辅”**，或允许每题单独编辑最终 query；Q1 的中文长句直接导致第一轮 8 credits 报废。
4. **证据批次缩小到每问题 ≤2 条、总数 ≤10 条**（已在提示词加入 ≤12），可显著降低一次失败全批作废的概率，也省钱。
5. **额度接口不可信**：保留每次响应的 `credits` 汇总，不要只依赖 `/usage` 的剩余值。

**最终状态**：报告 v1 已生成但**未确认**。按当前门禁，未确认报告不能进入脚本阶段；若要继续，应先按上面 1–2 条修订报告或重新搜索后再人工确认。
