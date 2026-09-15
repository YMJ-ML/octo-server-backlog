#!/usr/bin/env python3
"""AINOL 多Bot消息发送工具 - 支持三个角色bot各自用自己身份发消息"""
import json
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path('/home/mlclaw/.openclaw/openclaw.json')
API_URL = 'https://im.deepminer.com.cn/api'

# 三个考试Bot的账号映射
BOT_ACCOUNTS = {
    'wuguanjia': '288xq13tm5a4f369a69_bot',  # octo产品管家 (A1)
    'prd': '288zjw1tfpzd99e9672_bot',         # octo PRD (A2)
    'review': '288zkcwrkt862dbd28c_bot',      # octo Review (A3)
    'wuxidixi': 'wuxidixi',                   # 唔西迪西（备用/调试）
}

def load_token(account_name):
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    accounts = cfg['channels']['octo']['accounts']
    if account_name not in accounts:
        raise ValueError(f"Account {account_name} not found in config")
    return accounts[account_name]['botToken']

def send_text(target, content, bot_role='wuguanjia', channel_type=2):
    """以指定bot角色发送消息到群
    bot_role: wuguanjia / prd / review / wuxidixi
    """
    account = BOT_ACCOUNTS.get(bot_role, BOT_ACCOUNTS['wuguanjia'])
    token = load_token(account)
    payload = {
        'channel_id': target,
        'channel_type': int(channel_type),
        'payload': {'type': 1, 'content': content},
    }
    res = subprocess.run([
        'curl', '-sS', '-X', 'POST', f'{API_URL}/v1/bot/sendMessage',
        '-H', f'Authorization: Bearer {token}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps(payload, ensure_ascii=False),
    ], capture_output=True, text=True, timeout=20)
    if res.returncode != 0:
        return {'success': False, 'error': f'curl failed: {res.stderr[:300]}', 'account': account}
    try:
        data = json.loads(res.stdout)
    except Exception:
        return {'success': False, 'error': f'bad json: {res.stdout[:300]}', 'account': account}
    if 'message_id' not in data:
        return {'success': False, 'error': str(data), 'account': account}
    return {'success': True, 'message_id': data['message_id'], 'account': account, 'bot_role': bot_role}


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print('用法: python3 send_ainol_bot.py <bot_role> <target> <内容> [channel_type]')
        print('bot_role: wuguanjia(产品管家)/prd/review/wuxidixi')
        print('channel_type: 2=群(默认)')
        sys.exit(1)
    bot_role = sys.argv[1]
    target = sys.argv[2]
    content = sys.argv[3]
    channel_type = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    result = send_text(target, content, bot_role, channel_type)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['success'] else 1)
