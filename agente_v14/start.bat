@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ============================================================
:: AGENTE LOCAL AUTONOMO v14 - Script de Inicio Completo
:: ============================================================
:: Script con comprobaciones exhaustivas para arrancar el agente.
:: Verifica: Python, estructura, dependencias, imports, Ollama,
:: GPU, puerto, procesos, directorios, y mas.
::
:: Uso: start.bat            (inicio completo con verificaciones)
::       start.bat --skip     (saltar verificaciones, inicio rapido)
::       start.bat --check    (solo verificar, no iniciar)
::       start.bat --install  (instalar/actualizar dependencias)
::       start.bat --diag     (diagnostico completo con GPU)
::       start.bat --update   (actualizar desde GitHub)
:: ============================================================

title Agente Autonomo v14 - Inicio

echo.
echo  ========================================================
echo   AGENTE LOCAL AUTONOMO v14
echo   Arquitectura Modular / ReAct + TripleMemory
echo  ========================================================
echo.

:: ============================================================
:: PARSEAR ARGUMENTOS
:: ============================================================
set "SKIP_CHECK=0"
set "CHECK_ONLY=0"
set "FORCE_INSTALL=0"
set "DIAG_MODE=0"
set "UPDATE_MODE=0"

:parse_args
if "%~1"=="--skip" set "SKIP_CHECK=1"
if "%~1"=="--check" set "CHECK_ONLY=1"
if "%~1"=="--install" set "FORCE_INSTALL=1"
if "%~1"=="--diag" set "DIAG_MODE=1"
if "%~1"=="--update" set "UPDATE_MODE=1"
if "%~1"=="--help" goto :show_help
if not "%~1"=="" (
    shift
    goto parse_args
)

:: ============================================================
:: MODO ACTUALIZAR
:: ============================================================
if %UPDATE_MODE%==1 (
    echo  [ACTUALIZAR] Actualizando desde GitHub...
    echo.
    where git >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo  [XX] Git no encontrado. Instala Git desde https://git-scm.com
        goto :error_exit
    )
    git pull origin main
    if !ERRORLEVEL! neq 0 (
        echo  [!!] No se pudo hacer git pull. Puede que haya cambios locales.
        echo      Intenta: git stash ^&^& git pull ^&^& git stash pop
    ) else (
        echo  [OK] Repositorio actualizado.
    )
    echo.
    echo  Instalando dependencias actualizadas...
    call :find_python
    if defined PYTHON_CMD (
        %PYTHON_CMD% -m pip install -r requirements.txt --quiet 2>nul
        if !ERRORLEVEL!==0 (
            echo  [OK] Dependencias instaladas.
        ) else (
            echo  [!!] No se encontró requirements.txt o hubo error. Instalando manual...
            %PYTHON_CMD% -m pip install streamlit ollama chromadb --quiet
        )
    )
    echo.
    echo  Actualizacion completada. Ejecuta start.bat para iniciar.
    goto :end
)

:: ============================================================
:: MODO DIAGNOSTICO
:: ============================================================
if %DIAG_MODE%==1 (
    echo  [DIAG] Modo diagnostico completo...
    echo.
    call :find_python
    if defined PYTHON_CMD (
        if exist "%AGENTE_DIR%\check_gpu.py" (
            %PYTHON_CMD% "%AGENTE_DIR%\check_gpu.py"
        ) else (
            echo  [!!] check_gpu.py no encontrado.
        )
        echo.
        echo  --- Diagnostico de red ---
        %PYTHON_CMD% -c "import urllib.request,json; resp=urllib.request.urlopen('http://localhost:11434/api/tags',timeout=3); data=json.loads(resp.read()); print('Ollama OK - Modelos:', len(data.get('models',[])))" 2>nul || echo  [XX] Ollama no responde en localhost:11434
        echo.
        echo  --- Versiones ---
        %PYTHON_CMD% --version
        %PYTHON_CMD% -c "import streamlit; print('Streamlit:', streamlit.__version__)" 2>nul || echo  [XX] Streamlit no instalado
        %PYTHON_CMD% -c "import ollama; print('Ollama lib OK')" 2>nul || echo  [!!] Ollama lib Python no instalada (opcional)
        %PYTHON_CMD% -c "import chromadb; print('ChromaDB:', chromadb.__version__)" 2>nul || echo  [!!] ChromaDB no instalado (opcional)
    )
    echo.
    echo  Diagnostico completado.
    goto :end
)

