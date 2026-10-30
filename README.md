# ai-hotspot-radar · AI 热点雷达

个人使用的 AI 选题候选收集工具。第一期实现公开数据采集、规范化去重、SQLite 历史存储与中文 Streamlit 展示。

## 环境与安装

已在 Windows 11、Python 3.13.12 上安装并运行。直接依赖固定为 Streamlit 1.66.1、requests 2.34.2、python-dotenv 1.2.4、pytest 9.2.0；SQLite 使用标准库。

在本项目目录打开 PowerShell，执行：

```powershell
# 进入项目根目录。
Set-Location 'E:\one\ai-hotspot-radar'

# 首次配置时创建独立虚拟环境；已有 .venv 可跳过。
py -3.13 -m venv .venv

# 仅向项目虚拟环境安装依赖，不修改全局 Python。
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 可选：仅在 .env 不存在时复制配置示例，避免覆盖已有密钥。
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
```

无需激活虚拟环境，直接使用其中的解释器即可，避免 PowerShell 执行策略影响。其他操作系统可将解释器路径换成 `.venv/bin/python`。

## 配置

不创建 `.env` 也可以运行。支持两个环境变量；系统环境变量优先于 `.env`。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `GITHUB_TOKEN` | 空 | 可选，从环境读取，不写入代码或数据库；无效 Token 会导致 GitHub 认证失败 |
| `AI_RADAR_DB_PATH` | `data/hotspots.sqlite3` | 相对路径以项目根目录为基准，也支持绝对路径 |

数据库及其父目录在首次启动时自动创建，历史数据不会因网页刷新或服务重启而删除。实际 `.env`、数据库、虚拟环境和日志均已加入 `.gitignore`。

## 启动与使用

```powershell
# 在本机启动网页；关闭匿名使用统计，日志默认输出到当前终端。
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

浏览器打开 [AI 热点雷达](http://127.0.0.1:8501)。终端按 `Ctrl+C` 停止服务。

1. 页面先展示 SQLite 中的历史记录；空数据库会显示提示，不会自动请求 API。
2. 点击“手动刷新”采集两个来源，页面分别显示新增、更新、去重跳过及错误。
3. 使用关键词搜索标题、摘要或链接，按来源筛选；列表每页最多 20 条，超过后可切换页码。
4. 点击“打开原始链接”访问来源提供的页面；没有外链的 HN 帖子打开其原讨论。

网页展示标题、来源、类别、摘要、发布时间、首次采集时间和来源专属热度。时间均为 UTC，缺失字段显示“暂无”，不会使用虚构指标补齐。

## 采集口径

| 来源 | 官方入口与范围 | 原始指标 | 时间字段 |
| --- | --- | --- | --- |
| GitHub | [仓库搜索 API](https://docs.github.com/en/rest/search/search#search-repositories)；`topic:artificial-intelligence pushed:>=最近7天 archived:false`，按 Stars 降序取前 30 条 | `stargazers_count`，累计 Stars | `created_at`，仓库创建时间，可能远早于 7 天 |
| Hacker News | [官方 Firebase API](https://github.com/HackerNews/API)；热门列表前 60 条，按标题和正文中的 AI 关键词筛选，排除已删除、失效与超过 7 天的帖子 | `score`，HN 积分 | `time`，帖子发布时间；缺失时保留为空并警告 |

HN 关键词包括 AI、LLM、GPT、Claude、Qwen、Ollama、人工智能、大模型等；英文缩写使用单词边界，避免将 `email`、`railway` 误判为 AI。样本和关键词筛选会有遗漏或误匹配，范围不限于新发布的产品。

GitHub Stars 不是最近的增长量，HN 积分也不与 Stars 合并或比较。网页按发布时间倒序，时间未知的记录放在最后。这是候选信息清单，尚未计算趋势、增长率或统一热点排名。

请求使用 5 秒连接超时、15 秒单次读取超时；HN 最多 6 个并发详情请求。每次刷新 GitHub 使用 1 次搜索请求，HN 最多 61 次请求。不会对限流自动重试，也不会绕过登录、验证码或其他访问限制。

## 存储与去重

SQLite 表 `hotspots` 保存 `id`、`title`、`url`、`source`、`summary`、`published_at`、`collected_at`、`score`、`category`，并保存内部去重键和搜索文本。`id` 由数据库生成，可选字段允许为空。

- URL：规范化主机和默认端口，删除片段、`utm_*`、`fbclid`、`gclid` 等明确跟踪参数。保留协议、路径大小写、尾斜线、业务参数及同名参数顺序，避免误合并。
- 标题：Unicode NFKC 规范化、大小写折叠、压缩空白。
- 标题或规范化 URL 任一相同即视为重复，数据库对两个键分别建立唯一约束。
- 同来源、同 URL 再次采集时更新标题、摘要、发布时间及指标，保留首次采集时间和首个原始链接。指标缺失时保存为空。
- 不同链接但同标题、跨来源重复，或一次更新同时命中不同记录时，跳过新记录并保留首条。因此同一链接可能只出现在一个来源筛选中，不会将 HN 积分写进 GitHub Stars。
- 每个来源单独事务保存；某来源请求或保存失败时，其他来源继续处理。HN 单条详情失败也会尽量保存其余帖子。

## 目录与文件

```text
app.py                         中文 Streamlit 页面
config.py                      环境变量及 .env 配置
models.py                      统一记录、时间处理和结果模型
collectors/__init__.py          采集模块说明
collectors/http.py              HTTP 请求及安全错误提示
collectors/github.py            GitHub 官方仓库搜索
collectors/hacker_news.py       HN 热门样本筛选
services/__init__.py            服务模块说明
services/normalization.py      URL、标题及 HTML 文本规范化
services/refresh.py            来源故障隔离及刷新统计
database/__init__.py            数据库模块说明
database/store.py               SQLite 保存、更新、查询和分页
tests/test_normalization.py    去重键与纯文本处理测试
tests/test_store.py            持久化、唯一约束、更新及搜索测试
tests/test_collectors.py       API 映射、缺失字段和失败测试
tests/test_refresh.py          来源故障隔离测试
tests/test_app.py              Streamlit 页面及交互测试
requirements.txt               固定直接依赖版本
pytest.ini                     测试入口配置
.env.example                   无真实密钥的配置示例
.gitignore                     排除本地数据、密钥与生成文件
PLAN.md                        已确认的实施计划及完成状态
README.md                      配置、运行、数据口径与验证说明
```

运行生成的 `.venv/`、`data/`、`logs/` 不提交。无需额外 API 服务、ORM、消息队列或其他数据库。

## 运行测试

```powershell
# 运行全部自动化测试；默认使用简洁输出。
.\.venv\Scripts\python.exe -m pytest

