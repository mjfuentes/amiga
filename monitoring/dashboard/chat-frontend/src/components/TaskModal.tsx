import React, { useState, useEffect, useRef, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';
import {
  TaskDetails,
  ToolCallDetail,
  TaskDocument,
  TaskScreenshot,
  WorkflowStep,
} from '../types/task';
import './TaskModal.css';

const SOCKET_URL = process.env.REACT_APP_SOCKET_URL || 'http://localhost:3000';

interface TaskModalProps {
  taskId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export const TaskModal: React.FC<TaskModalProps> = ({ taskId, isOpen, onClose }) => {
  const [taskDetails, setTaskDetails] = useState<TaskDetails | null>(null);
  const [toolCalls, setToolCalls] = useState<ToolCallDetail[]>([]);
  const [documents, setDocuments] = useState<TaskDocument[]>([]);
  const [screenshots, setScreenshots] = useState<TaskScreenshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [expandedTools, setExpandedTools] = useState<Set<number>>(new Set());
  const [lightboxImage, setLightboxImage] = useState<{
    url: string;
    index: number;
  } | null>(null);

  const socketRef = useRef<Socket | null>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  // Fetch task data
  const fetchTaskData = useCallback(async () => {
    if (!taskId) return;

    try {
      setLoading(true);
      setError(null);

      // Fetch task details
      const taskResponse = await fetch(`${SOCKET_URL}/api/tasks/${taskId}`);
      if (!taskResponse.ok) {
        throw new Error(taskResponse.status === 404 ? 'Task not found' : 'Failed to load task');
      }
      const taskData = await taskResponse.json();
      setTaskDetails(taskData);

      // Fetch tool usage
      const toolResponse = await fetch(`${SOCKET_URL}/api/tasks/${taskId}/tool-usage`);
      if (toolResponse.ok) {
        const toolData = await toolResponse.json();
        setToolCalls(toolData.tool_calls || []);
      }

      // Fetch documents
      const docsResponse = await fetch(`${SOCKET_URL}/api/tasks/${taskId}/documents`);
      if (docsResponse.ok) {
        const docsData = await docsResponse.json();
        setDocuments(docsData.documents || []);
      }

      // Fetch screenshots
      const screenshotsResponse = await fetch(`${SOCKET_URL}/api/tasks/${taskId}/screenshots`);
      if (screenshotsResponse.ok) {
        const screenshotsData = await screenshotsResponse.json();
        setScreenshots(screenshotsData.screenshots || []);
      }
    } catch (err) {
      console.error('Error fetching task data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load task data');
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  // Setup Socket.IO for real-time updates
  useEffect(() => {
    if (!isOpen || !taskId) return;

    const socket = io(SOCKET_URL, {
      transports: ['polling', 'websocket'],
    });

    socket.on('connect', () => {
      console.log('TaskModal: Connected to Socket.IO');
    });

    socket.on('tool_execution', (data: any) => {
      if (data.task_id === taskId) {
        console.log('TaskModal: Tool execution update', data);
        // Refresh tool usage
        fetch(`${SOCKET_URL}/api/tasks/${taskId}/tool-usage`)
          .then((res) => res.json())
          .then((toolData) => setToolCalls(toolData.tool_calls || []))
          .catch(console.error);
      }
    });

    socket.on('task_stopped', (data: any) => {
      if (data.task_id === taskId) {
        console.log('TaskModal: Task stopped', data);
        fetchTaskData();
      }
    });

    socketRef.current = socket;

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [isOpen, taskId, fetchTaskData]);

  // Fetch data when modal opens
  useEffect(() => {
    if (isOpen && taskId) {
      fetchTaskData();
    }
  }, [isOpen, taskId, fetchTaskData]);

  // Handle Escape key to close
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        if (lightboxImage) {
          setLightboxImage(null);
        } else {
          onClose();
        }
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, lightboxImage, onClose]);

  // Stop task
  const handleStopTask = async () => {
    if (!taskId || actionLoading) return;

    try {
      setActionLoading('stop');
      const response = await fetch(`${SOCKET_URL}/api/tasks/${taskId}/stop`, {
        method: 'POST',
      });

      if (response.ok) {
        await fetchTaskData();
      } else {
        throw new Error('Failed to stop task');
      }
    } catch (err) {
      console.error('Error stopping task:', err);
      alert('Failed to stop task');
    } finally {
      setActionLoading(null);
    }
  };

  // Revert task
  const handleRevertTask = async () => {
    if (!taskId || actionLoading) return;

    if (!window.confirm('Create a new task to revert the changes made in this task?')) {
      return;
    }

    try {
      setActionLoading('revert');
      const response = await fetch(`${SOCKET_URL}/api/tasks/${taskId}/revert`, {
        method: 'POST',
      });

      if (response.ok) {
        const data = await response.json();
        alert(`Revert task created: ${data.task_id}`);
        onClose();
      } else {
        throw new Error('Failed to create revert task');
      }
    } catch (err) {
      console.error('Error reverting task:', err);
      alert('Failed to create revert task');
    } finally {
      setActionLoading(null);
    }
  };

  // Mark task as fixed
  const handleMarkFixed = async () => {
    if (!taskId || actionLoading) return;

    try {
      setActionLoading('mark-fixed');
      const response = await fetch(`${SOCKET_URL}/api/tasks/${taskId}/mark-fixed`, {
        method: 'POST',
      });

      if (response.ok) {
        await fetchTaskData();
      } else {
        throw new Error('Failed to mark task as fixed');
      }
    } catch (err) {
      console.error('Error marking task as fixed:', err);
      alert('Failed to mark task as fixed');
    } finally {
      setActionLoading(null);
    }
  };

  // Toggle tool expansion
  const toggleToolExpansion = (index: number) => {
    setExpandedTools((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index);
      } else {
        newSet.add(index);
      }
      return newSet;
    });
  };

  // Open lightbox
  const openLightbox = (url: string, index: number) => {
    setLightboxImage({ url, index });
  };

  // Navigate lightbox
  const navigateLightbox = (direction: number) => {
    if (!lightboxImage || screenshots.length === 0) return;

    let newIndex = lightboxImage.index + direction;
    if (newIndex < 0) newIndex = screenshots.length - 1;
    if (newIndex >= screenshots.length) newIndex = 0;

    setLightboxImage({
      url: screenshots[newIndex].url,
      index: newIndex,
    });
  };

  // Format timestamp
  const formatTimestamp = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleString();
    } catch {
      return timestamp;
    }
  };

  // Format duration
  const formatDuration = (ms: number) => {
    const roundedMs = Math.floor(ms);
    if (roundedMs < 1000) return `${roundedMs}ms`;
    if (roundedMs < 60000) return `${(roundedMs / 1000).toFixed(1)}s`;
    return `${(roundedMs / 60000).toFixed(1)}m`;
  };

  // Get status badge class
  const getStatusClass = (status: string) => {
    switch (status) {
      case 'running':
      case 'in_progress':
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

  if (!isOpen || !taskId) return null;

  return (
    <>
      <div className="task-modal-overlay" onClick={onClose}>
        <div className="task-modal" ref={modalRef} onClick={(e) => e.stopPropagation()}>
          {/* Header */}
          <div className="task-modal-header">
            <button className="task-modal-back" onClick={onClose} aria-label="Close modal">
              <span>←</span>
              <span>Back</span>
            </button>

            {loading ? (
              <div className="task-modal-header-info">
                <div className="task-modal-title">Loading...</div>
              </div>
            ) : error ? (
              <div className="task-modal-header-info">
                <div className="task-modal-title">Error</div>
                <div className="task-modal-subtitle">{error}</div>
              </div>
            ) : taskDetails ? (
              <>
                <div className="task-modal-header-info">
                  <div className="task-modal-title">{taskDetails.description}</div>
                  <div className="task-modal-subtitle">
                    <span className={`status-badge ${getStatusClass(taskDetails.status)}`}>
                      {taskDetails.status}
                    </span>
                    {taskDetails.agent_type && (
                      <span className="agent-badge">{taskDetails.agent_type}</span>
                    )}
                    {taskDetails.model && <span className="model-badge">{taskDetails.model}</span>}
                    <span className="task-id-badge">#{taskDetails.task_id}</span>
                  </div>
                </div>

                {/* Action buttons */}
                <div className="task-modal-actions">
                  {taskDetails.status === 'running' && (
                    <button
                      className="task-action-btn task-action-stop"
                      onClick={handleStopTask}
                      disabled={actionLoading === 'stop'}
                      aria-label="Stop task"
                    >
                      {actionLoading === 'stop' ? 'Stopping...' : 'Stop'}
                    </button>
                  )}
                  {taskDetails.status === 'completed' && (
                    <button
                      className="task-action-btn task-action-revert"
                      onClick={handleRevertTask}
                      disabled={actionLoading === 'revert'}
                      aria-label="Revert task changes"
                    >
                      {actionLoading === 'revert' ? 'Creating...' : '↶ Revert'}
                    </button>
                  )}
                  {taskDetails.status === 'failed' && (
                    <button
                      className="task-action-btn task-action-fix"
                      onClick={handleMarkFixed}
                      disabled={actionLoading === 'mark-fixed'}
                      aria-label="Mark task as fixed"
                    >
                      {actionLoading === 'mark-fixed' ? 'Marking...' : '✓ Mark Fixed'}
                    </button>
                  )}
                </div>
              </>
            ) : null}
          </div>

          {/* Body */}
          <div className="task-modal-body">
            {loading ? (
              <div className="task-modal-loading">
                <div className="spinner"></div>
                <p>Loading task details...</p>
              </div>
            ) : error ? (
              <div className="task-modal-error">
                <p>{error}</p>
                <button onClick={fetchTaskData}>Retry</button>
              </div>
            ) : taskDetails ? (
              <>
                {/* Workflow Progress */}
                {taskDetails.workflow && taskDetails.workflow.length > 0 && (
                  <section className="task-section">
                    <h3 className="task-section-title">📋 Planning & Workflow</h3>
                    <div className="workflow-steps">
                      {taskDetails.workflow.map((step: WorkflowStep, index: number) => (
                        <div key={index} className={`workflow-step ${getStatusClass(step.status)}`}>
                          <div className="workflow-step-header">
                            <span className="workflow-step-icon">
                              {step.status === 'completed' ? '✓' : 
                               step.status === 'in_progress' ? '⟳' :
                               step.status === 'failed' ? '✗' : '○'}
                            </span>
                            <span className="workflow-step-name">{step.name}</span>
                            <span className={`workflow-step-status ${getStatusClass(step.status)}`}>
                              {step.status}
                            </span>
                          </div>
                          {step.description && (
                            <div className="workflow-step-description">{step.description}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {/* Tool Usage */}
                {toolCalls.length > 0 && (
                  <section className="task-section">
                    <h3 className="task-section-title">🔧 Tool Execution Log</h3>
                    <div className="tool-calls-list">
                      {toolCalls.map((tool, index) => (
                        <div
                          key={index}
                          className={`tool-call ${tool.has_error ? 'tool-call-error' : ''} ${
                            tool.in_progress ? 'tool-call-running' : ''
                          }`}
                        >
                          <div
                            className="tool-call-header"
                            onClick={() => toggleToolExpansion(index)}
                          >
                            <span className="tool-call-icon">
                              {tool.in_progress ? '⟳' : tool.has_error ? '✗' : '✓'}
                            </span>
                            <span className="tool-call-name">{tool.tool_name}</span>
                            <span className="tool-call-time">{formatTimestamp(tool.timestamp)}</span>
                            {tool.duration_ms > 0 && (
                              <span className="tool-call-duration">
                                {formatDuration(tool.duration_ms)}
                              </span>
                            )}
                            <span className="tool-call-expand">
                              {expandedTools.has(index) ? '▼' : '▶'}
                            </span>
                          </div>

                          {expandedTools.has(index) && (
                            <div className="tool-call-details">
                              {tool.parameters && (
                                <div className="tool-call-section">
                                  <strong>Parameters:</strong>
                                  <pre>{JSON.stringify(tool.parameters, null, 2)}</pre>
                                </div>
                              )}
                              {tool.output_preview && (
                                <div className="tool-call-section">
                                  <strong>Output:</strong>
                                  <pre>
                                    {typeof tool.output_preview === 'string'
                                      ? tool.output_preview
                                      : JSON.stringify(tool.output_preview, null, 2)}
                                  </pre>
                                </div>
                              )}
                              {tool.error && (
                                <div className="tool-call-section tool-call-error-message">
                                  <strong>Error:</strong>
                                  <pre>{tool.error}</pre>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {/* Documents */}
                {documents.length > 0 && (
                  <section className="task-section">
                    <h3 className="task-section-title">📄 Documents</h3>
                    <div className="documents-list">
                      {documents.map((doc, index) => (
                        <div key={index} className="document-item">
                          <span className="document-icon">📄</span>
                          <span className="document-name">{doc.name}</span>
                          <span className="document-size">
                            {(doc.size / 1024).toFixed(1)} KB
                          </span>
                          <a
                            href={`${SOCKET_URL}/api/tasks/${taskId}/documents/${doc.name}`}
                            download
                            className="document-download"
                            aria-label={`Download ${doc.name}`}
                          >
                            ⬇
                          </a>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {/* Screenshots */}
                {screenshots.length > 0 && (
                  <section className="task-section">
                    <h3 className="task-section-title">📸 Screenshots</h3>
                    <div className="screenshots-grid">
                      {screenshots.map((screenshot, index) => (
                        <div
                          key={index}
                          className="screenshot-item"
                          onClick={() => openLightbox(screenshot.url, index)}
                        >
                          <img src={screenshot.url} alt={`Screenshot ${index + 1}`} />
                          <div className="screenshot-overlay">
                            <span>{screenshot.tool_name}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {/* Activity Log */}
                {taskDetails.activity_log && taskDetails.activity_log.length > 0 && (() => {
                  // Filter out "Updated planning items" entries as they're redundant with the Planning & Workflow section
                  const filteredLog = taskDetails.activity_log.filter((entry) => {
                    const message = entry.message.toLowerCase();
                    return !message.includes('updated planning items') &&
                           !message.includes('update planning items');
                  });

                  // Only render section if there are entries after filtering
                  if (filteredLog.length === 0) return null;

                  return (
                    <section className="task-section">
                      <h3 className="task-section-title">📝 Activity Log</h3>
                      <div className="activity-log">
                        {filteredLog.map((entry, index) => (
                          <div key={index} className={`activity-entry ${entry.level || 'info'}`}>
                            <span className="activity-time">{formatTimestamp(entry.timestamp)}</span>
                            <span className="activity-message">{entry.message}</span>
                          </div>
                        ))}
                      </div>
                    </section>
                  );
                })()}

                {/* Token Usage */}
                {taskDetails.token_usage && (
                  <section className="task-section">
                    <h3 className="task-section-title">💰 Token Usage</h3>
                    <div className="token-usage-grid">
                      <div className="token-usage-item">
                        <span className="token-label">Input:</span>
                        <span className="token-value">
                          {taskDetails.token_usage.input_tokens.toLocaleString()}
                        </span>
                      </div>
                      <div className="token-usage-item">
                        <span className="token-label">Output:</span>
                        <span className="token-value">
                          {taskDetails.token_usage.output_tokens.toLocaleString()}
                        </span>
                      </div>
                      <div className="token-usage-item">
                        <span className="token-label">Cache (created):</span>
                        <span className="token-value">
                          {taskDetails.token_usage.cache_creation_tokens.toLocaleString()}
                        </span>
                      </div>
                      <div className="token-usage-item">
                        <span className="token-label">Cache (read):</span>
                        <span className="token-value">
                          {taskDetails.token_usage.cache_read_tokens.toLocaleString()}
                        </span>
                      </div>
                      <div className="token-usage-item token-usage-total">
                        <span className="token-label">Total Cost:</span>
                        <span className="token-value">
                          ${taskDetails.token_usage.total_cost.toFixed(4)}
                        </span>
                      </div>
                    </div>
                  </section>
                )}
              </>
            ) : null}
          </div>
        </div>
      </div>

      {/* Lightbox for screenshots */}
      {lightboxImage && (
        <div className="lightbox" onClick={() => setLightboxImage(null)}>
          <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
            <button
              className="lightbox-close"
              onClick={() => setLightboxImage(null)}
              aria-label="Close lightbox"
            >
              ×
            </button>
            <img
              src={lightboxImage.url}
              alt={`Screenshot ${lightboxImage.index + 1}`}
              className="lightbox-image"
            />
            <div className="lightbox-nav">
              <button
                className="lightbox-nav-btn"
                onClick={() => navigateLightbox(-1)}
                aria-label="Previous screenshot"
              >
                ← Previous
              </button>
              <div className="lightbox-info">
                {lightboxImage.index + 1} / {screenshots.length}
              </div>
              <button
                className="lightbox-nav-btn"
                onClick={() => navigateLightbox(1)}
                aria-label="Next screenshot"
              >
                Next →
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
