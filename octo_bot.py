"""
octo_bot.py - Octo Bot API 消息工具
支持：群消息、@单/多人蓝色高亮、私聊
配置从环境变量或openclaw config读取
"""
import os
import json
import time
import subprocess
import tempfile
import requests
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

# ==================== 配置读取 ====================

def _get_bot_token(bot_key):
    """从OpenClaw配置或环境变量获取bot token"""
    candidates = [bot_key]
    # 自动补全_bot后缀或去掉_bot后缀
    if not bot_key.endswith('_bot'):
        candidates.append(bot_key + '_bot')
    else:
        candidates.append(bot_key.replace('_bot', ''))
    for account in candidates:
        try:
            r = subprocess.run(
                ['openclaw', 'config', 'get', f'channels.octo.accounts.{account}.botToken'],
                capture_output=True, text=True, timeout=5
            )
            token = r.stdout.strip().strip('"')
            if token and len(token) > 20:
                return token
        except:
            pass
    # fallback环境变量
    env_key = bot_key.upper().replace('-', '_') + '_TOKEN'
    return os.getenv(env_key, os.getenv('OCTO_BOT_TOKEN', ''))


def _get_api_url():
    try:
        r = subprocess.run(
            ['openclaw', 'config', 'get', 'channels.octo.apiUrl'],
            capture_output=True, text=True, timeout=5
        )
        url = r.stdout.strip().strip('"').rstrip('/')
        if url:
            return url
    except:
        pass
    return os.getenv('OCTO_API_URL', 'https://im.deepminer.com.cn/api')


# ==================== 底层发送 ====================

def _send_message(bot_key, channel_id, channel_type, text, mentions=None):
    """
    底层消息发送
    channel_type: 1=私聊, 2=群聊
    mentions: [{'uid': 'xxx', 'offset': N, 'length': M}, ...]
    """
    token = _get_bot_token(bot_key)
    api_url = _get_api_url()
    if not token:
        print(f"❌ 找不到bot {bot_key}的token")
        return False

    payload = {
        'channel_id': channel_id,
        'channel_type': channel_type,
        'payload': {'type': 1, 'content': text}
    }
    if mentions:
        payload['payload']['mention'] = {'entities': mentions}

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
        pf = f.name
    try:
        r = subprocess.run(
            ['curl', '-sS', '-X', 'POST', f'{api_url}/v1/bot/sendMessage',
             '-H', f'Authorization: Bearer {token}',
             '-H', 'Content-Type: application/json',
             '-d', f'@{pf}'],
            capture_output=True, text=True, timeout=15
        )
        os.unlink(pf)
        try:
            resp = json.loads(r.stdout)
            ok = 'message_id' in resp
            if not ok:
                print(f"⚠️ 发送返回: {r.stdout[:200]}")
            return ok
        except:
            print(f"⚠️ 发送返回非JSON: {r.stdout[:200]}")
            return False
    except Exception as e:
        if os.path.exists(pf):
            os.unlink(pf)
        print(f"❌ 发消息异常: {e}")
        return False


# ==================== 公开接口 ====================

def send_group(bot_key, group_no, text, mentions=None):
    """
    发群消息
    bot_key: bot标识，如 'wuxidixi' 或 robot_id
    group_no: 群号
    text: 消息文本
    mentions: mention实体列表（可由build_mentions生成）
    """
    return _send_message(bot_key, group_no, 2, text, mentions)


def send_dm(bot_key, uid, text):
    """发私聊"""
    return _send_message(bot_key, uid, 1, text)


def build_mentions(text, mentions_list):
    """
    在文本中插入@并构建mention.entities
    mentions_list: [{'uid': 'xxx', 'name': '张三'}, ...] 按顺序
    会在text开头依次插入 @xxx，自动计算offset/length
    
    返回 (final_text, entities)
    """
    parts = []
    entities = []
    current_offset = 0

    for m in mentions_list:
        mention_text = f"@{m['name']}"
        parts.append(mention_text)
        entities.append({
            'uid': m['uid'],
            'offset': current_offset,
            'length': len(mention_text.encode('utf-8')) if False else len(mention_text)
        })
        current_offset += len(mention_text)
        parts.append(' ')
        current_offset += 1

    # @人之后空行，再是正文
    parts.append('\n')
    current_offset += 1

    final_text = ''.join(parts) + text
    return final_text, entities


def notify_group(bot_key, group_no, text, mention_uids=None, exam_group=None, examiner_uid=None, examiner_name='主考'):
    """
    便捷发群通知：自动@当事人+@主考
    bot_key: 用哪个bot发
    group_no: 群号（优先用传入值，否则用EXAM_GROUP环境变量）
    text: 消息正文
    mention_uids: [{'uid': 'xxx', 'name': '张三'}, ...] 额外@的人（当事人）
    examiner_uid/examiner_name: 主考信息，始终@
    """
    group = group_no or exam_group or os.getenv('OCTO_EXAM_GROUP', '')
    if not group:
        print(f"[通知-DRYRUN] {text[:200]}")
        return True

    mentions_to_add = []

    # 始终@主考
    e_uid = examiner_uid or os.getenv('OCTO_MAIN_EXAMINER', '')
    e_name = examiner_name or os.getenv('OCTO_MAIN_EXAMINER_NAME', '主考')
    if e_uid:
        mentions_to_add.append({'uid': e_uid, 'name': e_name})

    # @当事人
    if mention_uids:
        mentions_to_add.extend(mention_uids)

    final_text, entities = build_mentions(text, mentions_to_add)
    return send_group(bot_key, group, final_text, entities if entities else None)


