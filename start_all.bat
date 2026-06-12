@echo off
chcp 65001 >nul 2>&1
title ZAI - Agente Local Autonomo
color 0A

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║           ZAI - Agente Local Autonomo v14             ║
echo ║           Inicio Unificado de Servicios               ║
echo ╚════════════════════════════════════════════════════════╝
echo.

:: ── Verificar Python ──
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.10+
    pause
    exit /b 1
)
echo [OK] Python encontrado

:: ── Verificar Node.js ──
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js no encontrado. Instala Node.js 18+
    pause
    exit /b 1
)
echo [OK] Node.js encontrado

:: ── Buscar directorio del agente ──
set "AGENT_DIR="
if exist "%~dp0agente_v14\bridge_api.py" (
    set "AGENT_DIR=%~dp0agente_v14"
) else if exist "%~dp0..\agente_v14\bridge_api.py" (
    set "AGENT_DIR=%~dp0..\agente_v14"
) else if exist "%~dp0bridge_api.py" (
    set "AGENT_DIR=%~dp0"
)

if "%AGENT_DIR%"=="" (
    echo [ERROR] No se encontro bridge_api.py
    echo Busca en: %~dp0 o subcarpetas
    pause
    exit /b 1
)
echo [OK] Agente encontrado: %AGENT_DIR%

:: ── Buscar directorio Next.js ──
set "WEB_DIR="
if exist "%~dp0package.json" (
    set "WEB_DIR=%~dp0"
) else if exist "%~dp0src\app\page.tsx" (
    set "WEB_DIR=%~dp0"
)

if "%WEB_DIR%"=="" (
    echo [WARN] No se encontro proyecto Next.js en %~dp0
    echo La interfaz web no se iniciara.
)

:: ── Verificar Ollama ──
echo.
echo [..] Verificando Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [WARN] Ollama no esta corriendo. Iniciando...
    start "" /B ollama serve
    timeout /t 5 /nobreak >nul
    curl -s http://localhost:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] No se pudo iniciar Ollama.
        echo Ejecuta manualmente: ollama serve
        pause
        exit /b 1
    )
)
echo [OK] Ollama corriendo

:: ── Verificar dependencias Python ──
echo.
echo [..] Verificando dependencias Python...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo [..] Instalando fastapi uvicorn...
    pip install fastapi uvicorn --quiet
)
echo [OK] Dependencias Python OK

:: ── Verificar dependencias Node ──
if not "%WEB_DIR%"=="" (
    if not exist "%WEB_DIR%node_modules" (
        echo [..] Instalando dependencias Node.js...
        cd /d "%WEB_DIR%"
        npm install
    )
    echo [OK] Dependencias Node.js OK
)

:: ── Verificar puerto 8000 (Bridge) ──
echo.
curl -s http://localhost:8000/api/health >nul 2>&1
if not errorlevel 1 (
    echo [OK] Bridge ya corriendo en puerto 8000
) else (
    echo [..] Iniciando Bridge API en puerto 8000...
    start "ZAI Bridge" cmd /c "cd /d "%AGENT_DIR%" && python bridge_api.py"
    timeout /t 3 /nobreak >nul
    curl -s http://localhost:8000/api/health >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Bridge tarda en arrancar, esperando...
        timeout /t 5 /nobreak >nul
    )
    echo [OK] Bridge iniciado
)

:: ── Verificar puerto 3000 (Web) ──
if not "%WEB_DIR%"=="" (
    echo.
    echo [..] Iniciando interfaz web en puerto 3000...
    start "ZAI Web" cmd /c "cd /d "%WEB_DIR%" && npm run dev"
    echo [OK] Interfaz web iniciada
)

:: ── Resumen ──
echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║                 SERVICIOS INICIADOS                    ║
echo ╠════════════════════════════════════════════════════════╣
echo ║  Ollama      : http://localhost:11434                  ║
echo ║  Bridge API  : http://localhost:8000                   ║
echo ║  Web UI      : http://localhost:3000                   ║
echo ╠════════════════════════════════════════════════════════╣
echo ║  Abre tu navegador en: http://localhost:3000           ║
echo ║                                                        ║
echo ║  AGENT mode = Con herramientas (Bridge + Ollama)       ║
echo ║  CHAT mode  = Solo chat (Ollama directo)               ║
echo ╚════════════════════════════════════════════════════════╝
echo.
echo Presiona Ctrl+C para cerrar este script.
echo Los servicios seguiran corriendo en sus ventanas.
echo.
pause
