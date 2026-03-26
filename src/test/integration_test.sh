#!/bin/bash
# Integration test for the Wire Fact Gathering Tool runner.
# Run this on a machine with access to a Wire deployment.
#
# Prerequisites:
# - SSH access to the admin host with the configured key
# - kubectl configured with access to the Wire cluster
# - A valid config.yaml file
#
# Usage:
#   ./src/test/integration_test.sh config.yaml

set -euo pipefail

CONFIG="${1:?Usage: $0 <config.yaml>}"
OUTPUT="/tmp/wire-facts-test-$(date +%Y%m%d-%H%M%S).jsonl"

echo "=== Wire Fact Gathering Tool — Integration Test ==="
echo "Config: $CONFIG"
echo "Output: $OUTPUT"
echo ""

# Run all targets
echo "--- Running all targets ---"
python3 src/script/runner.py --config "$CONFIG" --output "$OUTPUT" --verbose

echo ""
echo "--- Output file ---"
echo "Lines: $(wc -l < "$OUTPUT")"
echo "Size: $(du -h "$OUTPUT" | cut -f1)"
echo ""

# Validate output format
echo "--- Validating JSONL format ---"
python3 -c "
import json
import sys
errors = 0
with open('$OUTPUT') as f:
    for i, line in enumerate(f, 1):
        try:
            obj = json.loads(line)
            required = ['path', 'value', 'description']
            for key in required:
                if key not in obj:
                    print(f'Line {i}: missing key \"{key}\"')
                    errors += 1
        except json.JSONDecodeError as e:
            print(f'Line {i}: invalid JSON — {e}')
            errors += 1
if errors:
    print(f'{errors} error(s) found')
    sys.exit(1)
else:
    print('All lines valid')
"

echo ""
echo "--- Running single target test ---"
python3 src/script/runner.py --config "$CONFIG" --output /tmp/single-target-test.jsonl \
    --target host/disk_usage --verbose

echo ""
echo "--- Running category test ---"
python3 src/script/runner.py --config "$CONFIG" --output /tmp/category-test.jsonl \
    --target kubernetes --verbose

echo ""
echo "=== Integration test complete ==="
echo "Full output: $OUTPUT"
