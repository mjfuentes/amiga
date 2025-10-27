# Dashboard JavaScript Changes Required

## Summary
The HTML and CSS have been updated to implement the consolidated dashboard design. The JavaScript file needs the following changes to support the new unified interface.

## Key Changes Needed in `telegram_bot/static/js/dashboard.js`

### 1. Remove Theme Toggle Function
- Delete `toggleTheme()` function (lines ~54-66)
- Remove from window exports at bottom
- Theme is now hardcoded to dark in HTML

### 2. Replace Task Filter with Unified Filter

**Replace:**
```javascript
let currentTaskFilter = 'active'; // 'active', 'completed', 'failed', 'all'

function setTaskFilter(filter) {
    currentTaskFilter = filter;
    // ...
}

function fetchRunningTasks() {
    // Separate endpoints for different filters
}
```

**With:**
```javascript
let currentUnifiedFilter = 'all'; // 'all', 'tasks', 'sessions', 'active', 'completed', 'failed'

function setUnifiedFilter(filter) {
    currentUnifiedFilter = filter;
    currentPage = 1;
    
    // Update button states in tasks/sessions section
    document.querySelectorAll('#tasksSessionsSection .filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === filter);
    });
    
    fetchUnifiedData();
}

async function fetchUnifiedData() {
    let tasks = [];
    let sessions = [];
    
    // Fetch tasks if filter includes them
    if (['all', 'tasks', 'active', 'completed', 'failed'].includes(currentUnifiedFilter)) {
        let endpoint = '/api/tasks/all';
        if (currentUnifiedFilter === 'active') endpoint = '/api/tasks/running';
        else if (currentUnifiedFilter === 'completed') endpoint = '/api/tasks/completed';
        else if (currentUnifiedFilter === 'failed') endpoint = '/api/tasks/failed';
        
        endpoint += `?page=${currentPage}&page_size=${pageSize}`;
        
        const response = await fetch(endpoint);
        if (response.ok) {
            const data = await response.json();
            tasks = data.tasks || [];
        }
    }
    
    // Fetch sessions if filter includes them
    if (['all', 'sessions'].includes(currentUnifiedFilter)) {
        const data = await fetchWithErrorHandling('/api/metrics/claude-sessions?hours=168');
        if (data.recent_sessions) {
            // Filter out task sessions - only UUID sessions
            sessions = data.recent_sessions.filter(s =>
                s.session_id.includes('-') && s.session_id.length > 20
            ).map(s => ({ ...s, type: 'session' }));
        }
    }
    
    renderUnifiedGrid(tasks, sessions);
}

function renderUnifiedGrid(tasks, sessions) {
    const grid = document.getElementById('unifiedGrid');
    const badge = document.getElementById('tasksSessionsBadge');
    
    let items = [];
    
    if (['all', 'tasks', 'active', 'completed', 'failed'].includes(currentUnifiedFilter)) {
        items = items.concat(tasks.map(t => ({ ...t, type: 'task' })));
    }
    
    if (['all', 'sessions'].includes(currentUnifiedFilter)) {
        items = items.concat(sessions);
    }
    
    badge.textContent = items.length;
    updatePagination(items.length);
    
    if (items.length === 0) {
        grid.innerHTML = `<div class="empty-state">No ${currentUnifiedFilter} items</div>`;
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
    return `<div class="task-card ${task.status}" onclick="showTaskDetail('${task.task_id}')">
        <div class="task-header">
            <div class="task-id">Task #${task.task_id}</div>
            <div class="task-status ${task.status}">${formatStatus(task.status)}</div>
        </div>
        <div class="task-description">${escapeHtml(task.description)}</div>
        <div class="task-meta">
            <div class="task-meta-item">
                <span>⚙️</span>
                <span>${task.workflow || task.worker_type || 'N/A'}</span>
            </div>
            <div class="task-meta-item">
                <span>🧠</span>
                <span>${task.model}</span>
            </div>
            <div class="task-meta-item">
                <span>📅</span>
                <span>${formatRelativeTime(task.updated_at)}</span>
            </div>
        </div>
        ${task.latest_activity ? `
            <div class="task-activity">
                ${escapeHtml(task.latest_activity)}
            </div>
        ` : ''}
    </div>`;
}

function renderSessionCard(session) {
    return `<div class="task-card session" onclick="showSessionDetail('${session.session_id}')">
        <div class="task-header">
            <div class="task-id">Session ${session.session_id.substring(0, 8)}...</div>
            <div class="task-status session">Session</div>
        </div>
        <div class="task-description">Claude Code Session</div>
        <div class="task-meta">
            <div class="task-meta-item">
                <span>🔧</span>
                <span>${session.total_tools} tools</span>
            </div>
            ${session.errors > 0 ? `
                <div class="task-meta-item">
                    <span>❌</span>
                    <span>${session.errors} errors</span>
                </div>
            ` : ''}
        </div>
    </div>`;
}
```

### 3. Update Badge Logic

