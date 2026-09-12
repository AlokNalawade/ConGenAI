#!/bin/bash
# ConGen AI Content Factory Startup Script

set -e

# Navigate to application root
cd "$(dirname "$0")"

echo "=================================================="
echo "🚀 Starting ConGen AI Content Factory..."
echo "=================================================="

# 1. Start Docker services (PostgreSQL & Redis)
if command -v docker &> /dev/null; then
    echo "📦 Checking infrastructure services (Postgres & Redis)..."
    docker compose up -d
else
    echo "⚠️  Docker not found. Ensure PostgreSQL (5432) and Redis (6379) are running locally."
fi

# 2. Verify / Initialize DB schema
echo "🗄️  Verifying database schema..."
PYTHONPATH=apps/api ./apps/api/.venv/bin/python apps/api/app/db/init_db.py > /dev/null 2>&1 || true

# 3. Start ARQ Pipeline Worker in background
echo "⚙️  Starting ARQ Pipeline Background Worker..."
PYTHONPATH=apps/api ./apps/api/.venv/bin/python -m app.workflows.task_queue &
WORKER_PID=$!

# Trap Ctrl+C (SIGINT) and kill background worker
cleanup() {
    echo ""
    echo "🛑 Shutting down ConGen AI Content Factory..."
    if kill -0 $WORKER_PID 2>/dev/null; then
        echo "   Stopping ARQ Worker (PID: $WORKER_PID)..."
        kill -SIGTERM $WORKER_PID 2>/dev/null || true
        wait $WORKER_PID 2>/dev/null || true
    fi
    echo "👋 Shutdown complete."
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "=================================================="
echo "✨ All services online!"
echo "📍 Web Dashboard:   http://localhost:8000"
echo "📖 API Docs:        http://localhost:8000/docs"
echo "⚙️  Worker PID:      $WORKER_PID"
echo "Press Ctrl+C to stop all services."
echo "=================================================="

# 4. Start FastAPI server in foreground
PYTHONPATH=apps/api ./apps/api/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
