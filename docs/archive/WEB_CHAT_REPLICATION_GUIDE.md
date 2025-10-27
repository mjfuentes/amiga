# Web Chat Interface - Telegram Bot Architecture Replication Guide

This guide shows how to replicate the Telegram bot's architecture in a web-based chat interface.

---

## 1. Message Flow: What Needs to Happen

### Current Telegram Flow
```
User sends text/voice
    ↓
Telegram webhook → main.py
    ↓
Authorization + rate limiting
    ↓
Queued to per-user message queue
    ↓
Process sequentially (one message at a time per user)
    ↓
Route: Haiku (fast) or Sonnet (code task)
    ↓
Send response
```

### Web Chat Equivalent
```
User types and hits Send
    ↓
HTTP POST /api/chat
    ↓
Authorization (session/token check)
    ↓
Rate limiting check
    ↓
Queue to per-user message queue
    ↓
Process sequentially (one message at a time per user)
    ↓
Route: Haiku or Sonnet (same logic)
    ↓
Stream response via WebSocket or HTTP chunking
```

---

## 2. Core Components to Implement

### A. API Endpoint: POST /api/chat

**Request**:
```json
{
  "message": "Fix the bug in main.py",
  "conversation_id": "user-123",
  "user_id": 123
}
```

**Response** (streaming):
```json
{
  "status": "processing",
  "response": "Task #abc123 started...",
  "task_id": "abc123",
  "type": "background_task"
}
```

**Implementation** (Flask):
```python
@app.route('/api/chat', methods=['POST'])
async def handle_chat():
    data = request.json
    user_id = data['user_id']
    message = data['message']
    
    # 1. Auth check
    if not authorize_user(user_id):
        return {"error": "Unauthorized"}, 403
    
    # 2. Rate limit check
    allowed, error = rate_limiter.check_rate_limit(user_id)
    if not allowed:
        return {"error": error}, 429
    
    # 3. Queue message
    await queue_manager.enqueue_message(
        user_id=user_id,
        message=message,
        handler=process_chat_message
    )
    
    # 4. Return immediately (don't wait for processing)
    return {"status": "queued", "user_id": user_id}, 202
```

### B. WebSocket for Real-Time Updates

**Connection** (Socket.io):
```javascript
const socket = io('http://localhost:5000');
socket.on('chat_response', (data) => {
  // Update UI with response
  document.getElementById('chat').innerHTML += data.message;
});
```

**Server Broadcasting**:
```python
@socketio.on('connect')
def handle_connect():
    room = request.sid
    join_room(room)

async def process_chat_message(user_id, message):
    # ... (same routing logic as Telegram)
    response = await ask_claude(message, ...)
    
    # Broadcast to user's socket room
    emit('chat_response', {
        'message': response,
        'type': 'direct_answer'
    }, room=user_rooms[user_id])
```

### C. Message Queue (Reuse from Telegram Bot)

The `message_queue.py` module can be reused directly:

```python
# In web chat handler
from message_queue import MessageQueueManager

queue_manager = MessageQueueManager()

async def web_message_handler(update):
    """Adapter to use same message_queue as Telegram"""
    user_id = update['user_id']
    message = update['message']
    
    await queue_manager.enqueue_message(
        user_id=user_id,
        update=update,
        context=None,  # No Telegram context
        handler=async_process_web_message,
        handler_name="web_message"
    )
```

### D. Session Management (Reuse from Telegram Bot)

The `session.py` module is framework-agnostic:

```python
from session import SessionManager

session_manager = SessionManager(data_dir="data")

@app.route('/api/history', methods=['GET'])
def get_conversation_history():
    user_id = request.args.get('user_id')
    session = session_manager.get_session(user_id)
    
    return {
        'history': [
            {'role': msg.role, 'content': msg.content, 'timestamp': msg.timestamp}
            for msg in session.history[-10:]  # Last 10 messages
        ]
    }
```

### E. Routing Engine (Reuse from Telegram Bot)

The `claude_api.py` module works as-is:

```python
from claude_api import ask_claude

async def route_message(user_id, message, conversation_history):
    response, background_task_info, usage_info = await ask_claude(
        user_query=message,
        input_method="text",
        conversation_history=conversation_history,
        current_workspace=None,  # Web users don't have workspace
        bot_repository=BOT_REPOSITORY,
        workspace_path=WORKSPACE_PATH,
        available_repositories=[],
        active_tasks=[]
    )
    
    return {
        'response': response,
        'background_task_info': background_task_info,
        'usage_info': usage_info
    }
```