# 可选：只检查虚拟环境中的依赖冲突，不安装或更新依赖。
.\.venv\Scripts\python.exe -m pip check
```

自动化测试用临时 SQLite 数据库和模拟 HTTP，保证无网也能运行，不会写入真实热点数据库。网页测试使用 Streamlit 官方 `AppTest`。

## 本次验证结果

2026-10-31（北京时间）已完成：

- TDD：实现前 37 项测试失败；实现后全量 **37 passed**。
- Python 3.13.12 虚拟环境依赖安装成功，`pip check` 未发现冲突。
- Hacker News 实际取得 9 条匹配记录并存入默认 SQLite 数据库；1 条详情网络请求失败，其他记录继续处理。
- 重复写入同一真实采集快照：新增 0 条、更新 9 条，总数仍为 9；关闭连接后重开数据库数据仍在。
- Streamlit 本机服务启动成功：首页 HTTP 200，`/_stcore/health` 返回 HTTP 200 和 `ok`。
- 使用真实 SQLite 数据运行页面测试，成功渲染 9 条记录和 9 个原始链接，无页面异常。
- 自动化验证了来源故障隔离、缺失值展示、搜索、来源筛选、手动刷新和原始链接 URL。

尚未完成的验证：

- **GitHub 真实端到端采集**：环境检查时公开 API 可达，随后使用应用采集器联调两次均请求超时，未取得 GitHub 真实记录。字段映射、认证、限流、超时及格式错误的模拟测试已通过；需要网络恢复后点击“手动刷新”再验证真实采集。
- **完整人工浏览器操作和视觉检查**：已验证真实 HTTP 服务与 AppTest 交互，尚未人工逐项点击、检查不同屏幕尺寸或打开全部外部页面。

详细本地记录位于 `logs/pytest-red.log`、`logs/pytest-full.log`、`logs/live-check.json`、`logs/github-check.json`、`logs/streamlit.log`；这些文件不进入 Git。后续刷新会改变数据数量，以上是本次验证快照。

## 常见问题

**GitHub 超时、无法连接或认证失败**：检查网络、代理和 `.env` 的 Token；Token 可留空。认证失败时修正或移除无效 Token。应用会提示错误，并继续处理 HN。不要关闭证书校验来规避网络错误。

**API 提示限流**：遵循页面中的等待提示稍后再刷新，避免连续点击。[GitHub 搜索限流文档](https://docs.github.com/en/rest/search/search#rate-limit)说明了搜索配额；可选 Token 需要配置后才会随请求发送。

**本次没有匹配内容**：HN 只检查前 60 条热门帖，GitHub 只检查指定主题。零匹配可能是正常采样结果；历史数据仍保留。检查来源状态，区分没有匹配与采集失败。

**数据库无法打开或锁定**：检查 `AI_RADAR_DB_PATH` 是否指向文件、父目录是否可写，以及磁盘空间。数据库连接会等待锁最多 10 秒；请避免其他程序长时间占用写事务。修复后重新运行页面。

**8501 端口被占用**：启动命令改用 `--server.port 8502`，然后访问对应地址。不要为此停止不相关的程序。

**服务重启后数据不见了**：核对是否改变了 `AI_RADAR_DB_PATH`。相对路径固定以项目根目录为基准；不同数据库路径保存不同历史。

**想从零开始收集**：先停止服务并备份数据库，再将 `AI_RADAR_DB_PATH` 指向新的文件；应用不会自动删除旧库。

第一期没有定时采集、AI 摘要、趋势分析、登录或内容发布功能。
