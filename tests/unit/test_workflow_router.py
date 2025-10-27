"""
Test workflow routing logic
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.routing import WorkflowRouter


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic API client"""
    with patch("core.routing.Anthropic") as mock_client:
        yield mock_client


class TestWorkflowRouter:
    """Test workflow routing decisions"""

    def setup_method(self):
        """Reset singleton before each test"""
        import core.routing

        core.routing._router = None

    def test_agent_improvement_routing_orchestrator(self, mock_anthropic_client):
        """Test routing for orchestrator agent improvement"""
        # Mock API response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="improve-agent")]
        mock_anthropic_client.return_value.messages.create.return_value = mock_response

        router = WorkflowRouter()
        result = router.route_task("Optimize orchestrator agent")

        assert result == "/workflows:improve-agent"

    def test_agent_improvement_routing_code_agent(self, mock_anthropic_client):
        """Test routing for code_agent improvement"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="improve-agent")]
        mock_anthropic_client.return_value.messages.create.return_value = mock_response

        router = WorkflowRouter()
        result = router.route_task("Improve code_agent performance")

        assert result == "/workflows:improve-agent"

    def test_agent_improvement_routing_frontend_agent(self, mock_anthropic_client):
        """Test routing for frontend_agent improvement"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="improve-agent")]
        mock_anthropic_client.return_value.messages.create.return_value = mock_response

        router = WorkflowRouter()
        result = router.route_task("Update research_agent based on logs")

        assert result == "/workflows:improve-agent"

    def test_bug_fix_routing(self, mock_anthropic_client):
        """Test routing for bug fixes"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="smart-fix")]
        mock_anthropic_client.return_value.messages.create.return_value = mock_response

        router = WorkflowRouter()
        result = router.route_task("Fix authentication bug")

        assert result == "/workflows:smart-fix"

    def test_error_routing(self, mock_anthropic_client):
        """Test routing for error handling"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="smart-fix")]
        mock_anthropic_client.return_value.messages.create.return_value = mock_response

        router = WorkflowRouter()
        result = router.route_task("Error in session handler")

        assert result == "/workflows:smart-fix"

    def test_feature_development_routing(self, mock_anthropic_client):
        """Test routing for new feature development"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="code-task")]
        mock_anthropic_client.return_value.messages.create.return_value = mock_response

        router = WorkflowRouter()
        result = router.route_task("Add new dashboard feature")

        assert result == "/workflows:code-task"

    def test_refactoring_routing(self, mock_anthropic_client):
        """Test routing for refactoring tasks"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="code-task")]
        mock_anthropic_client.return_value.messages.create.return_value = mock_response

        router = WorkflowRouter()
        result = router.route_task("Refactor session management module")

        assert result == "/workflows:code-task"

    def test_invalid_response_defaults_to_code_task(self, mock_anthropic_client):
        """Test that invalid API responses default to code-task"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="invalid-workflow")]
        mock_anthropic_client.return_value.messages.create.return_value = mock_response

        router = WorkflowRouter()
        result = router.route_task("Some random task")

        assert result == "/workflows:code-task"

    def test_api_exception_defaults_to_code_task(self, mock_anthropic_client):
        """Test that API exceptions default to code-task"""
        mock_anthropic_client.return_value.messages.create.side_effect = Exception("API Error")

        router = WorkflowRouter()
        result = router.route_task("Some task")

        assert result == "/workflows:code-task"

    def test_workflow_info_completeness(self):
        """Test that all workflows have required information"""
        router = WorkflowRouter()

        required_keys = ["description", "use_for"]
        for workflow_name, workflow_info in router.available_workflows.items():
            for key in required_keys:
                assert key in workflow_info, f"Workflow '{workflow_name}' missing '{key}'"
                assert workflow_info[key], f"Workflow '{workflow_name}' has empty '{key}'"

    def test_multiple_agent_improvement_variations(self, mock_anthropic_client):
        """Test various phrasings for agent improvement tasks"""
        test_cases = [
            "optimize orchestrator agent",
            "improve the code_agent",
            "enhance frontend_agent behavior",
            "update research_agent configuration",
            "optimize agent performance",
        ]

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="improve-agent")]
        mock_anthropic_client.return_value.messages.create.return_value = mock_response

        router = WorkflowRouter()

        for task in test_cases:
            result = router.route_task(task)
            assert result == "/workflows:improve-agent", f"Failed for task: {task}"

    def test_multiple_bug_fix_variations(self, mock_anthropic_client):
        """Test various phrasings for bug fix tasks"""
        test_cases = [
            "fix the broken authentication",
            "bug in session handler",
            "error when processing requests",
            "not working properly",
            "issue with database connection",
        ]

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="smart-fix")]
        mock_anthropic_client.return_value.messages.create.return_value = mock_response

        router = WorkflowRouter()

        for task in test_cases:
            result = router.route_task(task)
            assert result == "/workflows:smart-fix", f"Failed for task: {task}"
