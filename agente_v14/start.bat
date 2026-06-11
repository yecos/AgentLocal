@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ============================================================
:: AGENTE LOCAL AUTONOMO v14 - Script de Inicio
:: ============================================================
:: Se auto-ubica: encuentra el directorio del proyecto
:: buscando app.py hacia arriba o hacia abajo.
:: Uso: start.bat          (inicio completo)
::       start.bat --skip   (saltar verificaciones)
::       start.bat --check  (solo verificar)
::       start.bat --install (instalar dependencias)
:: ============================================================

title Agente Autonomo v14

echo.
echo  ========================================================
echo   AGENTE LOCAL AUTONOMO v14
echo   Arquitectura Modular / ReAct + TripleMemory
echo  ========================================================
echo.

:: Parsear argumentos
set "SKIP_CHECK=0"
set "CHECK_ONLY=0"
set "FORCE_INSTALL=0"
:parse_args
if "%~1"=="--skip" set "SKIP_CHECK=1"
if "%~1"=="--check" set "CHECK_ONLY=1"
if "%~1"=="--install" set "FORCE_INSTALL=1"
if not "%~1"=="" (
    shift
    goto parse_args
)

:: ============================================================
:: AUTO-DETECTAR DIRECTORIO DEL PROYECTO
:: ============================================================
:: Busca app.py en: directorio del bat, subdirectorios, padre
:: Esto resuelve el problema de doble carpeta (agente_v14/agente_v14)

set "AGENTE_DIR="

:: 1. Mismo directorio del start.bat
if exist "%~dp0app.py" (
    set "AGENTE_DIR=%~dp0"
    goto :found_dir
)

:: 2. Subdirectorio agente_v14 (caso: repo raiz con subcarpeta)
if exist "%~dp0agente_v14\app.py" (
    set "AGENTE_DIR=%~dp0agente_v14"
    goto :found_dir
)

:: 3. Directorio padre (caso: ejecutando desde subcarpeta agente_v14)
if exist "%~dp0..\app.py" (
    set "AGENTE_DIR=%~dp0.."
    goto :found_dir
)

:: 4. Directorio actual de trabajo
if exist "%cd%\app.py" (
    set "AGENTE_DIR=%cd%"
    goto :found_dir
)

:: 5. Subdirectorio del directorio actual
for /d %%D in ("%cd%\*") do (
    if exist "%%D\app.py" (
        set "AGENTE_DIR=%%D"
        goto :found_dir
    )
)

:: 6. Buscar en directorios comunes
for %%P in (
    "%USERPROFILE%\ia-local\agente_v14"
    "%USERPROFILE%\ia-local\agente_v14\agente_v14"
    "%USERPROFILE%\Documents\agente_v14"
    "C:\ia-local\agente_v14"
    "C:\ia-local\agente_v14\agente_v14"
    "D:\ia-local\agente_v14"
    "D:\ia-local\agente_v14\agente_v14"
) do (
    if exist "%%~P\app.py" (
        set "AGENTE_DIR=%%~P"
        goto :found_dir
    )
)

:: No encontrado
echo  [XX] No se encontro app.py en ningun lugar.
echo.
echo  Estructura esperada:
echo    agente_v14/
echo      start.bat    ^(este archivo^)
echo      app.py
echo      config.py
echo      llm.py
echo      agent/
echo      tools/
echo      memory/
echo.
echo  Si tienes doble carpeta, mueve start.bat al nivel de app.py
echo  o ejecuta desde el directorio correcto.
echo.
pause
exit /b 1

:found_dir
:: Limpiar barra final
if "%AGENTE_DIR:~-1%"=="\" set "AGENTE_DIR=%AGENTE_DIR:~0,-1%"
cd /d "%AGENTE_DIR%"

echo  Directorio encontrado: %AGENTE_DIR%
echo.

if %SKIP_CHECK%==1 goto :start_ollama

:: ============================================================
:: 1. VERIFICAR PYTHON
:: ============================================================
echo  [1/7] Verificando Python...
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

if not defined PYTHON_CMD (
    echo  [XX] Python no encontrado. Instala Python 3.8+ y agregalo al PATH.
    goto :error_exit
)

