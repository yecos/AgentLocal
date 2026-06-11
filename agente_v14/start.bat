@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ============================================================
:: AGENTE LOCAL AUTONOMO v14 - Script de Inicio
:: ============================================================
:: Uso: start.bat          (inicio completo con verificacion)
::       start.bat --skip   (saltar verificaciones, solo iniciar)
::       start.bat --check  (solo verificar, no iniciar)
::       start.bat --install (instalar dependencias faltantes)
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

:: Directorio del proyecto (donde esta start.bat)
set "AGENTE_DIR=%~dp0"
if "%AGENTE_DIR:~-1%"=="\" set "AGENTE_DIR=%AGENTE_DIR:~0,-1%"
cd /d "%AGENTE_DIR%"

echo  Directorio: %AGENTE_DIR%
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
    echo  [XX] Python no encontrado. Instala Python 3.8+ y marcalo en el PATH.
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
    echo  [XX] Faltan archivos. No se puede continuar.
    goto :error_exit
)

:: ============================================================
:: 3. VERIFICAR DEPENDENCIAS PYTHON
:: ============================================================
echo.
echo  [3/7] Verificando dependencias Python...
echo.

set "PKG_MISSING=0"

%PYTHON_CMD% _helpers.py check_streamlit >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] streamlit instalado
) else (
    echo  [!!] streamlit NO instalado
    set "PKG_MISSING=1"
)

%PYTHON_CMD% _helpers.py check_ollama_lib >nul 2>&1
echo  [OK] ollama python (opcional)

:: ============================================================
:: 4. VERIFICAR IMPORTACIONES
:: ============================================================
echo.
echo  [4/7] Verificando modulos...
echo.

%PYTHON_CMD% _helpers.py check_imports
if !ERRORLEVEL! neq 0 (
    echo  [XX] Error en importaciones. Revisa los mensajes arriba.
    set "MISSING=1"
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
    %PYTHON_CMD% _helpers.py install_deps
) else (
    echo.
    echo  [6/7] Dependencias OK
)

if %FORCE_INSTALL%==1 (
    echo.
    echo  Instalando/actualizando dependencias...
    %PYTHON_CMD% -m pip install streamlit ollama --upgrade --quiet
    echo  [OK] Dependencias actualizadas
)

echo.

:: ============================================================
:: 7. VERIFICAR E INICIAR OLLAMA
:: ============================================================
:start_ollama
echo  [7/7] Verificando Ollama...
echo.

%PYTHON_CMD% _helpers.py check_ollama
set "OLLAMA_RESULT=!ERRORLEVEL!"

if %OLLAMA_RESULT%==0 (
    :: Ollama esta corriendo, listar modelos
    echo.
    echo  Modelos disponibles:
    %PYTHON_CMD% _helpers.py list_models

    :: Verificar si hay modelos
    %PYTHON_CMD% _helpers.py check_model_available >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo.
        echo  [!!] No hay modelos descargados. Descargando qwen3:4b...
        echo      Esto puede tardar unos minutos...
        ollama pull qwen3:4b
    )
) else if %OLLAMA_RESULT%==1 (
    echo  [!!] Ollama no pudo iniciarse automaticamente.
    echo      Intenta abrir Ollama manualmente desde el Menu Inicio y vuelve a ejecutar start.bat
    echo.
    echo  Presiona una tecla para continuar de todos modos, o Ctrl+C para salir...
    pause >nul
) else (
    echo  [!!] Ollama no esta instalado. El agente lo necesita para funcionar.
    echo      Instalalo desde https://ollama.com y vuelve a ejecutar start.bat
    echo.
    echo  Presiona una tecla para continuar de todos modos, o Ctrl+C para salir...
    pause >nul
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
echo.
pause
exit /b 1

:end
echo.
echo  Agente detenido.
pause
