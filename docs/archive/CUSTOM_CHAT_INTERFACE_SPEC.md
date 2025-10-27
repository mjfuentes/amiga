# Custom Chat Interface - Design & Scope

**Project**: AMIGA (Autonomous Modular Interactive Graphical Agent) → Custom Web Chat Interface
**Goal**: Replace Telegram dependency with custom web-based chat interface
**Created**: 2025-10-21
**Status**: Design & Scoping Phase

---

## Executive Summary

Replace current Telegram-based chat interface with custom web application while preserving all core functionality. This enables:

- **No platform lock-in**: Full control over UI/UX
- **Rich interactions**: File uploads, code snippets, real-time updates beyond Telegram limits
- **Better integration**: Seamless connection with existing Flask monitoring dashboard
- **Enhanced features**: Multi-file uploads, inline code editing, better voice transcription UI

---

## Current Architecture Analysis

### Core Components (45 Python files)

**Primary Interface Layer**:
- `main.py` (300+ lines): Telegram bot handlers, command routing, authorization
  - Commands: /start, /status, /clear, /workspace, /usage, /restart, /stopall
  - Handlers: Text, voice, image messages
  - Authorization: ALLOWED_USERS environment variable
  - Rate limiting: 30 msg/min, 500/hour per user

**Backend Services** (reusable):
- `claude_api.py`: Claude Haiku 4.5 routing & Q&A (API-based, fast)
- `claude_interactive.py`: Claude Sonnet 4.5 coding sessions (CLI-based, powerful)
- `session.py`: Conversation history (10 msgs max)
- `tasks.py`: Background task tracking (SQLite)
- `cost_tracker.py`: API usage tracking
- `agent_pool.py`: Bounded worker pool (3 concurrent)
- `message_queue.py`: Per-user message serialization
- `formatter.py`: Response formatting (chunking, code blocks)

**Monitoring Dashboard** (already web-based):
- `monitoring_server.py`: Flask + SSE (port 3000)
- `templates/dashboard.html`: Real-time task/session monitoring
- REST API: `/api/tasks/*`, `/api/metrics/*`, `/api/stream/metrics`

**Dependencies**:
- `python-telegram-bot>=21.0`: **Only component requiring replacement**
- Flask, anthropic, whisper, sqlite3: All reusable

---

## Feature Requirements

### Must-Have (MVP)

**Authentication & Authorization**:
- Login system (username/password or OAuth)
- User whitelist (equivalent to ALLOWED_USERS)
- Session management (JWT tokens)

**Chat Interface**:
- Real-time messaging (WebSocket or SSE)
- Text input with multiline support
- Message history scrolling
- Typing indicators
- Status indicators (thinking/processing)

**Message Types**:
- Text messages (plain & markdown)
- Code blocks with syntax highlighting
- Voice messages (file upload + transcription)
- Image uploads (drag & drop + paste)
- File attachments (download links)

**Core Commands**:
- `/start`: Clear session
- `/status`: Active tasks
- `/clear`: Clear history
- `/workspace <name>`: Switch repository
- `/usage`: Cost tracking
- `/stopall`: Cancel all tasks

**Backend Integration**:
- Reuse existing session management
- Reuse Claude API routing
- Reuse task execution pipeline
- Reuse cost tracking

### Nice-to-Have (Post-MVP)

**Enhanced UI**:
- Dark/light theme toggle
- Code snippet editing inline
- Multi-file batch upload
- Progress bars for long tasks
- Task output preview panel

**Advanced Features**:
- Multi-session support (tabs for different repos)
- Voice recording directly in browser
- Collaborative sessions (multiple users)
- Desktop notifications
- Mobile-responsive layout

**Developer Tools**:
- API key management UI
- Cost limit configuration UI
- Workspace management UI
- Agent/workflow selection dropdown

---

## Technical Architecture

### Stack Recommendation

**Frontend**:
- **Framework**: React + TypeScript
  - **Why**: Component reusability, strong typing, excellent ecosystem
  - **Alternatives**: Vue.js (simpler), Svelte (faster)
- **Real-time**: Socket.IO client
- **UI Components**: Tailwind CSS + shadcn/ui
- **Code Highlighting**: Prism.js or Highlight.js
- **Markdown**: marked.js (already used in dashboard)

**Backend**:
- **Framework**: Flask (already in use) or FastAPI (better async)
  - **Recommendation**: **FastAPI** for native WebSocket + async support
  - **Why**: Better than Flask for real-time, same Python ecosystem
- **WebSocket**: python-socketio or FastAPI WebSockets
- **Database**: SQLite (already used) + SQLAlchemy
- **Auth**: JWT tokens (PyJWT) or OAuth2 (Authlib)

