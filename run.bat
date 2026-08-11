@echo off
setlocal

echo =========================================
echo  Setting up CyberSim AI Platform         
echo =========================================

where uv >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: 'uv' is not installed. Please install it from https://github.com/astral-sh/uv or via 'pip install uv'
    exit /b 1
)

where pnpm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: 'pnpm' is not installed. Please install it using 'npm install -g pnpm'
    exit /b 1
)

echo =^> Syncing backend dependencies with uv...
call uv sync
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo =^> Installing frontend dependencies with pnpm...
cd apps\web
call pnpm install
if %ERRORLEVEL% neq 0 (
    cd ..\..
    exit /b %ERRORLEVEL%
)
cd ..\..

echo =========================================
echo  Starting Services...                    
echo =========================================

echo =^> Starting FastAPI Backend...
start "CyberSim Backend" cmd /c "uv run uvicorn cybersim.api.main:create_app --factory --reload --port 8000"

:: Wait briefly for backend
timeout /t 2 /nobreak >nul

echo =^> Starting Next.js Frontend...
cd apps\web
start "CyberSim Frontend" cmd /c "pnpm run dev"
cd ..\..

echo.
echo =========================================
echo  🚀 CyberSim AI Platform is Running!     
echo                                          
echo  🌐 Frontend UI: http://localhost:3000   
echo  ⚙️  Backend API: http://localhost:8000   
echo  🔑 Login Creds: admin / admin           
echo                                          
echo  Close the newly opened command windows  
echo  to stop the services.                   
echo =========================================
echo.
