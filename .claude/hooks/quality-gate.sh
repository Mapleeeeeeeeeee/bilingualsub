#!/bin/bash
# Quality gate hook: Full quality check including coverage
# Use this before PR or release

set -euo pipefail

echo "=========================================="
echo "Running Full Quality Gate..."
echo "=========================================="

cd "$(git rev-parse --show-toplevel)" || exit 1

FAILED=0

# 1. Ruff lint
echo ""
echo "[1/7] Ruff lint..."
if uv run ruff check src/ tests/; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# 2. Ruff format
echo ""
echo "[2/7] Ruff format..."
if uv run ruff format --check src/ tests/; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# 3. Mypy
echo ""
echo "[3/7] Mypy type check..."
if uv run mypy src/; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# 4. Vulture dead code
echo ""
echo "[4/7] Vulture dead code..."
if uv run vulture src/bilingualsub --min-confidence=80; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# 5. Unit tests with coverage
echo ""
echo "[5/7] Unit tests (coverage >= 80%)..."
if uv run pytest tests/unit -m unit --cov=bilingualsub --cov-fail-under=80 -q; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# 6. Integration tests
echo ""
echo "[6/7] Integration tests..."
if uv run pytest tests/integration -m integration -q --no-cov; then
    echo "PASS"
else
    echo "FAIL"
    FAILED=1
fi

# 7. Security audit
echo ""
echo "[7/7] Security audit..."
if uv run pip-audit 2>/dev/null; then
    echo "PASS"
else
    echo "WARNING (non-blocking)"
fi

echo ""
echo "=========================================="
if [[ $FAILED -eq 1 ]]; then
    echo "Quality Gate: FAILED"
    exit 1
else
    echo "Quality Gate: PASSED"
    exit 0
fi
