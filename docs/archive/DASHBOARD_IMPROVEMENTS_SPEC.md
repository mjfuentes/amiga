# Dashboard Improvements Specification

## Overview
The monitoring dashboard has been recently refactored into modular files (separate CSS, JS). This document outlines the required improvements.

## Current Structure
- **HTML**: `telegram_bot/templates/dashboard.html` (minimal structure)
- **CSS**: `telegram_bot/static/css/dashboard.css` (styling)
- **JS**: `telegram_bot/static/js/dashboard.js` (logic)
- **Config**: `telegram_bot/static/js/config.js` (constants)

## Required Changes

### 1. Remove Light Theme (CSS + JS)
**Files**: `dashboard.css`, `dashboard.js`

**Actions**:
- Remove `:root` light theme CSS variables (keep only `[data-theme="dark"]`)
- Remove theme toggle button from controls
- Remove `toggleTheme()` function
- Remove localStorage theme persistence
- Force dark theme only

### 2. Remove Manual Refresh Controls (HTML + JS)
**Files**: `dashboard.html`, `dashboard.js`

**Actions**:
- Remove "🔄 Refresh" button from controls
- Remove auto-refresh toggle checkbox from status indicator
- Remove `manualRefresh()` and `toggleAutoRefresh()` functions
- Always enable SSE auto-refresh
- Keep SSE connection status indicator (connected/reconnecting/failed)

### 3. Merge Tasks and Cloud Sessions (HTML + JS)
**Files**: `dashboard.html`, `dashboard.js`

**Current**:
- Separate "Tasks" section with filters (Active/Completed/Failed/All)
- Separate "Claude Sessions" tab

**New**:
- Single unified section "Tasks & Sessions"
- Three filters: "Tasks", "Cloud Sessions", "All"
- Fetch both task data and session data
- Render unified card grid
- Task cards show: task ID, description, status, worker, model, timestamp
- Session cards show: session ID, tool count, errors
- Both clickable for details modal

**API Endpoints**:
- `/api/tasks/all` - Get all tasks
- `/api/metrics/claude-sessions?hours=168` - Get sessions
- Filter UUID sessions only (length > 20, contains `-`)

### 4. Consolidate Metrics to Footer (HTML + CSS + JS)
**Files**: `dashboard.html`, `dashboard.css`, `dashboard.js`

**Current**:
- Metrics row with large cards (Errors, Total Tasks, API Cost, Tool Calls)
- Overview tab with duplicate stats
- Recent Activity tab (not working well)
- Tools tab

**New**:
- Remove metrics row cards
- Remove Overview/Activity/Tools tabs entirely
- Create footer stats panel with compact layout
- Show: Errors (24h), Total Tasks, Success Rate, API Cost, API Requests, Tool Calls, Sessions

**CSS Styling**:
```css
.footer-stats {
    background: var(--bg-secondary);
    border: 1.5px solid var(--border-color);
    border-radius: 1rem;
    padding: 1.25rem;
    margin-top: 2rem;
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem;
}

.stat-item {
    display: flex;
    flex-direction: column;
}

.stat-label {
    font-size: 0.75rem;
    color: var(--text-muted);
}

.stat-value {
    font-size: 1.25rem;
    font-weight: 600;
}
```

### 5. Documentation as Standalone Section (HTML + CSS)
**Files**: `dashboard.html`, `dashboard.css`

**Current**:
- Documentation is a tab

**New**:
- Remove docs tab
- Create standalone section below unified tasks/sessions
- Same functionality (filter active/archive, view, archive docs)
- Better visual hierarchy

**HTML Structure**:
```html
<div class="documentation-section">
    <div class="documentation-header">
        <div class="documentation-title">Documentation</div>
        <div class="documentation-controls">
            <button class="btn active">Active</button>
            <button class="btn">Archive</button>
            <button class="btn">All</button>
        </div>
    </div>
    <div id="docsList">...</div>
    <div class="pagination">...</div>
</div>
```

### 6. Fix/Remove Overview and Recent Activity
**Files**: `dashboard.js`

**Analysis Needed**:
- Check if these sections provide value
- If not useful, remove entirely
- If useful, fix data sources and rendering

**Current Issues**:
- Overview shows duplicate stats
- Recent Activity feed may not populate correctly

**Decision**: Remove both (already covered by footer stats and unified view)

## Implementation Priority

1. **High**: Remove light theme, remove manual refresh controls
2. **High**: Merge tasks and sessions into unified view
3. **High**: Consolidate metrics to footer
4. **Medium**: Documentation as standalone section
5. **Low**: Clean up removed Overview/Activity tabs code

## Testing Checklist

- [ ] Dark theme only (no light theme toggle)
- [ ] SSE auto-refresh works (no manual controls)
- [ ] Unified tasks/sessions view with filters
- [ ] Task cards clickable → modal with tool usage
- [ ] Session cards clickable → modal with tool usage
- [ ] Footer stats display correctly
- [ ] Documentation section standalone and functional
- [ ] No console errors
- [ ] Responsive design maintained

## Notes

- Maintain all existing modal functionality
- Keep terminal-style tool usage display
- Preserve SSE real-time updates
- Maintain pagination for tasks/sessions/docs
- Keep accessibility features

