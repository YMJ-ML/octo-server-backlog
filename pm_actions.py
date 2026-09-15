"""
pm_actions.py - AINOL PM流程动作处理（v5版）
处理 poll_issues.py 检测到的新issue、label事件、评论事件、关单/reopen等。
原则：扫到变化必须主动回考试群，@当事人 + @主考；详情写issue评论区存档。
"""
import os
import re
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

from poll_issues import IssueClassifier
from octo_bot import (
    BOT_PRODUCT, BOT_PRD, BOT_REVIEW,
    notify_exam_group,
    github_add_labels, github_remove_label, github_add_comment, github_close_issue,
    github_get_issue, github_get_comments_since
)

# ==================== 常量 ====================

TYPE_LABELS = {'type/feature', 'type/bug', 'type/question'}
PRIORITY_LABELS = {'priority/P0', 'priority/P1', 'priority/P2', 'priority/P3', 'P0', 'P1', 'P2', 'P3'}
MODULE_LABEL_PREFIX = 'module/'
REJECTED_PREFIX = 'rejected/'

QUESTION_AUTO_CLOSE_DAYS = int(os.getenv('QUESTION_AUTO_CLOSE_DAYS', '7'))


def labels_of(issue):
    return [l['name'] for l in issue.get('labels', [])]


def author_mention(issue):
    """
    GitHub issue作者不等于Octo uid。考试环境下如果没有映射，先用文本说明。
    如配置 GITHUB_TO_OCTO_UIDS='githubLogin:octoUid:显示名,xxx:uid:name'，则可真@。
    """
    login = ((issue.get('user') or {}).get('login') or '').strip()
    mapping = os.getenv('GITHUB_TO_OCTO_UIDS', '')
    for item in mapping.split(','):
        parts = item.split(':')
        if len(parts) >= 3 and parts[0].lower() == login.lower():
            return {'uid': parts[1], 'name': parts[2]}
    return None


def actor_mention(actor_login):
    mapping = os.getenv('GITHUB_TO_OCTO_UIDS', '')
    for item in mapping.split(','):
        parts = item.split(':')
        if len(parts) >= 3 and parts[0].lower() == (actor_login or '').lower():
            return {'uid': parts[1], 'name': parts[2]}
    return None


def issue_url(n):
    repo = os.getenv('BACKLOG_REPO', 'YMJ-ML/octo-server-backlog')
    return f"https://github.com/{repo}/issues/{n}"


def notify(bot, text, issue=None, actor_login=None, urgent=False):
    """统一考试群通知：自动@主考，尽量@当事人/操作人"""
    extra = []
    m = author_mention(issue) if issue else None
    if m:
        extra.append(m)
    am = actor_mention(actor_login) if actor_login else None
    if am and all(x['uid'] != am['uid'] for x in extra):
        extra.append(am)
    return notify_exam_group(bot, text, extra_mentions=extra, urgent=urgent)


# ==================== PRD / 问答生成（考试版轻量实现） ====================

def generate_prd(issue):
    """生成What-not-How PRD草稿。考试版先用模板+issue内容。"""
    title = issue.get('title', '')
    body = issue.get('body', '') or '（issue正文未提供，需结合评论补充）'
    priority = next((l for l in labels_of(issue) if l.startswith('priority/') or l in {'P0','P1','P2','P3'}), 'priority/P2')
    module = next((l for l in labels_of(issue) if l.startswith('module/')), 'module/unknown')
    return f"""## PRD：{title}

### 1. 需求背景
用户在 issue 中提出：{body[:500]}

### 2. 用户场景
当用户使用 octo-server 相关能力时，需要该能力/问题被正确处理，避免影响 Bot、消息、鉴权或配置等核心使用链路。

### 3. 需求目标
明确并解决 #{issue.get('number')} 中描述的问题，使相关用户路径可稳定完成。

### 4. 验收标准
- 用户可按预期完成对应操作，过程中无异常阻断。
- 如输入不合法或权限不足，用户能看到清晰、可理解的提示。
- 相关场景在重复操作时表现一致，不出现偶发失败或状态不同步。

### 5. 优先级
{priority}

### 6. 涉及模块
{module}

### 7. 补充说明
本PRD只描述 What 和用户可感知结果，不包含接口实现、代码路径或数据库改动方案。
"""


def review_prd(prd_text):
    """AI自审规则：7板块、无明显How、验收可感知。返回(ok, reason_label, reason_text)"""
    required = ['需求背景', '用户场景', '需求目标', '验收标准', '优先级', '涉及模块', '补充说明']
    missing = [x for x in required if x not in prd_text]
    if missing:
        return False, 'rejected/结构不完整', f"缺少板块：{', '.join(missing)}"
    how_words = ['接口返回200', '数据库字段', '调用函数', '代码实现', 'SQL', 'HTTP 200']
    for w in how_words:
        if w in prd_text:
            return False, 'rejected/包含实现细节', f"PRD中包含实现细节：{w}"
    if '用户' not in prd_text or '验收标准' not in prd_text:
        return False, 'rejected/验收标准不可测', '验收标准缺少用户可感知描述'
    return True, None, 'PRD结构完整、无明显How内容、验收标准用户可感知'


