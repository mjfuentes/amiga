# Web Chat Interface Specification

## Overview

Custom web-based chat interface to replace/supplement Telegram bot. Reuses 70% of existing backend logic with WebSocket for real-time communication.

## Architecture

### Stack
- **Backend:** Flask + Flask-SocketIO (WebSocket)
- **Frontend:** React + TypeScript + Socket.IO client
- **Auth:** JWT tokens (session cookies)
- **Database:** SQLite (reuse existing `database.py`)
- **Styling:** TailwindCSS

### Directory Structure
```
web_chat/
├── server.py                 # Flask-SocketIO entry point
├── auth.py                   # JWT authentication
├── websocket_handlers.py     # WebSocket event handlers
├── api_routes.py             # REST endpoints (history, tasks)
├── requirements.txt          # flask-socketio, pyjwt, bcrypt
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── TaskCard.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── AuthModal.tsx
│   │   ├── hooks/
│   │   │   ├── useSocket.ts
│   │   │   ├── useAuth.ts
│   │   │   └── useChat.ts
│   │   └── services/
│   │       ├── api.ts
│   │       └── socket.ts
│   └── public/
└── shared/                   # Symlinks to telegram_bot modules
    ├── session.py -> ../../telegram_bot/session.py
    ├── claude_api.py -> ../../telegram_bot/claude_api.py
    ├── tasks.py -> ../../telegram_bot/tasks.py
    ├── agent_pool.py -> ../../telegram_bot/agent_pool.py
    └── cost_tracker.py -> ../../telegram_bot/cost_tracker.py
```

## Backend Components

### 1. Flask-SocketIO Server (`server.py`)

**Port:** 5000
**Features:** WebSocket + REST endpoints

```python
from flask import Flask, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import sys
from pathlib import Path

# Add telegram_bot to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "telegram_bot"))

from session import SessionManager
from claude_api import ask_claude
from tasks import TaskManager, Task
from agent_pool import AgentPool
from cost_tracker import CostTracker
from orchestrator import discover_repositories
import auth  # Local auth.py

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-secret-change-in-prod')
CORS(app, origins=['http://localhost:3001'], supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

# Reuse existing managers
session_manager = SessionManager(data_dir='../telegram_bot/data')
task_manager = TaskManager(data_dir='../telegram_bot/data')
agent_pool = AgentPool(max_agents=3)
cost_tracker = CostTracker(data_dir='../telegram_bot/data')

WORKSPACE_PATH = os.getenv('WORKSPACE_PATH')
BOT_REPOSITORY = Path(__file__).parent.parent / 'telegram_bot'

# WebSocket event handlers
@socketio.on('connect')
def handle_connect(auth_data):
    """Client connected - verify JWT"""
    token = auth_data.get('token')
    user_id = auth.verify_token(token)

    if not user_id:
        return False  # Reject connection

    # Store in Flask session
    session['user_id'] = user_id
    join_room(user_id)  # Join user-specific room for targeted messages

    emit('connected', {'user_id': user_id})

@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected"""
    user_id = session.get('user_id')
    if user_id:
        leave_room(user_id)

@socketio.on('message')
def handle_message(data):
    """Client sent a message"""
    user_id = session.get('user_id')
    if not user_id:
        emit('error', {'message': 'Unauthorized'})
        return

    message_text = data.get('message')

    # Get session history
    session_obj = session_manager.get_or_create_session(user_id)
    history = [{"role": msg.role, "content": msg.content} for msg in session_obj.history[-10:]]

    # Add user message to history
    session_manager.add_message(user_id, "user", message_text)

    # Call Claude API (same logic as Telegram bot)
    try:
        response, background_task_info, usage_info = asyncio.run(ask_claude(
            user_query=message_text,
            input_method="text",
            conversation_history=history,
            current_workspace=session_manager.get_workspace(user_id),
            bot_repository=str(BOT_REPOSITORY),
            workspace_path=WORKSPACE_PATH,
            available_repositories=discover_repositories(WORKSPACE_PATH),
            active_tasks=task_manager.get_active_tasks(user_id)
        ))

        # Record cost
        if usage_info:
            cost_tracker.record_usage(
                user_id=user_id,
                model=usage_info.get('model'),
                input_tokens=usage_info.get('input_tokens'),
                output_tokens=usage_info.get('output_tokens'),
                request_type='chat'
            )

        # Add assistant response to history
        session_manager.add_message(user_id, "assistant", response)

        # Check if background task needed
        if background_task_info:
            task = task_manager.create_task(
                user_id=user_id,
                description=background_task_info['description'],
                workspace=session_manager.get_workspace(user_id) or WORKSPACE_PATH,
                model='sonnet',
                agent_type=background_task_info.get('agent_type', 'orchestrator')
            )

            # Submit to agent pool
            agent_pool.submit_async(execute_code_task_web, task, user_id)

            emit('response', {
                'message': background_task_info['user_message'],
                'task_id': task.task_id,
                'type': 'task_started'
            })
        else:
            # Direct response
            emit('response', {
                'message': response,
                'type': 'direct'
            })

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        emit('error', {'message': f'Error: {str(e)}'})

@socketio.on('typing')
def handle_typing(data):
    """Client is typing - broadcast to other users in same workspace (future)"""
    user_id = session.get('user_id')
    if user_id:
        emit('user_typing', {'user_id': user_id}, room=user_id, skip_sid=request.sid)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
```