### F. Task Execution (Reuse from Telegram Bot)

The agent pool and task execution can be reused:

```python
from agent_pool import AgentPool, TaskPriority
from tasks import Task, TaskManager

agent_pool = AgentPool(max_agents=3)
task_manager = TaskManager(db=db)

# When background task detected
if background_task_info:
    task = await task_manager.create_task(
        user_id=user_id,
        description=background_task_info['description'],
        workspace=workspace,
        model='sonnet',
        context=background_task_info['context']
    )
    
    # Queue to agent pool
    await agent_pool.submit(
        execute_web_code_task,
        task,
        user_id=user_id,
        priority=TaskPriority.HIGH
    )

async def execute_web_code_task(task, user_id):
    """Web-adapted version of execute_code_task from main.py"""
    # Same logic as Telegram version, but:
    # - Use WebSocket to notify user instead of Telegram message
    # - Stream results via SSE instead of sending document
    
    success, result, pid, workflow = await claude_pool.execute_task(...)
    
    # Notify user via WebSocket
    emit('task_update', {
        'task_id': task.task_id,
        'status': 'completed' if success else 'failed',
        'result': result
    }, room=user_rooms.get(user_id))
```

---

## 3. Web-Specific Considerations

### A. Authentication

**Telegram**: User ID from Telegram
**Web**: Session token or JWT

```python
from functools import wraps

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        user_id = verify_token(token)
        if not user_id:
            return {'error': 'Unauthorized'}, 401
        return f(*args, user_id=user_id, **kwargs)
    return decorated

@app.route('/api/chat', methods=['POST'])
@require_auth
def handle_chat(user_id):
    # user_id extracted from token
    ...
```

### B. Streaming Responses

**Telegram**: Send messages one at a time
**Web**: Stream via SSE or WebSocket

```python
# Server-Sent Events approach
@app.route('/api/chat/stream')
@require_auth
def stream_response(user_id):
    message = request.args.get('message')
    
    def event_stream():
        # Route message
        response, task_info, usage = await route_message(
            user_id, message, get_session_history(user_id)
        )
        
        # Stream response chunks
        yield f"data: {json.dumps({'type': 'response', 'text': response})}\n\n"
        
        # If background task, stream task updates
        if task_info:
            task = create_task(...)
            yield f"data: {json.dumps({'type': 'task_created', 'task_id': task.task_id})}\n\n"
    
    return Response(event_stream(), mimetype='text/event-stream')
```

### C. Conversation UI

**Telegram**: Chat-style messages
**Web**: React/Vue chat component

```javascript
// React example
function ChatWindow() {
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  
  const sendMessage = async () => {
    // Add user message
    setMessages([...messages, { role: 'user', content: inputText }]);
    setInputText('');
    
    // Stream response
    const response = await fetch('/api/chat/stream?message=' + inputText);
    const reader = response.body.getReader();
    
    let assistantMessage = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      const chunk = new TextDecoder().decode(value);
      const lines = chunk.split('\n');
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          if (data.type === 'response') {
            assistantMessage += data.text;
            setMessages(msgs => {
              const updated = [...msgs];
              updated[updated.length - 1] = {
                role: 'assistant',
                content: assistantMessage
              };
              return updated;
            });
          }
        }
      }
    }
  };
  
  return (
    <div>
      {messages.map(msg => <ChatMessage {...msg} />)}
      <input 
        value={inputText} 
        onChange={e => setInputText(e.target.value)}
        onKeyPress={e => e.key === 'Enter' && sendMessage()}
      />
    </div>
  );
}
```

### D. Background Tasks Display

**Telegram**: User gets notification message
**Web**: Show task in UI, stream progress

```javascript
// Real-time task updates via WebSocket
socket.on('task_update', (data) => {
  setTasks(prev => {
    const task = prev.find(t => t.id === data.task_id);
    if (task) {
      task.status = data.status;
      task.result = data.result;
    }
    return [...prev];
  });
});

// Display running tasks
function TaskList({ tasks }) {
  return (
    <div>
      {tasks.filter(t => t.status === 'running').map(task => (
        <div key={task.id}>
          <strong>Task #{task.id}</strong>
          <p>{task.description}</p>
          <progress value={task.progress} />
        </div>
      ))}
    </div>
  );
}
```

### E. File Uploads (Chat Images)

