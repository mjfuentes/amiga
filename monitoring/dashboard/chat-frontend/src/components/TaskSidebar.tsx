import React, { useState, useEffect } from 'react';
import './TaskSidebar.css';

interface Task {
  task_id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'stopped';
  created_at: string;
  updated_at: string;
  model: string;
  agent_type: string;
  last_agent_type?: string;
  result?: string;
  error?: string;
  tool_usage?: ToolUsage[];
}

interface ToolUsage {
  tool_name: string;
  timestamp: string;
  duration_ms?: number;
  success: boolean;
  error?: string;
}

interface TaskSidebarProps {
  visible: boolean;
}

/**
 * TaskSidebar Component
 * =====================
 *
 * Displays active and completed background tasks with real-time tool usage.
 *
 * VISIBILITY BEHAVIOR (Progressive Reveal Pattern):
 * - Hidden on landing page (home screen with centered input)
 * - Appears when user types anything into input box (chatViewActive=true)
 * - Controlled by App.tsx via `visible` prop
 *
 * See docs/CHAT_INTERFACE_UX.md for complete navigation pattern documentation.
 */
export const TaskSidebar: React.FC<TaskSidebarProps> = ({ visible }) => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [connected, setConnected] = useState(false);
  const [filter, setFilter] = useState<'active' | 'completed'>('active');
  const [, setTick] = useState(0); // Force re-render for time updates

  // Update time display every 30 seconds
  useEffect(() => {
    if (!visible) return;

    const interval = setInterval(() => {
      setTick(prev => prev + 1);
    }, 30000);

    return () => clearInterval(interval);
  }, [visible]);

  useEffect(() => {
    if (!visible) return;

    let eventSource: EventSource | null = null;

    const connectSSE = () => {
      try {
        // Use same base URL as WebSocket (respects REACT_APP_SOCKET_URL)
        const baseUrl = process.env.REACT_APP_SOCKET_URL || window.location.origin;
        const sseUrl = `${baseUrl}/api/stream/metrics?hours=24`;
        eventSource = new EventSource(sseUrl);

        eventSource.onopen = () => {
          console.log('Task sidebar connected to SSE');
          setConnected(true);
        };

        eventSource.onmessage = (event) => {
          try {
            // Skip empty or heartbeat messages
            if (!event.data || event.data.trim() === '' || event.data.trim() === ': heartbeat') {
              return;
            }
            
            const data = JSON.parse(event.data);
            // SSE sends: { overview: { task_statistics: { recent_24h: { tasks: [...] } } } }
            const allTasks = data?.overview?.task_statistics?.recent_24h?.tasks;
            if (allTasks && Array.isArray(allTasks)) {
              setTasks(allTasks);
            }
          } catch (error) {
            console.error('Failed to parse SSE data:', error);
          }
        };

        eventSource.onerror = (error) => {
          console.error('SSE connection error:', error);
          console.error('EventSource readyState:', eventSource?.readyState);
          setConnected(false);
          eventSource?.close();

          // Retry connection after 5 seconds
          setTimeout(connectSSE, 5000);
        };
      } catch (error) {
        console.error('Failed to create EventSource:', error);
        setConnected(false);
      }
    };

    connectSSE();

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [visible]);

  const formatTaskId = (taskId: string) => {
    // Extract short ID (first 6 chars after "task_")
    if (taskId.startsWith('task_')) {
      return taskId.substring(5, 11);
    }
    return taskId.substring(0, 6);
  };

  const formatTimestamp = (timestamp: string) => {
    if (!timestamp) {
      return 'unknown';
    }

    try {
      // Parse ISO timestamp - handle SQLite format "2025-10-16 23:11:15.782996"
      // or ISO format "2025-10-16T23:11:15.782996"
      // Backend stores timestamps in LOCAL timezone without timezone suffix
      let isoTimestamp = timestamp.trim();

      // Replace space with 'T' if needed for proper ISO format
      isoTimestamp = isoTimestamp.replace(' ', 'T');

      // Parse as local time (backend sends local timestamps without timezone info)
      // Do NOT add 'Z' as that would incorrectly interpret as UTC
      const date = new Date(isoTimestamp);

      // Validate date
      if (isNaN(date.getTime())) {
        console.error('Invalid timestamp:', timestamp, 'parsed as:', isoTimestamp);
        return 'unknown';
      }

      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffSecs = Math.floor(diffMs / 1000);
      const diffMins = Math.floor(diffSecs / 60);
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);

      // Handle negative differences (future timestamps - shouldn't happen but be defensive)
      if (diffMs < 0) {
        console.warn('Future timestamp detected:', timestamp);
        return 'just now';
      }

      if (diffSecs < 10) return 'just now';
      if (diffMins < 1) return `${diffSecs}s ago`;
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch (error) {
      console.error('Error formatting timestamp:', timestamp, error);
      return 'unknown';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return '#6a9fb5';
      case 'pending':
        return '#888';
      case 'completed':
        return '#7cb342';
      case 'failed':
        return '#f87171';
      case 'stopped':
        return '#888';
      default:
        return '#888';
    }
  };

  const handleTaskClick = (taskId: string) => {
    // Navigate to monitoring dashboard with task highlighted and referrer info
    window.location.href = `/dashboard#${taskId}?ref=chat`;
  };

  const handleMarkFixed = async (taskId: string, event: React.MouseEvent) => {
    // Stop propagation to prevent task click
    event.stopPropagation();
    
    try {
      const response = await fetch(`/api/tasks/${taskId}/mark-fixed`, {
        method: 'POST',
      });
      
      if (response.ok) {
        console.log(`Task ${taskId} marked as fixed`);
        // Task list will update via SSE
      } else {
        const error = await response.json();
        console.error('Failed to mark task as fixed:', error);
      }
    } catch (error) {
      console.error('Error marking task as fixed:', error);
    }
  };

  if (!visible) return null;

  // Helper function to get the most recent activity timestamp for a task
  const getLastActivityTimestamp = (task: Task): number => {
    // Start with updated_at timestamp
    let latestTimestamp = new Date(task.updated_at.replace(' ', 'T')).getTime();

    // Check if there's any tool usage with a more recent timestamp
    if (task.tool_usage && task.tool_usage.length > 0) {
      const lastToolTimestamp = new Date(
        task.tool_usage[task.tool_usage.length - 1].timestamp.replace(' ', 'T')
      ).getTime();

      // Use the most recent timestamp between updated_at and last tool usage
      latestTimestamp = Math.max(latestTimestamp, lastToolTimestamp);
    }

    return latestTimestamp;
  };

  // Filter tasks based on selected filter
  const filteredTasks = tasks
    .filter((task) => {
      if (filter === 'active') {
        return task.status === 'running' || task.status === 'pending';
      } else {
        return task.status === 'completed' || task.status === 'failed' || task.status === 'stopped';
      }
    })
    .sort((a, b) => {
      // Sort completed tasks by most recent activity (descending - newest first)
      if (filter === 'completed') {
        return getLastActivityTimestamp(b) - getLastActivityTimestamp(a);
      }
      // Keep original order for active tasks
      return 0;
    });

  // Calculate counts from full task list (not filtered)
  const activeCount = tasks.filter(t => t.status === 'running' || t.status === 'pending').length;
  const completedCount = tasks.filter(t => t.status === 'completed' || t.status === 'failed' || t.status === 'stopped').length;

  return (
    <div className="task-sidebar">
      <div className="sidebar-header">
        <h3>Tasks</h3>
        <span className={`connection-indicator ${connected ? 'connected' : 'disconnected'}`}>
          {connected ? '●' : '○'}
        </span>
      </div>

      <div className="filter-toggle">
        <button
          className={`filter-button ${filter === 'active' ? 'active' : ''}`}
          onClick={() => setFilter('active')}
        >
          Active ({activeCount})
        </button>
        <button
          className={`filter-button ${filter === 'completed' ? 'active' : ''}`}
          onClick={() => setFilter('completed')}
        >
          Completed ({completedCount})
        </button>
      </div>

      <div className="sidebar-content">
        {filteredTasks.length === 0 ? (
          <div className="empty-state">
            <p>No {filter} tasks</p>
          </div>
        ) : (
          <div className="tasks-list">
            {filteredTasks.map((task) => (
              <div
                key={task.task_id}
                className={`task-item ${task.status}`}
                onClick={() => handleTaskClick(task.task_id)}
                role="button"
                tabIndex={0}
                onKeyPress={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    handleTaskClick(task.task_id);
                  }
                }}
              >
                <div className="task-header">
                  <span
                    className="task-id"
                    style={{ color: getStatusColor(task.status) }}
                  >
                    #{formatTaskId(task.task_id)}
                  </span>
                  <span className="task-status" style={{ color: getStatusColor(task.status) }}>
                    {task.status}
                  </span>
                </div>
                <div className="task-description">{task.description}</div>
                <div className="task-meta">
                  <span className="task-agent">{task.last_agent_type || task.agent_type}</span>
                  <span className="task-time">{formatTimestamp(task.updated_at)}</span>
                </div>
                {task.tool_usage && task.tool_usage.length > 0 && (
                  <div className="task-tools">
                    <span className="tools-label">Tools:</span>
                    <span className="tools-count">{task.tool_usage.length}</span>
                  </div>
                )}
                {task.status === 'failed' && (
                  <div className="task-actions">
                    <button
                      className="mark-fixed-button"
                      onClick={(e) => handleMarkFixed(task.task_id, e)}
                      title="Mark this task as fixed"
                    >
                      Mark as Fixed
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
