# Setup Bot with launchd (Auto-restart on Mac)

This guide sets up the Telegram bot to run 24/7 on your Mac with automatic restarts.

## Features
- ✅ Bot auto-starts when Mac boots
- ✅ Auto-restarts if it crashes
- ✅ Logs to `logs/bot_stdout.log` and `logs/bot_stderr.log`
- ✅ Throttled restarts (10s delay) to prevent rapid failures

## Prerequisites
1. Bot is working when run manually: `python telegram_bot/main.py`
2. Virtual environment exists at `venv/`
3. `.env` file configured with tokens

## Installation Steps

### 1. Copy launchd plist to LaunchAgents
```bash
# Create LaunchAgents directory if it doesn't exist
mkdir -p ~/Library/LaunchAgents

# Copy plist file
cp com.agentlab.telegrambot.plist ~/Library/LaunchAgents/

# Set correct permissions
chmod 644 ~/Library/LaunchAgents/com.agentlab.telegrambot.plist
```

### 2. Load the service
```bash
# Load the service (starts bot immediately)
launchctl load ~/Library/LaunchAgents/com.agentlab.telegrambot.plist

# Check if it's running
launchctl list | grep agentlab
```

### 3. Verify bot is running
```bash
# Check logs
tail -f logs/bot_stdout.log

# You should see:
# "Bot started successfully!"
```

## Keep Mac Awake (Optional)

Choose one option:

### Option A: System Settings (GUI)
1. System Settings → Battery (or Energy Saver)
2. Set "Turn display off after" to Never (or high value)
3. Uncheck "Put hard disks to sleep when possible"
4. Check "Prevent automatic sleeping when display is off"

### Option B: caffeinate (Temporary)
```bash
# Keep Mac awake while process runs
caffeinate -s &

# Or keep awake indefinitely
caffeinate -d &
```

### Option C: pmset (Permanent)
```bash
# Disable sleep on AC power
sudo pmset -c sleep 0
sudo pmset -c displaysleep 10  # Display can sleep after 10 min
```

## Managing the Service

### Check Status
```bash
# List running services
launchctl list | grep agentlab

# View logs
tail -f logs/bot_stdout.log
tail -f logs/bot_stderr.log
```

### Stop Bot
```bash
launchctl unload ~/Library/LaunchAgents/com.agentlab.telegrambot.plist
```

### Restart Bot
```bash
# Unload then load
launchctl unload ~/Library/LaunchAgents/com.agentlab.telegrambot.plist
launchctl load ~/Library/LaunchAgents/com.agentlab.telegrambot.plist

# Or use /restart command in Telegram
```

### Update Bot Code
```bash
# Pull changes
git pull

# Restart service (launchd will use new code)
launchctl unload ~/Library/LaunchAgents/com.agentlab.telegrambot.plist
launchctl load ~/Library/LaunchAgents/com.agentlab.telegrambot.plist
```

### Remove Service
```bash
# Unload and remove
launchctl unload ~/Library/LaunchAgents/com.agentlab.telegrambot.plist
rm ~/Library/LaunchAgents/com.agentlab.telegrambot.plist
```

## Troubleshooting

### Bot not starting
1. Check logs: `cat logs/bot_stderr.log`
2. Test manually: `python telegram_bot/main.py`
3. Verify paths in plist are correct
4. Check permissions: `ls -l ~/Library/LaunchAgents/com.agentlab.telegrambot.plist`

### Bot crashes immediately
1. Check stderr: `cat logs/bot_stderr.log`
2. Ensure .env file exists and has valid tokens
3. Test venv activation: `source venv/bin/activate && python --version`

### Service not loading
```bash
# Check for syntax errors in plist
plutil -lint ~/Library/LaunchAgents/com.agentlab.telegrambot.plist

# View launchd logs
log show --predicate 'subsystem == "com.apple.launchd"' --last 5m
```

### Can't find service
```bash
# List all user services
launchctl list

# Search for our service
launchctl list | grep agentlab
```

## Environment Variables

If your bot needs environment variables from `.env`, you have two options:

### Option 1: Use python-dotenv (Current approach)
The bot already loads `.env` via `python-dotenv` in `main.py`.

### Option 2: Add to plist
Edit the plist file's EnvironmentVariables section:
```xml
<key>EnvironmentVariables</key>
<dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin</string>
    <key>TELEGRAM_BOT_TOKEN</key>
    <string>your_token_here</string>
    <!-- Add more env vars as needed -->
</dict>
```

## Benefits vs Running Manually

| Feature | Manual | launchd |
|---------|--------|---------|
| Auto-start on boot | ❌ | ✅ |
| Auto-restart on crash | ❌ | ✅ |
| Background process | ❌ | ✅ |
| Survives terminal close | ❌ | ✅ |
| Log management | Manual | Automatic |

## Next Steps

Once working locally with launchd, consider:
1. Monitor uptime: `launchctl list | grep agentlab`
2. Set up log rotation for `logs/*.log`
3. Create backup strategy for `data/*.json`
4. If you need true 24/7, migrate to VPS later