for /f "tokens=*" %%v in ('%PYTHON_CMD% --version 2^>^&1') do echo  [OK] %%v

%PYTHON_CMD% -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo  [XX] Python 3.8+ requerido.
    goto :error_exit
)

:: ============================================================
:: 2. VERIFICAR ESTRUCTURA DE ARCHIVOS
:: ============================================================
echo.
echo  [2/7] Verificando estructura...
echo.

set "MISSING=0"
for %%F in (app.py config.py llm.py __init__.py) do (
    if exist "%AGENTE_DIR%\%%F" (
        echo  [OK] %%F
    ) else (
        echo  [XX] %%F NO ENCONTRADO
        set "MISSING=1"
    )
)
for %%F in (agent\__init__.py agent\react.py agent\schemas.py) do (
    if exist "%AGENTE_DIR%\%%F" (
        echo  [OK] %%F
    ) else (
        echo  [XX] %%F NO ENCONTRADO
        set "MISSING=1"
    )
)
for %%F in (tools\__init__.py tools\schemas.py tools\sistema.py tools\archivos.py tools\apps.py tools\proyecto.py tools\codigo.py tools\web.py) do (
    if exist "%AGENTE_DIR%\%%F" (
        echo  [OK] %%F
    ) else (
        echo  [XX] %%F NO ENCONTRADO
        set "MISSING=1"
    )
)
for %%F in (memory\__init__.py memory\triple_memory.py memory\learning.py memory\vectorstore.py) do (
    if exist "%AGENTE_DIR%\%%F" (
        echo  [OK] %%F
    ) else (
        echo  [XX] %%F NO ENCONTRADO
        set "MISSING=1"
    )
)
for %%F in (utils\__init__.py utils\helpers.py utils\security.py) do (
    if exist "%AGENTE_DIR%\%%F" (
        echo  [OK] %%F
    ) else (
        echo  [XX] %%F NO ENCONTRADO
        set "MISSING=1"
    )
)

if %MISSING%==1 (
    echo.
    echo  [XX] Faltan archivos en: %AGENTE_DIR%
    echo      Verifica que estes en el directorio correcto del proyecto.
    goto :error_exit
)

:: ============================================================
:: 3. VERIFICAR DEPENDENCIAS PYTHON
:: ============================================================
echo.
echo  [3/7] Verificando dependencias Python...
echo.

set "PKG_MISSING=0"

%PYTHON_CMD% -c "import streamlit" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] streamlit instalado
) else (
    echo  [!!] streamlit NO instalado
    set "PKG_MISSING=1"
)

%PYTHON_CMD% -c "import chromadb" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] chromadb instalado
) else (
    echo  [!!] chromadb NO instalado (opcional, se usa VectorStore casero como fallback)
)

%PYTHON_CMD% -c "import ollama" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] ollama python instalado
) else (
    echo  [!!] ollama python NO instalado (opcional, se usa HTTP directo)
)

:: ============================================================
:: 4. VERIFICAR IMPORTACIONES
:: ============================================================
echo.
echo  [4/7] Verificando modulos...
echo.

if exist "%AGENTE_DIR%\_helpers.py" (
    %PYTHON_CMD% "%AGENTE_DIR%\_helpers.py" check_imports
    if !ERRORLEVEL! neq 0 (
        echo  [XX] Error en importaciones. Revisa los mensajes arriba.
        set "MISSING=1"
    )
) else (
    echo  [!!] _helpers.py no encontrado, saltando verificacion de imports
)

:: ============================================================
:: 5. VERIFICAR DIRECTORIOS
:: ============================================================
echo.
echo  [5/7] Verificando directorios...
echo.

if not exist "%USERPROFILE%\Documents" mkdir "%USERPROFILE%\Documents"
echo  [OK] %USERPROFILE%\Documents

if not exist "%USERPROFILE%\.ia-local\learning" mkdir "%USERPROFILE%\.ia-local\learning"
echo  [OK] %USERPROFILE%\.ia-local\learning

if not exist "%USERPROFILE%\.ia-local\learning\vectors" mkdir "%USERPROFILE%\.ia-local\learning\vectors"
echo  [OK] %USERPROFILE%\.ia-local\learning\vectors