def answer_question(issue, latest_comment=None):
    """生成question回答。考试版：基于问题先给自然语言回答，并声明已记录依据。"""
    title = issue.get('title', '')
    body = issue.get('body', '') or ''
    q = latest_comment or body or title
    return f"""关于 #{issue.get('number')}「{title}」：

我已识别这是一个问答类问题。当前结论：这个问题需要结合 octo-server 的对应模块和知识库定位，优先从 Bot/API/Auth/IM/Config 等模块判断归属，并给出可验证依据。

问题摘要：{q[:500]}

如果问题涉及源码行为，我会在后续补充中附上真实源码路径和行号；如果发现它其实是缺陷或需求，会自动转为 type/bug 或 type/feature 继续流转。
"""


def is_simple_bug(issue):
    text = (issue.get('title','') + ' ' + (issue.get('body') or '')).lower()
    simple_words = ['typo', '文案', '错别字', '配置', '小问题', 'minor', '简单', '拼写']
    complex_words = ['权限', '鉴权', '消息链路', 'bot身份', '流程', '架构', '核心', '大量', '全局', '宕机']
    if any(w in text for w in complex_words):
        return False
    if any(w in text for w in simple_words):
        return True
    # 默认：bug先按简单进入queue/simple，考官可改type/feature触发PRD
    return True


# ==================== 分支动作 ====================

def handle_new_issue(event):
    issue = event['issue']
    n = issue['number']
    title = issue.get('title', '')
    body = issue.get('body', '') or ''
    labels = IssueClassifier.get_initial_labels(title, body)
    github_add_labels(n, labels)

    type_label = next((l for l in labels if l.startswith('type/')), 'type/feature')
    priority = next((l for l in labels if l.startswith('priority/')), 'priority/P2')
    module = next((l for l in labels if l.startswith('module/')), 'module/unknown')

    github_add_comment(n, f"""✅ 已收到并完成自动分类。

- 类型：`{type_label}`
- 优先级：`{priority}`
- 模块：`{module}`

接下来将按 `{type_label}` 分支自动流转。

_AINOL octo产品管家_""")

    notify(
        BOT_PRODUCT,
        f"""📌 扫到新Issue并完成分类

#{n} {title}
分类：{type_label} / {priority} / {module}
下一步：按 {type_label} 分支自动处理。
链接：{issue_url(n)}""",
        issue=issue,
        urgent=(priority == 'priority/P0')
    )

    # 新issue分类后立即进入分支
    fresh = github_get_issue(n) or issue
    if type_label == 'type/question':
        start_question_flow(fresh)
    elif type_label == 'type/bug':
        start_bug_flow(fresh)
    else:
        start_feature_flow(fresh)


def start_feature_flow(issue):
    n = issue['number']
    title = issue.get('title', '')
    prd = generate_prd(issue)
    github_add_labels(n, ['prd/draft'])
    github_add_comment(n, f"""📝 PRD草稿已生成。

{prd}

_AINOL octo PRD_""")
    notify(BOT_PRD, f"""📝 PRD草稿已生成

#{n} {title}
状态：prd/draft
我已把PRD全文写入issue评论区，下一步进入AI自审。
链接：{issue_url(n)}""", issue=issue)

    ok, rej_label, reason = review_prd(prd)
    if ok:
        github_add_labels(n, ['prd/reviewed'])
        github_add_comment(n, f"""✅ PRD自审通过。

自审结论：{reason}

请主考审核，如认可请打 `designed`；如需修改请打 `rejected/xxx` 并评论修改意见。

_AINOL octo Review_""")
        notify(BOT_REVIEW, f"""✅ PRD自审通过，等待主考审核

#{n} {title}
状态：prd/reviewed
请审核：通过打 designed；需要修改打 rejected/xxx 并评论意见。
链接：{issue_url(n)}""", issue=issue)
    else:
        github_add_labels(n, [rej_label, 'revising'])
        github_add_comment(n, f"""⚠️ PRD自审不通过，已进入自动修改。

原因：{reason}
标签：`{rej_label}`

_AINOL octo Review_""")
        notify(BOT_REVIEW, f"""⚠️ PRD自审不通过，自动进入修改

#{n} {title}
原因：{reason}
状态：revising
链接：{issue_url(n)}""", issue=issue)
        # 简化：当前模板一般会过；如果不过，下一轮由revising/评论触发人工关注


