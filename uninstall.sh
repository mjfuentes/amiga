#!/usr/bin/env bash
# Standalone AMIGA uninstaller — for when the CLI itself is broken
set -euo pipefail

# Detect AMIGA_HOME: directory containing this script, or ~/.amiga fallback
if [ -f "$(dirname "${BASH_SOURCE[0]}")/amiga" ]; then
    AMIGA_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    AMIGA_HOME="${AMIGA_HOME:-$HOME/.amiga}"
fi

PORT=3000
PLIST_LABEL="com.amiga.server"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

# Colors (graceful degradation)
if command -v tput >/dev/null 2>&1 && [ -t 1 ]; then
    BOLD=$(tput bold)
    DIM=$(tput dim)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    RED=$(tput setaf 1)
    RESET=$(tput sgr0)
else
    BOLD="" DIM="" GREEN="" YELLOW="" RED="" RESET=""
fi

info()  { echo "${GREEN}>>>${RESET} $*"; }
warn()  { echo "${YELLOW}!!${RESET} $*"; }
err()   { echo "${RED}ERROR:${RESET} $*" >&2; }
dim()   { echo "${DIM}    $*${RESET}"; }

echo ""
echo "${BOLD}AMIGA Uninstaller${RESET}"
echo "================="
echo ""
echo "AMIGA_HOME: $AMIGA_HOME"
echo ""
warn "This will remove AMIGA from your system."
echo ""
echo -n "Type 'yes' to confirm: "
read -r confirm
if [ "$confirm" != "yes" ]; then
    info "Aborted"
    exit 0
fi

echo ""

# 1. Stop server (kill anything on port 3000)
pids=$(lsof -ti:$PORT 2>/dev/null || true)
if [ -n "$pids" ]; then
    info "Stopping server on port $PORT..."
    echo "$pids" | xargs kill -TERM 2>/dev/null || true
    sleep 2
    pids=$(lsof -ti:$PORT 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
    info "Server stopped"
else
    info "Server is not running"
fi

# 2. Unload daemon plist if exists (macOS)
if [ "$(uname)" = "Darwin" ] && [ -f "$PLIST_PATH" ]; then
    info "Unloading daemon..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    info "Daemon removed"
fi

# 3. Remove /usr/local/bin/amiga symlink
symlink="/usr/local/bin/amiga"
if [ -L "$symlink" ]; then
    info "Removing symlink $symlink..."
    rm -f "$symlink" 2>/dev/null || sudo rm -f "$symlink"
    info "Symlink removed"
fi

# 4. Remove PATH entries from shell profiles
profiles=("$HOME/.zshrc" "$HOME/.bashrc")
for profile in "${profiles[@]}"; do
    if [ -f "$profile" ]; then
        if grep -q -E '/\.amiga|# AMIGA' "$profile" 2>/dev/null; then
            info "Cleaning PATH entries from $(basename "$profile")..."
            sed -i.bak -E '/\/\.amiga|# AMIGA/d' "$profile"
            rm -f "$profile.bak"
        fi
    fi
done

echo ""
info "AMIGA services stopped and system entries removed."
echo ""

# 5. Ask to delete AMIGA_HOME directory
if [ -d "$AMIGA_HOME" ]; then
    echo -n "Delete $AMIGA_HOME? [y/N]: "
    read -r delete_dir
    if [[ "$delete_dir" =~ ^[Yy] ]]; then
        rm -rf "$AMIGA_HOME"
        info "Deleted $AMIGA_HOME"
    else
        dim "Files preserved at $AMIGA_HOME"
        dim "To remove later: rm -rf $AMIGA_HOME"
    fi
fi

echo ""
info "Uninstall complete."
echo ""
