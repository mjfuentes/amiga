"""
Unit tests for agent type extraction from context summary
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from monitoring.server import _extract_agent_type_from_context


class TestAgentTypeParsing:
    """Test agent type extraction from context summary"""

    def test_frontend_agent_detection(self):
        """Test frontend-agent prefix detection"""
        context = "use frontend-agent to add dark mode to chat. User asked: 'add dark mode to chat'. Working in amiga repo."
        assert _extract_agent_type_from_context(context) == "frontend_agent"

    def test_frontend_agent_underscore_format(self):
        """Test frontend_agent prefix (underscore instead of hyphen)"""
        context = "use frontend_agent to make chat full width. User asked: 'make chat full width'."
        assert _extract_agent_type_from_context(context) == "frontend_agent"

    def test_orchestrator_detection(self):
        """Test orchestrator prefix detection"""
        context = "use orchestrator to build authentication system. User asked: 'build auth system'."
        assert _extract_agent_type_from_context(context) == "orchestrator"

    def test_research_agent_detection(self):
        """Test research-agent prefix detection"""
        context = "use research-agent to analyze performance bottleneck. User asked: 'why is X slow?'"
        assert _extract_agent_type_from_context(context) == "research_agent"

    def test_research_agent_underscore_format(self):
        """Test research_agent prefix (underscore instead of hyphen)"""
        context = "use research_agent to investigate bug. User asked: 'investigate error'."
        assert _extract_agent_type_from_context(context) == "research_agent"

    def test_code_agent_default(self):
        """Test default to code_agent when no prefix"""
        context = "User asked: 'fix bug in main.py'. Working in amiga repo."
        assert _extract_agent_type_from_context(context) == "code_agent"

    def test_none_context(self):
        """Test None context returns code_agent"""
        assert _extract_agent_type_from_context(None) == "code_agent"

    def test_empty_context(self):
        """Test empty context returns code_agent"""
        assert _extract_agent_type_from_context("") == "code_agent"

    def test_whitespace_context(self):
        """Test whitespace-only context returns code_agent"""
        assert _extract_agent_type_from_context("   ") == "code_agent"

    def test_case_insensitive(self):
        """Test case insensitive prefix matching"""
        context = "USE FRONTEND-AGENT TO add feature. User asked: 'add feature'."
        assert _extract_agent_type_from_context(context) == "frontend_agent"

    def test_real_world_frontend_example(self):
        """Test real-world frontend context from task #f424c7"""
        context = "use frontend-agent to make message list container as wide as its parent container in chat. User reported: \"message list container and parent container have different widths\". Working in amiga repo at /Users/matifuentes/Workspace/amiga."
        assert _extract_agent_type_from_context(context) == "frontend_agent"

    def test_partial_match_does_not_trigger(self):
        """Test that 'use' in middle of sentence doesn't trigger matching"""
        context = "We should use best practices. Fix bug in frontend-agent.py."
        assert _extract_agent_type_from_context(context) == "code_agent"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