**Deployment**:
- **Development**: Vite dev server (React) + uvicorn (FastAPI)
- **Production**: Nginx → FastAPI (Gunicorn + Uvicorn workers)
- **Static Assets**: Nginx serves React build

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Custom Chat UI                          │
│              (React + TypeScript + Tailwind)                 │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Chat Panel   │  │ Task Monitor │  │ Settings     │      │
│  │              │  │              │  │              │      │
│  │ • Messages   │  │ • Active     │  │ • Workspace  │      │
│  │ • Input      │  │ • Completed  │  │ • Cost       │      │
│  │ • Upload     │  │ • Logs       │  │ • API Keys   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└──────────────────┬──────────────────────────────────────────┘
                   │ WebSocket / REST API
┌──────────────────▼──────────────────────────────────────────┐
│                   FastAPI Backend                            │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  WebSocket Manager (Real-time messaging)             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Auth     │  │ Session  │  │ Message  │  │ Task     │   │
│  │ Handler  │  │ Manager  │  │ Router   │  │ Monitor  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │       Existing Backend Services (Reused)               │ │
│  │                                                        │ │
│  │  • claude_api.py (Haiku routing)                      │ │
│  │  • claude_interactive.py (Sonnet sessions)            │ │
│  │  • session.py (conversation history)                  │ │
│  │  • tasks.py (background tasks)                        │ │
│  │  • cost_tracker.py (usage tracking)                   │ │
│  │  • agent_pool.py (worker pool)                        │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                   │ Claude API / CLI
┌──────────────────▼──────────────────────────────────────────┐
│              Claude AI Services                              │
│                                                              │
│  • Haiku 4.5: Fast Q&A routing                              │
│  • Sonnet 4.5: Code execution                               │
│  • Opus 4.5: Research & debugging                           │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

**Message Send**:
1. User types message in React chat panel
2. WebSocket sends to FastAPI backend
3. Auth middleware validates JWT token
4. Message router invokes appropriate handler:
   - Quick Q&A → `claude_api.py` (Haiku)
   - Coding task → `tasks.py` + `claude_interactive.py` (Sonnet)
5. Response streams back via WebSocket
6. React updates chat UI in real-time

**Task Execution**:
1. User message triggers BACKGROUND_TASK routing
2. Task created in SQLite (`tasks.py`)
3. Agent pool assigns worker (`agent_pool.py`)
4. Claude Code CLI session started (`claude_interactive.py`)
5. Progress updates sent via WebSocket (SSE alternative)
6. Completion triggers notification in UI

---

## Implementation Plan

### Phase 1: Backend API (Week 1-2)

**Goal**: FastAPI backend with WebSocket support, reusing existing services

**Tasks**:
1. Setup FastAPI project structure
2. Implement WebSocket connection handler
3. Create auth system (JWT tokens)
4. Port message routing from `main.py`:
   - Text handler → `/ws/message`
   - Command handler → `/api/command`
   - File upload → `/api/upload`
5. Integrate existing services:
   - Session manager
   - Claude API routing
   - Task execution
   - Cost tracking
6. Add REST endpoints:
   - `/api/auth/login`
   - `/api/auth/logout`
   - `/api/session/history`
   - `/api/tasks/*` (reuse monitoring_server endpoints)
7. Testing with Postman/curl

**Deliverables**:
- Working FastAPI backend
- WebSocket echo/test endpoint
- Auth system functional
- Existing features accessible via API

### Phase 2: Frontend Foundation (Week 3)

**Goal**: React chat interface with basic messaging

**Tasks**:
1. Setup Vite + React + TypeScript
2. Configure Tailwind CSS + shadcn/ui
3. Implement core components:
   - Login page
   - Chat layout (sidebar + main panel)
   - Message list (scrollable)
   - Input box (multiline textarea)
4. WebSocket client integration (Socket.IO or native)
5. Message rendering:
   - Plain text
   - Markdown preview
   - Code blocks with syntax highlighting
6. Basic styling (dark theme)

**Deliverables**:
- React app connecting to FastAPI
- Real-time message send/receive
- Login/logout flow
- Basic chat UI functional

### Phase 3: Feature Parity (Week 4-5)

**Goal**: Match all Telegram bot features

**Tasks**:
1. File uploads:
   - Drag & drop
   - Image paste from clipboard
   - Voice file upload + transcription display
2. Command system:
   - `/start`, `/clear`, `/status`, etc.
   - Autocomplete dropdown
3. Task monitoring:
   - Active tasks list
   - Real-time status updates
   - Task output preview
4. Cost tracking display:
   - Usage stats
   - Daily/monthly limits
5. Workspace switching:
   - Dropdown selector
   - Context preservation
6. Error handling:
   - Connection lost UI
   - Retry mechanism
   - User-friendly error messages

**Deliverables**:
- Feature parity with Telegram bot
- All commands working
- File uploads functional
- Task monitoring integrated

### Phase 4: Polish & Launch (Week 6)

**Goal**: Production-ready deployment

**Tasks**:
1. UI/UX improvements:
   - Loading states
   - Animations
   - Mobile responsive
2. Testing:
   - Unit tests (Jest)
   - Integration tests (Playwright)
   - Load testing (concurrent users)
3. Documentation:
   - User guide
   - API documentation
   - Deployment guide
