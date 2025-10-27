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
  parameters?: string; // JSON string with subagent_type for Task tools
}

interface SubagentGroup {
  subagent_type: string;
  tools: ToolUsage[];
  start_time: string;
  end_time?: string;
}

interface TaskSidebarProps {
  visible: boolean;
}

export const TaskSidebar: React.FC<TaskSidebarProps> = ({ visible }) => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [connected, setConnected] = useState(false);
  const [filter, setFilter] = useState<'active' | 'completed'>('active');

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

        eventSource.onmessage = (event) => {
          try {
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
    // Parse ISO timestamp (handle formats like "2025-10-16T23:11:15.782996" without timezone)
    // Ensure proper ISO format by appending 'Z' if no timezone info present
    let isoTimestamp = timestamp;
    if (timestamp && !timestamp.includes('Z') && !timestamp.includes('+') && !timestamp.includes('-', 10)) {
      isoTimestamp = timestamp + 'Z';
    }

    const date = new Date(isoTimestamp);

    // Validate date
    if (isNaN(date.getTime())) {
      console.error('Invalid timestamp:', timestamp);
      return 'unknown';
    }

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
    // Navigate to monitoring dashboard with task highlighted and referrer info
    window.location.href = `/dashboard#${taskId}?ref=chat`;
  };

  // Group tools by subagent sessions
  const groupToolsBySubagent = (tools: ToolUsage[]): (SubagentGroup | ToolUsage)[] => {
    const result: (SubagentGroup | ToolUsage)[] = [];
    let currentGroup: SubagentGroup | null = null;

    for (const tool of tools) {
      // Check if this is a Task tool (subagent delegation)
      if (tool.tool_name === 'Task') {
        try {
          const params = tool.parameters ? JSON.parse(tool.parameters) : null;
          const subagentType = params?.subagent_type;

          if (subagentType) {
            // Start a new subagent group
            if (currentGroup) {
              // Close previous group
              result.push(currentGroup);
            }
            currentGroup = {
              subagent_type: subagentType,
              tools: [tool],
              start_time: tool.timestamp,
            };
          } else if (currentGroup) {
            // Task completion (no subagent_type means end of delegation)
            currentGroup.end_time = tool.timestamp;
            currentGroup.tools.push(tool);
            result.push(currentGroup);
            currentGroup = null;
          } else {
            // Standalone Task tool
            result.push(tool);
          }
        } catch (e) {
          // Invalid JSON in parameters, treat as standalone tool
          if (currentGroup) {
            currentGroup.tools.push(tool);
          } else {
            result.push(tool);
          }
        }
      } else {
        // Regular tool
        if (currentGroup) {
          // Add to current subagent group
          currentGroup.tools.push(tool);
        } else {
          // Standalone tool
          result.push(tool);
        }
      }
    }

    // Close any remaining open group
    if (currentGroup) {
      result.push(currentGroup);
    }

    return result;
  };

  const renderToolIcon = (toolName: string) => {
    const icons: { [key: string]: string } = {
      Read: '📖',
      Write: '✍️',
      Edit: '✏️',
      Bash: '⚡',
      Grep: '🔍',
      Glob: '📂',
      Task: '🔄',
    };
    return icons[toolName] || '🔧';
  };

  const renderTool = (tool: ToolUsage, index: number) => {
    const icon = renderToolIcon(tool.tool_name);
    const statusClass = tool.success ? 'success' : tool.error ? 'error' : 'pending';

    return (
      <div key={index} className={`tool-item ${statusClass}`}>
        <span className="tool-icon">{icon}</span>
        <span className="tool-name">{tool.tool_name}</span>
        {tool.duration_ms !== undefined && tool.duration_ms !== null && (
          <span className="tool-duration">{Math.round(tool.duration_ms)}ms</span>
        )}
      </div>
    );
  };

  const renderSubagentGroup = (group: SubagentGroup, index: number) => {
    return (
      <div key={`group-${index}`} className="subagent-group">
        <div className="subagent-header">
          <span className="subagent-icon">🤖</span>
          <span className="subagent-name">{group.subagent_type}</span>
          <span className="subagent-status">{group.end_time ? '✓' : '⏳'}</span>
        </div>
        <div className="subagent-tools">
          {group.tools.slice(1).map((tool, idx) => renderTool(tool, idx))}
        </div>
      </div>
    );
  };

  const renderToolUsage = (toolUsage: ToolUsage[]) => {
    const grouped = groupToolsBySubagent(toolUsage);

    return (
      <div className="tool-usage-container">
        {grouped.map((item, index) => {
          if ('subagent_type' in item) {
            // SubagentGroup
            return renderSubagentGroup(item, index);
          } else {
            // Standalone ToolUsage
            return renderTool(item, index);
          }
        })}
      </div>
    );
  };

  if (!visible) return null;

  // Filter tasks based on selected filter
  const filteredTasks = tasks.filter((task) => {
    if (filter === 'active') {
      return task.status === 'running' || task.status === 'pending';
    } else {
      return task.status === 'completed' || task.status === 'failed' || task.status === 'stopped';
    }
  });

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
          Active ({tasks.filter(t => t.status === 'running' || t.status === 'pending').length})
        </button>
        <button
          className={`filter-button ${filter === 'completed' ? 'active' : ''}`}
          onClick={() => setFilter('completed')}
        >
          Completed ({tasks.filter(t => t.status === 'completed' || t.status === 'failed' || t.status === 'stopped').length})
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
                  renderToolUsage(task.tool_usage)
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
