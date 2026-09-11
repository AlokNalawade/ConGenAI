#!/bin/bash
# ConGen AI Content Factory Startup Script

set -e

# Navigate to application root
cd "$(dirname "$0")"

echo "=========================================="
echo "🚀 ConGen AI Content Factory Starting..."
echo "📍 Open browser: http://localhost:8000"
echo "=========================================="

# Run uvicorn using the virtual environment python interpreter
PYTHONPATH=apps/api ./apps/api/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
