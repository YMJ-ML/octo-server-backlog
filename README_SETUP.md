# AINOL Agent Architecture - Setup & Deployment Guide

## 📋 Overview

AINOL (AI-Driven Intelligent Operations Loop) is an intelligent agent architecture that:

- 🔄 **Polls GitHub Issues** → Analyzes with 6 AI platforms → Posts insights → Syncs to PM
- 🤖 **Leverages Multiple AI** — Kimi, DeepSeek, 元宝, 千问, 百度AI, 豆包
- 🔀 **Maintains Bidirectional Sync** — GitHub ↔ PM tasks, statuses, comments
- 📊 **Analyzes Issues** — Category, Priority, Scope, Solution, Effort
- 🎯 **Automates Workflows** — Reduces manual coordination overhead

---

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/your_org/AINOL_Backlog.git
cd AINOL_Backlog
```

### 2. Setup Python Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
# Copy example config
cp config.env.example config.env

# Edit config.env with your actual API keys and credentials
nano config.env
```

**Required configurations:**
- `GITHUB_TOKEN` — Your GitHub personal access token
- `GITHUB_REPO_OWNER` & `GITHUB_REPO_NAME` — Your target repository
- `KIMI_API_KEY` — Moonshot API key
- `DEEPSEEK_API_KEY` — DeepSeek API key
- `YUANPAO_API_KEY`, `QIANWEN_API_KEY`, `BAIDU_AI_API_KEY`, `DOUBAO_API_KEY` — Other AI platform keys
- `PM_API_URL`, `PM_API_TOKEN`, `PM_PROJECT_ID` — PM system configuration

### 4. Run Sync Runners

**GitHub Sync (one-time):**
```bash
python3 run_sync.py
```

**GitHub Sync (continuous polling):**
```bash
python3 run_sync.py --continuous
```

**PM Sync (one-time):**
```bash
python3 run_pm.py
```

**PM Sync (continuous):**
```bash
python3 run_pm.py --continuous
```

---

## 🏗️ Architecture Components

### **agentlib.py** — Shared Library
Core abstractions and utilities:
- `Config` — Configuration management
- `Cache` — In-memory caching with TTL
- `KnowledgeBase` — Knowledge base loading and search
- `GitHubAPI` — GitHub REST API wrapper
- `AIAgent` (base class) + 6 implementations
- `AIAgentManager` — Multi-agent orchestration
- `PMAPI` — PM system API wrapper
- Utility functions

### **run_sync.py** — GitHub → AI → PM Pipeline
**Workflow:**
```
GitHub Issues (open) 
    ↓ [filter unprocessed]
AI Analysis [concurrent]
    • Kimi
    • DeepSeek
    • Yuanpao
    • Qianwen
    • BaiduAI
    • Doubao
    ↓ [aggregate results]
Post Comment [GitHub Issue]
    ↓
Create Task [PM System]
```

**Usage:**
```bash
# Single run
python3 run_sync.py

# Continuous (default: poll every 300s)
python3 run_sync.py --continuous

# Custom interval (60 seconds)
python3 run_sync.py --continuous --interval 60
```

### **run_pm.py** — Bidirectional GitHub ↔ PM Sync
**Workflow:**
```
PM Tasks (changed status)
    ↓
Extract issue number
    ↓
Map PM status → GitHub labels
    ↓
Post comment [GitHub Issue]
    ↓
↔️ [Bidirectional]
    ↓
GitHub Issues (updated)
    ↓
Extract PM task ID
    ↓
Map GitHub labels → PM status
    ↓
Update task [PM System]
```

**Usage:**
```bash
# Single run
python3 run_pm.py

# Continuous
python3 run_pm.py --continuous

# Custom interval
python3 run_pm.py --continuous --interval 120
```

---

## 📊 AI Analysis Framework

Each issue is analyzed across 5 dimensions:

1. **Category** — Bug / Feature / Enhancement / Documentation / Discussion
2. **Priority** — Critical / High / Medium / Low
3. **Scope** — Backend / Frontend / Infrastructure / Documentation / Other
4. **Solution** — Recommended action (brief)
5. **Effort** — Small / Medium / Large

**Example analysis output:**
```json
{
  "category": "Bug",
  "priority": "High",
  "scope": "Backend",
  "solution": "Add rate limiting middleware to API",
  "effort": "Medium"
}
```

---

## 🔀 Status Mapping

### PM Status → GitHub Labels
| PM Status | GitHub Label |
|-----------|-------------|
| todo | `status:todo` |
| in_progress | `status:in-progress` |
| in_review | `status:in-review` |
| done | `status:done` |
| blocked | `status:blocked` |
| cancelled | `status:cancelled` |

