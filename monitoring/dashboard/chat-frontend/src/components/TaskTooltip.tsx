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
  context?: string; // Full prompt/context for the task
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

  // Fetch task details and tool calls
  useEffect(() => {
    const fetchTaskData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch task details
        const taskResponse = await fetch(`/api/tasks/${taskId}`);
        if (!taskResponse.ok) {
          if (taskResponse.status === 404) {
            setError('Task not found');
          } else {
            setError('Failed to load task details');
          }
          return;
        }
        const taskData = await taskResponse.json();
        setTaskDetails(taskData);
      } catch (err) {
        console.error('Error fetching task data:', err);
        setError('Failed to load task details');
      } finally {
        setLoading(false);
      }
    };

    fetchTaskData();
  }, [taskId]);

  // Calculate tooltip position
  useEffect(() => {
    if (!tooltipRef.current || !targetElement) return;

    const calculatePosition = () => {
      const targetRect = targetElement.getBoundingClientRect();
      const tooltipRect = tooltipRef.current!.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      // Position below the target with 8px gap
      let top = targetRect.bottom + 8;
      let left = targetRect.left;

      // Center tooltip under the task ID if tooltip is wider than the link
      if (tooltipRect.width > targetRect.width) {
        left = targetRect.left + (targetRect.width / 2) - (tooltipRect.width / 2);
      }

      // If tooltip goes off right edge, align to right edge of viewport
      if (left + tooltipRect.width > viewportWidth - 16) {
        left = viewportWidth - tooltipRect.width - 16;
      }

      // If tooltip goes off left edge, align to left edge of viewport
      if (left < 16) {
        left = 16;
      }

      // If tooltip goes off bottom edge, position above the target
      if (top + tooltipRect.height > viewportHeight - 16) {
        top = targetRect.top - tooltipRect.height - 8;
      }

      // If positioning above would go off top edge, position below anyway and let it scroll
      if (top < 16) {
        top = targetRect.bottom + 8;
      }

      setPosition({ top, left });
    };

    // Initial calculation with slight delay to ensure DOM is ready
    const initialTimer = setTimeout(calculatePosition, 10);

    // Recalculate on scroll or resize
    window.addEventListener('scroll', calculatePosition, true);
    window.addEventListener('resize', calculatePosition);

    return () => {
      clearTimeout(initialTimer);
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
      className="task-tooltip task-tooltip-compact"
      style={{ top: `${position.top}px`, left: `${position.left}px` }}
    >
      {loading ? (
        <div className="task-tooltip-loading">
          <div className="loading-spinner" />
        </div>
      ) : error ? (
        <div className="task-tooltip-error">
          <span className="error-icon">⚠</span>
          <span>{error}</span>
        </div>
      ) : taskDetails ? (
        <div className="task-tooltip-content">
          <div
            className="task-status-badge"
            style={{ backgroundColor: getStatusColor(taskDetails.status) }}
          >
            <span className="status-icon">{getStatusIcon(taskDetails.status)}</span>
            <span className="status-text">{taskDetails.status}</span>
          </div>

          <div className="task-tooltip-actions">
            <button className="tooltip-button add-to-chat" onClick={handleAddToChat}>
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
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
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                <path
                  d="M8 3.5c-3.5 0-6.5 3-6.5 4.5s3 4.5 6.5 4.5 6.5-3 6.5-4.5-3-4.5-6.5-4.5z"
                  stroke="currentColor"
                  strokeWidth="1.5"
                />
                <circle cx="8" cy="8" r="2" fill="currentColor" />
              </svg>
              Open
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
};
