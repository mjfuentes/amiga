"""Simple cache implementation - needs improvement"""

cache = {}

def get_data(key):
    if key in cache:
        return cache[key]
    data = expensive_fetch(key)
    cache[key] = data
    return data

def expensive_fetch(key):
    # Simulate expensive operation
    import time
    time.sleep(1)
    return f"data_{key}"
