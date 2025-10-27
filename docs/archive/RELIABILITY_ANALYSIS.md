# Bot Reliability Analysis & 24/7 Uptime Strategy

**Analysis Date:** October 17, 2025
**Bot Version:** agentlab Telegram Bot
**Current Status:** Running under launchd on macOS

## Executive Summary

The bot has **good fundamental architecture** with proper process management, restart capabilities, and error handling. However, there are **critical single points of failure** that could lead to complete service outage, especially when Telegram or mobile access is unavailable.

**Key Finding:** Worker pool initialization race condition has caused recent failures. Critical access path through Telegram only creates risk when mobile/Telegram is down.

---

## 1. Architecture Analysis

### Current Stack
```
┌─────────────────────────────────────────┐
│         Telegram Bot API                │
│    (Single Access Point - RISK!)        │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│      main.py - Bot Entry Point          │
│   - Message handlers & routing          │
│   - Command processing (/start, etc)    │
└─────────────────────────────────────────┘
                    ↓
┌──────────────┬──────────────┬───────────┐
│ Session Mgr  │ Message Queue│ Worker Pool│
│ (sessions.   │ (Sequential  │ (3 workers)│
│  json)       │  per-user)   │ Background │
└──────────────┴──────────────┴───────────┘
                    ↓
┌─────────────────────────────────────────┐
│    Claude Interactive Sessions          │
│  (claude_interactive.py - spawns CLI)   │
│    Background task execution            │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         File System & Git               │
│    (data/, logs/, repositories)         │
└─────────────────────────────────────────┘
```

### Process Management (launchd)
- **Service:** `com.agentlab.telegrambot`
- **Auto-restart:** Yes (KeepAlive with SuccessfulExit=false)
- **Throttle:** 10 seconds between restarts
- **Logs:** Combined stdout/stderr to `logs/bot.log`
- **Manual restart:** `/restart` command (exit code 42)

### Strengths
1. ✅ **Persistent state** - Sessions, tasks, and cost tracking survive restarts
2. ✅ **Task recovery** - PID tracking allows detection of orphaned tasks after restart
3. ✅ **Sequential processing** - Message queue prevents race conditions per user
4. ✅ **Bounded concurrency** - Worker pool limits resource usage (3 workers max)
5. ✅ **Workflow enforcement** - Pre-commit hooks, tests validation before commits
6. ✅ **Rate limiting** - 30 req/min, 500 req/hour protection
7. ✅ **Cost tracking** - Daily/monthly limits prevent runaway API costs
8. ✅ **Graceful restart** - User notification on `/restart` command

---

## 2. Critical Issues Found

### 🔴 CRITICAL: Worker Pool Race Condition
**Log Evidence:**
```
2025-10-17 14:20:44 ERROR - Worker pool not started
2025-10-17 14:20:50 ERROR - Worker pool not started
2025-10-17 14:31:11 ERROR - Worker pool not started
```

**Problem:** Tasks submitted before `post_init` completes
- Worker pool starts in `post_init()` after bot commands registered
- Messages can arrive and queue tasks BEFORE worker pool is ready
- Causes: "Worker pool not started" errors, user requests fail

**Impact:** Bot appears to work but silently fails to process requests

**Root Cause in main.py:1574-1576:**
```python
# Start worker pool for background task execution
logger.info("Starting background worker pool...")
await worker_pool.start()
```
This runs AFTER bot is already polling and accepting messages.

### 🔴 CRITICAL: Single Access Point (Telegram Only)
**Problem:** No alternative access when Telegram/mobile unavailable
- 100% dependent on Telegram API for all interactions
- If Telegram down OR user's mobile device inaccessible → complete lockout
- Cannot check logs, status, or issue commands
- Bot keeps running but is unreachable

**Scenario:** You're away from your mobile device and Telegram has an outage → bot is completely inaccessible even though server is running fine.

### 🟡 MEDIUM: Restart State Age Check Too Aggressive
**Log Evidence:**
```
2025-10-17 13:54:15 WARNING - Restart state too old (1760504154s), discarding
```

**Problem:** Restart state validation has unrealistic timestamp (1.7 billion seconds = 55 years)
- Likely timestamp format mismatch or corruption
- Current limit: 5 minutes (300s)
- When exceeded, restart notification is skipped (user sees no feedback)

