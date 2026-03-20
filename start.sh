#!/bin/bash
cd "$(dirname "$0")"

# Start backend
source venv/bin/activate
uvicorn api.server:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
cd frontend
pnpm dev &
FRONTEND_PID=$!

echo "Backend running on :8000 (PID $BACKEND_PID)"
echo "Frontend running on :3001 (PID $FRONTEND_PID)"
echo "Press Ctrl+C to stop both"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT
wait
