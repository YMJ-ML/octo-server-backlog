"""
AINOL Agent Architecture - Shared Library
Provides unified interfaces for AI platforms, GitHub, PM, and utilities.
"""

import os
import json
import logging
import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv
import requests
from functools import lru_cache
from pathlib import Path

# ============================================================================
# Configuration Loading
# ============================================================================

load_dotenv('config.env')

class Config:
    """Configuration management"""
    
    # GitHub
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
    GITHUB_REPO_OWNER = os.getenv('GITHUB_REPO_OWNER')
    GITHUB_REPO_NAME = os.getenv('GITHUB_REPO_NAME')
    GITHUB_REPO_URL = os.getenv('GITHUB_REPO_URL')
    GITHUB_POLL_INTERVAL = int(os.getenv('GITHUB_POLL_INTERVAL', 300))
    
    # AI Platforms
    KIMI_API_KEY = os.getenv('KIMI_API_KEY')
    KIMI_API_URL = os.getenv('KIMI_API_URL', 'https://api.moonshot.cn/openai/v1')
    KIMI_MODEL = os.getenv('KIMI_MODEL', 'moonshot-v1-8k')
    
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
    DEEPSEEK_API_URL = os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1')
    DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
    
    YUANPAO_API_KEY = os.getenv('YUANPAO_API_KEY')
    YUANPAO_API_URL = os.getenv('YUANPAO_API_URL', 'https://api.baidu.com/api/v1')
    YUANPAO_MODEL = os.getenv('YUANPAO_MODEL', 'eb-instant')
    
    QIANWEN_API_KEY = os.getenv('QIANWEN_API_KEY')
    QIANWEN_API_URL = os.getenv('QIANWEN_API_URL', 'https://dashscope.aliyuncs.com/api/v1')
    QIANWEN_MODEL = os.getenv('QIANWEN_MODEL', 'qwen-max')
    
    BAIDU_AI_API_KEY = os.getenv('BAIDU_AI_API_KEY')
    BAIDU_AI_SECRET_KEY = os.getenv('BAIDU_AI_SECRET_KEY')
    BAIDU_AI_MODEL = os.getenv('BAIDU_AI_MODEL', 'ernie-4.0-turbo-8k')
    
    DOUBAO_API_KEY = os.getenv('DOUBAO_API_KEY')
    DOUBAO_API_URL = os.getenv('DOUBAO_API_URL', 'https://api.doubao.com/v1')
    DOUBAO_MODEL = os.getenv('DOUBAO_MODEL', 'doubao-pro')
    
    # Polling & Concurrency
    CONCURRENT_REQUESTS = int(os.getenv('CONCURRENT_REQUESTS', 3))
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 30))
    
    # PM Configuration
    PM_API_URL = os.getenv('PM_API_URL')
    PM_API_TOKEN = os.getenv('PM_API_TOKEN')
    PM_PROJECT_ID = os.getenv('PM_PROJECT_ID')
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'logs/ainol.log')
    LOG_TO_CONSOLE = os.getenv('LOG_TO_CONSOLE', 'true').lower() == 'true'
    
    # Knowledge Base
    KNOWLEDGE_BASE_PATH = os.getenv('KNOWLEDGE_BASE_PATH', './AINOL_Knowledge_Base_9_Domains.md')
    KNOWLEDGE_BASE_REFRESH_INTERVAL = int(os.getenv('KNOWLEDGE_BASE_REFRESH_INTERVAL', 3600))
    
    # Cache
    CACHE_TYPE = os.getenv('CACHE_TYPE', 'memory')
    CACHE_TTL = int(os.getenv('CACHE_TTL', 600))
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Environment
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
    PROJECT_NAME = os.getenv('PROJECT_NAME', 'AINOL Agent Architecture')
    VERSION = os.getenv('VERSION', '1.0.0')


# ============================================================================
# Logging Setup
# ============================================================================

