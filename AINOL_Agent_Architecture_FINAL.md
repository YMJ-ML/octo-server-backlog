# octo-server 产品管家 Agent —— 架构设计 v5（考试流程优化最终版）

> 适用场景：AINOL 延期考试。  
> 本版是在 9/10 代码拆分基础上，结合 9/11 与 9/14 讨论结果，对原有 GitHub Backlog + Octo 群通知流程做优化；**不是新建系统**。

---

## 0. 三个核心前提

1. **目标仓库只读**：`Mininglamp-OSS/octo-server` 只能读取源码，不允许写入。
2. **Backlog 仓库可写**：考试需求池仓库 `YMJ-ML/octo-server-backlog` 用于 issue、label、评论和流程状态管理。
3. **Cron 自驱闭环**：Agent 每 5 分钟轮询 GitHub，不依赖人工通知；考官在 GitHub 上打标签、评论、关单、reopen 等操作后，Agent 自动识别并推进下一步。

---

## 1. Agent 角色设计

考试中使用 3 个 Bot/Agent，各自负责清晰边界：

| Agent | 主要职责 | 发言场景 |
|---|---|---|
| `octo产品管家` | 轮询 GitHub、识别新 issue、分类、打标签、处理 question、发考试群通知 | 新 issue 认领、问题回答、状态流转通知、异常提醒 |
| `octo PRD` | 根据 feature/复杂 bug 生成 PRD | 在 issue 评论区输出 PRD 草稿 |
| `octo Review` | 自审 PRD，判断是否满足规范 | 审核通过/不通过后打标签、评论原因 |

> 群消息必须通过 Octo Bot API 正确构建 `mention.entities`，确保 @ 主考/相关人蓝色高亮。

---

## 2. 标签体系（最终版）

### 2.1 类型标签

| 标签 | 含义 | 谁打 |
|---|---|---|
| `type/feature` | 功能需求 / 产品需求 | Agent 自动打，考官可改 |
| `type/bug` | 缺陷 / 异常 / 故障 | Agent 自动打，考官可改 |
| `type/question` | 产品/代码/流程问答 | Agent 自动打，考官可改 |

### 2.2 优先级标签

| 标签 | 含义 | 触发逻辑 |
|---|---|---|
| `priority/P0` | 紧急/阻塞/严重事故 | 标题或正文含 urgent、critical、宕机、阻塞、严重等 |
| `priority/P1` | 高优 | 重要、尽快、高优等 |
| `priority/P2` | 默认中优 | 默认值 |
| `priority/P3` | 低优 | 明确低优/可排期 |

> 如仓库里已存在 `P0/P1/P2` 旧标签，代码可兼容读取；最终架构建议统一为 `priority/P0-P3`。

### 2.3 模块标签

| 标签格式 | 含义 |
|---|---|
| `module/bot` | Bot / Agent / app_bot / botfather 相关 |
| `module/api` | Bot API / HTTP API / 错误码相关 |
| `module/auth` | token、cookie、鉴权、权限相关 |
| `module/im` | WuKongIM、消息通道、IM 控制面相关 |
| `module/config` | 配置、部署、环境变量相关 |
| `module/storage` | 数据库、Redis、对象存储相关 |
| `module/build` | 构建、发布、Docker、Makefile 相关 |
| `module/unknown` | 无法稳定判断模块 |

### 2.4 流程状态标签

| 标签 | 含义 | 使用场景 |
|---|---|---|
| `confirmed` | 已确认是有效 bug/需求 | bug 分支初始确认 |
| `queue/simple` | 简单 bug，排队修复 | 简单 bug 不走 PRD |
| `prd/draft` | PRD 草稿已生成 | PRD Agent 输出后 |
| `prd/reviewed` | PRD 已通过 AI 自审 | Review Agent 审核通过 |
| `revising` | 正在根据退回意见修改 | 考官打回后 |
| `designed` | 考官确认设计通过 | 考官决策标签 |
| `in_progress` | 已进入开发/修复阶段 | designed 后进入执行阶段 |
| `done` | 已完成，待验收或已验收 | 开发完成/关单前后 |
| `answered` | question 已回答 | 问答分支 |
| `duplicate` | 重复 issue | 考官决策标签 |
| `wontfix` | 不处理/不修复 | 考官决策标签 |

