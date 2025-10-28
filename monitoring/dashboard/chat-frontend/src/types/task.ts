// Task-related TypeScript interfaces for TaskModal component

export interface TaskDetails {
  task_id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'stopped';
  agent_type?: string;
  model?: string;
  created_at: string;
  updated_at: string;
  error?: string;
  result?: string;
  activity_log?: ActivityLogEntry[];
  workflow?: WorkflowStep[];
  session_uuid?: string;
  has_output_file?: boolean;
  token_usage?: TokenUsage;
}

export interface ActivityLogEntry {
  timestamp: string;
  message: string;
  level?: 'info' | 'warning' | 'error';
}

export interface WorkflowStep {
  name: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  description?: string;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  total_cost: number;
}

export interface ToolCallDetail {
  tool_name: string;
  timestamp: string;
  parameters?: Record<string, any>;
  success: boolean | null;
  has_error: boolean;
  error?: string;
  error_category?: string;
  output_preview?: string | { todos?: any[] };
  output_length?: number;
  duration_ms: number;
  in_progress: boolean;
  screenshot_path?: string;
}

export interface TaskDocument {
  name: string;
  path: string;
  size: number;
  modified: string;
}

export interface TaskScreenshot {
  path: string;
  tool_name: string;
  timestamp: string;
  url: string;
}
