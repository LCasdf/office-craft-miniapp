#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> uv sync"
uv sync

echo "==> ruff"
uv run ruff check packages apps

echo "==> pytest"
uv run pytest -q

echo "==> done"
