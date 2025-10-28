import React, { useState, useEffect, useRef } from 'react';
import './TaskDetailModal.css';

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
  activity_log?: ActivityLogEntry[];
}

interface ActivityLogEntry {
  timestamp: string;
  message: string;
}

interface ToolCall {
  tool: string;
  timestamp: string;
  duration_ms?: number;
  success: boolean;
  error?: string;
  parameters?: any;
  output_preview?: string;
}

interface TaskDocument {
  filename: string;
  size: number;
  modified: string;
  content?: string;
}

interface TaskDetailModalProps {
  taskId: string | null;
  onClose: () => void;
}

export const TaskDetailModal: React.FC<TaskDetailModalProps> = ({ taskId, onClose }) => {
  const [task, setTask] = useState<Task | null>(null);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [documents, setDocuments] = useState<TaskDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [terminalExpanded, setTerminalExpanded] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const terminalScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!taskId) return;

    const fetchTaskDetails = async () => {
      setLoading(true);
      setError(null);

      try {
        // Fetch basic task info
        const taskResponse = await fetch(`/api/tasks/${taskId}`);
        if (!taskResponse.ok) throw new Error('Failed to fetch task details');
        const taskData = await taskResponse.json();
        setTask(taskData);

        // Fetch tool usage
        const toolResponse = await fetch(`/api/tasks/${taskId}/tool-usage`);
        if (toolResponse.ok) {
          const toolData = await toolResponse.json();
          setToolCalls(toolData.tool_calls || []);
        }

        // Fetch documents if completed
        if (taskData.status === 'completed') {
          const docsResponse = await fetch(`/api/tasks/${taskId}/documents`);
          if (docsResponse.ok) {
            const docsData = await docsResponse.json();
            setDocuments(docsData.documents || []);
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchTaskDetails();

    // Poll for updates if task is running
    let interval: NodeJS.Timeout | null = null;
    if (task?.status === 'running' || task?.status === 'pending') {
      interval = setInterval(fetchTaskDetails, 2000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [taskId, task?.status]);

  // Auto-scroll terminal
  useEffect(() => {
    if (autoScroll && terminalScrollRef.current && terminalExpanded) {
      terminalScrollRef.current.scrollTop = terminalScrollRef.current.scrollHeight;
    }
  }, [toolCalls, autoScroll, terminalExpanded]);

  // Handle ESC key
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  const handleStopTask = async () => {
    if (!taskId) return;
    try {
      const response = await fetch(`/api/tasks/${taskId}/stop`, { method: 'POST' });
      if (response.ok) {
        // Refresh task details
        const taskData = await response.json();
        setTask(taskData);
      }
    } catch (err) {
      console.error('Failed to stop task:', err);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    try {
      const date = new Date(timestamp.replace(' ', 'T'));
      return date.toLocaleString();
    } catch {
      return timestamp;
    }
  };

  const formatRelativeTime = (timestamp: string) => {
    try {
      const date = new Date(timestamp.replace(' ', 'T'));
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffSecs = Math.floor(diffMs / 1000);
      const diffMins = Math.floor(diffSecs / 60);
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);

      if (diffSecs < 10) return 'just now';
      if (diffMins < 1) return `${diffSecs}s ago`;
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch {
      return 'unknown';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return '#6a9fb5';
      case 'pending': return '#888';
      case 'completed': return '#7cb342';
      case 'failed': return '#f87171';
      case 'stopped': return '#888';
      default: return '#888';
    }
  };

  const formatStatus = (status: string) => {
    return status.charAt(0).toUpperCase() + status.slice(1);
  };

  if (!taskId) return null;

  return (
    <div className="task-detail-modal" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <button className="modal-back" onClick={onClose}>
            <span>←</span>
            <span>Back</span>
          </button>
          <div className="modal-header-info">
            <div className="modal-title">Task #{taskId.substring(0, 6)}</div>
            {task && (
              <div className="modal-subtitle">{task.description}</div>
            )}
          </div>
          {task?.status === 'running' && (
            <button className="modal-stop-btn" onClick={handleStopTask}>
              <span>⏹</span>
              <span>Stop</span>
            </button>
          )}
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          {loading && <div className="loading">Loading...</div>}
          {error && <div className="error-message">Error: {error}</div>}
          
          {task && (
            <>
              {/* Task Info */}
              <div className="task-info-section">
                <div className="task-info-item">
                  <span className="task-info-label">Status</span>
                  <span className="task-status" style={{ color: getStatusColor(task.status) }}>
                    {formatStatus(task.status)}
                  </span>
                </div>
                <div className="task-info-item">
                  <span className="task-info-label">Model</span>
                  <span>{task.model}</span>
                </div>
                <div className="task-info-item">
                  <span className="task-info-label">Agent</span>
                  <span>{task.last_agent_type || task.agent_type}</span>
                </div>
                <div className="task-info-item">
                  <span className="task-info-label">Updated</span>
                  <span>{formatRelativeTime(task.updated_at)}</span>
                </div>
              </div>

              {/* Tool Execution Log */}
              {toolCalls.length > 0 && (
                <div className="section">
                  <div className="terminal-container">
                    <div className="terminal-header" onClick={() => setTerminalExpanded(!terminalExpanded)}>
                      <div className="terminal-title">
                        <span className={`terminal-toggle ${terminalExpanded ? 'expanded' : ''}`}>▼</span>
                        <span>Tool Execution Log</span>
                        <span style={{ color: '#484f58' }}> • </span>
                        <span>{toolCalls.length} calls</span>
                      </div>
                      <div className="terminal-controls" onClick={(e) => e.stopPropagation()}>
                        {task.status === 'running' && (
                          <button className="terminal-btn terminal-btn-danger" onClick={handleStopTask}>
                            ⏹ Stop Task
                          </button>
                        )}
                        <button
                          className={`terminal-btn ${autoScroll ? 'active' : ''}`}
                          onClick={() => setAutoScroll(!autoScroll)}
                        >
                          ↓ Auto-scroll
                        </button>
                      </div>
                    </div>
                    {terminalExpanded && (
                      <div className="terminal-body" ref={terminalScrollRef}>
                        {toolCalls.slice(-50).map((call, index) => (
                          <div key={index} className="tool-call-item">
                            <div className="tool-call-header">
                              <span className="tool-call-name">{call.tool}</span>
                              <span className="tool-call-time">{formatTimestamp(call.timestamp)}</span>
                            </div>
                            {call.parameters && (
                              <div className="tool-call-params">
                                <pre>{JSON.stringify(call.parameters, null, 2)}</pre>
                              </div>
                            )}
                            {call.output_preview && (
                              <div className="tool-call-output">
                                {call.output_preview}
                              </div>
                            )}
                            {call.error && (
                              <div className="tool-call-error">
                                ❌ {call.error}
                              </div>
                            )}
                            {call.duration_ms && (
                              <div className="tool-call-duration">
                                ⏱️ {call.duration_ms}ms
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Activity Log */}
              {task.activity_log && task.activity_log.length > 0 && (
                <div className="section">
                  <h3 className="section-title">Activity Log</h3>
                  <div className="activity-log">
                    {task.activity_log.slice().reverse().map((entry, index) => (
                      <div key={index} className="activity-item">
                        <div className="activity-time">{formatTimestamp(entry.timestamp)}</div>
                        <div className="activity-message">{entry.message}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Documents */}
              {documents.length > 0 && (
                <div className="section">
                  <h3 className="section-title">Documents</h3>
                  <div className="documents-list">
                    {documents.map((doc, index) => (
                      <div key={index} className="document-item">
                        <span>📄</span>
                        <span className="document-name">{doc.filename}</span>
                        <span className="document-size">
                          {(doc.size / 1024).toFixed(1)} KB
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Error Message */}
              {task.error && (
                <div className="section">
                  <h3 className="section-title">Error</h3>
                  <div className="error-box">
                    {task.error}
                  </div>
                </div>
              )}

              {/* Result */}
              {task.result && (
                <div className="section">
                  <h3 className="section-title">Result</h3>
                  <div className="result-box">
                    {task.result}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
