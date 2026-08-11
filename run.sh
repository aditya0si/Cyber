#!/bin/bash
set -e

echo "========================================="
echo " Setting up CyberSim AI Platform         "
echo "========================================="

# Check requirements
if ! command -v uv &> /dev/null; then
    echo "Error: 'uv' is not installed. Please install it from https://github.com/astral-sh/uv or via 'pip install uv'"
    exit 1
fi

if ! command -v pnpm &> /dev/null; then
    echo "Error: 'pnpm' is not installed. Please install it using 'npm install -g pnpm'"
    exit 1
fi

echo "=> Syncing backend dependencies with uv..."
uv sync

echo "=> Installing frontend dependencies with pnpm..."
cd apps/web
pnpm install
cd ../..

echo "========================================="
echo " Starting Services...                    "
echo "========================================="

echo "=> Starting FastAPI Backend..."
uv run uvicorn cybersim.api.main:create_app --factory --reload --port 8000 &
BACKEND_PID=$!

# Wait briefly for backend to start up
sleep 2

echo "=> Starting Next.js Frontend..."
cd apps/web
pnpm run dev &
FRONTEND_PID=$!
cd ../..

echo ""
echo "========================================="
echo " 🚀 CyberSim AI Platform is Running!     "
echo "                                         "
echo " 🌐 Frontend UI: http://localhost:3000   "
echo " ⚙️  Backend API: http://localhost:8000   "
echo " 🔑 Login Creds: admin / admin           "
echo "                                         "
echo " Press Ctrl+C to stop both services.     "
echo "========================================="
echo ""

cleanup() {
    echo -e "\nShutting down services..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT
wait $BACKEND_PID $FRONTEND_PID
