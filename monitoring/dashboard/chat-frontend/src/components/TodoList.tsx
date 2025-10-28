import React from 'react';
import './TodoList.css';

export interface TodoItem {
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
  activeForm?: string;
}

interface TodoListProps {
  todos: TodoItem[];
}

const getStatusIcon = (status: string): string => {
  switch (status) {
    case 'pending':
      return '⏳';
    case 'in_progress':
      return '▶️';
    case 'completed':
      return '✅';
    default:
      return '⏳';
  }
};

const getStatusClass = (status: string): string => {
  switch (status) {
    case 'pending':
      return 'todo-status-pending';
    case 'in_progress':
      return 'todo-status-in-progress';
    case 'completed':
      return 'todo-status-completed';
    default:
      return 'todo-status-pending';
  }
};

export const TodoList: React.FC<TodoListProps> = ({ todos }) => {
  if (!todos || todos.length === 0) {
    return null;
  }

  return (
    <div className="todo-list-container">
      <div className="todo-list-header">
        <span className="todo-list-title">Planning Tasks</span>
        <span className="todo-list-count">
          {todos.filter(t => t.status === 'completed').length}/{todos.length}
        </span>
      </div>
      <ol className="todo-list">
        {todos.map((todo, index) => (
          <li key={index} className={`todo-item ${getStatusClass(todo.status)}`}>
            <span className="todo-status-icon" aria-label={`Status: ${todo.status}`}>
              {getStatusIcon(todo.status)}
            </span>
            <span className="todo-content">{todo.content}</span>
          </li>
        ))}
      </ol>
    </div>
  );
};
