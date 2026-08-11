#!/bin/bash

echo "========================================="
echo " Starting CyberSim AI Platform           "
echo "========================================="

# Start backend
echo "=> Starting FastAPI Backend..."
uv run uvicorn cybersim.api.main:create_app --factory --reload --port 8000 &
BACKEND_PID=$!

# Start frontend
echo "=> Starting Next.js Frontend..."
cd apps/web
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npx pnpm install
fi
npx pnpm run dev &
FRONTEND_PID=$!

cd ../..

echo ""
echo "========================================="
echo " Services are running!"
echo " Backend API: http://localhost:8000"
echo " Frontend UI: http://localhost:3000/demo"
echo " Press Ctrl+C to stop both services."
echo "========================================="
echo ""

# Cleanup function to kill specific PIDs rather than process group
cleanup() {
    echo -e "\nShutting down services..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    exit 0
}

# Trap termination signals
trap cleanup SIGINT SIGTERM EXIT

# Wait for background processes to keep script running
wait $BACKEND_PID $FRONTEND_PID