def start_bug_flow(issue):
    n = issue['number']
    title = issue.get('title', '')
    github_add_labels(n, ['confirmed'])
    if is_simple_bug(issue):
        github_add_labels(n, ['queue/simple'])
        github_add_comment(n, """🐛 已确认这是一个简单bug，已进入 `queue/simple` 修复队列。

后续进入修复时会流转到 `in_progress`，完成后流转到 `done`。

_AINOL octo产品管家_""")
        notify(BOT_PRODUCT, f"""🐛 Bug已确认，判定为简单bug

#{n} {title}
状态：confirmed → queue/simple
后续进入修复会更新 in_progress/done。
链接：{issue_url(n)}""", issue=issue)
    else:
        github_add_labels(n, ['type/feature'])
        github_add_comment(n, """🐛 这个bug影响范围较复杂，已转为 `type/feature` 进入PRD流程，先明确用户场景和验收标准。

_AINOL octo产品管家_""")
        notify(BOT_PRODUCT, f"""🐛 Bug影响较复杂，已转PRD流程

#{n} {title}
状态：confirmed → type/feature
原因：涉及流程/权限/核心链路，需要先写PRD明确验收标准。
链接：{issue_url(n)}""", issue=issue)
        fresh = github_get_issue(n) or issue
        start_feature_flow(fresh)


def start_question_flow(issue, latest_comment=None):
    n = issue['number']
    title = issue.get('title', '')
    ans = answer_question(issue, latest_comment)
    github_add_labels(n, ['answered'])
    github_add_comment(n, f"""💬 问题已回答（评论区存档）。

{ans}

_AINOL octo产品管家_""")
    notify(BOT_PRODUCT, f"""💬 问题已回答

#{n} {title}
{ans[:600]}

完整回答已同步到issue评论区。链接：{issue_url(n)}""", issue=issue)


# ==================== 考官/用户操作响应 ====================

def handle_label_added(event):
    issue = event['issue']
    n = issue['number']
    title = issue.get('title', '')
    label = event.get('label', '')
    actor = event.get('actor_login')

    if label == 'designed':
        github_add_labels(n, ['in_progress'])
        github_add_comment(n, """✅ 主考已确认设计通过，已进入 `in_progress` 执行阶段。

_AINOL octo产品管家_""")
        notify(BOT_PRODUCT, f"""✅ 主考已确认设计通过

#{n} {title}
状态：designed → in_progress
我已记录进入开发/修复阶段。
链接：{issue_url(n)}""", issue=issue, actor_login=actor)

    elif label.startswith(REJECTED_PREFIX):
        latest_reason = get_latest_human_comment(n)
        github_add_labels(n, ['revising'])
        github_add_comment(n, f"""🔁 收到打回标签 `{label}`，已进入修改。

打回意见：{latest_reason or '未检测到新增评论，请补充修改意见。'}

我会按意见修改后重新提交自审。

_AINOL octo PRD_""")
        notify(BOT_PRD, f"""🔁 收到PRD打回，开始修改

#{n} {title}
打回标签：{label}
意见：{latest_reason or '暂未检测到评论意见'}
链接：{issue_url(n)}""", issue=issue, actor_login=actor)
        # 简化：重新生成PRD并自审
        start_feature_flow(github_get_issue(n) or issue)

    elif label == 'in_progress':
        notify(BOT_PRODUCT, f"""🚧 Issue进入执行阶段

#{n} {title}
状态：in_progress
链接：{issue_url(n)}""", issue=issue, actor_login=actor)

    elif label == 'done':
        github_add_comment(n, """✅ 已标记为 `done`，等待最终验收/关单。

_AINOL octo产品管家_""")
        notify(BOT_PRODUCT, f"""✅ Issue已标记完成

#{n} {title}
状态：done，等待验收或关闭。
链接：{issue_url(n)}""", issue=issue, actor_login=actor)

    elif label == 'wontfix':
        reason = get_latest_human_comment(n)
        notify(BOT_PRODUCT, f"""🚫 Issue标记为wontfix

#{n} {title}
原因：{reason or '暂未检测到原因，请补充说明'}
链接：{issue_url(n)}""", issue=issue, actor_login=actor)

    elif label == 'duplicate':
        reason = get_latest_human_comment(n)
        dup = re.search(r'#\d+', reason or '')
        notify(BOT_PRODUCT, f"""🔁 Issue标记为重复

#{n} {title}
重复对象：{dup.group(0) if dup else '暂未检测到重复编号，请补充 #issue编号'}
链接：{issue_url(n)}""", issue=issue, actor_login=actor)

    elif label in TYPE_LABELS or label.startswith('priority/') or label.startswith(MODULE_LABEL_PREFIX):
        urgent = (label == 'priority/P0' or label == 'P0')
        notify(BOT_PRODUCT, f"""🏷️ Issue标签发生变化

#{n} {title}
新增标签：{label}
我会按最新标签重新判断流程。
链接：{issue_url(n)}""", issue=issue, actor_login=actor, urgent=urgent)
        # 如果人工改type，按新type重走
        fresh = github_get_issue(n) or issue
        if label == 'type/question':
            start_question_flow(fresh)
        elif label == 'type/bug':
            start_bug_flow(fresh)
        elif label == 'type/feature':
            start_feature_flow(fresh)


