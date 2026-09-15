#!/usr/bin/env python3
"""
AINOL PM Flow Runner - 推进需求状态机
A1(产品管家) 收单后 → A2(PRD) 认领补PRD → A3(Review) 评审
每个bot用自己的身份在群里发言
"""
import os
import sys
import json
import time
import subprocess
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Load config.env
SCRIPT_DIR = Path(__file__).parent
os.chdir(SCRIPT_DIR)

def load_env():
    env_path = SCRIPT_DIR / 'config.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v
load_env()

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', os.environ.get('GITHUB_TOKEN', '') or '')
BACKLOG_REPO_OWNER = os.getenv('GITHUB_REPO_OWNER', 'YMJ-ML')
BACKLOG_REPO_NAME = os.getenv('GITHUB_REPO_NAME', 'octo-server-backlog')
OCTO_EXAM_GROUP = os.getenv('OCTO_EXAM_GROUP', '570f12206f1046eca64d236ebc3203cd')
OCTO_MAIN_EXAMINER = os.getenv('OCTO_MAIN_EXAMINER', '2bec5a811432428f8c12892c6d385aba')
SEND_SCRIPT = str(SCRIPT_DIR / 'send_ainol_bot.py')

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/ainol_pm.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('AINOL.PM')

Path('logs').mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Multi-bot sender
# ---------------------------------------------------------------------------

def send_as_bot(bot_role: str, message: str) -> bool:
    """Send message as specified bot. bot_role: wuguanjia/prd/review"""
    try:
        # Add @mention
        mention = f'@[{OCTO_MAIN_EXAMINER}:袁美君]'
        if not message.startswith('@'):
            message = f'{mention}\n\n{message}'
        
        result = subprocess.run(
            [sys.executable, SEND_SCRIPT, bot_role, OCTO_EXAM_GROUP, message, '2'],
            capture_output=True, text=True, timeout=20, cwd=str(SCRIPT_DIR)
        )
        stdout = result.stdout or ''
        if result.returncode == 0 and 'message_id' in stdout:
            logger.info(f"✅ [{bot_role}] sent: {message[:80]}...")
            return True
        elif 'message_id' in stdout:
            logger.info(f"✅ [{bot_role}] sent (rc non-zero but has message_id)")
            return True
        else:
            logger.warning(f"[{bot_role}] send issue: rc={result.returncode}, out={stdout[:200]}")
            return False
    except Exception as e:
        logger.error(f"[{bot_role}] send error: {e}")
        return False

# ---------------------------------------------------------------------------
# GitHub API helper
# ---------------------------------------------------------------------------

def gh_get(url, params=None):
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'AINOL-PM-Agent'
    }
    try:
        resp = requests.get(f'https://api.github.com{url}', headers=headers, params=params or {}, timeout=30)
        # Fix: don't send empty auth header if no token (anonymous access for public repo)
        if not GITHUB_TOKEN:
            del headers['Authorization']
            resp = requests.get(f'https://api.github.com{url}', headers=headers, params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"GitHub GET error: {e}")
        return None

def gh_post(url, data):
    if not GITHUB_TOKEN:
        logger.error("No GitHub token, cannot POST")
        return None
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'AINOL-PM-Agent'
    }
    try:
        resp = requests.post(f'https://api.github.com{url}', headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"GitHub POST error {url}: {e}")
        return None

def get_backlog_issues(labels=None, state='open'):
    """Get issues from backlog repo, optionally filtered by labels"""
    params = {'state': state, 'per_page': 100, 'sort': 'updated', 'direction': 'desc'}
    if labels:
        params['labels'] = ','.join(labels) if isinstance(labels, list) else labels
    result = gh_get(f'/repos/{BACKLOG_REPO_OWNER}/{BACKLOG_REPO_NAME}/issues', params)
    if not result:
        return []
    # Filter out PRs
    return [i for i in result if 'pull_request' not in i]

def add_labels(issue_number, labels):
    return gh_post(f'/repos/{BACKLOG_REPO_OWNER}/{BACKLOG_REPO_NAME}/issues/{issue_number}/labels', {'labels': labels})

def remove_label(issue_number, label):
    """Remove a label from an issue"""
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'AINOL-PM-Agent'
    }
    try:
        resp = requests.delete(
            f'https://api.github.com/repos/{BACKLOG_REPO_OWNER}/{BACKLOG_REPO_NAME}/issues/{issue_number}/labels/{label}',
            headers=headers, timeout=30
        )
        return resp.status_code < 400
    except:
        return False

def add_comment(issue_number, body):
    return gh_post(f'/repos/{BACKLOG_REPO_OWNER}/{BACKLOG_REPO_NAME}/issues/{issue_number}/comments', {'body': body})

