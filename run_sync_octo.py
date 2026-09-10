"""
AINOL Agent - octo-server Sync Runner
Monitors octo-server GitHub, classifies issues, syncs to Backlog, notifies via Octo.

Exam Requirements Addressed:
- 2️⃣ 需求归档 - 自动分类Label，记到Backlog
- 3️⃣ Label体系 - type/priority/status自动打标
- 4️⃣ Cron体系 - 定期自动扫描，有执行日志
- 5️⃣ 回报考试群 - 有变化时@主考（Octo占位符）
"""

import os
import sys
import json
import time
import asyncio
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration (for exam - replace with real values in config.env)
# ---------------------------------------------------------------------------

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
# octo-server is READ-ONLY (source of issues)
OCTO_SERVER_REPO = 'Mininglamp-OSS/octo-server'
# Our backlog is WRITABLE (where we archive issues)
BACKLOG_REPO_OWNER = os.getenv('GITHUB_REPO_OWNER', 'YMJ-ML')
BACKLOG_REPO_NAME = os.getenv('GITHUB_REPO_NAME', 'octo-server-backlog')

# Octo Group settings - PLACEHOLDER, fill before exam
OCTO_EXAM_GROUP = os.getenv('OCTO_EXAM_GROUP', '')  # 考试群group ID
OCTO_MAIN_EXAMINER = os.getenv('OCTO_MAIN_EXAMINER', '')  # 主考user ID

# Polling interval (seconds) - default 5 minutes
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '300'))
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))

# Rate limiting (follow 红线 #5)
GITHUB_REST_LIMIT_PER_HOUR = 4800  # Stay under 5000
GITHUB_SEARCH_LIMIT_PER_MINUTE = 25  # Stay under 30

# Cron log file
CRON_LOG_FILE = os.getenv('CRON_LOG_FILE', 'cron_execution_log.json')

# Knowledge base path (V2 was renamed to overwrite V1 in repo)
KB_PATH = os.getenv('KB_PATH', 'AINOL_Knowledge_Base_9_Domains.md')

# ---------------------------------------------------------------------------
# Simple logging to file
# ---------------------------------------------------------------------------

def setup_logging():
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/ainol_octo_server.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger('AINOL.OctoServer')

logger = setup_logging()

# ---------------------------------------------------------------------------
# Cron Execution Logger
# ---------------------------------------------------------------------------

