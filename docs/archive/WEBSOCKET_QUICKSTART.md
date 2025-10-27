# WebSocket Dashboard - Quick Start Guide

## 🚀 Quick Start (5 minutes)

### 1. Install Dependencies

```bash
cd /Users/matifuentes/Workspace/agentlab
pip install "flask-socketio>=5.3.0" "python-socketio>=5.11.0" "eventlet>=0.35.0"
```

✅ **Status**: Dependencies added to `requirements.txt`

### 2. Start the Server

```bash
cd /Users/matifuentes/Workspace/agentlab/telegram_bot
python3 monitoring_server.py
```

You should see:
```
INFO - Starting monitoring server on 0.0.0.0:3000
INFO - Server initialized for eventlet.
```

### 3. Open Test Dashboard

**Option A - Built-in Test Page**:
```bash
open http://localhost:3000/websocket-test
```

**Option B - Standalone Test Page**:
```bash
open /Users/matifuentes/Workspace/agentlab/websocket_test_standalone.html
```

### 4. Test the Connection

In the test dashboard:

1. Click **"Connect"** button
2. Wait for green "Connected" status
3. Click **"Subscribe"** to start receiving metrics
4. Click **"Request Refresh"** to force an update
5. Watch the Event Log for real-time updates

You should see events like:
- ✓ Connected to server
- ✓ Received 'connected' event
- ✓ Subscribed
- ✓ Metrics update received

### 5. Verify It's Working

Open browser DevTools (F12):
- Go to **Network** tab
- Filter by **"WS"** (WebSocket)
- See active WebSocket connection
- Click on connection to see frames

## 🧪 Testing Options

### Automated Tests

```bash
cd /Users/matifuentes/Workspace/agentlab/telegram_bot
pytest tests/test_websocket.py -v
```

### Python Client Test

```bash
cd /Users/matifuentes/Workspace/agentlab
python3 test_websocket_simple.py
```

### Browser Testing

1. **Interactive Dashboard**: http://localhost:3000/websocket-test
2. **Standalone HTML**: Open `websocket_test_standalone.html`
3. **Main Dashboard (SSE)**: http://localhost:3000/ (still works!)

## 📊 What You'll See

### Connection Stats
- Events Received: Real-time counter
- Metrics Updates: Number of data pushes
- Total Tasks: From monitoring system
- Total Cost: API usage costs

### Event Log
- Connection status changes
- Subscription confirmations
- Metrics updates
- Errors (if any)

### Recent Activity
- Task descriptions
- Timestamps
- Status updates

## 🎮 Interactive Controls

| Button | Action |
|--------|--------|
| **Connect** | Establish WebSocket connection |
| **Disconnect** | Close connection |
| **Subscribe** | Start receiving metrics |
| **Unsubscribe** | Stop receiving metrics |
| **Request Refresh** | Force immediate update |
| **Set Interval** | Change update frequency (1-60s) |
| **Clear Logs** | Clear event log |

## 🔧 Configuration

### Update Interval

Default: **2 seconds**

Change it:
1. Enter new value (1-60 seconds)
2. Click "Set Interval"

### Time Range

Default: **24 hours**

Configurable when subscribing:
```javascript
socket.emit('subscribe', {
    hours: 12,           // Last 12 hours
    update_interval: 5   // Update every 5 seconds
});
```

## 🐛 Troubleshooting

### Server Won't Start

**Error**: `ModuleNotFoundError: No module named 'flask_socketio'`

**Fix**:
```bash
pip install flask-socketio python-socketio eventlet
```

### Can't Connect

**Error**: `Connection error: Error: websocket error`

**Fix**:
1. Check server is running: `lsof -i :3000`
2. Verify URL: `http://localhost:3000` (not https)
3. Check firewall settings

### No Metrics Updates

**Problem**: Connected but no data

**Fix**:
1. Click "Subscribe" button
2. Click "Request Refresh" to force update
3. Check server logs for errors

