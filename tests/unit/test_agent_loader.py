"""Tests for claude/agent_loader.py - agent definition loading from markdown files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from claude_agent_sdk import AgentDefinition

from claude.agent_loader import (
    ExtendedAgentDefinition,
    _VALID_EFFORT_LEVEL_VALUES,
    _VALID_ISOLATION_VALUES,
    _VALID_MEMORY_VALUES,
    _VALID_PERMISSION_MODE_VALUES,
    _parse_bool,
    _parse_frontmatter,
    _parse_int,
    _parse_list,
    _parse_model,
    _parse_validated_str,
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

EXTENDED_AGENT_MD = """\
---
name: extended-agent
description: Agent with all extended fields
tools: Task, Read, Bash
model: claude-sonnet-4-5-20250929
disallowedTools: Write, Edit
permissionMode: bypassPermissions
maxTurns: 25
skills: git, python, testing
memory: project
background: true
isolation: worktree
effortLevel: high
---

You are an extended agent with extra capabilities.
"""

EFFORT_LEVEL_AGENT_MD = """\
---
name: effort-agent
description: Agent with effort level
model: sonnet
effortLevel: max
permissionMode: plan
---

Agent with effort controls.
"""

INVALID_VALIDATED_FIELDS_MD = """\
---
name: invalid-fields-agent
description: Agent with invalid validated field values
memory: globalScope
isolation: docker
permissionMode: fullAdmin
effortLevel: extreme
---

Agent with unrecognized field values.
"""

EXTENDED_YAML_LIST_AGENT_MD = """\
---
name: list-agent
description: Agent using YAML list syntax
tools: [Task, Read]
disallowedTools: [Write, Edit, Bash]
skills:
  - git
  - python
  - testing
---

Agent with YAML list fields.
"""

EXTENDED_NESTED_AGENT_MD = """\
---
name: nested-agent
description: Agent with nested dict fields
tools: Task
mcpServers:
  playwright: npx @playwright/mcp
  filesystem: npx @modelcontextprotocol/server-filesystem
hooks:
  PreToolUse: validate_input
  PostToolUse: log_result
---

Agent with nested configuration.
"""

FULL_MODEL_STRING_MD = """\
---
name: full-model-agent
description: Agent with full model identifier
model: claude-sonnet-4-5-20250929
---

Uses a full model string.
"""

OPUS_MODEL_MD = """\
---
name: opus-agent
description: Agent using opus model
model: claude-opus-4-5-20250929
---

Uses opus model.
"""

HAIKU_MODEL_MD = """\
---
name: haiku-agent
description: Agent using haiku model
model: claude-haiku-4-5-20250929
---

Uses haiku model.
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

    def test_full_sonnet_model_string(self):
        assert _parse_model("claude-sonnet-4-5-20250929") == "sonnet"

    def test_full_opus_model_string(self):
        assert _parse_model("claude-opus-4-5-20250929") == "opus"

    def test_full_haiku_model_string(self):
        assert _parse_model("claude-haiku-4-5-20250929") == "haiku"


# ---------------------------------------------------------------------------
# _parse_list tests
# ---------------------------------------------------------------------------


class TestParseList:
    def test_comma_separated(self):
        result = _parse_list("Task, TodoWrite, Read, Glob, Grep, Bash")
        assert result == ["Task", "TodoWrite", "Read", "Glob", "Grep", "Bash"]

    def test_single_item(self):
        assert _parse_list("Read") == ["Read"]

    def test_empty_string(self):
        assert _parse_list("") is None

    def test_whitespace_only(self):
        assert _parse_list("   ") is None

    def test_extra_whitespace(self):
        result = _parse_list("  Task ,  Read  ,  Bash  ")
        assert result == ["Task", "Read", "Bash"]

    def test_trailing_comma(self):
        result = _parse_list("Task, Read,")
        assert result == ["Task", "Read"]

    def test_no_spaces(self):
        result = _parse_list("Task,Read,Bash")
        assert result == ["Task", "Read", "Bash"]

    def test_yaml_inline_list(self):
        result = _parse_list("[Task, Read, Bash]")
        assert result == ["Task", "Read", "Bash"]

    def test_yaml_inline_list_empty(self):
        assert _parse_list("[]") is None

    def test_yaml_inline_list_single(self):
        assert _parse_list("[Read]") == ["Read"]