def setup_logger(name: str) -> logging.Logger:
    """Setup logger with console and file output"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, Config.LOG_LEVEL))
    
    # Create logs directory if not exists
    log_dir = os.path.dirname(Config.LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # File handler
    fh = logging.FileHandler(Config.LOG_FILE)
    fh.setLevel(getattr(logging, Config.LOG_LEVEL))
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(getattr(logging, Config.LOG_LEVEL))
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(fh)
        if Config.LOG_TO_CONSOLE:
            logger.addHandler(ch)
    
    return logger

logger = setup_logger('AINOL')


# ============================================================================
# Cache Management
# ============================================================================

class Cache:
    """Simple in-memory cache (can be extended for Redis)"""
    
    _store: Dict[str, tuple] = {}
    
    @classmethod
    def set(cls, key: str, value: Any, ttl: Optional[int] = None):
        """Set cache value"""
        ttl = ttl or Config.CACHE_TTL
        cls._store[key] = (value, datetime.now().timestamp() + ttl)
        logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
    
    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        """Get cache value (returns None if expired or not found)"""
        if key not in cls._store:
            return None
        
        value, expiry = cls._store[key]
        if datetime.now().timestamp() > expiry:
            del cls._store[key]
            logger.debug(f"Cache expired: {key}")
            return None
        
        logger.debug(f"Cache hit: {key}")
        return value
    
    @classmethod
    def clear(cls):
        """Clear all cache"""
        cls._store.clear()
        logger.info("Cache cleared")


# ============================================================================
# Knowledge Base Management
# ============================================================================

class KnowledgeBase:
    """Knowledge base loader and manager"""
    
    _content: Optional[str] = None
    _loaded_at: Optional[float] = None
    
    @classmethod
    def load(cls) -> str:
        """Load knowledge base from file"""
        cache_key = "kb_content"
        cached = Cache.get(cache_key)
        
        if cached:
            return cached
        
        try:
            kb_path = Config.KNOWLEDGE_BASE_PATH
            if not os.path.exists(kb_path):
                logger.warning(f"Knowledge base not found: {kb_path}")
                return ""
            
            with open(kb_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            Cache.set(cache_key, content, Config.KNOWLEDGE_BASE_REFRESH_INTERVAL)
            logger.info(f"Knowledge base loaded: {len(content)} chars")
            return content
        except Exception as e:
            logger.error(f"Failed to load knowledge base: {e}")
            return ""
    
    @classmethod
    def search(cls, query: str, max_results: int = 5) -> List[str]:
        """Search knowledge base (simple keyword matching)"""
        content = cls.load()
        lines = content.split('\n')
        
        results = []
        for line in lines:
            if query.lower() in line.lower():
                results.append(line.strip())
                if len(results) >= max_results:
                    break
        
        logger.debug(f"KB search '{query}': {len(results)} results")
        return results


# ============================================================================
# GitHub API Wrapper
# ============================================================================

class GitHubAPI:
    """GitHub API operations"""
    
    BASE_URL = "https://api.github.com"
    HEADERS = {
        "Authorization": f"token {Config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    @classmethod
    def get_issues(cls, state: str = 'open', labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get issues from repository"""
        try:
            url = f"{cls.BASE_URL}/repos/{Config.GITHUB_REPO_OWNER}/{Config.GITHUB_REPO_NAME}/issues"
            params = {
                'state': state,
                'per_page': 100
            }
            
            if labels:
                params['labels'] = ','.join(labels)
            
            response = requests.get(url, headers=cls.HEADERS, params=params, timeout=Config.REQUEST_TIMEOUT)
            response.raise_for_status()
            
            issues = response.json()
            logger.info(f"Retrieved {len(issues)} issues from GitHub (state={state})")
            return issues
        except Exception as e:
            logger.error(f"Failed to get GitHub issues: {e}")
            return []
    
    @classmethod
    def get_issue_details(cls, issue_number: int) -> Optional[Dict[str, Any]]:
        """Get detailed issue information"""
        try:
            url = f"{cls.BASE_URL}/repos/{Config.GITHUB_REPO_OWNER}/{Config.GITHUB_REPO_NAME}/issues/{issue_number}"
            response = requests.get(url, headers=cls.HEADERS, timeout=Config.REQUEST_TIMEOUT)
            response.raise_for_status()
            
            logger.debug(f"Retrieved issue #{issue_number} details")
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get issue #{issue_number}: {e}")
            return None
    
    @classmethod
    def create_issue(cls, title: str, body: str, labels: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Create new GitHub issue"""
        try:
            url = f"{cls.BASE_URL}/repos/{Config.GITHUB_REPO_OWNER}/{Config.GITHUB_REPO_NAME}/issues"
            payload = {
                'title': title,
                'body': body,
                'labels': labels or []
            }
            
            response = requests.post(url, headers=cls.HEADERS, json=payload, timeout=Config.REQUEST_TIMEOUT)
            response.raise_for_status()
            
            issue = response.json()
            logger.info(f"Created GitHub issue: {issue['number']}")
            return issue
        except Exception as e:
            logger.error(f"Failed to create GitHub issue: {e}")
            return None
    
    @classmethod
    def add_comment(cls, issue_number: int, body: str) -> Optional[Dict[str, Any]]:
        """Add comment to GitHub issue"""
        try:
            url = f"{cls.BASE_URL}/repos/{Config.GITHUB_REPO_OWNER}/{Config.GITHUB_REPO_NAME}/issues/{issue_number}/comments"
            payload = {'body': body}
            
            response = requests.post(url, headers=cls.HEADERS, json=payload, timeout=Config.REQUEST_TIMEOUT)
            response.raise_for_status()
            
            logger.info(f"Added comment to issue #{issue_number}")
            return response.json()
        except Exception as e:
            logger.error(f"Failed to add comment to issue #{issue_number}: {e}")
            return None


# ============================================================================
# AI Platform Wrappers
# ============================================================================

class AIAgent:
    """Base AI agent class"""
    
    def __init__(self, name: str, api_key: str, api_url: str, model: str):
        self.name = name
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.logger = setup_logger(f"AINOL.{name}")
    
    def query(self, prompt: str, context: Optional[str] = None) -> str:
        """Query AI platform (to be implemented by subclasses)"""
        raise NotImplementedError


class KimiAgent(AIAgent):
    """Kimi AI Agent"""
    
    def __init__(self):
        super().__init__("Kimi", Config.KIMI_API_KEY, Config.KIMI_API_URL, Config.KIMI_MODEL)
    
    def query(self, prompt: str, context: Optional[str] = None) -> str:
        """Query Kimi API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            messages = []
            if context:
                messages.append({"role": "system", "content": context})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7
            }
            
            response = requests.post(
                f"{self.api_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=Config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            result = response.json()
            answer = result['choices'][0]['message']['content']
            self.logger.debug(f"Kimi query successful: {len(answer)} chars")
            return answer
        except Exception as e:
            self.logger.error(f"Kimi query failed: {e}")
            return ""


class DeepSeekAgent(AIAgent):
    """DeepSeek AI Agent"""
    
    def __init__(self):
        super().__init__("DeepSeek", Config.DEEPSEEK_API_KEY, Config.DEEPSEEK_API_URL, Config.DEEPSEEK_MODEL)
    
    def query(self, prompt: str, context: Optional[str] = None) -> str:
        """Query DeepSeek API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            messages = []
            if context:
                messages.append({"role": "system", "content": context})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7
            }
            
            response = requests.post(
                f"{self.api_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=Config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            result = response.json()
            answer = result['choices'][0]['message']['content']
            self.logger.debug(f"DeepSeek query successful: {len(answer)} chars")
            return answer
        except Exception as e:
            self.logger.error(f"DeepSeek query failed: {e}")
            return ""


class YuanpaoAgent(AIAgent):
    """Yuanpao (Baidu) AI Agent"""
    
    def __init__(self):
        super().__init__("Yuanpao", Config.YUANPAO_API_KEY, Config.YUANPAO_API_URL, Config.YUANPAO_MODEL)
    
    def query(self, prompt: str, context: Optional[str] = None) -> str:
        """Query Yuanpao API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            messages = []
            if context:
                messages.append({"role": "system", "content": context})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "messages": messages,
                "model": self.model
            }
            
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=Config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            result = response.json()
            answer = result['result']
            self.logger.debug(f"Yuanpao query successful: {len(answer)} chars")
            return answer
        except Exception as e:
            self.logger.error(f"Yuanpao query failed: {e}")
            return ""


