"""
poll_issues.py - GitHub Issue 轮询引擎（v5版）
核心改动：
- 从快照对比改为 event.id / comment.id 游标增量模式
- 支持 labeled/unlabeled/closed/reopened 等全部事件
- 支持 Comments API 读取考官评论内容
- 按 actor.id 过滤Bot自己产生的事件，防自触发
- 发现变化后调用 pm_actions.handle_event 处理
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
def _load_env_files():
    """兼容加载 .env 和 config.env；即使没装python-dotenv也能读简单KEY=VALUE。"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        load_dotenv('config.env')
        return
    except ImportError:
        pass
    for env_file in ['.env', 'config.env']:
        p = Path(env_file)
        if not p.exists():
            continue
        for line in p.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)

_load_env_files()

# ==================== 配置 ====================

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
BACKLOG_REPO = os.getenv('BACKLOG_REPO', 'YMJ-ML/octo-server-backlog')
STATE_FILE = os.getenv('STATE_FILE', 'issue_state.json')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '300'))  # 秒，默认5分钟
LOG_DIR = os.getenv('LOG_DIR', 'logs')

# Bot自己的GitHub login（用于过滤自触发事件）
BOT_GITHUB_LOGINS = [
    x.strip() for x in os.getenv('BOT_GITHUB_LOGINS', 'YMJ-ML').split(',') if x.strip()
]


# ==================== Issue分类器 ====================

class IssueClassifier:
    """新issue自动分类：type/priority/module"""

    TYPE_BUG_KEYWORDS = [
        'bug', 'crash', 'error', 'fail', 'broken', 'issue', 'problem', 'wrong',
        'not working', 'exception', 'panic', 'abnormal', '故障', '错误', '崩溃',
        '异常', '修复', '宕机', '失效', 'leak', 'never', '无法', '不能用', '挂了'
    ]
    TYPE_QUESTION_PREFIX = ['如何', '请问', '怎么', 'what', 'how', 'why', '?', '？']
    TYPE_QUESTION_KEYWORDS = [
        '?', 'how', 'why', 'what', 'when', 'where', 'who',
        'question', 'help', 'explain', '请问', '如何', '为什么', '什么', '吗', '？', '疑问',
        '咨询', '了解', '解释'
    ]
    TYPE_FEATURE_KEYWORDS = [
        '✨', 'feat', 'feature', 'add', '新增', '支持', '建议', '需求', '功能',
        '优化', '改进', '增强', '希望', '期望', '建议', '可以'
    ]

    PRIORITY_P0_KEYWORDS = [
        'urgent', 'critical', 'blocker', 'emergency', 'asap', '紧急', '阻塞',
        '致命', '立即', '严重', 'down', '宕机', '线上故障', 'p0', '事故', '挂了'
    ]
    PRIORITY_P1_KEYWORDS = ['important', 'high', 'soon', '尽快', '重要', '高优', 'p1', '尽快处理']
    PRIORITY_P3_KEYWORDS = ['low', 'minor', 'whenever', '低优', '不急', '有空', 'p3', '低优先级']

    MODULE_RULES = {
        'module/bot': ['bot', 'agent', 'app_bot', 'botfather', 'bot_provision', 'botidentity', '机器人', '助手'],
        'module/api': ['api', 'http', 'rest', 'endpoint', 'response', 'error code', '错误码', '接口', '请求'],
        'module/auth': ['auth', 'token', 'cookie', 'permission', 'acl', 'rbac', '鉴权', '权限', '认证', '登录'],
        'module/im': ['wukong', 'wukongim', 'message', 'chat', 'channel', '消息', '群', '聊天', '推送', 'im'],
        'module/config': ['config', 'env', 'yaml', '部署', '配置', '环境变量'],
        'module/storage': ['database', 'db', 'mysql', 'redis', 'cache', 'storage', 's3', 'object', '数据库', '缓存', '存储'],
        'module/build': ['build', 'docker', 'makefile', 'compile', 'release', '构建', '编译', '打包', '发布', '部署'],
    }

    @classmethod
    def classify_type(cls, title, body=''):
        text = (title + ' ' + (body or '')).lower()
        tl = title.lower()
        # Bug明显标识
        for m in cls.TYPE_BUG_KEYWORDS:
            if m in tl or m in text[:200]:
                return 'type/bug'
        # Question：问号/疑问词开头
        if '?' in title or '？' in title:
            return 'type/question'
        for p in cls.TYPE_QUESTION_PREFIX:
            if tl.startswith(p):
                return 'type/question'
        # Feature明显标识
        for m in cls.TYPE_FEATURE_KEYWORDS:
            if m in tl:
                return 'type/feature'
        # 默认按feature算
        return 'type/feature'

    @classmethod
    def classify_priority(cls, title, body=''):
        text = (title + ' ' + (body or '')).lower()
        for kw in cls.PRIORITY_P0_KEYWORDS:
            if kw in text:
                return 'priority/P0'
        for kw in cls.PRIORITY_P1_KEYWORDS:
            if kw in text:
                return 'priority/P1'
        for kw in cls.PRIORITY_P3_KEYWORDS:
            if kw in text:
                return 'priority/P3'
        return 'priority/P2'

    @classmethod
    def classify_module(cls, title, body=''):
        text = (title + ' ' + (body or '')).lower()
        for module, keywords in cls.MODULE_RULES.items():
            for kw in keywords:
                if kw in text:
                    return module
        return 'module/unknown'

    @classmethod
    def get_initial_labels(cls, title, body=''):
        """新issue首次自动分类标签（不含流程状态标签）"""
        return [
            cls.classify_type(title, body),
            cls.classify_priority(title, body),
            cls.classify_module(title, body),
        ]


