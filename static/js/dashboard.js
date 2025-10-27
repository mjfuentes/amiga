// Import configuration constants
import {
    TASK_LIMIT,
    TOOL_CALLS_LIMIT,
    ACTIVITY_ITEMS_LIMIT,
    TRUNCATE_LENGTH,
    SHORT_TRUNCATE_LENGTH,
    MAX_RECONNECT_ATTEMPTS,
    INITIAL_RECONNECT_DELAY,
    MAX_SILENCE_TIME,
    CONNECTION_MONITOR_INTERVAL,
    DEFAULT_THEME
} from './config.js';

// Global state
let currentTimeRange = 24;
let eventSource = null;
let autoRefreshEnabled = true;
let currentData = null;
let currentTaskId = null;
let currentTaskStatus = null;
let reconnectAttempts = 0;
let maxReconnectAttempts = MAX_RECONNECT_ATTEMPTS;
let reconnectDelay = INITIAL_RECONNECT_DELAY;
let lastUpdateTime = null;
let connectionStateChangeCallbacks = [];
let currentUnifiedFilter = 'active'; // 'active', 'completed', or 'all'
let currentPage = 1;
let pageSize = TASK_LIMIT;
let totalPages = 1;
let preventAutoRefetch = false; // Prevent SSE from refetching tasks
let allDocs = [];
let currentDocsFilter = 'active';
let docsPage = 1;
let docsPageSize = 8;

// Throttle state for auto-refresh
let lastFetchTime = 0;
let fetchThrottleMs = 2000; // Minimum 2 seconds between fetches

// Tool auto-scroll state
let autoScrollEnabled = true;

// SocketIO connection for real-time tool updates
let socket = null;

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    // Always use dark theme
    document.documentElement.setAttribute('data-theme', 'dark');

    // Initial load
    fetchUnifiedData();
    loadDocumentation();

    startRealtimeUpdates();
    startConnectionMonitor();
    initializeSocketIO();

    // Setup keyboard navigation for filter buttons
    setupFilterKeyboardNavigation();
    setupDocumentationFilterKeyboardNavigation();
});

// Setup keyboard navigation for filter buttons
function setupFilterKeyboardNavigation() {
    const filterButtons = document.querySelectorAll('#tasksSessionsSection .filter-btn');

    filterButtons.forEach((button, index) => {
        button.addEventListener('keydown', (e) => {
            // Arrow key navigation
            if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                e.preventDefault();
                const direction = e.key === 'ArrowRight' ? 1 : -1;
                const nextIndex = (index + direction + filterButtons.length) % filterButtons.length;
                filterButtons[nextIndex].focus();
            }
            // Home/End keys
            else if (e.key === 'Home') {
                e.preventDefault();
                filterButtons[0].focus();
            }
            else if (e.key === 'End') {
                e.preventDefault();
                filterButtons[filterButtons.length - 1].focus();
            }
        });
    });
}

// Setup keyboard navigation for documentation filter buttons
function setupDocumentationFilterKeyboardNavigation() {
    const filterButtons = document.querySelectorAll('#documentationSection .filter-btn');

    filterButtons.forEach((button, index) => {
        button.addEventListener('keydown', (e) => {
            // Arrow key navigation
            if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                e.preventDefault();
                const direction = e.key === 'ArrowRight' ? 1 : -1;
                const nextIndex = (index + direction + filterButtons.length) % filterButtons.length;
                filterButtons[nextIndex].focus();
            }
            // Home/End keys
            else if (e.key === 'Home') {
                e.preventDefault();
                filterButtons[0].focus();
            }
            else if (e.key === 'End') {
                e.preventDefault();
                filterButtons[filterButtons.length - 1].focus();
            }
        });
    });
}

