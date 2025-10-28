import React, { useState, useEffect } from 'react';
import './SessionsSidebar.css';

interface Session {
  session_id: string;
  total_tools: number;
  blocked: number;
  errors: number;
  last_activity: string;
}

interface SessionsSidebarProps {
  visible: boolean;
}

export const SessionsSidebar: React.FC<SessionsSidebarProps> = ({ visible }) => {
  const [sessions, setSessions] = useState<Session[]>([]);
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

    let intervalId: NodeJS.Timeout | null = null;

    const fetchSessions = async () => {
      try {
        // Fetch sessions based on current filter (same logic as monitoring dashboard)
        const endpoint = filter === 'active'
          ? '/api/metrics/cli-sessions?minutes=5'  // Active: last 5 minutes
          : '/api/metrics/cli-sessions?hours=24';  // Completed: last 24 hours

        const response = await fetch(endpoint);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        const sessionsList = data?.sessions || [];

        // For completed filter, only show sessions that are NOT active
        if (filter === 'completed') {
          const completedSessions = sessionsList.filter((session: Session) => {
            const status = getSessionStatus(session.last_activity);
            return status !== 'active';
          });
          setSessions(completedSessions);
        } else {
          setSessions(sessionsList);
        }

        setConnected(true);
      } catch (error) {
        console.error('Failed to fetch sessions:', error);
        setConnected(false);
      }
    };

    // Initial fetch
    fetchSessions();

    // Poll every 5 seconds for updates
    intervalId = setInterval(fetchSessions, 5000);

    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [visible, filter]);

  const formatSessionId = (sessionId: string) => {
    // Extract short ID (first 6 chars after "task_")
    if (sessionId.startsWith('task_')) {
      return sessionId.substring(5, 11);
    }
    return sessionId.substring(0, 6);
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

  const getSessionStatus = (lastActivity: string): 'active' | 'completed' => {
    if (!lastActivity) return 'completed';

    try {
      let isoTimestamp = lastActivity.trim().replace(' ', 'T');
      const date = new Date(isoTimestamp);

      if (isNaN(date.getTime())) {
        return 'completed';
      }

      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 1000 / 60);

      // Active if last activity was within 5 minutes
      return diffMins < 5 ? 'active' : 'completed';
    } catch (error) {
      return 'completed';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return '#6a9fb5';
      case 'completed':
        return '#888';
      default:
        return '#888';
    }
  };

  const handleSessionClick = (sessionId: string) => {
    // Navigate to monitoring dashboard with session highlighted and referrer info
    window.location.href = `/dashboard#${sessionId}?ref=chat`;
  };

  if (!visible) return null;

  // Filter sessions based on selected filter
  const filteredSessions = sessions.filter((session) => {
    const status = getSessionStatus(session.last_activity);
    if (filter === 'active') {
      return status === 'active';
    } else {
      return status === 'completed';
    }
  });

  return (
    <div className="sessions-sidebar">
      <div className="sidebar-header">
        <h3>Sessions</h3>
        <span className={`connection-indicator ${connected ? 'connected' : 'disconnected'}`}>
          {connected ? '●' : '○'}
        </span>
      </div>

      <div className="filter-toggle">
        <button
          className={`filter-button ${filter === 'active' ? 'active' : ''}`}
          onClick={() => setFilter('active')}
        >
          Active ({sessions.filter(s => getSessionStatus(s.last_activity) === 'active').length})
        </button>
        <button
          className={`filter-button ${filter === 'completed' ? 'active' : ''}`}
          onClick={() => setFilter('completed')}
        >
          Completed ({sessions.filter(s => getSessionStatus(s.last_activity) === 'completed').length})
        </button>
      </div>

      <div className="sidebar-content">
        {filteredSessions.length === 0 ? (
          <div className="empty-state">
            <p>No {filter} sessions</p>
          </div>
        ) : (
          <div className="sessions-list">
            {filteredSessions.map((session) => {
              const status = getSessionStatus(session.last_activity);
              return (
                <div
                  key={session.session_id}
                  className={`session-item ${status}`}
                  onClick={() => handleSessionClick(session.session_id)}
                  role="button"
                  tabIndex={0}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      handleSessionClick(session.session_id);
                    }
                  }}
                >
                  <div className="session-header">
                    <span
                      className="session-id"
                      style={{ color: getStatusColor(status) }}
                    >
                      #{formatSessionId(session.session_id)}
                    </span>
                    <span className="session-status" style={{ color: getStatusColor(status) }}>
                      {status}
                    </span>
                  </div>
                  <div className="session-meta">
                    <span className="session-tools">
                      {session.total_tools} {session.total_tools === 1 ? 'tool' : 'tools'}
                    </span>
                    <span className="session-time">{formatTimestamp(session.last_activity)}</span>
                  </div>
                  {session.errors > 0 && (
                    <div className="session-errors">
                      <span className="errors-label">Errors:</span>
                      <span className="errors-count">{session.errors}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
