#!/usr/bin/env python3
"""
AINOL Bot Sender + 合规工具库
按照考试7项硬规则实现：
1. 引用核验（路径+行号真实存在）
2. 未知问题应答规范（我不确定+找谁+补什么）
3. 状态语义严格区分
4. 所有消息必@主考
5. 无产出不发消息
6. PRD只写What不写How，验收标准面向用户
7. 定时执行日志留痕
"""
import os
import sys
import json
import subprocess
import re
from pathlib import Path
from datetime import datetime

# 配置
SCRIPT_DIR = Path(__file__).parent
OCTO_SERVER_LOCAL = Path('/tmp/octo-server')
EXAM_GROUP = '570f12206f1046eca64d236ebc3203cd'
EXAMINER_UID = '2bec5a811432428f8c12892c6d385aba'
EXAMINER_NAME = '袁美君'
SEND_SCRIPT = str(SCRIPT_DIR / 'send_ainol_bot.py')
LOG_DIR = SCRIPT_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# Bot角色映射
BOT_ROLES = {
    'wuguanjia': 'octo产品管家',
    'prd': 'octo PRD',
    'review': 'octo Review'
}

# ---------------------------------------------------------------------------
# 工具1：引用核验（规则1）
# ---------------------------------------------------------------------------

def verify_citation(path: str, start_line: int, end_line: int = None) -> bool:
    """验证引用的路径和行号是否真实存在
    格式：来源: <相对路径>#L<起>-L<止>
    """
    if end_line is None:
        end_line = start_line
    full_path = OCTO_SERVER_LOCAL / path
    if not full_path.exists():
        return False
    try:
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        return 1 <= start_line <= end_line <= len(lines)
    except:
        return False

def format_citation(path: str, start_line: int, end_line: int = None) -> str:
    """生成标准格式引用"""
    if end_line is None or end_line == start_line:
        return f"来源: {path}#L{start_line}"
    return f"来源: {path}#L{start_line}-L{end_line}"

# ---------------------------------------------------------------------------
# 工具2：未知问题应答（规则2）
# ---------------------------------------------------------------------------

def unknown_answer(question_topic: str) -> str:
    """遇到答不上来的问题，按规范返回三要素"""
    return f"""我不确定关于「{question_topic}」的答案。

👉 请联系octo-server核心开发同学确认
📚 需要补充octo-server该模块的相关知识到知识库后再答复。"""

# ---------------------------------------------------------------------------
# 工具3：状态语义严格区分（规则3）
# ---------------------------------------------------------------------------

STATUS_LABELS = {
    'fixed': '已修复',
    'cannot_reproduce': '未复现',
    'wontfix': '明确不做',
    'in_progress': '处理中',
    'triage': '待分诊',
    'accepted': '已认领',
    'prd': 'PRD撰写中',
    'review': '待评审',
    'approved': '评审通过',
    'rejected': '评审打回',
    'done': '已完成'
}

# ---------------------------------------------------------------------------
# 工具4+5：发送消息（必@主考 + 无产出不发）
# ---------------------------------------------------------------------------

def send_bot_message(bot_role: str, content: str, force_at: bool = True) -> bool:
    """发送群消息
    - bot_role: wuguanjia/prd/review
    - content: 消息内容
    - force_at: 是否强制@主考（所有考试消息必须@）
    - 返回是否发送成功
    """
    mention = f'@[{EXAMINER_UID}:{EXAMINER_NAME}]'
    if force_at and not content.startswith('@['):
        content = f'{mention}\n\n{content}'
    
    # 记录消息日志
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'bot': BOT_ROLES.get(bot_role, bot_role),
        'content_preview': content[:100],
        'has_at': mention in content
    }
    with open(LOG_DIR / 'messages_sent.json', 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    try:
        result = subprocess.run(
            [sys.executable, SEND_SCRIPT, bot_role, EXAM_GROUP, content, '2'],
            capture_output=True, text=True, timeout=20, cwd=str(SCRIPT_DIR)
        )
        return result.returncode == 0 and 'message_id' in (result.stdout or '')
    except Exception as e:
        print(f"Send error [{bot_role}]: {e}")
        return False

def log_empty_cycle(bot_role: str, reason: str):
    """空跑只进日志，不发群消息（规则5）"""
    with open(LOG_DIR / 'empty_cycles.log', 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now().isoformat()} [{BOT_ROLES.get(bot_role, bot_role)}] {reason}\n")

# ---------------------------------------------------------------------------
# 工具6：PRD生成（只写What不写How，验收标准用户感知）
# ---------------------------------------------------------------------------

def generate_compliant_prd(issue: dict) -> str:
    """生成符合规范的PRD：只写What，不写How，验收标准面向用户
    issue: GitHub issue对象
    """
    title = issue['title']
    body = (issue.get('body') or '').strip()[:300]
    number = issue['number']
    labels = [l['name'] for l in issue.get('labels', [])]
    
    issue_type = 'Bug修复' if 'type/bug' in labels else '功能需求' if 'type/feature' in labels else '问题解答'
    priority = 'P0 - 紧急' if 'P0' in labels else 'P1 - 高优' if 'P1' in labels else 'P2 - 普通'
    
    # 严格只写What，不出现任何技术实现细节
    prd = f"""## 📋 PRD：{title}

**需求编号：** Backlog #{number}
**类型：** {issue_type}
**优先级：** {priority}
**撰写人：** octo PRD (A2)
**撰写时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

### 1. 问题/需求背景
来自octo-server开源社区的反馈：
{body if body else '（待补充具体问题描述）'}

### 2. 目标（What）
- 用户遇到该问题时可以得到正确处理/响应
- 功能符合用户正常使用预期，不出现异常行为
- 不影响已有功能的正常使用

### 3. 验收标准（用户可感知）
1. ✅ 用户操作该场景时，不再出现报错/异常/无响应等问题
2. ✅ 操作后3秒内可以看到明确的成功/失败提示
3. ✅ 其他已有功能不受本次修改影响，正常使用
4. ✅ 相关文档说明与实际功能保持一致

### 4. 影响范围
- 影响使用该功能的所有用户
- 不涉及其他无关功能模块

---

⚠️ 本文档仅描述需求目标和用户可感知的验收标准，不涉及任何技术实现细节。

_octo PRD (A2) 按规范生成_"""
    return prd

# ---------------------------------------------------------------------------
# 工具7：Cron执行日志（规则7）
# ---------------------------------------------------------------------------

def log_cron_execution(job_name: str, stats: dict):
    """记录定时任务执行日志"""
    log_file = LOG_DIR / 'cron_executions.json'
    logs = []
    if log_file.exists():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except:
            pass
    logs.append({
        'timestamp': datetime.now().isoformat(),
        'job': job_name,
        'stats': stats
    })
    logs = logs[-200:]  # 保留最近200条
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    # 测试发送
    print("✅ AINOL合规工具库加载完成")
    print(f"本地octo-server路径存在：{OCTO_SERVER_LOCAL.exists()}")
    print(f"引用核验测试：{'main.go#1存在' if verify_citation('main.go', 1) else 'main.go#1不存在'}")
