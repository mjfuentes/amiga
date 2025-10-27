#!/usr/bin/env python3
"""
Test the hook's error detection logic on sample outputs
"""

def detect_error_like_hook(tool_output):
    """Replicate hook's error detection logic"""
    output_str = str(tool_output)
    has_error = 'error' in output_str.lower() if output_str else False
    return has_error

# Test cases
test_cases = [
    ("Successful read of error handling code",
     "def handle_error(e):\n    logger.error('Failed')\n    return None",
     "Reading file with error handling → FALSE POSITIVE"),

    ("Successful edit of error message",
     "{'file_path': '/foo/bar.py', 'old_string': 'old error', 'new_string': 'new error'}",
     "Editing error messages → FALSE POSITIVE"),

    ("Grep finding error patterns",
     "Found 5 matches for 'error' in main.py",
     "Grep searching for 'error' → FALSE POSITIVE"),

    ("Actual tool failure",
     "Error: file not found",
     "Genuine error → TRUE POSITIVE"),

    ("Clean success",
     "File edited successfully",
     "Normal success → TRUE NEGATIVE"),

    ("Bash output with stderr info",
     "{'stdout': 'OK', 'stderr': 'warning: deprecated', 'error': None}",
     "Bash with 'error' key → FALSE POSITIVE"),

    ("Reading error documentation",
     "## Error Handling\n\nThis module handles errors gracefully...",
     "Reading docs about errors → FALSE POSITIVE"),
]

print("="*80)
print("TESTING HOOK ERROR DETECTION LOGIC")
print("="*80)

false_positives = 0
true_negatives = 0
true_positives = 0

for name, output, expected in test_cases:
    detected = detect_error_like_hook(output)

    print(f"\n{name}")
    print(f"  Output snippet: {output[:80]}...")
    print(f"  Detected as error: {detected}")
    print(f"  {expected}")

    if "FALSE POSITIVE" in expected and detected:
        false_positives += 1
    elif "TRUE NEGATIVE" in expected and not detected:
        true_negatives += 1
    elif "TRUE POSITIVE" in expected and detected:
        true_positives += 1

print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"False positives detected: {false_positives}/{len(test_cases)}")
print(f"True negatives: {true_negatives}")
print(f"True positives: {true_positives}")
print()
print("CONCLUSION: The hook's simple string matching for 'error' causes many")
print("false positives, especially when working with error handling code.")