**Replace:**
```javascript
function renderRunningTasks(taskStats) {
    const badge = document.getElementById('runningTasksBadge');
    // ...
}
```

**With:**
```javascript
function updateUnifiedBadge(taskStats) {
    const badge = document.getElementById('tasksSessionsBadge');
    
    if (currentUnifiedFilter === 'all') {
        badge.textContent = taskStats.total_tasks || 0;
    } else if (currentUnifiedFilter === 'active') {
        badge.textContent = (taskStats.by_status.running || 0) + (taskStats.by_status.pending || 0);
    } else if (currentUnifiedFilter === 'completed') {
        badge.textContent = taskStats.by_status.completed || 0;
    } else if (currentUnifiedFilter === 'failed') {
        badge.textContent = taskStats.by_status.failed || 0;
    }
}
```

### 4. Remove Tab-Related Functions

**Delete these functions:**
- `switchTab()` - no longer needed, no tabs
- `renderActivityFeed()` - activity feed removed
- `renderToolsList()` - tools list removed
- `renderSessionsList()` - merged into unified grid

### 5. Update renderDashboard() 

**Replace:**
```javascript
function renderDashboard(data) {
    const overview = data.overview;
    const sessions = data.sessions;

    // Running Tasks
    renderRunningTasks(overview.task_statistics);

    // Metrics
    document.getElementById('errorCount').textContent = overview.system_health.recent_errors_24h;
    document.getElementById('totalTasks').textContent = overview.task_statistics.total_tasks.toLocaleString();
    document.getElementById('successRate').textContent = `${overview.task_statistics.success_rate.toFixed(1)}% success`;
    document.getElementById('apiCost').textContent = `$${overview.claude_api_usage.recent_cost.toFixed(2)}`;
    document.getElementById('apiRequests').textContent = `${overview.claude_api_usage.recent_requests.toLocaleString()} requests`;
    document.getElementById('toolCalls').textContent = sessions.total_tool_calls.toLocaleString();
    document.getElementById('codeSessions').textContent = `${sessions.total_sessions} sessions`;

    // Overview tab
    document.getElementById('completedTasks').textContent = overview.task_statistics.by_status.completed;
    // ... etc
}
```

**With:**
```javascript
function renderDashboard(data) {
    const overview = data.overview;
    const sessions = data.sessions;

    // Update unified badge
    updateUnifiedBadge(overview.task_statistics);

    // Update footer stats
    document.getElementById('errorCount').textContent = overview.system_health.recent_errors_24h;
    document.getElementById('totalTasks').textContent = overview.task_statistics.total_tasks.toLocaleString();
    document.getElementById('successRate').textContent = `${overview.task_statistics.success_rate.toFixed(1)}%`;
    document.getElementById('apiCost').textContent = `$${overview.claude_api_usage.recent_cost.toFixed(2)}`;
    document.getElementById('apiRequests').textContent = overview.claude_api_usage.recent_requests.toLocaleString();
    document.getElementById('toolCalls').textContent = sessions.total_tool_calls.toLocaleString();
    document.getElementById('codeSessions').textContent = sessions.total_sessions;
}
```

### 6. Update Pagination Element IDs

**Replace:**
```javascript
const paginationDiv = document.getElementById('tasksPagination');
```

**With:**
```javascript
const paginationDiv = document.getElementById('unifiedPagination');
```

### 7. Update DOMContentLoaded

**Replace:**
```javascript
document.addEventListener('DOMContentLoaded', () => {
    const savedTheme = localStorage.getItem('dashboard-theme') || DEFAULT_THEME;
    document.documentElement.setAttribute('data-theme', savedTheme);
    
    fetchRunningTasks();
    
    startRealtimeUpdates();
    startConnectionMonitor();
});
```

**With:**
```javascript
document.addEventListener('DOMContentLoaded', () => {
    // Always use dark theme
    document.documentElement.setAttribute('data-theme', 'dark');
    
    // Initial load
    fetchUnifiedData();
    loadDocumentation();
    
    startRealtimeUpdates();
    startConnectionMonitor();
});
```

### 8. Update Window Exports

**Remove:**
```javascript
window.toggleTheme = toggleTheme;
window.setTaskFilter = setTaskFilter;
window.switchTab = switchTab;
```

**Add:**
```javascript
window.setUnifiedFilter = setUnifiedFilter;
```

## Testing Checklist

- [ ] Unified filter buttons work (All, Tasks, Sessions, Active, Completed, Failed)
- [ ] Task cards render correctly with click to view details
- [ ] Session cards render correctly with click to view details
- [ ] Pagination works for large lists
- [ ] Badge updates correctly based on filter
- [ ] Footer stats update via SSE
- [ ] No JavaScript console errors
- [ ] Documentation section filters work (All, Active, Archive)
- [ ] Error modal still works when clicking errors stat
- [ ] Dark theme is always active

## Files Modified

1. `telegram_bot/templates/dashboard.html` - DONE ✓
2. `telegram_bot/static/css/dashboard.css` - DONE ✓
3. `telegram_bot/static/js/dashboard.js` - TODO (changes documented above)
