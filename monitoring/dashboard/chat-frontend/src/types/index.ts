export interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: number;
}

export interface Task {
  task_id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  created_at: string;
}

export interface User {
  user_id: string;
  username?: string;
}

export interface SocketResponse {
  message: string;
  type: 'direct' | 'task_started' | 'task_update';
  task_id?: string;
  tokens?: {
    input: number;
    output: number;
  };
}

export interface TodoItem {
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
  activeForm?: string;
}

export interface ToolCall {
  timestamp: string;
  tool_name: string;
  success: boolean | null;
  has_error: boolean;
  error?: string;
  output_preview?: string | { todos?: TodoItem[] };
  parameters?: any;
  in_progress: boolean;
  duration_ms: number;
}