:: ============================================================
:: AUTO-DETECTAR DIRECTORIO DEL PROYECTO
:: ============================================================
:: Busca app.py en: directorio del bat, subdirectorios, padre,
:: directorio actual, y rutas comunes.

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

:: 3. Directorio padre (caso: ejecutando desde subcarpeta)
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

:: 6. Buscar en directorios comunes del usuario
for %%P in (
    "%USERPROFILE%\Downloads\IA\agente_v14\agente_v14"
    "%USERPROFILE%\Downloads\IA\agente_v14"
    "%USERPROFILE%\ia-local\agente_v14"
    "%USERPROFILE%\ia-local\agente_v14\agente_v14"
    "%USERPROFILE%\Documents\agente_v14"
    "%USERPROFILE%\Documents\agente_v14\agente_v14"
    "%USERPROFILE%\Desktop\agente_v14"
    "%USERPROFILE%\Desktop\agente_v14\agente_v14"
    "C:\ia-local\agente_v14"
    "C:\ia-local\agente_v14\agente_v14"
    "D:\ia-local\agente_v14"
    "D:\ia-local\agente_v14\agente_v14"
    "D:\Downloads\IA\agente_v14\agente_v14"
    "D:\Downloads\IA\agente_v14"
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
:: 1/10 - VERIFICAR PYTHON
:: ============================================================
echo  [ 1/10] Verificando Python...
echo.

call :find_python

if not defined PYTHON_CMD (
    echo  [XX] Python no encontrado. Instala Python 3.8+ y agregalo al PATH.
    echo.
    echo  Descarga: https://www.python.org/downloads/
    echo  IMPORTANTE: Marca "Add Python to PATH" al instalar.
    goto :error_exit
)

for /f "tokens=*" %%v in ('%PYTHON_CMD% --version 2^>^&1') do echo  [OK] %%v

%PYTHON_CMD% -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo  [XX] Python 3.8+ requerido. Tu version es muy antigua.
    goto :error_exit
)

:: Verificar pip
%PYTHON_CMD% -m pip --version >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo  [XX] pip no encontrado. Reinstala Python con pip incluido.
    goto :error_exit
)
echo  [OK] pip disponible

:: ============================================================
:: 2/10 - VERIFICAR ESTRUCTURA DE ARCHIVOS
:: ============================================================
echo.
echo  [ 2/10] Verificando estructura de archivos...
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
    echo      Intenta: git pull para descargar archivos faltantes.
    goto :error_exit
)

:: ============================================================
:: 3/10 - VERIFICAR DEPENDENCIAS PYTHON
:: ============================================================
echo.
echo  [ 3/10] Verificando dependencias Python...
echo.

set "PKG_MISSING=0"
set "PKG_LIST="

%PYTHON_CMD% -c "import streamlit" >nul 2>&1
if !ERRORLEVEL!==0 (
    for /f "tokens=*" %%v in ('%PYTHON_CMD% -c "import streamlit; print(streamlit.__version__)" 2^>^&1') do echo  [OK] streamlit %%v
) else (
    echo  [!!] streamlit NO instalado
    set "PKG_MISSING=1"
    set "PKG_LIST=!PKG_LIST! streamlit"
)

%PYTHON_CMD% -c "import ollama" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] ollama python instalado
) else (
    echo  [!!] ollama python NO instalado (se usara HTTP directo como fallback)
)

%PYTHON_CMD% -c "import chromadb" >nul 2>&1
if !ERRORLEVEL!==0 (
    for /f "tokens=*" %%v in ('%PYTHON_CMD% -c "import chromadb; print(chromadb.__version__)" 2^>^&1') do echo  [OK] chromadb %%v
) else (
    echo  [!!] chromadb NO instalado (se usara VectorStore casero como fallback)
)

%PYTHON_CMD% -c "import numpy" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] numpy instalado (optimizacion de embeddings)
) else (
    echo  [!!] numpy NO instalado (opcional, mejora rendimiento de similitud)
)

:: ============================================================
:: 4/10 - VERIFICAR IMPORTACIONES DE MODULOS
:: ============================================================
echo.
echo  [ 4/10] Verificando importaciones de modulos...
echo.

if exist "%AGENTE_DIR%\_helpers.py" (
    %PYTHON_CMD% "%AGENTE_DIR%\_helpers.py" check_imports
    if !ERRORLEVEL! neq 0 (
        echo  [XX] Error en importaciones. Revisa los mensajes arriba.
        echo      Intenta: start.bat --install
        set "MISSING=1"
    )
) else (
    echo  [!!] _helpers.py no encontrado, verificacion de imports saltada
)

