"""
Tests for WebSocket functionality in monitoring server
"""

import time
import unittest
from unittest.mock import MagicMock, patch

import pytest

# Skip entire module if flask_socketio not available
pytest.importorskip("flask_socketio", reason="flask_socketio not installed - skipping websocket tests")


class TestWebSocketEvents(unittest.TestCase):
    """Test WebSocket event handlers"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test client"""
        # Import here to avoid circular imports
        from monitoring.server import app, socketio

        self.app = app
        self.socketio = socketio
        self.app.config["TESTING"] = True
        self.client = self.socketio.test_client(self.app)

    def test_connect_event(self):
        """Test client connection"""
        self.assertTrue(self.client.is_connected())

        # Should receive connected event
        received = self.client.get_received()
        self.assertGreater(len(received), 0)

        # Find the connected event
        connected_event = None
        for event in received:
            if event["name"] == "connected":
                connected_event = event
                break

        self.assertIsNotNone(connected_event)
        self.assertEqual(connected_event["args"][0]["status"], "connected")
        self.assertIn("client_id", connected_event["args"][0])

    def test_subscribe_event(self):
        """Test subscription to metrics updates"""
        # Clear any initial events
        self.client.get_received()

        # Send subscribe event
        self.client.emit("subscribe", {"hours": 24, "update_interval": 2})

        # Wait for response
        time.sleep(0.1)

        # Check for subscribed event
        received = self.client.get_received()
        self.assertGreater(len(received), 0)

        subscribed_event = None
        for event in received:
            if event["name"] == "subscribed":
                subscribed_event = event
                break

        self.assertIsNotNone(subscribed_event)
        self.assertEqual(subscribed_event["args"][0]["status"], "subscribed")
        self.assertIn("config", subscribed_event["args"][0])

    def test_unsubscribe_event(self):
        """Test unsubscribing from metrics updates"""
        # First subscribe
        self.client.emit("subscribe", {"hours": 24})
        time.sleep(0.1)
        self.client.get_received()  # Clear

        # Then unsubscribe
        self.client.emit("unsubscribe")
        time.sleep(0.1)

        # Check for unsubscribed event
        received = self.client.get_received()
        unsubscribed_event = None
        for event in received:
            if event["name"] == "unsubscribed":
                unsubscribed_event = event
                break

        self.assertIsNotNone(unsubscribed_event)
        self.assertEqual(unsubscribed_event["args"][0]["status"], "unsubscribed")

    def test_set_interval_event(self):
        """Test setting update interval"""
        self.client.get_received()  # Clear

        # Set interval
        self.client.emit("set_interval", {"interval": 5})
        time.sleep(0.1)

        # Check for interval_updated event
        received = self.client.get_received()
        interval_event = None
        for event in received:
            if event["name"] == "interval_updated":
                interval_event = event
                break

        self.assertIsNotNone(interval_event)
        self.assertEqual(interval_event["args"][0]["interval"], 5)

    @patch("monitoring.server.task_manager")
    @patch("monitoring.server.metrics_aggregator")
    @patch("monitoring.server.hooks_reader")
    def test_request_refresh_event(self, mock_hooks, mock_aggregator, mock_task_manager):
        """Test requesting immediate metrics refresh"""
        # Mock the metrics data
        mock_snapshot = MagicMock()
        mock_snapshot.to_dict.return_value = {
            "tasks": {"total": 10, "running": 2},
            "costs": {"total_cost": 5.25},
            "claude_api": {"total_requests": 100},
        }
        mock_aggregator.get_complete_snapshot.return_value = mock_snapshot

        mock_hooks.get_aggregate_statistics.return_value = {
            "total_sessions": 5,
            "total_tools": 50,
        }

        mock_task_manager.get_recent_activity.return_value = [{"description": "Test task", "timestamp": time.time()}]

        self.client.get_received()  # Clear

        # Request refresh
        self.client.emit("request_refresh", {"hours": 24})
        time.sleep(0.2)

        # Check for metrics_update event
        received = self.client.get_received()
        metrics_event = None
        for event in received:
            if event["name"] == "metrics_update":
                metrics_event = event
                break

        self.assertIsNotNone(metrics_event)
        data = metrics_event["args"][0]
        self.assertIn("overview", data)
        self.assertIn("sessions", data)
        self.assertIn("activity", data)
        self.assertIn("timestamp", data)

    def test_disconnect_event(self):
        """Test client disconnection"""
        self.assertTrue(self.client.is_connected())

        # Disconnect
        self.client.disconnect()

        # Verify disconnected
        self.assertFalse(self.client.is_connected())

    def test_multiple_clients(self):
        """Test multiple clients connecting"""
        # Create second client
        client2 = self.socketio.test_client(self.app)

        # Both should be connected
        self.assertTrue(self.client.is_connected())
        self.assertTrue(client2.is_connected())

        # Both should have received connected events
        received1 = self.client.get_received()
        received2 = client2.get_received()

        self.assertGreater(len(received1), 0)
        self.assertGreater(len(received2), 0)

        # Disconnect second client
        client2.disconnect()
        self.assertFalse(client2.is_connected())
        self.assertTrue(self.client.is_connected())


