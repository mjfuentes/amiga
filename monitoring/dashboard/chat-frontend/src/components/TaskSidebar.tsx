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

export const TaskSidebar: React.FC<TaskSidebarProps> = ({ visible }) => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!visible) return;

    let eventSource: EventSource | null = null;

    const connectSSE = () => {
      try {
        // Connect to the same SSE endpoint as the monitoring dashboard
        eventSource = new EventSource('/api/stream/metrics?hours=24');

        eventSource.onopen = () => {
          console.log('Task sidebar connected to SSE');
          setConnected(true);
        };

        eventSource.addEventListener('metrics_update', (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.tasks) {
              // Filter to show only active tasks (running or pending)
              const activeTasks = data.tasks.filter(
                (task: Task) => task.status === 'running' || task.status === 'pending'
              );
              setTasks(activeTasks);
            }
          } catch (error) {
            console.error('Failed to parse SSE data:', error);
          }
        });

        eventSource.onerror = (error) => {
          console.error('SSE connection error:', error);
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
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
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
    // Navigate to monitoring dashboard with task highlighted
    window.location.href = `http://localhost:3000/#${taskId}`;
  };

  if (!visible) return null;

  return (
    <div className="task-sidebar">
      <div className="sidebar-header">
        <h3>Active Tasks</h3>
        <span className={`connection-indicator ${connected ? 'connected' : 'disconnected'}`}>
          {connected ? '●' : '○'}
        </span>
      </div>

      <div className="sidebar-content">
        {tasks.length === 0 ? (
          <div className="empty-state">
            <p>No active tasks</p>
          </div>
        ) : (
          <div className="tasks-list">
            {tasks.map((task) => (
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
                  <span className="task-agent">{task.agent_type}</span>
                  <span className="task-time">{formatTimestamp(task.updated_at)}</span>
                </div>
                {task.tool_usage && task.tool_usage.length > 0 && (
                  <div className="task-tools">
                    <span className="tools-label">Tools:</span>
                    <span className="tools-count">{task.tool_usage.length}</span>
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