### 🟡 MEDIUM: Stale In-Progress Tasks After Restart
**Issue:** Tasks marked "in_progress" during restart
- Recovery: Checks if PID is still alive
- ✅ If alive: Task continues
- ✅ If dead: Marked as failed with "Task cancelled due to bot restart"
- **Risk:** PID reuse could incorrectly mark unrelated process as "still running"

### 🟢 LOW: Resource Leak Warning
```
resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
```
Indicates multiprocessing cleanup issue (minor memory leak on restart)

---

## 3. Single Points of Failure (SPOF)

| Component | Risk | Impact if Failed | Mitigation Status |
|-----------|------|------------------|-------------------|
| **Telegram API** | 🔴 HIGH | Complete service unavailable | ❌ None |
| **Worker Pool Init** | 🔴 HIGH | Requests fail silently | ❌ None |
| **launchd** | 🟡 MEDIUM | Bot stays down | ✅ Auto-restart |
| **sessions.json** | 🟡 MEDIUM | History lost, sessions reset | ⚠️ No backups |
| **tasks.json** | 🟡 MEDIUM | Task tracking lost | ⚠️ No backups |
| **File System** | 🟡 MEDIUM | State corruption | ⚠️ No backups |
| **Claude API** | 🟡 MEDIUM | Tasks fail, chat works | ✅ Graceful fallback |
| **Network** | 🟡 MEDIUM | Bot unreachable | ✅ launchd retries |
| **Python venv** | 🟢 LOW | Bot won't start | ✅ Logged, detectable |

---

## 4. Historical Reliability Issues (from Git)

### Recent Fixes (Last 4 Weeks)
1. **Restart functionality** - Multiple fixes to make `/restart` reliable
2. **PID tracking** - Fixed to save immediately when process starts (not after completion)
3. **Orchestrator loading** - CRITICAL FIX: orchestrator.md was never being loaded
4. **Worker pool not started** - Current issue (detected in logs)
5. **Message queue priority** - Added priority system for /restart, /start commands

### Patterns Observed
- **Restart complexity** - 4+ commits fixing restart behavior (indicates fragility)
- **State management** - Frequent issues with task/session persistence
- **Race conditions** - Multiple fixes for timing/ordering issues
- **Import errors** - Past issues with missing modules (e.g., 'a' module import error)

---

## 5. Graceful Degradation Strategy

### Tier 1: Prevent Failures (Proactive)
1. **Fix worker pool race condition** (IMMEDIATE)
   ```python
   # In main.py, move worker_pool.start() to BEFORE application creation
   async def main():
       # Start worker pool FIRST
       await worker_pool.start()

       # THEN create application
       application = Application.builder().token(TOKEN).build()
   ```

2. **Add health check endpoint** (HTTP server)
   ```python
   # Simple HTTP server on localhost:8080/health
   # Returns: {"status": "ok", "uptime": 123, "active_tasks": 2}
   # Enables monitoring without Telegram
   ```

3. **Add backup access channel**
   - **Option A:** Local Unix socket for CLI access
     ```bash
     echo "status" | nc -U /tmp/agentlab.sock
     ```
   - **Option B:** SSH + tmux for emergency console
   - **Option C:** Local web dashboard (read-only status)

4. **Watchdog monitoring**
   ```python
   # External process that checks:
   # - Bot process alive (PID check)
   # - Responds to health check
   # - Log file growing (activity check)
   # - Telegram API reachable
   # Alerts: local notification, email, SMS
   ```

### Tier 2: Detect Failures (Monitoring)
1. **Enhanced logging**
   - Structured logs (JSON format)
   - Log aggregation (ship to external service)
   - Alert on ERROR patterns

2. **Metrics collection**
   ```python
   # Track and expose:
   # - Messages processed/min
   # - Task success/failure rate
   # - Worker pool queue depth
   # - API response times
   # - Memory/CPU usage
   ```

3. **Dead man's switch**
   - Periodic heartbeat to external service
   - If heartbeat stops → alert sent
   - Simple: cron job + curl to healthcheck.io

### Tier 3: Recover from Failures (Resilience)
1. **Automatic backups**
   ```python
   # Backup data/*.json every hour
   # Keep last 24 backups (1 day retention)
   # On corruption: auto-restore from latest backup
   ```

2. **Task retry logic** (ALREADY EXISTS ✅)
   - `/retry` command works well
   - Could add: auto-retry on failure (max 3 attempts)