### Browser Console Errors

**Error**: `io is not defined`

**Fix**: Check that Socket.IO CDN is loading:
```html
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
```

## 📱 Example Client Code

### Minimal Example

```html
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
</head>
<body>
    <h1>WebSocket Test</h1>
    <div id="status">Connecting...</div>
    <div id="data"></div>

    <script>
        const socket = io('http://localhost:3000');

        socket.on('connect', () => {
            document.getElementById('status').textContent = 'Connected!';
            socket.emit('subscribe', { hours: 24 });
        });

        socket.on('metrics_update', (data) => {
            document.getElementById('data').textContent =
                JSON.stringify(data, null, 2);
        });
    </script>
</body>
</html>
```

### Python Client Example

```python
import socketio
import time

sio = socketio.Client()

@sio.on('connect')
def on_connect():
    print('Connected!')
    sio.emit('subscribe', {'hours': 24})

@sio.on('metrics_update')
def on_metrics(data):
    print('Metrics:', data)

sio.connect('http://localhost:3000')
time.sleep(60)  # Listen for 60 seconds
sio.disconnect()
```

## 🎯 What's New vs SSE

| Feature | SSE (Old) | WebSocket (New) |
|---------|-----------|-----------------|
| **Direction** | One-way only | Bidirectional ✨ |
| **Client Control** | None | Full control ✨ |
| **Force Refresh** | ❌ | ✅ |
| **Change Interval** | ❌ | ✅ |
| **Subscribe/Unsubscribe** | ❌ | ✅ |
| **Reconnection** | Automatic | Automatic |
| **Browser Support** | Good | Excellent |

Both are still available!

## 📖 Next Steps

1. ✅ **Test basic connection** (this guide)
2. 📚 **Read full docs**: `WEBSOCKET_IMPLEMENTATION.md`
3. 🔧 **Integrate with your code**
4. 🚀 **Deploy to production**

## 🆘 Getting Help

### Check Logs

**Server logs**:
```bash
cd /Users/matifuentes/Workspace/agentlab/telegram_bot
python3 monitoring_server.py
# Watch console output
```

**Browser console**:
- Press F12
- Go to Console tab
- Look for errors

### Test Endpoints

**REST API** (should work):
```bash
curl http://localhost:3000/api/metrics/overview
```

**WebSocket test page**:
```bash
curl http://localhost:3000/websocket-test
```

### Common Issues

1. **Port already in use**: Change port in `.env`:
   ```bash
   MONITORING_PORT=3001
   ```

2. **Permission denied**: Use sudo or change to port >1024

3. **Module not found**: Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## ✨ Features Demonstrated

### Real-time Updates
- Automatic push when metrics change
- Configurable update frequency
- Change detection (efficient)

### Bidirectional Control
- Subscribe/unsubscribe on demand
- Request immediate refresh
- Change update interval dynamically

### Connection Management
- Auto-reconnection on disconnect
- Connection status indicators
- Error handling and recovery

### Metrics Display
- Task statistics
- Cost tracking
- Activity feed
- Tool usage

## 🎉 Success Criteria

You've successfully set up WebSocket dashboard if:

✅ Server starts without errors
✅ Test page loads in browser
✅ Connection status shows "Connected"
✅ Event log shows "Connected" and "Subscribed" events
✅ Metrics counters are updating
✅ WebSocket connection visible in DevTools Network tab

## 📝 Summary

**Time to setup**: ~5 minutes
**Files modified**: 2 (monitoring_server.py, requirements.txt)
**Files created**: 4 (test pages, tests, docs)
**Lines of code**: ~500 (server) + ~300 (client) + tests

**Status**: ✅ Production Ready

---

**Need more details?** See `WEBSOCKET_IMPLEMENTATION.md` for complete documentation.

**Found a bug?** Check troubleshooting section above or review server logs.

**Ready to integrate?** Use the example code provided to build your own client!