### 2.5 打回标签

| 标签 | 含义 |
|---|---|
| `rejected/结构不完整` | PRD 七板块缺失 |
| `rejected/包含实现细节` | 写了 How，不符合 What not How |
| `rejected/验收标准不可测` | 验收标准不是用户可感知结果 |
| `rejected/逻辑矛盾` | 背景、目标、验收标准之间矛盾 |
| `rejected/模块错误` | 涉及模块与知识库不一致 |
| `rejected/自定义原因` | 考官自定义打回原因 |

> 已废弃：`needs-analysis`。新 issue 不再进入“待分析”状态，而是由 Agent 自动分类并立即进入对应分支。

---

## 3. 整体流程图

```text
新 Issue 创建
  ↓
Cron 轮询发现新 issue
  ↓
octo产品管家自动分类：type + priority + module
  ↓
按 type 分三条分支

┌──────────────────────┬──────────────────────┬──────────────────────┐
│ type/feature          │ type/bug              │ type/question         │
│ 功能/需求              │ 缺陷/异常              │ 问答                  │
├──────────────────────┼──────────────────────┼──────────────────────┤
│ 自动生成 PRD           │ confirmed             │ 查知识库/源码回答       │
│ PRD 自审               │ 判断简单/复杂           │ 评论区存档             │
│ 通过后等考官 designed  │ 简单：queue/simple     │ 考试群自然语言回答       │
│ designed→in_progress  │ 复杂：转 feature PRD   │ answered              │
│ done/close 完成通知    │ done/close 完成通知     │ 确认/超时/转需求或bug    │
└──────────────────────┴──────────────────────┴──────────────────────┘
```

---

## 4. 分支流程设计

## 4.1 新 issue 统一入口

### 触发条件

GitHub Backlog 仓库出现新 issue。

### Agent 动作

1. 读取 issue 标题、正文、已有标签。
2. 自动判断：
   - `type/feature` / `type/bug` / `type/question`
   - `priority/P0-P3`
   - `module/xxx`
3. 给 issue 打上分类标签。
4. 在 issue 评论区写认领评论，说明已进入哪条流程。
5. 默认**不在考试群通知**，避免新 issue 太多刷屏；但 `priority/P0` 必须考试群提醒。

---

## 4.2 Feature / 需求分支

### 流程

```text
type/feature
  ↓
octo PRD 自动生成 PRD
  ↓
打 prd/draft，评论 PRD 内容
  ↓
octo Review 自审
  ↓
通过：打 prd/reviewed，考试群 @主考 审核
不通过：打 rejected/xxx + revising，自动修改后再次自审（无限循环，不设次数上限）
  ↓
考官审核
  ↓
通过：考官打 designed
  ↓
Agent 自动进入 in_progress，并考试群通知进入开发/排期
  ↓
开发完成：打 done 或关单
  ↓
Agent 考试群通知完成/验收结果
```

### PRD 规范：只写 What，不写 How

PRD 必须包含 7 个板块：

1. 需求背景
2. 用户场景
3. 需求目标
4. 验收标准
5. 优先级
6. 涉及模块
7. 补充说明

### 验收标准要求

验收标准必须是**用户可感知结果**，不能写成技术实现细节。

错误示例：
- “接口返回 200”
- “数据库字段成功更新”
- “调用某某函数”

正确示例：
- “用户发送消息后，能在 3 秒内看到机器人回复”
- “当 token 失效时，页面提示用户重新登录”

---

## 4.3 Bug 分支

### 流程

```text
type/bug
  ↓
Agent 打 confirmed
  ↓
判断复杂度
  ↓
简单 bug：打 queue/simple，进入修复队列，可后续打 in_progress/done
复杂 bug：转 type/feature，进入 PRD 分支
```

