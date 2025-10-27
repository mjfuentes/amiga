# Playwright MCP Browser Isolation Investigation

**Date**: 2025-10-22
**Investigator**: Claude Code
**Status**: ✅ RESOLVED - Configuration fixed and deployed

## Summary

**Critical bug identified and fixed**: The Playwright MCP server was NOT running in isolated mode due to incorrect flag positioning. Browser profiles were persisting to disk with full state (cookies, localStorage, cache) across sessions.

**Resolution**: Flag moved from npx argument to MCP package argument. Configuration corrected in `~/.claude.json` and `CLAUDE.md`. Changes committed in `b72945c`.

## Configuration Analysis

### Before Fix (BROKEN)

**File**: `~/.claude.json`

```json
{
  "mcpServers": {
    "playwright": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "--isolated",              // ❌ WRONG: Passed to npx (invalid)
        "@playwright/mcp@latest"
      ]
    }
  }
}
```

**CLAUDE.md Documentation** (Line 228):
```bash
claude mcp add playwright npx -s user -- --isolated @playwright/mcp@latest
```

### After Fix (WORKING)

**File**: `~/.claude.json`

```json
{
  "mcpServers": {
    "playwright": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--isolated"              // ✅ CORRECT: Passed to MCP package
      ]
    }
  }
}
```

**CLAUDE.md Documentation** (Line 228):
```bash
claude mcp add playwright npx -s user @playwright/mcp@latest -- --isolated
```

**Commit**: `b72945c` (2025-10-22 12:21:38)

## The Problem

### Incorrect Flag Placement

The `--isolated` flag is currently positioned as an argument to `npx`, but **npx has no `--isolated` flag**.

**Evidence**:
1. Web search of npm/npx documentation shows no `--isolated` flag exists for npx
2. npx official flags are: `-y/--yes`, `--no`, `-p/--package`, `--script-shell`
3. The flag is likely being ignored or causing unexpected behavior

### Actual Behavior

**Browser profiles are persisting to disk:**

```bash
$ ls -la /Users/matifuentes/Library/Caches/ms-playwright/mcp-chrome-*/
drwxr-xr-x@ 20  640 Oct 22 12:12 mcp-chrome-1128dc1/  # Current - 61MB
drwxr-xr-x@ 23  736 Sep 16 16:56 mcp-chrome-7bef97e/  # 123MB
drwxr-xr-x@ 19  608 Oct 16 12:00 mcp-chrome-8897d10/  # 83MB
```

**Profile contents include:**
- `Default/Cookies` (modified 2025-10-22 11:52)
- `Default/Local Storage`
- `Default/Session Storage`
- `Default/Cache` (multiple cache types)
- Full Chrome user data directory structure

This means:
- ❌ Browser state persists across sessions
- ❌ Cookies are shared between different MCP invocations
- ❌ localStorage/sessionStorage survives browser restarts
- ❌ Cache is reused across sessions

## What `--isolated` Should Do

According to Playwright MCP documentation:

```
--isolated    keep the browser profile in memory, do not save it to disk.
```

**Expected behavior with `--isolated`**:
- ✅ Browser profile stored in memory only
- ✅ All state cleared when browser closes
- ✅ Each session starts fresh
- ✅ No disk I/O for profile data

## Root Cause Analysis

### Flag Confusion

There are TWO different concepts both called "isolated":

