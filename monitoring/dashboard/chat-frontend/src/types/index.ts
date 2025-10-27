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
}