---

## 📈 Monitoring & Logging

### Log Levels
Configure in `config.env`:
```bash
LOG_LEVEL=DEBUG      # Verbose (development)
LOG_LEVEL=INFO       # Normal (production)
LOG_LEVEL=WARNING    # Warnings only
LOG_LEVEL=ERROR      # Errors only
```

### Log Output
- **File:** `logs/ainol.log` (default)
- **Console:** Configurable via `LOG_TO_CONSOLE`

### Sample Log
```
2026-09-09 21:30:15,123 - AINOL - INFO - Starting sync cycle at 2026-09-09T21:30:15
2026-09-09 21:30:15,456 - AINOL - INFO - Found 3 unprocessed issues
2026-09-09 21:30:16,789 - AINOL.Kimi - DEBUG - Kimi query successful: 1245 chars
2026-09-09 21:30:17,012 - AINOL - INFO - Posted analysis comment to issue #123
2026-09-09 21:30:17,345 - AINOL - INFO - Created PM task for issue #123
```

---

## 🧪 Testing

### Unit Tests
```bash
pytest tests/ -v
```

### Integration Tests
```bash
pytest tests/integration/ -v --asyncio-mode=auto
```

### Coverage Report
```bash
pytest tests/ --cov=agentlib --cov-report=html
```

---

## 🔧 Troubleshooting

### Issue: `Failed to get GitHub issues: 401`
**Problem:** Invalid GitHub token
**Solution:** 
1. Verify `GITHUB_TOKEN` in `config.env`
2. Ensure token has `repo` scope permissions
3. Token should not be expired

### Issue: `No AI results for issue`
**Problem:** AI platform API errors
**Solution:**
1. Check API keys in `config.env`
2. Verify API endpoints are correct
3. Check API rate limits
4. Review logs in `logs/ainol.log`

### Issue: `PM sync failing: Not found`
**Problem:** PM task ID extraction or API issues
**Solution:**
1. Ensure PM issue numbers are in GitHub issue title: `[GitHub #123]`
2. Verify `PM_API_URL` and `PM_API_TOKEN`
3. Check PM project configuration

### Issue: Duplicate comments on GitHub
**Problem:** Runner processed same issue multiple times
**Solution:**
1. Check `run_sync.py` logic for processed issues
2. Look for race conditions if running multiple instances
3. Use `Cache` to deduplicate

---

## 🚀 Deployment

### Docker Deployment (Optional)
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

CMD ["python3", "run_sync.py", "--continuous"]
```

Build and run:
```bash
docker build -t ainol:latest .
docker run -d \
  -e GITHUB_TOKEN=your_token \
  -e GITHUB_REPO_OWNER=your_org \
  -e GITHUB_REPO_NAME=your_repo \
  ainol:latest
```

### Kubernetes Deployment (Optional)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ainol-sync
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ainol
  template:
    metadata:
      labels:
        app: ainol
    spec:
      containers:
      - name: ainol
        image: ainol:latest
        env:
        - name: GITHUB_TOKEN
          valueFrom:
            secretKeyRef:
              name: ainol-secrets
              key: github-token
        # ... other env vars
```

---

## 📚 Development

### Code Style
```bash
# Format code
black agentlib.py run_sync.py run_pm.py

# Lint
flake8 agentlib.py run_sync.py run_pm.py

# Type checking (if using type hints)
mypy agentlib.py
```

### Adding New AI Platforms

1. Create new agent class in `agentlib.py`:
```python
class NewAIAgent(AIAgent):
    def __init__(self):
        super().__init__("NewAI", api_key, api_url, model)
    
    def query(self, prompt: str, context: Optional[str] = None) -> str:
        # Implement API call
        pass
```

2. Register in `AIAgentManager.initialize()`:
```python
cls._agents['new_ai'] = NewAIAgent()
```

3. Update `config.env` and `config.env.example` with new API keys

### Adding New Sync Rules

1. Extend status mappings in `run_pm.py`:
```python
status_map = {
    # ... existing mappings
    'new_status': 'new_github_label'
}
```

2. Update GitHub label schema documentation

---

## 📞 Support

For issues or questions:
1. Check logs in `logs/ainol.log`
2. Review this README
3. Create GitHub issue in the repository
4. Check API platform documentation

---

## 📄 License

[Your License Here]

---

## 🙏 Acknowledgments

Built with:
- GitHub API
- Multiple AI platforms (Kimi, DeepSeek, 元宝, 千问, 百度AI, 豆包)
- Python asyncio for concurrent operations
- Community best practices

---

**Version:** 1.0.0  
**Last Updated:** 2026-09-09  
**Status:** Production Ready ✅