# ---------------------------------------------------------------------------
# _parse_bool tests
# ---------------------------------------------------------------------------


class TestParseBool:
    def test_true_variants(self):
        assert _parse_bool("true") is True
        assert _parse_bool("True") is True
        assert _parse_bool("TRUE") is True
        assert _parse_bool("yes") is True
        assert _parse_bool("on") is True
        assert _parse_bool("1") is True

    def test_false_variants(self):
        assert _parse_bool("false") is False
        assert _parse_bool("False") is False
        assert _parse_bool("no") is False
        assert _parse_bool("off") is False
        assert _parse_bool("0") is False

    def test_whitespace(self):
        assert _parse_bool("  true  ") is True
        assert _parse_bool("  false  ") is False

    def test_empty(self):
        assert _parse_bool("") is False


# ---------------------------------------------------------------------------
# _parse_int tests
# ---------------------------------------------------------------------------


class TestParseInt:
    def test_valid_int(self):
        assert _parse_int("25") == 25
        assert _parse_int("100") == 100

    def test_zero(self):
        assert _parse_int("0") is None

    def test_negative(self):
        assert _parse_int("-5") is None

    def test_whitespace(self):
        assert _parse_int("  42  ") == 42

    def test_invalid(self):
        assert _parse_int("abc") is None
        assert _parse_int("12.5") is None

    def test_empty(self):
        assert _parse_int("") is None
        assert _parse_int("   ") is None

    def test_max_turns_zero(self):
        """Zero is not a valid positive turn count."""
        assert _parse_int("0") is None

    def test_max_turns_negative(self):
        """Negative values are not valid turn counts."""
        assert _parse_int("-10") is None


# ---------------------------------------------------------------------------
# _parse_validated_str tests
# ---------------------------------------------------------------------------


class TestParseValidatedStr:
    def test_valid_value_returned(self):
        assert _parse_validated_str("project", _VALID_MEMORY_VALUES, "memory") == "project"

    def test_valid_value_stripped(self):
        assert _parse_validated_str("  user  ", _VALID_MEMORY_VALUES, "memory") == "user"

    def test_invalid_value_returns_none(self):
        assert _parse_validated_str("globalScope", _VALID_MEMORY_VALUES, "memory") is None

    def test_empty_string_returns_none(self):
        assert _parse_validated_str("", _VALID_MEMORY_VALUES, "memory") is None

    def test_whitespace_only_returns_none(self):
        assert _parse_validated_str("   ", _VALID_MEMORY_VALUES, "memory") is None

    def test_non_string_returns_none(self):
        assert _parse_validated_str(42, _VALID_MEMORY_VALUES, "memory") is None
        assert _parse_validated_str(None, _VALID_MEMORY_VALUES, "memory") is None

    def test_all_memory_values(self):
        for val in ("user", "project", "local"):
            assert _parse_validated_str(val, _VALID_MEMORY_VALUES, "memory") == val

    def test_all_isolation_values(self):
        assert _parse_validated_str("worktree", _VALID_ISOLATION_VALUES, "isolation") == "worktree"

    def test_all_permission_mode_values(self):
        for val in ("plan", "acceptEdits", "bypassPermissions"):
            assert _parse_validated_str(val, _VALID_PERMISSION_MODE_VALUES, "permissionMode") == val

    def test_all_effort_level_values(self):
        for val in ("low", "medium", "high", "max"):
            assert _parse_validated_str(val, _VALID_EFFORT_LEVEL_VALUES, "effortLevel") == val

    def test_case_sensitive(self):
        # Validation is case-sensitive: "High" is not "high"
        assert _parse_validated_str("High", _VALID_EFFORT_LEVEL_VALUES, "effortLevel") is None


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

    def test_nested_dict(self):
        text = "mcpServers:\n  playwright: npx @playwright/mcp\n  fs: npx @mcp/fs"
        result = _parse_frontmatter(text)
        assert isinstance(result["mcpServers"], dict)
        assert result["mcpServers"]["playwright"] == "npx @playwright/mcp"
        assert result["mcpServers"]["fs"] == "npx @mcp/fs"

    def test_yaml_list_items(self):
        text = "skills:\n  - git\n  - python\n  - testing"
        result = _parse_frontmatter(text)
        assert result["skills"] == ["git", "python", "testing"]

    def test_mixed_flat_and_nested(self):
        text = "name: agent\nhooks:\n  PreToolUse: validate\nmodel: sonnet"
        result = _parse_frontmatter(text)
        assert result["name"] == "agent"
        assert result["hooks"] == {"PreToolUse": "validate"}
        assert result["model"] == "sonnet"


