#!/bin/bash
# AINOL Cron: run_pm.sh 每15分钟跑一次（PRD+Review流程推进）
# 严格遵守规则5：无产出不发群消息，只写日志；有产出才发批量汇总消息
cd /home/mlclaw/.openclaw/workspace/AINOL_Backlog
set -a
source ./config.env
set +a
python3 -u run_pm_octo.py --once >> logs/cron_pm.log 2>&1
