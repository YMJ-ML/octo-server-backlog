"""
AINOL Agent Architecture - PM Sync Runner
Monitors PM tasks, syncs status back to GitHub, and maintains bidirectional sync.
"""

import asyncio
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from agentlib import (
    Config, logger, Cache, GitHubAPI, PMAPI, parse_ai_response
)


class PMSyncRunner:
    """PM sync runner for bidirectional GitHub ↔ PM synchronization"""
    
    def __init__(self):
        self.logger = logger
        self.last_pm_check = None
        self.synced_tasks = set()
        self.task_github_mapping = {}  # task_id -> issue_number
    
    def get_pm_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get PM tasks (optionally filtered by status)"""
        try:
            # This is a placeholder - actual implementation depends on PM API
            # For demonstration, we'll return empty list
            # In production, this would query the actual PM API
            
            self.logger.debug(f"Fetching PM tasks (status={status})")
            
            # TODO: Implement actual PM task fetching
            # For now, return empty to demonstrate structure
            return []
        except Exception as e:
            self.logger.error(f"Failed to get PM tasks: {e}")
            return []
    
    def extract_issue_number(self, pm_task: Dict[str, Any]) -> Optional[int]:
        """Extract GitHub issue number from PM task"""
        try:
            # Look for issue number in task title or description
            # Pattern: [GitHub #123] or similar
            
            title = pm_task.get('title', '')
            description = pm_task.get('description', '')
            
            import re
            
            # Try to find [GitHub #123] pattern
            match = re.search(r'\[GitHub #(\d+)\]', title)
            if match:
                return int(match.group(1))
            
            # Try in description
            match = re.search(r'GitHub Issue.*?#(\d+)', description)
            if match:
                return int(match.group(1))
            
            return None
        except Exception as e:
            self.logger.debug(f"Could not extract issue number: {e}")
            return None
    
    def map_pm_status_to_github(self, pm_status: str) -> List[str]:
        """Map PM status to GitHub labels"""
        status_map = {
            'todo': ['status:todo'],
            'in_progress': ['status:in-progress'],
            'in_review': ['status:in-review'],
            'done': ['status:done'],
            'blocked': ['status:blocked'],
            'cancelled': ['status:cancelled']
        }
        
        return status_map.get(pm_status, [])
    
    async def sync_pm_task_to_github(self, pm_task: Dict[str, Any]) -> bool:
        """Sync PM task status back to GitHub issue"""
        try:
            # Extract issue number from PM task
            issue_number = self.extract_issue_number(pm_task)
            
            if not issue_number:
                self.logger.debug(f"No GitHub issue number found in PM task: {pm_task.get('id')}")
                return False
            
            # Get PM task status
            pm_status = pm_task.get('status', 'unknown')
            github_labels = self.map_pm_status_to_github(pm_status)
            
            self.logger.info(f"Syncing PM task {pm_task.get('id')} (status={pm_status}) to GitHub issue #{issue_number}")
            
            # Update GitHub issue with status label
            if github_labels:
                # Add comment to issue about status update
                comment = f"**📊 PM Status Update:** Status changed to `{pm_status}`\n\n"
                
                if pm_task.get('assigned_to'):
                    comment += f"👤 **Assigned to:** {pm_task.get('assigned_to')}\n"
                
                if pm_task.get('due_date'):
                    comment += f"📅 **Due Date:** {pm_task.get('due_date')}\n"
                
                if pm_task.get('priority'):
                    comment += f"⚡ **Priority:** {pm_task.get('priority')}\n"
                
                if pm_task.get('description'):
                    comment += f"\n**Description:**\n{pm_task.get('description')[:500]}"
                
                comment += "\n\n_Status synced from PM_"
                
                result = GitHubAPI.add_comment(issue_number, comment)
                
                if result:
                    self.logger.info(f"Successfully synced PM task to issue #{issue_number}")
                    task_id = f"pm_task_{pm_task.get('id')}"
                    self.synced_tasks.add(task_id)
                    self.task_github_mapping[pm_task.get('id')] = issue_number
                    return True
            
            return False
        except Exception as e:
            self.logger.error(f"Failed to sync PM task to GitHub: {e}")
            return False
    
    def get_github_issue_updates(self) -> List[Dict[str, Any]]:
        """Get recently updated GitHub issues"""
        try:
            # Get open issues sorted by most recently updated
            issues = GitHubAPI.get_issues(state='open')
            
            if not issues:
                return []
            
            # Sort by updated_at descending
            issues.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
            
            # Return issues updated in last hour
            recent_issues = []
            now = datetime.now()
            
            for issue in issues:
                updated_at = datetime.fromisoformat(issue['updated_at'].replace('Z', '+00:00'))
                if now - updated_at < timedelta(hours=1):
                    recent_issues.append(issue)
            
            self.logger.debug(f"Found {len(recent_issues)} recently updated issues")
            return recent_issues
        except Exception as e:
            self.logger.error(f"Failed to get GitHub issue updates: {e}")
            return []
    
    def extract_pm_task_id(self, issue: Dict[str, Any]) -> Optional[str]:
        """Extract PM task ID from GitHub issue"""
        try:
            description = issue.get('body', '')
            comments_text = issue.get('comments', 0)
            
            # Look for PM task ID in issue body or comments
            import re
            
            # Pattern: pm_task_id=... or task_id=...
            match = re.search(r'[pm_]*task[_id]*=(\w+)', description, re.IGNORECASE)
            if match:
                return match.group(1)
            
            return None
        except Exception as e:
            self.logger.debug(f"Could not extract PM task ID: {e}")
            return None
    
    def map_github_labels_to_pm_status(self, labels: List[Dict[str, str]]) -> Optional[str]:
        """Map GitHub labels to PM status"""
        label_names = [l.get('name', '') for l in labels]
        
        status_map = {
            'status:todo': 'todo',
            'status:in-progress': 'in_progress',
            'status:in-review': 'in_review',
            'status:done': 'done',
            'status:blocked': 'blocked',
            'status:cancelled': 'cancelled'
        }
        
        for label, status in status_map.items():
            if label in label_names:
                return status
        
        return None
    
    async def sync_github_issue_to_pm(self, issue: Dict[str, Any]) -> bool:
        """Sync GitHub issue updates back to PM"""
        try:
            # Extract PM task ID from issue
            pm_task_id = self.extract_pm_task_id(issue)
            
            if not pm_task_id:
                self.logger.debug(f"No PM task ID found in issue #{issue['number']}")
                return False
            
            self.logger.info(f"Syncing GitHub issue #{issue['number']} to PM task {pm_task_id}")
            
            # Extract status from labels
            labels = issue.get('labels', [])
            pm_status = self.map_github_labels_to_pm_status(labels)
            
            # Build PM update
            update_data = {
                'status': pm_status,
                'title': issue['title'],
                'description': issue.get('body', ''),
                'url': issue.get('html_url', ''),
                'last_synced': datetime.now().isoformat()
            }
            
            # Update PM task
            if pm_status:
                result = PMAPI.update_task(
                    pm_task_id,
                    pm_status,
                    f"Status updated from GitHub: {issue['html_url']}"
                )
                
                if result:
                    self.logger.info(f"Successfully synced GitHub issue #{issue['number']} to PM task {pm_task_id}")
                    sync_id = f"github_issue_{issue['number']}"
                    self.synced_tasks.add(sync_id)
                    return True
            
            return False
        except Exception as e:
            self.logger.error(f"Failed to sync GitHub issue to PM: {e}")
            return False
    
    def generate_sync_report(self, stats: Dict[str, int]) -> str:
        """Generate sync report"""
        report = f"""