class QianwenAgent(AIAgent):
    """Qianwen (Alibaba) AI Agent"""
    
    def __init__(self):
        super().__init__("Qianwen", Config.QIANWEN_API_KEY, Config.QIANWEN_API_URL, Config.QIANWEN_MODEL)
    
    def query(self, prompt: str, context: Optional[str] = None) -> str:
        """Query Qianwen API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            messages = []
            if context:
                messages.append({"role": "system", "content": context})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.model,
                "messages": messages
            }
            
            response = requests.post(
                f"{self.api_url}/services/aigc/text-generation/generation",
                headers=headers,
                json=payload,
                timeout=Config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            result = response.json()
            answer = result['output']['text']
            self.logger.debug(f"Qianwen query successful: {len(answer)} chars")
            return answer
        except Exception as e:
            self.logger.error(f"Qianwen query failed: {e}")
            return ""


class BaiduAIAgent(AIAgent):
    """Baidu AI (Wenxin) Agent"""
    
    def __init__(self):
        super().__init__("BaiduAI", Config.BAIDU_AI_API_KEY, "https://api.baidu.com", Config.BAIDU_AI_MODEL)
    
    def query(self, prompt: str, context: Optional[str] = None) -> str:
        """Query Baidu AI API"""
        try:
            headers = {
                "Content-Type": "application/json"
            }
            
            messages = []
            if context:
                messages.append({"role": "system", "content": context})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "messages": messages,
                "model": self.model
            }
            
            response = requests.post(
                f"{self.api_url}/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions",
                headers=headers,
                json=payload,
                auth=(Config.BAIDU_AI_API_KEY, Config.BAIDU_AI_SECRET_KEY),
                timeout=Config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            result = response.json()
            answer = result['result']
            self.logger.debug(f"BaiduAI query successful: {len(answer)} chars")
            return answer
        except Exception as e:
            self.logger.error(f"BaiduAI query failed: {e}")
            return ""


class DoubaoAgent(AIAgent):
    """Doubao (ByteDance) AI Agent"""
    
    def __init__(self):
        super().__init__("Doubao", Config.DOUBAO_API_KEY, Config.DOUBAO_API_URL, Config.DOUBAO_MODEL)
    
    def query(self, prompt: str, context: Optional[str] = None) -> str:
        """Query Doubao API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            messages = []
            if context:
                messages.append({"role": "system", "content": context})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7
            }
            
            response = requests.post(
                f"{self.api_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=Config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            result = response.json()
            answer = result['choices'][0]['message']['content']
            self.logger.debug(f"Doubao query successful: {len(answer)} chars")
            return answer
        except Exception as e:
            self.logger.error(f"Doubao query failed: {e}")
            return ""


# ============================================================================
# AI Agent Manager
# ============================================================================

class AIAgentManager:
    """Manage all AI agents"""
    
    _agents: Dict[str, AIAgent] = {}
    
    @classmethod
    def initialize(cls):
        """Initialize all AI agents"""
        cls._agents = {
            'kimi': KimiAgent(),
            'deepseek': DeepSeekAgent(),
            'yuanpao': YuanpaoAgent(),
            'qianwen': QianwenAgent(),
            'baidu_ai': BaiduAIAgent(),
            'doubao': DoubaoAgent()
        }
        logger.info(f"Initialized {len(cls._agents)} AI agents")
    
    @classmethod
    def get_agent(cls, name: str) -> Optional[AIAgent]:
        """Get specific AI agent"""
        return cls._agents.get(name)
    
    @classmethod
    def get_all_agents(cls) -> Dict[str, AIAgent]:
        """Get all AI agents"""
        return cls._agents
    
    @classmethod
    async def query_all(cls, prompt: str, context: Optional[str] = None) -> Dict[str, str]:
        """Query all AI agents concurrently"""
        if not cls._agents:
            cls.initialize()
        
        results = {}
        
        async def query_agent(name: str, agent: AIAgent):
            result = await asyncio.to_thread(agent.query, prompt, context)
            results[name] = result
        
        tasks = [query_agent(name, agent) for name, agent in cls._agents.items()]
        await asyncio.gather(*tasks)
        
        logger.info(f"Queried all {len(cls._agents)} agents")
        return results


# ============================================================================
# PM API Wrapper
# ============================================================================

class PMAPI:
    """Project Management API operations"""
    
    HEADERS = {
        "Authorization": f"Bearer {Config.PM_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    @classmethod
    def create_task(cls, title: str, description: str, priority: str = "medium") -> Optional[Dict[str, Any]]:
        """Create PM task"""
        try:
            payload = {
                'project_id': Config.PM_PROJECT_ID,
                'title': title,
                'description': description,
                'priority': priority,
                'status': 'todo'
            }
            
            response = requests.post(
                f"{Config.PM_API_URL}/tasks",
                headers=cls.HEADERS,
                json=payload,
                timeout=Config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            task = response.json()
            logger.info(f"Created PM task: {task.get('id')}")
            return task
        except Exception as e:
            logger.error(f"Failed to create PM task: {e}")
            return None
    
    @classmethod
    def update_task(cls, task_id: str, status: str, comment: Optional[str] = None) -> bool:
        """Update PM task status"""
        try:
            payload = {
                'status': status
            }
            
            if comment:
                payload['comment'] = comment
            
            response = requests.patch(
                f"{Config.PM_API_URL}/tasks/{task_id}",
                headers=cls.HEADERS,
                json=payload,
                timeout=Config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            logger.info(f"Updated PM task {task_id} to status: {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to update PM task {task_id}: {e}")
            return False


# ============================================================================
# Utilities
# ============================================================================

def format_issue_for_ai(issue: Dict[str, Any]) -> str:
    """Format GitHub issue for AI analysis"""
    return f"""
Issue #{issue['number']}: {issue['title']}

Labels: {', '.join([l['name'] for l in issue.get('labels', [])])}
Status: {issue.get('state', 'unknown')}
Created: {issue.get('created_at', 'N/A')}

Description:
{issue.get('body', 'No description')}

URL: {issue.get('html_url', 'N/A')}
"""


def parse_ai_response(response: str) -> Dict[str, Any]:
    """Parse AI response (extract JSON if present)"""
    try:
        # Try to extract JSON from response
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = response[start:end]
            return json.loads(json_str)
    except Exception as e:
        logger.debug(f"Could not parse JSON from AI response: {e}")
    
    return {'text': response, 'parsed': False}


if __name__ == '__main__':
    logger.info(f"AINOL Library v{Config.VERSION} loaded successfully")
    AIAgentManager.initialize()