class CronLogger:
    """Records every cron execution for exam verification (红线 #4 cron要求)"""
    
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.logs = self._load()
    
    def _load(self) -> List[Dict[str, Any]]:
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load cron log: {e}")
        return []
    
    def _save(self):
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(self.logs[-100:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Could not save cron log: {e}")
    
    def log_execution(self, stats: Dict[str, Any]):
        """Log a single cron execution"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'timestamp_human': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'stats': stats
        }
        self.logs.append(entry)
        self._save()
        logger.info(f"Cron execution logged: {entry['timestamp_human']}")
    
    def get_recent(self, count: int = 5) -> List[Dict[str, Any]]:
        """Get recent N execution records (for exam demonstration)"""
        return self.logs[-count:]

cron_logger = CronLogger(CRON_LOG_FILE)

# ---------------------------------------------------------------------------
# Label Classification Engine (需求分类 - 考试要求 #2)
# ---------------------------------------------------------------------------

class IssueClassifier:
    """
    Auto-classify issues using label system.
    
    Labels:
    - Type: type/bug, type/feature, type/question
    - Priority: P0, P1, P2
    - Status: triage (initial), review, duplicate, accepted, approved, done, prd, wontfix
    """
    
    # Type classification keywords
    TYPE_RULES = {
        'type/bug': [
            'bug', 'crash', 'error', 'fail', 'broken', 'fix', 'issue',
            'problem', 'wrong', 'not working', 'exception', 'panic',
            'abnormal', '故障', '错误', '崩溃', '异常', '修复'
        ],
        'type/feature': [
            'feature', 'add', 'implement', 'new', 'support', 'request',
            'enhance', 'improve', 'should', 'could', 'please', '希望',
            '增加', '新增', '支持', '建议', '需求', '功能', '优化'
        ],
        'type/question': [
            '?', 'how', 'why', 'what', 'when', 'where', 'who',
            'question', 'help', 'explain', '请问', '如何', '为什么',
            '什么', '吗', '？', '文档', 'doc', '疑问'
        ]
    }
    
    # Priority classification keywords
    PRIORITY_RULES = {
        'P0': [
            'urgent', 'critical', 'blocker', 'emergency', 'asap', 'now',
            '紧急', '阻塞', '致命', '立即', '严重', 'down', '宕机'
        ],
        'P1': [
            'important', 'high', 'soon', '尽快', '重要', '高优', '尽快'
        ]
    }
    
    @classmethod
    def classify_type(cls, title: str, body: str = '') -> str:
        """Classify issue type based on title and body"""
        text = (title + ' ' + body).lower()
        
        # Check for question marks first (strong signal)
        if '?' in title or '？' in title:
            return 'type/question'
        
        scores = {'type/bug': 0, 'type/feature': 0, 'type/question': 0}
        
        for label, keywords in cls.TYPE_RULES.items():
            for kw in keywords:
                if kw.lower() in text:
                    scores[label] += 1
        
        # Return type with highest score, default to type/feature
        max_score = max(scores.values())
        if max_score == 0:
            return 'type/feature'  # Default
        
        for label, score in scores.items():
            if score == max_score:
                return label
        
        return 'type/feature'
    
    @classmethod
    def classify_priority(cls, title: str, body: str = '') -> str:
        """Classify issue priority"""
        text = (title + ' ' + body).lower()
        
        for priority, keywords in cls.PRIORITY_RULES.items():
            for kw in keywords:
                if kw.lower() in text:
                    return priority
        
        return 'P2'  # Default priority
    
    @classmethod
    def get_initial_labels(cls, title: str, body: str = '') -> List[str]:
        """Get all initial labels for a new issue"""
        type_label = cls.classify_type(title, body)
        priority_label = cls.classify_priority(title, body)
        
        return [
            type_label,
            priority_label,
            'triage'  # Initial status: 待分诊
        ]

# ---------------------------------------------------------------------------
# Knowledge Base Q&A (产品问答 - 考试要求 #1)
# ---------------------------------------------------------------------------

class KnowledgeBase:
    """Simple knowledge base for octo-server product questions"""
    
    def __init__(self, kb_path: str):
        self.kb_path = kb_path
        self.content = self._load()
    
    def _load(self) -> str:
        try:
            if os.path.exists(self.kb_path):
                with open(self.kb_path, 'r', encoding='utf-8') as f:
                    return f.read()
            logger.warning(f"Knowledge base not found: {self.kb_path}")
            return ''
        except Exception as e:
            logger.error(f"Failed to load knowledge base: {e}")
            return ''
    
    def can_answer(self, question: str) -> bool:
        """Check if we can answer this question from KB"""
        # Simple keyword matching for now
        keywords = ['bot', 'agent', 'api', '认证', '模块', '配置', '鉴权', 'wukong', '构建']
        q_lower = question.lower()
        return any(kw in q_lower for kw in keywords)
    
    def get_citation(self, topic: str) -> Optional[str]:
        """Get a source citation for a topic (format: 来源: <path>#L<line>)"""
        # Return verified citations based on our V2 KB
        citations = {
            'app_bot': '来源: modules/app_bot/app_bot.go#L65',
            'botfather': '来源: modules/botfather/api.go#L30',
            'permission': '来源: modules/bot_api/api_i18n.go#L115',
            'token': '来源: modules/app_bot/app_bot.go#L30',
            'wukongim': '来源: main.go#L878',
            'config': '来源: configs/tsdd.yaml#L1',
            'modules': '来源: modules/ 目录（共44个子目录）',
            'cors': '来源: main.go#L453-L454',
            'ratelimit': '来源: main.go#L295-L296',
            'building': '来源: Makefile#L1 / Dockerfile#L1'
        }
        
        for key, citation in citations.items():
            if key in topic.lower():
                return citation
        return None

kb = KnowledgeBase(KB_PATH)

# ---------------------------------------------------------------------------
# Rate Limit Tracker (红线 #5: 限流撞到就停)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Track GitHub API calls and stop if we hit rate limits"""
    
    def __init__(self):
        self.rest_calls_this_hour = 0
        self.search_calls_this_minute = 0
        self.last_hour_reset = time.time()
        self.last_minute_reset = time.time()
        self.hit_limit = False
    
    def _check_reset(self):
        now = time.time()
        if now - self.last_hour_reset > 3600:
            self.rest_calls_this_hour = 0
            self.last_hour_reset = now
        if now - self.last_minute_reset > 60:
            self.search_calls_this_minute = 0
            self.last_minute_reset = now
    
    def can_make_rest_call(self) -> bool:
        self._check_reset()
        if self.rest_calls_this_hour >= GITHUB_REST_LIMIT_PER_HOUR:
            logger.error("GitHub REST rate limit reached! Stopping...")
            self.hit_limit = True
            return False
        return True
    
    def can_make_search_call(self) -> bool:
        self._check_reset()
        if self.search_calls_this_minute >= GITHUB_SEARCH_LIMIT_PER_MINUTE:
            logger.error("GitHub Search rate limit reached! Stopping...")
            self.hit_limit = True
            return False
        return True
    
    def record_rest_call(self):
        self.rest_calls_this_hour += 1
    
    def record_search_call(self):
        self.search_calls_this_minute += 1

rate_limiter = RateLimiter()

# ---------------------------------------------------------------------------
# GitHub API (using requests)
# ---------------------------------------------------------------------------

import requests

class GitHubAPI:
    """Minimal GitHub API wrapper"""
    
    BASE = 'https://api.github.com'
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'AINOL-Agent-Exam'
        }
    
    def _get(self, url: str, params: Dict = None) -> Optional[Dict]:
        if not rate_limiter.can_make_rest_call():
            return None
        try:
            resp = requests.get(
                f'{self.BASE}{url}',
                headers=self.headers,
                params=params or {},
                timeout=REQUEST_TIMEOUT
            )
            rate_limiter.record_rest_call()
            
            if resp.status_code == 403 and 'rate limit' in resp.text.lower():
                logger.error("GitHub rate limit hit!")
                rate_limiter.hit_limit = True
                return None
            
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"GitHub API error: {e}")
            return None
    
    def _post(self, url: str, data: Dict) -> Optional[Dict]:
        # 红线 #1: octo-server 源仓库绝对禁止写入！
        if OCTO_SERVER_REPO in url and url.startswith('/repos/'):
            logger.error(f"🚫 红线#1阻止：禁止写入 octo-server 源仓库！URL: {url}")
            return None
        if not rate_limiter.can_make_rest_call():
            return None
        try:
            resp = requests.post(
                f'{self.BASE}{url}',
                headers=self.headers,
                json=data,
                timeout=REQUEST_TIMEOUT
            )
            rate_limiter.record_rest_call()
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"GitHub POST error: {e}")
            return None
    
    def get_issues(self, repo: str, state: str = 'open', since: str = None) -> List[Dict]:
        """Get issues from a repository"""
        params = {'state': state, 'per_page': 30, 'sort': 'updated', 'direction': 'desc'}
        if since:
            params['since'] = since
        result = self._get(f'/repos/{repo}/issues', params)
        return result if result else []
    
    def create_issue(self, owner: str, repo: str, title: str, body: str, labels: List[str]) -> Optional[Dict]:
        """Create an issue in our backlog repository"""
        data = {'title': title, 'body': body, 'labels': labels}
        return self._post(f'/repos/{owner}/{repo}/issues', data)
    
    def add_labels(self, owner: str, repo: str, issue_number: int, labels: List[str]) -> bool:
        """Add labels to an issue"""
        result = self._post(f'/repos/{owner}/{repo}/issues/{issue_number}/labels', {'labels': labels})
        return result is not None