## 🔄 AINOL PM-GitHub Sync Report

**Sync Time:** {datetime.now().isoformat()}

### Statistics:
- ✅ PM → GitHub: {stats.get('pm_to_github', 0)} synced
- ✅ GitHub → PM: {stats.get('github_to_pm', 0)} synced
- ⚠️ Failed: {stats.get('failed', 0)}
- ⏭️ Skipped: {stats.get('skipped', 0)}

### Last Sync Details:
- PM Tasks Checked: {stats.get('pm_tasks_checked', 0)}
- GitHub Issues Checked: {stats.get('github_issues_checked', 0)}
- Total Sync Pairs: {stats.get('sync_pairs', 0)}

### Status:
{('🟢 All syncs completed successfully' if stats.get('failed', 0) == 0 else '🟡 Some syncs encountered errors')}

---
_Report generated by AINOL Agent Architecture_
"""
        return report
    
    async def run_sync_cycle(self) -> Dict[str, int]:
        """Run one PM ↔ GitHub sync cycle"""
        try:
            self.logger.info(f"Starting PM sync cycle at {datetime.now().isoformat()}")
            
            stats = {
                'pm_to_github': 0,
                'github_to_pm': 0,
                'failed': 0,
                'skipped': 0,
                'pm_tasks_checked': 0,
                'github_issues_checked': 0,
                'sync_pairs': 0
            }
            
            # Step 1: Sync PM tasks to GitHub
            pm_tasks = self.get_pm_tasks()
            stats['pm_tasks_checked'] = len(pm_tasks)
            
            if pm_tasks:
                self.logger.info(f"Processing {len(pm_tasks)} PM tasks")
                
                # Process with concurrency limit
                semaphore = asyncio.Semaphore(Config.CONCURRENT_REQUESTS)
                
                async def sync_pm_with_limit(task):
                    async with semaphore:
                        return await self.sync_pm_task_to_github(task)
                
                pm_results = await asyncio.gather(
                    *[sync_pm_with_limit(task) for task in pm_tasks],
                    return_exceptions=True
                )
                
                for result in pm_results:
                    if isinstance(result, Exception):
                        stats['failed'] += 1
                    elif result:
                        stats['pm_to_github'] += 1
                    else:
                        stats['skipped'] += 1
            
            # Step 2: Sync GitHub issues to PM
            github_issues = self.get_github_issue_updates()
            stats['github_issues_checked'] = len(github_issues)
            
            if github_issues:
                self.logger.info(f"Processing {len(github_issues)} GitHub issues")
                
                # Process with concurrency limit
                semaphore = asyncio.Semaphore(Config.CONCURRENT_REQUESTS)
                
                async def sync_github_with_limit(issue):
                    async with semaphore:
                        return await self.sync_github_issue_to_pm(issue)
                
                github_results = await asyncio.gather(
                    *[sync_github_with_limit(issue) for issue in github_issues],
                    return_exceptions=True
                )
                
                for result in github_results:
                    if isinstance(result, Exception):
                        stats['failed'] += 1
                    elif result:
                        stats['github_to_pm'] += 1
                    else:
                        stats['skipped'] += 1
            
            stats['sync_pairs'] = stats['pm_to_github'] + stats['github_to_pm']
            
            # Log summary
            self.logger.info(
                f"Sync cycle completed: "
                f"PM→GitHub={stats['pm_to_github']}, "
                f"GitHub→PM={stats['github_to_pm']}, "
                f"Failed={stats['failed']}"
            )
            
            return stats
        except Exception as e:
            self.logger.error(f"Sync cycle failed: {e}")
            return {
                'pm_to_github': 0,
                'github_to_pm': 0,
                'failed': 1,
                'skipped': 0,
                'pm_tasks_checked': 0,
                'github_issues_checked': 0,
                'sync_pairs': 0
            }
    
    async def run(self, continuous: bool = False):
        """Run PM sync runner"""
        self.logger.info(f"Starting PM Sync Runner (continuous={continuous})")
        
        try:
            if continuous:
                # Run continuously
                cycle_count = 0
                while True:
                    try:
                        cycle_count += 1
                        self.logger.info(f"=== Sync Cycle #{cycle_count} ===")
                        
                        stats = await self.run_sync_cycle()
                        report = self.generate_sync_report(stats)
                        self.logger.info(report)
                        
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
                report = self.generate_sync_report(stats)
                self.logger.info(report)
                self.logger.info(f"Final stats: {stats}")
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            sys.exit(1)


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AINOL PM Sync Runner')
    parser.add_argument('--continuous', '-c', action='store_true',
                       help='Run continuously instead of once')
    parser.add_argument('--interval', '-i', type=int,
                       help='Override sync interval (seconds)')
    
    args = parser.parse_args()
    
    # Override interval if provided
    if args.interval:
        Config.GITHUB_POLL_INTERVAL = args.interval
    
    runner = PMSyncRunner()
    await runner.run(continuous=args.continuous)


if __name__ == '__main__':
    asyncio.run(main())