# ==================== 状态管理 ====================

def load_state():
    """加载本地状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 加载state文件失败: {e}")
    return {
        'last_poll_at': None,
        'issues': {}
    }


def save_state(state):
    """保存状态到本地"""
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ==================== GitHub API ====================

def _headers():
    return {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }


def _check_rate_limit():
    """检查限流，返回剩余请求数，不足时返回0"""
    try:
        r = requests.get('https://api.github.com/rate_limit', headers=_headers(), timeout=10)
        if r.status_code == 200:
            data = r.json()
            core = data.get('resources', {}).get('core', {})
            remaining = core.get('remaining', 5000)
            reset_at = core.get('reset', 0)
            if remaining < 50:
                print(f"⚠️ GitHub API限流接近: 剩余{remaining}，reset@{reset_at}")
            return remaining
    except:
        pass
    return 5000


def get_updated_issues(since_dt=None):
    """
    获取 since 之后有更新的所有issue（含open+recent closed）
    since_dt: datetime对象（UTC）
    """
    issues = []
    # 拉取open+closed，用since过滤
    for state in ['open', 'closed']:
        page = 1
        while True:
            try:
                params = {
                    'state': state,
                    'per_page': 100,
                    'page': page,
                    'sort': 'updated',
                    'direction': 'desc',
                }
                if since_dt:
                    params['since'] = since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                r = requests.get(
                    f'https://api.github.com/repos/{BACKLOG_REPO}/issues',
                    headers=_headers(), params=params, timeout=30
                )
                if r.status_code == 403 and 'rate limit' in r.text.lower():
                    print('🚨 撞到GitHub限流，本轮暂停')
                    return issues
                r.raise_for_status()
                batch = r.json()
                if not batch:
                    break
                issues.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
                time.sleep(0.3)
            except Exception as e:
                print(f"⚠️ 拉issue列表失败(page={page}, state={state}): {e}")
                break
    return issues


def get_issue_events(issue_number):
    """获取单个issue的所有events"""
    events = []
    page = 1
    while True:
        try:
            r = requests.get(
                f'https://api.github.com/repos/{BACKLOG_REPO}/issues/{issue_number}/events',
                headers=_headers(),
                params={'per_page': 100, 'page': page},
                timeout=20
            )
            if r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            events.extend(batch)
            if len(batch) < 100:
                break
            page += 1
            time.sleep(0.2)
        except:
            break
    return events


def get_issue_comments(issue_number):
    """获取单个issue的所有comments"""
    comments = []
    page = 1
    while True:
        try:
            r = requests.get(
                f'https://api.github.com/repos/{BACKLOG_REPO}/issues/{issue_number}/comments',
                headers=_headers(),
                params={'per_page': 100, 'page': page},
                timeout=20
            )
            if r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            comments.extend(batch)
            if len(batch) < 100:
                break
            page += 1
            time.sleep(0.2)
        except:
            break
    return comments


# ==================== 事件识别 ====================

def _is_bot_actor(event):
    """判断事件是否Bot自己产生的"""
    actor = event.get('actor') or {}
    login = (actor.get('login') or '').lower()
    for bot_login in BOT_GITHUB_LOGINS:
        if login == bot_login.lower():
            return True
    return False


def _is_bot_comment(comment):
    """判断评论是否Bot自己发的"""
    user = comment.get('user') or {}
    login = (user.get('login') or '').lower()
    for bot_login in BOT_GITHUB_LOGINS:
        if login == bot_login.lower():
            return True
    return False


def detect_new_events(issue, issue_state, events, comments):
    """
    对比游标，返回新的事件列表（归一化后）
    返回：list[dict] 每个元素是一个归一化事件
    """
    number = str(issue['number'])
    last_event_id = issue_state.get('last_event_id', 0) if issue_state else 0
    last_comment_id = issue_state.get('last_comment_id', 0) if issue_state else 0

    # 新events
    new_events = [e for e in events if e.get('id', 0) > last_event_id and not _is_bot_actor(e)]
    new_comments = [c for c in comments if c.get('id', 0) > last_comment_id and not _is_bot_comment(c)]

    normalized = []

    # --- 处理events ---
    for e in new_events:
        event_type = e.get('event', '')
        ev = {
            'source': 'event',
            'event_id': e['id'],
            'number': issue['number'],
            'title': issue.get('title', ''),
            'issue': issue,
            'actor_login': (e.get('actor') or {}).get('login', ''),
            'created_at': e.get('created_at', ''),
            'raw_event': e,
        }

        if event_type == 'labeled':
            label_name = ((e.get('label') or {}).get('name') or '')
            ev['type'] = 'label_added'
            ev['label'] = label_name
        elif event_type == 'unlabeled':
            label_name = ((e.get('label') or {}).get('name') or '')
            ev['type'] = 'label_removed'
            ev['label'] = label_name
        elif event_type == 'closed':
            ev['type'] = 'issue_closed'
            ev['close_reason'] = issue.get('state_reason', '') or ''
        elif event_type == 'reopened':
            ev['type'] = 'issue_reopened'
        elif event_type == 'assigned':
            ev['type'] = 'issue_assigned'
            ev['assignee'] = ((e.get('assignee') or {}).get('login') or '')
        else:
            # 其他事件类型（renamed/milestoned等）暂时只记录，不单独处理
            ev['type'] = f'other_{event_type}'

        normalized.append(ev)

    # --- 处理comments（用户/考官新评论）---
    for c in new_comments:
        normalized.append({
            'source': 'comment',
            'comment_id': c['id'],
            'type': 'new_comment',
            'number': issue['number'],
            'title': issue.get('title', ''),
            'issue': issue,
            'actor_login': (c.get('user') or {}).get('login', ''),
            'body': c.get('body', '') or '',
            'html_url': c.get('html_url', ''),
            'created_at': c.get('created_at', ''),
            'raw_comment': c,
        })

    # 按时间排序
    normalized.sort(key=lambda x: x.get('created_at', ''))

    return normalized


def detect_new_issue(issue, issue_state):
    """判断是否是从未见过的issue（首次发现）"""
    return issue_state is None


# ==================== 主轮询逻辑 ====================

def poll_once():
    """执行一次轮询，返回待处理事件列表"""
    if not GITHUB_TOKEN:
        print('❌ GITHUB_TOKEN 未配置')
        return []

    state = load_state()
    now_utc = datetime.now(timezone.utc)
    last_poll = state.get('last_poll_at')
    if last_poll:
        try:
            since_dt = datetime.fromisoformat(last_poll.replace('Z', '+00:00'))
            # 多往回1分钟，避免边界漏事件
            since_dt = since_dt - timedelta(minutes=1)
        except:
            since_dt = now_utc - timedelta(minutes=10)
    else:
        # 首次运行，只扫描最近10分钟
        since_dt = now_utc - timedelta(minutes=10)

    # 检查限流
    remaining = _check_rate_limit()
    if remaining < 20:
        print('⚠️ API剩余额度不足，本轮跳过')
        state['last_poll_at'] = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        save_state(state)
        return [{'type': 'rate_limit_warning', 'number': 0, 'title': ''}]

    print(f"🔍 轮询中... since={since_dt.isoformat()}")
    updated_issues = get_updated_issues(since_dt)
    print(f"   发现 {len(updated_issues)} 个有更新的issue")

    all_events = []

    for issue in updated_issues:
        # 跳过pull request
        if issue.get('pull_request'):
            continue

        number = str(issue['number'])
        issue_state = state['issues'].get(number)

        # 1. 新issue识别
        if detect_new_issue(issue, issue_state):
            all_events.append({
                'source': 'system',
                'type': 'new_issue',
                'number': issue['number'],
                'title': issue.get('title', ''),
                'body': issue.get('body', '') or '',
                'issue': issue,
                'author_login': (issue.get('user') or {}).get('login', ''),
            })

        # 2. 拉events和comments，对比游标
        events = get_issue_events(issue['number'])
        comments = get_issue_comments(issue['number'])
        new_evts = detect_new_events(issue, issue_state, events, comments)
        all_events.extend(new_evts)

        # 3. 更新游标
        max_event_id = max((e.get('id', 0) for e in events), default=0)
        max_comment_id = max((c.get('id', 0) for c in comments), default=0)
        cur_labels = [l['name'] for l in issue.get('labels', [])]
        state['issues'][number] = {
            'last_event_id': max(max_event_id, issue_state.get('last_event_id', 0) if issue_state else 0),
            'last_comment_id': max(max_comment_id, issue_state.get('last_comment_id', 0) if issue_state else 0),
            'labels': cur_labels,
            'state': issue.get('state', ''),
            'title': issue.get('title', ''),
            'author_login': (issue.get('user') or {}).get('login', ''),
            'updated_at': issue.get('updated_at', ''),
        }

    state['last_poll_at'] = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    save_state(state)
    return all_events


def run_continuous():
    """持续轮询主循环"""
    Path(LOG_DIR).mkdir(exist_ok=True)
    print(f"🚀 AINOL 产品管家轮询启动，仓库: {BACKLOG_REPO}，间隔: {POLL_INTERVAL}s")
    print(f"   Bot GitHub logins: {BOT_GITHUB_LOGINS}")

    # 延迟导入避免循环
    from pm_actions import handle_event

    while True:
        try:
            events = poll_once()
            if events:
                print(f"📨 检测到 {len(events)} 个新事件")
                for ev in events:
                    ev_type = ev.get('type', '')
                    n = ev.get('number', 0)
                    title = (ev.get('title', '') or '')[:60]
                    print(f"  → #{n} [{ev_type}] {title}")
                    try:
                        handle_event(ev)
                    except Exception as e:
                        import traceback
                        print(f"❌ 处理事件失败 #{n} [{ev_type}]: {e}")
                        traceback.print_exc()
            else:
                print(f"   {time.strftime('%H:%M:%S')} 无新事件")
        except KeyboardInterrupt:
            print("\n👋 停止轮询")
            break
        except Exception as e:
            import traceback
            print(f"❌ 轮询异常: {e}")
            traceback.print_exc()

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == '--once':
            events = poll_once()
            print(f"\n📊 本次检测到 {len(events)} 个事件：")
            for ev in events:
                et = ev.get('type', '')
                n = ev.get('number', 0)
                title = (ev.get('title', '') or '')[:70]
                extra = ''
                if ev.get('label'):
                    extra += f" label={ev['label']}"
                if ev.get('actor_login'):
                    extra += f" by={ev['actor_login']}"
                print(f"  #{n} [{et}]{extra} {title}")
        elif cmd == '--reset':
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
                print(f"🗑️ 已删除 {STATE_FILE}，下次运行将从头开始")
            else:
                print("没有state文件")
        else:
            print(f"未知命令: {cmd}")
            print("用法: python poll_issues.py [--once|--reset]")
    else:
        run_continuous()