### 简单 bug 判断

满足以下情况之一，可视为简单 bug：

- 文案错误
- 配置缺失
- 明确的小范围异常
- 不涉及产品流程改动
- 不需要重新定义用户体验或验收逻辑

### 复杂 bug 判断

满足以下情况之一，转 feature/PRD：

- 涉及用户路径变化
- 涉及权限、消息链路、Bot 身份等核心机制
- 需要设计新的交互规则
- 影响范围不清，需要先定义验收标准

---

## 4.4 Question / 问答分支

### 流程

```text
type/question
  ↓
Agent 查询知识库 + 必要时读取 octo-server 源码
  ↓
生成自然语言回答
  ↓
评论区存档完整回答（含来源路径+行号）
  ↓
考试群直接自然语言回答问题，不固定格式
  ↓
打 answered
  ↓
等待用户/考官确认
  ├─ 确认已解决：可关单/打 done
  ├─ 不满意：继续补充回答
  ├─ 发现是 bug：转 type/bug
  └─ 发现是需求：转 type/feature
```

### 群消息格式原则

不固定模板，自然语言说清楚即可，但必须做到：

- 直接回答问题，不只说“去 issue 看评论”
- 必要时给出核心依据
- 长内容放评论区，群里给摘要和结论
- 如引用源码结论，必须带路径和行号

示例：

```text
@主考 这个问题我查到了：octo-server 的 Bot API 鉴权主要在 xxx.go 里处理，核心判断是 token 前缀和 bot 身份绑定。结论是：普通用户 token 不能直接走 bot send API，需要 bot token。

我已把完整依据和源码路径补到 #12 评论区，方便验收。
```

---

## 5. 考官操作响应规则

| 考官操作 | Agent 检测方式 | Agent 动作 |
|---|---|---|
| 打 `designed` | GitHub Issue Events `labeled` | 视为 PRD 通过，进入 `in_progress`，考试群通知 |
| 打 `rejected/xxx` + 评论意见 | Events + Comments API | 读取最新评论，进入 `revising`，修改 PRD 后重新自审；无限循环 |
| 直接 close，且有 `designed`/`done` | Events `closed` | 视为验收完成，打/确认 `done`，考试群通知 |
| close + `wontfix` | Events `closed/labeled` + Comments | 通知不处理原因；若无原因，群里提醒考官补充 |
| 打 `duplicate` + 评论 `#xxx` | Events + Comments | 通知重复 issue；若无重复编号，提醒补充 |
| 修改 type/priority/module | Events `labeled/unlabeled` | 按新标签重新进入对应流程；P0 变更立即群提醒 |
| reopen | Events `reopened` | 根据当前标签恢复到对应阶段，并考试群通知 |
| 打 `in_progress` | Events `labeled` | 记录进入开发/修复阶段，必要时群通知 |
| 打 `done` | Events `labeled` | 记录完成，提醒等待验收或关闭 issue |

---

## 6. 轮询技术方案

现有旧方案是“全量 issue 快照对比”，问题是：

1. 读不到评论内容。
2. closed issue 只看最近 10 分钟，宕机超过 10 分钟可能漏事件。
3. 无法区分是考官操作还是 Bot 自己操作，容易自己触发自己。

### 新方案：事件游标 + 评论游标

```text
Cron 每 5 分钟运行
  ↓
GET /issues?state=all&since=上次轮询时间-1min
  ↓
找出更新过的 issue
  ↓
对每个 issue 拉取：
  - /issues/{n}/events     # 标签、关单、reopen 等事件
  - /issues/{n}/comments   # 新增评论正文
  ↓
根据 event.id / comment.id 增量处理
  ↓
保存本地状态，避免重复处理
```

### 需要使用的 GitHub API

| API | 用途 |
|---|---|
| `GET /repos/{owner}/{repo}/issues?state=all&since=...` | 发现最近更新的 issue |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/events` | 读取 labeled/unlabeled/closed/reopened/assigned 等事件 |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/comments` | 读取考官评论、打回原因、wontfix 原因、question 追问 |
| 可选：`GET /repos/{owner}/{repo}/issues/{issue_number}/timeline` | 如果需要统一读取评论+事件时间线，可替代 events+comments 组合 |

