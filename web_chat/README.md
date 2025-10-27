# AgentLab Web Chat Interface

Web-based chat interface to replace/supplement Telegram bot integration.

## Architecture

- **Backend:** Flask + Flask-SocketIO (WebSocket for real-time communication)
- **Frontend:** React + TypeScript + Socket.IO client
- **Auth:** JWT tokens with bcrypt password hashing
- **Database:** SQLite (reuses existing telegram_bot data structure)

## Features

✅ Real-time WebSocket communication
✅ JWT authentication with login/register
✅ Markdown message rendering with syntax highlighting
✅ Task creation and real-time status updates
✅ Session persistence across reconnects
✅ Reuses 70% of Telegram bot backend logic

## Directory Structure

```
web_chat/
├── server.py                 # Flask-SocketIO server
├── auth.py                   # JWT authentication
├── api_routes.py             # REST API endpoints
├── requirements.txt          # Python dependencies
├── data/
│   └── users.json            # User database
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Main app component
│   │   ├── hooks/
│   │   │   ├── useAuth.ts    # Authentication hook
│   │   │   ├── useSocket.ts  # WebSocket connection hook
│   │   │   └── useChat.ts    # Chat state management hook
│   │   └── components/
│   │       ├── AuthModal.tsx      # Login/register modal
│   │       ├── ChatWindow.tsx     # Main chat interface
│   │       └── MessageBubble.tsx  # Message display component
│   └── package.json          # Frontend dependencies
└── README.md                 # This file
```

## Setup

### Prerequisites

- **Python 3.10+** (REQUIRED - 3.9 will fail due to PEP 604 type unions in telegram_bot modules)
- Node.js 18+
- npm or yarn

### Backend Setup

```bash
# Navigate to web_chat directory
cd web_chat

# Create virtual environment (ensure Python 3.10+)
python3 --version  # Must show 3.10 or higher
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify all imports work (optional but recommended)
python verify_imports.py

# Set environment variables (create .env file from example)
cp .env.example .env
# Edit .env with your actual values:
# - JWT_SECRET_KEY (generate a random secret)
# - ANTHROPIC_API_KEY (from your Anthropic account)
# - WORKSPACE_PATH (path to your workspace directory)

# Run server
python server.py
```

Server will start on http://localhost:5000

### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

Frontend will start on http://localhost:3000 (or 3001 if 3000 is taken)

## Usage

### 1. Register/Login

On first visit, you'll see a login modal. Register a new account or login with existing credentials.

### 2. Chat Interface

Once logged in, you'll see the main chat interface:
- Type messages in the input field at the bottom
- Messages appear in real-time
- Code blocks are syntax highlighted
- Task status updates appear inline

### 3. Background Tasks

When you request a coding task (e.g., "Fix the bug in main.py"), the system will:
1. Create a task via Claude API
2. Show immediate acknowledgment with task ID
3. Execute task in background using Claude Code CLI
4. Send real-time progress updates via WebSocket
5. Display final result when complete

## API Endpoints

### Authentication

- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login existing user
- `GET /api/auth/verify` - Verify JWT token

### Chat

- `GET /api/chat/history` - Get chat history
- `POST /api/chat/clear` - Clear chat history

### Tasks

- `GET /api/tasks` - Get active tasks
- `GET /api/tasks/<task_id>` - Get specific task

### Usage

- `GET /api/usage` - Get API cost usage statistics

## WebSocket Events

### Client → Server

- `connect` - Authenticate with JWT token
- `message` - Send chat message
- `typing` - Notify typing status
- `ping` - Keepalive

### Server → Client

- `connected` - Authentication successful
- `response` - Message response from assistant
- `task_update` - Task status changed
- `task_progress` - Task progress update
- `task_completed` - Task finished successfully
- `task_failed` - Task failed with error
- `error` - Error occurred

## Development

### Backend

```bash
# Run with debug mode
DEBUG=True python server.py

# View logs
tail -f ../telegram_bot/logs/bot.log
```

### Frontend

```bash
# Start dev server with hot reload
npm start

# Build for production
npm run build
```

## Testing

### Manual Testing Checklist

Backend:
- [ ] Server starts without errors
- [ ] User registration works
- [ ] User login works
- [ ] JWT token verification works
- [ ] WebSocket connection established
- [ ] Message sending/receiving works
- [ ] Task creation works