4. Deployment:
   - Docker containerization
   - Nginx configuration
   - SSL/TLS setup
   - Environment config

**Deliverables**:
- Production deployment
- User documentation
- Monitoring/logging setup
- Backup/recovery plan

---

## Migration Strategy

### Parallel Operation

**Phase 1-3**: Run both interfaces simultaneously
- Telegram bot remains primary
- Custom interface in beta testing
- Shared backend services (SQLite, tasks, sessions)
- Separate user sessions (no cross-contamination)

**Phase 4**: Gradual migration
- Announce new interface to users
- Provide onboarding guide
- Monitor usage metrics
- Collect feedback

**Phase 5**: Deprecation
- Set Telegram bot to read-only (redirect to web)
- Archive Telegram-specific code
- Remove `python-telegram-bot` dependency

### Rollback Plan

- Keep Telegram bot code in separate branch
- Database schema remains compatible
- Can revert in <1 hour if critical issues

---

## Risk Assessment

### Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| WebSocket connection instability | High | Medium | Implement reconnection logic, fallback to polling |
| Session management complexity | Medium | Low | Reuse existing `session.py`, add JWT layer |
| Real-time performance at scale | Medium | Low | Load test early, implement caching |
| Browser compatibility issues | Low | Medium | Target modern browsers only (no IE) |
| Security vulnerabilities (XSS, CSRF) | High | Medium | Security audit, input sanitization, CSP headers |

### Operational Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| User adoption resistance | Medium | Low | Provide migration guide, parallel operation |
| Deployment complexity | Medium | Medium | Docker + scripts, test on staging |
| Increased hosting costs | Low | Low | Static frontend (cheap), backend unchanged |
| Maintenance burden | Medium | Low | Well-documented, TypeScript reduces bugs |

---

## Resource Requirements

### Development

**Estimated Effort**: 6 weeks (1 developer full-time)

**Breakdown**:
- Backend API: 2 weeks
- Frontend foundation: 1 week
- Feature parity: 2 weeks
- Polish & deploy: 1 week

**Skills Needed**:
- Python (FastAPI, async)
- TypeScript/React
- WebSocket programming
- Docker/deployment

### Infrastructure

**Development**:
- Local machine sufficient
- Port 3000 (monitoring), 8000 (chat API), 5173 (Vite dev)

**Production**:
- VPS/Cloud instance (same as current)
- Nginx reverse proxy
- SSL certificate (Let's Encrypt)
- Domain name (optional subdomain)

### Ongoing Maintenance

- **Minimal**: Most code reused from existing bot
- **Security updates**: React/FastAPI dependencies
- **Feature additions**: User-requested improvements

---

## Success Metrics

### MVP Success (End of Phase 3)

- ✅ All Telegram features replicated
- ✅ <500ms message latency
- ✅ 99% WebSocket uptime in testing
- ✅ Zero data loss in sessions/tasks
- ✅ Mobile-responsive layout

### Production Success (3 months post-launch)

- ✅ 100% user migration from Telegram
- ✅ <1s message response time (p95)
- ✅ <5 bug reports per month
- ✅ Positive user feedback (survey)

---

## Open Questions

1. **Authentication method**: Username/password or OAuth (GitHub, Google)?
   - **Recommendation**: Start with simple username/password, add OAuth later

2. **Hosting**: Self-hosted or cloud (Vercel/Render/Railway)?
   - **Recommendation**: Self-hosted for cost control, migrate to cloud if needed

3. **Mobile app**: Build native app or PWA?
   - **Recommendation**: PWA first (cheaper), native app if user demand

4. **Multi-user support**: Single user or multi-tenant from day 1?
   - **Recommendation**: Single user MVP, multi-tenant post-launch

5. **Telegram bot deprecation timeline**: Immediate or gradual?
   - **Recommendation**: 2-3 month parallel operation, then deprecate

---

## Next Steps

1. **Approve scope & architecture**: Review this document, confirm approach
2. **Prototype backend**: Build FastAPI WebSocket echo server (1 day)
3. **Prototype frontend**: Build React chat UI mockup (1 day)
4. **Full implementation**: Follow Phase 1-4 plan (6 weeks)

---

## Appendix: Key Code Modules to Preserve

**Must keep (backend services)**:
- `claude_api.py` - Haiku routing
- `claude_interactive.py` - Sonnet sessions
- `session.py` - History management
- `tasks.py` - Task tracking
- `cost_tracker.py` - Usage tracking
- `agent_pool.py` - Worker pool
- `database.py` - SQLite abstraction
- `workflow_router.py` - Task routing logic
- `tool_usage_tracker.py` - Metrics

**Can replace (interface layer)**:
- `main.py` - Telegram handlers → FastAPI routes
- `formatter.py` - Telegram formatting → React components
- `message_queue.py` - Telegram rate limits → WebSocket throttling

**Already web-based (integrate)**:
- `monitoring_server.py` - Merge into new API
- `templates/dashboard.html` - Integrate into React app

---

**End of Specification**
