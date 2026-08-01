@echo off
cd /d "D:\zuomian\2026暑期课\智能化软件工程师训练营\CodingAgentHarness\webui"
call npm install
call npm run build
echo --- Build complete ---
dir dist\index.html