Frontend:
- [ ] Login modal displays
- [ ] Registration form works
- [ ] Login form works
- [ ] Chat window displays after login
- [ ] Messages display correctly
- [ ] Markdown rendering works
- [ ] Code syntax highlighting works
- [ ] WebSocket connection indicator updates
- [ ] Logout works

### Unit Tests (Future)

```bash
# Backend tests
pytest web_chat/tests/

# Frontend tests
cd frontend && npm test
```

## Deployment

### Development

Use separate terminals:

```bash
# Terminal 1: Backend
cd web_chat
source venv/bin/activate
python server.py

# Terminal 2: Frontend
cd web_chat/frontend
npm start
```

### Production (Docker)

```bash
# Build and run with Docker Compose
docker-compose up -d
```

See `WEB_CHAT_SPEC.md` for detailed deployment configuration.

## Security

### Implemented

✅ JWT token authentication
✅ bcrypt password hashing (12 rounds)
✅ Input sanitization (reuses telegram_bot/claude_api.py)
✅ Prompt injection detection
✅ Path traversal prevention
✅ CORS configuration

### TODO

- [ ] Rate limiting (flask-limiter)
- [ ] CSRF protection (flask-wtf)
- [ ] HTTPS/SSL in production
- [ ] Session expiration/refresh tokens
- [ ] IP-based rate limiting

## Troubleshooting

### Backend Issues

**"Python version too old" or "unsupported operand type(s) for |"**
- Your venv uses Python 3.9, but Python 3.10+ is required
- Solution: Recreate venv with Python 3.10+:
  ```bash
  rm -rf venv
  python3 -m venv venv  # Ensure this uses Python 3.10+
  source venv/bin/activate
  pip install -r requirements.txt
  ```

**"ModuleNotFoundError: No module named 'anthropic'"**
- Missing dependencies in venv
- Solution: `pip install -r requirements.txt`

**"ModuleNotFoundError: No module named 'session'"**
- Ensure telegram_bot directory is accessible
- Check `sys.path.insert()` in server.py

**"Connection refused"**
- Check server is running on port 5000
- Check CORS origins in server.py

**"Unauthorized" on WebSocket connect**
- Check JWT_SECRET_KEY matches between backend and frontend
- Verify token in browser localStorage

### Frontend Issues

**"WebSocket connection failed"**
- Check backend server is running
- Check REACT_APP_SOCKET_URL in .env
- Open browser console for detailed error

**"Cannot read property 'user_id'"**
- Check token verification response format
- Check API endpoint returns correct user object

**Blank screen after login**
- Check browser console for errors
- Verify all components imported correctly
- Check React DevTools for component tree

## Environment Variables

### Backend (.env in web_chat/)

See `.env.example` for full list of configuration options.

**Required variables:**
```bash
JWT_SECRET_KEY=your-secret-key-change-in-prod
ANTHROPIC_API_KEY=your-anthropic-api-key
WORKSPACE_PATH=/path/to/workspace
```

**Optional variables:**
```bash
PORT=5000
DEBUG=False
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
DAILY_COST_LIMIT=100
MONTHLY_COST_LIMIT=1000
```

**Setup:**
```bash
cp .env.example .env
# Edit .env with your values
```

### Frontend (.env in web_chat/frontend/)

See `frontend/.env.example` for configuration.

**Required variables:**
```bash
REACT_APP_API_URL=http://localhost:5000/api
REACT_APP_SOCKET_URL=http://localhost:5000
```

**Setup:**
```bash
cd frontend
cp .env.example .env
# Edit if you're using different ports
```

## Migration from Telegram Bot

The web chat interface reuses existing backend logic:

**Shared modules (via import):**
- `session.py` - Session management
- `claude_api.py` - Claude API integration
- `tasks.py` - Task lifecycle
- `agent_pool.py` - Worker pool
- `cost_tracker.py` - Cost tracking
- `database.py` - SQLite operations
- `orchestrator.py` - Repository discovery

**Telegram bot continues to work** - Both interfaces can run simultaneously using the same data directory.

## Future Enhancements

- [ ] Voice input (Web Speech API)
- [ ] File upload support
- [ ] Image analysis
- [ ] Multi-workspace support
- [ ] Collaborative chat (multiple users in same workspace)
- [ ] Message search
- [ ] Export chat history
- [ ] Mobile responsive design improvements
- [ ] Dark mode theme
- [ ] Keyboard shortcuts

## License

Same as parent AgentLab project.

## Support

See main project README for issue reporting and support channels.