3. **Graceful degradation modes**
   ```python
   # When Claude API down:
   # - Queue tasks for later
   # - Respond with "API temporarily unavailable"
   #
   # When Telegram slow:
   # - Increase timeouts
   # - Reduce message size
   #
   # When disk full:
   # - Archive old logs
   # - Clear completed tasks > 7 days
   ```

4. **Circuit breaker pattern**
   ```python
   # For external dependencies (Claude API, Telegram):
   # - Track failure rate
   # - If > 50% failures in 1 min → open circuit
   # - Stop making requests for 30s
   # - Try one request after 30s (half-open)
   # - If success → close circuit (resume)
   ```

### Tier 4: Survive Failures (Redundancy)
1. **Multi-server deployment** (ADVANCED)
   - Primary + standby bot instances
   - Shared state (Redis/PostgreSQL instead of JSON files)
   - Load balancer / failover logic
   - **Overkill for current scale**

2. **Container deployment** (Docker + Kubernetes)
   - Auto-restart on failure
   - Resource limits
   - Easy rollback
   - **Not needed on macOS launchd**

---

## 6. Immediate Action Plan

### Phase 1: Critical Fixes (This Week)
1. ✅ **Fix worker pool race condition**
   - Move `worker_pool.start()` earlier in initialization
   - Add startup barrier: don't accept messages until ready
   - Test: Start bot, immediately send message

2. ✅ **Add health check endpoint**
   - Simple HTTP server on localhost:8080
   - Returns JSON with status, uptime, metrics
   - Test: `curl localhost:8080/health`

3. ✅ **Fix restart state timestamp**
   - Use consistent timestamp format (Unix epoch)
   - Validate on load, discard if corrupt
   - Test: `/restart` command, verify notification

### Phase 2: Monitoring (Next Week)
4. **Add watchdog script**
   - Check bot health every 60s
   - Alert on failure (local notification)
   - Auto-restart if hung (no response for 5 min)

