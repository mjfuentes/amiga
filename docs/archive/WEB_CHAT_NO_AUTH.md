# Web Chat - No Authentication Mode

## Overview

The web chat interface at `http://localhost:3000/chat` now works without authentication. It automatically connects as the admin user from the environment configuration.

## Configuration

**Admin User ID**: Taken from first user in `ALLOWED_USERS` environment variable (currently: `521930094`)

## How It Works

### Frontend (React App)

**Location**: `web_chat/frontend/` (source) → `telegram_bot/static/chat/` (built)

**Changes Made**:
1. **useAuth.ts**: Auto-authenticates with admin user ID, bypassing JWT login
2. **useSocket.ts**: Connects with dummy token (`dummy-token-{ADMIN_USER_ID}`)
3. **Environment**: Added `REACT_APP_ADMIN_USER_ID=521930094` to `.env`

### Backend (Flask/SocketIO)

**Location**: `telegram_bot/monitoring_server.py`

**Changes Made**:
- Modified `handle_connect()` to accept dummy tokens
- Dummy token format: `dummy-token-{user_id}`
- Extracts user ID from token and auto-authenticates
- Falls back to real JWT verification for other clients

## Testing

### Manual Test (Browser)
1. Open `http://localhost:3000/chat` in browser
2. Should show chat interface immediately (no login screen)
3. Send a message - should receive response from Claude

### Programmatic Test
```python
import socketio

sio = socketio.Client()
dummy_token = "dummy-token-521930094"

sio.connect(
    'http://localhost:3000',
    auth={'token': dummy_token},
    transports=['polling']
)

sio.emit('message', {'message': 'Hello!'})
# Wait for response...
```

## Rebuilding Frontend

If you modify the React source code:

```bash
cd web_chat/frontend
npm run build
rm -rf ../../telegram_bot/static/chat/*
cp -r build/* ../../telegram_bot/static/chat/
```

**Important**: The build is configured with `"homepage": "/chat"` in `package.json` to match the `/chat` route.

## Security Note

This no-auth mode is intended for:
- Single-user environments
- Development/testing
- Local deployments

For production with multiple users, the original JWT authentication should be used.

## Files Modified

- `web_chat/frontend/src/hooks/useAuth.ts` - Auto-authentication
- `web_chat/frontend/src/hooks/useSocket.ts` - Dummy token connection
- `web_chat/frontend/.env` - Admin user ID configuration
- `web_chat/frontend/package.json` - Homepage path
- `telegram_bot/monitoring_server.py` - Dummy token handling
- `telegram_bot/static/chat/*` - Rebuilt React app
- `.gitignore` - Exclude large JS build files

## Verification

```bash
# Check server is running
curl http://localhost:3000/health

# Open chat interface
open http://localhost:3000/chat
```

