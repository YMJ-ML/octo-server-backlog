# octo-agent cron 脚本

cron 层只负责**定时唤醒 + 只读拉状态 + 选 issue + 叫 agent**。所有 GitHub 写入和群消息都由 agent 运行时完成。

## 文件

| 文件 | 作用 |
|---|---|
| `agentlib.py` | 共享库：gh 只读拉取、state.json 读写、调用 agent、写 EXECUTION_LOG |
| `run_sync.py` | 每 5 分钟：检测需求池的**外部变更**（考官关单/wontfix/打 label/指派给人）→ 叫 octo产品管家回报群 |
| `run_pm.py` | 每 15 分钟（或 `--issue=<n>` 事件触发）：按 PM 链路推进 认领→补PRD→评审→改稿 |
| `config.env.example` | 环境变量模板 |

## 部署

```cron
*/5 * * * * root . ${AGENT_HOME}/config.env; /usr/bin/python3 ${AGENT_HOME}/scripts/run_sync.py >> ${AGENT_HOME}/logs/sync.log 2>&1
*/15 * * * * root . ${AGENT_HOME}/config.env; /usr/bin/python3 ${AGENT_HOME}/scripts/run_pm.py >> ${AGENT_HOME}/logs/pm.log 2>&1
```

其中 `${AGENT_HOME}` 为你的实际工作目录（如 `~/octo-server-backlog`）。

## agent 运行时契约（接入点）

脚本通过 `POST {AGENT_API_BASE}/invoke` 调用 agent，请求体：

```json
{ "bot": "octo产品管家 | octo PRD | octo Review", "task": { ... } }
```

`agentlib.invoke_agent()` 里已留好占位实现（urllib POST），替换成你平台的真实 invoke 端点即可。

### agent 被调用时收到的 task

- `run_sync` 对每条外部变更调用：
 `{ "action": "report_external_change", "issue": {...}, "previous": {...} }`
 → octo产品管家 据此在群里通报（**必须 @主考 + @相关人**，原样复述"已关单/已 wontfix/已打 feature"等）。
- `run_pm` 按状态调用，动作取值：`claim` / `write_prd` / `review` / `revise`
 - `claim`（octo PRD）：认领，置 `accepted`
 - `write_prd`（octo PRD）：补 PRD（只写 What），置 `prd` → `review` 并显式指派 reviewer
 - `review`（octo Review）：评审；通过置 `approved`→`done`，打回置 `rejected/<原因>`（结构化理由）
 - `revise`（octo PRD）：按 `rejected/<原因>` 改稿，回到 `prd`→`review`
 → 各 bot **自行写 GitHub（label/PRD 正文）+ 自行在群回报**，每条群消息必须 @主考。

## 事件快路径（近实时接管，贯穿整条 PM 链路）

`run_pm.py` 支持 `--issue=<n>` 只聚焦单条，且**幂等、按状态推进该单当前能走的所有步**。因此 PM 链路里**任何一步 bot 写回状态后，都由该 bot 的运行时代码再执行一次 `run_pm.py --issue=<n>` 推进下一环**，形成链式近实时闭环：

- octo产品管家 建单（`triage` #N）→ 运行时代码执行 `run_pm.py --issue=N` → A2 秒级认领
- octo PRD 写完 PRD 置 `review` 并指派 A3 → 运行时代码执行 `run_pm.py --issue=N` → A3 秒级评审
- octo Review 打回置 `rejected/<原因>` → 运行时代码执行 `run_pm.py --issue=N` → A2 秒级改稿

接线方式（二选一，作用于"谁写完状态就由谁触发下一跳"）：

- **方式 A（推荐）**：在每个 bot 的"写回状态"动作之后，由该 bot 的运行时代码直接 `subprocess` 调用
 `python3 ${AGENT_HOME}/scripts/run_pm.py --issue=N`。
- **方式 B**：需求池仓库配 GitHub webhook，状态变化事件打到一台小服务，该服务调用上面的命令。

cron 仍独立运行，作为任何一跳事件丢失时的兜底（保证"没人提醒也会自己醒"）。A2、A3 均可通过此机制被即时唤醒，并非只能等 15 分钟 cron。

## 限流与可靠性

- 只用 GitHub REST list（`issues` / `issues/events`，`requests` 或 `gh api` 均可），不用 Search API（30/分限流）。5 分钟一轮约 288 次/天，远低于 REST 5000/小时。
- `invoke_agent` 失败只返回 `{"ok": False}`，**不中断 cron 循环**；下一轮继续。
- 每次运行都写 `EXECUTION_LOG.md`，自证"系统在定时自驱"。
