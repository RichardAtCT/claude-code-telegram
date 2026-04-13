@echo off
:: Claude Code Telegram Bot - Auto-start with watchdog
:: Solo avisa por Telegram si hay un crash, no en arranques normales

chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK=1
set BOT_DIR=C:\Users\ander\Documents\GitHub\claude-code-telegram\.claude\worktrees\awesome-brattain
set LOG_FILE=%BOT_DIR%\data\bot_startup.log
set BOT_TOKEN=8752111954:AAH5S9rzpcP_V8LMs3GBs2op3xdWi80i8A8
set CHAT_ID=8201259371
set CRASH_COUNT=0

cd /d "%BOT_DIR%"

:: Esperar 10 segundos al inicio del sistema para que la red este lista
timeout /t 10 /nobreak >nul

:loop
echo [%date% %time%] Iniciando bot... >> "%LOG_FILE%"

python -m src.main >> "%LOG_FILE%" 2>&1

:: Solo avisa si es un crash (no si se para manualmente)
set /a CRASH_COUNT+=1
echo [%date% %time%] Bot caido (crash #%CRASH_COUNT%). Reiniciando en 15s... >> "%LOG_FILE%"

if %CRASH_COUNT% GEQ 2 (
    curl -s "https://api.telegram.org/bot%BOT_TOKEN%/sendMessage" -d "chat_id=%CHAT_ID%" -d "text=Conexion con PC Asus perdida. Crash #%CRASH_COUNT%. Reiniciando..." >nul 2>&1
)

timeout /t 15 /nobreak >nul
goto loop
