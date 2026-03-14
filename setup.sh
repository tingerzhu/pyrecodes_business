#!/usr/bin/env bash
# pyrecodes environment setup
# NOTE: rewet and wntrfr are NOT installed due to dependency conflicts.

set -e

REQUIRED_PYTHON="3.9.13"

# --- Check Python version ---
check_python() {
    local py="$1"
    if command -v "$py" &>/dev/null; then
        local ver
        ver=$("$py" -c "import sys; print('%d.%d.%d' % sys.version_info[:3])")
        python3 -c "
import sys
req = tuple(int(x) for x in '$REQUIRED_PYTHON'.split('.'))
got = tuple(int(x) for x in '$ver'.split('.'))
sys.exit(0 if got >= req else 1)
" 2>/dev/null && echo "$py" && return 0
    fi
    return 1
}

PYTHON=$(check_python python3.9 || check_python python3 || check_python python || true)

if [ -z "$PYTHON" ]; then
    echo "Python >= $REQUIRED_PYTHON not found. Installing via pyenv..."
    if ! command -v pyenv &>/dev/null; then
        echo "Installing pyenv..."
        curl -fsSL https://pyenv.run | bash
        export PATH="$HOME/.pyenv/bin:$PATH"
        eval "$(pyenv init -)"
    fi
    pyenv install "$REQUIRED_PYTHON"
    pyenv local "$REQUIRED_PYTHON"
    PYTHON=$(pyenv which python)
fi

echo "Using Python: $PYTHON ($($PYTHON --version))"

# --- Create virtual environment ---
if [ ! -d "env" ]; then
    "$PYTHON" -m venv env
fi
source env/bin/activate

# --- Install requirements (excluding rewet and wntrfr) ---
pip install --upgrade pip

# Filter out rewet and wntrfr from requirements.txt and install
grep -v -E "^\s*(rewet|wntrfr)" requirements.txt | pip install -r /dev/stdin

echo ""
echo "Setup complete."
echo ""
echo "NOTE: The following packages were NOT installed due to dependency conflicts:"
echo "  - rewet"
echo "  - wntrfr"
echo "To install them manually, run: pip install rewet==0.2.0b12 wntrfr==1.1.0.1.2"