### 2. Authentication Module (`auth.py`)

```python
import jwt
import bcrypt
from datetime import datetime, timedelta
from pathlib import Path
import json
import uuid

SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-secret-change-in-prod')
TOKEN_EXPIRATION_HOURS = 1
REFRESH_TOKEN_EXPIRATION_DAYS = 7

# Simple user database (JSON file for now, can migrate to SQLite later)
USERS_FILE = Path(__file__).parent / 'data' / 'users.json'

def load_users():
    if not USERS_FILE.exists():
        return {}
    with open(USERS_FILE) as f:
        return json.load(f)

def save_users(users):
    USERS_FILE.parent.mkdir(exist_ok=True)
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def hash_password(password: str) -> str:
    """Hash password with bcrypt"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def create_token(user_id: str, expiration_hours: int = TOKEN_EXPIRATION_HOURS) -> str:
    """Create JWT token"""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(hours=expiration_hours),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def verify_token(token: str) -> str | None:
    """Verify JWT token and return user_id, or None if invalid"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload['user_id']
    except jwt.InvalidTokenError:
        return None

def register_user(username: str, email: str, password: str) -> tuple[bool, str]:
    """Register new user. Returns (success, message/user_id)"""
    users = load_users()

    # Check if username or email already exists
    if username in users:
        return False, "Username already exists"
    if any(u['email'] == email for u in users.values()):
        return False, "Email already registered"

    # Create user
    user_id = str(uuid.uuid4())
    users[username] = {
        'id': user_id,
        'email': email,
        'password_hash': hash_password(password),
        'created_at': datetime.utcnow().isoformat(),
        'is_admin': False
    }

    save_users(users)
    return True, user_id

def login_user(username: str, password: str) -> tuple[bool, str]:
    """Login user. Returns (success, token/error_message)"""
    users = load_users()

    if username not in users:
        return False, "Invalid username or password"

    user = users[username]
    if not verify_password(password, user['password_hash']):
        return False, "Invalid username or password"

    # Create token
    token = create_token(user['id'])
    return True, token

def get_user_info(user_id: str) -> dict | None:
    """Get user information by user_id"""
    users = load_users()
    for username, user in users.items():
        if user['id'] == user_id:
            return {
                'user_id': user_id,
                'username': username,
                'email': user['email'],
                'created_at': user['created_at'],
                'is_admin': user.get('is_admin', False)
            }
    return None
```

### 3. API Routes (`api_routes.py`)

REST endpoints for auth and data fetching:

