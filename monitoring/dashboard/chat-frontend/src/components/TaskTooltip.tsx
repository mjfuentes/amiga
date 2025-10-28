import React, { useState, useEffect, useRef } from 'react';
import './TaskTooltip.css';

interface TaskDetails {
  task_id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'stopped';
  created_at: string;
  updated_at: string;
  error?: string;
  result?: string;
}

interface TaskTooltipProps {
  taskId: string;
  targetElement: HTMLElement;
  onAddToChat: (taskRef: string) => void;
  onClose: () => void;
}

export const TaskTooltip: React.FC<TaskTooltipProps> = ({
  taskId,
  targetElement,
  onAddToChat,
  onClose,
}) => {
  const [taskDetails, setTaskDetails] = useState<TaskDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [position, setPosition] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const tooltipRef = useRef<HTMLDivElement>(null);

  // Fetch task details
  useEffect(() => {
    const fetchTaskDetails = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch(`/api/tasks/${taskId}`);

        if (!response.ok) {
          if (response.status === 404) {
            setError('Task not found');
          } else {
            setError('Failed to load task details');
          }
          return;
        }

        const data = await response.json();
        setTaskDetails(data);
      } catch (err) {
        console.error('Error fetching task details:', err);
        setError('Failed to load task details');
      } finally {
        setLoading(false);
      }
    };

    fetchTaskDetails();
  }, [taskId]);

  // Calculate tooltip position
  useEffect(() => {
    if (!tooltipRef.current || !targetElement) return;

    const calculatePosition = () => {
      const targetRect = targetElement.getBoundingClientRect();
      const tooltipRect = tooltipRef.current!.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      // Try to position below the target
      let top = targetRect.bottom + 8;
      let left = targetRect.left;

      // If tooltip goes off right edge, align to right
      if (left + tooltipRect.width > viewportWidth - 16) {
        left = viewportWidth - tooltipRect.width - 16;
      }

      // If tooltip goes off bottom edge, position above
      if (top + tooltipRect.height > viewportHeight - 16) {
        top = targetRect.top - tooltipRect.height - 8;
      }

      // Ensure minimum left position
      left = Math.max(16, left);

      setPosition({ top, left });
    };

    // Initial calculation
    calculatePosition();

    // Recalculate on scroll or resize
    window.addEventListener('scroll', calculatePosition, true);
    window.addEventListener('resize', calculatePosition);

    return () => {
      window.removeEventListener('scroll', calculatePosition, true);
      window.removeEventListener('resize', calculatePosition);
    };
  }, [targetElement, loading]); // Recalculate when content loads

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        tooltipRef.current &&
        !tooltipRef.current.contains(e.target as Node) &&
        !targetElement.contains(e.target as Node)
      ) {
        onClose();
      }
    };

    // Add listener with slight delay to prevent immediate close
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 100);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [targetElement, onClose]);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleAddToChat = () => {
    onAddToChat(`#${taskId}`);
    onClose();
  };

  const formatTimestamp = (timestamp: string): string => {
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);

      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;

      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
      });
    } catch {
      return timestamp;
    }
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'running':
        return '#6a9fb5';
      case 'completed':
        return '#7cb342';
      case 'failed':
        return '#f87171';
      case 'pending':
        return '#888';
      case 'stopped':
        return '#888';
      default:
        return '#888';
    }
  };

  const getStatusIcon = (status: string): string => {
    switch (status) {
      case 'running':
        return '⏳';
      case 'completed':
        return '✓';
      case 'failed':
        return '✗';
      case 'pending':
        return '○';
      case 'stopped':
        return '■';
      default:
        return '?';
    }
  };

  return (
    <div
      ref={tooltipRef}
      className="task-tooltip"
      style={{ top: `${position.top}px`, left: `${position.left}px` }}
    >
      {loading ? (
        <div className="task-tooltip-loading">
          <div className="loading-spinner" />
          <span>Loading task details...</span>
        </div>
      ) : error ? (
        <div className="task-tooltip-error">
          <span className="error-icon">⚠</span>
          <span>{error}</span>
        </div>
      ) : taskDetails ? (
        <div className="task-tooltip-content">
          <div className="task-tooltip-header">
            <div className="task-id-section">
              <span className="task-id-label">Task ID:</span>
              <code className="task-id-value">#{taskId}</code>
            </div>
            <div
              className="task-status-badge"
              style={{ backgroundColor: getStatusColor(taskDetails.status) }}
            >
              <span className="status-icon">{getStatusIcon(taskDetails.status)}</span>
              <span className="status-text">{taskDetails.status}</span>
            </div>
          </div>

          <div className="task-tooltip-body">
            <div className="task-field">
              <span className="field-label">Description:</span>
              <p className="field-value description">{taskDetails.description}</p>
            </div>

            <div className="task-timestamps">
              <div className="task-field timestamp">
                <span className="field-label">Created:</span>
                <span className="field-value">{formatTimestamp(taskDetails.created_at)}</span>
              </div>
              <div className="task-field timestamp">
                <span className="field-label">Updated:</span>
                <span className="field-value">{formatTimestamp(taskDetails.updated_at)}</span>
              </div>
            </div>

            {taskDetails.error && (
              <div className="task-field error-field">
                <span className="field-label">Error:</span>
                <p className="field-value error-message">{taskDetails.error}</p>
              </div>
            )}

            {taskDetails.result && !taskDetails.error && (
              <div className="task-field result-field">
                <span className="field-label">Result:</span>
                <p className="field-value result-message">{taskDetails.result}</p>
              </div>
            )}
          </div>

          <div className="task-tooltip-actions">
            <button className="tooltip-button add-to-chat" onClick={handleAddToChat}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path
                  d="M8 2v12M2 8h12"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
              Add to chat
            </button>
            <button className="tooltip-button view-details" onClick={() => {
              window.location.href = `/dashboard#${taskId}?ref=chat`;
            }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path
                  d="M8 3.5c-3.5 0-6.5 3-6.5 4.5s3 4.5 6.5 4.5 6.5-3 6.5-4.5-3-4.5-6.5-4.5z"
                  stroke="currentColor"
                  strokeWidth="1.5"
                />
                <circle cx="8" cy="8" r="2" fill="currentColor" />
              </svg>
              View in dashboard
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
};
