@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ============================================================
:: AGENTE LOCAL AUTONOMO v14 - Script de Inicio y Verificacion
:: ============================================================
:: Uso: start.bat          (inicio completo con verificacion)
::       start.bat --skip   (saltar verificaciones, solo iniciar)
::       start.bat --check  (solo verificar, no iniciar)
::       start.bat --install (instalar dependencias faltantes)
:: ============================================================

title Agente Autonomo v14

:: Colores para mensajes
:: [OK] verde, [!!] amarillo, [XX] rojo, [..] cyan info
set "OK=[92m[OK][0m"
set "WARN=[93m[!!][0m"
set "FAIL=[91m[XX][0m"
set "INFO=[96m[..][0m"

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║     AGENTE LOCAL AUTONOMO v14 - Inicio          ║
echo  ║     Arquitectura Modular / ReAct + TripleMemory ║
echo  ╚══════════════════════════════════════════════════╝
echo.

:: Parsear argumentos
set "SKIP_CHECK=0"
set "CHECK_ONLY=0"
set "FORCE_INSTALL=0"
:parse_args
if "%~1"=="--skip" set "SKIP_CHECK=1"
if "%~1"=="--check" set "CHECK_ONLY=1"
if "%~1"=="--install" set "FORCE_INSTALL=1"
shift
if not "%~1"=="" goto parse_args

:: ============================================================
:: 1. VERIFICAR ESTRUCTURA DE ARCHIVOS
:: ============================================================
if %SKIP_CHECK%==1 goto :skip_checks