### 本地状态文件

`issue_state.json` 建议结构：

```json
{
  "last_poll_at": "2026-09-14T14:30:00Z",
  "issues": {
    "12": {
      "last_event_id": 123456,
      "last_comment_id": 78910,
      "labels": ["type/feature", "priority/P2", "prd/reviewed"],
      "state": "open",
      "stage": "waiting_examiner_review",
      "updated_at": "2026-09-14T14:28:00Z"
    }
  }
}
```

### 防重复和防死循环

1. 记录 `last_event_id`，只处理新事件。
2. 记录 `last_comment_id`，只处理新评论。
3. 通过 `actor.login` 或 `actor.id` 判断事件发起人。
4. 如果事件是 3 个 Bot 自己产生的，默认跳过，避免“自己打标签 → 自己触发自己”。
5. 对必须响应的 Bot 内部事件，用显式 stage 控制，而不是靠再次检测标签触发。

---

## 7. 通知策略

### 7.1 通知渠道

考试场景下，所有需要人的通知都发到**考试群**，不单独建开发群。

### 7.2 通知核心原则（9/14 老大确认）

**扫到变化必须主动回群说，不等待人来查。**

每条群通知必须满足：
1. **说清楚发生了什么**：哪个issue编号、什么变化、当前流转到哪个状态
2. **@ 对应当事人**：提issue的人是需求/问题/defect的发起人，永远@；考官操作引起变化则也@考官
3. **始终 @ 主考**：所有通知都要@主考抄送知情
4. 群消息用自然语言简洁表达，不固定模板；详细内容（PRD全文、源码引用、回答依据）在issue评论区存档

### 7.3 Issue 评论区与考试群分工

| 渠道 | 用途 |
|---|---|
| Issue 评论区 | 官方存档：PRD全文、回答依据、打回修改记录、源码路径行号、状态说明 |
| 考试群 | **所有流程变化主动通知**：简洁说明+@当事人+@主考 |

### 7.4 发群消息场景（所有变化全发，@当事人+@主考）

| 场景 | @谁 |
|---|---|
| 新 issue 自动分类完成（含type/priority/module识别结果） | @提issue的人 + @主考 |
| P0 新 issue（高优先级提示） | @提issue的人 + @主考 |
| question 回答完成（自然语言答+评论区已存依据） | @提issue的人 + @主考 |
| PRD 草稿生成完成 | @主考 |
| PRD 自审通过、提交考官审核 | @主考 |
| PRD 自审不通过、自动进入修改 | @主考 |
| 考官打 rejected、AI读取意见修改中 | @主考（说明打回原因） |
| 修改后重新自审通过、再次提交审核 | @主考 |
| 考官打 designed → 进入 in_progress | @提issue的人 + @主考 |
| bug 确认confirmed、判为简单bug→queue/simple | @提issue的人 + @主考 |
| bug 判为复杂→转type/feature走PRD流程 | @提issue的人 + @主考 |
| in_progress → done 开发完成、待验收 | @提issue的人 + @主考 |
| done / close 验收完成关闭 | @提issue的人 + @主考 |
| wontfix 拒绝关闭（附原因） | @提issue的人 + @主考 |
| duplicate 重复关闭（附重复编号#xxx） | @提issue的人 + @主考 |
| 缺少必要信息（wontfix没写原因/duplicate没编号）——催考官补充 | @操作考官 + @主考 |
| 考官改type/priority/module → 按新标签重走流程 | @提issue的人 + @主考 |
| P0变更紧急调整 | @提issue的人 + @主考（加🔴紧急标识） |
| Reopen 恢复流程 | @操作人 + @主考 |
| question 用户确认OK/超时7天自动关单 | @提issue的人 + @主考 |
| question 追问/不满意继续回答 | @提issue的人 + @主考 |
| question 发现是bug/feature → 转对应流程 | @提issue的人 + @主考 |
| API 限流/鉴权失败/轮询异常 | @主考（加⚠️异常标识） |
| Bot 自身打回修改循环次数过多（如超过5轮）需要人工介入 | @主考 |

