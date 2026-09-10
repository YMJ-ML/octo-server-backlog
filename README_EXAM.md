# AINOL Agent - 考试使用指南

> 考试日期：2026-09-09  
> 版本：v2.0（验证版）

---

## 🚀 快速开始

### 1. 文件清单

| 文件 | 用途 |
|------|------|
| `AINOL_Knowledge_Base_9_Domains_V2.md` | ✅ 9大领域知识库（所有引用已验证） |
| `run_sync_octo.py` | ✅ octo-server监控主程序 |
| `config.env.example` | 配置模板 |
| `requirements.txt` | Python依赖 |
| `README_EXAM.md` | 本文档（考试使用指南） |

### 2. 环境准备

```bash
# 安装Python依赖
pip install requests python-dotenv

# 复制配置文件
cp config.env.example config.env

# 编辑配置（填入真实的GitHub Token）
nano config.env
```

### 3. 配置说明

在 `config.env` 中填入：

```bash
# GitHub Token（必需，需要repo权限）
GITHUB_TOKEN=***

# Backlog仓库（我们的仓库，可写）
GITHUB_REPO_OWNER=YMJ-ML
GITHUB_REPO_NAME=octo-server-backlog

# 考试群配置（临近考试前填入）
OCTO_EXAM_GROUP=<考试群group_id>
OCTO_MAIN_EXAMINER=<主考user_id>

# 轮询间隔（秒），默认300秒（5分钟）
POLL_INTERVAL=300
```

---

## 📋 考试6项要求对应实现

### ✅ 要求1：产品问答

**实现位置：** `AINOL_Knowledge_Base_9_Domains_V2.md`

**功能说明：**
- 覆盖 octo-server 9大领域知识库
- **所有引用均已通过源码验证**（逐条grep核验）
- 引用格式：`来源: <相对路径>#L<行号>`
- 答不上来时回答「我不确定」+ 指出该找谁

**覆盖领域：**
1. Bot与Agent关系（app_bot/botfather/bot_api/bot_provision/botidentity）
2. API与错误约定（gin框架/wkhttp/限流/CORS）
3. 认证与身份（Token前缀/认证守卫/JWT）
4. 业务模块清单（44个模块完整列表）
5. 鉴权模型（4层权限检查流程）
6. IM控制面与WuKongIM分工（集成点4处）
7. 配置文件结构（tsdd.yaml 6大配置段）
8. 存储与外部依赖（go.mod/SQL目录/核心依赖）
9. 构建与发布（Makefile/Dockerfile/BUILDING.md/RELEASING.md）

**验证证据示例：**
- `来源: modules/app_bot/app_bot.go#L65` — AppBot struct真实存在
- `来源: modules/botfather/api.go#L30` — BotFather struct真实存在
- `来源: modules/bot_api/api_i18n.go#L115` — checkSendPermission真实存在
- `来源: configs/tsdd.yaml#L1` — 配置文件真实存在
- `来源: main.go#L878` — WuKongIM引用真实存在

---

### ✅ 要求2：需求归档

**实现位置：** `run_sync_octo.py` - `IssueClassifier` 类

**功能说明：**
- 自动判断 Issue 类型（type/bug, type/feature, type/question）
- 自动判断优先级（P0, P1, P2）
- 自动创建初始状态标签（triage = 待分诊）
- 将 Issue 归档到 Backlog 仓库（YMJ-ML/octo-server-backlog）

**分类规则：**

**类型判断（基于关键词）：**
- `type/bug`：bug, crash, error, fail, broken, 故障, 错误, 崩溃...
- `type/feature`：feature, add, implement, new, support, 希望, 增加, 新增...
- `type/question`：?, how, why, what, 请问, 如何, 为什么, ？...

**优先级判断：**
- `P0`：urgent, critical, blocker, emergency, 紧急, 阻塞, 致命, 宕机...
- `P1`：important, high, 尽快, 重要, 高优...
- `P2`：默认优先级

---

### ✅ 要求3：Label体系

**实现位置：** GitHub Labels（已在Backlog仓库配置）

**Label清单：**

| 类别 | Labels |
|------|--------|
| 类型 | `type/bug`（Bug报告）, `type/feature`（功能需求）, `type/question`（问题咨询） |
| 优先级 | `P0`（紧急）, `P1`（高）, `P2`（中） |
| PM状态 | `triage`（待分诊）, `review`（待评审）, `duplicate`（重复）, `accepted`（已认领）, `approved`（已通过）, `done`（完成）, `prd`（已有PRD）, `wontfix`（不修复） |

**自动打标逻辑：**
- 新Issue发现时 → 自动打 type + priority + triage
- 后续PM流程推进时 → 更新对应状态Label

---

### ✅ 要求4：Cron体系

