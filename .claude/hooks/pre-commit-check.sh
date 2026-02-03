#!/bin/bash
# Pre-commit hook: Run all quality checks before commit
# This hook blocks commit if checks fail

set -euo pipefail

echo "Running pre-commit quality checks..."

# Change to project root
cd "$(git rev-parse --show-toplevel)" || exit 1

FAILED=0

# 1. Ruff lint
echo "  Checking: Ruff lint..."
if ! uv run ruff check src/ tests/ 2>/dev/null; then
    echo "  FAILED: Ruff lint"
    FAILED=1
fi

# 2. Ruff format
echo "  Checking: Ruff format..."
if ! uv run ruff format --check src/ tests/ 2>/dev/null; then
    echo "  FAILED: Ruff format"
    FAILED=1
fi

# 3. Mypy
echo "  Checking: Mypy type check..."
if ! uv run mypy src/ 2>/dev/null; then
    echo "  FAILED: Mypy type check"
    FAILED=1
fi

# 4. Vulture dead code
echo "  Checking: Vulture dead code..."
if ! uv run vulture src/bilingualsub --min-confidence=80 2>/dev/null; then
    echo "  FAILED: Vulture dead code detection"
    FAILED=1
fi

# 5. Unit tests
echo "  Checking: Unit tests..."
if ! uv run pytest tests/unit -m unit -q --no-cov 2>/dev/null; then
    echo "  FAILED: Unit tests"
    FAILED=1
fi

if [[ $FAILED -eq 1 ]]; then
    echo ""
    echo "Pre-commit checks FAILED. Please fix the issues above."
    exit 1
fi

echo "All pre-commit checks passed!"
exit 0
