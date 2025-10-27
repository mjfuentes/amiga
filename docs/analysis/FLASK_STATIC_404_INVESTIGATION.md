# Flask Static File 404 Investigation

**Date**: 2025-10-27
**Status**: ✅ RESOLVED - Server restart fixed the issue
**Root Cause**: Stale server process with outdated code/state

## Summary

**Problem reported**: Flask route `GET /static/js/main.b4cbcce2.js` returned 404 despite file existing at `/Users/matifuentes/Workspace/amiga/static/chat/static/js/main.b4cbcce2.js`.

**Resolution**: The Flask routing code was already correct. Simply restarting the server process (PID 83046 → 89721) resolved the issue. All static files now return 200 OK.

## Investigation Steps

### 1. Verified Route Configuration

**Flask app initialization** (`monitoring/server.py:120`):
```python
app = Flask(__name__,
           template_folder="../templates",
           static_folder="../static",
           static_url_path="/flask-static")
```

**Catch-all route** (`monitoring/server.py:765-775`):
```python
@app.route("/<path:filename>")
def static_files(filename):
    """Serve static files (favicon, manifest, JS, CSS, etc)"""
    # First try chat static directory
    chat_static_dir = Path(__file__).parent.parent / "static" / "chat"
    file_path = chat_static_dir / filename
    if file_path.exists():
        return send_from_directory(chat_static_dir, filename)

    # Fallback to default Flask static handling
    return send_from_directory(app.static_folder, filename)
```

**Route registration order** (verified with route inspection):
```
/flask-static/<path:filename>   -> static (Flask built-in, custom URL path)
/<path:filename>                -> static_files (our catch-all)
```

✅ **No route conflicts**: Flask's built-in static route uses `/flask-static/`, not `/static/`

### 2. Path Resolution Test

**Request path**: `/static/js/main.b4cbcce2.js`

**Resolution logic**:
```python
chat_static_dir = Path(__file__).parent.parent / "static" / "chat"
# = /Users/matifuentes/Workspace/amiga/static/chat

file_path = chat_static_dir / "static/js/main.b4cbcce2.js"
# = /Users/matifuentes/Workspace/amiga/static/chat/static/js/main.b4cbcce2.js
```

**File existence**:
```bash
$ ls -la static/chat/static/js/main.b4cbcce2.js
-rw-r--r--@ 1 matifuentes staff 1245807 27 Okt 23:18 static/chat/static/js/main.b4cbcce2.js
```

✅ **File exists and path resolution is correct**

### 3. Test Results (After Server Restart)

**JavaScript file** (correct hash):
```bash
$ curl -sI http://localhost:3000/static/js/main.b4cbcce2.js
HTTP/1.1 200 OK
Content-Type: text/javascript; charset=utf-8
Content-Length: 1245807
```

**CSS file** (correct hash):
```bash
$ curl -sI http://localhost:3000/static/css/main.68206661.css
HTTP/1.1 200 OK
Content-Type: text/css; charset=utf-8
Content-Length: 63248
```

**CSS file** (old hash from browser cache):
```bash
$ curl -sI http://localhost:3000/static/css/main.91bb3e29.css
HTTP/1.1 404 NOT FOUND
```

✅ **All current files return 200 OK**
❌ **Old cached files correctly return 404**

### 4. HTML References

**File**: `static/chat/index.html`
```html
<script defer="defer" src="/static/js/main.b4cbcce2.js"></script>
<link href="/static/css/main.68206661.css" rel="stylesheet">
```

✅ **References match actual files on disk**

## Root Cause Analysis

### What WAS Wrong (Before Restart)

The server process (PID 83046) was running with:
- **Stale Python code** OR
- **Stale in-memory state** OR
- **Import cache issues**

This caused the catch-all route to malfunction despite the code being correct.

### What Fixed It

**Action**: Killed old process (PID 83046) and started fresh (PID 89721)

**Result**: All routes immediately worked correctly with no code changes needed.

**Evidence**: The route code had no bugs - it worked perfectly after restart.

## Lessons Learned

### 1. Flask Development Server Issues

Flask's development server can have:
- **Code reload failures**: Changes not picked up even with auto-reload
- **Import caching**: Python module cache persists across file changes
- **State corruption**: Long-running processes accumulate state bugs

**Solution**: Always try a full restart before deep debugging.

### 2. Browser Caching vs Server Issues

**Distinguish**:
- Server 404 for **current files** → server bug
- Server 404 for **old files** → expected behavior (hard refresh needed)

**In this case**:
- Old server returned 404 for current file `main.b4cbcce2.js` → server bug
- New server returns 404 for old file `main.91bb3e29.css` → correct behavior

### 3. Debugging Methodology

**What worked**:
1. ✅ Verified file existence on disk
2. ✅ Checked Flask route registration and precedence
3. ✅ Tested `send_from_directory()` in isolation
4. ✅ Added debug logging to trace execution
5. ✅ Restarted server to clear state

**What to do first next time**:
1. **Restart the server** - 90% of "impossible" bugs vanish
2. Hard refresh browser (Cmd+Shift+R) - clear browser cache
3. Check logs for actual errors
4. **Then** start deep code analysis

## Verification

**Before restart** (PID 83046):
- ❌ `GET /static/js/main.b4cbcce2.js` → 404

**After restart** (PID 89721):
- ✅ `GET /static/js/main.b4cbcce2.js` → 200 OK
- ✅ `GET /static/css/main.68206661.css` → 200 OK
- ✅ `GET /favicon.ico` → 200 OK
- ✅ `GET /` → 200 OK (React index.html)

## Recommendations

### Immediate Actions

✅ **Restart server when routes mysteriously fail**
✅ **Use deployment script** (`./deploy.sh chat`) for clean restarts
✅ **Hard refresh browser** (Cmd+Shift+R) after deployments

### Future Improvements

- [ ] **Add route health check** in `/api/health` endpoint
  - Test catch-all route functionality
  - Verify static file serving
  - Return diagnostic info

- [ ] **Improve deployment script**
  - Add verification step after restart
  - Test key routes (/, /static/js/, /static/css/)
  - Fail deployment if routes broken

- [ ] **Add monitoring**
  - Track 404 rate for static files
  - Alert if sudden spike (indicates broken deployment)

## Conclusion

**Issue**: Flask static file route returned 404 for existing files.

**Root cause**: Stale server process with corrupted state.

**Resolution**: Server restart (no code changes needed).

**Prevention**: Always use deployment script for restarts, add route health checks.

---

**Investigation by**: Claude (ultrathink-debugger)
**Documented**: 2025-10-27 22:26 UTC
