"""
Load agent definitions from .claude/agents/*.md files.

Parses YAML frontmatter and markdown body into ExtendedAgentDefinition instances
compatible with the Claude Agent SDK (subclass of AgentDefinition).
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from claude_agent_sdk import AgentDefinition

logger = logging.getLogger(__name__)

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

_SKIP_FILES = frozenset({"CHANGELOG.md"})

_MODEL_ALIASES: tuple[tuple[str, Literal["sonnet", "opus", "haiku", "inherit"]], ...] = (
    ("inherit", "inherit"),
    ("sonnet", "sonnet"),
    ("opus", "opus"),
    ("haiku", "haiku"),
)

_VALID_MEMORY_VALUES: frozenset[str] = frozenset({"user", "project", "local"})
_VALID_ISOLATION_VALUES: frozenset[str] = frozenset({"worktree"})
_VALID_PERMISSION_MODE_VALUES: frozenset[str] = frozenset({"plan", "acceptEdits", "bypassPermissions"})
_VALID_EFFORT_LEVEL_VALUES: frozenset[str] = frozenset({"low", "medium", "high", "max"})


@dataclass
class ExtendedAgentDefinition(AgentDefinition):
    """Agent definition with extended frontmatter fields.

    Inherits from the SDK's AgentDefinition (description, prompt, tools, model)
    and adds optional fields parsed from agent markdown frontmatter.

    All new fields use immutable defaults (None or False). Dict/list fields
    default to None rather than mutable empty containers.
    """

    disallowed_tools: list[str] | None = None
    permission_mode: str | None = None
    max_turns: int | None = None
    skills: list[str] | None = None
    mcp_servers: dict[str, Any] | None = None
    hooks: dict[str, Any] | None = None
    memory: str | None = None
    background: bool = False
    isolation: str | None = None
    effort_level: str | None = None


def _parse_model(raw: str) -> Literal["sonnet", "opus", "haiku", "inherit"] | None:
    """Map a raw model string to a valid SDK model alias.

    Accepts short aliases directly (``sonnet``, ``opus``, ``haiku``, ``inherit``)
    and normalizes full model identifiers (e.g. ``claude-sonnet-4-5-20250929``)
    to their short form.

    Returns None if no recognized model keyword is found.
    """
    normalized = raw.strip().lower()
    if not normalized:
        return None

    # Fast path: exact match on short aliases
    if normalized in ("sonnet", "opus", "haiku", "inherit"):
        return normalized  # type: ignore[return-value]

    # Fallback: substring search for full model identifiers
    for keyword, alias in _MODEL_ALIASES:
        if keyword in normalized:
            return alias

    return None


def _parse_validated_str(
    raw: Any, valid_values: frozenset[str], field_name: str
) -> str | None:
    """Parse and validate a string against a set of allowed values.

    Returns the stripped string if it is in ``valid_values``, None otherwise.
    Logs a warning when an unrecognized value is encountered.
    """
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if stripped not in valid_values:
        logger.warning(
            "Unrecognized %s value '%s', expected one of %s",
            field_name,
            stripped,
            sorted(valid_values),
        )
        return None
    return stripped


def _parse_list(raw: str) -> list[str] | None:
    """Parse a comma-separated string into a list of stripped tokens.

    Also handles YAML-style inline lists: ``[a, b, c]``.
    Returns None if the input is empty or whitespace-only.
    """
    stripped = raw.strip()
    if not stripped:
        return None

    # Handle YAML inline list syntax: [item1, item2]
    if stripped.startswith("[") and stripped.endswith("]"):
        stripped = stripped[1:-1].strip()
        if not stripped:
            return None

    return [item.strip() for item in stripped.split(",") if item.strip()]


def _parse_bool(raw: str) -> bool:
    """Parse a YAML-style boolean string.

    Recognizes ``true``, ``yes``, ``on``, ``1`` as True (case-insensitive).
    Everything else is False.
    """
    return raw.strip().lower() in ("true", "yes", "on", "1")


def _parse_int(raw: str) -> int | None:
    """Parse an integer string, returning None on failure."""
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        result = int(stripped)
    except ValueError:
        return None
    return result if result > 0 else None



def _coerce_optional_str(raw: Any) -> str | None:
    """Coerce a raw value to a stripped string, returning None if empty."""
    if isinstance(raw, str):
        stripped = raw.strip()
        return stripped if stripped else None
    return None


def _coerce_optional_list(raw: Any) -> list[str] | None:
    """Coerce a raw value to a list of stripped strings.

    Handles both comma-separated strings and YAML-parsed lists.
    Returns None if the result would be empty.
    """
    if isinstance(raw, str):
        return _parse_list(raw)
    if isinstance(raw, list):
        result = [str(item).strip() for item in raw if str(item).strip()]
        return result if result else None
    return None


def _collect_nested_lines(
    lines: list[str], start: int, base_indent: int
) -> tuple[list[str], int]:
    """Collect indented lines belonging to a nested YAML block.

    Skips blank lines and stops when indentation returns to or below
    ``base_indent``.

    Args:
        lines: All lines of the frontmatter text.
        start: Index of the first line after the parent key.
        base_indent: Indentation level of the parent key.

    Returns:
        A tuple of (collected lines, next index to resume parsing).
    """
    collected: list[str] = []
    i = start
    while i < len(lines):
        next_line = lines[i]
        next_stripped = next_line.strip()
        if not next_stripped:
            i += 1
            continue
        next_indent = len(next_line) - len(next_line.lstrip())
        if next_indent <= base_indent:
            break
        collected.append(next_line)
        i += 1
    return collected, i


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse YAML frontmatter supporting flat values and one-level nesting.

    Handles:
    - Simple ``key: value`` pairs (strings)
    - Nested blocks (dict values via indented children)
    - YAML list items (``- item`` syntax under a parent key)

    Does NOT handle arbitrary deep nesting or complex YAML features.
    For full YAML support, add PyYAML as a dependency.

    Returns a dict mapping string keys to parsed values.
    """
    result: dict[str, Any] = {}
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if ":" not in stripped:
            i += 1
            continue

        # Determine indentation of this line
        content = line.lstrip()
        current_indent = len(line) - len(content)

        key, _, value = content.partition(":")
        key = key.strip()
        value = value.strip()

        if not key:
            i += 1
            continue

        if value:
            # Simple key: value on one line
            result[key] = value
            i += 1
        else:
            # Key with no inline value — check for nested block or list
            i += 1
            nested_lines, i = _collect_nested_lines(lines, i, current_indent)

            if not nested_lines:
                result[key] = ""
                continue

            # Detect if it's a list (lines starting with "- ")
            first_content = nested_lines[0].strip()
            if first_content.startswith("- "):
                items: list[str] = []
                for nl in nested_lines:
                    nc = nl.strip()
                    if nc.startswith("- "):
                        items.append(nc[2:].strip())
                result[key] = items
            else:
                # Parse as nested dict
                nested: dict[str, Any] = {}
                for nl in nested_lines:
                    nc = nl.strip()
                    if ":" in nc:
                        nk, _, nv = nc.partition(":")
                        nk = nk.strip()
                        nv = nv.strip()
                        if nk:
                            nested[nk] = nv
                result[key] = nested

    return result


