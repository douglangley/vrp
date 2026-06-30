#!/usr/bin/env bash
# ===========================================================================
#  Run Versatile Radio Programmer from source (macOS). See run-win.bat for
#  the Windows equivalent.
#
#  First run: clones the CHIRP library, downloads Python 3.11 + dependencies
#  via uv, then launches the app (a native wx UI; VoiceOver reads its grid).
#  Subsequent runs just launch (fast). Any arguments (e.g. --debug) are passed
#  through to main.py.
#
#  Prerequisites (one-time):
#    - uv   ->  curl -LsSf https://astral.sh/uv/install.sh | sh
#    - git  ->  ships with Xcode Command Line Tools (xcode-select --install)
# ===========================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# The CHIRP commit this VRP version was tested against (reproducible pin).
CHIRP_SHA=""
if [ -f CHIRP_COMMIT ]; then
  CHIRP_SHA="$(tr -d '[:space:]' < CHIRP_COMMIT)"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo
  echo "'uv' was not found on your PATH."
  echo "Install it once with:   curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "Then open a new terminal and run this script again."
  echo
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo
  echo "'git' was not found on your PATH. Install the Xcode Command Line Tools:"
  echo "  xcode-select --install"
  echo
  exit 1
fi

# CHIRP is a required editable path dependency; clone it into ./chirp if missing,
# pinned to the tested commit (CHIRP_COMMIT) for reproducibility.
if [ ! -f "chirp/chirp/__init__.py" ]; then
  echo "Cloning the CHIRP radio library into ./chirp ..."
  if ! git clone --depth=1 https://github.com/kk7ds/chirp.git chirp; then
    echo
    echo "Failed to clone CHIRP. Check your internet connection and try again."
    exit 1
  fi
  if [ -n "$CHIRP_SHA" ]; then
    echo "Pinning CHIRP to $CHIRP_SHA ..."
    if ! (git -C chirp fetch --depth=1 origin "$CHIRP_SHA" && git -C chirp checkout --quiet "$CHIRP_SHA"); then
      echo "WARNING: could not pin CHIRP to that commit; using latest instead."
    fi
  fi
fi

echo "Installing/updating dependencies (first run downloads Python 3.11 + packages)..."
# --inexact: install the run dependencies but DON'T uninstall anything else
# already in the venv. Without it, plain "uv sync" prunes the env to exactly the
# base deps, removing dev tools like pytest every time a developer runs the app
# (testers are unaffected — a fresh env has nothing extra to keep).
if ! uv sync --inexact; then
  echo
  echo "Dependency installation failed. See the messages above."
  exit 1
fi

echo "Starting Versatile Radio Programmer..."
uv run python main.py "$@"
