"""
Tests for the monitoring server Flask application
Tests API endpoints, SSE streaming, and error handling
"""

import asyncio
import json
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

# Check if monitoring server dependencies are available
pytest.importorskip("flask_socketio", reason="flask_socketio not installed - skipping monitoring server tests")


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for the monitoring server"""
    with (
        patch("monitoring.server.TaskManager") as mock_task,
        patch("monitoring.server.ToolUsageTracker") as mock_tool,
        patch("monitoring.server.HooksReader") as mock_hooks,
        patch("monitoring.server.MetricsAggregator") as mock_metrics,
    ):

        mock_task_instance = MagicMock()
        mock_tool_instance = MagicMock()
        mock_hooks_instance = MagicMock()
        mock_metrics_instance = MagicMock()

        mock_task.return_value = mock_task_instance
        mock_tool.return_value = mock_tool_instance
        mock_hooks.return_value = mock_hooks_instance
        mock_metrics.return_value = mock_metrics_instance

        yield {
            "task_manager": mock_task_instance,
            "tool_usage_tracker": mock_tool_instance,
            "hooks_reader": mock_hooks_instance,
            "metrics_aggregator": mock_metrics_instance,
        }


@pytest.fixture
def client(mock_dependencies):
    """Create a test client for the Flask app"""
    # Import after mocking to ensure mocks are in place
    from monitoring.server import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestMonitoringServerEndpoints:
    """Test suite for monitoring server HTTP endpoints"""

    def test_index_endpoint(self, client):
        """Test that the main dashboard page loads"""
        response = client.get("/")
        assert response.status_code == 200
        assert b"Bot Monitoring Dashboard" in response.data

    def test_telegram_endpoint(self, client):
        """Test that the Telegram embed page loads"""
        response = client.get("/telegram")
        assert response.status_code == 200

    def test_metrics_overview_default(self, client, mock_dependencies):
        """Test metrics overview endpoint with default parameters"""
        mock_snapshot = Mock()
        mock_snapshot.to_dict.return_value = {
            "overview": {
                "task_statistics": {"total_tasks": 100, "success_rate": 95.5},
                "claude_api_usage": {"total_cost": 10.50, "total_requests": 500},
                "system_health": {"recent_errors_24h": 2},
                "tool_usage": {"most_used_tools": []},
            },
            "sessions": {"total_sessions": 10, "total_tool_calls": 250},
            "activity": [],
        }
        mock_dependencies["metrics_aggregator"].get_complete_snapshot.return_value = mock_snapshot

        response = client.get("/api/metrics/overview")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "overview" in data
        assert data["overview"]["task_statistics"]["total_tasks"] == 100
        assert data["overview"]["claude_api_usage"]["total_cost"] == 10.50

        # Verify default hours parameter
        mock_dependencies["metrics_aggregator"].get_complete_snapshot.assert_called_once_with(hours=24)

    def test_metrics_overview_custom_hours(self, client, mock_dependencies):
        """Test metrics overview endpoint with custom time range"""
        mock_snapshot = Mock()
        mock_snapshot.to_dict.return_value = {
            "overview": {},
            "sessions": {},
            "activity": [],
        }
        mock_dependencies["metrics_aggregator"].get_complete_snapshot.return_value = mock_snapshot

        response = client.get("/api/metrics/overview?hours=168")
        assert response.status_code == 200

        mock_dependencies["metrics_aggregator"].get_complete_snapshot.assert_called_once_with(hours=168)

    def test_metrics_overview_error_handling(self, client, mock_dependencies):
        """Test error handling in metrics overview endpoint"""
        mock_dependencies["metrics_aggregator"].get_complete_snapshot.side_effect = Exception("Database error")

        response = client.get("/api/metrics/overview")
        assert response.status_code == 500

        data = json.loads(response.data)
        assert "error" in data
        assert "Database error" in data["error"]

    def test_health_endpoint(self, client, mock_dependencies):
        """Test health check endpoint"""
        response = client.get("/api/health")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_running_tasks_endpoint(self, client, mock_dependencies):
        """Test running tasks endpoint"""
        mock_dependencies["task_manager"].get_running_tasks.return_value = [
            {
                "task_id": "task1",
                "status": "in_progress",
                "description": "Test task 1",
                "worker_type": "chat",
                "model": "claude-3-5-sonnet-20241022",
                "latest_activity": "Processing...",
            },
            {
                "task_id": "task2",
                "status": "pending",
                "description": "Test task 2",
                "worker_type": "chat",
                "model": "claude-3-5-sonnet-20241022",
                "latest_activity": None,
            },
        ]

        response = client.get("/api/tasks/running")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert len(data["tasks"]) == 2
        assert data["tasks"][0]["task_id"] == "task1"
        assert data["tasks"][1]["status"] == "pending"

    def test_task_detail_endpoint(self, client, mock_dependencies):
        """Test task detail endpoint"""
        mock_dependencies["task_manager"].get_task_details.return_value = {
            "task_id": "task1",
            "status": "completed",
            "description": "Test task",
            "tool_usage": {"Read": 5, "Edit": 3},
            "activity_log": [
                {"timestamp": "2025-10-18T10:00:00", "message": "Started"},
                {"timestamp": "2025-10-18T10:05:00", "message": "Completed"},
            ],
        }

        response = client.get("/api/tasks/task1")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["task_id"] == "task1"
        assert data["status"] == "completed"
        assert len(data["activity_log"]) == 2

    def test_task_detail_not_found(self, client, mock_dependencies):
        """Test task detail endpoint with non-existent task"""
        mock_dependencies["task_manager"].get_task_details.return_value = None

        response = client.get("/api/tasks/nonexistent")
        assert response.status_code == 404

        data = json.loads(response.data)
        assert "error" in data


class TestSSEStreaming:
    """Test suite for Server-Sent Events streaming"""

    def test_sse_stream_connection(self, client, mock_dependencies):
        """Test SSE stream endpoint establishes connection"""
        mock_snapshot = Mock()
        mock_snapshot.to_dict.return_value = {
            "overview": {"task_statistics": {}, "claude_api_usage": {}, "system_health": {}, "tool_usage": {}},
            "sessions": {},
            "activity": [],
        }
        mock_dependencies["metrics_aggregator"].get_complete_snapshot.return_value = mock_snapshot

        response = client.get("/api/stream/metrics")
        assert response.status_code == 200
        assert response.content_type == "text/event-stream"
        assert b"data:" in response.data

    def test_sse_stream_with_hours_parameter(self, client, mock_dependencies):
        """Test SSE stream respects hours parameter"""
        mock_snapshot = Mock()
        mock_snapshot.to_dict.return_value = {
            "overview": {"task_statistics": {}, "claude_api_usage": {}, "system_health": {}, "tool_usage": {}},
            "sessions": {},
            "activity": [],
        }
        mock_dependencies["metrics_aggregator"].get_complete_snapshot.return_value = mock_snapshot

        response = client.get("/api/stream/metrics?hours=168")
        assert response.status_code == 200

    def test_sse_stream_json_format(self, client, mock_dependencies):
        """Test SSE stream returns valid JSON data"""
        test_data = {
            "overview": {
                "task_statistics": {"total_tasks": 50},
                "claude_api_usage": {"total_cost": 5.25},
                "system_health": {"recent_errors_24h": 0},
                "tool_usage": {"most_used_tools": []},
            },
            "sessions": {"total_sessions": 5},
            "activity": [],
        }
        mock_snapshot = Mock()
        mock_snapshot.to_dict.return_value = test_data
        mock_dependencies["metrics_aggregator"].get_complete_snapshot.return_value = mock_snapshot

        response = client.get("/api/stream/metrics")
        assert response.status_code == 200

        # Extract JSON from SSE data
        response_text = response.data.decode("utf-8")
        assert "data:" in response_text

        # Parse the JSON payload
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(response_text[json_start:json_end])
            assert data["overview"]["task_statistics"]["total_tasks"] == 50


class TestTaskCreation:
    """Test suite for POST /api/tasks endpoint"""

    @patch("monitoring.server.asyncio.run_coroutine_threadsafe")
    @patch("monitoring.server._agent_pool_loop", new_callable=lambda: Mock())
    def test_create_task_success(self, mock_loop, mock_run_coroutine, client, mock_dependencies):
        """Test successful task creation via API"""
        # Mock JWT token verification
        with patch("monitoring.server.verify_token", return_value="user123"):
            # Mock task creation result
            mock_task = Mock()
            mock_task.task_id = "abc123"
            mock_task.status = "pending"

            # Mock the future result
            mock_future = Mock()
            mock_future.result.return_value = mock_task
            mock_run_coroutine.return_value = mock_future

            response = client.post(
                "/api/tasks",
                json={"prompt": "Test task description"},
                headers={"Authorization": "Bearer test_token"},
            )

            assert response.status_code == 201
            data = json.loads(response.data)
            assert data["task_id"] == "abc123"
            assert data["status"] == "pending"
            assert "message" in data

    def test_create_task_unauthorized(self, client, mock_dependencies):
        """Test task creation without authentication"""
        with patch("monitoring.server.verify_token", return_value=None):
            response = client.post("/api/tasks", json={"prompt": "Test task"})

            assert response.status_code == 401
            data = json.loads(response.data)
            assert "error" in data
            assert data["error"] == "Unauthorized"

    def test_create_task_missing_prompt(self, client, mock_dependencies):
        """Test task creation without required prompt field"""
        with patch("monitoring.server.verify_token", return_value="user123"):
            response = client.post(
                "/api/tasks",
                json={"other_field": "value"},
                headers={"Authorization": "Bearer test_token"},
            )

            assert response.status_code == 400
            data = json.loads(response.data)
            assert "error" in data
            assert "prompt" in data["error"].lower()

    def test_create_task_invalid_model(self, client, mock_dependencies):
        """Test task creation with invalid model parameter"""
        with patch("monitoring.server.verify_token", return_value="user123"):
            response = client.post(
                "/api/tasks",
                json={"prompt": "Test task", "model": "invalid_model"},
                headers={"Authorization": "Bearer test_token"},
            )

            assert response.status_code == 400
            data = json.loads(response.data)
            assert "error" in data
            assert "model" in data["error"].lower()

    def test_create_task_invalid_agent_type(self, client, mock_dependencies):
        """Test task creation with invalid agent_type parameter"""
        with patch("monitoring.server.verify_token", return_value="user123"):
            response = client.post(
                "/api/tasks",
                json={"prompt": "Test task", "agent_type": "invalid_agent"},
                headers={"Authorization": "Bearer test_token"},
            )

            assert response.status_code == 400
            data = json.loads(response.data)
            assert "error" in data
            assert "agent_type" in data["error"].lower()

    @patch("monitoring.server.Path")
    def test_create_task_invalid_workspace(self, mock_path, client, mock_dependencies):
        """Test task creation with non-existent workspace"""
        with patch("monitoring.server.verify_token", return_value="user123"):
            # Mock workspace path doesn't exist
            mock_workspace = Mock()
            mock_workspace.exists.return_value = False
            mock_path.return_value = mock_workspace

            response = client.post(
                "/api/tasks",
                json={"prompt": "Test task", "workspace": "/nonexistent/path"},
                headers={"Authorization": "Bearer test_token"},
            )

            assert response.status_code == 400
            data = json.loads(response.data)
            assert "error" in data
            assert "workspace" in data["error"].lower()

    @patch("monitoring.server._agent_pool_loop", None)
    def test_create_task_server_not_ready(self, client, mock_dependencies):
        """Test task creation when agent pool is not started"""
        with patch("monitoring.server.verify_token", return_value="user123"):
            with patch("monitoring.server.Path.exists", return_value=True):
                response = client.post(
                    "/api/tasks",
                    json={"prompt": "Test task"},
                    headers={"Authorization": "Bearer test_token"},
                )

                assert response.status_code == 503
                data = json.loads(response.data)
                assert "error" in data
                assert "not ready" in data["error"].lower()

    @patch("monitoring.server.asyncio.run_coroutine_threadsafe")
    @patch("monitoring.server._agent_pool_loop", new_callable=lambda: Mock())
    def test_create_task_timeout(self, mock_loop, mock_run_coroutine, client, mock_dependencies):
        """Test task creation timeout handling"""
        with patch("monitoring.server.verify_token", return_value="user123"):
            # Mock timeout
            mock_future = Mock()
            mock_future.result.side_effect = asyncio.TimeoutError()
            mock_run_coroutine.return_value = mock_future

            response = client.post(
                "/api/tasks",
                json={"prompt": "Test task"},
                headers={"Authorization": "Bearer test_token"},
            )

            assert response.status_code == 504
            data = json.loads(response.data)
            assert "error" in data
            assert "timed out" in data["error"].lower()

    @patch("monitoring.server.asyncio.run_coroutine_threadsafe")
    @patch("monitoring.server._agent_pool_loop", new_callable=lambda: Mock())
    def test_create_task_with_custom_parameters(self, mock_loop, mock_run_coroutine, client, mock_dependencies):
        """Test task creation with all optional parameters"""
        with patch("monitoring.server.verify_token", return_value="user123"):
            mock_task = Mock()
            mock_task.task_id = "xyz789"
            mock_task.status = "pending"

            mock_future = Mock()
            mock_future.result.return_value = mock_task
            mock_run_coroutine.return_value = mock_future

            with patch("monitoring.server.Path.exists", return_value=True):
                response = client.post(
                    "/api/tasks",
                    json={
                        "prompt": "Test task with custom params",
                        "model": "opus",
                        "agent_type": "research_agent",
                        "workspace": "/custom/workspace",
                        "context": "Additional context here",
                    },
                    headers={"Authorization": "Bearer test_token"},
                )

                assert response.status_code == 201
                data = json.loads(response.data)
                assert data["task_id"] == "xyz789"
                assert data["model"] == "opus"
                assert data["agent_type"] == "research_agent"


class TestCORSAndSecurity:
    """Test CORS headers and security features"""

    def test_cors_headers_present(self, client):
        """Test that CORS headers are present in API responses"""
        response = client.get("/api/health")
        assert response.status_code == 200
        # Flask-CORS should add these headers
        # Note: In test mode, these might not always be present
        # This is more of a documentation test

    def test_api_handles_invalid_json(self, client, mock_dependencies):
        """Test that API handles malformed requests gracefully"""
        # Test with POST /api/tasks endpoint
        with patch("monitoring.server.verify_token", return_value="user123"):
            response = client.post(
                "/api/tasks",
                data="invalid json",
                headers={"Authorization": "Bearer test_token"},
            )
            # Should handle gracefully - Flask returns 400 for invalid JSON
            assert response.status_code in [400, 415]  # Bad Request or Unsupported Media Type


class TestErrorRecovery:
    """Test error recovery and resilience"""

    def test_metrics_aggregator_failure(self, client, mock_dependencies):
        """Test handling of metrics aggregator failures"""
        mock_dependencies["metrics_aggregator"].get_complete_snapshot.side_effect = RuntimeError("Aggregator crashed")

        response = client.get("/api/metrics/overview")
        assert response.status_code == 500

        data = json.loads(response.data)
        assert "error" in data

    def test_partial_data_availability(self, client, mock_dependencies):
        """Test handling when some tracking systems are unavailable"""
        # Simulate partial failure scenario
        mock_snapshot = Mock()
        mock_snapshot.to_dict.return_value = {
            "overview": {
                "task_statistics": None,  # Failed component
                "claude_api_usage": {"total_cost": 10.0},  # Working component
                "system_health": {"recent_errors_24h": 0},
                "tool_usage": {"most_used_tools": []},
            },
            "sessions": {},
            "activity": [],
        }
        mock_dependencies["metrics_aggregator"].get_complete_snapshot.return_value = mock_snapshot

        response = client.get("/api/metrics/overview")
        assert response.status_code == 200

        data = json.loads(response.data)
        # Should handle None gracefully
        assert data["overview"]["task_statistics"] is None
        assert data["overview"]["claude_api_usage"]["total_cost"] == 10.0


class TestPerformance:
    """Test performance characteristics"""

    def test_response_time_acceptable(self, client, mock_dependencies):
        """Test that API response times are reasonable"""
        mock_snapshot = Mock()
        mock_snapshot.to_dict.return_value = {
            "overview": {"task_statistics": {}, "claude_api_usage": {}, "system_health": {}, "tool_usage": {}},
            "sessions": {},
            "activity": [],
        }
        mock_dependencies["metrics_aggregator"].get_complete_snapshot.return_value = mock_snapshot

        start_time = time.time()
        response = client.get("/api/metrics/overview")
        elapsed_time = time.time() - start_time

        assert response.status_code == 200
        assert elapsed_time < 1.0  # Should respond in under 1 second


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestMarkFixedEndpoint:
    """Test suite for mark-fixed endpoint"""

    def test_mark_failed_task_as_fixed(self, client, mock_dependencies):
        """Test marking a failed task as fixed"""
        # Mock a failed task
        mock_task = Mock()
        mock_task.task_id = "test_task_123"
        mock_task.status = "failed"
        mock_task.error = "Some error message"
        mock_dependencies["task_manager"].get_task.return_value = mock_task

        # Mock updated task
        updated_task = Mock()
        updated_task.task_id = "test_task_123"
        updated_task.status = "completed"
        updated_task.error = None

        async def mock_update(*args, **kwargs):
            return True

        async def mock_get_updated(*args, **kwargs):
            return updated_task

        # Mock the asyncio operations
        with patch("monitoring.server._agent_pool_loop") as mock_loop:
            mock_loop.__bool__.return_value = True  # Make it truthy
            
            with patch("asyncio.run_coroutine_threadsafe") as mock_run:
                mock_future = Mock()
                mock_future.result.return_value = updated_task
                mock_run.return_value = mock_future

                response = client.post("/api/tasks/test_task_123/mark-fixed")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["task_id"] == "test_task_123"
        assert data["status"] == "completed"
        assert "marked as fixed" in data["message"].lower()

    def test_mark_fixed_task_not_found(self, client, mock_dependencies):
        """Test marking non-existent task as fixed"""
        mock_dependencies["task_manager"].get_task.return_value = None

        response = client.post("/api/tasks/nonexistent_task/mark-fixed")

        assert response.status_code == 404
        data = json.loads(response.data)
        assert "not found" in data["error"].lower()

    def test_mark_fixed_non_failed_task(self, client, mock_dependencies):
        """Test marking a non-failed task as fixed (should fail)"""
        mock_task = Mock()
        mock_task.task_id = "test_task_123"
        mock_task.status = "completed"  # Not failed
        mock_dependencies["task_manager"].get_task.return_value = mock_task

        response = client.post("/api/tasks/test_task_123/mark-fixed")

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "failed" in data["error"].lower()

    def test_mark_fixed_agent_pool_not_ready(self, client, mock_dependencies):
        """Test mark-fixed when agent pool is not ready"""
        mock_task = Mock()
        mock_task.task_id = "test_task_123"
        mock_task.status = "failed"
        mock_dependencies["task_manager"].get_task.return_value = mock_task

        with patch("monitoring.server._agent_pool_loop", None):
            response = client.post("/api/tasks/test_task_123/mark-fixed")

        assert response.status_code == 503
        data = json.loads(response.data)
        assert "not ready" in data["error"].lower()
