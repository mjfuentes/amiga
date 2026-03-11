"""Tests for ThinkingConfig mapping in sdk_client."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from claude_agent_sdk import (
    ThinkingConfigAdaptive,
    ThinkingConfigDisabled,
    ThinkingConfigEnabled,
)

from claude.sdk_client import (
    _THINKING_BUDGET_MAX,
    _build_thinking_config,
)


class TestBuildThinkingConfig:
    """Tests for _build_thinking_config effort-to-thinking mapping."""

    def test_low_effort_returns_disabled(self):
        config = _build_thinking_config("low")
        assert config is not None
        assert config["type"] == "disabled"

    def test_medium_effort_returns_adaptive(self):
        config = _build_thinking_config("medium")
        assert config is not None
        assert config["type"] == "adaptive"

    def test_high_effort_returns_adaptive(self):
        config = _build_thinking_config("high")
        assert config is not None
        assert config["type"] == "adaptive"

    def test_max_effort_returns_enabled_with_budget(self):
        config = _build_thinking_config("max")
        assert config is not None
        assert config["type"] == "enabled"
        assert config["budget_tokens"] == _THINKING_BUDGET_MAX

    def test_max_budget_is_32000(self):
        assert _THINKING_BUDGET_MAX == 32_000

    def test_configs_are_distinct_dicts(self):
        """Each call returns a fresh dict (no shared mutable state)."""
        config_a = _build_thinking_config("low")
        config_b = _build_thinking_config("low")
        assert config_a == config_b
        assert config_a is not config_b

    def test_disabled_has_no_budget_key(self):
        config = _build_thinking_config("low")
        assert "budget_tokens" not in config

    def test_adaptive_has_no_budget_key(self):
        config = _build_thinking_config("medium")
        assert "budget_tokens" not in config

    def test_enabled_has_budget_key(self):
        config = _build_thinking_config("max")
        assert "budget_tokens" in config