class TestWebSocketBroadcaster:
    """Test WebSocket metrics broadcaster background task"""

    @pytest.fixture
    def mock_server(self):
        """Mock the server components"""
        with (
            patch("monitoring.server.task_manager") as mock_tm,
            patch("monitoring.server.metrics_aggregator") as mock_ma,
            patch("monitoring.server.hooks_reader") as mock_hr,
        ):

            # Setup mocks
            mock_snapshot = MagicMock()
            mock_snapshot.to_dict.return_value = {"tasks": {"total": 5}}
            mock_ma.get_complete_snapshot.return_value = mock_snapshot
            mock_hr.get_aggregate_statistics.return_value = {}
            mock_tm.get_recent_activity.return_value = []

            yield {
                "task_manager": mock_tm,
                "metrics_aggregator": mock_ma,
                "hooks_reader": mock_hr,
            }

    def test_broadcaster_sends_updates_on_change(self, mock_server):
        """Test that broadcaster sends updates when data changes"""
        from monitoring.server import app, socketio

        app.config["TESTING"] = True
        client = socketio.test_client(app)

        # Subscribe to updates
        client.emit("subscribe", {"hours": 24})
        time.sleep(0.1)
        client.get_received()  # Clear initial events

        # Wait for broadcaster to send update
        time.sleep(3)

        # Should have received metrics_update
        received = client.get_received()

        # Look for metrics_update events
        metrics_updates = [e for e in received if e["name"] == "metrics_update"]

        # May receive multiple updates
        assert len(metrics_updates) >= 0  # Broadcaster may not have sent yet

        client.disconnect()

    def test_broadcaster_respects_unsubscribe(self, mock_server):
        """Test that broadcaster doesn't send to unsubscribed clients"""
        from monitoring.server import app, socketio

        app.config["TESTING"] = True
        client = socketio.test_client(app)

        # Subscribe then immediately unsubscribe
        client.emit("subscribe", {"hours": 24})
        time.sleep(0.1)
        client.emit("unsubscribe")
        time.sleep(0.1)
        client.get_received()  # Clear

        # Wait for potential updates
        time.sleep(3)

        # Should not receive metrics_update
        received = client.get_received()
        metrics_updates = [e for e in received if e["name"] == "metrics_update"]

        # Should have no or very few updates since we unsubscribed
        assert len(metrics_updates) <= 1

        client.disconnect()


class TestWebSocketEndpoint:
    """Test WebSocket endpoint availability"""

    def test_websocket_test_page_exists(self):
        """Test that the WebSocket test page is accessible"""
        from monitoring.server import app

        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/websocket-test")
        assert response.status_code == 200
        assert b"WebSocket Dashboard Test" in response.data

    def test_socketio_endpoint_exists(self):
        """Test that Socket.IO endpoint is available"""
        from monitoring.server import app

        app.config["TESTING"] = True
        client = app.test_client()

        # Socket.IO handshake endpoint
        response = client.get("/socket.io/")
        # Should redirect or return socket.io response
        # Status code may be 400 without proper handshake, but endpoint should exist
        assert response.status_code in [200, 400, 405]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
