#!/bin/bash
# AINOL Cron: run_poll.sh 每5分钟跑一次（轮询backlog新issue/事件→发考试群通知）
# 严格遵守规则5：无产出不发群消息，只写日志
cd /home/mlclaw/.openclaw/workspace/AINOL_Backlog
python3 -u -c "
import sys, asyncio
sys.path.insert(0, '.')
from poll_issues import poll_once
from pm_actions import handle_event
events = poll_once()
if events:
    for ev in events:
        try:
            handle_event(ev)
        except Exception as e:
            import traceback
            traceback.print_exc()
" >> logs/cron_poll.log 2>&1