:: ============================================================
:: 5/10 - VERIFICAR DIRECTORIOS DE DATOS
:: ============================================================
echo.
echo  [ 5/10] Verificando directorios de datos...
echo.

if not exist "%USERPROFILE%\Documents" (
    mkdir "%USERPROFILE%\Documents"
    echo  [OK] Creado: %USERPROFILE%\Documents
) else (
    echo  [OK] %USERPROFILE%\Documents
)

if not exist "%USERPROFILE%\.ia-local" mkdir "%USERPROFILE%\.ia-local"
if not exist "%USERPROFILE%\.ia-local\learning" mkdir "%USERPROFILE%\.ia-local\learning"
echo  [OK] %USERPROFILE%\.ia-local\learning

if not exist "%USERPROFILE%\.ia-local\learning\vectors" mkdir "%USERPROFILE%\.ia-local\learning\vectors"
echo  [OK] %USERPROFILE%\.ia-local\learning\vectors

:: Verificar permisos de escritura
echo test_write > "%USERPROFILE%\.ia-local\learning\_write_test.tmp" 2>nul
if exist "%USERPROFILE%\.ia-local\learning\_write_test.tmp" (
    del "%USERPROFILE%\.ia-local\learning\_write_test.tmp" >nul 2>&1
    echo  [OK] Permisos de escritura verificados
) else (
    echo  [XX] No se puede escribir en %USERPROFILE%\.ia-local\learning
    echo      El agente necesita permisos de escritura para guardar datos.
)

:: ============================================================
:: 6/10 - INSTALAR DEPENDENCIAS SI FALTAN
:: ============================================================
if %PKG_MISSING%==1 (
    echo.
    echo  [ 6/10] Instalando dependencias faltantes...
    echo.
    if exist "%AGENTE_DIR%\requirements.txt" (
        echo  Instalando desde requirements.txt...
        %PYTHON_CMD% -m pip install -r "%AGENTE_DIR%\requirements.txt" --quiet
        if !ERRORLEVEL! neq 0 (
            echo  [!!] Error con requirements.txt, instalando manualmente...
            %PYTHON_CMD% -m pip install streamlit ollama chromadb --quiet
        )
    ) else (
        %PYTHON_CMD% -m pip install streamlit ollama chromadb --quiet
    )
    if !ERRORLEVEL! neq 0 (
        echo  [XX] Error instalando dependencias. Prueba manualmente:
        echo      pip install streamlit ollama chromadb
    ) else (
        echo  [OK] Dependencias instaladas correctamente
    )
) else (
    echo.
    echo  [ 6/10] Todas las dependencias OK
)

if %FORCE_INSTALL%==1 (
    echo.
    echo  Instalando/actualizando todas las dependencias...
    if exist "%AGENTE_DIR%\requirements.txt" (
        %PYTHON_CMD% -m pip install -r "%AGENTE_DIR%\requirements.txt" --upgrade --quiet
    ) else (
        %PYTHON_CMD% -m pip install streamlit ollama chromadb --upgrade --quiet
    )
    echo  [OK] Dependencias actualizadas
)

:: ============================================================
:: 7/10 - VERIFICAR OLLAMA
:: ============================================================
:start_ollama
echo.
echo  [ 7/10] Verificando Ollama...
echo.

:: Verificar si Ollama esta instalado
where ollama >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo  [!!] Comando "ollama" no encontrado en el PATH.
    echo      Buscando en ubicaciones alternativas...
    
    set "OLLAMA_FOUND=0"
    for %%P in (
        "%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
        "%ProgramFiles%\Ollama\ollama.exe"
        "%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe"
    ) do (
        if exist %%P (
            echo  [OK] Ollama encontrado en: %%P
            set "OLLAMA_FOUND=1"
        )
    )
    
    if !OLLAMA_FOUND!==0 (
        echo  [XX] Ollama no esta instalado.
        echo      Descargalo desde: https://ollama.com
        echo.
        echo  Presiona una tecla para abrir la pagina de descarga, o Ctrl+C para salir...
        pause >nul
        start https://ollama.com
        goto :error_exit
    )
)

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
echo.