// Toast notification system for errors and messages
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 2rem;
        right: 2rem;
        background: var(--bg-secondary);
        border: 1.5px solid var(--border-color);
        border-radius: 0.5rem;
        padding: 1rem 1.5rem;
        box-shadow: 0 4px 12px var(--shadow-medium);
        z-index: 10000;
        animation: slideIn 0.3s ease;
        max-width: 300px;
    `;

    if (type === 'error') {
        toast.style.borderColor = 'var(--accent-red)';
        toast.style.color = 'var(--accent-red)';
    } else if (type === 'success') {
        toast.style.borderColor = 'var(--accent-green)';
        toast.style.color = 'var(--accent-green)';
    }

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Enhanced API error handling
async function fetchWithErrorHandling(url, options = {}) {
    try {
        const response = await fetch(url, options);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    } catch (error) {
        console.error(`API Error (${url}):`, error);
        showToast(`Failed to fetch data: ${error.message}`, 'error');
        throw error;
    }
}

function setTimeRange(hours) {
    currentTimeRange = hours;
    document.querySelectorAll('.controls .btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    stopRealtimeUpdates();
    startRealtimeUpdates();
}

function startRealtimeUpdates() {
    if (!autoRefreshEnabled) return;

    if (eventSource) {
        eventSource.close();
    }

    updateStatus('Connecting...', true);

    try {
        eventSource = new EventSource(`/api/stream/metrics?hours=${currentTimeRange}`);

        eventSource.onopen = () => {
            console.log('SSE connection established');
            reconnectAttempts = 0;
            reconnectDelay = INITIAL_RECONNECT_DELAY;
            updateStatus('Live', false);
            notifyConnectionStateChange('connected');
        };

        eventSource.onmessage = (event) => {
            try {
                // Skip empty or heartbeat messages
                if (!event.data || event.data.trim() === '') {
                    return;
                }

                // Log raw data for debugging if parse fails
                const data = JSON.parse(event.data);
                currentData = data;
                lastUpdateTime = Date.now();
                renderDashboard(data);
                updateStatus('Live', false);
            } catch (error) {
                console.error('Error parsing SSE data:', error);
                console.error('Raw event data:', event.data); // Add debugging
                updateStatus('Error parsing data', false);
                showToast('Error parsing server data', 'error');
            }
        };

        // Add explicit error event handler for SSE error events
        eventSource.addEventListener('error', (event) => {
            console.warn('Server error event:', event.data);
            try {
                const errorData = JSON.parse(event.data);
                showToast(`Server error: ${errorData.error}`, 'error');
            } catch (e) {
                showToast('Server error occurred', 'error');
            }
        });

        eventSource.onerror = (error) => {
            console.error('SSE connection error:', error);

            if (eventSource.readyState === EventSource.CLOSED) {
                handleReconnection();
            }
        };
    } catch (error) {
        console.error('Failed to create EventSource:', error);
        showToast('Failed to connect to server', 'error');
        handleReconnection();
    }
}

function handleReconnection() {
    if (!autoRefreshEnabled) return;

    reconnectAttempts++;

    if (reconnectAttempts >= maxReconnectAttempts) {
        updateStatus(`Connection failed (${reconnectAttempts} attempts)`, false);
        notifyConnectionStateChange('failed');
        showToast('Connection failed after multiple attempts', 'error');
        return;
    }

    // Exponential backoff with jitter
    const jitter = Math.random() * 1000;
    const delay = Math.min(reconnectDelay * Math.pow(1.5, reconnectAttempts - 1) + jitter, 30000);

    updateStatus(`Reconnecting... (attempt ${reconnectAttempts}/${maxReconnectAttempts})`, true);
    notifyConnectionStateChange('reconnecting');

    setTimeout(() => {
        startRealtimeUpdates();
    }, delay);
}

function startConnectionMonitor() {
    // Monitor connection health by checking last update time
    setInterval(() => {
        if (!autoRefreshEnabled || !lastUpdateTime) return;

        const timeSinceLastUpdate = Date.now() - lastUpdateTime;

        if (timeSinceLastUpdate > MAX_SILENCE_TIME && eventSource?.readyState === EventSource.OPEN) {
            console.warn('Connection appears stale, reconnecting...');
            stopRealtimeUpdates();
            startRealtimeUpdates();
        }
    }, CONNECTION_MONITOR_INTERVAL);
}

function initializeSocketIO() {
    // Initialize SocketIO for real-time tool execution updates
    // Note: No authentication needed for dashboard (monitoring only)
    if (typeof io === 'undefined') {
        console.warn('Socket.IO library not loaded - real-time tool updates disabled');
        return;
    }

    socket = io({
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionAttempts: 10
    });

    socket.on('connect', () => {
        console.log('SocketIO connected for real-time updates');
    });

    socket.on('disconnect', () => {
        console.log('SocketIO disconnected');
    });

    socket.on('tool_execution', (data) => {
        handleToolExecutionUpdate(data);
    });

    socket.on('task_stopped', (data) => {
        console.log('Task stopped event received:', data);
        
        // Update current task status if this is the task we're viewing
        if (data.task_id === currentTaskId) {
            currentTaskStatus = 'stopped';
            
            // Hide stop button
            const stopBtn = document.getElementById('stopTaskBtn');
            if (stopBtn) {
                stopBtn.style.display = 'none';
            }
            
            // Add stop message to tool execution log
            appendToolExecutionToModal({
                tool_name: 'System',
                timestamp: data.timestamp || new Date().toISOString(),
                success: true,
                output_preview: JSON.stringify({
                    message: data.message || 'Task stopped by user'
                }),
                status: 'completed'
            });
            
            // Show toast notification
            showToast('Task stopped', 'info');
        }
        
        // Refresh task list to update status
        fetchUnifiedData();
    });

    socket.on('connect_error', (error) => {
        console.error('SocketIO connection error:', error);
    });
}

function handleToolExecutionUpdate(data) {
    // Only update if we're currently viewing this task's modal
    if (!currentTaskId || currentTaskId !== data.task_id) {
        return;
    }

    const modal = document.getElementById('taskModal');
    if (!modal.classList.contains('active')) {
        return;
    }

    // Add the new tool execution to the display
    appendToolExecutionToModal(data);

    // Re-render planning progress if TodoWrite tool
    if (data.tool_name === 'TodoWrite' && data.success) {
        // Refetch tool usage to get updated TodoWrite state
        refetchTaskToolUsage(data.task_id);
    }
}

function appendToolExecutionToModal(toolData) {
    const scrollContainer = document.getElementById('toolTimelineScroll');
    if (!scrollContainer) return;

    // Build tool call entry
    const toolCall = {
        tool: toolData.tool_name,
        timestamp: toolData.timestamp,
        has_error: !toolData.success,
        output_preview: toolData.error ? JSON.stringify({ error: toolData.error }) : toolData.output_preview,
        output_length: toolData.output_preview ? toolData.output_preview.length : 0,
        parameters: toolData.parameters || {},
        status: toolData.status || 'completed'
    };

    // Check if last call is identical (deduplication)
    const lastCallElement = scrollContainer.querySelector('.tool-call-entry:last-child');
    if (lastCallElement) {
        const lastToolAttr = lastCallElement.getAttribute('data-tool');
        const lastParamsAttr = lastCallElement.getAttribute('data-params');

        const currentParams = JSON.stringify(toolCall.parameters);

        // Skip if identical to previous
        if (lastToolAttr === toolCall.tool && lastParamsAttr === currentParams) {
            return;
        }
    }

    // Save scroll state
    const wasAtBottom = scrollContainer.scrollHeight - scrollContainer.scrollTop <= scrollContainer.clientHeight + 50;

    // Get current tool count
    const currentCalls = scrollContainer.querySelectorAll('.tool-call-entry').length;

    // Append new tool call
    const toolHtml = renderTerminalToolCall(toolCall, currentCalls + 1);
    scrollContainer.insertAdjacentHTML('beforeend', toolHtml);

    // Restore scroll behavior
    if (autoScrollEnabled || wasAtBottom) {
        scrollToBottom();
    }
}

async function refetchTaskToolUsage(taskId) {
    try {
        const toolUsageResponse = await fetch(`/api/tasks/${taskId}/tool-usage`);
        if (toolUsageResponse.ok) {
            const toolData = await toolUsageResponse.json();
            // Only re-render planning progress, don't replace entire tool list
            renderPlanningProgress(toolData.tool_calls);
        }
    } catch (error) {
        console.error('Error refetching tool usage:', error);
    }
}

function notifyConnectionStateChange(state) {
    connectionStateChangeCallbacks.forEach(callback => {
        try {
            callback(state);
        } catch (error) {
            console.error('Error in connection state callback:', error);
        }
    });
}

function onConnectionStateChange(callback) {
    connectionStateChangeCallbacks.push(callback);
}

function stopRealtimeUpdates() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    reconnectAttempts = 0;
    updateStatus('Disconnected', false);
    notifyConnectionStateChange('disconnected');
}

function toggleAutoRefresh() {
    // Auto-refresh is always enabled, this function is kept for compatibility
    return;
}

async function manualRefresh() {
    if (!autoRefreshEnabled) {
        // If auto-refresh is disabled, do a one-time fetch
        try {
            const data = await fetchWithErrorHandling(`/api/metrics/overview?hours=${currentTimeRange}`);
            currentData = data;
            renderDashboard(data);
            updateStatus('Updated', false);
        } catch (error) {
            updateStatus('Error', false);
        }
    } else {
        // Force reconnect if auto-refresh is enabled
        stopRealtimeUpdates();
        setTimeout(() => startRealtimeUpdates(), 100);
    }
}

function updateStatus(text, isUpdating, connectionState = null) {
    // Status updates are no longer displayed in the UI
    // This function is kept for compatibility
    console.debug(`Status: ${text}`, { isUpdating, connectionState });
}

function renderDashboard(data) {
    const overview = data.overview;
    const sessions = data.sessions;

    // Update unified badge
    updateUnifiedBadge(overview.task_statistics);

    // Update footer stats
    document.getElementById('errorCount').textContent = overview.system_health.recent_errors_24h;
    document.getElementById('totalTasks').textContent = overview.task_statistics.total_tasks.toLocaleString();
    document.getElementById('successRate').textContent = `${overview.task_statistics.success_rate.toFixed(1)}%`;
    // API cost/requests removed - elements don't exist in HTML footer
    document.getElementById('toolCalls').textContent = sessions.total_tool_calls.toLocaleString();
    document.getElementById('codeSessions').textContent = sessions.total_sessions;

    // Auto-refresh tasks/sessions list when SSE updates arrive (throttled)
    const now = Date.now();
    if (now - lastFetchTime >= fetchThrottleMs) {
        lastFetchTime = now;
        fetchUnifiedData();
    }
}

function updateUnifiedBadge(taskStats) {
    const badge = document.getElementById('tasksSessionsBadge');

    if (currentUnifiedFilter === 'active') {
        // Active = only running tasks
        badge.textContent = (taskStats.by_status.running || 0) + (taskStats.by_status.pending || 0);
    } else if (currentUnifiedFilter === 'completed') {
        badge.textContent = taskStats.by_status.completed || 0;
    } else if (currentUnifiedFilter === 'all') {
        badge.textContent = taskStats.total_tasks || 0;
    }
}

function setUnifiedFilter(filter) {
    currentUnifiedFilter = filter;
    currentPage = 1;

    // Update button states in tasks/sessions section
    document.querySelectorAll('#tasksSessionsSection .filter-btn').forEach(btn => {
        const isActive = btn.dataset.filter === filter;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-pressed', isActive.toString());
    });

    fetchUnifiedData();
}

function changePage(delta) {
    const newPage = currentPage + delta;
    if (newPage >= 1 && newPage <= totalPages) {
        currentPage = newPage;
        fetchUnifiedData();
    }
}

function updatePagination(total) {
    totalPages = Math.ceil(total / pageSize);

    const paginationDiv = document.getElementById('unifiedPagination');
    const paginationInfo = document.getElementById('paginationInfo');
    const buttons = paginationDiv.querySelectorAll('.pagination-btn');

    if (totalPages <= 1) {
        paginationDiv.style.display = 'none';
        return;
    }

    paginationDiv.style.display = 'flex';
    paginationInfo.textContent = `Page ${currentPage} of ${totalPages}`;

    // Update button states
    buttons[0].disabled = currentPage === 1; // Previous
    buttons[1].disabled = currentPage === totalPages; // Next
}

async function fetchUnifiedData() {
    let tasks = [];
    let sessions = [];
    let totalTasks = 0;
    let totalSessions = 0;

    // Fetch tasks based on filter
    let taskEndpoint;
    if (currentUnifiedFilter === 'active') {
        // Active = only running tasks
        taskEndpoint = `/api/tasks/running?active_only=true&page=${currentPage}&page_size=${pageSize}`;
    } else if (currentUnifiedFilter === 'completed') {
        taskEndpoint = `/api/tasks/completed?page=${currentPage}&page_size=${pageSize}`;
    } else if (currentUnifiedFilter === 'all') {
        taskEndpoint = `/api/tasks/all?page=${currentPage}&page_size=${pageSize}`;
    }

    // Fetch sessions based on filter
    let sessionEndpoint;
    if (currentUnifiedFilter === 'active') {
        // Active sessions: last activity within 5 minutes
        sessionEndpoint = `/api/metrics/cli-sessions?minutes=5&page=${currentPage}&page_size=${pageSize}`;
    } else if (currentUnifiedFilter === 'completed') {
        // Completed sessions: no activity for 30+ minutes, within last 24 hours
        sessionEndpoint = `/api/metrics/cli-sessions?hours=24&page=${currentPage}&page_size=${pageSize}`;
    } else if (currentUnifiedFilter === 'all') {
        // All sessions within last 7 days
        sessionEndpoint = `/api/metrics/cli-sessions?hours=168&page=${currentPage}&page_size=${pageSize}`;
    }

    try {
        // Fetch tasks
        const taskResponse = await fetch(taskEndpoint);
        if (taskResponse.ok) {
            const data = await taskResponse.json();
            tasks = data.tasks || [];
            totalTasks = data.total || 0;
        }
    } catch (error) {
        console.error('Error fetching tasks:', error);
    }

    try {
        // Fetch sessions
        const sessionResponse = await fetch(sessionEndpoint);
        if (sessionResponse.ok) {
            const data = await sessionResponse.json();
            let allSessions = data.sessions || [];

            // Filter sessions based on status if needed
            if (currentUnifiedFilter === 'completed') {
                // Only show completed sessions
                sessions = allSessions.filter(s => s.status === 'completed');
                // Count how many sessions match the filter
                const allSessionsTotal = data.total || 0;
                const completedCount = data.sessions.filter(s => s.status === 'completed').length;
                // Estimate total completed sessions (this is approximate)
                totalSessions = completedCount;
            } else {
                sessions = allSessions;
                totalSessions = data.total || 0;
            }
        }
    } catch (error) {
        console.error('Error fetching sessions:', error);
    }

    // Update pagination using total counts from backend
    const totalItems = totalTasks + totalSessions;
    updatePagination(totalItems);

    // Render with total counts for badge
    renderUnifiedGrid(tasks, sessions, totalTasks, totalSessions);
}

function renderUnifiedGrid(tasks, sessions = [], totalTasks = 0, totalSessions = 0) {
    const grid = document.getElementById('unifiedGrid');
    const badge = document.getElementById('tasksSessionsBadge');

    // Convert tasks and sessions to items with type tag
    const taskItems = tasks.map(t => ({ ...t, type: 'task', sort_time: t.updated_at }));
    const sessionItems = sessions.map(s => ({ ...s, type: 'session', sort_time: s.last_activity }));
    const items = [...taskItems, ...sessionItems];

    // Sort items: tasks by time (recent first), sessions by name (alphabetical)
    items.sort((a, b) => {
        // If both are tasks or both are sessions, sort within type
        if (a.type === 'task' && b.type === 'task') {
            // Tasks: sort by time (most recent first)
            const timeA = a.sort_time;
            const timeB = b.sort_time;
            if (!timeA && !timeB) return 0;
            if (!timeA) return 1;
            if (!timeB) return -1;
            return timeB.localeCompare(timeA);
        } else if (a.type === 'session' && b.type === 'session') {
            // Sessions: sort alphabetically by session_id
            return (a.session_id || '').localeCompare(b.session_id || '');
        } else {
            // Mixed: tasks first, then sessions
            return a.type === 'task' ? -1 : 1;
        }
    });

    // Update badge with TOTAL count from backend, not current page items
    const totalItems = totalTasks + totalSessions;
    badge.textContent = totalItems;
    badge.title = `${totalTasks} task${totalTasks !== 1 ? 's' : ''}, ${totalSessions} session${totalSessions !== 1 ? 's' : ''}`;

    if (items.length === 0) {
        const filterLabel = currentUnifiedFilter === 'active' ? 'active' :
                           currentUnifiedFilter === 'completed' ? 'completed' : '';
        grid.innerHTML = `<div class="empty-state">No ${filterLabel} tasks or sessions</div>`;
        return;
    }

    grid.innerHTML = items.map(item => {
        if (item.type === 'task') {
            return renderTaskCard(item);
        } else {
            return renderSessionCard(item);
        }
    }).join('');
}

function renderTaskCard(task) {
    // Show download button for completed tasks with output files
    const showDownloadBtn = task.status === 'completed' && task.has_output_file;

    // Format token usage if available
    const tokenInfo = formatTokenUsage(task.token_usage);

    return `<div class="task-card ${task.status}">
        <div class="task-card-clickable" onclick="showTaskDetail('${task.task_id}')">
            <div class="task-header">
                <div class="task-id">Task #${task.task_id}</div>
                <div class="task-status ${task.status}">${formatStatus(task.status)}</div>
            </div>
            <div class="task-description">${escapeHtml(task.description)}</div>
            <div class="task-meta">
                <div class="task-meta-item">
                    <span>🧠</span>
                    <span>${task.model}</span>
                </div>
                <div class="task-meta-item">
                    <span>📅</span>
                    <span>${formatRelativeTime(task.updated_at)}</span>
                </div>
                ${tokenInfo ? `
                <div class="task-meta-item task-meta-tokens">
                    <span>🎟️</span>
                    <span>${tokenInfo.display}</span>
                </div>
                ` : ''}
            </div>
            ${task.latest_activity ? `
                <div class="task-activity">
                    ${escapeHtml(task.latest_activity)}
                </div>
            ` : ''}
        </div>
        ${showDownloadBtn ? `
            <div class="task-actions">
                <button class="download-btn" onclick="event.stopPropagation(); downloadTaskOutput('${task.task_id}')" title="Download output file">
                    <span class="download-icon">⬇</span>
                    <span class="download-text">Download</span>
                </button>
            </div>
        ` : ''}
    </div>`;
}

function renderSessionCard(session) {
    const lastActivity = session.last_activity ? formatRelativeTime(session.last_activity) : 'Unknown';
    const startTime = session.start_time ? formatRelativeTime(session.start_time) : 'Unknown';
    const duration = session.duration_seconds ? formatDuration(session.duration_seconds) : '0s';
    const toolCount = session.tool_count || session.total_tools || 0;

    // Map session status to display class and label
    let statusClass = 'session';
    let statusLabel = 'Unknown';

    if (session.status === 'active') {
        statusClass = 'running';
        statusLabel = 'Active';
    } else if (session.status === 'idle') {
        statusClass = 'session';
        statusLabel = 'Idle';
    } else if (session.status === 'completed' || session.status === 'ended') {
        statusClass = 'completed';
        statusLabel = 'Completed';
    }

    return `<div class="task-card ${statusClass}">
        <div class="task-card-clickable" onclick="showSessionDetail('${session.session_id}')">
            <div class="task-header">
                <div class="task-id">CLI Session ${session.session_id.substring(0, 8)}...</div>
                <div class="task-status ${statusClass}">${statusLabel}</div>
            </div>
            <div class="task-description">Claude Code CLI Session</div>
            <div class="task-meta">
                <div class="task-meta-item">
                    <span>⏱️</span>
                    <span>${duration}</span>
                </div>
                <div class="task-meta-item">
                    <span>🔧</span>
                    <span>${toolCount} tools</span>
                </div>
                <div class="task-meta-item">
                    <span>📅</span>
                    <span>${lastActivity}</span>
                </div>
                ${session.errors > 0 ? `
                    <div class="task-meta-item">
                        <span>❌</span>
                        <span>${session.errors} errors</span>
                    </div>
                ` : ''}
            </div>
        </div>
    </div>`;
}

// Format duration in seconds to human-readable format
function formatDuration(seconds) {
    if (seconds < 60) {
        return `${seconds}s`;
    } else if (seconds < 3600) {
        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return secs > 0 ? `${minutes}m ${secs}s` : `${minutes}m`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
    }
}

async function showSessionDetail(sessionId) {
    const modal = document.getElementById('taskModal');
    modal.classList.add('active');

    document.getElementById('modalTaskTitle').textContent = `Session ${sessionId.substring(0, 13)}...`;
    document.getElementById('modalTaskSubtitle').textContent = 'Claude Code Session';
    document.getElementById('taskToolUsage').innerHTML = '<div class="no-data">Loading...</div>';
    document.getElementById('taskActivityLog').innerHTML = '<div class="no-data">No activity log available for sessions</div>';

    try {
        // Fetch screenshots
        await loadScreenshots(sessionId, 'session');

        const data = await fetchWithErrorHandling(`/api/sessions/${sessionId}/tool-usage`);

        if (data.error) {
            document.getElementById('taskToolUsage').innerHTML = `<div class="no-data">${escapeHtml(data.error)}</div>`;
            return;
        }

        renderTaskToolUsage(data);
    } catch (error) {
        document.getElementById('taskToolUsage').innerHTML = '<div class="no-data">Error loading session details</div>';
    }
}

async function showTaskDetail(taskId) {
    currentTaskId = taskId;
    const modal = document.getElementById('taskModal');
    modal.classList.add('active');

    document.getElementById('modalTaskTitle').textContent = `Task #${taskId}`;
    document.getElementById('modalTaskSubtitle').textContent = 'Loading details...';
    document.getElementById('taskToolUsage').innerHTML = '<div class="no-data">Loading...</div>';
    document.getElementById('taskActivityLog').innerHTML = '<div class="no-data">Loading...</div>';

    try {
        // Fetch task details
        const task = await fetchWithErrorHandling(`/api/tasks/${taskId}`);

        // Store task status globally
        currentTaskStatus = task.status;

        document.getElementById('modalTaskSubtitle').textContent = task.description;

        // Fetch screenshots
        await loadScreenshots(taskId, 'task');

        // Render activity log - combine consecutive identical messages
        if (task.activity_log && task.activity_log.length > 0) {
            // Combine consecutive identical messages
            const combined = [];
            let prev = null;

            for (const entry of task.activity_log) {
                if (prev && prev.message === entry.message) {
                    // Same as previous, skip it
                    continue;
                }
                combined.push(entry);
                prev = entry;
            }

            document.getElementById('taskActivityLog').innerHTML = combined.map(entry => `
                <div class="tool-item" style="margin-bottom: 0.5rem;">
                    <div>
                        <div class="tool-stats">${new Date(entry.timestamp).toLocaleString()}</div>
                        <div style="margin-top: 0.25rem;">${escapeHtml(entry.message)}</div>
                    </div>
                </div>
            `).reverse().join('');
        } else {
            document.getElementById('taskActivityLog').innerHTML = '<div class="no-data">No activity yet</div>';
        }

        // Fetch tool usage and worker chain for this task
        const toolUsageResponse = await fetch(`/api/tasks/${taskId}/tool-usage`);

        if (toolUsageResponse.ok) {
            const toolData = await toolUsageResponse.json();
            renderTaskToolUsage(toolData);
        } else {
            document.getElementById('taskToolUsage').innerHTML = '<div class="no-data">No tool usage data available yet</div>';
        }

        // Fetch documents for completed tasks
        if (task.status === 'completed') {
            const docsResponse = await fetch(`/api/tasks/${taskId}/documents`);
            if (docsResponse.ok) {
                const docsData = await docsResponse.json();
                renderTaskDocuments(docsData.documents, taskId);
            }
        }

    } catch (error) {
        console.error('Error loading task details:', error);
        document.getElementById('taskToolUsage').innerHTML = '<div class="no-data">Error loading tool usage</div>';
        document.getElementById('taskActivityLog').innerHTML = '<div class="no-data">Error loading activity</div>';
    }
}