**Telegram**: Direct image/document handling
**Web**: Form upload with file handling

```python
@app.route('/api/upload', methods=['POST'])
@require_auth
def upload_file(user_id):
    file = request.files['file']
    temp_path = f"/tmp/{user_id}_{file.filename}"
    file.save(temp_path)
    
    # Use same image handling as Telegram
    response, task_info, usage = await ask_claude(
        user_query=request.form.get('caption', ''),
        input_method='text',
        conversation_history=get_session_history(user_id),
        image_path=temp_path,  # Same as Telegram
        ...
    )
    
    return {'response': response, 'task_id': task_info.get('task_id') if task_info else None}
```

---

## 4. Database and Persistence

### Use Same Data Store as Telegram

```python
# Reuse exact same database files
from database import Database
from tasks import TaskManager
from session import SessionManager

db = Database("data/agentlab.db")
task_manager = TaskManager(db=db)
session_manager = SessionManager("data")

# Both Telegram bot and web chat access same data:
# - Same task history
# - Same conversation sessions
# - Same cost tracking
```

**Benefits**:
- User can switch between platforms and see same history
- Task status visible in both Telegram and web
- Unified cost tracking

---

## 5. Full Architecture Diagram: Web Chat

```
WEB CLIENT (React/Vue)
├─ Chat UI
├─ File upload
├─ Task status
└─ WebSocket connection

        ↓ HTTP + WebSocket

FLASK BACKEND
├─ /api/chat (POST) - Handle message
├─ /api/history (GET) - Conversation history
├─ /api/upload (POST) - File upload
├─ /api/tasks (GET) - Task list
└─ WebSocket handlers - Real-time updates

        ↓ (Reuse Telegram bot modules)

CORE MODULES (Shared)
├─ message_queue.py - Sequential processing
├─ session.py - Conversation history
├─ claude_api.py - Routing (Haiku)
├─ claude_interactive.py - Code execution (Sonnet)
├─ agent_pool.py - Bounded workers
├─ tasks.py - Task tracking
└─ database.py - SQLite persistence

        ↓

EXTERNAL SERVICES
├─ Claude API (Haiku) - Routing
└─ Claude Code CLI (Sonnet) - Code execution
```

---

## 6. Migration Path

### Phase 1: Minimal Web Chat
```python
# Just routing, no background tasks
- POST /api/chat → Call ask_claude → Return response
- GET /api/history → Return session history
- Simple WebSocket connection for real-time
```

### Phase 2: Add Task Execution
```python
# Add background task support
- Create tasks in database
- Queue to agent_pool
- Stream task progress via WebSocket
- Display task status in UI
```

### Phase 3: Add Persistence
```python
# Share data with Telegram bot
- Same database (agentlab.db)
- Same sessions (sessions.json)
- Same cost tracking (cost_tracking.json)
- Users see same history in both platforms
```

### Phase 4: Add Advanced Features
```python
# Optional enhancements
- File uploads and analysis
- Voice input (Whisper)
- Dashboard integration
- Collaboration (multi-user sessions)
```

---

## 7. Key Implementation Files

| Module | Purpose | Changes Needed |
|--------|---------|-----------------|
| `message_queue.py` | Sequential processing | None (reuse as-is) |
| `session.py` | Conversation history | None (reuse as-is) |
| `claude_api.py` | Routing logic | None (reuse as-is) |
| `claude_interactive.py` | Code execution | None (reuse as-is) |
| `agent_pool.py` | Worker pool | None (reuse as-is) |
| `tasks.py` | Task management | None (reuse as-is) |
| `database.py` | SQLite | None (reuse as-is) |
| `formatter.py` | Response formatting | Adapt for HTML instead of Telegram |
| `main.py` | Telegram handlers | Create new `web_handlers.py` for Flask |

---

## 8. Sample Flask Application Structure

