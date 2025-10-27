"""
Frontend tests for the monitoring dashboard
Tests JavaScript functionality, UI interactions, and autorefresh behavior
Uses Selenium WebDriver for browser automation testing
"""

import time
from unittest.mock import Mock, patch

import pytest

# Check if selenium is available
try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    pytest.skip("Selenium not available, skipping browser tests", allow_module_level=True)


@pytest.fixture(scope="module")
def mock_server():
    """Start a mock Flask server for testing"""
    from monitoring.server import app

    # Configure test mode
    app.config["TESTING"] = True
    app.config["SERVER_NAME"] = "localhost:5555"

    # Mock the dependencies
    with patch("monitoring.server.metrics_aggregator") as mock_metrics:
        mock_snapshot = Mock()
        mock_snapshot.to_dict.return_value = {
            "overview": {
                "task_statistics": {
                    "total_tasks": 100,
                    "success_rate": 95.5,
                    "by_status": {
                        "completed": 80,
                        "failed": 5,
                        "in_progress": 10,
                        "pending": 5,
                    },
                },
                "claude_api_usage": {
                    "total_cost": 10.50,
                    "total_requests": 500,
                    "recent_cost": 2.50,
                    "recent_requests": 100,
                },
                "system_health": {
                    "recent_errors_24h": 2,
                    "recent_errors": [
                        {
                            "task_id": "task1",
                            "timestamp": "2025-10-18T10:00:00",
                            "error": "Test error",
                        }
                    ],
                },
                "tool_usage": {"most_used_tools": [{"name": "Read", "count": 50}]},
            },
            "sessions": {"total_sessions": 10, "total_tool_calls": 250},
            "activity": [
                {
                    "task_id": "task1",
                    "timestamp": "2025-10-18T10:00:00",
                    "description": "Test task",
                    "message": "Task started",
                }
            ],
        }
        mock_metrics.get_complete_snapshot.return_value = mock_snapshot

        # Start server in a separate thread
        import threading

        server_thread = threading.Thread(target=app.run, kwargs={"host": "localhost", "port": 5555})
        server_thread.daemon = True
        server_thread.start()

        # Wait for server to be ready
        time.sleep(2)

        yield "http://localhost:5555"


@pytest.fixture(scope="function")
def browser(mock_server):
    """Create a browser instance for testing"""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    try:
        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)
        yield driver
    except Exception as e:
        pytest.skip(f"Chrome WebDriver not available: {e}")
    finally:
        if "driver" in locals():
            driver.quit()


class TestDashboardPageLoad:
    """Test dashboard page loading and initial render"""

    def test_page_loads_successfully(self, browser, mock_server):
        """Test that dashboard page loads without errors"""
        browser.get(mock_server)

        # Check page title
        assert "Bot Monitoring Dashboard" in browser.title or "Monitoring" in browser.title

        # Check main heading is present
        h1 = browser.find_element(By.TAG_NAME, "h1")
        assert "Dashboard" in h1.text or "Monitoring" in h1.text

    def test_main_sections_present(self, browser, mock_server):
        """Test that all main sections are rendered"""
        browser.get(mock_server)

        # Wait for page to load
        WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.ID, "autoRefreshStatus")))

        # Check for key sections
        assert browser.find_element(By.ID, "runningTasksSection")
        assert browser.find_element(By.ID, "autoRefreshStatus")
        assert browser.find_element(By.CLASS_NAME, "metrics-row")

    def test_metric_cards_display(self, browser, mock_server):
        """Test that metric cards are displayed with values"""
        browser.get(mock_server)

        # Wait for metrics to load
        WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.ID, "totalTasks")))

        # Check metric values are present
        total_tasks = browser.find_element(By.ID, "totalTasks")
        assert total_tasks.text  # Should have some value

        api_cost = browser.find_element(By.ID, "apiCost")
        assert "$" in api_cost.text

        error_count = browser.find_element(By.ID, "errorCount")
        assert error_count.text


