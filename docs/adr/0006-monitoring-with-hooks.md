# 6. Monitoring with Claude Code Hooks

Date: 2025-01-15

## Status

Accepted

## Context

Need visibility into Claude Code agent behavior to:

1. **Track tool usage**: Which tools are used, how often, success rates
2. **Debug failures**: Understand what went wrong when tasks fail
3. **Monitor performance**: Tool execution times, bottlenecks
4. **Cost tracking**: Token usage per tool call, aggregate costs
5. **User analytics**: What tasks users request, success patterns
6. **Real-time updates**: Live dashboard showing active tasks

**Challenges:**
- Claude Code CLI is a black box subprocess (no built-in monitoring)
- Need to intercept tool calls without modifying Claude Code itself
- Want real-time updates (not just post-mortem logs)
- Need to correlate tool usage with task outcomes
- Must not impact agent performance significantly

**Available mechanisms:**
- Claude Code supports lifecycle hooks (pre-tool-use, post-tool-use, session-end)
- Hooks are shell scripts invoked before/after each tool execution
- Hooks receive JSON data on stdin with tool details

## Decision

Use **Claude Code lifecycle hooks** for real-time monitoring and metrics collection.

**Architecture:**

**Hook scripts** (`.claude/hooks/`):
1. `pre-tool-use.sh` - Logs before tool execution
2. `post-tool-use.sh` - Logs results, errors, tokens
3. `session-end.sh` - Aggregates session summary

**Data flow:**
```
Claude Code → Hook Script → JSONL Log → Database → Dashboard
```

**Hook implementation** (`.claude/hooks/post-tool-use.sh`):
```bash
#!/bin/bash
# Read tool data from stdin
INPUT=$(cat)

# Extract task ID from environment
TASK_ID=${AGENTLAB_TASK_ID:-unknown}

# Write to session log
SESSION_DIR="logs/sessions/$SESSION_UUID"
echo "$INPUT" | jq -c '.' >> "$SESSION_DIR/post_tool_use.jsonl"

# Extract and store in database via Python script
echo "$INPUT" | python3 .claude/hooks/post_tool_use_db.py "$TASK_ID"
```

**Database integration** (`tasks/tracker.py`):
- Hooks call Python scripts to insert data into SQLite
- `record_tool_usage()` - Creates in-progress record (pre-hook)
- `update_tool_usage()` - Updates with results (post-hook)
- Tracks: tool name, duration, success, error, tokens

**Hook data** (`.claude/hooks/hooks_reader.py`):
- Parses JSONL logs for historical analysis
- Aggregates statistics across sessions
- Powers monitoring dashboard

## Consequences

### Positive

- **Real-time visibility**: See tool calls as they happen
- **No code changes**: Hooks are external to Claude Code (stable)
- **Rich data**: Get tool parameters, output, errors, tokens
- **Correlation**: Link tool usage to task outcomes
- **Debugging**: Full timeline of what agent did
- **Performance tracking**: Measure tool execution times
- **Cost monitoring**: Track token usage per tool
- **Dashboard integration**: Live updates via Server-Sent Events

### Negative

- **Performance overhead**: ~50-100ms per tool call for hook execution
- **Disk I/O**: JSONL logs grow over time (mitigated by cleanup)
- **Parsing complexity**: Need to parse JSON from shell scripts
- **Reliability**: If hook fails, data might be lost (hooks log errors)
- **Maintenance**: Need to keep hooks in sync with Claude Code updates
- **Storage growth**: Session logs accumulate in `logs/sessions/`

## Alternatives Considered

1. **Modify Claude Code Source**
   - Rejected: Would need to maintain fork
   - Breaks on Claude Code updates
   - Hooks are officially supported mechanism

2. **Parse Claude Code Output**
   - Rejected: Output format is for humans, not machines
   - Unreliable (format changes)
   - Can't capture structured tool data

3. **Wrapper Around Claude Code**
   - Rejected: Can't intercept individual tool calls
   - Only sees final output
   - No real-time visibility

4. **Separate Logging Server**
   - Rejected: Overkill for single-machine deployment
   - Adds network latency
   - More complex to deploy

5. **Pull-Based Polling**
   - Rejected: High latency (seconds to minutes)
   - Inefficient (constant polling)
   - Misses transient states

6. **OpenTelemetry/APM Tools**
   - Considered: Datadog, New Relic, etc.
   - Rejected: Too heavy for development bot
   - Hooks provide equivalent functionality
   - Cost and complexity not justified

## Hook Lifecycle

**Tool execution flow:**

```
1. Agent decides to use tool (e.g., Read)
2. pre-tool-use.sh called with tool name, parameters
   → Logs to logs/sessions/{uuid}/pre_tool_use.jsonl
   → Creates database record (success=NULL)
3. Tool executes (e.g., file read)
4. post-tool-use.sh called with output, errors, tokens
   → Logs to logs/sessions/{uuid}/post_tool_use.jsonl
   → Updates database record (success=true/false, tokens, etc.)
5. Session ends → session-end.sh aggregates summary
   → Writes logs/sessions/{uuid}/summary.json
```

## Data Schema

**Pre-tool-use log:**
```json
{
  "timestamp": "2025-01-15T10:30:00Z",
  "tool": "Read",
  "parameters": {"file_path": "/path/to/file.py"},
  "session_uuid": "abc123"
}
```

**Post-tool-use log:**
```json
{
  "timestamp": "2025-01-15T10:30:01Z",
  "tool": "Read",
  "output_length": 1024,
  "has_error": false,
  "duration_ms": 150,
  "usage": {
    "input_tokens": 100,
    "output_tokens": 50,
    "cache_read_tokens": 200
  }
}
```

## References

- Hook scripts: `.claude/hooks/` (pre-tool-use.sh, post-tool-use.sh, session-end.sh)
- Hook reader: `monitoring/hooks_reader.py:31-262`
- Database tracker: `tasks/tracker.py`
- Dashboard integration: `monitoring/server.py` (SSE endpoints)
- Database schema: `tasks/database.py` (tool_usage table, lines 159-173)
- Session logs: `logs/sessions/{uuid}/` (JSONL files)