def _build_agent_definition(
    *,
    description: str,
    prompt: str,
    metadata: dict[str, Any],
) -> ExtendedAgentDefinition:
    """Construct an ExtendedAgentDefinition from parsed frontmatter metadata.

    Applies type coercion and model alias normalization.

    Args:
        description: Agent description string.
        prompt: System prompt (markdown body after frontmatter).
        metadata: Parsed frontmatter key-value pairs.

    Returns:
        A fully populated ExtendedAgentDefinition.
    """
    # Core fields
    tools = _coerce_optional_list(metadata.get("tools", ""))

    model_raw = metadata.get("model", "")
    model = _parse_model(model_raw) if isinstance(model_raw, str) else None

    # Extended fields
    disallowed_tools = _coerce_optional_list(metadata.get("disallowedTools", ""))

    max_turns_raw = metadata.get("maxTurns", "")
    max_turns: int | None = None
    if isinstance(max_turns_raw, str):
        max_turns = _parse_int(max_turns_raw)
    elif isinstance(max_turns_raw, int):
        max_turns = max_turns_raw if max_turns_raw > 0 else None

    skills = _coerce_optional_list(metadata.get("skills", ""))

    mcp_servers_raw = metadata.get("mcpServers")
    mcp_servers: dict[str, Any] | None = (
        mcp_servers_raw if isinstance(mcp_servers_raw, dict) else None
    )

    hooks_raw = metadata.get("hooks")
    hooks: dict[str, Any] | None = (
        hooks_raw if isinstance(hooks_raw, dict) else None
    )

    memory = _parse_validated_str(
        metadata.get("memory", ""), _VALID_MEMORY_VALUES, "memory"
    )

    background_raw = metadata.get("background", "")
    background: bool = False
    if isinstance(background_raw, str):
        background = _parse_bool(background_raw)
    elif isinstance(background_raw, bool):
        background = background_raw

    isolation = _parse_validated_str(
        metadata.get("isolation", ""), _VALID_ISOLATION_VALUES, "isolation"
    )

    # Override permission_mode with validated parsing if raw value is present
    permission_mode = _parse_validated_str(
        metadata.get("permissionMode", ""),
        _VALID_PERMISSION_MODE_VALUES,
        "permissionMode",
    )

    effort_level = _parse_validated_str(
        metadata.get("effortLevel", ""),
        _VALID_EFFORT_LEVEL_VALUES,
        "effortLevel",
    )

    return ExtendedAgentDefinition(
        description=description,
        prompt=prompt,
        tools=tools,
        model=model,
        disallowed_tools=disallowed_tools,
        permission_mode=permission_mode,
        max_turns=max_turns,
        skills=skills,
        mcp_servers=mcp_servers,
        hooks=hooks,
        memory=memory,
        background=background,
        isolation=isolation,
        effort_level=effort_level,
    )


