#!/bin/bash
# AINOL Cron: run_sync.sh 每5分钟跑一次（产品管家同步issue）
# 严格遵守规则5：无产出不发群消息，只写日志
cd /home/mlclaw/.openclaw/workspace/AINOL_Backlog
set -a
source ./config.env
set +a
python3 -u run_sync_octo.py --once >> logs/cron_sync.log 2>&1