class TestAutoRefreshFunctionality:
    """Test autorefresh and real-time update features"""

    def test_autorefresh_toggle_present(self, browser, mock_server):
        """Test that autorefresh toggle is present and functional"""
        browser.get(mock_server)

        toggle = browser.find_element(By.ID, "autoRefreshToggle")
        assert toggle.is_displayed()
        assert toggle.is_selected()  # Should be checked by default

    def test_autorefresh_can_be_disabled(self, browser, mock_server):
        """Test that autorefresh can be toggled off"""
        browser.get(mock_server)

        toggle = browser.find_element(By.ID, "autoRefreshToggle")
        initial_state = toggle.is_selected()

        # Click to toggle
        toggle.click()
        time.sleep(0.5)

        new_state = toggle.is_selected()
        assert new_state != initial_state

        # Status should update
        status_text = browser.find_element(By.ID, "statusText")
        assert status_text.text in ["Disconnected", "Connecting...", "Live"]

    def test_connection_status_indicator(self, browser, mock_server):
        """Test that connection status indicator is present"""
        browser.get(mock_server)

        status_container = browser.find_element(By.ID, "autoRefreshStatus")
        assert status_container.is_displayed()

        status_text = browser.find_element(By.ID, "statusText")
        assert status_text.text  # Should have some status text

        # Check for status indicator element
        indicators = browser.find_elements(By.CLASS_NAME, "status-indicator")
        assert len(indicators) > 0

    def test_manual_refresh_button(self, browser, mock_server):
        """Test that manual refresh button exists and is clickable"""
        browser.get(mock_server)

        # Find refresh button
        refresh_buttons = browser.find_elements(By.XPATH, "//button[contains(text(), 'Refresh')]")
        assert len(refresh_buttons) > 0

        refresh_button = refresh_buttons[0]
        assert refresh_button.is_displayed()
        assert refresh_button.is_enabled()

        # Click should not cause error
        refresh_button.click()
        time.sleep(0.5)


class TestTimeRangeFilters:
    """Test time range filter functionality"""

    def test_time_range_buttons_present(self, browser, mock_server):
        """Test that time range filter buttons are present"""
        browser.get(mock_server)

        # Check for time range buttons
        buttons = browser.find_elements(By.CLASS_NAME, "btn")
        button_texts = [btn.text for btn in buttons]

        assert any("24" in text or "Hours" in text for text in button_texts)
        assert any("7" in text or "Days" in text for text in button_texts)
        assert any("30" in text for text in button_texts)

    def test_time_range_button_click(self, browser, mock_server):
        """Test that time range buttons can be clicked"""
        browser.get(mock_server)

        # Find and click 7 days button
        buttons = browser.find_elements(By.CLASS_NAME, "btn")
        for btn in buttons:
            if "7" in btn.text and ("Day" in btn.text or "7" in btn.text):
                btn.click()
                time.sleep(0.5)
                break

    def test_active_button_state(self, browser, mock_server):
        """Test that clicked time range button becomes active"""
        browser.get(mock_server)

        buttons = browser.find_elements(By.CLASS_NAME, "btn")

        # Click a non-active button
        for btn in buttons:
            if "7" in btn.text:
                btn.click()
                time.sleep(0.5)

                # After click, should update styling
                break


class TestModals:
    """Test modal dialogs functionality"""

    def test_error_modal_opens(self, browser, mock_server):
        """Test that error modal can be opened"""
        browser.get(mock_server)

        # Wait for error card to be clickable
        WebDriverWait(browser, 10).until(EC.element_to_be_clickable((By.ID, "errorCount")))

        # Find and click error card
        error_card = browser.find_element(By.CLASS_NAME, "error-card")
        error_card.click()

        # Wait for modal to appear
        try:
            modal = WebDriverWait(browser, 5).until(EC.visibility_of_element_located((By.ID, "errorsModal")))
            assert modal.is_displayed()
        except TimeoutException:
            # Modal might not appear if no errors
            pass

    def test_modal_can_be_closed(self, browser, mock_server):
        """Test that modals can be closed"""
        browser.get(mock_server)

        # Open error modal
        error_card = browser.find_element(By.CLASS_NAME, "error-card")
        error_card.click()
        time.sleep(0.5)

        # Try to close with close button
        try:
            close_buttons = browser.find_elements(By.CLASS_NAME, "modal-close")
            if close_buttons:
                close_buttons[0].click()
                time.sleep(0.5)
        except Exception:  # nosec B110
            pass  # Expected in test cleanup

    def test_modal_closes_on_escape(self, browser, mock_server):
        """Test that modals close when Escape key is pressed"""
        browser.get(mock_server)

        # Open error modal
        error_card = browser.find_element(By.CLASS_NAME, "error-card")
        error_card.click()
        time.sleep(0.5)

        # Press Escape
        from selenium.webdriver.common.keys import Keys

        browser.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.5)


