"""
Intelligent workflow router using Claude API
Uses Haiku to analyze task and select appropriate workflow
"""

import logging
import os

from anthropic import Anthropic

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)


class WorkflowRouter:
    """Routes tasks to appropriate workflows using Claude API intelligence"""

    def __init__(self):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.available_workflows = {
            "code-task": {
                "description": "General-purpose coding task orchestration. Analyzes task, routes to appropriate agents (code_agent, frontend_agent, research_agent), runs QA checks, commits changes.",
                "use_for": "New features, bug fixes, refactoring, general development tasks",
            },
            "smart-fix": {
                "description": "Intelligent issue resolution with automatic agent selection based on problem domain. Escalates to deep debugging for complex issues. Handles deployment, performance, security, integration issues.",
                "use_for": "Bugs, errors, crashes, performance problems, security issues, broken functionality",
            },
            "improve-agent": {
                "description": "Analyzes agent performance from logs, identifies patterns in failures, updates agent configuration with improved instructions and examples.",
                "use_for": "Improving existing agent behavior, fixing agent issues, optimizing agent performance",
            },
        }

    def route_task(self, task_description: str) -> str:
        """
        Use Claude API to intelligently select the best workflow

        Args:
            task_description: User's task description

        Returns:
            Workflow command (e.g., "/workflows:code-task")
        """
        try:
            # Build workflow selection prompt
            workflows_info = "\n\n".join(
                [
                    f"**{name}**:\n- Description: {info['description']}\n- Use for: {info['use_for']}"
                    for name, info in self.available_workflows.items()
                ]
            )

            prompt = f"""You are a workflow router for a coding bot. Analyze the user's task and select the SINGLE most appropriate workflow.

Available workflows:

{workflows_info}

User's task: "{task_description}"

Analyze the task and respond with ONLY the workflow name (code-task, smart-fix, or improve-agent). No explanation, just the name.

Decision criteria:
- If task mentions "fix", "bug", "error", "broken", "not working", "issue" → smart-fix
- If task mentions "improve", "optimize", "enhance" an AGENT → improve-agent
- If task is building/creating new features → code-task
- If task is modifying existing code → code-task
- Default to code-task for general development

Respond with only: code-task, smart-fix, or improve-agent"""

            # Call Claude API (Haiku 4.5 for speed and cost)
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",  # Haiku 4.5 - faster and cheaper
                max_tokens=50,  # Only need workflow name
                temperature=0,  # Deterministic routing
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract workflow name
            raw_response = response.content[0].text.strip()
            workflow_name = raw_response.lower()

            logger.debug(f"Claude API raw response: '{raw_response}'")

            # Validate and normalize
            if workflow_name not in self.available_workflows:
                logger.warning(
                    f"Claude API returned unexpected workflow '{workflow_name}' (raw: '{raw_response}'), defaulting to code-task"
                )
                workflow_name = "code-task"

            logger.info(f"Workflow router selected: {workflow_name} for task: {task_description[:100]}...")

            return f"/workflows:{workflow_name}"

        except Exception as e:
            logger.error(f"Workflow routing failed: {e}, defaulting to code-task", exc_info=True)
            return "/workflows:code-task"  # Safe fallback


# Singleton instance
_router = None


def get_workflow_router() -> WorkflowRouter:
    """Get or create singleton workflow router"""
    global _router
    if _router is None:
        _router = WorkflowRouter()
    return _router
