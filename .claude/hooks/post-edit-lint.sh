#!/bin/bash
# Post-edit hook: Run ruff check on edited Python files
# This hook runs after Claude edits a file

set -euo pipefail

FILE_PATH="$1"

# Only check Python files
if [[ "$FILE_PATH" == *.py ]]; then
    # Run ruff check (non-blocking, just report)
    if command -v uv &> /dev/null; then
        uv run ruff check "$FILE_PATH" --fix 2>/dev/null || true
        uv run ruff format "$FILE_PATH" 2>/dev/null || true
    fi
fi

exit 0