function getToolIcon(tool) {
    if (tool === 'Bash') return '▶️';
    if (tool === 'Read') return '📖';
    if (tool === 'Write') return '📝';
    if (tool === 'Edit') return '✏️';
    if (tool === 'Grep') return '🔍';
    if (tool === 'Glob') return '🔎';
    if (tool === 'TodoWrite') return '✅';
    if (tool === 'Task') return '🚀';
    if (tool === 'WebSearch' || tool === 'web_search') return '🌐';
    
    // Playwright browser tools
    if (tool.includes('browser_navigate')) return '🧭';
    if (tool.includes('browser_click')) return '👆';
    if (tool.includes('browser_fill')) return '⌨️';
    if (tool.includes('browser_select')) return '🎯';
    if (tool.includes('browser_hover')) return '🖱️';
    if (tool.includes('browser_wait')) return '⏳';
    if (tool.includes('browser_get_text')) return '📝';
    if (tool.includes('browser_scroll')) return '📜';
    if (tool.includes('browser_evaluate')) return '⚡';
    if (tool.includes('browser_take_screenshot') || tool.includes('browser_screenshot')) return '📸';
    if (tool.includes('browser_close')) return '🚪';
    if (tool.includes('playwright')) return '🎭';
    
    // Generic MCP tools
    if (tool.startsWith('mcp__')) return '🔌';
    return '🔧';
}

