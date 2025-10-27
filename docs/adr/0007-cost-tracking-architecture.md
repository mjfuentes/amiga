# 7. Cost Tracking Architecture

Date: 2025-01-15

## Status

Accepted

## Context

Claude API usage incurs costs that must be monitored and controlled:

1. **Token-based pricing**: Charged per input/output token
2. **Variable costs**: Haiku ($0.0001/1K) vs Sonnet ($0.003/1K) vs Opus ($0.015/1K)
3. **Caching**: Cache reads reduce costs significantly (10x cheaper)
4. **Runaway risk**: Bugs or misuse could cause unexpected high costs
5. **Budget tracking**: Need daily and monthly cost visibility
6. **Cost limits**: Want to automatically stop when budget exceeded

**Requirements:**
- Track costs per API call (Claude API + Claude Code CLI)
- Aggregate daily and monthly totals
- Enforce spending limits to prevent overruns
- Persist across bot restarts
- Simple to query and monitor
- Support both Anthropic API and usage API

**Cost calculation** (Anthropic pricing):
```
Input tokens:    $X per 1M tokens
Output tokens:   $Y per 1M tokens
Cache writes:    $Z per 1M tokens (1.25x input price)
Cache reads:     $W per 1M tokens (0.1x input price)
```

## Decision

Implement **JSON file-based cost tracking** with daily/monthly limits.

**Architecture:**

**Storage** (`data/cost_tracking.json`):
```json
{
  "daily": {
    "2025-01-15": {
      "haiku": {
        "input_tokens": 1000000,
        "output_tokens": 500000,
        "cache_creation_tokens": 100000,
        "cache_read_tokens": 2000000,
        "total_cost": 0.45
      },
      "sonnet": { ... }
    }
  },
  "monthly": {
    "2025-01": { ... }
  },
  "total_cost": 1234.56,
  "last_updated": "2025-01-15T10:30:00Z"
}
```

**Implementation** (`tasks/analytics.py`):
```python
class CostTracker:
    def track_cost(self, model, input_tokens, output_tokens,
                   cache_creation_tokens, cache_read_tokens):
        # Calculate cost based on model pricing
        cost = calculate_cost(...)

        # Update daily/monthly aggregates
        self._update_daily(date, model, tokens, cost)
        self._update_monthly(month, model, tokens, cost)

        # Check against limits
        if self._check_limits():
            raise CostLimitExceeded()
```

**Limit enforcement:**
- `DAILY_COST_LIMIT` environment variable (default: $100)
- `MONTHLY_COST_LIMIT` environment variable (default: $1000)
- Bot refuses new tasks when limit exceeded
- Users notified via Telegram message

**Cost sources:**
1. **Claude API** (Q&A, routing): Tracked in `claude/api_client.py`
2. **Claude Code CLI**: Tracked via hooks (`post-tool-use.sh`)
3. **Usage API sync**: Optional sync from Anthropic API (admin key required)

## Consequences

### Positive

- **Budget protection**: Automatic stop when limits reached
- **Cost visibility**: Daily breakdown by model
- **Simple persistence**: JSON file, easy to read/edit
- **No database dependency**: Works independently of SQLite
- **Granular tracking**: Per-model costs and token counts
- **Cache awareness**: Tracks cache effectiveness
- **Manual override**: Can edit JSON file to reset limits
- **Audit trail**: Historical costs preserved

### Negative

- **Manual resets**: Daily/monthly totals don't auto-reset (by design)
- **File-based races**: Concurrent writes could corrupt (mitigated by locks)
- **No automatic billing**: Can't charge users or integrate payment
- **Estimation errors**: If pricing changes, historical costs wrong
- **Separate from database**: Cost data not in SQLite (consistency risk)
- **No per-user limits**: Single global limit for all users

## Alternatives Considered

1. **Database Table for Costs**
   - Considered: Add `costs` table to SQLite
   - Rejected: Simpler to have separate JSON file
   - Would provide better querying but adds complexity

2. **In-Memory Tracking Only**
   - Rejected: Lost on bot restart
   - Can't track historical costs
   - No persistence for limits

3. **Cloud Cost Tracking (Anthropic Console)**
   - Rejected: Not real-time (delayed by hours)
   - Can't enforce limits programmatically
   - No per-bot breakdown

4. **Third-Party Analytics (Helicone, LangSmith)**
   - Rejected: External dependency
   - Requires sending data to third party
   - Cost and privacy concerns

5. **Per-User Cost Tracking**
   - Considered: Track costs per Telegram user
   - Rejected: Adds complexity, single owner bot
   - Could be added later if needed

6. **Redis for Cost State**
   - Rejected: Overkill for simple counter
   - Adds infrastructure dependency
   - JSON file is sufficient

## Cost Calculation

**Pricing** (as of 2025-01-15):

| Model | Input (MTok) | Output (MTok) | Cache Write (MTok) | Cache Read (MTok) |
|-------|-------------|---------------|-------------------|-------------------|
| Haiku 4.5 | $0.10 | $0.50 | $0.125 | $0.01 |
| Sonnet 4.5 | $3.00 | $15.00 | $3.75 | $0.30 |
| Opus 4.5 | $15.00 | $75.00 | $18.75 | $1.50 |

**Example calculation:**
```python
def calculate_cost(model, tokens):
    pricing = MODEL_PRICING[model]

    cost = (
        tokens['input'] * pricing['input'] / 1_000_000 +
        tokens['output'] * pricing['output'] / 1_000_000 +
        tokens['cache_creation'] * pricing['cache_creation'] / 1_000_000 +
        tokens['cache_read'] * pricing['cache_read'] / 1_000_000
    )
    return cost
```

## Limit Enforcement

**Daily limit check:**
```python
if daily_cost >= DAILY_COST_LIMIT:
    raise CostLimitExceeded(
        f"Daily limit of ${DAILY_COST_LIMIT} exceeded "
        f"(current: ${daily_cost:.2f})"
    )
```

**User notification:**
```
⚠️ Daily cost limit reached ($100.00)
Bot will resume tomorrow. Contact owner if urgent.
```

**Override:** Owner can edit `data/cost_tracking.json` to reset counters.

## References

- Implementation: `tasks/analytics.py`
- Cost file: `data/cost_tracking.json`
- Pricing constants: `tasks/analytics.py` (MODEL_PRICING)
- Environment variables: `.env.example` (DAILY_COST_LIMIT, MONTHLY_COST_LIMIT)
- Usage tracking: `claude/api_client.py`, `.claude/hooks/post-tool-use.sh`
- Limit checks: `tasks/manager.py` (before task submission)
- User command: `/usage` in `core/main.py`