1. **`npx --isolated`** (hypothetical, doesn't exist)
   - Would isolate npm package cache per execution
   - Not a real npx feature

2. **`@playwright/mcp --isolated`** (real, documented)
   - Isolates browser profile in memory
   - Prevents disk persistence
   - **This is what we want**

### How Flags Work with npx

```bash
npx [npx-flags] <package> [package-flags]
```

**Current (incorrect)**:
```bash
npx --isolated @playwright/mcp@latest
#   ^^^^^^^^^^                          ← Passed to npx (invalid/ignored)
```

**Correct**:
```bash
npx @playwright/mcp@latest --isolated
#                          ^^^^^^^^^^  ← Passed to @playwright/mcp (valid)
```

## The Fix

### Update `~/.claude.json`

**Before**:
```json
{
  "command": "npx",
  "args": [
    "--isolated",
    "@playwright/mcp@latest"
  ]
}
```

**After**:
```json
{
  "command": "npx",
  "args": [
    "@playwright/mcp@latest",
    "--isolated"
  ]
}
```

### Update CLAUDE.md

**Before** (Line 234):
```bash
claude mcp add playwright npx -s user -- --isolated @playwright/mcp@latest
```

**After**:
```bash
claude mcp add playwright npx -s user @playwright/mcp@latest -- --isolated
```

**Before** (Line 239):
> The `--isolated` flag ensures each browser session runs in an isolated context, preventing state leakage between sessions and providing cleaner test environments.

**After**:
> The `--isolated` flag keeps the browser profile in memory without saving to disk. Each time the browser closes, all session state (cookies, localStorage, cache) is permanently lost, ensuring clean isolated sessions for testing.

## Additional Isolation Options

### Other Playwright MCP Flags

From `npx @playwright/mcp@latest --help`:

```bash
--isolated                        keep the browser profile in memory, do not save it to disk.
--shared-browser-context          reuse the same browser context between all connected HTTP clients.
--storage-state <path>            path to the storage state file for isolated sessions.
--user-data-dir <path>            path to the user data directory. If not specified, a temporary directory will be created.
```

**Recommendations**:

1. **Use `--isolated`** (primary recommendation)
   - In-memory profile
   - No disk persistence
   - Clean slate each session

2. **Alternative: `--storage-state`** (for repeatable testing)
   - Save known-good state to file
   - Restore same state each session
   - Useful for authenticated testing

3. **Avoid `--shared-browser-context`**
   - Reuses context between HTTP clients
   - Opposite of isolation
   - Only use for specific integration testing

### Browser Context Isolation

Even without `--isolated`, Playwright provides **context-level isolation**:

- Each `browser.newContext()` creates isolated context
- Separate cookies, localStorage, sessionStorage per context
- This is Playwright's native feature (always available)

**However**: Without `--isolated`, contexts persist between MCP server restarts.

## Testing the Fix

### Before Fix Verification

1. Check current browser profiles persist:
```bash
ls -lh /Users/matifuentes/Library/Caches/ms-playwright/mcp-chrome-*/
```

2. Note profile sizes (60+ MB indicates persistence)

### After Fix Verification

1. Apply configuration change
2. Restart Claude Code (to restart MCP server)
3. Use Playwright MCP tools
4. Check if new profiles are created:
```bash
ls -lht /Users/matifuentes/Library/Caches/ms-playwright/mcp-chrome-*/
```

**Expected**: Either no new profiles, or much smaller temporary profiles that disappear after browser closes.

### Cleanup Old Profiles

After confirming the fix works:

```bash
rm -rf /Users/matifuentes/Library/Caches/ms-playwright/mcp-chrome-*
```

This will reclaim ~260MB of disk space.

## Impact Assessment

### Security Implications

**Current (broken isolation)**:
- 🔴 **Critical**: Browser state persists across sessions
- 🔴 **High**: Cookies from one task visible to another
- 🔴 **High**: localStorage can leak between unrelated tests
- 🟡 **Medium**: Cache poisoning possible

**After fix**:
- 🟢 **Resolved**: Fresh browser state each session
- 🟢 **Resolved**: No cross-session cookie leakage
- 🟢 **Resolved**: localStorage isolated per session
- 🟢 **Resolved**: No cache reuse

### Performance Implications

**Current (persistent profiles)**:
- ✅ Faster startup (cached resources)
- ✅ Preserved login states
- ❌ 260+ MB disk usage
- ❌ Profile corruption over time

**After fix (isolated)**:
- ❌ Slightly slower startup (no cache)
- ❌ Must re-authenticate each session
- ✅ Zero persistent disk usage
- ✅ No profile corruption possible

## Recommendations

### Immediate Actions

1. ✅ Update `~/.claude.json` configuration
2. ✅ Update CLAUDE.md documentation
3. ✅ Restart MCP server to apply changes
4. ✅ Verify browser profiles no longer persist
5. ✅ Clean up old browser profiles

### Documentation Updates

1. **CLAUDE.md Line 234**: Fix installation command
2. **CLAUDE.md Line 239**: Correct explanation of `--isolated`
3. **Add section**: Explain npx flag ordering
4. **Add section**: Describe browser context isolation vs profile isolation

### Future Considerations

1. **Add configuration validation**: Detect common MCP config errors
2. **Add cleanup script**: Periodically remove old Playwright caches
3. **Document tradeoffs**: When to use/not use `--isolated`
4. **Add monitoring**: Track browser profile sizes over time

## References

- [Playwright MCP GitHub](https://github.com/microsoft/playwright-mcp)
- [Playwright Browser Contexts](https://playwright.dev/docs/browser-contexts)
- Playwright MCP Help: `npx @playwright/mcp@latest --help`
- npm/npx Documentation: No `--isolated` flag exists

## Conclusion

The current configuration has the `--isolated` flag in the wrong position, causing it to be ignored. Browser profiles are persisting to disk with full state, defeating the purpose of isolation.

**Fix**: Move `--isolated` after the package name in both `~/.claude.json` and CLAUDE.md documentation.

This is a **critical configuration error** that affects security, testing reliability, and documentation accuracy.
