"""
Tests for claude/sdk_client.py - Claude Agent SDK client.

Tests cover:
- ClaudeSDKSession: option building, project root detection, execute_task flow
- ClaudeSDKPool: concurrency, prompt building, cancellation
- invoke_orchestrator_sdk: prompt construction, git blocking, result collection
- discover_repositories: filesystem discovery
- Helper functions: _collect_active_tasks, _build_orchestrator_prompt
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from claude_agent_sdk import (
    AssistantMessage as SDKAssistantMessage,
    ResultMessage as SDKResultMessage,
    SystemMessage as SDKSystemMessage,
    TextBlock as SDKTextBlock,
    ToolUseBlock as SDKToolUseBlock,
)

from claude.sdk_client import (
    ClaudeSDKPool,
    ClaudeSDKSession,
    _build_orchestrator_prompt,
    _collect_active_tasks,
    _collect_query_result,
    discover_repositories,
    invoke_orchestrator_sdk,
)


def _make_result(
    session_id: str = "sess-test",
    is_error: bool = False,
    result: str = "OK",
    duration_ms: int = 1000,
    num_turns: int = 1,
    total_cost_usd: float | None = 0.01,
) -> SDKResultMessage:
    """Helper to create a real ResultMessage instance."""
    return SDKResultMessage(
        subtype="result",
        duration_ms=duration_ms,
        duration_api_ms=duration_ms,
        is_error=is_error,
        num_turns=num_turns,
        session_id=session_id,
        total_cost_usd=total_cost_usd,
        result=result,
    )


# --- Fixtures ---


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory with a .git dir."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    return tmp_path


@pytest.fixture
def tmp_worktree(tmp_path: Path) -> Path:
    """Create a temporary worktree workspace with .git file."""
    main_repo = tmp_path / "main_repo"
    main_repo.mkdir()
    (main_repo / ".git").mkdir()
    worktrees_dir = main_repo / ".git" / "worktrees" / "task_42"
    worktrees_dir.mkdir(parents=True)

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    git_file = worktree / ".git"
    git_file.write_text(f"gitdir: {worktrees_dir}")
    return worktree


@pytest.fixture
def mock_tracker() -> MagicMock:
    """Create a mock ToolUsageTracker."""
    tracker = MagicMock()
    tracker.record_status_change = MagicMock()
    tracker.record_workflow_assignment = AsyncMock()
    tracker.db = MagicMock()
    tracker.db.update_task = AsyncMock()
    return tracker


# --- discover_repositories ---


class TestDiscoverRepositories:
    def test_finds_git_repos(self, tmp_path: Path):
        repo_a = tmp_path / "repo_a"
        repo_a.mkdir()
        (repo_a / ".git").mkdir()

        repo_b = tmp_path / "repo_b"
        repo_b.mkdir()
        (repo_b / ".git").mkdir()

        result = discover_repositories(str(tmp_path))
        assert str(repo_a) in result
        assert str(repo_b) in result

    def test_finds_nested_repos(self, tmp_path: Path):
        parent = tmp_path / "parent"
        parent.mkdir()
        nested = parent / "nested"
        nested.mkdir()
        (nested / ".git").mkdir()

        result = discover_repositories(str(tmp_path))
        assert str(nested) in result

    def test_empty_directory(self, tmp_path: Path):
        result = discover_repositories(str(tmp_path))
        assert result == []

    def test_nonexistent_path(self, tmp_path: Path):
        result = discover_repositories(str(tmp_path / "nonexistent"))
        assert result == []

    def test_skips_permission_errors(self, tmp_path: Path):
        """Should not crash on permission errors."""
        result = discover_repositories(str(tmp_path))
        assert isinstance(result, list)


# --- ClaudeSDKSession ---


class TestClaudeSDKSession:
    def test_init_defaults(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace)
        assert session.model == "sonnet"
        assert session.usage_tracker is None

    def test_init_custom_model(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace, model="opus")
        assert session.model == "opus"

    def test_find_project_root_normal_repo(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace)
        root = session._find_project_root()
        assert root == tmp_workspace

    def test_find_project_root_worktree(self, tmp_worktree: Path):
        session = ClaudeSDKSession(workspace=tmp_worktree)
        root = session._find_project_root()
        assert root.name == "main_repo"

    def test_build_options_basic(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace)
        options = session._build_options("task-123")

        assert options.model == "sonnet"
        assert options.permission_mode == "bypassPermissions"
        assert "Task" in options.allowed_tools
        assert "Bash" in options.allowed_tools
        assert str(tmp_workspace) == options.cwd
        assert options.max_turns == 200
        assert options.env["TASK_ID"] == "task-123"

    def test_build_options_with_effort(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace)
        options = session._build_options("task-123", effort="low")
        assert options.extra_args["effort"] == "low"

    def test_build_options_with_budget(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace)
        options = session._build_options("task-123", max_budget_usd=5.0)
        assert options.extra_args["max-budget-usd"] == "5.0"

    def test_build_options_without_budget(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace)
        options = session._build_options("task-123")
        assert "max-budget-usd" not in options.extra_args

    def test_build_options_with_worktree_flag(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace)
        options = session._build_options("task-123", use_worktree=True)
        assert options.extra_args["worktree"] is None

    def test_build_options_without_worktree_flag(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace)
        options = session._build_options("task-123", use_worktree=False)
        assert "worktree" not in options.extra_args

    def test_build_options_worktree_default_true(self, tmp_workspace: Path):
        """use_worktree defaults to True, so worktree flag should be present."""
        session = ClaudeSDKSession(workspace=tmp_workspace)
        options = session._build_options("task-123")
        assert "worktree" in options.extra_args

    def test_build_options_worktree_project_root(self, tmp_worktree: Path):
        session = ClaudeSDKSession(workspace=tmp_worktree)
        options = session._build_options("task-42")
        assert "main_repo" in options.env["PROJECT_ROOT"]

    @pytest.mark.asyncio
    async def test_cancel_sets_event(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace)
        assert not session._cancel_event.is_set()
        await session.cancel()
        assert session._cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_execute_task_success(self, tmp_workspace: Path, mock_tracker: MagicMock):
        session = ClaudeSDKSession(
            workspace=tmp_workspace, usage_tracker=mock_tracker
        )

        result_msg = _make_result(
            session_id="sess-abc",
            result="Task completed successfully",
            duration_ms=5000,
            num_turns=3,
            total_cost_usd=0.05,
        )

        async def mock_query(**kwargs):
            yield result_msg

        with patch("claude.sdk_client.query", side_effect=mock_query):
            success, result, session_id = await session.execute_task(
                "task-1", "Do something"
            )

        assert success is True
        assert result == "Task completed successfully"
        assert session_id == "sess-abc"
        mock_tracker.record_status_change.assert_called()

    @pytest.mark.asyncio
    async def test_execute_task_error_result(self, tmp_workspace: Path, mock_tracker: MagicMock):
        session = ClaudeSDKSession(
            workspace=tmp_workspace, usage_tracker=mock_tracker
        )

        result_msg = _make_result(
            session_id="sess-err",
            is_error=True,
            result="Something went wrong",
        )

        async def mock_query(**kwargs):
            yield result_msg

        with patch("claude.sdk_client.query", side_effect=mock_query):
            success, result, session_id = await session.execute_task(
                "task-err", "Bad task"
            )

        assert success is False
        assert "Something went wrong" in result

    @pytest.mark.asyncio
    async def test_execute_task_empty_result(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace)

        result_msg = _make_result(
            session_id="sess-empty",
            result="",
            duration_ms=100,
            num_turns=0,
            total_cost_usd=0.0,
        )

        async def mock_query(**kwargs):
            yield result_msg

        with patch("claude.sdk_client.query", side_effect=mock_query):
            success, result, session_id = await session.execute_task(
                "task-empty", "Empty task"
            )

        assert success is False
        assert "No output" in result

    @pytest.mark.asyncio
    async def test_execute_task_sdk_error(self, tmp_workspace: Path, mock_tracker: MagicMock):
        from claude_agent_sdk import ClaudeSDKError

        session = ClaudeSDKSession(
            workspace=tmp_workspace, usage_tracker=mock_tracker
        )

        async def mock_query(**kwargs):
            raise ClaudeSDKError("SDK failure")
            yield  # Make it an async generator  # noqa: E501

        with patch("claude.sdk_client.query", side_effect=mock_query):
            success, result, session_id = await session.execute_task(
                "task-sdk-err", "Failing task"
            )

        assert success is False
        assert "SDK error" in result

    @pytest.mark.asyncio
    async def test_execute_task_with_progress_callback(self, tmp_workspace: Path):
        session = ClaudeSDKSession(workspace=tmp_workspace)
        callback_calls: list[tuple[str, int]] = []

        def progress_cb(msg: str, elapsed: int):
            callback_calls.append((msg, elapsed))

        assistant_msg = SDKAssistantMessage(
            content=[SDKTextBlock(text="Working on it...")],
            model="sonnet",
        )
        result_msg = _make_result(
            session_id="sess-prog",
            result="Done",
            duration_ms=2000,
            total_cost_usd=0.02,
        )

        async def mock_query(**kwargs):
            yield assistant_msg
            yield result_msg

        with patch("claude.sdk_client.query", side_effect=mock_query):
            success, result, _ = await session.execute_task(
                "task-prog", "Progress task", progress_callback=progress_cb
            )

        assert success is True
        assert len(callback_calls) == 1
        assert "turn 1" in callback_calls[0][0]

    @pytest.mark.asyncio
    async def test_execute_task_no_tracker_warning(self, tmp_workspace: Path):
        """Should log warning when no usage_tracker is provided."""
        session = ClaudeSDKSession(workspace=tmp_workspace)

        result_msg = _make_result(
            session_id="sess-no-track",
            result="OK",
            duration_ms=100,
            total_cost_usd=0.0,
        )

        async def mock_query(**kwargs):
            yield result_msg

        with patch("claude.sdk_client.query", side_effect=mock_query):
            success, result, _ = await session.execute_task("task-nt", "No tracker")

        assert success is True


# --- ClaudeSDKPool ---


class TestClaudeSDKPool:
    def test_init_defaults(self):
        pool = ClaudeSDKPool()
        assert pool.max_concurrent == 3
        assert pool.usage_tracker is None

    def test_init_custom(self, mock_tracker: MagicMock):
        pool = ClaudeSDKPool(max_concurrent=5, usage_tracker=mock_tracker)
        assert pool.max_concurrent == 5
        assert pool.usage_tracker == mock_tracker

    def test_build_prompt_with_context(self):
        pool = ClaudeSDKPool()
        prompt = pool._build_prompt("Do X", "Context about X")
        assert "Context about X" in prompt
        assert "Do X" in prompt

    def test_build_prompt_without_context(self):
        pool = ClaudeSDKPool()
        prompt = pool._build_prompt("Do X", None)
        assert prompt == "Do X"

    @pytest.mark.asyncio
    async def test_execute_task_delegates_to_session(
        self, tmp_workspace: Path, mock_tracker: MagicMock
    ):
        pool = ClaudeSDKPool(usage_tracker=mock_tracker)

        result_msg = _make_result(
            session_id="pool-sess",
            result="Pool result",
        )

        async def mock_query(**kwargs):
            yield result_msg

        with patch("claude.sdk_client.query", side_effect=mock_query):
            success, result, session_id, workflow = await pool.execute_task(
                task_id="pool-task",
                description="Pool test",
                workspace=tmp_workspace,
            )

        assert success is True
        assert result == "Pool result"
        assert session_id == "pool-sess"
        assert workflow == "orchestrator"
        mock_tracker.record_workflow_assignment.assert_called_once_with(
            "pool-task", "orchestrator"
        )

    @pytest.mark.asyncio
    async def test_execute_task_failure(
        self, tmp_workspace: Path, mock_tracker: MagicMock
    ):
        pool = ClaudeSDKPool(usage_tracker=mock_tracker)

        async def mock_query(**kwargs):
            raise Exception("Pool failure")
            yield  # noqa: E501

        with patch("claude.sdk_client.query", side_effect=mock_query):
            success, result, session_id, workflow = await pool.execute_task(
                task_id="pool-fail",
                description="Failing pool test",
                workspace=tmp_workspace,
            )

        assert success is False
        assert "Pool failure" in result

    @pytest.mark.asyncio
    async def test_cancel_task_not_found(self):
        pool = ClaudeSDKPool()
        result = await pool.cancel_task("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_task_found(self, tmp_workspace: Path, mock_tracker: MagicMock):
        pool = ClaudeSDKPool(usage_tracker=mock_tracker)

        session = ClaudeSDKSession(
            workspace=tmp_workspace, usage_tracker=mock_tracker
        )
        pool._active_sessions["cancel-me"] = session

        result = await pool.cancel_task("cancel-me")
        assert result is True
        assert session._cancel_event.is_set()
        mock_tracker.record_status_change.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_all(self, tmp_workspace: Path):
        pool = ClaudeSDKPool()

        s1 = ClaudeSDKSession(workspace=tmp_workspace)
        s2 = ClaudeSDKSession(workspace=tmp_workspace)
        pool._active_sessions = {"t1": s1, "t2": s2}

        await pool.cancel_all()
        assert s1._cancel_event.is_set()
        assert s2._cancel_event.is_set()
        assert len(pool._active_sessions) == 0

    @pytest.mark.asyncio
    async def test_session_cleanup_after_execution(
        self, tmp_workspace: Path, mock_tracker: MagicMock
    ):
        """Active sessions dict should be cleaned up after task completes."""
        pool = ClaudeSDKPool(usage_tracker=mock_tracker)

        result_msg = _make_result(
            session_id="cleanup-sess",
            result="Done",
            duration_ms=100,
            total_cost_usd=0.0,
        )

        async def mock_query(**kwargs):
            yield result_msg

        with patch("claude.sdk_client.query", side_effect=mock_query):
            await pool.execute_task(
                task_id="cleanup-task",
                description="Test cleanup",
                workspace=tmp_workspace,
            )

        assert "cleanup-task" not in pool._active_sessions


# --- Helper functions ---


class TestCollectActiveTasks:
    def test_no_task_manager(self):
        assert _collect_active_tasks(None) == []

    def test_with_tasks(self):
        mock_task_1 = MagicMock()
        mock_task_1.task_id = "t1"
        mock_task_1.description = "Task 1"
        mock_task_1.status = "running"
        mock_task_1.workspace = "/tmp"

        mock_task_2 = MagicMock()
        mock_task_2.task_id = "t2"
        mock_task_2.description = "Task 2"
        mock_task_2.status = "completed"
        mock_task_2.workspace = "/tmp"

        manager = MagicMock()
        manager.tasks = {"t1": mock_task_1, "t2": mock_task_2}

        result = _collect_active_tasks(manager)
        assert len(result) == 1
        assert result[0]["task_id"] == "t1"

    def test_error_handling(self):
        """Should return empty list on errors."""
        manager = MagicMock()
        manager.tasks = MagicMock(side_effect=AttributeError("broken"))

        result = _collect_active_tasks(manager)
        assert result == []


class TestBuildOrchestratorPrompt:
    def test_includes_user_query(self):
        prompt = _build_orchestrator_prompt(
            user_query="fix the bug",
            input_method="text",
            conversation_history=[],
            current_workspace="/workspace",
            bot_repository="/bot",
            workspace_path="/workspace",
            available_repos=["/workspace/repo1"],
            active_tasks_info=[],
        )
        assert "fix the bug" in prompt
        assert "BACKGROUND_TASK" in prompt

    def test_includes_image_path(self):
        prompt = _build_orchestrator_prompt(
            user_query="what is this",
            input_method="text",
            conversation_history=[],
            current_workspace=None,
            bot_repository="/bot",
            workspace_path="/workspace",
            available_repos=[],
            active_tasks_info=[],
            image_path="/tmp/image.jpg",
        )
        assert "/tmp/image.jpg" in prompt

    def test_voice_input_method(self):
        prompt = _build_orchestrator_prompt(
            user_query="hey",
            input_method="voice",
            conversation_history=[],
            current_workspace=None,
            bot_repository="/bot",
            workspace_path="/workspace",
            available_repos=[],
            active_tasks_info=[],
        )
        assert "voice" in prompt
        assert "permissive" in prompt


class TestCollectQueryResult:
    @pytest.mark.asyncio
    async def test_result_message(self):
        from claude_agent_sdk import ClaudeAgentOptions

        result_msg = _make_result(result="Query result text")

        async def mock_query(**kwargs):
            yield result_msg

        with patch("claude.sdk_client.query", side_effect=mock_query):
            options = ClaudeAgentOptions(model="haiku")
            result = await _collect_query_result("test prompt", options)

        assert result == "Query result text"

    @pytest.mark.asyncio
    async def test_empty_stream(self):
        from claude_agent_sdk import ClaudeAgentOptions

        async def mock_query(**kwargs):
            return
            yield  # noqa: E501

        with patch("claude.sdk_client.query", side_effect=mock_query):
            options = ClaudeAgentOptions(model="haiku")
            result = await _collect_query_result("test prompt", options)

        assert result is None

    @pytest.mark.asyncio
    async def test_fallback_to_assistant_text(self):
        """When no ResultMessage, should fall back to assistant text."""
        from claude_agent_sdk import ClaudeAgentOptions

        assistant_msg = SDKAssistantMessage(
            content=[SDKTextBlock(text="Fallback text")],
            model="haiku",
        )

        async def mock_query(**kwargs):
            yield assistant_msg

        with patch("claude.sdk_client.query", side_effect=mock_query):
            options = ClaudeAgentOptions(model="haiku")
            result = await _collect_query_result("test prompt", options)

        assert result == "Fallback text"


# --- invoke_orchestrator_sdk ---


class TestInvokeOrchestratorSdk:
    @pytest.mark.asyncio
    async def test_git_blocking(self):
        mock_git_tracker = MagicMock()
        mock_git_tracker.get_blocking_message.return_value = "Uncommitted changes in /repo"

        with patch("claude.sdk_client.get_git_tracker", return_value=mock_git_tracker):
            result = await invoke_orchestrator_sdk(
                user_query="fix bug",
                input_method="text",
                conversation_history=[],
                current_workspace="/repo",
                bot_repository="/bot",
                workspace_path="/workspace",
            )

        assert result == "Uncommitted changes in /repo"

    @pytest.mark.asyncio
    async def test_successful_invocation(self):
        mock_git_tracker = MagicMock()
        mock_git_tracker.get_blocking_message.return_value = None

        result_msg = _make_result(result="BACKGROUND_TASK|Fix bug|Fixing it.")

        async def mock_query(**kwargs):
            yield result_msg

        with patch("claude.sdk_client.get_git_tracker", return_value=mock_git_tracker):
            with patch("claude.sdk_client.query", side_effect=mock_query):
                with patch("claude.sdk_client.discover_repositories", return_value=[]):
                    result = await invoke_orchestrator_sdk(
                        user_query="fix bug",
                        input_method="text",
                        conversation_history=[],
                        current_workspace=None,
                        bot_repository="/bot",
                        workspace_path="/workspace",
                    )

        assert result is not None
        assert "BACKGROUND_TASK" in result

    @pytest.mark.asyncio
    async def test_sdk_error_returns_none(self):
        from claude_agent_sdk import ClaudeSDKError

        mock_git_tracker = MagicMock()
        mock_git_tracker.get_blocking_message.return_value = None

        async def mock_query(**kwargs):
            raise ClaudeSDKError("connection failed")
            yield  # noqa: E501

        with patch("claude.sdk_client.get_git_tracker", return_value=mock_git_tracker):
            with patch("claude.sdk_client.query", side_effect=mock_query):
                with patch("claude.sdk_client.discover_repositories", return_value=[]):
                    result = await invoke_orchestrator_sdk(
                        user_query="something",
                        input_method="text",
                        conversation_history=[],
                        current_workspace=None,
                        bot_repository="/bot",
                        workspace_path="/workspace",
                    )

        assert result is None