```python
from flask import Blueprint, request, jsonify
import auth
from session import SessionManager
from tasks import TaskManager
from cost_tracker import CostTracker

api = Blueprint('api', __name__, url_prefix='/api')

session_manager = SessionManager(data_dir='../telegram_bot/data')
task_manager = TaskManager(data_dir='../telegram_bot/data')
cost_tracker = CostTracker(data_dir='../telegram_bot/data')

# Auth endpoints
@api.route('/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not all([username, email, password]):
        return jsonify({'error': 'Missing fields'}), 400

    success, result = auth.register_user(username, email, password)
    if success:
        token = auth.create_token(result)
        return jsonify({'token': token, 'user_id': result})
    else:
        return jsonify({'error': result}), 400

@api.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not all([username, password]):
        return jsonify({'error': 'Missing fields'}), 400

    success, result = auth.login_user(username, password)
    if success:
        return jsonify({'token': result})
    else:
        return jsonify({'error': result}), 401

@api.route('/auth/verify', methods=['GET'])
def verify():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    user_id = auth.verify_token(token)

    if not user_id:
        return jsonify({'error': 'Invalid token'}), 401

    user_info = auth.get_user_info(user_id)
    return jsonify(user_info)

# Chat endpoints
@api.route('/chat/history', methods=['GET'])
def get_history():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    user_id = auth.verify_token(token)

    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    session = session_manager.get_or_create_session(user_id)
    history = [
        {
            'role': msg.role,
            'content': msg.content,
            'timestamp': msg.timestamp
        }
        for msg in session.history
    ]

    return jsonify({'history': history})

@api.route('/chat/clear', methods=['POST'])
def clear_history():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    user_id = auth.verify_token(token)

    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    session_manager.clear_session(user_id)
    return jsonify({'success': True})

# Task endpoints
@api.route('/tasks', methods=['GET'])
def get_tasks():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    user_id = auth.verify_token(token)

    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    tasks = task_manager.get_active_tasks(user_id)
    return jsonify({'tasks': [task.to_dict() for task in tasks]})

@api.route('/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    user_id = auth.verify_token(token)

    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    task = task_manager.get_task(task_id)
    if not task or task.user_id != user_id:
        return jsonify({'error': 'Not found'}), 404

    return jsonify(task.to_dict())

# Cost tracking endpoints
@api.route('/usage', methods=['GET'])
def get_usage():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    user_id = auth.verify_token(token)

    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    stats = cost_tracker.get_usage_stats(user_id)
    return jsonify(stats)
```

### 4. Task Execution Adapter (`task_executor.py`)

Adapts `execute_code_task` to use WebSocket notifications:

```python
import asyncio
from pathlib import Path
from tasks import Task, TaskManager
from agent_pool import AgentPool
from flask_socketio import SocketIO

async def execute_code_task_web(task: Task, user_id: str, socketio: SocketIO):
    """Execute code task and notify via WebSocket"""
    from claude_interactive import create_task_branch, merge_task_branch
    from orchestrator import get_workspace_path

    task_manager = TaskManager(data_dir='../telegram_bot/data')

    try:
        # Update task status
        task_manager.update_task(task.task_id, status="running")
        socketio.emit('task_update', {
            'task_id': task.task_id,
            'status': 'running'
        }, room=user_id)

        # Create git branch
        workspace_path = get_workspace_path(task.workspace)
        branch_success, branch_info = create_task_branch(task.task_id, workspace_path)

        # Execute using Claude pool
        claude_pool = AgentPool(max_agents=3)
        success, result, pid, workflow = await claude_pool.execute_task(
            task_id=task.task_id,
            description=task.description,
            workspace=Path(task.workspace),
            bot_repo_path=Path(__file__).parent.parent / 'telegram_bot',
            model=task.model,
            agent=task.agent_type,
            context=task.context,
            pid_callback=lambda pid: socketio.emit('task_progress', {
                'task_id': task.task_id,
                'message': f'Task started (PID: {pid})'
            }, room=user_id),
            progress_callback=lambda msg: socketio.emit('task_progress', {
                'task_id': task.task_id,
                'message': msg
            }, room=user_id)
        )

        # Update task
        if success:
            task_manager.update_task(task.task_id, status="completed", result=result)

            # Merge branch
            if branch_success:
                merge_task_branch(task.task_id, workspace_path)

            # Notify user
            socketio.emit('task_completed', {
                'task_id': task.task_id,
                'result': result,
                'workflow': workflow
            }, room=user_id)
        else:
            task_manager.update_task(task.task_id, status="failed", error=result)
            socketio.emit('task_failed', {
                'task_id': task.task_id,
                'error': result
            }, room=user_id)

    except Exception as e:
        logger.error(f"Task execution error: {e}", exc_info=True)
        task_manager.update_task(task.task_id, status="failed", error=str(e))
        socketio.emit('task_error', {
            'task_id': task.task_id,
            'error': str(e)
        }, room=user_id)
```

