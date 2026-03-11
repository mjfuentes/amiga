"""
Load agent definitions from .claude/agents/*.md files.

Parses YAML frontmatter and markdown body into AgentDefinition instances
compatible with the Claude Agent SDK.
"""

import logging
import re
from pathlib import Path
from typing import Literal

from claude_agent_sdk import AgentDefinition

logger = logging.getLogger(__name__)

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

_SKIP_FILES = frozenset({"CHANGELOG.md"})

_MODEL_KEYWORDS: list[tuple[str, Literal["sonnet", "opus", "haiku", "inherit"]]] = [
    ("inherit", "inherit"),
    ("sonnet", "sonnet"),
    ("opus", "opus"),
    ("haiku", "haiku"),
]


def _parse_model(raw: str) -> Literal["sonnet", "opus", "haiku", "inherit"] | None:
    """Map a raw model string to a valid SDK model literal.

    Returns None if no recognized model keyword is found.
    """
    normalized = raw.strip().lower()
    if not normalized:
        return None

    for keyword, model_value in _MODEL_KEYWORDS:
        if keyword in normalized:
            return model_value

    return None


def _parse_tools(raw: str) -> list[str] | None:
    """Parse a comma-separated tools string into a list.

    Returns None if the input is empty or whitespace-only.
    """
    stripped = raw.strip()
    if not stripped:
        return None

    return [tool.strip() for tool in stripped.split(",") if tool.strip()]


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Parse simple key: value pairs from a YAML frontmatter block.

    Only handles flat key-value pairs (no nested YAML).
    Returns a dict of string keys to string values.
    """
    result: dict[str, str] = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key:
                result[key] = value
    return result


def parse_agent_file(file_path: Path) -> tuple[str, AgentDefinition] | None:
    """Parse a single agent markdown file into a named AgentDefinition.

    Reads the file, extracts YAML frontmatter for metadata, and uses
    everything after the closing --- delimiter as the system prompt.

    Args:
        file_path: Path to a .md file with YAML frontmatter.

    Returns:
        A (name, AgentDefinition) tuple, or None if parsing fails.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to read agent file %s: %s", file_path, e)
        return None

    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        logger.debug("No frontmatter found in %s, skipping", file_path.name)
        return None

    frontmatter_text = match.group(1)
    prompt = content[match.end():].strip()

    metadata = _parse_frontmatter(frontmatter_text)

    name = metadata.get("name", "").strip()
    if not name:
        logger.warning("Agent file %s missing 'name' in frontmatter, skipping", file_path.name)
        return None

    description = metadata.get("description", "").strip()
    if not description:
        logger.warning("Agent file %s missing 'description' in frontmatter, skipping", file_path.name)
        return None

    tools = _parse_tools(metadata.get("tools", ""))
    model = _parse_model(metadata.get("model", ""))

    agent = AgentDefinition(
        description=description,
        prompt=prompt,
        tools=tools,
        model=model,
    )

    return (name, agent)


def load_agents(agents_dir: Path) -> dict[str, AgentDefinition]:
    """Load all agent definitions from a directory of markdown files.

    Globs for *.md files, skipping known non-agent files like CHANGELOG.md.

    Args:
        agents_dir: Directory containing agent .md files.

    Returns:
        Dict mapping agent name to AgentDefinition.
    """
    agents: dict[str, AgentDefinition] = {}

    md_files = sorted(agents_dir.glob("*.md"))

    for file_path in md_files:
        if file_path.name in _SKIP_FILES:
            logger.debug("Skipping non-agent file: %s", file_path.name)
            continue

        result = parse_agent_file(file_path)
        if result is not None:
            name, agent_def = result
            agents[name] = agent_def

    logger.info("Loaded %d agent definitions from %s", len(agents), agents_dir)
    return agents


def load_project_agents(project_root: Path | None = None) -> dict[str, AgentDefinition]:
    """Load agent definitions from a project's .claude/agents/ directory.

    Args:
        project_root: Root of the project. Falls back to cwd if None.

    Returns:
        Dict mapping agent name to AgentDefinition.
        Empty dict if the agents directory does not exist.
    """
    root = project_root if project_root is not None else Path.cwd()
    agents_dir = root / ".claude" / "agents"

    if not agents_dir.is_dir():
        logger.debug("No agents directory found at %s", agents_dir)
        return {}

    return load_agents(agents_dir)