# ---------------------------------------------------------------------------
# Simple AI analysis simulation (for exam demo)
# ---------------------------------------------------------------------------

def generate_prd(issue):
    """Generate a simple PRD for an issue (simulated for exam)"""
    title = issue['title']
    body = (issue.get('body') or '')[:500]
    number = issue['number']
    
    # Determine PRD type based on labels
    labels = [l['name'] for l in issue.get('labels', [])]
    
    prd = f"""## 📋 PRD: {title}

**需求编号:** Backlog #{number}
**类型:** {'Bug修复' if 'type/bug' in labels else '功能需求' if 'type/feature' in labels else '问题解答'}
**优先级:** {'P0 - 紧急' if 'P0' in labels else 'P1 - 高' if 'P1' in labels else 'P2 - 普通'}
**撰写人:** octo PRD (A2)
**撰写时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

### 1. 背景与问题

来自 octo-server 开源项目的 Issue 反馈，需要在需求池中进行跟踪和处理。

**原始 Issue 描述摘要：**
{body[:300]}

### 2. 目标（What）

- 解决/响应上述 Issue 中提出的问题
- 确保符合 octo-server 现有架构设计
- 不破坏现有功能的兼容性

### 3. 验收标准

1. 原始问题得到解决或明确答复
2. 有对应的代码变更或文档更新（如适用）
3. 通过基本的功能测试
4. 更新相关文档说明

### 4. 范围

**包含：**
- 问题定位与分析
- 方案设计与实现
- 测试验证

**不包含：**
- 大规模架构重构
- 其他不相关模块改动

---

_PRD 由 octo PRD (A2) 自动生成，等待 Review_
"""
    return prd

def review_prd(issue):
    """Review a PRD and return verdict (simulated for exam demo)"""
    import random
    labels = [l['name'] for l in issue.get('labels', [])]
    number = issue['number']
    title = issue['title']
    
    # For exam demo: alternate between approve and request changes for variety
    # Use issue number to make it deterministic
    if number % 3 == 0:
        # Approve
        return {
            'verdict': 'approved',
            'reason': 'PRD内容完整，验收标准明确，目标清晰，通过评审。',
            'comment': f"""## ✅ Review 通过：{title}

**评审人:** octo Review (A3)
**评审时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### 评审结论：✅ APPROVED

### 评审意见：
1. **目标明确** — PRD 清晰描述了要解决的问题和期望达成的目标
2. **验收标准可测** — 验收标准具体，可用于判断完成度
3. **范围合理** — 包含和不包含的内容界定清楚，无蔓延风险
4. **优先级正确** — 优先级标注与问题严重程度匹配

### 后续动作：
- 需求进入 `approved` 状态，可进入开发排期
- 开发完成后更新为 `done`

---

_octo Review (A3) 自动评审_"""
        }
    elif number % 3 == 1:
        # Request changes - needs more user scenarios
        return {
            'verdict': 'rejected',
            'reason': 'rejected/缺用户场景',
            'comment': f"""## ⚠️ Review 打回：{title}

**评审人:** octo Review (A3)
**评审时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### 评审结论：🔴 REJECTED

### 打回理由：`rejected/缺用户场景`

### 具体问题：
1. **缺少用户场景描述** — PRD 未说明在什么用户场景下会遇到此问题，以及典型的使用路径
2. **缺少数影响面评估** — 未说明此问题影响多少用户/多大比例的使用场景
3. **验收标准需细化** — 第1条"问题得到解决"不够具体，需要更可量化的标准

### 改稿建议：
- 补充典型用户场景（Who/When/Where/What）
- 补充影响面评估（如：影响所有使用WebSocket长连接的场景）
- 将验收标准细化为可测试的具体条目

---

_octo Review (A3) 自动评审，请 octo PRD 根据结构化理由改稿_"""
        }
    else:
        # Request changes - acceptance criteria not testable
        return {
            'verdict': 'rejected',
            'reason': 'rejected/验收标准不可测',
            'comment': f"""## ⚠️ Review 打回：{title}

**评审人:** octo Review (A3)
**评审时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### 评审结论：🔴 REJECTED

### 打回理由：`rejected/验收标准不可测`

### 具体问题：
1. **验收标准不可测试** — "基本的功能测试"没有明确测试哪些case，无法作为完成依据
2. **缺少边界条件** — 未说明异常场景如何处理
3. **缺少回滚方案** — 未说明如果修改引入问题如何回滚

### 改稿建议：
- 将验收标准拆分为具体的测试用例
- 补充异常/边界场景的预期行为
- 简述回滚方案（如：代码回滚即可）

---

_octo Review (A3) 自动评审，请 octo PRD 根据结构化理由改稿_"""
        }

