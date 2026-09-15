"""
AINOL Agent Architecture - GitHub Sync Runner
Polls GitHub for new issues, analyzes with AI, posts comments, and syncs to PM.
"""

import asyncio
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from agentlib import (
    Config, logger, Cache, KnowledgeBase, GitHubAPI, AIAgentManager,
    PMAPI, format_issue_for_ai, parse_ai_response
)


class GitHubSyncRunner:
    """Main GitHub sync runner"""
    
    def __init__(self):
        self.logger = logger
        self.last_sync_time = None
        self.processed_issues = set()
        self.kb = KnowledgeBase()
        AIAgentManager.initialize()
    
    def get_unprocessed_issues(self) -> List[Dict[str, Any]]:
        """Get issues that haven't been processed yet"""
        try:
            # Get all open issues
            all_issues = GitHubAPI.get_issues(state='open')
            
            if not all_issues:
                self.logger.info("No open issues found")
                return []
            
            # Filter out already processed issues
            unprocessed = []
            for issue in all_issues:
                issue_id = f"issue_{issue['number']}"
                
                # Check if issue was already processed
                if issue_id in self.processed_issues:
                    self.logger.debug(f"Issue #{issue['number']} already processed, skipping")
                    continue
                
                # Check if issue has AI analysis comment already
                if self._has_ai_comment(issue):
                    self.logger.debug(f"Issue #{issue['number']} already has AI comment, marking as processed")
                    self.processed_issues.add(issue_id)
                    continue
                
                unprocessed.append(issue)
            
            self.logger.info(f"Found {len(unprocessed)} unprocessed issues")
            return unprocessed
        except Exception as e:
            self.logger.error(f"Failed to get unprocessed issues: {e}")
            return []
    
    def _has_ai_comment(self, issue: Dict[str, Any]) -> bool:
        """Check if issue already has AI analysis comment"""
        try:
            issue_details = GitHubAPI.get_issue_details(issue['number'])
            if not issue_details:
                return False
            
            comments = issue_details.get('comments', 0)
            if comments == 0:
                return False
            
            # Simple heuristic: if has comments and issue is not too new, assume AI has analyzed it
            created_at = datetime.fromisoformat(issue_details['created_at'].replace('Z', '+00:00'))
            if datetime.now(created_at.tzinfo) - created_at < timedelta(minutes=5):
                return False  # Too new, might be still processing
            
            return comments > 0
        except Exception as e:
            self.logger.debug(f"Error checking AI comment: {e}")
            return False
    
    async def analyze_issue(self, issue: Dict[str, Any]) -> Dict[str, str]:
        """Analyze issue with all AI agents"""
        try:
            formatted_issue = format_issue_for_ai(issue)
            
            # Get context from knowledge base
            kb_context = self.kb.load()[:2000]  # Limit KB context
            
            prompt = f"""请分析以下GitHub Issue，并提供以下信息：
1. 问题分类（Bug、Feature、Enhancement、Documentation、Discussion）
2. 优先级（Critical、High、Medium、Low）
3. 影响范围（后端、前端、基础设施、文档等）
4. 建议的解决方案（简明扼要）
5. 预估工作量（小/中/大）

Issue内容：
{formatted_issue}

相关背景知识：
{kb_context}

请用JSON格式返回分析结果：
{{
  "category": "...",
  "priority": "...",
  "scope": "...",
  "solution": "...",
  "effort": "..."
}}"""
            
            self.logger.info(f"Starting AI analysis for issue #{issue['number']}")
            
            # Query all AI agents concurrently
            results = await AIAgentManager.query_all(prompt, None)
            
            self.logger.info(f"Completed AI analysis for issue #{issue['number']}")
            return results
        except Exception as e:
            self.logger.error(f"Failed to analyze issue #{issue['number']}: {e}")
            return {}
    
    def aggregate_analysis(self, ai_results: Dict[str, str]) -> str:
        """Aggregate results from multiple AI agents"""
        try:
            if not ai_results:
                return "无法获取AI分析结果"
            
            # Parse responses
            parsed_results = {}
            for agent_name, response in ai_results.items():
                parsed = parse_ai_response(response)
                parsed_results[agent_name] = parsed
                self.logger.debug(f"{agent_name}: {parsed}")
            
            # Build aggregated comment
            comment = "## 🤖 AINOL AI Analysis Report\n\n"
            
            # Consensus analysis
            comment += "### AI Agent Perspectives:\n\n"
            for agent_name, parsed in parsed_results.items():
                if parsed.get('parsed'):
                    comment += f"**{agent_name}**: "
                    comment += f"Category={parsed.get('category', 'N/A')}, "
                    comment += f"Priority={parsed.get('priority', 'N/A')}, "
                    comment += f"Effort={parsed.get('effort', 'N/A')}\n"
                else:
                    comment += f"**{agent_name}**: {parsed.get('text', 'No response')[:200]}...\n"
            
            # Recommendations
            comment += "\n### Recommended Action:\n"
            comment += "- 🏷️ Apply appropriate labels based on analysis\n"
            comment += "- 📊 Prioritize in backlog\n"
            comment += "- 👥 Assign to relevant team member\n"
            comment += "- 📝 Update issue description with additional context if needed\n"
            
            comment += "\n_Analysis powered by AINOL Agent Architecture_"
            
            return comment
        except Exception as e:
            self.logger.error(f"Failed to aggregate analysis: {e}")
            return "Error during aggregation"
    
    def post_analysis_comment(self, issue: Dict[str, Any], comment: str) -> bool:
        """Post analysis comment to GitHub issue"""
        try:
            result = GitHubAPI.add_comment(issue['number'], comment)
            if result:
                self.logger.info(f"Posted analysis comment to issue #{issue['number']}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to post comment to issue #{issue['number']}: {e}")
            return False
    
    def sync_to_pm(self, issue: Dict[str, Any], ai_analysis: Dict[str, str]) -> bool:
        """Create PM task from GitHub issue"""
        try:
            parsed = parse_ai_response(list(ai_analysis.values())[0] if ai_analysis else "")
            
            title = f"[GitHub #{issue['number']}] {issue['title']}"
            
            description = f"""GitHub Issue: {issue['html_url']}

Labels: {', '.join([l['name'] for l in issue.get('labels', [])])}

Description:
{issue.get('body', 'No description')}

AI Analysis:
- Category: {parsed.get('category', 'N/A')}
- Priority: {parsed.get('priority', 'N/A')}
- Recommended Solution: {parsed.get('solution', 'N/A')}
- Estimated Effort: {parsed.get('effort', 'N/A')}
"""
            
            priority_map = {
                'Critical': 'critical',
                'High': 'high',
                'Medium': 'medium',
                'Low': 'low'
            }
            
            priority = priority_map.get(parsed.get('priority', 'medium'), 'medium')
            
            result = PMAPI.create_task(title, description, priority)
            if result:
                self.logger.info(f"Created PM task for issue #{issue['number']}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to sync issue #{issue['number']} to PM: {e}")
            return False
    
    async def process_issue(self, issue: Dict[str, Any]) -> bool:
        """Process single issue: analyze + comment + sync"""
        try:
            self.logger.info(f"Processing issue #{issue['number']}: {issue['title']}")
            
            # Step 1: Analyze with AI
            ai_results = await self.analyze_issue(issue)
            
            if not ai_results:
                self.logger.warning(f"No AI results for issue #{issue['number']}")
                return False
            
            # Step 2: Aggregate analysis
            comment = self.aggregate_analysis(ai_results)
            
            # Step 3: Post comment
            self.post_analysis_comment(issue, comment)
            
            # Step 4: Sync to PM
            self.sync_to_pm(issue, ai_results)
            
            # Mark as processed
            issue_id = f"issue_{issue['number']}"
            self.processed_issues.add(issue_id)
            
            self.logger.info(f"✅ Successfully processed issue #{issue['number']}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to process issue #{issue['number']}: {e}")
            return False
    
    async def run_sync_cycle(self) -> Dict[str, int]:
        """Run one sync cycle"""
        try:
            self.logger.info(f"Starting sync cycle at {datetime.now().isoformat()}")
            
            stats = {
                'total_issues': 0,
                'processed': 0,
                'failed': 0,
                'skipped': 0
            }
            
            # Get unprocessed issues
            unprocessed = self.get_unprocessed_issues()
            stats['total_issues'] = len(unprocessed)
            
            if not unprocessed:
                self.logger.info("No issues to process")
                return stats
            
            # Process issues with concurrency limit
            semaphore = asyncio.Semaphore(Config.CONCURRENT_REQUESTS)
            
            async def process_with_limit(issue):
                async with semaphore:
                    return await self.process_issue(issue)
            
            results = await asyncio.gather(
                *[process_with_limit(issue) for issue in unprocessed],
                return_exceptions=True
            )
            
            # Count results
            for result in results:
                if isinstance(result, Exception):
                    stats['failed'] += 1
                elif result:
                    stats['processed'] += 1
                else:
                    stats['failed'] += 1
            
            stats['skipped'] = stats['total_issues'] - stats['processed'] - stats['failed']
            
            self.logger.info(f"Sync cycle completed: {stats['processed']} processed, {stats['failed']} failed")
            return stats
        except Exception as e:
            self.logger.error(f"Sync cycle failed: {e}")
            return {'total_issues': 0, 'processed': 0, 'failed': 1, 'skipped': 0}
    
    async def run(self, continuous: bool = False):
        """Run sync runner"""
        self.logger.info(f"Starting GitHub Sync Runner (continuous={continuous})")
        
        try:
            if continuous:
                # Run continuously
                while True:
                    try:
                        stats = await self.run_sync_cycle()
                        self.logger.info(f"Cycle stats: {stats}")
                        
                        self.logger.info(f"Waiting {Config.GITHUB_POLL_INTERVAL}s before next cycle...")
                        await asyncio.sleep(Config.GITHUB_POLL_INTERVAL)
                    except KeyboardInterrupt:
                        self.logger.info("Received interrupt signal, stopping...")
                        break
                    except Exception as e:
                        self.logger.error(f"Error in sync cycle: {e}")
                        await asyncio.sleep(Config.GITHUB_POLL_INTERVAL)
            else:
                # Run once
                stats = await self.run_sync_cycle()
                self.logger.info(f"Final stats: {stats}")
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            sys.exit(1)


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AINOL GitHub Sync Runner')
    parser.add_argument('--continuous', '-c', action='store_true', 
                       help='Run continuously instead of once')
    parser.add_argument('--interval', '-i', type=int, 
                       help='Override poll interval (seconds)')
    
    args = parser.parse_args()
    
    # Override interval if provided
    if args.interval:
        Config.GITHUB_POLL_INTERVAL = args.interval
    
    runner = GitHubSyncRunner()
    await runner.run(continuous=args.continuous)


if __name__ == '__main__':
    asyncio.run(main())
