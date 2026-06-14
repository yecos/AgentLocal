@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ============================================================
:: AgentLocal - Script de Instalacion y Configuracion (Windows)
:: ============================================================
:: Ejecutar DESPUES de clonar el repo:
::   git clone https://github.com/yecos/AgentLocal.git
::   cd AgentLocal
::   setup.bat
:: ============================================================

title AgentLocal - Instalacion

echo.
echo  ========================================================
echo   AgentLocal - Instalacion y Configuracion
echo  ========================================================
echo.

set "PROJECT_DIR=%~dp0"
echo  Directorio del proyecto: %PROJECT_DIR%
echo.

:: ============================================================
:: 1. VERIFICAR PRERREQUISITOS
:: ============================================================
echo  [1/8] Verificando prerrequisitos...
echo.

set "ERRORS=0"

:: Python
where python >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo  [XX] Python no encontrado. Instala Python 3.10+ desde https://www.python.org
    set "ERRORS=1"
) else (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  [OK] Python: %%v
    set "PYTHON_CMD=python"
)

:: Node.js
where node >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo  [XX] Node.js no encontrado. Instala Node.js 18+ desde https://nodejs.org
    set "ERRORS=1"
) else (
    for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo  [OK] Node.js: %%v
)

:: npm
where npm >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo  [XX] npm no encontrado.
    set "ERRORS=1"
) else (
    for /f "tokens=*" %%v in ('npm --version 2^>^&1') do echo  [OK] npm: %%v
)

:: Ollama
where ollama >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo  [!!] Ollama no encontrado. Instalalo desde https://ollama.com
    echo       Despues descarga un modelo: ollama pull qwen3:4b
) else (
    echo  [OK] Ollama instalado
)

if !ERRORS!==1 (
    echo.
    echo  [XX] Faltan prerrequisitos. Instalalos y vuelve a ejecutar este script.
    pause
    exit /b 1
)

echo.

:: ============================================================
:: 2. LIMPIAR CLONES DUPLICADOS
:: ============================================================
echo  [2/8] Limpiando duplicados...
echo.

for %%d in (AgentLocal AgentLocal-repo) do (
    if exist "%PROJECT_DIR%%%d" (
        echo  [..] Eliminando %%d/ ^(clon duplicado^)
        rmdir /s /q "%PROJECT_DIR%%%d" 2>nul
        echo  [OK] %%d/ eliminado
    )
)

if exist "%PROJECT_DIR%download" (
    echo  [..] Eliminando download/ ^(archivos generados^)
    rmdir /s /q "%PROJECT_DIR%download" 2>nul
    echo  [OK] download/ eliminado
)

echo  [OK] Limpieza completada
echo.

:: ============================================================
:: 3. CREAR ARCHIVO .env
:: ============================================================
echo  [3/8] Configurando entorno...
echo.

if not exist "%PROJECT_DIR%.env" (
    copy "%PROJECT_DIR%.env.example" "%PROJECT_DIR%.env" >nul
    echo  [OK] .env creado desde .env.example
) else (
    echo  [OK] .env ya existe
)

echo.

:: ============================================================
:: 4. CREAR DIRECTORIOS NECESARIOS
:: ============================================================
echo  [4/8] Creando directorios de trabajo...
echo.

for %%d in (db upload tool-results LEARN_DIR) do (
    if not exist "%PROJECT_DIR%%%d" (
        mkdir "%PROJECT_DIR%%%d"
        echo  [OK] Creado: %%d/
    ) else (
        echo  [OK] Existe: %%d/
    )
)

echo.

:: ============================================================
:: 5. INSTALAR DEPENDENCIAS PYTHON
:: ============================================================
echo  [5/8] Instalando dependencias Python...
echo.

cd /d "%PROJECT_DIR%agente_v14"

if exist "requirements.txt" (
    python -m pip install -r requirements.txt --quiet
    echo  [OK] Dependencias Python instaladas
) else (
    echo  [!!] requirements.txt no encontrado, instalando lo basico...
    python -m pip install fastapi uvicorn ollama chromadb streamlit --quiet
    echo  [OK] Dependencias basicas instaladas
)

echo.

:: ============================================================
:: 6. INSTALAR DEPENDENCIAS NODE.JS
:: ============================================================
echo  [6/8] Instalando dependencias Node.js...
echo.

cd /d "%PROJECT_DIR%"

if exist "package.json" (
    npm install --legacy-peer-deps
    echo  [OK] Dependencias Node.js instaladas
) else (
    echo  [!!] package.json no encontrado
)

echo.

:: ============================================================
:: 7. VERIFICAR OLLAMA
:: ============================================================
echo  [7/8] Verificando Ollama...
echo.

python -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] Ollama corriendo en localhost:11434
) else (
    echo  [!!] Ollama no esta corriendo
    echo       Inicialo con: ollama serve
    echo       Descarga un modelo: ollama pull qwen3:4b
)

echo.

:: ============================================================
:: 8. VERIFICACION FINAL
:: ============================================================
echo  [8/8] Verificando imports del agente...
echo.

cd /d "%PROJECT_DIR%agente_v14"

for %%m in (config llm utils.security utils.helpers memory.triple_memory tools agent) do (
    python -c "import %%m" >nul 2>&1
    if !ERRORLEVEL!==0 (
        echo  [OK] %%m
    ) else (
        echo  [XX] %%m - Error importando
    )
)

python -c "from fastapi import FastAPI" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] fastapi ^(bridge_api^)
) else (
    echo  [XX] fastapi - Error importando
)

echo.

:: ============================================================
:: RESUMEN FINAL
:: ============================================================
echo  ========================================================
echo   INSTALACION COMPLETADA
echo  ========================================================
echo.
echo  Para iniciar el agente necesitas 2 terminales:
echo.
echo  TERMINAL 1 - Bridge API ^(backend Python^):
echo    cd %PROJECT_DIR%agente_v14
echo    python bridge_api.py
echo.
echo  TERMINAL 2 - Interfaz web ^(Next.js^):
echo    cd %PROJECT_DIR%
echo    npm run dev
echo.
echo  Luego abre: http://localhost:3000
echo.
echo  Alternativa rapida ^(solo agente, sin web^):
echo    cd %PROJECT_DIR%agente_v14
echo    start.bat
echo.
echo  ========================================================

pause
