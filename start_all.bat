@echo off
chcp 65001 >nul
title Taiwan Stock Screener Launcher

set ROOT=%~dp0

echo ================================
echo Starting Taiwan Stock System
echo ================================

echo.
echo Starting backend...
start cmd /k "cd /d %ROOT%backend && venv\Scripts\activate && uvicorn main:app --reload"

timeout /t 3 /nobreak >nul

echo.
echo Starting frontend...
start cmd /k "cd /d %ROOT%twstock-realtime-screener-frontend && npm run dev"

echo.
echo ================================
echo System started
echo ================================
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://localhost:3000
echo ================================
pause