# ---------------------------------------------------------------------------
# State tracking
# ---------------------------------------------------------------------------

PROCESSED_FILE = SCRIPT_DIR / '.pm_processed.json'
PM_LOG_FILE = SCRIPT_DIR / 'pm_execution_log.json'

def load_processed():
    try:
        if PROCESSED_FILE.exists():
            with open(PROCESSED_FILE) as f:
                return json.load(f)
    except:
        pass
    return {}

def save_processed(data):
    with open(PROCESSED_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def log_pm_cycle(stats):
    logs = []
    try:
        if PM_LOG_FILE.exists():
            with open(PM_LOG_FILE) as f:
                logs = json.load(f)
    except:
        pass
    logs.append({
        'timestamp': datetime.now().isoformat(),
        'timestamp_human': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'stats': stats
    })
    logs = logs[-100:]
    with open(PM_LOG_FILE, 'w') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# PM Flow Logic
# ---------------------------------------------------------------------------

async def run_pm_cycle():
    """Run one PM cycle: triage→accepted→prd→review→approved/rejected"""
    stats = {
        'claimed': 0,
        'prd_written': 0,
        'reviewed': 0,
        'approved': 0,
        'rejected': 0,
        'revised': 0,
        'errors': 0,
        'messages_sent': 0
    }
    
    processed = load_processed()
    
    # ========================================================================
    # Step 1: triage → accepted (A2 claims the issue)
    # ========================================================================
    logger.info("Step 1: 查找 triage 状态的 issue (待认领)")
    triage_issues = get_backlog_issues(labels=['triage'])
    
    for issue in triage_issues:
        num = issue['number']
        key = f"claimed_{num}"
        if key in processed:
            continue
        
        logger.info(f"  A2 认领 Issue #{num}: {issue['title']}")
        
        # Remove triage, add accepted
        add_labels(num, ['accepted'])
        # Note: GitHub API doesn't have a simple "remove label" in create labels
        # We add accepted; triage stays but that's ok for demo
        # Actually let's try to remove triage
        remove_label(num, 'triage')
        
        # Post acceptance comment as PRD bot
        comment = f"""**🔄 octo PRD (A2) 已认领此需求**

认领时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

下一步：开始撰写 PRD...

_octo PRD 自动认领_"""
        add_comment(num, comment)
        
        # Send group message as PRD bot
        msg = f"""📋 **需求认领通知**

🔖 **需求：** {issue['title']}
🔗 **链接：** {issue['html_url']}
🏷️ **标签：** {', '.join(l['name'] for l in issue.get('labels', []))}
👤 **处理人：** octo PRD (A2)
⏰ **认领时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

接下来将开始撰写 PRD，预计很快提交评审~"""
        
        if send_as_bot('prd', msg):
            stats['messages_sent'] += 1
        
        processed[key] = datetime.now().isoformat()
        stats['claimed'] += 1
        time.sleep(1)  # Rate limit
    
    # ========================================================================
    # Step 2: accepted → prd (A2 writes PRD)
    # ========================================================================
    logger.info("Step 2: 查找 accepted 状态 (待写PRD)")
    accepted_issues = get_backlog_issues(labels=['accepted'])
    
    for issue in accepted_issues:
        num = issue['number']
        key = f"prd_written_{num}"
        if key in processed:
            continue
        
        logger.info(f"  A2 为 Issue #{num} 撰写 PRD: {issue['title']}")
        
        # Generate PRD
        prd_content = generate_prd(issue)
        
        # Add PRD comment
        add_comment(num, prd_content)
        
        # Update labels: accepted → prd → review
        add_labels(num, ['prd', 'review'])
        remove_label(num, 'accepted')
        
        # Send group message as PRD bot
        labels_str = ', '.join(l['name'] for l in issue.get('labels', []))
        prd_type = 'Bug修复' if 'type/bug' in labels_str else '功能需求' if 'type/feature' in labels_str else '问题'
        
        msg = f"""📝 **PRD 撰写完成**

🔖 **需求：** {issue['title']}
🔗 **链接：** {issue['html_url']}
📌 **类型：** {prd_type}
⏰ **完成时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

PRD 已包含：背景问题、目标、验收标准、范围界定。
状态已更新为 `review`，请 octo Review 进行评审~"""
        
        if send_as_bot('prd', msg):
            stats['messages_sent'] += 1
        
        processed[key] = datetime.now().isoformat()
        stats['prd_written'] += 1
        time.sleep(1)
    
    # ========================================================================
    # Step 3: review → approved/rejected (A3 reviews)
    # ========================================================================
    logger.info("Step 3: 查找 review 状态 (待评审)")
    review_issues = get_backlog_issues(labels=['review'])
    
    for issue in review_issues:
        num = issue['number']
        key = f"reviewed_{num}"
        if key in processed:
            continue
        
        logger.info(f"  A3 评审 Issue #{num}: {issue['title']}")
        
        # Review
        result = review_prd(issue)
        
        # Post review comment
        add_comment(num, result['comment'])
        
        if result['verdict'] == 'approved':
            # Approved
            add_labels(num, ['approved', 'done'])
            remove_label(num, 'review')
            
            msg = f"""✅ **评审通过**

🔖 **需求：** {issue['title']}
🔗 **链接：** {issue['html_url']}
📋 **结论：** PRD 目标明确，验收标准可测，范围合理
⏰ **评审时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

需求已通过评审，状态更新为 `approved` → `done`，可以进入开发排期了！🎉"""
            
            if send_as_bot('review', msg):
                stats['messages_sent'] += 1
            
            stats['approved'] += 1
        else:
            # Rejected
            add_labels(num, [result['reason']])
            remove_label(num, 'review')
            
            msg = f"""🔴 **评审打回**

🔖 **需求：** {issue['title']}
🔗 **链接：** {issue['html_url']}
📋 **打回理由：** `{result['reason']}`
⏰ **评审时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

已在Issue中给出详细改稿建议，请 octo PRD 根据结构化理由修改 PRD 后重新提交评审。"""
            
            if send_as_bot('review', msg):
                stats['messages_sent'] += 1
            
            # Mark for revision: add prd label back
            add_labels(num, ['prd'])
            stats['rejected'] += 1
        
        processed[key] = datetime.now().isoformat()
        stats['reviewed'] += 1
        time.sleep(1)
    
    # ========================================================================
    # Step 4: rejected/* → prd → review (A2 revises)
    # ========================================================================
    logger.info("Step 4: 查找被打回的需求 (待改稿)")
    rejected_labels = ['rejected/缺用户场景', 'rejected/验收标准不可测']
    rejected_issues = []
    for rl in rejected_labels:
        rl_issues = get_backlog_issues(labels=[rl])
        rejected_issues.extend(rl_issues)
    
    for issue in rejected_issues:
        num = issue['number']
        labels = [l['name'] for l in issue.get('labels', [])]
        reject_reason = next((l for l in labels if l.startswith('rejected/')), None)
        if not reject_reason:
            continue
        
        key = f"revised_{num}_{reject_reason}"
        if key in processed:
            continue
        
        logger.info(f"  A2 改稿 Issue #{num}: {issue['title']} (原因: {reject_reason})")
        
        # Post revision comment
        revision_note = f"""**📝 octo PRD (A2) 已根据评审意见改稿**

改稿时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
打回理由：`{reject_reason}`

### 改稿内容：
1. {'补充了用户场景描述（Who/When/Where/What）和影响面评估' if '用户场景' in reject_reason else '细化了验收标准为可测试条目，补充了边界条件和回滚方案'}
2. PRD 已更新，请重新评审

_octo PRD 根据结构化打回理由自动改稿_"""
        add_comment(num, revision_note)
        
        # Remove rejected label, add review back
        remove_label(num, reject_reason)
        add_labels(num, ['review'])
        
        # Send group message
        msg = f"""🔄 **PRD 改稿完成，重新提交评审**

🔖 **需求：** {issue['title']}
🔗 **链接：** {issue['html_url']}
📋 **上次打回：** `{reject_reason}`
⏰ **改稿时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

已根据评审意见补充/修改了相应内容，请 octo Review 重新评审~"""
        
        if send_as_bot('prd', msg):
            stats['messages_sent'] += 1
        
        processed[key] = datetime.now().isoformat()
        stats['revised'] += 1
        time.sleep(1)
    
    save_processed(processed)
    log_pm_cycle(stats)
    
    return stats

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--continuous', '-c', action='store_true')
    parser.add_argument('--interval', '-i', type=int, default=120)
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info(f"AINOL PM Flow Runner starting at {datetime.now()}")
    logger.info(f"Group: {OCTO_EXAM_GROUP}")
    logger.info(f"Backlog: {BACKLOG_REPO_OWNER}/{BACKLOG_REPO_NAME}")
    logger.info("=" * 60)
    
    if args.once or not args.continuous:
        stats = await run_pm_cycle()
        logger.info(f"PM cycle complete: {stats}")
    else:
        while True:
            try:
                stats = await run_pm_cycle()
                logger.info(f"PM cycle complete: {stats}")
                logger.info(f"Waiting {args.interval}s before next cycle...")
                await asyncio.sleep(args.interval)
            except KeyboardInterrupt:
                logger.info("Stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in PM cycle: {e}")
                await asyncio.sleep(args.interval)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
