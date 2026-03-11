import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { TaskSidebar } from './TaskSidebar';
import { io } from 'socket.io-client';

// Mock socket.io-client
jest.mock('socket.io-client');
const mockIo = io as jest.MockedFunction<typeof io>;

// Mock fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Mock EventSource
class MockEventSource {
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  readyState = 0;
  close = jest.fn();

  constructor(_url: string) {
    setTimeout(() => {
      if (this.onopen) this.onopen();
    }, 0);
  }
}

(global as any).EventSource = MockEventSource;

describe('TaskSidebar Socket.IO Integration', () => {
  let mockOn: jest.Mock;
  let mockClose: jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();

    mockOn = jest.fn();
    mockClose = jest.fn();

    mockIo.mockReturnValue({
      on: mockOn,
      close: mockClose,
    } as any);

    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ recent_24h: { tasks: [] } }),
    });
  });

  it('should not connect Socket.IO when not visible', () => {
    render(<TaskSidebar visible={false} />);
    expect(mockIo).not.toHaveBeenCalled();
  });

  it('should connect Socket.IO when visible', () => {
    render(<TaskSidebar visible={true} />);
    expect(mockIo).toHaveBeenCalledWith(
      expect.any(String),
      { transports: ['polling', 'websocket'] }
    );
  });

  it('should register task_update and task_stopped listeners', () => {
    render(<TaskSidebar visible={true} />);

    const registeredEvents = mockOn.mock.calls.map(
      (call: [string, Function]) => call[0]
    );
    expect(registeredEvents).toContain('task_update');
    expect(registeredEvents).toContain('task_stopped');
  });

  it('should fetch tasks from REST when task_update fires', async () => {
    const mockTasks = [
      {
        task_id: 'task_abc123',
        description: 'Test task',
        status: 'running' as const,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        model: 'sonnet',
        agent_type: 'code_agent',
      },
    ];

    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ recent_24h: { tasks: mockTasks } }),
    });

    render(<TaskSidebar visible={true} />);

    // Find the task_update callback and invoke it
    const taskUpdateCall = mockOn.mock.calls.find(
      (call: [string, Function]) => call[0] === 'task_update'
    );
    expect(taskUpdateCall).toBeDefined();

    const taskUpdateCallback = taskUpdateCall[1];

    await act(async () => {
      await taskUpdateCallback({ task_id: 'abc123', status: 'running' });
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/metrics/tasks')
    );

    await waitFor(() => {
      expect(screen.getByText('Test task')).toBeInTheDocument();
    });
  });

  it('should fetch tasks from REST when task_stopped fires', async () => {
    render(<TaskSidebar visible={true} />);

    const taskStoppedCall = mockOn.mock.calls.find(
      (call: [string, Function]) => call[0] === 'task_stopped'
    );
    expect(taskStoppedCall).toBeDefined();

    const taskStoppedCallback = taskStoppedCall[1];

    await act(async () => {
      await taskStoppedCallback({ task_id: 'abc123' });
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/metrics/tasks')
    );
  });

  it('should close Socket.IO on unmount', () => {
    const { unmount } = render(<TaskSidebar visible={true} />);
    unmount();
    expect(mockClose).toHaveBeenCalled();
  });

  it('should handle fetch failure gracefully without crashing', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    render(<TaskSidebar visible={true} />);

    const taskUpdateCall = mockOn.mock.calls.find(
      (call: [string, Function]) => call[0] === 'task_update'
    );
    const taskUpdateCallback = taskUpdateCall[1];

    // Should not throw
    await act(async () => {
      await taskUpdateCallback({ task_id: 'abc123', status: 'running' });
    });

    expect(screen.getByText('Tasks')).toBeInTheDocument();
  });

  it('should handle non-ok response gracefully', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
    });

    render(<TaskSidebar visible={true} />);

    const taskUpdateCall = mockOn.mock.calls.find(
      (call: [string, Function]) => call[0] === 'task_update'
    );
    const taskUpdateCallback = taskUpdateCall[1];

    await act(async () => {
      await taskUpdateCallback({ task_id: 'abc123', status: 'running' });
    });

    expect(screen.getByText('Tasks')).toBeInTheDocument();
  });
});