# ---------------------------------------------------------------------------
# ExtendedAgentDefinition tests
# ---------------------------------------------------------------------------


class TestExtendedAgentDefinition:
    def test_is_subclass_of_agent_definition(self):
        agent = ExtendedAgentDefinition(description="test", prompt="prompt")
        assert isinstance(agent, AgentDefinition)

    def test_defaults_are_none_or_false(self):
        agent = ExtendedAgentDefinition(description="test", prompt="prompt")
        assert agent.disallowed_tools is None
        assert agent.permission_mode is None
        assert agent.max_turns is None
        assert agent.skills is None
        assert agent.mcp_servers is None
        assert agent.hooks is None
        assert agent.memory is None
        assert agent.background is False
        assert agent.isolation is None
        assert agent.effort_level is None

    def test_all_fields_settable(self):
        agent = ExtendedAgentDefinition(
            description="test",
            prompt="prompt",
            tools=["Read"],
            model="sonnet",
            disallowed_tools=["Write"],
            permission_mode="bypassPermissions",
            max_turns=10,
            skills=["git"],
            mcp_servers={"playwright": "npx @playwright/mcp"},
            hooks={"PreToolUse": "validate"},
            memory="project",
            background=True,
            isolation="worktree",
            effort_level="high",
        )
        assert agent.disallowed_tools == ["Write"]
        assert agent.permission_mode == "bypassPermissions"
        assert agent.max_turns == 10
        assert agent.skills == ["git"]
        assert agent.mcp_servers == {"playwright": "npx @playwright/mcp"}
        assert agent.hooks == {"PreToolUse": "validate"}
        assert agent.memory == "project"
        assert agent.background is True
        assert agent.isolation == "worktree"
        assert agent.effort_level == "high"

    def test_inherits_base_fields(self):
        agent = ExtendedAgentDefinition(
            description="desc",
            prompt="sys prompt",
            tools=["Read", "Write"],
            model="opus",
        )
        assert agent.description == "desc"
        assert agent.prompt == "sys prompt"
        assert agent.tools == ["Read", "Write"]
        assert agent.model == "opus"


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

    def test_returns_extended_agent_definition(self, tmp_path: Path):
        path = _write_agent(tmp_path, "test.md", VALID_AGENT_MD)
        result = parse_agent_file(path)
        assert result is not None
        _, agent = result
        assert isinstance(agent, ExtendedAgentDefinition)
        assert isinstance(agent, AgentDefinition)

    def test_extended_fields_parsed(self, tmp_path: Path):
        path = _write_agent(tmp_path, "extended.md", EXTENDED_AGENT_MD)
        result = parse_agent_file(path)

        assert result is not None
        name, agent = result
        assert name == "extended-agent"
        assert agent.tools == ["Task", "Read", "Bash"]
        # Model should be normalized from full string to alias
        assert agent.model == "sonnet"
        assert agent.disallowed_tools == ["Write", "Edit"]
        assert agent.permission_mode == "bypassPermissions"
        assert agent.max_turns == 25
        assert agent.skills == ["git", "python", "testing"]
        assert agent.memory == "project"
        assert agent.background is True
        assert agent.isolation == "worktree"
        assert agent.effort_level == "high"

    def test_yaml_list_syntax_fields(self, tmp_path: Path):
        path = _write_agent(tmp_path, "list.md", EXTENDED_YAML_LIST_AGENT_MD)
        result = parse_agent_file(path)

        assert result is not None
        name, agent = result
        assert name == "list-agent"
        assert agent.tools == ["Task", "Read"]
        assert agent.disallowed_tools == ["Write", "Edit", "Bash"]
        assert agent.skills == ["git", "python", "testing"]

    def test_nested_dict_fields(self, tmp_path: Path):
        path = _write_agent(tmp_path, "nested.md", EXTENDED_NESTED_AGENT_MD)
        result = parse_agent_file(path)

        assert result is not None
        name, agent = result
        assert name == "nested-agent"
        assert agent.mcp_servers is not None
        assert "playwright" in agent.mcp_servers
        assert agent.hooks is not None
        assert "PreToolUse" in agent.hooks

    def test_full_model_string_normalized_to_sonnet(self, tmp_path: Path):
        path = _write_agent(tmp_path, "model.md", FULL_MODEL_STRING_MD)
        result = parse_agent_file(path)

        assert result is not None
        _, agent = result
        assert agent.model == "sonnet"

    def test_full_model_string_normalized_to_opus(self, tmp_path: Path):
        path = _write_agent(tmp_path, "opus.md", OPUS_MODEL_MD)
        result = parse_agent_file(path)

        assert result is not None
        _, agent = result
        assert agent.model == "opus"

    def test_full_model_string_normalized_to_haiku(self, tmp_path: Path):
        path = _write_agent(tmp_path, "haiku.md", HAIKU_MODEL_MD)
        result = parse_agent_file(path)

        assert result is not None
        _, agent = result
        assert agent.model == "haiku"

    def test_effort_level_and_permission_mode_parsed(self, tmp_path: Path):
        path = _write_agent(tmp_path, "effort.md", EFFORT_LEVEL_AGENT_MD)
        result = parse_agent_file(path)

        assert result is not None
        name, agent = result
        assert name == "effort-agent"
        assert agent.model == "sonnet"
        assert agent.effort_level == "max"
        assert agent.permission_mode == "plan"

    def test_invalid_validated_fields_default_to_none(self, tmp_path: Path):
        path = _write_agent(tmp_path, "invalid.md", INVALID_VALIDATED_FIELDS_MD)
        result = parse_agent_file(path)

        assert result is not None
        _, agent = result
        # All invalid values should be rejected and default to None
        assert agent.memory is None
        assert agent.isolation is None
        assert agent.permission_mode is None
        assert agent.effort_level is None

    def test_optional_fields_default_none(self, tmp_path: Path):
        path = _write_agent(tmp_path, "minimal.md", MINIMAL_AGENT_MD)
        result = parse_agent_file(path)

        assert result is not None
        _, agent = result
        assert agent.disallowed_tools is None
        assert agent.permission_mode is None
        assert agent.max_turns is None
        assert agent.skills is None
        assert agent.mcp_servers is None
        assert agent.hooks is None
        assert agent.memory is None
        assert agent.background is False
        assert agent.isolation is None
        assert agent.effort_level is None


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

    def test_returns_dict_of_extended_agent_definitions(self, agents_dir: Path):
        _write_agent(agents_dir, "orchestrator.md", VALID_AGENT_MD)

        result = load_agents(agents_dir)
        for name, agent in result.items():
            assert isinstance(name, str)
            assert isinstance(agent, ExtendedAgentDefinition)
            assert isinstance(agent, AgentDefinition)

    def test_loads_extended_agents(self, agents_dir: Path):
        _write_agent(agents_dir, "extended.md", EXTENDED_AGENT_MD)

        result = load_agents(agents_dir)
        assert "extended-agent" in result
        agent = result["extended-agent"]
        assert agent.max_turns == 25
        assert agent.background is True


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
