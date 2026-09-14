# AINOL 考试使用指南 v5

## 文件结构

```
├── octo_bot.py          # Octo Bot消息工具：群通知、@高亮、GitHub写评论/标签工具
├── poll_issues.py       # GitHub轮询：event/comment游标、变化检测、事件分发
├── pm_actions.py        # PM流程动作：feature/bug/question三分支+考官操作响应
├── config.env.example   # 配置模板
├── requirements.txt     # Python依赖
├── issue_state.json     # 游标状态（自动生成）
└── logs/                # 日志目录（自动生成）
```

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置
```bash
cp config.env.example config.env
# 填入 GITHUB_TOKEN / OCTO_EXAM_GROUP / OCTO_MAIN_EXAMINER / 三个Bot账号
```

### 3. 运行
```bash
# 单次测试
python3 poll_issues.py --once

# 持续轮询（考试用）
python3 poll_issues.py
```

## Label 标签体系（v5最终版）

### 类型标签
- `type/feature`：功能需求/产品需求
- `type/bug`：缺陷/异常/故障
- `type/question`：产品/代码/流程问答

### 优先级标签
- `priority/P0`：紧急/阻塞/严重事故
- `priority/P1`：高优
- `priority/P2`：默认中优
- `priority/P3`：低优

### 模块标签
- `module/bot`
- `module/api`
- `module/auth`
- `module/im`
- `module/config`
- `module/storage`
- `module/build`
- `module/unknown`

### 流程状态标签
- `confirmed`
- `queue/simple`
- `prd/draft`
- `prd/reviewed`
- `revising`
- `designed`
- `in_progress`
- `done`
- `answered`
- `duplicate`
- `wontfix`

### 打回标签
- `rejected/结构不完整`
- `rejected/包含实现细节`
- `rejected/验收标准不可测`
- `rejected/逻辑矛盾`
- `rejected/模块错误`
- `rejected/自定义原因`

## 工作流

1. 新issue → 自动分类打 `type + priority + module` → 主动回考试群（@当事人+@主考）
2. `type/feature` → 自动生成PRD → `prd/draft` → Review自审 → `prd/reviewed` → 等主考打 `designed`
3. `type/bug` → `confirmed` → 简单bug `queue/simple`；复杂bug转 `type/feature` 走PRD
4. `type/question` → 自然语言回答 → 评论区存档 → 考试群回答 → `answered`
5. 主考打 `designed` → 自动打 `in_progress` 并回群
6. `done` / close / `wontfix` / `duplicate` / reopen / 改标签 / 新评论 → 都会主动回考试群，@当事人+@主考

## 轮询机制

- 每5分钟执行一次
- 使用 GitHub `issues?since=...` 找出变化issue
- 对变化issue读取：
  - `/issues/{n}/events`：标签、关单、reopen
  - `/issues/{n}/comments`：评论、打回意见、wontfix原因
- 本地记录 `last_event_id` 和 `last_comment_id`，避免重复处理
- 过滤Bot自己在GitHub上产生的事件，防止自触发死循环

## Cron配置

```cron
*/5 * * * * cd /path/to/AINOL_Backlog && python3 poll_issues.py >> logs/poll.log 2>&1
```

## 红线

- 目标源码仓库 `Mininglamp-OSS/octo-server` 只读
- 凭证只放本地 `config.env`，不进群、不进git
- 代码引用必须真实可验证，不确定就说不确定
- 冻结后不改Agent逻辑
- GitHub限流不足时停止轮询并提醒
- 不做虚假演示，所有动作真实写GitHub/发考试群
