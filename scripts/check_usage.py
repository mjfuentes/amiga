#!/usr/bin/env python3
from telegram_bot.usage_api import ClaudeUsageAPI
from datetime import datetime

try:
    api = ClaudeUsageAPI()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    usage = api.get_usage_report(today, datetime.now(), '1d', group_by=['model'])

    print('Today usage from Anthropic API:')
    total_cost = 0
    for bucket in usage.get('buckets', []):
        for group in bucket.get('groups', []):
            model = group.get('model', 'unknown')
            metrics = group.get('metrics', {})
            input_tok = metrics.get('input_tokens', 0)
            output_tok = metrics.get('output_tokens', 0)
            print(f'{model}: {input_tok:,} in, {output_tok:,} out')

            # Calculate cost for haiku
            if 'haiku' in model.lower():
                cost = (input_tok / 1_000_000 * 0.80) + (output_tok / 1_000_000 * 4.00)
                total_cost += cost
                print(f'  Cost: ${cost:.4f}')

    print(f'\nTotal cost today: ${total_cost:.4f}')
except Exception as e:
    print(f'Error: {e}')
    print('Admin API key not configured or invalid')