## Frontend Components

### 1. Socket.IO Hook (`hooks/useSocket.ts`)

```typescript
import { useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';

export const useSocket = (token: string | null) => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!token) return;

    const newSocket = io('http://localhost:5000', {
      auth: { token },
      transports: ['websocket']
    });

    newSocket.on('connect', () => {
      console.log('Connected to WebSocket');
      setConnected(true);
    });

    newSocket.on('disconnect', () => {
      console.log('Disconnected from WebSocket');
      setConnected(false);
    });

    newSocket.on('connected', (data) => {
      console.log('Authenticated:', data.user_id);
    });

    setSocket(newSocket);

    return () => {
      newSocket.close();
    };
  }, [token]);

  return { socket, connected };
};
```

### 2. Chat Hook (`hooks/useChat.ts`)

```typescript
import { useState, useEffect } from 'react';
import { Socket } from 'socket.io-client';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  type?: 'direct' | 'task_started' | 'task_progress' | 'task_completed';
  task_id?: string;
}

export const useChat = (socket: Socket | null) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    if (!socket) return;

    socket.on('response', (data) => {
      const message: Message = {
        role: 'assistant',
        content: data.message,
        timestamp: new Date().toISOString(),
        type: data.type,
        task_id: data.task_id
      };
      setMessages(prev => [...prev, message]);
      setIsTyping(false);
    });

    socket.on('task_update', (data) => {
      // Update task status in message history
      setMessages(prev => prev.map(msg =>
        msg.task_id === data.task_id
          ? { ...msg, content: `Task #${data.task_id}: ${data.status}` }
          : msg
      ));
    });

    socket.on('task_completed', (data) => {
      const message: Message = {
        role: 'assistant',
        content: `Task #${data.task_id} completed:\n\n${data.result}`,
        timestamp: new Date().toISOString(),
        type: 'task_completed',
        task_id: data.task_id
      };
      setMessages(prev => [...prev, message]);
    });

    socket.on('error', (data) => {
      const message: Message = {
        role: 'assistant',
        content: `Error: ${data.message}`,
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, message]);
      setIsTyping(false);
    });

  }, [socket]);

  const sendMessage = (content: string) => {
    if (!socket) return;

    const userMessage: Message = {
      role: 'user',
      content,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setIsTyping(true);

    socket.emit('message', { message: content });
  };

  return { messages, sendMessage, isTyping };
};
```

### 3. Chat Window Component (`components/ChatWindow.tsx`)

```typescript
import React, { useRef, useEffect } from 'react';
import MessageBubble from './MessageBubble';
import { Message } from '../hooks/useChat';

interface ChatWindowProps {
  messages: Message[];
  isTyping: boolean;
  onSendMessage: (message: string) => void;
}

const ChatWindow: React.FC<ChatWindowProps> = ({ messages, isTyping, onSendMessage }) => {
  const [input, setInput] = React.useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim()) {
      onSendMessage(input);
      setInput('');
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4 shadow-sm">
        <h1 className="text-xl font-semibold text-gray-800">AMIGA Chat</h1>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.map((msg, idx) => (
          <MessageBubble key={idx} message={msg} />
        ))}
        {isTyping && (
          <div className="flex items-center space-x-2 text-gray-500">
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="bg-white border-t px-6 py-4">
        <form onSubmit={handleSubmit} className="flex space-x-4">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={!input.trim()}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
};

export default ChatWindow;
```

### 4. Message Bubble Component (`components/MessageBubble.tsx`)

```typescript
import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Message } from '../hooks/useChat';

