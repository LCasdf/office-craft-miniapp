#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> uv sync"
uv sync

echo "==> ruff (if available)"
uv run ruff check packages apps || true

echo "==> pytest"
uv run pytest -q

echo "==> done"
