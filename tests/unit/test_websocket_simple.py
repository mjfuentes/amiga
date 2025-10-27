#!/usr/bin/env python3
"""
Simple WebSocket connection test script
Tests WebSocket functionality without requiring full server dependencies
"""

import time
import socketio

# Create Socket.IO client
sio = socketio.Client()

# Track events
events_received = []


@sio.on('connect')
def on_connect():
    print('✓ Connected to server')
    events_received.append('connect')


@sio.on('connected')
def on_connected(data):
    print(f'✓ Received "connected" event: {data}')
    events_received.append('connected')


@sio.on('subscribed')
def on_subscribed(data):
    print(f'✓ Subscribed: {data}')
    events_received.append('subscribed')


@sio.on('metrics_update')
def on_metrics_update(data):
    print(f'✓ Metrics update received at {time.strftime("%H:%M:%S")}')
    print(f'  - Keys: {list(data.keys())}')
    if 'overview' in data:
        print(f'  - Overview keys: {list(data["overview"].keys())}')
    events_received.append('metrics_update')


@sio.on('error')
def on_error(data):
    print(f'✗ Error: {data}')
    events_received.append('error')


@sio.on('disconnect')
def on_disconnect():
    print('✓ Disconnected from server')
    events_received.append('disconnect')


def main():
    """Run the WebSocket test"""
    server_url = 'http://localhost:3000'

    print(f'WebSocket Test Script')
    print(f'=' * 50)
    print(f'Server: {server_url}')
    print(f'=' * 50)
    print()

    try:
        # Connect to server
        print('Connecting to server...')
        sio.connect(server_url, transports=['websocket'])

        # Wait a moment for connection events
        time.sleep(1)

        # Subscribe to metrics
        print('\nSubscribing to metrics updates...')
        sio.emit('subscribe', {'hours': 24, 'update_interval': 2})

        # Wait for subscription confirmation
        time.sleep(1)

        # Request immediate refresh
        print('\nRequesting immediate refresh...')
        sio.emit('request_refresh', {'hours': 24})

        # Wait for metrics update
        time.sleep(2)

        # Wait for a few updates
        print('\nWaiting for real-time updates (10 seconds)...')
        for i in range(10):
            time.sleep(1)
            print(f'  Waiting... {i+1}/10s', end='\r')

        print('\n\nTest interval change...')
        sio.emit('set_interval', {'interval': 5})
        time.sleep(1)

        # Disconnect
        print('\nDisconnecting...')
        sio.disconnect()

        # Summary
        print('\n' + '=' * 50)
        print('Test Summary')
        print('=' * 50)
        print(f'Total events received: {len(events_received)}')
        print(f'Events: {events_received}')

        # Count metrics updates
        metrics_count = events_received.count('metrics_update')
        print(f'\nMetrics updates received: {metrics_count}')

        if metrics_count > 0:
            print('✓ WebSocket metrics streaming is working!')
        else:
            print('✗ No metrics updates received')

        print('\n✓ Test completed successfully!')

    except socketio.exceptions.ConnectionError as e:
        print(f'\n✗ Connection error: {e}')
        print('\nMake sure the monitoring server is running:')
        print('  cd /Users/matifuentes/Workspace/agentlab/telegram_bot')
        print('  python3 monitoring_server.py')
    except Exception as e:
        print(f'\n✗ Error: {e}')
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
