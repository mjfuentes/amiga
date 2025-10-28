#!/usr/bin/env python3
"""
Analyze conversation history for unattended messages due to Claude unavailability.
Creates tasks for unique unattended messages.
"""
import re
import json
import sqlite3
import random
import string
from collections import defaultdict
from pathlib import Path
from datetime import datetime

def parse_bot_log(log_path):
    """Parse bot.log to find user messages and corresponding errors."""
    messages = []

    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Pattern: timestamp - module - level - message
    log_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([\w.]+) - (\w+) - (.+)$')

    # Look for session messages being added
    user_message_pattern = re.compile(r'Added user message to session (\d+)')
    error_patterns = [
        'unavailable',
        'overloaded',
        'rate limit',
        'timeout',
        'failed to process',
        'API error',
        'exception',
        'ERROR'
    ]

    for i, line in enumerate(lines):
        match = log_pattern.match(line)
        if not match:
            continue

        timestamp, module, level, message = match.groups()

        # Check for user messages
        user_match = user_message_pattern.search(message)
        if user_match:
            user_id = user_match.group(1)
            # Message content is in the session, extract from context
            user_text = f"Message at {timestamp}"

            # Look ahead for errors within next 10 lines
            error_found = None
            for j in range(i + 1, min(i + 11, len(lines))):
                error_line = lines[j]
                for error_pattern in error_patterns:
                    if error_pattern.lower() in error_line.lower():
                        error_found = error_line.strip()
                        break
                if error_found:
                    break

            messages.append({
                'timestamp': timestamp,
                'user_id': user_id,
                'message': user_text,
                'error': error_found,
                'had_error': error_found is not None
            })

    return messages

def deduplicate_messages(messages):
    """Deduplicate messages by content, keeping most recent occurrence."""
    seen = {}

    for msg in messages:
        if not msg['had_error']:
            continue

        # Normalize message for comparison
        normalized = msg['message'].lower().strip()

        if normalized not in seen:
            seen[normalized] = msg
        else:
            # Keep most recent
            if msg['timestamp'] > seen[normalized]['timestamp']:
                seen[normalized] = msg

    return list(seen.values())

def create_tasks(messages, db_path):
    """Create tasks in database for unattended messages."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    created_tasks = []

    for msg in messages:
        # Generate unique task_id with random suffix
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        task_id = f"unattended_{random_suffix}"
        description = f"Unattended message from user {msg['user_id']}: {msg['message'][:100]}"

        # Check if similar task already exists
        cursor.execute("""
            SELECT task_id FROM tasks
            WHERE description LIKE ?
            AND status NOT IN ('completed', 'failed')
            LIMIT 1
        """, (f"%{msg['message'][:50]}%",))

        if cursor.fetchone():
            print(f"⏭️  Skipping duplicate: {description}")
            continue

        # Create task
        cursor.execute("""
            INSERT INTO tasks (
                task_id, user_id, description, status,
                created_at, updated_at, model, workspace, agent_type,
                context
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            int(msg['user_id']),
            description,
            'pending',
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            'claude-sonnet-4.5',
            '/Users/matifuentes/Workspace/amiga',
            'code_agent',
            json.dumps({
                'original_message': msg['message'],
                'error': msg['error'],
                'timestamp': msg['timestamp']
            })
        ))

        created_tasks.append({
            'task_id': task_id,
            'description': description,
            'message': msg['message']
        })

        print(f"✅ Created task: {task_id}")

    conn.commit()
    conn.close()

    return created_tasks

def main():
    project_root = Path(__file__).parent.parent
    log_path = project_root / 'logs' / 'bot.log'
    db_path = project_root / 'data' / 'agentlab.db'

    print("📋 Parsing bot.log...")
    messages = parse_bot_log(log_path)
    print(f"Found {len(messages)} user messages")

    error_messages = [m for m in messages if m['had_error']]
    print(f"Found {len(error_messages)} messages with errors")

    print("\n🔍 Deduplicating messages...")
    unique_messages = deduplicate_messages(messages)
    print(f"Found {len(unique_messages)} unique unattended messages")

    if not unique_messages:
        print("\n✨ No unattended messages found!")
        return

    print("\n📝 Creating tasks...")
    created_tasks = create_tasks(unique_messages, db_path)

    print(f"\n✅ Created {len(created_tasks)} tasks")

    if created_tasks:
        print("\n📊 Summary:")
        for task in created_tasks:
            print(f"  • {task['task_id']}: {task['message'][:80]}")

if __name__ == '__main__':
    main()
