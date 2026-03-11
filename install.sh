#!/usr/bin/env bash
# AMIGA Remote Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/mjfuentes/amiga/main/install.sh | bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Colors (graceful degradation for non-interactive / no tput)
# ---------------------------------------------------------------------------
if command -v tput >/dev/null 2>&1 && [ -t 1 ]; then
    BOLD=$(tput bold)
    DIM=$(tput dim)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    RED=$(tput setaf 1)
    CYAN=$(tput setaf 6)
    RESET=$(tput sgr0)
else
    BOLD="" DIM="" GREEN="" YELLOW="" RED="" CYAN="" RESET=""
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { echo "${GREEN}>>>${RESET} $*"; }
warn()  { echo "${YELLOW}!!${RESET} $*"; }
err()   { echo "${RED}ERROR:${RESET} $*" >&2; }
step()  { echo ""; echo "${BOLD}${CYAN}--- $* ---${RESET}"; }

fail() {
    err "$1"
    exit 1
}

add_path_to_profile() {
    local dir_to_add="$1"
    local profile=""
    local shell_name
    shell_name="$(basename "${SHELL:-/bin/bash}")"

    case "$shell_name" in
        zsh)  profile="$HOME/.zshrc" ;;
        bash)
            if [ -f "$HOME/.bash_profile" ]; then
                profile="$HOME/.bash_profile"
            else
                profile="$HOME/.bashrc"
            fi
            ;;
        *)    profile="$HOME/.profile" ;;
    esac

    local path_line="export PATH=\"$dir_to_add:\$PATH\""

    # Idempotent: don't duplicate entries
    if [ -f "$profile" ] && grep -qF "$dir_to_add" "$profile" 2>/dev/null; then
        info "PATH entry already in $profile"
        return
    fi

    echo "" >> "$profile"
    echo "# AMIGA" >> "$profile"
    echo "$path_line" >> "$profile"
    info "Added $dir_to_add to PATH in $profile"
    warn "Restart your shell or run: source $profile"
}

AMIGA_HOME="${AMIGA_HOME:-$HOME/.amiga}"

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo "${BOLD}Installing AMIGA${RESET}"
echo "Autonomous Modular Interactive Graphical Agent"
echo "-----------------------------------------------"

# ---------------------------------------------------------------------------
# 1. Check prerequisites
# ---------------------------------------------------------------------------
step "Checking prerequisites"

# Python 3.12+
if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 not found. Install Python 3.12+ and try again.
  macOS:  brew install python@3.12
  Ubuntu: sudo apt install python3.12"
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
    fail "Python 3.12+ required (found $PY_VERSION).
  macOS:  brew install python@3.12
  Ubuntu: sudo apt install python3.12"
fi
info "Python $PY_VERSION"

# Node 18+
if ! command -v node >/dev/null 2>&1; then
    fail "Node.js not found. Install Node 18+ and try again.
  macOS:  brew install node
  Ubuntu: https://nodejs.org/en/download"
fi

NODE_VERSION=$(node -v | sed 's/^v//')
NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 18 ]; then
    fail "Node 18+ required (found $NODE_VERSION).
  macOS:  brew install node
  Ubuntu: https://nodejs.org/en/download"
fi
info "Node $NODE_VERSION"

# git
if ! command -v git >/dev/null 2>&1; then
    fail "git not found. Install git and try again.
  macOS:  xcode-select --install
  Ubuntu: sudo apt install git"
fi
info "git $(git --version | awk '{print $3}')"

# jq (optional — warn only)
if ! command -v jq >/dev/null 2>&1; then
    warn "jq not found. Some features (hooks, CLI operations) need it."
    echo "    Install with: brew install jq (macOS) or sudo apt install jq (Linux)"
else
    info "jq $(jq --version 2>/dev/null | sed 's/^jq-//')"
fi

# ---------------------------------------------------------------------------
# 2. Install location — clone or update
# ---------------------------------------------------------------------------
step "Install location"

if [ -d "$AMIGA_HOME" ]; then
    if [ -d "$AMIGA_HOME/.git" ]; then
        info "Existing installation found at $AMIGA_HOME"
        info "Updating..."
        cd "$AMIGA_HOME"
        git pull --ff-only || {
            warn "Fast-forward pull failed. Trying merge..."
            git pull || fail "Could not update repository. Resolve conflicts manually in $AMIGA_HOME"
        }
    else
        fail "$AMIGA_HOME exists but is not an AMIGA installation. Remove it or set AMIGA_HOME to a different path."
    fi
else
    step "Cloning repository"
    info "Cloning into $AMIGA_HOME..."

    # Try SSH first, fall back to HTTPS
    if git clone git@github.com:mjfuentes/amiga.git "$AMIGA_HOME" 2>/dev/null; then
        info "Cloned via SSH"
    elif git clone https://github.com/mjfuentes/amiga.git "$AMIGA_HOME"; then
        info "Cloned via HTTPS"
    else
        fail "Could not clone repository. Check your network connection and GitHub access."
    fi
fi

cd "$AMIGA_HOME"

# ---------------------------------------------------------------------------
# 3. Run setup (delegates interactive prompts to the CLI wizard)
# ---------------------------------------------------------------------------
step "Running setup"

if [ -f "$AMIGA_HOME/amiga" ]; then
    chmod +x "$AMIGA_HOME/amiga"
    bash "$AMIGA_HOME/amiga" setup
else
    fail "amiga CLI not found at $AMIGA_HOME/amiga. The repository may be incomplete."
fi

# ---------------------------------------------------------------------------
# 4. Add to PATH
# ---------------------------------------------------------------------------
step "Adding to PATH"

SYMLINK_CREATED=false

# Try /usr/local/bin first (common on macOS, many Linux distros)
if [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
    ln -sf "$AMIGA_HOME/amiga" /usr/local/bin/amiga
    SYMLINK_CREATED=true
    info "Symlinked amiga -> /usr/local/bin/amiga"
fi

# Fallback: ~/.local/bin (XDG standard)
if [ "$SYMLINK_CREATED" = false ]; then
    LOCAL_BIN="$HOME/.local/bin"
    mkdir -p "$LOCAL_BIN"
    ln -sf "$AMIGA_HOME/amiga" "$LOCAL_BIN/amiga"
    SYMLINK_CREATED=true
    info "Symlinked amiga -> $LOCAL_BIN/amiga"

    # Ensure ~/.local/bin is in PATH for future shells
    if ! echo "$PATH" | tr ':' '\n' | grep -qx "$LOCAL_BIN"; then
        add_path_to_profile "$LOCAL_BIN"
    fi
fi

# Last resort: add AMIGA_HOME itself to PATH
if [ "$SYMLINK_CREATED" = false ]; then
    add_path_to_profile "$AMIGA_HOME"
fi

# ---------------------------------------------------------------------------
# 5. Success
# ---------------------------------------------------------------------------
echo ""
echo "-----------------------------------------------"
echo "${BOLD}${GREEN}AMIGA installed successfully.${RESET}"
echo ""
echo "  Run '${CYAN}amiga start${RESET}' to start the server."
echo "  Run '${CYAN}amiga help${RESET}'  for all commands."
echo ""
