@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ============================================================
:: AGENTE LOCAL AUTONOMO v14 - Arranque desde raiz del repo
:: ============================================================
:: Este archivo va en la RAIZ del repositorio.
:: Auto-detecta donde esta app.py y ejecuta desde ahi.
:: ============================================================

title Agente Autonomo v14

echo.
echo  ========================================================
echo   AGENTE LOCAL AUTONOMO v14
echo   Arquitectura Modular / ReAct + TripleMemory
echo  ========================================================
echo.

:: ============================================================
:: BUSCAR APP.PY
:: ============================================================
set "APP_DIR="

:: 1. Mismo directorio
if exist "%~dp0app.py" (
    set "APP_DIR=%~dp0"
    goto :found
)

:: 2. Subdirectorio agente_v14
if exist "%~dp0agente_v14\app.py" (
    set "APP_DIR=%~dp0agente_v14"
    goto :found
)

:: 3. Directorio actual
if exist "%cd%\app.py" (
    set "APP_DIR=%cd%"
    goto :found
)

:: 4. Subdirectorio del directorio actual
for /d %%D in ("%cd%\*") do (
    if exist "%%D\app.py" (
        set "APP_DIR=%%D"
        goto :found
    )
)

:: No encontrado
echo  [ERROR] No se encontro app.py
echo.
echo  Estructura esperada:
echo    agente_v14\start.bat    ^<-- este archivo
echo    agente_v14\app.py
echo    agente_v14\config.py
echo.
echo  O si estas en la raiz del repo:
echo    start.bat               ^<-- este archivo
echo    agente_v14\app.py
echo.
pause
exit /b 1

:found
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

echo  Proyecto encontrado: %APP_DIR%
echo.

:: ============================================================
:: VERIFICAR PYTHON
:: ============================================================
echo  [1/5] Buscando Python...
echo.

set "PYTHON_CMD="
where python >nul 2>&1
if !ERRORLEVEL!==0 (
    set "PYTHON_CMD=python"
) else (
    where python3 >nul 2>&1
    if !ERRORLEVEL!==0 (
        set "PYTHON_CMD=python3"
    )
)

:: Buscar en rutas comunes de Windows
if not defined PYTHON_CMD (
    for %%P in (
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python38\python.exe"
        "C:\Python312\python.exe"
        "C:\Python311\python.exe"
        "C:\Python310\python.exe"
    ) do (
        if exist %%P (
            set "PYTHON_CMD=%%P"
            goto :python_found
        )
    )
)

:python_found
if not defined PYTHON_CMD (
    echo  [ERROR] Python no encontrado.
    echo.
    echo  Descarga Python 3.8+ de: https://www.python.org/downloads/
    echo  IMPORTANTE: Marca "Add Python to PATH" al instalar.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('%PYTHON_CMD% --version 2^>^&1') do echo  [OK] %%v

:: ============================================================
:: VERIFICAR DEPENDENCIAS
:: ============================================================
echo.
echo  [2/5] Verificando dependencias...
echo.

set "NEED_INSTALL=0"

%PYTHON_CMD% -c "import streamlit" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] streamlit
) else (
    echo  [!!] streamlit NO instalado
    set "NEED_INSTALL=1"
)

%PYTHON_CMD% -c "import ollama" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] ollama
) else (
    echo  [!!] ollama NO instalado
    set "NEED_INSTALL=1"
)

%PYTHON_CMD% -c "import chromadb" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] chromadb
) else (
    echo  [!!] chromadb NO instalado
    set "NEED_INSTALL=1"
)

if %NEED_INSTALL%==1 (
    echo.
    echo  Instalando dependencias faltantes...
    %PYTHON_CMD% -m pip install streamlit ollama chromadb --quiet
    if !ERRORLEVEL! neq 0 (
        echo  [ERROR] Fallo la instalacion. Prueba manual:
        echo      pip install streamlit ollama chromadb
        pause
        exit /b 1
    )
    echo  [OK] Dependencias instaladas
)

:: ============================================================
:: VERIFICAR OLLAMA
:: ============================================================
echo.
echo  [3/5] Verificando Ollama...
echo.

%PYTHON_CMD% -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] Ollama corriendo en localhost:11434
    echo.
    echo  Modelos:
    %PYTHON_CMD% -c "import urllib.request,json; resp=urllib.request.urlopen('http://localhost:11434/api/tags',timeout=5); data=json.loads(resp.read()); [print(f'  - {m[\"name\"]} ({m[\"size\"]/(1024**3):.1f} GB)') for m in data.get('models',[])]" 2>nul
    goto :ollama_ok
)

:: Intentar iniciar Ollama
echo  [!!] Ollama no responde. Intentando iniciar...
start "" ollama app >nul 2>&1

:: Esperar hasta 20 segundos
echo  Esperando a Ollama...
for /L %%i in (1,1,20) do (
    %PYTHON_CMD% -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=2)" >nul 2>&1
    if !ERRORLEVEL!==0 (
        echo  [OK] Ollama iniciado!
        goto :ollama_ok
    )
    <nul set /p "=."
    timeout /t 1 /nobreak >nul
)
echo.

:: Buscar en rutas alternativas
for %%P in (
    "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
    "%ProgramFiles%\Ollama\ollama app.exe"
) do (
    if exist %%P (
        echo  Iniciando desde: %%P
        start "" %%P >nul 2>&1
        timeout /t 5 /nobreak >nul
        %PYTHON_CMD% -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
        if !ERRORLEVEL!==0 (
            echo  [OK] Ollama iniciado!
            goto :ollama_ok
        )
    )
)

echo.
echo  [!!] No se pudo iniciar Ollama automaticamente.
echo      Abre Ollama desde el Menu Inicio y vuelve a ejecutar start.bat
echo.
echo  Presiona una tecla para continuar sin Ollama, o Ctrl+C para salir...
pause >nul

:ollama_ok
:: Verificar modelos
%PYTHON_CMD% -c "import urllib.request,json; resp=urllib.request.urlopen('http://localhost:11434/api/tags',timeout=5); data=json.loads(resp.read()); exit(0 if data.get('models') else 1)" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo.
    echo  [!!] No hay modelos. Descargando qwen3:4b...
    ollama pull qwen3:4b
)

:: ============================================================
:: VERIFICAR PUERTO
:: ============================================================
echo.
echo  [4/5] Verificando puerto 8501...
echo.

set "USE_PORT=8501"
netstat -ano 2>nul | findstr ":8501 " | findstr "LISTENING" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [!!] Puerto 8501 en uso. Usando 8502.
    set "USE_PORT=8502"
) else (
    echo  [OK] Puerto 8501 disponible
)

:: ============================================================
:: CREAR DIRECTORIOS NECESARIOS
:: ============================================================
echo.
echo  [5/5] Preparando directorios...
echo.

if not exist "%USERPROFILE%\.ia-local\learning\vectors" (
    mkdir "%USERPROFILE%\.ia-local\learning\vectors" 2>nul
)
echo  [OK] Directorios listos

:: ============================================================
:: INICIAR
:: ============================================================
echo.
echo  ========================================================
echo   INICIANDO AGENTE
echo  ========================================================
echo.
echo  Directorio: %APP_DIR%
echo  Puerto:     %USE_PORT%
echo  URL:        http://localhost:%USE_PORT%
echo.
echo  Presiona Ctrl+C para detener.
echo.

cd /d "%APP_DIR%"
%PYTHON_CMD% -m streamlit run app.py --server.port %USE_PORT%

echo.
echo  Agente detenido.
pause
