# AgentLab Chat Frontend

Modern React chat interface using **@chatscope/chat-ui-kit-react** that connects to `monitoring_server.py` backend.

## Architecture

- **UI Library:** @chatscope/chat-ui-kit-react (open-source chat components)
- **Framework:** React 19 + TypeScript
- **WebSocket:** Socket.IO client
- **Markdown:** react-markdown with syntax highlighting
- **Backend:** monitoring_server.py (existing Flask + SocketIO server)

## Features

✅ Professional chat UI inspired by Stream Chat
✅ Real-time WebSocket communication
✅ JWT authentication + no-auth development mode
✅ Markdown rendering with code syntax highlighting
✅ Task status updates
✅ Session persistence
✅ Responsive design

## Quick Start

### Development Mode

```bash
# Install dependencies (first time only)
npm install

# Start dev server
npm start
```

Open http://localhost:3000 - connects to monitoring_server.py at http://localhost:3000

### Building for Production

```bash
# Build React app
npm run build

# Deploy to telegram_bot/static/chat/
rm -rf ../static/chat/*
cp -r build/* ../static/chat/
```

Then access at: http://localhost:3000/chat (via monitoring_server.py)

## Configuration

**File:** `.env`

```bash
# Backend URLs (monitoring_server.py)
REACT_APP_API_URL=http://localhost:3000/api
REACT_APP_SOCKET_URL=http://localhost:3000

# No-auth mode (auto-login as admin)
REACT_APP_NO_AUTH_MODE=true
REACT_APP_ADMIN_USER_ID=521930094
```

### No-Auth Mode

For development, `NO_AUTH_MODE=true` auto-authenticates with a dummy token:
- No login screen
- Connects as admin user (ADMIN_USER_ID)
- monitoring_server.py accepts `dummy-token-{user_id}` format

For production, set `NO_AUTH_MODE=false` to require real JWT authentication.

## API Integration

Connects to existing **monitoring_server.py** endpoints - NO separate backend needed.

### REST API
- `POST /api/auth/register` - Create account
- `POST /api/auth/login` - Get JWT token
- `GET /api/chat/history` - Get conversation history

### WebSocket Events
- `connect` - Authenticate with JWT
- `message` - Send chat message
- `response` - Receive assistant response
- `task_update` - Task status changed

## Components

Uses **@chatscope/chat-ui-kit-react** for professional UI:
- MainContainer, ChatContainer
- MessageList, Message
- MessageInput
- TypingIndicator

## Development

```bash
# Start with hot reload
npm start

# Build for production
npm run build

# Type checking
npx tsc --noEmit
```

## Deployment

Build and copy to `static/chat/`:

```bash
npm run build && rm -rf ../static/chat/* && cp -r build/* ../static/chat/
```

Access at **http://localhost:3000/chat**

## License

Same as parent AgentLab project.