def parse_agent_file(file_path: Path) -> tuple[str, ExtendedAgentDefinition] | None:
    """Parse a single agent markdown file into a named ExtendedAgentDefinition.

    Reads the file, extracts YAML frontmatter for metadata, and uses
    everything after the closing --- delimiter as the system prompt.

    Args:
        file_path: Path to a .md file with YAML frontmatter.

    Returns:
        A (name, ExtendedAgentDefinition) tuple, or None if parsing fails.
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

    name_raw = metadata.get("name", "")
    name = name_raw.strip() if isinstance(name_raw, str) else ""
    if not name:
        logger.warning("Agent file %s missing 'name' in frontmatter, skipping", file_path.name)
        return None

    description_raw = metadata.get("description", "")
    description = description_raw.strip() if isinstance(description_raw, str) else ""
    if not description:
        logger.warning("Agent file %s missing 'description' in frontmatter, skipping", file_path.name)
        return None

    agent = _build_agent_definition(
        description=description,
        prompt=prompt,
        metadata=metadata,
    )

    return (name, agent)


def load_agents(agents_dir: Path) -> dict[str, ExtendedAgentDefinition]:
    """Load all agent definitions from a directory of markdown files.

    Globs for *.md files, skipping known non-agent files like CHANGELOG.md.

    Args:
        agents_dir: Directory containing agent .md files.

    Returns:
        Dict mapping agent name to ExtendedAgentDefinition.
    """
    agents: dict[str, ExtendedAgentDefinition] = {}

    md_files = sorted(agents_dir.glob("*.md"))

    for file_path in md_files:
        if file_path.is_symlink():
            logger.warning("Skipping symlink %s in agents directory", file_path.name)
            continue

        if file_path.name in _SKIP_FILES:
            logger.debug("Skipping non-agent file: %s", file_path.name)
            continue

        result = parse_agent_file(file_path)
        if result is not None:
            name, agent_def = result
            agents[name] = agent_def

    logger.info("Loaded %d agent definitions from %s", len(agents), agents_dir)
    return agents


def load_project_agents(project_root: Path | None = None) -> dict[str, ExtendedAgentDefinition]:
    """Load agent definitions from a project's .claude/agents/ directory.

    Args:
        project_root: Root of the project. Falls back to cwd if None.

    Returns:
        Dict mapping agent name to ExtendedAgentDefinition.
        Empty dict if the agents directory does not exist.
    """
    root = project_root if project_root is not None else Path.cwd()
    agents_dir = root / ".claude" / "agents"

    if not agents_dir.is_dir():
        logger.debug("No agents directory found at %s", agents_dir)
        return {}

    return load_agents(agents_dir)
