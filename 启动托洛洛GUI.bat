@echo off
chcp 65001 >nul
title TololoAgent Launcher

echo ==============================================
echo   TololoAgent - Solar System Knowledge Graph
echo   Python + Neo4j + Ollama + Chroma
echo ==============================================
echo.

cd /d "%~dp0"

REM ==== Step 1: Check if Ollama is installed ====
echo [1/5] Checking Ollama installation...
where ollama >nul 2>&1
if errorlevel 1 (
    echo [INFO] Ollama not found, trying to install...
    echo.
    winget install --id Ollama.Ollama --silent --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo [ERROR] Auto-install failed. Please install manually:
        echo   1. Go to https://ollama.com/download
        echo   2. Download and run OllamaSetup.exe
        echo   3. Restart this script after installation
        echo.
        pause
        exit /b 1
    )
    echo [OK] Ollama installed successfully!
    echo.
) else (
    echo [OK] Ollama is installed
    echo.
)

REM ==== Step 2: Set model directory ====
echo [2/5] Setting model storage directory...
set "OLLAMA_MODELS=%~dp0models\ollama"
if not exist "%OLLAMA_MODELS%" mkdir "%OLLAMA_MODELS%"
echo [OK] Model directory: %OLLAMA_MODELS%
echo.

REM ==== Step 3: Start Ollama service ====
echo [3/5] Starting Ollama service...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [WAIT] Ollama service not running, starting...
    start /b "" "ollama" serve >nul 2>&1
    echo   Waiting 5 seconds...
    timeout /t 5 /nobreak >nul
    curl -s http://localhost:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo   Still waiting...
        timeout /t 5 /nobreak >nul
        curl -s http://localhost:11434/api/tags >nul 2>&1
        if errorlevel 1 (
            echo [ERROR] Failed to start Ollama service!
            echo   Please open Ollama desktop app manually.
            pause
            exit /b 1
        )
    )
)
echo [OK] Ollama service is running
echo.

REM ==== Step 4: Check and download Qwen3 model ====
echo [4/5] Checking Qwen3 model (qwen3:4b)...
curl -s http://localhost:11434/api/tags > "%TEMP%\ollama_tags.json" 2>&1
findstr "qwen3:4b" "%TEMP%\ollama_tags.json" >nul 2>&1
if errorlevel 1 (
    echo [WAIT] Model qwen3:4b not found, downloading...
    echo   Model size: ~2-3GB, please be patient.
    echo.
    echo ====== Downloading model ======
    echo.
    ollama pull qwen3:4b
    if errorlevel 1 (
        echo [ERROR] Model download failed!
        echo   Please run manually: ollama pull qwen3:4b
        pause
        exit /b 1
    )
    echo [OK] Model qwen3:4b downloaded!
) else (
    echo [OK] Model qwen3:4b is ready
)
del "%TEMP%\ollama_tags.json" 2>nul
echo.

REM ==== Step 5: Find Python and Launch GUI ====
echo [5/5] Preparing to launch GUI...
echo.

REM Check a known Python path first
set "PYTHON_PATH="
if exist "D:\python.exe" set "PYTHON_PATH=D:\python.exe"

REM Try common Python install locations
if not defined PYTHON_PATH if exist "D:\Python312\python.exe" set "PYTHON_PATH=D:\Python312\python.exe"
if not defined PYTHON_PATH if exist "C:\Python312\python.exe" set "PYTHON_PATH=C:\Python312\python.exe"
if not defined PYTHON_PATH if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe" set "PYTHON_PATH=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"

REM Fall back to Python from PATH
if not defined PYTHON_PATH set "PYTHON_PATH=python"

echo   Python: %PYTHON_PATH%
echo.
echo ==============================================
echo   All checks passed, starting GUI...
echo ==============================================
echo.

echo  Launching TololoAgent, please wait...
echo  Missing dependencies will be installed automatically if needed.
echo.

"%PYTHON_PATH%" main.py
exit /B 0
