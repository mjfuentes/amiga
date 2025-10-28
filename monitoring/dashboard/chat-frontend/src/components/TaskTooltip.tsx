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

interface ToolCall {
  tool: string;
  timestamp: string;
  parameters: Record<string, any>;
  status: 'running' | 'completed';
  has_error: boolean;
  output_preview?: string;
  output_length?: number;
  count?: number;
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
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
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

        // Fetch tool execution logs
        const toolResponse = await fetch(`/api/tasks/${taskId}/tool-usage`);
        if (toolResponse.ok) {
          const toolData = await toolResponse.json();
          setToolCalls(toolData.tool_calls || []);
        }
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

  const escapeHtml = (text: string): string => {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  };

  const toRelativePath = (absolutePath: string): string => {
    if (!absolutePath) return '';
    const workspacePath = '/Users/matifuentes/Workspace/';
    if (absolutePath.startsWith(workspacePath)) {
      return absolutePath.substring(workspacePath.length);
    }
    return absolutePath;
  };

  const renderToolCall = (call: ToolCall) => {
    const hasError = call.has_error || false;
    const tool = call.tool || 'unknown';
    const parameters = call.parameters || {};
    const status = call.status || 'completed';

    // Parse output preview
    let previewObj: any = null;
    if (call.output_preview) {
      try {
        previewObj = JSON.parse(call.output_preview);
      } catch (e) {
        // Ignore parse errors
      }
    }

    // Build summary text with colors (matching dashboard.js renderTerminalToolCall)
    let summaryHtml = '';

    if (tool === 'Bash') {
      const cmd = parameters.command || previewObj?.command || 'command';
      const fullCmd = cmd.length > 100 ? cmd.substring(0, 100) + '...' : cmd;
      const cmdParts = fullCmd.trim().split(/\s+/);
      const cmdName = cmdParts[0] || '';
      const cmdArgs = cmdParts.slice(1).join(' ');

      // Check for git commit (special green highlighting)
      if (cmdName.toLowerCase() === 'git' && fullCmd.toLowerCase().includes('git commit')) {
        summaryHtml = `<span style="color: #3fb950;">git commit</span>`;
      } else {
        // Color based on command type
        let cmdColor = '#e6edf3';
        const cmdLower = cmdName.toLowerCase();

        if (cmdLower === 'git') cmdColor = '#58a6ff';
        else if (['ls', 'cd', 'pwd', 'mkdir', 'rm', 'cp', 'mv'].includes(cmdLower)) cmdColor = '#a0713c';
        else if (['npm', 'yarn', 'pnpm', 'pip', 'poetry'].includes(cmdLower)) cmdColor = '#d29922';
        else if (['python', 'node', 'ruby', 'go', 'java'].includes(cmdLower)) cmdColor = '#3fb950';
        else if (['docker', 'kubectl', 'terraform'].includes(cmdLower)) cmdColor = '#bc8cff';
        else if (['echo', 'cat', 'grep', 'sed', 'awk', 'find'].includes(cmdLower)) cmdColor = '#d29922';

        summaryHtml = `<span style="color: #6e7681;">Ran</span> <span style="color: ${cmdColor};">${escapeHtml(cmdName)}</span>`;
        if (cmdArgs) {
          summaryHtml += ` ${escapeHtml(cmdArgs)}`;
        }
      }
    } else if (tool === 'Read') {
      const filePath = parameters.file_path || previewObj?.filePath || previewObj?.file?.filePath || 'file';
      const relativePath = toRelativePath(filePath);
      summaryHtml = `<span style="color: #a0713c;">Read</span> <span style="color: #e8a87c;">${escapeHtml(relativePath)}</span>`;
    } else if (tool === 'Write') {
      const filePath = parameters.file_path || previewObj?.filePath || previewObj?.file?.filePath || 'file';
      const relativePath = toRelativePath(filePath);
      summaryHtml = `<span style="color: #58a6ff;">Wrote</span> <span style="color: #e8a87c;">${escapeHtml(relativePath)}</span>`;
    } else if (tool === 'Edit') {
      const filePath = parameters.file_path || previewObj?.filePath || previewObj?.file?.filePath || 'file';
      const relativePath = toRelativePath(filePath);
      summaryHtml = `<span style="color: #58a6ff;">Edited</span> <span style="color: #e8a87c;">${escapeHtml(relativePath)}</span>`;
    } else if (tool === 'Grep') {
      const pattern = parameters.pattern || previewObj?.pattern || 'pattern';
      const truncPat = pattern.length > 60 ? pattern.substring(0, 60) + '...' : pattern;
      const path = parameters.path || 'codebase';
      summaryHtml = `<span style="color: #a0713c;">Grepped</span> <span style="color: #d29922;">"${escapeHtml(truncPat)}"</span> in <span style="color: #e8a87c;">${escapeHtml(path)}</span>`;
    } else if (tool === 'Glob') {
      const pattern = parameters.pattern || previewObj?.pattern || 'pattern';
      summaryHtml = `<span style="color: #a0713c;">Searched</span> files matching <span style="color: #d29922;">"${escapeHtml(pattern)}"</span>`;
    } else if (tool === 'Task') {
      const description = parameters.description || previewObj?.description || 'task';
      const subagentType = parameters.subagent_type || previewObj?.subagent_type || '';
      let taskDesc = escapeHtml(description);
      if (subagentType) {
        taskDesc += ` <span style="color: #8b949e;">(${escapeHtml(subagentType)})</span>`;
      }
      summaryHtml = `<span style="color: #bc8cff;">Delegated</span> ${taskDesc}`;
    } else if (tool === 'TodoWrite') {
      const todos = parameters.todos || previewObj?.todos || [];
      if (todos.length > 0) {
        const completed = todos.filter((t: any) => t.status === 'completed').length;
        summaryHtml = `<span style="color: #3fb950;">Updated planning</span> <span style="color: #8b949e;">(${completed}/${todos.length} completed)</span>`;
      } else {
        summaryHtml = `<span style="color: #3fb950;">Updated planning</span>`;
      }
    } else if (tool.includes('playwright') || tool.includes('browser')) {
      // Playwright tools
      if (tool.includes('navigate')) {
        const url = parameters.url || previewObj?.url || 'page';
        const truncUrl = url.length > 60 ? url.substring(0, 60) + '...' : url;
        summaryHtml = `<span style="color: #bc8cff;">Navigated to</span> <span style="color: #58a6ff;">${escapeHtml(truncUrl)}</span>`;
      } else if (tool.includes('screenshot')) {
        const name = parameters.name || previewObj?.name || 'screenshot';
        summaryHtml = `<span style="color: #bc8cff;">Captured screenshot</span> <span style="color: #e8a87c;">${escapeHtml(name)}</span>`;
      } else if (tool.includes('click')) {
        const selector = parameters.selector || previewObj?.selector || 'element';
        summaryHtml = `<span style="color: #bc8cff;">Clicked</span> <span style="color: #d29922;">${escapeHtml(selector)}</span>`;
      } else {
        const action = tool.replace('mcp__playwright__browser_', '').replace(/_/g, ' ');
        summaryHtml = `<span style="color: #bc8cff;">Browser ${escapeHtml(action)}</span>`;
      }
    } else if (tool.startsWith('mcp__')) {
      const mcpTool = tool.replace('mcp__', '').replace(/__/g, ' » ').replace(/_/g, ' ');
      summaryHtml = `<span style="color: #bc8cff;">MCP:</span> ${escapeHtml(mcpTool)}`;
    } else {
      summaryHtml = escapeHtml(tool);
    }

    // Add timing info
    let timingHtml = '';
    if (previewObj?.duration) {
      const duration = Math.round(previewObj.duration);
      if (duration > 0) {
        timingHtml = `, ${duration}s`;
      }
    }

    // Count badge for consolidated calls
    const count = call.count || 1;
    let countBadgeHtml = '';
    if (count > 1) {
      countBadgeHtml = ` <span style="display: inline-block; background: #58a6ff; color: #0d1117; padding: 0.125rem 0.375rem; border-radius: 0.25rem; font-size: 0.75rem; font-weight: 600; margin-left: 0.375rem;">×${count}</span>`;
    }

    // Error indicator
    let errorHtml = '';
    if (hasError) {
      const errorMsg = previewObj?.error || 'error';
      errorHtml = ` <span style="color: #f85149;">• ${escapeHtml(errorMsg)}</span>`;
    }

    // Running indicator
    let runningHtml = '';
    if (status === 'running') {
      runningHtml = ` <span style="color: #58a6ff; font-style: italic;">running...</span>`;
    }

    const fullHtml = summaryHtml + countBadgeHtml + (timingHtml ? `<span style="color: #8b949e;">${timingHtml}</span>` : '') + errorHtml + runningHtml;

    return (
      <div
        key={call.timestamp}
        className="tool-call-entry"
        style={{ padding: '0.125rem 0', lineHeight: 1.3, color: '#e6edf3' }}
        dangerouslySetInnerHTML={{ __html: fullHtml }}
      />
    );
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

            {/* Tool Execution Log */}
            {toolCalls.length > 0 && (
              <div className="task-field tool-execution-log">
                <span className="field-label">Tool Execution Log:</span>
                <div className="tool-log-container">
                  {toolCalls.map((call, index) => (
                    <React.Fragment key={index}>
                      {renderToolCall(call)}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            )}

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