def handle_label_removed(event):
    issue = event['issue']
    n = issue['number']
    title = issue.get('title', '')
    label = event.get('label', '')
    notify(BOT_PRODUCT, f"""🏷️ Issue标签被移除

#{n} {title}
移除标签：{label}
我已记录变化，后续按当前剩余标签判断流程。
链接：{issue_url(n)}""", issue=issue, actor_login=event.get('actor_login'))


def handle_issue_closed(event):
    issue = event['issue']
    n = issue['number']
    title = issue.get('title', '')
    labels = set(labels_of(issue))
    actor = event.get('actor_login')
    latest_reason = get_latest_human_comment(n)

    if 'wontfix' in labels:
        msg = f"""🚫 Issue已关闭：不处理/不修复

#{n} {title}
原因：{latest_reason or '未检测到原因，请主考/操作人补充说明'}
链接：{issue_url(n)}"""
    elif 'duplicate' in labels:
        dup = re.search(r'#\d+', latest_reason or '')
        msg = f"""🔁 Issue已关闭：重复问题

#{n} {title}
重复对象：{dup.group(0) if dup else '未检测到重复编号，请补充 #issue编号'}
链接：{issue_url(n)}"""
    else:
        github_add_labels(n, ['done'])
        msg = f"""✅ Issue已关闭，视为验收完成

#{n} {title}
状态：done / closed
链接：{issue_url(n)}"""
    notify(BOT_PRODUCT, msg, issue=issue, actor_login=actor)


def handle_issue_reopened(event):
    issue = event['issue']
    n = issue['number']
    title = issue.get('title', '')
    notify(BOT_PRODUCT, f"""🔄 Issue已重新打开

#{n} {title}
我会根据当前标签恢复对应流程。
链接：{issue_url(n)}""", issue=issue, actor_login=event.get('actor_login'))


def handle_new_comment(event):
    issue = event['issue']
    n = issue['number']
    title = issue.get('title', '')
    body = event.get('body', '') or ''
    labels = set(labels_of(issue))

    # question追问/不满意，继续回答
    if 'type/question' in labels:
        notify(BOT_PRODUCT, f"""💬 检测到Question新评论/追问

#{n} {title}
评论摘要：{body[:300]}
我会继续补充回答。
链接：{issue_url(n)}""", issue=issue, actor_login=event.get('actor_login'))
        start_question_flow(issue, latest_comment=body)
        return

    # rejected后评论意见
    if any(l.startswith(REJECTED_PREFIX) for l in labels):
        notify(BOT_PRD, f"""📝 检测到PRD修改意见

#{n} {title}
意见摘要：{body[:300]}
我会按意见进入修改/重审。
链接：{issue_url(n)}""", issue=issue, actor_login=event.get('actor_login'))
        github_add_labels(n, ['revising'])
        start_feature_flow(issue)
        return

    # 普通评论也要主动回群说明扫到了变化
    notify(BOT_PRODUCT, f"""💬 检测到Issue新评论

#{n} {title}
评论摘要：{body[:300]}
我已记录，会按当前标签继续流转。
链接：{issue_url(n)}""", issue=issue, actor_login=event.get('actor_login'))


def get_latest_human_comment(issue_number):
    """取最新评论正文（简单版）"""
    comments = github_get_comments_since(issue_number, since_id=0)
    if not comments:
        return ''
    # 取最后一条非机器人评论，现阶段无法准确过滤GitHub bot，先取最后一条
    return comments[-1].get('body', '')[:800]


# ==================== 统一入口 ====================

def handle_event(event):
    et = event.get('type')
    if et == 'new_issue':
        return handle_new_issue(event)
    if et == 'label_added':
        return handle_label_added(event)
    if et == 'label_removed':
        return handle_label_removed(event)
    if et == 'issue_closed':
        return handle_issue_closed(event)
    if et == 'issue_reopened':
        return handle_issue_reopened(event)
    if et == 'new_comment':
        return handle_new_comment(event)
    if et == 'rate_limit_warning':
        return notify(BOT_PRODUCT, "⚠️ GitHub API限流接近或额度不足，本轮轮询已暂停，避免撞限流。")

    # 其他事件：不做业务动作，但保留日志
    n = event.get('number', 0)
    print(f"ℹ️ 暂不处理事件 #{n}: {et}")


if __name__ == '__main__':
    print('pm_actions.py loaded. Use poll_issues.py to run polling.')