function renderTaskToolUsage(toolData) {
    const container = document.getElementById('taskToolUsage');

    if (!toolData.tool_calls || toolData.tool_calls.length === 0) {
        container.innerHTML = '<div class="no-data">No tool usage data available yet</div>';
        return;
    }

    // Render planning progress if TodoWrite calls exist
    renderPlanningProgress(toolData.tool_calls);

    let html = '';

    // Terminal container with header
    html += '<div class="terminal-container">';
    html += '<div class="terminal-header" onclick="toggleToolExecutionLog()">';
    html += '<div class="terminal-title">';

    // Show total calls and how many are displayed
    const totalCalls = toolData.tool_calls.length;
    const displayedCalls = Math.min(totalCalls, TOOL_CALLS_LIMIT);
    const callsText = totalCalls > TOOL_CALLS_LIMIT
        ? `${displayedCalls} / ${totalCalls} calls (showing latest)`
        : `${totalCalls} calls`;

    html += `<span class="terminal-toggle" id="terminalToggle">▼</span>`;
    html += `<span>Tool Execution Log</span> <span style="color: #484f58;">•</span> <span>${callsText}</span>`;
    html += '</div>';
    html += '<div class="terminal-controls" onclick="event.stopPropagation()">';

    // Stop button (only for running tasks)
    if (currentTaskStatus === 'running') {
        html += `<button class="terminal-btn terminal-btn-danger" id="stopTaskBtn" onclick="stopCurrentTask()">⏹ Stop Task</button>`;
    }

    // Auto-scroll toggle
    html += `<button class="terminal-btn ${autoScrollEnabled ? 'active' : ''}" id="autoScrollToggle" onclick="toggleAutoScroll()">↓ Auto-scroll</button>`;
    html += '</div></div>';

    // Terminal body (expanded by default)
    const toolCalls = toolData.tool_calls || [];

    // Deduplicate consecutive identical tool calls
    const recentCalls = toolCalls.slice(-TOOL_CALLS_LIMIT);
    const dedupedCalls = [];
    let prev = null;

    for (const call of recentCalls) {
        // Check if this call is identical to previous (same tool + same parameters)
        if (prev && prev.tool === call.tool && JSON.stringify(prev.parameters) === JSON.stringify(call.parameters)) {
            // Skip consecutive duplicate
            continue;
        }
        dedupedCalls.push(call);
        prev = call;
    }

    html += '<div class="terminal-body expanded" id="toolTimelineScroll">';
    html += dedupedCalls.map((call, index) => {
        return renderTerminalToolCall(call, index + 1);
    }).join('');
    html += '</div>';

    html += '</div>'; // Close terminal-container

    container.innerHTML = html;

    // Pre-position at bottom immediately (no delay, no visible scroll)
    const scrollContainer = document.getElementById('toolTimelineScroll');
    if (scrollContainer && autoScrollEnabled) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
    }
}

function renderTaskDocuments(documents, taskId) {
    const container = document.getElementById('taskDocumentsList');

    if (!documents || documents.length === 0) {
        container.innerHTML = '<div class="no-data">No documents available</div>';
        return;
    }

    container.innerHTML = documents.map(doc => `
        <div class="tool-item" style="cursor: pointer; margin-bottom: 0.5rem;"
             onclick="showTaskDocument('${taskId}', '${escapeHtml(doc.filename)}')">
            <div class="tool-name">
                <span>📄</span>
                <span>${escapeHtml(doc.filename)}</span>
            </div>
            <div class="tool-stats">
                ${formatFileSize(doc.size)} • ${formatDate(doc.modified)}
            </div>
        </div>
    `).join('');
}