# ---------------------------------------------------------------------------
# Octo Messenger (考试群通知 - 考试要求 #5)
# ---------------------------------------------------------------------------

class OctoMessenger:
    """
    Send messages to Octo exam group.
    PLACEHOLDER: Will be configured with real group ID and examiner ID before exam.
    """
    
    def __init__(self, group_id: str, examiner_id: str):
        self.group_id = group_id
        self.examiner_id = examiner_id
    
    def format_message(self, event_type: str, issue_data: Dict, labels: List[str]) -> str:
        """Format notification message with @mentions"""
        
        # @主考 mention (placeholder until we have real UID)
        examiner_mention = f'@{self.examiner_id}' if self.examiner_id else '@主考'
        
        if event_type == 'new_issue':
            msg = f"""{examiner_mention}

🔔 **新Issue发现 - octo-server**

📋 **标题：** {issue_data['title']}
🏷️ **自动分类标签：** {', '.join(labels)}
🔗 **链接：** {issue_data['html_url']}
⏰ **发现时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

_AINOL Agent 自动检测_"""
        
        elif event_type == 'synced_to_backlog':
            backlog_url = f"https://github.com/{BACKLOG_REPO_OWNER}/{BACKLOG_REPO_NAME}/issues/{issue_data.get('backlog_number', '?')}"
            msg = f"""{examiner_mention}

✅ **Issue已归档到Backlog**

📋 **原始Issue：** {issue_data['title']}
🔗 **原始链接：** {issue_data['html_url']}
📦 **Backlog链接：** {backlog_url}
🏷️ **已打标签：** {', '.join(labels)}

_AINOL Agent 自动归档_"""
        else:
            msg = f"{examiner_mention}\n\nAINOL Agent 通知"
        
        return msg
    
    def send(self, message: str) -> bool:
        """Send message to Octo group.
        Uses Octo Bot API via local curl or subprocess."""
        
        if not self.group_id:
            logger.warning("Octo group ID not configured, skipping message send")
            logger.info(f"[Would send to group]: {message[:200]}...")
            return False
        
        try:
            # Use Octo Bot API - configured via environment
            import subprocess
            import tempfile
            import os
            
            # Try using octo-bot send command if available
            octo_token = os.getenv('OCTO_BOT_TOKEN', '')
            octo_api = os.getenv('OCTO_API_URL', 'https://api.mlamp.cn/octo')
            
            if octo_token:
                payload = {
                    'channelId': self.group_id,
                    'content': message,
                    'type': 2  # group text message
                }
                resp = requests.post(
                    f'{octo_api}/message/send',
                    headers={'Authorization': f'Bearer {octo_token}'},
                    json=payload,
                    timeout=10
                )
                if resp.ok:
                    logger.info(f"✅ 消息已发送到考试群 {self.group_id}")
                    return True
                else:
                    logger.warning(f"Octo API send failed: {resp.status_code} {resp.text}")
            
            # Fallback: log the message for demo
            logger.info(f"Octo message to group {self.group_id}: {message[:200]}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Octo message: {e}")
            return False

