import React, { useState, useEffect, useRef } from 'react';
import './MonitoringDashboard.css';

interface MonitoringDashboardProps {
  onBack: () => void;
}

interface Task {
  task_id: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
  agent_type?: string;
  model?: string;
  error?: string;
  tool_calls?: any[];
}

interface MetricsData {
  overview: {
    task_statistics: {
      total: number;
      by_status: Record<string, number>;
      running_tasks: Task[];
    };
    tool_usage: {
      total_calls: number;
      success_rate: number;
      by_tool: Record<string, number>;
      total_cost_24h: number;
      by_model: Record<string, number>;
    };
    system_health: {
      recent_errors: any[];
    };
  };
  activity: any[];
  sessions: any[];
}

export const MonitoringDashboard: React.FC<MonitoringDashboardProps> = ({ onBack }) => {
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // Connect to SSE endpoint
    const connectSSE = () => {
      try {
        const eventSource = new EventSource('http://localhost:3000/api/stream/metrics?hours=24');
        eventSourceRef.current = eventSource;

        eventSource.onopen = () => {
          console.log('SSE connection established');
          setLoading(false);
          setError(null);
        };

        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            console.log('Received SSE data:', data);
            setMetrics(data);
          } catch (err) {
            console.error('Failed to parse SSE data:', err);
          }
        };

        eventSource.onerror = (err) => {
          console.error('SSE connection error:', err);
          setError('Connection lost. Retrying...');
          eventSource.close();

          // Retry connection after 3 seconds
          setTimeout(connectSSE, 3000);
        };
      } catch (err) {
        console.error('Failed to connect SSE:', err);
        setError('Failed to connect to server');
        setLoading(false);
      }
    };

    connectSSE();

    // Cleanup on unmount
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    if (isToday) {
      return date.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      });
    }
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  };

  const formatCost = (cost: number) => {
    return `$${cost.toFixed(4)}`;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'status-running';
      case 'completed':
        return 'status-completed';
      case 'failed':
        return 'status-failed';
      case 'stopped':
        return 'status-stopped';
      default:
        return 'status-pending';
    }
  };

  if (loading) {
    return (
      <div className="monitoring-dashboard">
        <div className="dashboard-header">
          <button className="back-button" onClick={onBack}>
            <span>←</span>
            <span>Back to Chat</span>
          </button>
          <h1>Monitoring Dashboard</h1>
        </div>
        <div className="dashboard-loading">
          <div className="loading-spinner"></div>
          <p>Connecting to monitoring service...</p>
        </div>
      </div>
    );
  }

  if (error && !metrics) {
    return (
      <div className="monitoring-dashboard">
        <div className="dashboard-header">
          <button className="back-button" onClick={onBack}>
            <span>←</span>
            <span>Back to Chat</span>
          </button>
          <h1>Monitoring Dashboard</h1>
        </div>
        <div className="dashboard-error">
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="monitoring-dashboard">
      <div className="dashboard-header">
        <button className="back-button" onClick={onBack}>
          <span>←</span>
          <span>Back to Chat</span>
        </button>
        <h1>Monitoring Dashboard</h1>
        {error && <div className="connection-status error">{error}</div>}
      </div>

      <div className="dashboard-content">
        {/* Stats Grid */}
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Total Tasks</div>
            <div className="stat-value">{metrics?.overview.task_statistics.total || 0}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Success Rate</div>
            <div className="stat-value">
              {metrics?.overview.tool_usage.success_rate?.toFixed(1) || 0}%
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">24h Cost</div>
            <div className="stat-value">
              {formatCost(metrics?.overview.tool_usage.total_cost_24h || 0)}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Tool Calls</div>
            <div className="stat-value">{metrics?.overview.tool_usage.total_calls || 0}</div>
          </div>
        </div>

        {/* Running Tasks */}
        <div className="dashboard-section">
          <h2>Active Tasks</h2>
          <div className="tasks-list">
            {!metrics?.overview.task_statistics.running_tasks ||
            metrics.overview.task_statistics.running_tasks.length === 0 ? (
              <div className="empty-state">No active tasks</div>
            ) : (
              metrics.overview.task_statistics.running_tasks.map(task => (
                  <div key={task.task_id} className="task-card">
                    <div className="task-header">
                      <div className="task-info">
                        <div className="task-title">{task.description}</div>
                        <div className="task-meta">
                          <span className={`task-status ${getStatusColor(task.status)}`}>
                            {task.status}
                          </span>
                          <span className="task-time">{formatTime(task.created_at)}</span>
                          {task.agent_type && (
                            <span className="task-agent">{task.agent_type}</span>
                          )}
                        </div>
                      </div>
                    </div>
                    {task.tool_calls && task.tool_calls.length > 0 && (
                      <div className="tool-calls">
                        <div className="tool-calls-header">Recent Tool Calls</div>
                        <div className="tool-calls-list">
                          {task.tool_calls.slice(-5).map((call: any, idx: number) => (
                            <div key={idx} className="tool-call-item">
                              <span className="tool-name">{call.tool}</span>
                              <span className={`tool-status ${call.success ? 'success' : 'error'}`}>
                                {call.success ? '✓' : '✗'}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))
            )}
          </div>
        </div>

        {/* Recent Errors */}
        {metrics?.overview.system_health.recent_errors &&
          metrics.overview.system_health.recent_errors.length > 0 && (
            <div className="dashboard-section">
              <h2>Recent Errors</h2>
              <div className="errors-list">
                {metrics.overview.system_health.recent_errors.slice(0, 5).map((error: any, idx: number) => (
                <div key={idx} className="error-card">
                  <div className="error-header">
                    <span className="error-task">{error.task_id || 'Unknown'}</span>
                    <span className="error-time">{formatTime(error.timestamp)}</span>
                  </div>
                  <div className="error-message">{error.error || error.message}</div>
                </div>
                ))}
              </div>
            </div>
          )}

        {/* Cost Breakdown */}
        {metrics?.overview.tool_usage.by_model &&
          Object.keys(metrics.overview.tool_usage.by_model).length > 0 && (
            <div className="dashboard-section">
              <h2>Cost by Model (24h)</h2>
              <div className="cost-breakdown">
                {Object.entries(metrics.overview.tool_usage.by_model).map(([model, cost]) => (
                <div key={model} className="cost-item">
                  <span className="cost-model">{model}</span>
                  <span className="cost-value">{formatCost(cost as number)}</span>
                </div>
                ))}
              </div>
            </div>
          )}

        {/* Tool Usage */}
        {metrics?.overview.tool_usage.by_tool &&
          Object.keys(metrics.overview.tool_usage.by_tool).length > 0 && (
            <div className="dashboard-section">
              <h2>Tool Usage</h2>
              <div className="tool-usage">
                {Object.entries(metrics.overview.tool_usage.by_tool)
                  .sort(([, a], [, b]) => (b as number) - (a as number))
                  .slice(0, 10)
                  .map(([tool, count]) => (
                    <div key={tool} className="tool-usage-item">
                      <span className="tool-usage-name">{tool}</span>
                      <div className="tool-usage-bar">
                        <div
                          className="tool-usage-fill"
                          style={{
                            width: `${
                              ((count as number) / metrics.overview.tool_usage.total_calls) * 100
                            }%`
                          }}
                        />
                      </div>
                      <span className="tool-usage-count">{count}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
      </div>
    </div>
  );
};
