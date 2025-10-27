// Dashboard Configuration Constants

// Pagination limits
export const TASK_LIMIT = 8;
export const TOOL_CALLS_LIMIT = 1000; // Show up to 1000 tool calls (effectively unlimited for most tasks)
export const ACTIVITY_ITEMS_LIMIT = 8;
export const DOCS_PAGE_SIZE = 8;

// Truncation length for preview text
export const TRUNCATE_LENGTH = 300;
export const SHORT_TRUNCATE_LENGTH = 200;

// Connection settings
export const MAX_RECONNECT_ATTEMPTS = 10;
export const INITIAL_RECONNECT_DELAY = 2000; // 2 seconds
export const MAX_SILENCE_TIME = 15000; // 15 seconds without updates
export const CONNECTION_MONITOR_INTERVAL = 5000; // 5 seconds
export const SSE_POLL_INTERVAL = 2000; // 2 seconds

// API endpoints
export const API_ENDPOINTS = {
    STREAM_METRICS: '/api/stream/metrics',
    METRICS_OVERVIEW: '/api/metrics/overview',
    TASKS_RUNNING: '/api/tasks/running',
    TASKS_COMPLETED: '/api/tasks/completed',
    TASKS_FAILED: '/api/tasks/failed',
    TASKS_ALL: '/api/tasks/all',
    TASK_DETAIL: '/api/tasks',
    TASK_TOOL_USAGE: '/api/tasks',
    SESSIONS: '/api/sessions',
    CLAUDE_SESSIONS: '/api/metrics/claude-sessions',
    DOCS_LIST: '/api/docs/list',
    DOCS_CONTENT: '/api/docs/content',
    DOCS_ARCHIVE: '/api/docs/archive'
};

// Default theme
export const DEFAULT_THEME = 'dark';

// Time ranges (in hours)
export const TIME_RANGES = {
    DAY: 24,
    WEEK: 168,
    MONTH: 720
};