async function showTaskDocument(taskId, filename) {
    const modal = document.getElementById('docModal');
    modal.classList.add('active');

    document.getElementById('docModalTitle').textContent = filename;
    document.getElementById('docModalSubtitle').textContent = `Task #${taskId}`;
    document.getElementById('docContent').innerHTML = '<div class="no-data">Loading...</div>';

    try {
        const response = await fetch(`/api/tasks/${taskId}/documents?content=true`);
        const data = await response.json();
        const doc = data.documents.find(d => d.filename === filename);

        if (doc && doc.content) {
            document.getElementById('docContent').innerHTML = marked.parse(doc.content);
        } else {
            document.getElementById('docContent').innerHTML = '<div class="no-data">Document not found</div>';
        }
    } catch (error) {
        document.getElementById('docContent').innerHTML = '<div class="no-data">Error loading document</div>';
    }
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatDate(timestamp) {
    // Handle both ISO strings and Unix timestamps
    if (typeof timestamp === 'string') {
        return new Date(timestamp).toLocaleDateString();
    }
    return new Date(timestamp * 1000).toLocaleDateString();
}

function renderPlanningProgress(toolCalls) {
    const container = document.getElementById('taskPlanningProgress');

    // Extract all TodoWrite calls
    const todoWriteCalls = toolCalls.filter(call => call.tool === 'TodoWrite');

    if (todoWriteCalls.length === 0) {
        container.innerHTML = '';
        return;
    }

    // Get the latest TodoWrite call for current state
    const latestCall = todoWriteCalls[todoWriteCalls.length - 1];

    // Parse the output preview to get todos
    let todos = [];
    try {
        if (latestCall.output_preview) {
            // output_preview is a string representation of a Python dict
            // Convert single quotes to double quotes for JSON parsing
            const jsonStr = latestCall.output_preview
                .replace(/'/g, '"')
                .replace(/True/g, 'true')
                .replace(/False/g, 'false')
                .replace(/None/g, 'null');

            const preview = JSON.parse(jsonStr);
            todos = preview.newTodos || [];
        }
    } catch (error) {
        console.error('Error parsing TodoWrite output:', error);
        container.innerHTML = '';
        return;
    }

    if (todos.length === 0) {
        container.innerHTML = '';
        return;
    }

    // Calculate statistics
    const totalTodos = todos.length;
    const completedTodos = todos.filter(t => t.status === 'completed').length;
    const inProgressTodos = todos.filter(t => t.status === 'in_progress').length;

    // Build HTML - Terminal style, expanded by default
    let html = '<div class="planning-container">';

    // Header (clickable to toggle)
    html += '<div class="planning-header" onclick="togglePlanningProgress()">';
    html += '<div class="planning-title">';
    html += `<span class="planning-toggle" id="planningToggle">▼</span>`;
    html += `<span>Planning Progress</span>`;
    html += `<span style="color: #484f58;">•</span>`;
    html += `<span>${completedTodos}/${totalTodos} completed</span>`;
    if (inProgressTodos > 0) {
        html += `<span style="color: #484f58;">•</span>`;
        html += `<span style="color: #58a6ff;">${inProgressTodos} in progress</span>`;
    }
    html += '</div>';
    html += '</div>';

    // Body (expanded by default)
    html += '<div class="planning-body expanded" id="planningBody">';
    todos.forEach((todo, index) => {
        const statusIcon = getStatusIcon(todo.status);
        const statusClass = todo.status;

        html += `<div class="todo-item ${statusClass}">`;
        html += `<span class="todo-status-icon ${statusClass}">${statusIcon}</span>`;
        html += `<div class="todo-content">`;
        html += escapeHtml(todo.content);

        // Show activeForm if in progress
        if (todo.status === 'in_progress' && todo.activeForm) {
            html += `<div class="todo-active-form">↻ ${escapeHtml(todo.activeForm)}</div>`;
        }

        html += `</div>`;
        html += `</div>`;
    });
    html += '</div>';

    html += '</div>';

    container.innerHTML = html;
}

function togglePlanningProgress() {
    const toggle = document.getElementById('planningToggle');
    const body = document.getElementById('planningBody');

    if (!toggle || !body) return;

    const isExpanded = body.classList.contains('expanded');

    if (isExpanded) {
        body.classList.remove('expanded');
        toggle.classList.add('collapsed');
    } else {
        body.classList.add('expanded');
        toggle.classList.remove('collapsed');
    }
}

function toggleToolExecutionLog() {
    const toggle = document.getElementById('terminalToggle');
    const body = document.getElementById('toolTimelineScroll');

    if (!toggle || !body) return;

    const isExpanded = body.classList.contains('expanded');

    if (isExpanded) {
        body.classList.remove('expanded');
        toggle.classList.add('collapsed');
    } else {
        body.classList.add('expanded');
        toggle.classList.remove('collapsed');
    }
}

function getStatusIcon(status) {
    if (status === 'completed') return '✓';
    if (status === 'in_progress') return '⟳';
    return '○';
}

// Convert absolute path to relative path from workspace root
function toRelativePath(absolutePath) {
    if (!absolutePath) return '';

    // Try to extract workspace path from environment or use common prefix
    const workspacePath = '/Users/matifuentes/Workspace/';

    if (absolutePath.startsWith(workspacePath)) {
        return absolutePath.substring(workspacePath.length);
    }

    // If not in workspace, return as-is
    return absolutePath;
}

function renderTerminalToolCall(call, lineNumber) {
    const hasError = call.has_error || false;
    const outputLength = call.output_length || 0;
    const outputPreview = call.output_preview || '';
    const tool = call.tool || 'unknown';
    const timestamp = call.timestamp || null;
    const parameters = call.parameters || {};
    const status = call.status || 'completed';  // running or completed

    // Parse tool preview data
    let previewObj = null;
    if (outputPreview) {
        try {
            previewObj = JSON.parse(outputPreview);
        } catch (parseError) {
            previewObj = null;
        }
    }

    // Build clean summary text with selective color highlighting
    // Color scheme: commands have different colors, paths are orange
    let summaryText = '';

    if (tool === 'Bash') {
        const cmd = parameters.command || previewObj?.command || 'command';
        // Truncate long commands
        const fullCmd = cmd.length > 100 ? cmd.substring(0, 100) + '...' : cmd;
        
        // Parse command to highlight the command name
        const cmdParts = fullCmd.trim().split(/\s+/);
        const cmdName = cmdParts[0] || '';
        const cmdArgs = cmdParts.slice(1).join(' ');
        
        // Determine color based on command type
        let cmdColor = '#e6edf3'; // default white
        const cmdLower = cmdName.toLowerCase();
        
        if (cmdLower === 'git') {
            cmdColor = '#58a6ff'; // blue for git
        } else if (cmdLower === 'ls' || cmdLower === 'cd' || cmdLower === 'pwd' || cmdLower === 'mkdir' || cmdLower === 'rm' || cmdLower === 'cp' || cmdLower === 'mv') {
            cmdColor = '#a0713c'; // brown for file system commands
        } else if (cmdLower === 'npm' || cmdLower === 'yarn' || cmdLower === 'pnpm' || cmdLower === 'pip' || cmdLower === 'poetry') {
            cmdColor = '#d29922'; // yellow for package managers
        } else if (cmdLower === 'python' || cmdLower === 'node' || cmdLower === 'ruby' || cmdLower === 'go' || cmdLower === 'java') {
            cmdColor = '#3fb950'; // green for interpreters/runtimes
        } else if (cmdLower === 'docker' || cmdLower === 'kubectl' || cmdLower === 'terraform') {
            cmdColor = '#bc8cff'; // purple for devops tools
        } else if (cmdLower === 'echo' || cmdLower === 'cat' || cmdLower === 'grep' || cmdLower === 'sed' || cmdLower === 'awk' || cmdLower === 'find') {
            cmdColor = '#d29922'; // yellow for text processing
        }
        
        summaryText = `<span style="color: #6e7681;">Ran</span> <span style="color: ${cmdColor};">${escapeHtml(cmdName)}</span>`;
        if (cmdArgs) {
            summaryText += ` ${escapeHtml(cmdArgs)}`;
        }
    } else if (tool === 'Read') {
        const filePath = parameters.file_path || previewObj?.filePath || previewObj?.file?.filePath || 'file';
        const relativePath = toRelativePath(filePath);
        summaryText = `<span style="color: #a0713c;">Read</span> <span style="color: #e8a87c;">${escapeHtml(relativePath)}</span>`;
    } else if (tool === 'Write') {
        const filePath = parameters.file_path || previewObj?.filePath || previewObj?.file?.filePath || 'file';
        const relativePath = toRelativePath(filePath);
        summaryText = `<span style="color: #58a6ff;">Wrote</span> <span style="color: #e8a87c;">${escapeHtml(relativePath)}</span>`;
    } else if (tool === 'Edit') {
        const filePath = parameters.file_path || previewObj?.filePath || previewObj?.file?.filePath || 'file';
        const relativePath = toRelativePath(filePath);
        summaryText = `<span style="color: #58a6ff;">Edited</span> <span style="color: #e8a87c;">${escapeHtml(relativePath)}</span>`;
    } else if (tool === 'Grep') {
        const pattern = parameters.pattern || previewObj?.pattern || 'pattern';
        const truncPat = pattern.length > 60 ? pattern.substring(0, 60) + '...' : pattern;
        const path = parameters.path || 'codebase';
        summaryText = `<span style="color: #a0713c;">Grepped</span> <span style="color: #d29922;">"${escapeHtml(truncPat)}"</span> in <span style="color: #e8a87c;">${escapeHtml(path)}</span>`;
    } else if (tool === 'Glob') {
        const pattern = parameters.pattern || previewObj?.pattern || 'pattern';
        summaryText = `<span style="color: #a0713c;">Searched</span> files matching <span style="color: #d29922;">"${escapeHtml(pattern)}"</span>`;
    } else if (tool === 'CodebaseSearch' || tool === 'codebase_search') {
        const query = parameters.query || previewObj?.query || 'query';
        const truncQuery = query.length > 80 ? query.substring(0, 80) + '...' : query;
        summaryText = `<span style="color: #a0713c;">Searched</span> <span style="color: #d29922;">"${escapeHtml(truncQuery)}"</span>`;
    } else if (tool === 'Task') {
        const description = parameters.description || previewObj?.description || 'task';
        const subagentType = parameters.subagent_type || previewObj?.subagent_type || '';
        let taskDesc = escapeHtml(description);
        if (subagentType) {
            taskDesc += ` <span style="color: #8b949e;">(${escapeHtml(subagentType)})</span>`;
        }
        summaryText = `<span style="color: #bc8cff;">Delegated</span> ${taskDesc}`;
    } else if (tool === 'TodoWrite') {
        const todos = parameters.todos || previewObj?.todos || [];
        if (todos.length > 0) {
            const completed = todos.filter(t => t.status === 'completed').length;
            summaryText = `<span style="color: #3fb950;">Updated planning</span> <span style="color: #8b949e;">(${completed}/${todos.length} completed)</span>`;
        } else {
            summaryText = `<span style="color: #3fb950;">Updated planning</span>`;
        }
    } else if (tool === 'WebSearch' || tool === 'web_search') {
        const searchTerm = parameters.search_term || previewObj?.search_term || 'query';
        const truncTerm = searchTerm.length > 60 ? searchTerm.substring(0, 60) + '...' : searchTerm;
        summaryText = `<span style="color: #a0713c;">Searched web</span> for <span style="color: #d29922;">"${escapeHtml(truncTerm)}"</span>`;
    } else if (tool === 'mcp__playwright__browser_evaluate' || tool.includes('browser_evaluate')) {
        const script = parameters.script || previewObj?.script || '';
        const truncScript = script.length > 80 ? script.substring(0, 80) + '...' : script;
        if (truncScript) {
            summaryText = `<span style="color: #bc8cff;">Evaluated JS</span> <span style="color: #d29922;">"${escapeHtml(truncScript)}"</span>`;
        } else {
            summaryText = `<span style="color: #bc8cff;">Evaluated JavaScript</span> in browser`;
        }
    } else if (tool === 'mcp__playwright__browser_take_screenshot' || tool.includes('browser_take_screenshot')) {
        const name = parameters.name || previewObj?.name || 'screenshot';
        summaryText = `<span style="color: #bc8cff;">Captured screenshot</span> <span style="color: #e8a87c;">${escapeHtml(name)}</span>`;
    } else if (tool === 'mcp__playwright__browser_close' || tool.includes('browser_close')) {
        summaryText = `<span style="color: #bc8cff;">Closed browser</span> session`;
    } else if (tool === 'mcp__playwright__browser_navigate' || tool.includes('browser_navigate')) {
        const url = parameters.url || previewObj?.url || 'page';
        const truncUrl = url.length > 60 ? url.substring(0, 60) + '...' : url;
        summaryText = `<span style="color: #bc8cff;">Navigated to</span> <span style="color: #58a6ff;">${escapeHtml(truncUrl)}</span>`;
    } else if (tool === 'mcp__playwright__browser_click' || tool.includes('browser_click')) {
        const selector = parameters.selector || previewObj?.selector || 'element';
        summaryText = `<span style="color: #bc8cff;">Clicked</span> <span style="color: #d29922;">${escapeHtml(selector)}</span>`;
    } else if (tool === 'mcp__playwright__browser_fill' || tool.includes('browser_fill')) {
        const selector = parameters.selector || previewObj?.selector || 'field';
        const value = parameters.value || previewObj?.value || '';
        const truncValue = value.length > 40 ? value.substring(0, 40) + '...' : value;
        summaryText = `<span style="color: #bc8cff;">Filled</span> <span style="color: #d29922;">${escapeHtml(selector)}</span> with <span style="color: #e8a87c;">"${escapeHtml(truncValue)}"</span>`;
    } else if (tool === 'mcp__playwright__browser_select' || tool.includes('browser_select')) {
        const selector = parameters.selector || previewObj?.selector || 'dropdown';
        const value = parameters.value || previewObj?.value || '';
        summaryText = `<span style="color: #bc8cff;">Selected</span> <span style="color: #e8a87c;">"${escapeHtml(value)}"</span> in <span style="color: #d29922;">${escapeHtml(selector)}</span>`;
    } else if (tool === 'mcp__playwright__browser_hover' || tool.includes('browser_hover')) {
        const selector = parameters.selector || previewObj?.selector || 'element';
        summaryText = `<span style="color: #bc8cff;">Hovered over</span> <span style="color: #d29922;">${escapeHtml(selector)}</span>`;
    } else if (tool === 'mcp__playwright__browser_wait' || tool.includes('browser_wait')) {
        const selector = parameters.selector || previewObj?.selector || '';
        if (selector) {
            summaryText = `<span style="color: #bc8cff;">Waited for</span> <span style="color: #d29922;">${escapeHtml(selector)}</span>`;
        } else {
            summaryText = `<span style="color: #bc8cff;">Waited</span> for page load`;
        }
    } else if (tool === 'mcp__playwright__browser_get_text' || tool.includes('browser_get_text')) {
        const selector = parameters.selector || previewObj?.selector || 'element';
        summaryText = `<span style="color: #bc8cff;">Got text from</span> <span style="color: #d29922;">${escapeHtml(selector)}</span>`;
    } else if (tool === 'mcp__playwright__browser_scroll' || tool.includes('browser_scroll')) {
        summaryText = `<span style="color: #bc8cff;">Scrolled</span> page`;
    } else if (tool.startsWith('mcp__playwright__')) {
        // Generic Playwright tool handler
        const action = tool.replace('mcp__playwright__browser_', '').replace(/_/g, ' ');
        summaryText = `<span style="color: #bc8cff;">Browser ${escapeHtml(action)}</span>`;
    } else if (tool.startsWith('mcp__')) {
        // Generic MCP tool handler
        const mcpTool = tool.replace('mcp__', '').replace(/__/g, ' » ').replace(/_/g, ' ');
        summaryText = `<span style="color: #bc8cff;">MCP:</span> ${escapeHtml(mcpTool)}`;
    } else {
        // Generic fallback
        summaryText = `${escapeHtml(tool)}`;
    }

    // Add timing info if available (like "thought 4s" in screenshot)
    let timingInfo = '';
    if (previewObj?.duration) {
        const duration = Math.round(previewObj.duration);
        if (duration > 0) {
            timingInfo = `, ${duration}s`;
        }
    }

    // Build HTML - white text with colored highlights for key info
    const paramsJson = JSON.stringify(parameters);
    let html = `<div class="tool-call-entry" data-tool="${escapeHtml(tool)}" data-params="${escapeHtml(paramsJson)}" style="padding: 0.125rem 0; line-height: 1.3; color: #e6edf3;">`;

    html += summaryText;
    
    if (timingInfo) {
        html += `<span style="color: #8b949e;">${timingInfo}</span>`;
    }

    // Add error indicator if present
    if (hasError) {
        const errorMsg = previewObj?.error || 'error';
        html += ` <span style="color: #f85149;">• ${escapeHtml(errorMsg)}</span>`;
    }

    // Add running indicator
    if (status === 'running') {
        html += ` <span style="color: #58a6ff; font-style: italic;">running...</span>`;
    }

    html += `</div>`;

    return html;
}

function getToolClass(tool) {
    const normalized = tool.toLowerCase().replace(/_/g, '');
    if (normalized === 'bash') return 'bash';
    if (normalized === 'read') return 'read';
    if (normalized === 'write') return 'write';
    if (normalized === 'edit') return 'edit';
    if (normalized === 'grep') return 'grep';
    if (normalized === 'glob') return 'glob';
    if (normalized === 'task') return 'task';
    if (normalized === 'todowrite') return 'todowrite';
    if (normalized === 'websearch' || tool.includes('web_search')) return 'websearch';
    
    // Playwright tools get their own class
    if (tool.includes('playwright') || tool.includes('browser')) return 'playwright';
    
    // Generic MCP
    if (tool.startsWith('mcp__') || tool.startsWith('mcp_')) return 'mcp';
    return 'bash';
}

function getToolColorClass(tool) {
    const toolClass = getToolClass(tool);
    return `color-${toolClass}`;
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function toggleAutoScroll() {
    autoScrollEnabled = !autoScrollEnabled;
    const btn = document.getElementById('autoScrollToggle');
    if (btn) {
        if (autoScrollEnabled) {
            btn.classList.add('active');
            scrollToBottom();
        } else {
            btn.classList.remove('active');
        }
    }
}

function scrollToBottom() {
    const scrollContainer = document.getElementById('toolTimelineScroll');
    if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
    }
}

function expandToolCall(callId) {
    // Placeholder for future expand functionality
    console.log('Expand tool call:', callId);
}

function copyToClipboard(button, text) {
    // Decode HTML entities
    const textarea = document.createElement('textarea');
    textarea.innerHTML = text;
    const decodedText = textarea.value;

    navigator.clipboard.writeText(decodedText).then(() => {
        button.textContent = '✓ Copied';
        button.classList.add('copied');
        setTimeout(() => {
            button.textContent = 'Copy';
            button.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
        button.textContent = '✗ Failed';
    });
}

async function stopCurrentTask() {
    if (!currentTaskId) {
        showToast('No task selected', 'error');
        return;
    }

    if (!confirm('Stop this task? Progress will be saved but the task will not complete.')) {
        return;
    }

    try {
        const response = await fetch(`/api/tasks/${currentTaskId}/stop`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            showToast('Task stop requested', 'success');
            // Update status immediately in UI
            currentTaskStatus = 'stopped';
            // Hide stop button
            const stopBtn = document.getElementById('stopTaskBtn');
            if (stopBtn) {
                stopBtn.style.display = 'none';
            }
        } else {
            const error = await response.json();
            showToast(`Failed to stop task: ${error.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Error stopping task:', error);
        showToast('Error stopping task', 'error');
    }
}

function closeTaskModal() {
    document.getElementById('taskModal').classList.remove('active');
    currentTaskId = null;
    currentTaskStatus = null;
}

function showErrorsModal() {
    const modal = document.getElementById('errorsModal');
    modal.classList.add('active');

    const errorsList = document.getElementById('errorsList');
    errorsList.innerHTML = '<div class="no-data">Loading errors...</div>';

    if (currentData && currentData.overview.system_health.recent_errors) {
        const errors = currentData.overview.system_health.recent_errors;

        if (errors.length === 0) {
            errorsList.innerHTML = '<div class="no-errors">No recent errors</div>';
            return;
        }

        errorsList.innerHTML = errors.map(error => `
            <div class="error-item">
                <div class="error-header">
                    <div class="error-task-id">Task #${error.task_id}</div>
                    <div class="error-time">${new Date(error.timestamp).toLocaleString()}</div>
                </div>
                <div class="error-message">${escapeHtml(error.error)}</div>
            </div>
        `).join('');
    }
}

function closeErrorsModal() {
    document.getElementById('errorsModal').classList.remove('active');
}

function formatStatus(status) {
    return status.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function formatRelativeTime(timestamp) {
    const now = new Date();
    const then = new Date(timestamp);
    const diffMs = now - then;
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSecs < 60) return `${diffSecs}s ago`;
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
}

function formatTimestamp(timestamp) {
    // Format timestamp as HH:MM:SS
    const date = new Date(timestamp);
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    const seconds = date.getSeconds().toString().padStart(2, '0');
    return `${hours}:${minutes}:${seconds}`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Format number with commas (e.g., 12345 -> 12,345)
function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// Format number with K/M suffix for large numbers
function formatNumberCompact(num) {
    if (num === null || num === undefined || num === 0) return '0';
    if (num < 1000) return num.toString();
    if (num < 1000000) return (num / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    return (num / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
}

// Calculate total tokens and return formatted display string
function formatTokenUsage(tokenUsage) {
    if (!tokenUsage) return null;

    const input = tokenUsage.input_tokens || 0;
    const output = tokenUsage.output_tokens || 0;
    const cacheCreation = tokenUsage.cache_creation_tokens || 0;
    const cacheRead = tokenUsage.cache_read_tokens || 0;
    const total = input + output + cacheCreation + cacheRead;

    // Don't display if no tokens used
    if (total === 0) return null;

    return {
        total,
        input,
        output,
        cacheCreation,
        cacheRead,
        display: `${formatNumberCompact(total)} total (${formatNumberCompact(input)} in / ${formatNumberCompact(output)} out)`
    };
}

// Close errors modal on background click (task modal is full-screen, no background click)
document.getElementById('errorsModal').addEventListener('click', (e) => {
    if (e.target.id === 'errorsModal') {
        closeErrorsModal();
    }
});

// Close modals on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeTaskModal();
        closeErrorsModal();
        closeDocModal();
    }
});

// Documentation functions
async function loadDocumentation() {
    try {
        const data = await fetchWithErrorHandling('/api/docs/list');

        if (data.error) {
            document.getElementById('docsList').innerHTML = `<div class="no-data">Error: ${data.error}</div>`;
            return;
        }

        allDocs = data.files || [];
        renderDocsList();
    } catch (error) {
        document.getElementById('docsList').innerHTML = '<div class="no-data">Error loading documentation</div>';
    }
}

function filterDocs(filter) {
    currentDocsFilter = filter;
    docsPage = 1; // Reset to first page

    // Update button states and ARIA attributes
    const allBtn = document.getElementById('showAllDocs');
    const activeBtn = document.getElementById('showActiveDocs');
    const archiveBtn = document.getElementById('showArchiveDocs');

    const isAll = filter === 'all';
    const isActive = filter === 'active';
    const isArchive = filter === 'archive';

    allBtn.classList.toggle('active', isAll);
    allBtn.setAttribute('aria-pressed', isAll.toString());

    activeBtn.classList.toggle('active', isActive);
    activeBtn.setAttribute('aria-pressed', isActive.toString());

    archiveBtn.classList.toggle('active', isArchive);
    archiveBtn.setAttribute('aria-pressed', isArchive.toString());

    renderDocsList();
}

function changeDocsPage(delta) {
    const newPage = docsPage + delta;
    if (newPage >= 1) {
        docsPage = newPage;
        renderDocsList();
    }
}

function renderDocsList() {
    const list = document.getElementById('docsList');

    if (!allDocs || allDocs.length === 0) {
        list.innerHTML = '<div class="no-data">No documentation files found</div>';
        document.getElementById('docsPagination').style.display = 'none';
        return;
    }

    // Filter docs based on current filter
    let filteredDocs = allDocs;
    if (currentDocsFilter === 'active') {
        filteredDocs = allDocs.filter(doc => !doc.is_archive);
    } else if (currentDocsFilter === 'archive') {
        filteredDocs = allDocs.filter(doc => doc.is_archive);
    }

    // Sort by modification date (latest first)
    filteredDocs.sort((a, b) => b.modified - a.modified);

    if (filteredDocs.length === 0) {
        list.innerHTML = `<div class="no-data">No ${currentDocsFilter} documentation files</div>`;
        document.getElementById('docsPagination').style.display = 'none';
        return;
    }

    // Pagination
    const totalDocs = filteredDocs.length;
    const totalDocsPages = Math.ceil(totalDocs / docsPageSize);
    const startIdx = (docsPage - 1) * docsPageSize;
    const endIdx = Math.min(startIdx + docsPageSize, totalDocs);
    const paginatedDocs = filteredDocs.slice(startIdx, endIdx);

    // Update pagination controls
    const paginationDiv = document.getElementById('docsPagination');
    const paginationInfo = document.getElementById('docsPaginationInfo');
    const buttons = paginationDiv.querySelectorAll('.pagination-btn');

    if (totalDocsPages > 1) {
        paginationDiv.style.display = 'flex';
        paginationInfo.textContent = `Page ${docsPage} of ${totalDocsPages} (${totalDocs} docs)`;
        buttons[0].disabled = docsPage === 1;
        buttons[1].disabled = docsPage === totalDocsPages;
    } else {
        paginationDiv.style.display = 'none';
    }

    list.innerHTML = '<div class="tool-list">' + paginatedDocs.map(doc => {
        const sizeKB = (doc.size / 1024).toFixed(1);
        const modified = new Date(doc.modified * 1000).toLocaleString();
        const isArchive = doc.is_archive;
        const showArchiveBtn = !isArchive && currentDocsFilter !== 'archive';
        const showRestoreBtn = isArchive;

        // Status badge
        const statusBadge = isArchive
            ? '<span class="doc-status-badge archived">Archived</span>'
            : '<span class="doc-status-badge active">Active</span>';

        return `
            <div class="tool-item doc-item ${isArchive ? 'archived' : ''}">
                <div class="doc-item-content" onclick="showDocContent('${escapeHtml(doc.path)}')">
                    <div class="tool-name">
                        ${escapeHtml(doc.name)}
                        ${statusBadge}
                    </div>
                    <div class="tool-stats">${escapeHtml(doc.path)} • ${sizeKB} KB</div>
                    <div class="tool-stats" style="font-size: 0.7rem; margin-top: 0.25rem;">Modified: ${modified}</div>
                </div>
                ${showArchiveBtn ? `
                    <button class="archive-btn" onclick="event.stopPropagation(); archiveDocument('${escapeHtml(doc.path)}', '${escapeHtml(doc.name)}')">
                        📦 Archive
                    </button>
                ` : ''}
                ${showRestoreBtn ? `
                    <button class="restore-btn" onclick="event.stopPropagation(); restoreDocument('${escapeHtml(doc.path)}', '${escapeHtml(doc.name)}')">
                        ↺ Restore
                    </button>
                ` : ''}
                <div style="color: var(--accent-blue); font-size: 1.25rem; cursor: pointer;" onclick="showDocContent('${escapeHtml(doc.path)}')">→</div>
            </div>
        `;
    }).join('') + '</div>';
}

async function showDocContent(path) {
    const modal = document.getElementById('docModal');
    modal.classList.add('active');

    document.getElementById('docModalTitle').textContent = path.split('/').pop();
    document.getElementById('docModalSubtitle').textContent = path;
    document.getElementById('docContent').innerHTML = '<div class="no-data">Loading...</div>';

    try {
        const data = await fetchWithErrorHandling(`/api/docs/content?path=${encodeURIComponent(path)}`);

        if (data.error) {
            document.getElementById('docContent').innerHTML = `<div class="no-data">Error: ${data.error}</div>`;
            return;
        }

        // Render markdown content
        const content = data.content;
        const isMarkdown = path.toLowerCase().endsWith('.md');

        if (isMarkdown && typeof marked !== 'undefined') {
            // Configure marked for better rendering
            marked.setOptions({
                breaks: true,
                gfm: true,
                headerIds: true,
                mangle: false
            });
            document.getElementById('docContent').innerHTML = marked.parse(content);
        } else {
            // Plain text fallback
            document.getElementById('docContent').innerHTML = `<pre style="white-space: pre-wrap; font-family: ui-monospace, monospace;">${escapeHtml(content)}</pre>`;
        }

    } catch (error) {
        document.getElementById('docContent').innerHTML = '<div class="no-data">Error loading document</div>';
    }
}

function closeDocModal() {
    document.getElementById('docModal').classList.remove('active');
}

async function archiveDocument(path, name) {
    if (!confirm(`Archive "${name}"?`)) {
        return;
    }

    try {
        const response = await fetch('/api/docs/archive', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ path: path })
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showToast(`Archived "${name}" successfully`, 'success');
            // Reload the documentation list silently
            await loadDocumentation();
            renderDocsList();
        } else {
            showToast(`Error: ${result.error || 'Failed to archive document'}`, 'error');
        }
    } catch (error) {
        console.error('Error archiving document:', error);
        showToast('Error archiving document. Please try again.', 'error');
    }
}

async function restoreDocument(path, name) {
    if (!confirm(`Restore "${name}" from archive?`)) {
        return;
    }

    try {
        const response = await fetch('/api/docs/restore', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ path: path })
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showToast(`Restored "${name}" successfully`, 'success');
            // Reload the documentation list silently
            await loadDocumentation();
            renderDocsList();
        } else {
            showToast(`Error: ${result.error || 'Failed to restore document'}`, 'error');
        }
    } catch (error) {
        console.error('Error restoring document:', error);
        showToast('Error restoring document. Please try again.', 'error');
    }
}

// Close doc modal on background click
document.getElementById('docModal').addEventListener('click', (e) => {
    if (e.target.id === 'docModal') {
        closeDocModal();
    }
});

async function downloadTaskOutput(taskId) {
    const btn = event.target.closest('.download-btn');
    const originalContent = btn.innerHTML;

    try {
        // Show loading state
        btn.disabled = true;
        btn.innerHTML = '<span class="download-icon">⟳</span><span class="download-text">Downloading...</span>';

        // Trigger download
        const response = await fetch(`/api/tasks/${taskId}/output/download`);

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Download failed');
        }

        // Get filename from Content-Disposition header or use default
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `task_${taskId}_output.md`;
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
            if (filenameMatch) {
                filename = filenameMatch[1];
            }
        }

        // Download the file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        // Show success state
        btn.innerHTML = '<span class="download-icon">✓</span><span class="download-text">Downloaded</span>';
        showToast('Output file downloaded successfully', 'success');

        // Reset button after 2 seconds
        setTimeout(() => {
            btn.innerHTML = originalContent;
            btn.disabled = false;
        }, 2000);

    } catch (error) {
        console.error('Download error:', error);
        showToast(`Download failed: ${error.message}`, 'error');

        // Reset button
        btn.innerHTML = originalContent;
        btn.disabled = false;
    }
}

// Screenshot functionality
let currentScreenshots = [];
let currentScreenshotIndex = 0;

async function loadScreenshots(id, type) {
    try {
        const endpoint = type === 'task' ? `/api/tasks/${id}/screenshots` : `/api/sessions/${id}/screenshots`;
        const data = await fetchWithErrorHandling(endpoint);

        if (data.screenshots && data.screenshots.length > 0) {
            currentScreenshots = data.screenshots;
            renderScreenshots(data.screenshots);
        } else {
            // Add empty screenshots section
            const planningContainer = document.getElementById('taskPlanningProgress');
            planningContainer.innerHTML = '<div class="no-data">No screenshots available</div>';
        }
    } catch (error) {
        console.error('Error loading screenshots:', error);
    }
}

function renderScreenshots(screenshots) {
    if (!screenshots || screenshots.length === 0) return;

    const planningContainer = document.getElementById('taskPlanningProgress');

    let html = '<div class="screenshots-section">';
    html += '<div class="screenshots-header" onclick="toggleScreenshots()">';
    html += '<div class="screenshots-title">';
    html += `<span class="screenshots-toggle collapsed" id="screenshotsToggle">▼</span>`;
    html += `<span>Screenshots</span> <span style="color: #484f58;">•</span> <span>${screenshots.length} image${screenshots.length > 1 ? 's' : ''}</span>`;
    html += '</div>';
    html += '</div>';
    html += '<div class="screenshots-body" id="screenshotsBody">';
    html += '<div class="screenshots-grid">';

    screenshots.forEach((screenshot, index) => {
        const timestamp = new Date(screenshot.timestamp).toLocaleString();
        const filename = screenshot.filename || screenshot.path.split('/').pop();

        html += `<div class="screenshot-item" onclick="openLightbox(${index})">`;
        html += `<img src="${screenshot.url}" alt="${filename}" loading="lazy">`;
        html += `<div class="screenshot-caption">`;
        html += `<div>${escapeHtml(filename)}</div>`;
        html += `<div class="screenshot-timestamp">${timestamp}</div>`;
        html += '</div>';
        html += '</div>';
    });

    html += '</div>'; // screenshots-grid
    html += '</div>'; // screenshots-body
    html += '</div>'; // screenshots-section

    planningContainer.innerHTML = html;
}

function toggleScreenshots() {
    const toggle = document.getElementById('screenshotsToggle');
    const body = document.getElementById('screenshotsBody');

    if (toggle && body) {
        toggle.classList.toggle('collapsed');
        body.classList.toggle('expanded');
    }
}

function openLightbox(index) {
    currentScreenshotIndex = index;
    showLightbox();
}

function showLightbox() {
    const lightbox = document.getElementById('lightbox');
    const image = document.getElementById('lightboxImage');
    const info = document.getElementById('lightboxInfo');
    const prevBtn = document.getElementById('lightboxPrev');
    const nextBtn = document.getElementById('lightboxNext');

    if (currentScreenshots.length === 0) return;

    const screenshot = currentScreenshots[currentScreenshotIndex];
    image.src = screenshot.url;

    const filename = screenshot.filename || screenshot.path.split('/').pop();
    const timestamp = new Date(screenshot.timestamp).toLocaleString();
    info.textContent = `${filename} • ${timestamp} • ${currentScreenshotIndex + 1} / ${currentScreenshots.length}`;

    prevBtn.disabled = currentScreenshotIndex === 0;
    nextBtn.disabled = currentScreenshotIndex === currentScreenshots.length - 1;

    lightbox.classList.add('active');

    // Add keyboard navigation
    document.addEventListener('keydown', handleLightboxKeyboard);
}

function closeLightbox(event) {
    if (event && event.type === 'click' && event.target.closest('.lightbox-content')) {
        return; // Don't close if clicking inside content
    }

    const lightbox = document.getElementById('lightbox');
    lightbox.classList.remove('active');

    // Remove keyboard navigation
    document.removeEventListener('keydown', handleLightboxKeyboard);
}

function navigateLightbox(direction) {
    const newIndex = currentScreenshotIndex + direction;
    if (newIndex >= 0 && newIndex < currentScreenshots.length) {
        currentScreenshotIndex = newIndex;
        showLightbox();
    }
}

function handleLightboxKeyboard(e) {
    if (e.key === 'Escape') {
        closeLightbox();
    } else if (e.key === 'ArrowLeft') {
        navigateLightbox(-1);
    } else if (e.key === 'ArrowRight') {
        navigateLightbox(1);
    }
}

// Export functions to window for onclick handlers
window.setTimeRange = setTimeRange;
window.manualRefresh = manualRefresh;
window.toggleAutoRefresh = toggleAutoRefresh;
window.setUnifiedFilter = setUnifiedFilter;
window.changePage = changePage;
window.showTaskDetail = showTaskDetail;
window.showSessionDetail = showSessionDetail;
window.closeTaskModal = closeTaskModal;
window.showErrorsModal = showErrorsModal;
window.closeErrorsModal = closeErrorsModal;
window.toggleAutoScroll = toggleAutoScroll;
window.expandToolCall = expandToolCall;
window.copyToClipboard = copyToClipboard;
window.filterDocs = filterDocs;
window.changeDocsPage = changeDocsPage;
window.showDocContent = showDocContent;
window.closeDocModal = closeDocModal;
window.archiveDocument = archiveDocument;
window.restoreDocument = restoreDocument;
window.downloadTaskOutput = downloadTaskOutput;
window.togglePlanningProgress = togglePlanningProgress;
window.toggleToolExecutionLog = toggleToolExecutionLog;
window.toggleScreenshots = toggleScreenshots;
window.openLightbox = openLightbox;
window.closeLightbox = closeLightbox;
window.navigateLightbox = navigateLightbox;
window.showTaskDocument = showTaskDocument;