:: Metodo 1: ollama app (Windows system tray app)
where ollama >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  Iniciando Ollama...
    start "" ollama app >nul 2>&1
    
    :: Esperar hasta 20 segundos
    echo  Esperando a que Ollama inicie (hasta 20s)...
    for /L %%i in (1,1,20) do (
        %PYTHON_CMD% -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=2)" >nul 2>&1
        if !ERRORLEVEL!==0 (
            echo  [OK] Ollama iniciado correctamente! ^(%%i seg^)
            goto :ollama_ok
        )
        <nul set /p "=."
        timeout /t 1 /nobreak >nul
    )
    echo.
)

:: Metodo 2: Buscar en instalaciones comunes
for %%P in (
    "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
    "%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    "%ProgramFiles%\Ollama\ollama app.exe"
    "%ProgramFiles%\Ollama\ollama.exe"
    "%USERPROFILE%\AppData\Local\Programs\Ollama\ollama app.exe"
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

:: Metodo 3: ollama serve (modo CLI)
echo  Intentando ollama serve...
start "" /B ollama serve >nul 2>&1
timeout /t 5 /nobreak >nul
%PYTHON_CMD% -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [OK] Ollama serve iniciado!
    goto :ollama_ok
)

echo.
echo  [!!] No se pudo iniciar Ollama automaticamente.
echo      Pasos para solucionar:
echo      1. Abre Ollama desde el Menu Inicio
echo      2. Espera a que aparezca en la bandeja del sistema
echo      3. Vuelve a ejecutar start.bat
echo.
echo  Presiona una tecla para continuar de todos modos, o Ctrl+C para salir...
pause >nul

:ollama_ok
:: Verificar si hay modelos descargados
%PYTHON_CMD% -c "import urllib.request,json; resp=urllib.request.urlopen('http://localhost:11434/api/tags',timeout=5); data=json.loads(resp.read()); exit(0 if data.get('models') else 1)" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo.
    echo  [!!] No hay modelos descargados en Ollama.
    echo      Descargando qwen3:4b ^(recomendado, ~2.5 GB^)...
    echo      Esto puede tardar varios minutos dependiendo de tu conexion.
    echo.
    ollama pull qwen3:4b
    if !ERRORLEVEL! neq 0 (
        echo  [XX] Error descargando modelo. Prueba manualmente:
        echo      ollama pull qwen3:4b
    )
)

:: ============================================================
:: 8/10 - VERIFICAR PUERTO 8501
:: ============================================================
echo.
echo  [ 8/10] Verificando puerto 8501...
echo.

netstat -ano 2>nul | findstr ":8501 " | findstr "LISTENING" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [!!] El puerto 8501 ya esta en uso por otro proceso.
    echo.
    echo  Procesos usando el puerto:
    for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8501 " ^| findstr "LISTENING"') do (
        for /f "tokens=1" %%n in ('tasklist /FI "PID eq %%p" /NH 2^>nul') do (
            echo    PID %%p = %%n
        )
    )
    echo.
    echo  Opciones:
    echo    1. Cierra la otra aplicacion que usa el puerto
    echo    2. El agente usara un puerto alternativo automaticamente
    echo.
    set "PORT_ARG=--server.port 8502"
    echo  Se usara el puerto 8502.
) else (
    echo  [OK] Puerto 8501 disponible
    set "PORT_ARG=--server.port 8501"
)

:: ============================================================
:: 9/10 - VERIFICAR GPU (aviso rapido)
:: ============================================================
echo.
echo  [ 9/10] Verificando GPU...
echo.

where nvidia-smi >nul 2>&1
if !ERRORLEVEL!==0 (
    for /f "tokens=*" %%g in ('nvidia-smi --query-gpu^=name --format^=csv^,noheader 2^>nul') do (
        echo  [OK] GPU detectada: %%g
    )
    :: Verificar VRAM disponible
    for /f "tokens=*" %%v in ('nvidia-smi --query-gpu^=memory.total,memory.free --format^=csv^,noheader 2^>nul') do (
        echo  [OK] VRAM: %%v
    )
) else (
    echo  [!!] No se detecto GPU NVIDIA o nvidia-smi no esta en el PATH.
    echo      El agente correra en CPU ^(mas lento^).
    echo      Para diagnostico completo ejecuta: start.bat --diag
)

:: ============================================================
:: 10/10 - VERIFICAR PROCESO STREAMLIT EXISTENTE
:: ============================================================
echo.
echo  [10/10] Verificando procesos existentes...
echo.