---

## 8. 文件结构

```text
AINOL_Backlog/
├── octo_bot.py                  # Octo消息工具，负责群消息和@高亮
├── poll_issues.py               # GitHub轮询、event/comment游标、事件分发
├── pm_actions.py                # 业务流程处理：feature/bug/question/考官操作
├── run_pm_octo.py               # 可选整合入口/考试运行入口
├── ainol_compliance.py          # 红线/合规检查
├── AINOL_Knowledge_Base_9_Domains.md
├── AINOL_Knowledge_Base_9_Domains_V2.md
├── AINOL_Agent_Architecture_FINAL.md
├── README_EXAM.md
├── config.env.example
├── requirements.txt
├── issue_state.json             # 自动生成，本地状态游标
└── logs/                        # 自动生成，轮询和动作日志
```

---

## 9. 运行方式

```bash
cd AINOL_Backlog
pip install -r requirements.txt
cp config.env.example config.env
# 填入 GITHUB_TOKEN、考试群ID、主考UID等
python3 poll_issues.py --once
python3 poll_issues.py
```

### Cron 示例

```cron
*/5 * * * * cd /path/to/AINOL_Backlog && python3 poll_issues.py >> logs/poll.log 2>&1
```

---

## 10. 配置项

```env
GITHUB_TOKEN=xxx
BACKLOG_REPO=YMJ-ML/octo-server-backlog
SOURCE_REPO=Mininglamp-OSS/octo-server
POLL_INTERVAL=300
STATE_FILE=issue_state.json

EXAM_GROUP_ID=xxx
EXAMINER_UID=xxx

BOT_PRODUCT_ACCOUNT=octo_product_manager
BOT_PRD_ACCOUNT=octo_prd
BOT_REVIEW_ACCOUNT=octo_review

QUESTION_AUTO_CLOSE_DAYS=7
```

---

## 11. 红线遵守

| 红线 | 设计保证 |
|---|---|
| 目标仓库只读 | 代码层面对 `SOURCE_REPO` 只允许 GET，不允许 POST/PATCH/DELETE |
| 凭证不进群、不进 git | token 只放本地 `config.env`，`.gitignore` 排除 |
| 不编造代码引用 | 知识库结论必须带真实源码路径+行号；不确定就说明不确定 |
| 冻结后不改 Agent | 考试前确定冻结时间，冻结后只运行不改逻辑 |
| GitHub 限流撞到就停 | 检查 rate limit，低于阈值暂停并提醒 |
| 不做虚假演示 | 所有动作真实写 GitHub issue / label / comment，并发考试群 |

---

## 12. 当前待改代码点

基于本架构，现有代码需要从旧版 4 事件模型升级为新版流程：

1. `poll_issues.py`
   - 从快照对比改为 event/comment 游标。
   - 支持 `labeled/unlabeled/closed/reopened/commented` 等事件。
   - 加入 actor 过滤，避免 Bot 自触发。

2. `pm_actions.py`
   - 增加 feature/bug/question 三分支处理。
   - 增加 PRD 自审、rejected→revising→重写循环。
   - 增加 designed→in_progress→done 流程。
   - 增加 wontfix/duplicate/reopen/改标签处理。

3. `octo_bot.py`
   - 保留 @ 高亮能力。
   - 增加 question 自然语言群答复。
   - 所有人类通知统一发考试群。

4. `README_EXAM.md`
   - 更新最终标签体系、运行方式、红线说明、考试当天检查清单。

---

## 13. 一句话总结

本版架构的核心是：

> GitHub issue 是流程状态机，Octo 考试群是人类通知面；Agent 用 5 分钟轮询 + event/comment 游标稳定捕捉考官操作，按 feature/bug/question 三分支自动推进 PRD、问答、修复和验收闭环。