# ==================== 便捷函数：直接从环境变量读考试群+主考 ====================

EXAM_GROUP = os.getenv('OCTO_EXAM_GROUP', '')
EXAMINER_UID = os.getenv('OCTO_MAIN_EXAMINER', '')
EXAMINER_NAME = os.getenv('OCTO_MAIN_EXAMINER_NAME', '主考')
BOT_PRODUCT = os.getenv('BOT_PRODUCT', 'wuxidixi')
BOT_PRD = os.getenv('BOT_PRD', BOT_PRODUCT)
BOT_REVIEW = os.getenv('BOT_REVIEW', BOT_PRODUCT)


def notify_exam_group(bot_key, text, extra_mentions=None, urgent=False):
    """
    最简便：发考试群消息，自动@主考
    bot_key: 用哪个bot
    text: 正文
    extra_mentions: [{'uid','name'}, ...] 额外@的当事人
    urgent: 是否加🔴标识
    """
    if urgent:
        text = '🔴【紧急】\n' + text
    return notify_group(
        bot_key=bot_key,
        group_no=EXAM_GROUP,
        text=text,
        mention_uids=extra_mentions,
        examiner_uid=EXAMINER_UID,
        examiner_name=EXAMINER_NAME
    )


# ==================== GitHub API工具（评论区操作） ====================

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
BACKLOG_REPO = os.getenv('BACKLOG_REPO', 'YMJ-ML/octo-server-backlog')


def github_headers():
    return {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }


def github_add_labels(issue_number, labels):
    """给issue加标签"""
    if not labels:
        return
    try:
        r = requests.post(
            f'https://api.github.com/repos/{BACKLOG_REPO}/issues/{issue_number}/labels',
            headers=github_headers(), json={'labels': labels}, timeout=15
        )
        if r.status_code not in (200, 201):
            print(f"⚠️ 加标签失败 #{issue_number}: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"⚠️ 加标签异常 #{issue_number}: {e}")


def github_remove_label(issue_number, label):
    """删单个标签"""
    try:
        requests.delete(
            f'https://api.github.com/repos/{BACKLOG_REPO}/issues/{issue_number}/labels/{requests.utils.quote(label)}',
            headers=github_headers(), timeout=15
        )
    except Exception as e:
        print(f"⚠️ 删标签异常 #{issue_number}/{label}: {e}")


def github_add_comment(issue_number, body):
    """给issue加评论"""
    try:
        r = requests.post(
            f'https://api.github.com/repos/{BACKLOG_REPO}/issues/{issue_number}/comments',
            headers=github_headers(), json={'body': body}, timeout=20
        )
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"⚠️ 加评论异常 #{issue_number}: {e}")
        return False


def github_close_issue(issue_number):
    """关闭issue"""
    try:
        requests.patch(
            f'https://api.github.com/repos/{BACKLOG_REPO}/issues/{issue_number}',
            headers=github_headers(), json={'state': 'closed'}, timeout=15
        )
    except Exception as e:
        print(f"⚠️ 关单异常 #{issue_number}: {e}")


def github_get_issue(issue_number):
    """获取单个issue详情"""
    try:
        r = requests.get(
            f'https://api.github.com/repos/{BACKLOG_REPO}/issues/{issue_number}',
            headers=github_headers(), timeout=15
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"⚠️ 获取issue异常 #{issue_number}: {e}")
    return None


def github_get_comments_since(issue_number, since_id=None):
    """获取issue的评论，可从since_id之后增量"""
    comments = []
    page = 1
    while True:
        try:
            r = requests.get(
                f'https://api.github.com/repos/{BACKLOG_REPO}/issues/{issue_number}/comments',
                headers=github_headers(),
                params={'per_page': 100, 'page': page},
                timeout=15
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
        except:
            break
    if since_id:
        comments = [c for c in comments if c['id'] > since_id]
    return comments


def github_get_events_since(issue_number, since_id=None):
    """获取issue的events，可从since_id之后增量"""
    events = []
    page = 1
    while True:
        try:
            r = requests.get(
                f'https://api.github.com/repos/{BACKLOG_REPO}/issues/{issue_number}/events',
                headers=github_headers(),
                params={'per_page': 100, 'page': page},
                timeout=15
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
        except:
            break
    if since_id:
        events = [e for e in events if e['id'] > since_id]
    return events


def github_get_user_name(uid_or_login):
    """
    尝试将GitHub login转成可显示名字
    简单版本：直接用login作为显示名
    """
    return uid_or_login


def github_get_issue_author(issue):
    """从issue对象提取作者login"""
    user = issue.get('user') or {}
    return user.get('login', '')


if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 4:
        bot = sys.argv[1]
        group = sys.argv[2]
        text = ' '.join(sys.argv[3:])
        ok = send_group(bot, group, text)
        print(f"发送{'成功' if ok else '失败'}")