tasklist /FI "IMAGENAME eq streamlit.exe" 2>nul | findstr /I "streamlit" >nul 2>&1
if !ERRORLEVEL!==0 (
    echo  [!!] Ya hay un proceso Streamlit corriendo.
    echo      Si el agente no abre, cierra la instancia anterior primero.
) else (
    :: streamlit corre como python, buscar python con streamlit en el comando
    wmic process where "name='python.exe' or name='python3.exe'" get ProcessId,CommandLine 2>nul | findstr "streamlit" >nul 2>&1
    if !ERRORLEVEL!==0 (
        echo  [!!] Parece que ya hay un Streamlit corriendo.
        echo      Si no responde, cierra la ventana o mata el proceso.
    ) else (
        echo  [OK] No hay Streamlit corriendo
    )
)

:: ============================================================
:: RESUMEN DE VERIFICACION
:: ============================================================
echo.
echo  ========================================================
echo   VERIFICACION COMPLETADA
echo  ========================================================
echo.
echo  Directorio : %AGENTE_DIR%
echo  Python     : 
%PYTHON_CMD% --version 2>nul
echo  Ollama     : localhost:11434
echo  Puerto     : %PORT_ARG:--server.port =%
echo.

if %CHECK_ONLY%==1 (
    echo  Modo --check: Solo verificacion. No se iniciara el agente.
    goto :end
)

:: ============================================================
:: INICIAR AGENTE
:: ============================================================
echo  ========================================================
echo   INICIANDO AGENTE
echo  ========================================================
echo.
echo  Directorio: %AGENTE_DIR%
echo  Ejecutando: streamlit run app.py %PORT_ARG%
echo.
echo  Se abrira el navegador en http://localhost:%PORT_ARG:--server.port =%
echo.
echo  Presiona Ctrl+C para detener el agente.
echo.

cd /d "%AGENTE_DIR%"
%PYTHON_CMD% -m streamlit run app.py %PORT_ARG%

goto :end

:: ============================================================
:: FUNCIONES AUXILIARES
:: ============================================================

:find_python
:: Busca Python disponible en el sistema
set "PYTHON_CMD="
where python >nul 2>&1
if !ERRORLEVEL!==0 (
    set "PYTHON_CMD=python"
) else (
    where python3 >nul 2>&1
    if !ERRORLEVEL!==0 (
        set "PYTHON_CMD=python3"
    ) else (
        :: Buscar en ubicaciones comunes de Windows
        for %%P in (
            "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
            "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
            "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
            "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
            "%LOCALAPPDATA%\Programs\Python\Python38\python.exe"
            "C:\Python312\python.exe"
            "C:\Python311\python.exe"
            "C:\Python310\python.exe"
            "C:\Python39\python.exe"
            "C:\Python38\python.exe"
        ) do (
            if exist %%P (
                set "PYTHON_CMD=%%P"
                goto :found_python
            )
        )
    )
)
:found_python
goto :eof

:show_help
echo.
echo  USO: start.bat [OPCION]
echo.
echo  Opciones:
echo    (sin opcion)  Inicio completo con verificaciones
echo    --skip        Saltar verificaciones, inicio rapido
echo    --check       Solo verificar, no iniciar
echo    --install     Instalar/actualizar dependencias
echo    --diag        Diagnostico completo (GPU, red, versiones)
echo    --update      Actualizar desde GitHub
echo    --help        Mostrar esta ayuda
echo.
goto :end

:: ============================================================
:: ERROR
:: ============================================================
:error_exit
echo.
echo  ========================================================
echo   ERROR - No se pudo iniciar el agente
echo  ========================================================
echo.
echo  Sugerencias para solucionar:
echo.
echo    1. Verifica que Python 3.8+ este en el PATH
echo       Descarga: https://www.python.org/downloads/
echo       IMPORTANTE: Marca "Add Python to PATH" al instalar
echo.
echo    2. Instala dependencias manualmente:
echo       pip install streamlit ollama chromadb
echo.
echo    3. Abre Ollama desde el Menu Inicio antes de ejecutar start.bat
echo       Descarga: https://ollama.com
echo.
echo    4. Descarga un modelo:
echo       ollama pull qwen3:4b
echo.
echo    5. Asegurate de que start.bat este junto a app.py
echo.
echo    6. Actualiza el proyecto:
echo       start.bat --update
echo.
echo    7. Diagnostico completo:
echo       start.bat --diag
echo.
pause
exit /b 1

:end
echo.
echo  Agente detenido.
pause
