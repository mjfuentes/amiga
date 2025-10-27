#!/usr/bin/env bash
# Block recreation of telegram_bot/data as regular directory
# It MUST remain a symlink to ../data

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DATA_PATH="telegram_bot/data"

# Check if telegram_bot/data exists and is a symlink
if [ ! -e "$DATA_PATH" ]; then
    echo -e "${RED}ERROR: $DATA_PATH does not exist${NC}"
    echo "Expected: symlink to ../data"
    echo ""
    echo "Fix:"
    echo "  ln -s ../data telegram_bot/data"
    exit 1
fi

if [ ! -L "$DATA_PATH" ]; then
    echo -e "${RED}ERROR: $DATA_PATH must be a symlink to ../data${NC}"
    echo "Current state:"
    ls -la "$DATA_PATH" 2>&1
    echo ""
    echo "Fix:"
    echo "  rm -rf telegram_bot/data"
    echo "  ln -s ../data telegram_bot/data"
    exit 1
fi

# Verify it points to ../data
TARGET=$(readlink "$DATA_PATH")
if [ "$TARGET" != "../data" ]; then
    echo -e "${YELLOW}WARNING: $DATA_PATH points to unexpected target: $TARGET${NC}"
    echo "Expected: ../data"
    echo ""
    echo "Fix:"
    echo "  rm telegram_bot/data"
    echo "  ln -s ../data telegram_bot/data"
    exit 1
fi

# All checks passed
echo -e "${GREEN}✓ telegram_bot/data is correctly symlinked to ../data${NC}"
exit 0