```python
# web_app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import asyncio

from message_queue import MessageQueueManager
from session import SessionManager
from tasks import TaskManager, Task
from agent_pool import AgentPool, TaskPriority
from claude_api import ask_claude
from database import Database

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins='*')

# Initialize shared modules
db = Database('data/agentlab.db')
session_manager = SessionManager('data')
task_manager = TaskManager(db=db)
queue_manager = MessageQueueManager()
agent_pool = AgentPool(max_agents=3)

# Track user socket connections
user_rooms = {}

@socketio.on('connect')
def handle_connect():
    """User connected - track their socket room"""
    user_id = request.args.get('user_id')
    if user_id:
        user_rooms[user_id] = request.sid
        join_room(request.sid)
        emit('status', {'data': 'Connected'})

@socketio.on('disconnect')
def handle_disconnect():
    """User disconnected - clean up"""
    for user_id, room in list(user_rooms.items()):
        if room == request.sid:
            del user_rooms[user_id]
            break

@app.route('/api/chat', methods=['POST'])
async def handle_chat():
    """Handle incoming chat message"""
    data = request.json
    user_id = data['user_id']
    message = data['message']
    
    # Authorization
    if not authorize_user(user_id):
        return {'error': 'Unauthorized'}, 403
    
    # Rate limiting
    allowed, error = rate_limiter.check_rate_limit(user_id)
    if not allowed:
        return {'error': error}, 429
    
    # Get session history
    session = session_manager.get_or_create_session(user_id)
    history = [{'role': m.role, 'content': m.content} for m in session.history[-10:]]
    
    # Route message via ask_claude
    response, task_info, usage_info = await ask_claude(
        user_query=message,
        input_method='text',
        conversation_history=history,
        current_workspace=None,
        bot_repository=BOT_REPOSITORY,
        workspace_path=WORKSPACE_PATH,
        available_repositories=[],
        active_tasks=[]
    )
    
    # Create background task if needed
    task_id = None
    if task_info:
        task = await task_manager.create_task(
            user_id=user_id,
            description=task_info['description'],
            workspace=WORKSPACE_PATH,
            model='sonnet',
            context=task_info.get('context')
        )
        task_id = task.task_id
        
        # Queue to agent pool
        await agent_pool.submit(
            execute_web_code_task,
            task,
            user_id,
            priority=TaskPriority.HIGH
        )
        response = f"Task #{task_id} started.\n\n{task_info['user_message']}"
    
    # Update session
    session_manager.add_message(user_id, 'user', message)
    session_manager.add_message(user_id, 'assistant', response)
    
    # Notify via WebSocket
    room = user_rooms.get(user_id)
    if room:
        emit('chat_response', {
            'message': response,
            'task_id': task_id,
            'type': 'direct_answer' if not task_info else 'background_task'
        }, room=room)
    
    return {'status': 'ok', 'task_id': task_id}, 200

async def execute_web_code_task(task, user_id):
    """Execute background task (web-adapted)"""
    try:
        # Same logic as execute_code_task from main.py
        # But use WebSocket for updates instead of Telegram
        
        await task_manager.update_task(task.task_id, status='running')
        
        success, result, pid, workflow = await claude_pool.execute_task(
            task_id=task.task_id,
            description=task.description,
            workspace=Path(task.workspace),
            bot_repo_path=BOT_REPOSITORY,
            model=task.model,
            context=task.context,
            # ... other params
        )
        
        if success:
            await task_manager.update_task(task.task_id, status='completed', result=result)
        else:
            await task_manager.update_task(task.task_id, status='failed', error=result)
        
        # Notify user
        room = user_rooms.get(user_id)
        if room:
            emit('task_update', {
                'task_id': task.task_id,
                'status': 'completed' if success else 'failed',
                'result': result[:500] + '...' if len(result) > 500 else result
            }, room=room)
    
    except Exception as e:
        await task_manager.update_task(task.task_id, status='failed', error=str(e))
        room = user_rooms.get(user_id)
        if room:
            emit('task_update', {
                'task_id': task.task_id,
                'status': 'failed',
                'result': str(e)
            }, room=room)

if __name__ == '__main__':
    asyncio.run(agent_pool.start())
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
```

---

## Summary: Replication Checklist

- [ ] Identify which Telegram modules can be reused (all of them!)
- [ ] Create Flask app with `/api/chat` endpoint
- [ ] Add WebSocket support for real-time updates
- [ ] Share database files with Telegram bot
- [ ] Implement authorization (JWT/session tokens)
- [ ] Add rate limiting (reuse from bot)
- [ ] Connect to same MessageQueue, SessionManager
- [ ] Route via ask_claude (reuse from bot)
- [ ] Queue tasks to same agent_pool (reuse from bot)
- [ ] Create web-specific handlers that emit WebSocket events
- [ ] Build React/Vue UI for chat interface
- [ ] Test with both Telegram bot and web chat running

The key insight: You're not reimplementing the bot - you're adding a new frontend (web) to the same backend architecture.