echo [96m━━━ VERIFICACION DE ESTRUCTURA ━━━[0m
echo.

set "MISSING=0"
set "AGENTE_DIR=%~dp0"

:: Archivos obligatorios del proyecto
set "FILES=app.py,config.py,llm.py,__init__.py"
set "FILES=%FILES%;agent\__init__.py,agent\react.py,agent\schemas.py"
set "FILES=%FILES%;tools\__init__.py,tools\schemas.py,tools\sistema.py,tools\archivos.py,tools\apps.py,tools\proyecto.py,tools\codigo.py,tools\web.py"
set "FILES=%FILES%;memory\__init__.py,memory\triple_memory.py,memory\learning.py,memory\vectorstore.py"
set "FILES=%FILES%;utils\__init__.py,utils\helpers.py,utils\security.py"

for %%F in (%FILES%) do (
    if exist "%AGENTE_DIR%%%F" (
        echo   %OK% %%F
    ) else (
        echo   %FAIL% %%F - NO ENCONTRADO
        set "MISSING=1"
    )
)

echo.
if %MISSING%==1 (
    echo   %FAIL% Faltan archivos del proyecto. No se puede continuar.
    echo   Asegurate de que todos los archivos del agente_v14 esten en:
    echo   %AGENTE_DIR%
    goto :error_exit
)

:: ============================================================
:: 2. VERIFICAR PYTHON
:: ============================================================
echo [96m━━━ VERIFICACION DE PYTHON ━━━[0m
echo.

set "PYTHON_CMD="

:: Buscar python o python3
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    echo   %OK% Python encontrado: !PY_VER!
    set "PYTHON_CMD=python"
) else (
    where python3 >nul 2>&1
    if %ERRORLEVEL%==0 (
        for /f "tokens=*" %%v in ('python3 --version 2^>^&1') do set "PY_VER=%%v"
        echo   %OK% Python3 encontrado: !PY_VER!
        set "PYTHON_CMD=python3"
    ) else (
        echo   %FAIL% Python no encontrado en el PATH
        set "MISSING=1"
    )
)

if not defined PYTHON_CMD (
    echo.
    echo   %FAIL% Python 3.8+ es requerido. Instalalo desde:
    echo          https://www.python.org/downloads/
    echo          Asegurate de marcar "Add Python to PATH" al instalar.
    goto :error_exit
)

:: Verificar version minima (3.8+)
%PYTHON_CMD% -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   %FAIL% Python 3.8+ requerido. Version actual demasiado antigua.
    goto :error_exit
)

:: ============================================================
:: 3. VERIFICAR PAQUETES PYTHON
:: ============================================================
echo.
echo [96m━━━ VERIFICACION DE DEPENDENCIAS PYTHON ━━━[0m
echo.

set "PKG_MISSING=0"

:: Verificar streamlit
%PYTHON_CMD% -c "import streamlit; print(streamlit.__version__)" >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "tokens=*" %%v in ('%PYTHON_CMD% -c "import streamlit; print(streamlit.__version__)" 2^>nul') do echo   %OK% streamlit %%v
) else (
    echo   %WARN% streamlit - NO INSTALADO
    set "PKG_MISSING=1"
)

:: Verificar ollama
%PYTHON_CMD% -c "import ollama" >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "tokens=*" %%v in ('%PYTHON_CMD% -c "import ollama; print(ollama.__version__)" 2^>nul') do (
        echo   %OK% ollama %%v
    )
    if ERRORLEVEL 1 echo   %OK% ollama - instalado
) else (
    echo   %WARN% ollama - NO INSTALADO (opcional, se usa HTTP como fallback)
)

:: ============================================================
:: 4. VERIFICAR OLLAMA
:: ============================================================
echo.
echo [96m━━━ VERIFICACION DE OLLAMA ━━━[0m
echo.

:: Verificar si Ollama esta corriendo
%PYTHON_CMD% -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo   %OK% Ollama corriendo en localhost:11434

    :: Listar modelos disponibles
    echo.
    echo   %INFO% Modelos disponibles:
    for /f "tokens=*" %%m in ('%PYTHON_CMD% -c "import urllib.request,json; resp=urllib.request.urlopen('http://localhost:11434/api/tags',timeout=3); data=json.loads(resp.read()); [print(f'     - {m[\"name\"]}') for m in data.get('models',[])]" 2^>nul') do echo   %%m
) else (
    echo   %WARN% Ollama no responde en localhost:11434

    :: Verificar si Ollama esta instalado pero no corriendo
    where ollama >nul 2>&1
    if %ERRORLEVEL%==0 (
        echo   %INFO% Ollama esta instalado pero no esta corriendo.
        echo        Intentando iniciar Ollama...
        start "" ollama serve
        timeout /t 5 /nobreak >nul

        :: Re-verificar
        %PYTHON_CMD% -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=5)" >nul 2>&1
        if %ERRORLEVEL%==0 (
            echo   %OK% Ollama iniciado correctamente!
        ) else (
            echo   %WARN% Ollama no pudo iniciarse automaticamente.
            echo        Inicielo manualmente: ollama serve
        )
    ) else (
        echo   %FAIL% Ollama no encontrado. Instalalo desde: https://ollama.com
        echo        El agente usara fallback HTTP pero necesita Ollama corriendo.
    )
)

:: ============================================================
:: 5. VERIFICAR DIRECTORIOS DE TRABAJO
:: ============================================================
echo.
echo [96m━━━ VERIFICACION DE DIRECTORIOS ━━━[0m
echo.

:: Crear directorios necesarios
set "REPOS_DIR=%USERPROFILE%\Documents"
set "LEARN_DIR=%USERPROFILE%\.ia-local\learning"

if not exist "%REPOS_DIR%" (
    mkdir "%REPOS_DIR%"
    echo   %OK% Creado: %REPOS_DIR%
) else (
    echo   %OK% Existe: %REPOS_DIR%
)

if not exist "%LEARN_DIR%" (
    mkdir "%LEARN_DIR%"
    echo   %OK% Creado: %LEARN_DIR%
) else (
    echo   %OK% Existe: %LEARN_DIR%
)

if not exist "%LEARN_DIR%\vectors" (
    mkdir "%LEARN_DIR%\vectors"
    echo   %OK% Creado: %LEARN_DIR%\vectors
) else (
    echo   %OK% Existe: %LEARN_DIR%\vectors
)

:: ============================================================
:: 6. VERIFICACION DE IMPORTACIONES
:: ============================================================
echo.
echo [96m━━━ VERIFICACION DE IMPORTACIONES ━━━[0m
echo.

:: Test rapido de que todos los modulos se importan correctamente
cd /d "%AGENTE_DIR%"

%PYTHON_CMD% -c "from config import REPOS_DIR, IS_WINDOWS, logger; print(f'  config: OK (repos={REPOS_DIR}, windows={IS_WINDOWS})')" 2>nul
if %ERRORLEVEL% neq 0 (
    echo   %FAIL% Error importando config.py
    set "MISSING=1"
)

%PYTHON_CMD% -c "from utils.security import is_dangerous_command, validate_path; print('  utils.security: OK')" 2>nul
if %ERRORLEVEL% neq 0 (
    echo   %FAIL% Error importando utils.security
    set "MISSING=1"
)

%PYTHON_CMD% -c "from utils.helpers import strip_prefixes, open_in_browser; print('  utils.helpers: OK')" 2>nul
if %ERRORLEVEL% neq 0 (
    echo   %FAIL% Error importando utils.helpers
    set "MISSING=1"
)

%PYTHON_CMD% -c "from memory.vectorstore import VectorStore; print('  memory.vectorstore: OK')" 2>nul
if %ERRORLEVEL% neq 0 (
    echo   %FAIL% Error importando memory.vectorstore
    set "MISSING=1"
)

%PYTHON_CMD% -c "from memory.learning import LearningSystem; print('  memory.learning: OK')" 2>nul
if %ERRORLEVEL% neq 0 (
    echo   %FAIL% Error importando memory.learning
    set "MISSING=1"
)

%PYTHON_CMD% -c "from memory.triple_memory import TripleMemory; print('  memory.triple_memory: OK')" 2>nul
if %ERRORLEVEL% neq 0 (
    echo   %FAIL% Error importando memory.triple_memory
    set "MISSING=1"
)

%PYTHON_CMD% -c "from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS; print(f'  tools: OK ({len(TOOL_FUNCTIONS)} herramientas, {len(TOOL_SCHEMAS)} schemas)')" 2>nul
if %ERRORLEVEL% neq 0 (
    echo   %FAIL% Error importando tools
    set "MISSING=1"
)

%PYTHON_CMD% -c "from llm import ollama; print('  llm: OK')" 2>nul
if %ERRORLEVEL% neq 0 (
    echo   %FAIL% Error importando llm
    set "MISSING=1"
)

%PYTHON_CMD% -c "from agent import ReactAgent; print('  agent: OK')" 2>nul
if %ERRORLEVEL% neq 0 (
    echo   %FAIL% Error importando agent
    set "MISSING=1"
)

:skip_checks

if %CHECK_ONLY%==1 (
    echo.
    echo [96m━━━ VERIFICACION COMPLETADA ━━━[0m
    if %MISSING%==0 (
        echo   %OK% Todo correcto! El agente esta listo para ejecutarse.
    ) else (
        echo   %FAIL% Se encontraron problemas. Revisa los mensajes arriba.
    )
    goto :end
)

:: ============================================================
:: 7. INSTALAR DEPENDENCIAS FALTANTES
:: ============================================================
if %PKG_MISSING%==1 (
    echo.
    echo [96m━━━ INSTALANDO DEPENDENCIAS FALTANTES ━━━[0m
    echo.

    echo   %INFO% Instalando streamlit...
    %PYTHON_CMD% -m pip install streamlit --quiet
    if %ERRORLEVEL%==0 (
        echo   %OK% streamlit instalado
    ) else (
        echo   %FAIL% Error instalando streamlit
    )

    echo   %INFO% Instalando ollama...
    %PYTHON_CMD% -m pip install ollama --quiet
    if %ERRORLEVEL%==0 (
        echo   %OK% ollama instalado
    ) else (
        echo   %WARN% Error instalando ollama (se usara HTTP como fallback)
    )

    echo.
    echo   %OK% Dependencias instaladas.
)

if %FORCE_INSTALL%==1 (
    echo.
    echo [96m━━━ INSTALACION FORZADA DE DEPENDENCIAS ━━━[0m
    echo.
    echo   %INFO% Instalando/actualizando todas las dependencias...
    %PYTHON_CMD% -m pip install streamlit ollama --upgrade --quiet
    echo   %OK% Dependencias instaladas/actualizadas.
)

:: ============================================================
:: 8. RESUMEN PRE-INICIO
:: ============================================================
echo.
echo [96m━━━ RESUMEN ━━━[0m
echo.
echo   Proyecto:  %AGENTE_DIR%
echo   Python:    %PYTHON_CMD%
echo   Interfaz:  Streamlit (web)
echo   LLM:       Ollama (local)
echo.
echo   Comandos utiles:
echo     start.bat           - Inicio completo con verificacion
echo     start.bat --skip    - Inicio rapido (sin verificar)
echo     start.bat --check   - Solo verificar, no iniciar
echo     start.bat --install - Instalar/actualizar dependencias
echo.

:: ============================================================
:: 9. INICIAR AGENTE
:: ============================================================
echo [96m━━━ INICIANDO AGENTE ━━━[0m
echo.
echo   %INFO% Ejecutando: streamlit run app.py
echo   %INFO% Se abrira el navegador automaticamente.
echo   %INFO% Presiona Ctrl+C para detener el agente.
echo.

%PYTHON_CMD% -m streamlit run app.py --server.port 8501 --server.headless true

goto :end

:: ============================================================
:: ERROR EXIT
:: ============================================================
:error_exit
echo.
echo   %FAIL% No se pudo iniciar el agente. Revisa los errores arriba.
echo.
echo   Sugerencias:
echo     1. Verifica que Python 3.8+ este instalado y en el PATH
echo     2. Ejecuta: start.bat --install
echo     3. Asegurate que Ollama este corriendo: ollama serve
echo.
pause
exit /b 1

:end
echo.
echo   Agente detenido.
pause