interface MessageBubbleProps {
  message: Message;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-3xl rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-white text-gray-800 border shadow-sm'
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <ReactMarkdown
            className="prose prose-sm max-w-none"
            components={{
              code({ node, inline, className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || '');
                return !inline && match ? (
                  <SyntaxHighlighter
                    style={vscDarkPlus}
                    language={match[1]}
                    PreTag="div"
                    {...props}
                  >
                    {String(children).replace(/\n$/, '')}
                  </SyntaxHighlighter>
                ) : (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              }
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}

        {message.task_id && (
          <div className="mt-2 text-xs text-gray-500">
            Task ID: {message.task_id}
          </div>
        )}

        <div className={`text-xs mt-1 ${isUser ? 'text-blue-100' : 'text-gray-400'}`}>
          {new Date(message.timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
};

export default MessageBubble;
```

## Security Features

### 1. Input Sanitization
Reuse existing `claude_api.py` sanitization:
- `sanitize_xml_content()` - HTML escape + pattern removal
- `detect_prompt_injection()` - Detect attacks

### 2. Authentication
- JWT tokens (1h expiration)
- bcrypt password hashing (12 rounds)
- Refresh tokens (7 days)

### 3. Rate Limiting
Use `flask-limiter`:
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["100 per hour", "10 per minute"]
)

@api.route('/api/chat/message')
@limiter.limit("20 per minute")
def handle_message():
    pass
```

### 4. CORS Configuration
Production config:
```python
CORS(app,
     origins=['https://chat.example.com'],
     supports_credentials=True,
     methods=['GET', 'POST'],
     allow_headers=['Content-Type', 'Authorization'])
```

### 5. HTTPS
Production deployment requires:
- SSL certificate (Let's Encrypt)
- Nginx reverse proxy with HTTPS
- HTTP → HTTPS redirect

## Deployment

### Development
```bash
# Terminal 1: Backend
cd web_chat
python server.py  # Port 5000

# Terminal 2: Frontend
cd web_chat/frontend
npm start  # Port 3001
```

### Production (Docker)
```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy code
COPY telegram_bot/ telegram_bot/
COPY web_chat/ web_chat/

# Run Flask-SocketIO
EXPOSE 5000
CMD ["python", "web_chat/server.py"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  web:
    build: .
    ports:
      - "5000:5000"
    environment:
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - WORKSPACE_PATH=/workspace
    volumes:
      - ./data:/app/data
      - /path/to/workspace:/workspace
```

## Testing Plan

### Unit Tests
```python
# tests/test_auth.py
def test_register_user():
    success, user_id = auth.register_user('testuser', 'test@example.com', 'password123')
    assert success
    assert user_id

def test_login_user():
    auth.register_user('testuser', 'test@example.com', 'password123')
    success, token = auth.login_user('testuser', 'password123')
    assert success
    assert auth.verify_token(token) is not None
```

### Integration Tests
```python
# tests/test_websocket.py
def test_message_flow():
    client = socketio.test_client(app)
    client.emit('connect', {'token': test_token})
    client.emit('message', {'message': 'Hello'})

    received = client.get_received()
    assert len(received) > 0
    assert received[0]['name'] == 'response'
```

### Manual Checklist
- [ ] User registration/login
- [ ] Send message, receive response
- [ ] Background task creation
- [ ] Real-time task updates
- [ ] Session persistence
- [ ] Cost tracking display
- [ ] File upload
- [ ] Mobile responsive

## Migration Path

1. **Week 1:** Backend server + auth
2. **Week 2:** Frontend UI + WebSocket integration
3. **Week 3:** Testing + security audit
4. **Week 4:** Production deployment

Telegram bot remains operational throughout.

## Dependencies

### Backend (`web_chat/requirements.txt`)
```
flask>=3.0.0
flask-socketio>=5.3.0
flask-cors>=4.0.0
flask-limiter>=3.5.0
python-socketio>=5.10.0
eventlet>=0.33.0
pyjwt>=2.8.0
bcrypt>=4.1.2
python-dotenv>=1.0.0
```

### Frontend (`web_chat/frontend/package.json`)
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "socket.io-client": "^4.6.0",
    "react-markdown": "^9.0.0",
    "react-syntax-highlighter": "^15.5.0",
    "tailwindcss": "^3.4.0"
  }
}
```