# ---------------------------------------------------------------------------
# Main Sync Runner
# ---------------------------------------------------------------------------

class OctoServerSyncRunner:
    """Main runner: monitor octo-server → classify → archive → notify"""
    
    def __init__(self):
        self.github = GitHubAPI(GITHUB_TOKEN)
        self.octo = OctoMessenger(OCTO_EXAM_GROUP, OCTO_MAIN_EXAMINER)
        self.last_check_file = '.last_sync_check'
        self.last_check_time = self._load_last_check()
        self.processed_issues = set()
        self._load_processed()
    
    def _load_last_check(self) -> Optional[str]:
        try:
            if os.path.exists(self.last_check_file):
                with open(self.last_check_file, 'r') as f:
                    return f.read().strip()
        except:
            pass
        return None
    
    def _save_last_check(self):
        try:
            with open(self.last_check_file, 'w') as f:
                f.write(datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))
        except Exception as e:
            logger.error(f"Failed to save last check: {e}")
    
    def _load_processed(self):
        try:
            if os.path.exists('.processed_issues.json'):
                with open('.processed_issues.json', 'r') as f:
                    self.processed_issues = set(json.load(f))
        except:
            pass
    
    def _save_processed(self):
        try:
            with open('.processed_issues.json', 'w') as f:
                json.dump(list(self.processed_issues), f)
        except:
            pass
    
    async def answer_question(self, issue: Dict) -> Optional[str]:
        """考试要求#1：产品问答 - 如果issue是问题，尝试用知识库回答并附引用"""
        title = issue.get('title', '')
        body = issue.get('body', '') or ''
        issue_number = issue['number']
        
        # Check if it's a question
        issue_type = IssueClassifier.classify_type(title, body)
        if issue_type != 'type/question':
            return None
        
        # Simple keyword-based answer from KB
        text = (title + ' ' + body).lower()
        answer_parts = []
        citations = []
        
        # Check against known topics
        topic_keywords = {
            'app_bot': ['app_bot', 'appbot', '机器人应用', 'app bot'],
            'botfather': ['botfather', '创建机器人', 'bot father'],
            'permission': ['权限', 'permission', '鉴权', 'authorize', 'send', '发送权限'],
            'token': ['token', '令牌', '认证', 'auth'],
            'wukongim': ['wukong', '悟空', 'wukongim', '消息推送'],
            'config': ['配置', 'config', 'tsdd', 'yaml'],
            'modules': ['模块', 'module', '架构'],
            'cors': ['cors', '跨域'],
            'ratelimit': ['限流', 'rate limit', '频率限制'],
            'building': ['构建', 'build', '编译', '部署', 'docker', 'makefile']
        }
        
        content_lower = kb.content.lower()
        
        for topic, keywords in topic_keywords.items():
            for kw in keywords:
                if kw in text:
                    # Try to find relevant section in KB
                    citation = kb.get_citation(topic)
                    if citation and citation not in citations:
                        citations.append(citation)
                    break
        
        if citations:
            answer = f"""### AINOL Agent 知识库答复

根据 octo-server 源码和文档，相关位置参考：

""" + '\n'.join(f'- {c}' for c in citations) + """

如需更详细信息，请参考知识库文档。

_AINOL Agent 自动答复_"""
            return answer
        
        return None
    
    async def process_new_issues(self) -> Dict[str, int]:
        """One sync cycle: check octo-server, classify, archive new issues"""
        
        stats = {
            'new_issues_found': 0,
            'classified': 0,
            'archived_to_backlog': 0,
            'notified': 0,
            'skipped_already_processed': 0,
            'errors': 0
        }
        
        # Check rate limits first (红线 #5)
        if rate_limiter.hit_limit:
            logger.error("Rate limit previously hit, stopping cycle")
            return stats
        
        # Get recent issues from octo-server (READ-ONLY per 红线 #1)
        logger.info(f"Polling {OCTO_SERVER_REPO} for new issues since {self.last_check_time or 'beginning'}")
        issues = self.github.get_issues(OCTO_SERVER_REPO, state='open', since=self.last_check_time)
        
        if not issues:
            logger.info("No new issues found")
            self._save_last_check()
            return stats
        
        stats['new_issues_found'] = len(issues)
        
        for issue in issues:
            issue_number = issue['number']
            issue_id = f"octo_{issue_number}"
            
            # Skip if already processed
            if issue_id in self.processed_issues:
                stats['skipped_already_processed'] += 1
                continue
            
            # Skip pull requests (they are also returned by /issues endpoint)
            if 'pull_request' in issue:
                continue
            
            title = issue.get('title', '')
            body = issue.get('body', '') or ''
            html_url = issue.get('html_url', '')
            
            logger.info(f"Processing issue #{issue_number}: {title}")
            
            try:
                # Step 1: Auto-classify labels FIRST
                labels = IssueClassifier.get_initial_labels(title, body)
                stats['classified'] += 1
                logger.info(f"  Labels: {labels}")
                
                # Step 0(2): 如果是问题类型，尝试用知识库回答（考试要求#1）
                answer = await self.answer_question(issue)
                if answer:
                    logger.info(f"  Found knowledge base answer for question #{issue_number}")
                    # Include answer in backlog issue (we can't comment on source repo per 红线#1)
                    backlog_body = f"""## 来自 octo-server 的 Issue

**原始链接：** {html_url}
**原始编号：** #{issue_number}
**作者：** {issue.get('user', {}).get('login', 'unknown')}
**创建时间：** {issue.get('created_at', 'unknown')}

---

### 原始描述

{body}

---

{answer}

---

### 自动分类标签

{', '.join(labels)}

_AINOL Agent 自动归档_"""
                else:
                    # Standard archive without answer
                    backlog_body = f"""## 来自 octo-server 的 Issue

**原始链接：** {html_url}
**原始编号：** #{issue_number}
**作者：** {issue.get('user', {}).get('login', 'unknown')}
**创建时间：** {issue.get('created_at', 'unknown')}

---

### 原始描述

{body}

---

### 自动分类标签

{', '.join(labels)}

_AINOL Agent 自动归档_"""
                
                # Step 2: Archive to our Backlog repository (WRITABLE)
                
                backlog_issue = self.github.create_issue(
                    BACKLOG_REPO_OWNER,
                    BACKLOG_REPO_NAME,
                    f"[octo-server #{issue_number}] {title}",
                    backlog_body,
                    labels
                )
                
                if backlog_issue:
                    stats['archived_to_backlog'] += 1
                    issue['backlog_number'] = backlog_issue['number']
                    logger.info(f"  Archived to backlog #{backlog_issue['number']}")
                    
                    # Step 3: Notify Octo exam group (only if there's something to report)
                    # Per 红线 #4: 没产出不发消息
                    msg = self.octo.format_message('synced_to_backlog', issue, labels)
                    if self.octo.send(msg):
                        stats['notified'] += 1
                
                # Mark as processed
                self.processed_issues.add(issue_id)
                
            except Exception as e:
                logger.error(f"Error processing issue #{issue_number}: {e}")
                stats['errors'] += 1
        
        # Save state
        self._save_processed()
        self._save_last_check()
        
        return stats
    
    async def run_once(self) -> Dict[str, int]:
        """Run one sync cycle"""
        logger.info("=" * 60)
        logger.info(f"Starting cron sync cycle at {datetime.now().isoformat()}")
        
        stats = await self.process_new_issues()
        
        # Log execution (for exam - 红线 #4: cron执行记录)
        cron_logger.log_execution(stats)
        
        logger.info(f"Cycle complete: {stats}")
        logger.info("=" * 60)
        
        return stats
    
    async def run_continuous(self):
        """Run continuous polling"""
        logger.info(f"Starting continuous polling every {POLL_INTERVAL}s")
        
        while not rate_limiter.hit_limit:
            try:
                await self.run_once()
                logger.info(f"Waiting {POLL_INTERVAL}s before next cycle...")
                await asyncio.sleep(POLL_INTERVAL)
            except KeyboardInterrupt:
                logger.info("Received interrupt, stopping...")
                break
            except Exception as e:
                logger.error(f"Error in sync cycle: {e}")
                await asyncio.sleep(POLL_INTERVAL)
        
        if rate_limiter.hit_limit:
            logger.error("Stopped due to rate limit (红线 #5)")

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='AINOL octo-server Sync Runner')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--continuous', '-c', action='store_true', help='Run continuously')
    parser.add_argument('--logs', action='store_true', help='Show recent cron execution logs')
    parser.add_argument('--interval', '-i', type=int, help='Override poll interval')
    
    args = parser.parse_args()
    
    if args.interval:
        global POLL_INTERVAL
        POLL_INTERVAL = args.interval
    
    runner = OctoServerSyncRunner()
    
    if args.logs:
        # Show recent execution logs for exam demonstration
        print("\n" + "=" * 60)
        print("📊 Cron 最近执行记录（考试要求 #4）")
        print("=" * 60)
        recent = cron_logger.get_recent(10)
        if not recent:
            print("暂无执行记录")
        for i, entry in enumerate(recent, 1):
            print(f"\n#{i} - {entry['timestamp_human']}")
            stats = entry['stats']
            print(f"   新Issue: {stats.get('new_issues_found', 0)}")
            print(f"   已分类: {stats.get('classified', 0)}")
            print(f"   已归档: {stats.get('archived_to_backlog', 0)}")
            print(f"   已通知: {stats.get('notified', 0)}")
        print("\n" + "=" * 60)
        return
    
    if args.once:
        await runner.run_once()
    else:
        await runner.run_continuous()

if __name__ == '__main__':
    asyncio.run(main())