:: ============================================================
:: 6. INSTALAR DEPENDENCIAS SI FALTAN
:: ============================================================
if %PKG_MISSING%==1 (
    echo.
    echo  [6/7] Instalando dependencias faltantes...
    echo.
    %PYTHON_CMD% -m pip install streamlit ollama chromadb --quiet
    if !ERRORLEVEL! neq 0 (
        echo  [XX] Error instalando dependencias. Prueba manualmente:
        echo      pip install streamlit ollama chromadb
    )
) else (
    echo.
    echo  [6/7] Dependencias OK
)

if %FORCE_INSTALL%==1 (
    echo.
    echo  Instalando/actualizando dependencias...
    %PYTHON_CMD% -m pip install streamlit ollama chromadb --upgrade --quiet
    echo  [OK] Dependencias actualizadas
)

echo.

:: ============================================================
:: 7. VERIFICAR E INICIAR OLLAMA
:: ============================================================
:start_ollama
echo  [7/7] Verificando Ollama...
echo.

:: Verificar si Ollama esta corriendo
%PYTHON_CMD% -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] Ollama corriendo en localhost:11434
    echo.
    echo  Modelos disponibles:
    %PYTHON_CMD% -c "import urllib.request,json; resp=urllib.request.urlopen('http://localhost:11434/api/tags',timeout=5); data=json.loads(resp.read()); [print(f'  - {m[\"name\"]} ({m[\"size\"]/(1024**3):.1f} GB)') for m in data.get('models',[])]" 2>nul
    goto :ollama_ok
)

:: Ollama no esta corriendo, intentar iniciarlo
echo  [!!] Ollama no responde. Intentando iniciar...

:: Metodo 1: ollama app (Windows system tray)
where ollama >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  Iniciando Ollama...
    start "" ollama app >nul 2>&1

    :: Esperar hasta 15 segundos
    echo  Esperando a que Ollama inicie...
    for /L %%i in (1,1,15) do (
        %PYTHON_CMD% -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=2)" >nul 2>&1
        if !ERRORLEVEL!==0 (
            echo  [OK] Ollama iniciado correctamente!
            goto :ollama_ok
        )
        timeout /t 1 /nobreak >nul
    )
)

:: Metodo 2: Buscar en instalaciones comunes
for %%P in (
    "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
    "%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    "%ProgramFiles%\Ollama\ollama app.exe"
) do (
    if exist %%P (
        echo  Iniciando Ollama desde: %%P
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
echo      Abre Ollama manualmente desde el Menu Inicio y vuelve a ejecutar start.bat
echo.
echo  Presiona una tecla para continuar de todos modos, o Ctrl+C para salir...
pause >nul

:ollama_ok
:: Verificar si hay modelos
%PYTHON_CMD% -c "import urllib.request,json; resp=urllib.request.urlopen('http://localhost:11434/api/tags',timeout=5); data=json.loads(resp.read()); exit(0 if data.get('models') else 1)" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo.
    echo  [!!] No hay modelos descargados. Descargando qwen3:4b...
    echo      Esto puede tardar unos minutos...
    ollama pull qwen3:4b
)

if %CHECK_ONLY%==1 (
    echo.
    echo  Verificacion completada.
    goto :end
)

:: ============================================================
:: INICIAR AGENTE
:: ============================================================
echo.
echo  ========================================================
echo   INICIANDO AGENTE
echo  ========================================================
echo.
echo  Directorio: %AGENTE_DIR%
echo  Ejecutando: streamlit run app.py --server.port 8501
echo  Se abrira el navegador en http://localhost:8501
echo  Presiona Ctrl+C para detener.
echo.

cd /d "%AGENTE_DIR%"
%PYTHON_CMD% -m streamlit run app.py --server.port 8501

goto :end

:: ============================================================
:: ERROR
:: ============================================================
:error_exit
echo.
echo  [XX] No se pudo iniciar el agente.
echo.
echo  Sugerencias:
echo    1. Verifica que Python 3.8+ este en el PATH
echo    2. Ejecuta: start.bat --install
echo    3. Abre Ollama desde el Menu Inicio antes de ejecutar start.bat
echo    4. Asegurate de que start.bat este junto a app.py
echo.
pause
exit /b 1

:end
echo.
echo  Agente detenido.
pause
