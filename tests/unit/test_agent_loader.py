"""Tests for claude/agent_loader.py - agent definition loading from markdown files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from claude_agent_sdk import AgentDefinition

from claude.agent_loader import (
    _parse_frontmatter,
    _parse_model,
    _parse_tools,
    load_agents,
    load_project_agents,
    parse_agent_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_AGENT_MD = """\
---
name: orchestrator
description: Task orchestrator spawned for ALL background tasks
tools: Task, TodoWrite, Read, Glob, Grep, Bash
model: inherit
---

You are a task orchestrator.
Route tasks to the correct agent.
"""

MINIMAL_AGENT_MD = """\
---
name: simple-agent
description: A minimal agent with no tools or model
---

Just a prompt.
"""

NO_FRONTMATTER_MD = """\
# This is a regular markdown file

No YAML frontmatter here.
"""

MISSING_NAME_MD = """\
---
description: An agent without a name
tools: Read
---

Prompt text.
"""

MISSING_DESCRIPTION_MD = """\
---
name: nameless-desc
---

Prompt text.
"""

EMPTY_PROMPT_MD = """\
---
name: empty-prompt
description: Agent with no prompt body
tools: Read
model: sonnet
---
"""


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    """Create a temporary agents directory with test files."""
    d = tmp_path / "agents"
    d.mkdir()
    return d


def _write_agent(directory: Path, filename: str, content: str) -> Path:
    """Write a markdown file to the given directory."""
    path = directory / filename
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _parse_model tests
# ---------------------------------------------------------------------------


class TestParseModel:
    def test_inherit(self):
        assert _parse_model("inherit") == "inherit"

    def test_sonnet(self):
        assert _parse_model("sonnet") == "sonnet"

    def test_opus(self):
        assert _parse_model("opus") == "opus"

    def test_haiku(self):
        assert _parse_model("haiku") == "haiku"

    def test_model_with_version(self):
        assert _parse_model("claude-3-sonnet-20240229") == "sonnet"

    def test_opus_variant(self):
        assert _parse_model("claude-opus-4") == "opus"

    def test_haiku_variant(self):
        assert _parse_model("claude-3-haiku") == "haiku"

    def test_unknown_model(self):
        assert _parse_model("gpt-4") is None

    def test_empty_string(self):
        assert _parse_model("") is None

    def test_whitespace_only(self):
        assert _parse_model("   ") is None

    def test_case_insensitive(self):
        assert _parse_model("SONNET") == "sonnet"
        assert _parse_model("Opus") == "opus"

    def test_inherit_priority_over_others(self):
        # "inherit" is checked first, so "inherit-sonnet" would match inherit
        assert _parse_model("inherit") == "inherit"


# ---------------------------------------------------------------------------
# _parse_tools tests
# ---------------------------------------------------------------------------


class TestParseTools:
    def test_comma_separated(self):
        result = _parse_tools("Task, TodoWrite, Read, Glob, Grep, Bash")
        assert result == ["Task", "TodoWrite", "Read", "Glob", "Grep", "Bash"]

    def test_single_tool(self):
        assert _parse_tools("Read") == ["Read"]

    def test_empty_string(self):
        assert _parse_tools("") is None

    def test_whitespace_only(self):
        assert _parse_tools("   ") is None

    def test_extra_whitespace(self):
        result = _parse_tools("  Task ,  Read  ,  Bash  ")
        assert result == ["Task", "Read", "Bash"]

    def test_trailing_comma(self):
        result = _parse_tools("Task, Read,")
        assert result == ["Task", "Read"]

    def test_no_spaces(self):
        result = _parse_tools("Task,Read,Bash")
        assert result == ["Task", "Read", "Bash"]


# ---------------------------------------------------------------------------
# _parse_frontmatter tests
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_simple_pairs(self):
        text = "name: orchestrator\ndescription: A task orchestrator"
        result = _parse_frontmatter(text)
        assert result == {"name": "orchestrator", "description": "A task orchestrator"}

    def test_value_with_colons(self):
        text = "description: Task orchestrator: handles all tasks"
        result = _parse_frontmatter(text)
        assert result["description"] == "Task orchestrator: handles all tasks"

    def test_skips_comments(self):
        text = "# comment\nname: agent"
        result = _parse_frontmatter(text)
        assert result == {"name": "agent"}

    def test_skips_blank_lines(self):
        text = "name: agent\n\ndescription: test"
        result = _parse_frontmatter(text)
        assert len(result) == 2

    def test_empty_input(self):
        assert _parse_frontmatter("") == {}


# ---------------------------------------------------------------------------
# parse_agent_file tests
# ---------------------------------------------------------------------------


class TestParseAgentFile:
    def test_valid_file(self, tmp_path: Path):
        path = _write_agent(tmp_path, "orchestrator.md", VALID_AGENT_MD)
        result = parse_agent_file(path)

        assert result is not None
        name, agent = result
        assert name == "orchestrator"
        assert agent.description == "Task orchestrator spawned for ALL background tasks"
        assert agent.tools == ["Task", "TodoWrite", "Read", "Glob", "Grep", "Bash"]
        assert agent.model == "inherit"
        assert "task orchestrator" in agent.prompt.lower()

    def test_minimal_file(self, tmp_path: Path):
        path = _write_agent(tmp_path, "simple.md", MINIMAL_AGENT_MD)
        result = parse_agent_file(path)

        assert result is not None
        name, agent = result
        assert name == "simple-agent"
        assert agent.description == "A minimal agent with no tools or model"
        assert agent.tools is None
        assert agent.model is None
        assert agent.prompt == "Just a prompt."

    def test_no_frontmatter_returns_none(self, tmp_path: Path):
        path = _write_agent(tmp_path, "readme.md", NO_FRONTMATTER_MD)
        result = parse_agent_file(path)
        assert result is None

    def test_missing_name_returns_none(self, tmp_path: Path):
        path = _write_agent(tmp_path, "noname.md", MISSING_NAME_MD)
        result = parse_agent_file(path)
        assert result is None

    def test_missing_description_returns_none(self, tmp_path: Path):
        path = _write_agent(tmp_path, "nodesc.md", MISSING_DESCRIPTION_MD)
        result = parse_agent_file(path)
        assert result is None

    def test_empty_prompt(self, tmp_path: Path):
        path = _write_agent(tmp_path, "empty.md", EMPTY_PROMPT_MD)
        result = parse_agent_file(path)

        assert result is not None
        name, agent = result
        assert name == "empty-prompt"
        assert agent.prompt == ""

    def test_nonexistent_file(self, tmp_path: Path):
        path = tmp_path / "nonexistent.md"
        result = parse_agent_file(path)
        assert result is None

    def test_returns_agentdefinition_instance(self, tmp_path: Path):
        path = _write_agent(tmp_path, "test.md", VALID_AGENT_MD)
        result = parse_agent_file(path)
        assert result is not None
        _, agent = result
        assert isinstance(agent, AgentDefinition)


# ---------------------------------------------------------------------------
# load_agents tests
# ---------------------------------------------------------------------------


class TestLoadAgents:
    def test_loads_multiple_agents(self, agents_dir: Path):
        _write_agent(agents_dir, "orchestrator.md", VALID_AGENT_MD)
        _write_agent(agents_dir, "simple.md", MINIMAL_AGENT_MD)

        result = load_agents(agents_dir)
        assert len(result) == 2
        assert "orchestrator" in result
        assert "simple-agent" in result

    def test_skips_changelog(self, agents_dir: Path):
        _write_agent(agents_dir, "orchestrator.md", VALID_AGENT_MD)
        _write_agent(agents_dir, "CHANGELOG.md", "# Changelog\nSome changes.")

        result = load_agents(agents_dir)
        assert len(result) == 1
        assert "orchestrator" in result

    def test_skips_files_without_frontmatter(self, agents_dir: Path):
        _write_agent(agents_dir, "orchestrator.md", VALID_AGENT_MD)
        _write_agent(agents_dir, "notes.md", NO_FRONTMATTER_MD)

        result = load_agents(agents_dir)
        assert len(result) == 1

    def test_empty_directory(self, agents_dir: Path):
        result = load_agents(agents_dir)
        assert result == {}

    def test_returns_dict_of_agent_definitions(self, agents_dir: Path):
        _write_agent(agents_dir, "orchestrator.md", VALID_AGENT_MD)

        result = load_agents(agents_dir)
        for name, agent in result.items():
            assert isinstance(name, str)
            assert isinstance(agent, AgentDefinition)


# ---------------------------------------------------------------------------
# load_project_agents tests
# ---------------------------------------------------------------------------


class TestLoadProjectAgents:
    def test_loads_from_project_root(self, tmp_path: Path):
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        _write_agent(agents_dir, "orchestrator.md", VALID_AGENT_MD)

        result = load_project_agents(tmp_path)
        assert len(result) == 1
        assert "orchestrator" in result

    def test_nonexistent_directory_returns_empty(self, tmp_path: Path):
        result = load_project_agents(tmp_path)
        assert result == {}

    def test_falls_back_to_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        _write_agent(agents_dir, "simple.md", MINIMAL_AGENT_MD)

        monkeypatch.chdir(tmp_path)
        result = load_project_agents()
        assert len(result) == 1
        assert "simple-agent" in result

    def test_explicit_none_uses_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        _write_agent(agents_dir, "orchestrator.md", VALID_AGENT_MD)

        monkeypatch.chdir(tmp_path)
        result = load_project_agents(None)
        assert len(result) == 1
