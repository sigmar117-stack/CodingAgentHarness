@echo off
cd /d "%~dp0webui"
call npm install
call npm run build
echo --- Build complete ---
dir dist\index.html