5. **Backup automation**
   - Hourly backup of data/*.json
   - Keep 24 backups (rotating)
   - Test recovery: corrupt data file, verify auto-restore

6. **Structured logging**
   - JSON format logs
   - Include context: user_id, task_id, request_id
   - Log rotation (keep last 7 days)

### Phase 3: Alternative Access (Nice to Have)
7. **Local CLI tool**
   - Unix socket or HTTP API
   - Commands: status, logs, restart, task list
   - Usage: `agentlab-cli status`

8. **Email/SMS alerts**
   - On critical errors (bot crash, API limits hit)
   - Weekly summary report
   - Integration: Twilio (SMS) or SendGrid (email)

---

## 7. Recommended Architecture Changes

### High Priority
```python
# 1. Health Check Server (async)
from aiohttp import web

async def health_check(request):
    return web.json_response({
        "status": "ok",
        "uptime": time.time() - START_TIME,
        "worker_pool": worker_pool.get_status(),
        "message_queues": queue_manager.get_status(),
        "active_tasks": len(task_manager.get_active_tasks(all_users=True))
    })

app_http = web.Application()
app_http.router.add_get('/health', health_check)
# Run on port 8080 alongside Telegram bot
```

```python
# 2. Startup Barrier (ensure init complete before accepting messages)
class BotLifecycle:
    def __init__(self):
        self.ready = False
        self.start_time = time.time()

    async def wait_until_ready(self, timeout=30):
        deadline = time.time() + timeout
        while not self.ready and time.time() < deadline:
            await asyncio.sleep(0.1)
        if not self.ready:
            raise RuntimeError("Bot failed to initialize")

lifecycle = BotLifecycle()

# In post_init:
await worker_pool.start()
await message_queue.start()
lifecycle.ready = True  # ONLY set after everything initialized

# In message handlers:
await lifecycle.wait_until_ready()  # Block until ready
```

```python
# 3. Automatic Backup
import shutil
from pathlib import Path

async def backup_state():
    """Backup state files every hour"""
    backup_dir = Path("data/backups")
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for file in ["sessions.json", "tasks.json", "costs.json"]:
        src = Path(f"data/{file}")
        if src.exists():
            dst = backup_dir / f"{file}.{timestamp}"
            shutil.copy2(src, dst)

    # Clean old backups (keep last 24)
    for file_pattern in backup_dir.glob("*.json.*"):
        backups = sorted(backup_dir.glob(f"{file_pattern.stem}.json.*"))
        if len(backups) > 24:
            for old_backup in backups[:-24]:
                old_backup.unlink()

# Schedule backup every hour
job_queue.run_repeating(backup_task, interval=3600, first=3600)
```

### Medium Priority
```python
# 4. Circuit Breaker for Claude API
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=30):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.state = "closed"  # closed, open, half_open
        self.open_until = None

    async def call(self, func, *args, **kwargs):
        if self.state == "open":
            if time.time() < self.open_until:
                raise CircuitOpenError("Circuit breaker is open")
            self.state = "half_open"

        try:
            result = await func(*args, **kwargs)
            if self.state == "half_open":
                self.state = "closed"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                self.open_until = time.time() + self.timeout
            raise
```

---

## 8. Testing & Validation Plan

### Reliability Tests
1. **Worker pool race condition**
   - Start bot
   - Immediately send message (within 1s)
   - Verify: No "Worker pool not started" error

2. **Restart recovery**
   - Start task (long-running)
   - `/restart` during task execution
   - Verify: Task marked as failed OR continues if PID alive

3. **State corruption recovery**
   - Corrupt sessions.json (invalid JSON)
   - Restart bot
   - Verify: Bot starts, creates new sessions.json

4. **Health check**
   - Start bot
   - `curl localhost:8080/health`
   - Verify: Returns valid JSON with status

5. **Backup/restore**
   - Create session/tasks
   - Wait for backup (1 hour)
   - Delete data/*.json
   - Verify: Auto-restore from backup

### Load Tests
1. **Concurrent users**
   - Simulate 5 users sending messages simultaneously
   - Verify: All messages processed in order per user

2. **Worker pool saturation**
   - Queue 10 background tasks
   - Verify: Only 3 run concurrently, rest queued

3. **Rate limiting**
   - Send 40 messages in 1 minute
   - Verify: Rate limit triggered after 30

---

## 9. Monitoring Dashboard (Future)

### Metrics to Track
- **Uptime:** % availability over last 7/30 days
- **Message throughput:** msgs/min, tasks/hour
- **Error rate:** errors/hour, by type
- **Response time:** p50, p95, p99 latencies
- **Resource usage:** CPU, memory, disk
- **API costs:** daily/weekly/monthly spend
- **Worker pool:** queue depth, active workers

### Alerting Rules
```yaml
alerts:
  - name: bot_down
    condition: uptime == 0 for 5 minutes
    severity: critical

  - name: high_error_rate
    condition: error_rate > 10/minute for 5 minutes
    severity: warning

  - name: worker_pool_saturated
    condition: queue_depth > 20 for 10 minutes
    severity: warning

  - name: disk_full
    condition: disk_usage > 90%
    severity: critical

  - name: api_cost_limit
    condition: daily_cost > 0.80 * daily_limit
    severity: warning
```

---

## 10. Conclusion & Recommendations

### Summary
The bot has **solid foundations** but suffers from:
1. 🔴 **Critical race condition** in worker pool initialization
2. 🔴 **Single access point** through Telegram (no fallback)
3. 🟡 **No monitoring/alerting** when issues occur
4. 🟡 **No backups** of critical state files

### Top 3 Priorities
1. **Fix worker pool init race** → Prevents silent failures
2. **Add health check endpoint** → Enables monitoring without Telegram
3. **Implement automatic backups** → Prevents data loss

### Long-Term Vision (24/7 Reliability)
- **Target: 99.9% uptime** (< 45 min downtime/month)
- **Multi-channel access:** Telegram + HTTP API + local CLI
- **Self-healing:** Auto-restart, backup restore, circuit breakers
- **Proactive monitoring:** Alerts before user-visible failures
- **Graceful degradation:** Partial functionality during outages

### Effort Estimate
- **Phase 1 (Critical):** 4-6 hours
- **Phase 2 (Monitoring):** 8-12 hours
- **Phase 3 (Alternative Access):** 12-16 hours
- **Total:** ~2-3 days of focused work

### Risk Mitigation Success Metrics
- ✅ Zero "Worker pool not started" errors
- ✅ Health check responds within 100ms
- ✅ Backups run hourly (verify in logs)
- ✅ Bot accessible via at least 2 channels (Telegram + HTTP)
- ✅ Restart state 100% reliable (no "too old" warnings)
- ✅ Watchdog detects and alerts on failures within 2 minutes

---

**Next Steps:** Implement Phase 1 critical fixes immediately. This analysis provides the roadmap for achieving true 24/7 reliability with graceful degradation.