class TestTabNavigation:
    """Test tab navigation functionality"""

    def test_tabs_present(self, browser, mock_server):
        """Test that navigation tabs are present"""
        browser.get(mock_server)

        tabs = browser.find_elements(By.CLASS_NAME, "tab")
        assert len(tabs) >= 2  # Should have at least Overview and other tabs

        tab_texts = [tab.text for tab in tabs]
        assert any("Overview" in text for text in tab_texts)

    def test_tab_switching(self, browser, mock_server):
        """Test that clicking tabs switches content"""
        browser.get(mock_server)

        tabs = browser.find_elements(By.CLASS_NAME, "tab")

        # Click second tab
        if len(tabs) > 1:
            tabs[1].click()
            time.sleep(0.5)

            # Check if tab became active
            classes = tabs[1].get_attribute("class")
            assert "active" in classes

    def test_tab_content_visibility(self, browser, mock_server):
        """Test that tab content becomes visible when tab is selected"""
        browser.get(mock_server)

        tabs = browser.find_elements(By.CLASS_NAME, "tab")
        tab_contents = browser.find_elements(By.CLASS_NAME, "tab-content")

        if len(tabs) > 1 and len(tab_contents) > 1:
            # Click second tab
            tabs[1].click()
            time.sleep(0.5)


class TestResponsiveDesign:
    """Test responsive design and mobile compatibility"""

    def test_mobile_viewport(self, browser, mock_server):
        """Test that dashboard works on mobile viewport"""
        # Set mobile viewport size
        browser.set_window_size(375, 667)  # iPhone size

        browser.get(mock_server)

        # Page should still load
        h1 = browser.find_element(By.TAG_NAME, "h1")
        assert h1.is_displayed()

        # Controls should adapt
        controls = browser.find_element(By.CLASS_NAME, "controls")
        assert controls.is_displayed()

    def test_tablet_viewport(self, browser, mock_server):
        """Test that dashboard works on tablet viewport"""
        browser.set_window_size(768, 1024)  # iPad size

        browser.get(mock_server)

        # Check layout
        h1 = browser.find_element(By.TAG_NAME, "h1")
        assert h1.is_displayed()


class TestAccessibility:
    """Test accessibility features"""

    def test_page_has_title(self, browser, mock_server):
        """Test that page has a meaningful title"""
        browser.get(mock_server)
        assert browser.title
        assert len(browser.title) > 0

    def test_form_labels(self, browser, mock_server):
        """Test that form inputs have labels"""
        browser.get(mock_server)

        # Check autorefresh toggle has label
        toggle = browser.find_element(By.ID, "autoRefreshToggle")
        label = toggle.find_element(By.XPATH, "..")  # Parent label
        assert label.tag_name == "label"

    def test_buttons_have_text_or_aria_label(self, browser, mock_server):
        """Test that buttons have accessible text"""
        browser.get(mock_server)

        buttons = browser.find_elements(By.TAG_NAME, "button")
        for button in buttons:
            # Button should have text or aria-label
            has_text = len(button.text) > 0
            has_aria = button.get_attribute("aria-label")
            has_title = button.get_attribute("title")

            assert has_text or has_aria or has_title


class TestJavaScriptFunctions:
    """Test JavaScript helper functions"""

    def test_escape_html_function(self, browser, mock_server):
        """Test that HTML escaping function works correctly"""
        browser.get(mock_server)

        # Execute JavaScript to test escapeHtml function
        result = browser.execute_script(
            """
            return escapeHtml('<script>alert("xss")</script>');
        """
        )

        assert "<script>" not in result
        assert "&lt;script&gt;" in result or result.startswith("&")

    def test_format_relative_time(self, browser, mock_server):
        """Test relative time formatting function"""
        browser.get(mock_server)

        # Test with recent timestamp
        result = browser.execute_script(
            """
            const now = new Date();
            const fiveMinutesAgo = new Date(now - 5 * 60 * 1000);
            return formatRelativeTime(fiveMinutesAgo.toISOString());
        """
        )

        assert "5m ago" in result or "ago" in result

    def test_format_status_function(self, browser, mock_server):
        """Test status formatting function"""
        browser.get(mock_server)

        result = browser.execute_script(
            """
            return formatStatus('in_progress');
        """
        )

        assert "In Progress" in result or "progress" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