**实现位置：** `run_sync_octo.py` - `CronLogger` 类 + `run_continuous()` 方法

**功能说明：**
- 定期自动扫描 octo-server 仓库（默认300秒/5分钟）
- **不是靠人手动触发**
- 每次执行都记录日志
- 考试当天可以用 `--logs` 参数查看最近执行记录

**查看执行记录命令：**
```bash
python run_sync_octo.py --logs
```

**示例输出：**
```
============================================================
📊 Cron 最近执行记录（考试要求 #4）
============================================================

#1 - 2026-09-09 23:25:00
   新Issue: 2
   已分类: 2
   已归档: 2
   已通知: 2

#2 - 2026-09-09 23:30:00
   新Issue: 0
   已分类: 0
   已归档: 0
   已通知: 0
============================================================
```

**日志文件：** `cron_execution_log.json`（自动保存最近100次执行）

---

### ✅ 要求5：回报到考试群

**实现位置：** `run_sync_octo.py` - `OctoMessenger` 类

**功能说明：**
- 扫到变化时**主动发消息到考试群**
- 消息格式包含：@主考、Issue标题、自动分类标签、链接、时间
- **没有产出时不发消息**（遵守红线：禁止"正在检查"等过程消息）
- 目前是占位符，临近考试前填入真实的群ID和主考ID即可

**消息格式示例：**
```
@主考

🔔 新Issue发现 - octo-server

📋 标题：xxx
🏷️ 自动分类标签：type/bug, P2, triage
🔗 链接：https://github.com/...
⏰ 发现时间：2026-09-09 14:30:00

_AINOL Agent 自动检测_
```

**考试前配置：**
编辑 `config.env`，填入：
```bash
OCTO_EXAM_GROUP=<考试群group_id>
OCTO_MAIN_EXAMINER=<主考user_id>
```

---

### ✅ 要求6：PM链路

**PM流程（通过GitHub Labels + 评论实现）：**

```
新Issue → triage(待分诊)
    ↓
认领 → accepted(已认领)
    ↓
生成PRD → prd(已有PRD)
    ↓
找人Review → review(待评审)
    ↓
Review通过 → approved(已通过)
    ↓
完成 → done(完成)
    ↓
打回 → 按打回原因修改 → 重新review
```

**PRD原则：只写What不写How**
- ✅ 用户能感知的验收标准
- ✅ 功能描述
- ❌ 具体实现细节（不用Redis/不用加表）
- ❌ 不贴代码块

---

## 🚨 红线遵守情况

| 红线 | 实现方式 |
|------|---------|
| ❌ 目标仓库只读 | ✅ 只从 octo-server GET，从不 POST/PUT |
| ❌ 凭证不进群/git | ✅ config.env 被 .gitignore 排除 |
| ❌ 不编造引用 | ✅ 知识库V2所有引用经源码验证 |
| ❌ 冻结后不改Agent | ✅ 冻结前完成所有代码 |
| ❌ 限流撞到就停 | ✅ RateLimiter类监控，超限自动停止 |
| ❌ 不做虚假演示 | ✅ 所有功能真实可用 |

---

## 🛠️ 运行命令

**单次运行（测试用）：**
```bash
python run_sync_octo.py --once
```

**持续运行（Cron模式）：**
```bash
python run_sync_octo.py --continuous
```

**自定义轮询间隔（60秒）：**
```bash
python run_sync_octo.py --continuous --interval 60
```

**查看执行日志：**
```bash
python run_sync_octo.py --logs
```

---

## 📝 考试前检查清单

- [ ] GitHub Token 已配置到 config.env
- [ ] Backlog仓库地址正确（YMJ-ML/octo-server-backlog）
- [ ] 考试群group ID已填入
- [ ] 主考user ID已填入
- [ ] 知识库文件存在（AINOL_Knowledge_Base_9_Domains_V2.md）
- [ ] Python依赖已安装（pip install requests python-dotenv）
- [ ] 测试运行：python run_sync_octo.py --once
- [ ] Cron持续运行中
- [ ] 执行日志可查看：python run_sync_octo.py --logs

---

## ⚠️ 注意事项

1. **octo-server 是只读的** — 我们永远不会往那里写任何东西
2. **凭证安全** — config.env 绝对不能提交到git
3. **知识库引用** — V2版本所有引用已验证，V1版本（未验证）请不要使用
4. **限流处理** — 程序会自动监控GitHub API限流，撞到就停
5. **消息克制** — 没有新发现不发消息，不发"正在检查"等过程消息
6. **如实转达** — 已修复/没复现/wontfix 严格区分
7. **诚实回答** — 知识库里没有的回答「我不确定」

---

**版本：** v2.0（验证版）  
**最后更新：** 2026-09-09 23:35  
**考试状态：** ✅ 准备就绪
