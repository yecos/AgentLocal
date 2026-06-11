#!/usr/bin/env bash
# ============================================================
# AGENTE LOCAL AUTONOMO v14 - Script de Inicio y Verificacion
# ============================================================
# Uso: ./start.sh          (inicio completo con verificacion)
#      ./start.sh --skip   (saltar verificaciones, solo iniciar)
#      ./start.sh --check  (solo verificar, no iniciar)
#      ./start.sh --install (instalar dependencias faltantes)
# ============================================================

set -e

# Colores
OK='\033[92m[OK]\033[0m'
WARN='\033[93m[!!]\033[0m'
FAIL='\033[91m[XX]\033[0m'
INFO='\033[96m[..]\033[0m'
CYAN='\033[96m'
RESET='\033[0m'

# Argumentos
SKIP_CHECK=0
CHECK_ONLY=0
FORCE_INSTALL=0

for arg in "$@"; do
    case $arg in
        --skip)   SKIP_CHECK=1 ;;
        --check)  CHECK_ONLY=1 ;;
        --install) FORCE_INSTALL=1 ;;
        --help|-h)
            echo "Uso: $0 [--skip|--check|--install]"
            echo "  --skip    Saltar verificaciones"
            echo "  --check   Solo verificar, no iniciar"
            echo "  --install Instalar/actualizar dependencias"
            exit 0 ;;
    esac
done

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║     AGENTE LOCAL AUTONOMO v14 - Inicio          ║"
echo "  ║     Arquitectura Modular / ReAct + TripleMemory ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""

AGENTE_DIR="$(cd "$(dirname "$0")" && pwd)"

# ============================================================
# 1. VERIFICAR ESTRUCTURA DE ARCHIVOS
# ============================================================
if [ $SKIP_CHECK -eq 0 ]; then
    echo -e "${CYAN}━━━ VERIFICACION DE ESTRUCTURA ━━━${RESET}"
    echo ""

    MISSING=0
    REQUIRED_FILES=(
        "app.py" "config.py" "llm.py" "__init__.py"
        "agent/__init__.py" "agent/react.py" "agent/schemas.py"
        "tools/__init__.py" "tools/schemas.py" "tools/sistema.py"
        "tools/archivos.py" "tools/apps.py" "tools/proyecto.py"
        "tools/codigo.py" "tools/web.py"
        "memory/__init__.py" "memory/triple_memory.py"
        "memory/learning.py" "memory/vectorstore.py"
        "utils/__init__.py" "utils/helpers.py" "utils/security.py"
    )

    for f in "${REQUIRED_FILES[@]}"; do
        if [ -f "$AGENTE_DIR/$f" ]; then
            echo -e "  $OK $f"
        else
            echo -e "  $FAIL $f - NO ENCONTRADO"
            MISSING=1
        fi
    done

    echo ""
    if [ $MISSING -eq 1 ]; then
        echo -e "  $FAIL Faltan archivos del proyecto. No se puede continuar."
        exit 1
    fi

    # ============================================================
    # 2. VERIFICAR PYTHON
    # ============================================================
    echo -e "${CYAN}━━━ VERIFICACION DE PYTHON ━━━${RESET}"
    echo ""

    PYTHON_CMD=""
    if command -v python3 &>/dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &>/dev/null; then
        PYTHON_CMD="python"
    fi

    if [ -z "$PYTHON_CMD" ]; then
        echo -e "  $FAIL Python no encontrado en el PATH"
        echo -e "  Instala Python 3.8+ desde: https://www.python.org/downloads/"
        exit 1
    fi

    PY_VER=$($PYTHON_CMD --version 2>&1)
    echo -e "  $OK Python encontrado: $PY_VER"

    # Verificar version minima
    if ! $PYTHON_CMD -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)" 2>/dev/null; then
        echo -e "  $FAIL Python 3.8+ requerido. Version actual demasiado antigua."
        exit 1
    fi

    # ============================================================
    # 3. VERIFICAR PAQUETES PYTHON
    # ============================================================
    echo ""
    echo -e "${CYAN}━━━ VERIFICACION DE DEPENDENCIAS PYTHON ━━━${RESET}"
    echo ""

    PKG_MISSING=0

    if $PYTHON_CMD -c "import streamlit" 2>/dev/null; then
        ST_VER=$($PYTHON_CMD -c "import streamlit; print(streamlit.__version__)" 2>/dev/null)
        echo -e "  $OK streamlit $ST_VER"
    else
        echo -e "  $WARN streamlit - NO INSTALADO"
        PKG_MISSING=1
    fi

    if $PYTHON_CMD -c "import ollama" 2>/dev/null; then
        OL_VER=$($PYTHON_CMD -c "import ollama; print(ollama.__version__)" 2>/dev/null || echo "instalado")
        echo -e "  $OK ollama $OL_VER"
    else
        echo -e "  $WARN ollama - NO INSTALADO (opcional, se usa HTTP como fallback)"
    fi

    # ============================================================
    # 4. VERIFICAR OLLAMA
    # ============================================================
    echo ""
    echo -e "${CYAN}━━━ VERIFICACION DE OLLAMA ━━━${RESET}"
    echo ""

    if $PYTHON_CMD -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)" 2>/dev/null; then
        echo -e "  $OK Ollama corriendo en localhost:11434"
        echo ""
        echo -e "  $INFO Modelos disponibles:"
        $PYTHON_CMD -c "
import urllib.request, json
try:
    resp = urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)
    data = json.loads(resp.read())
    for m in data.get('models', []):
        print(f'     - {m[\"name\"]}')
except:
    pass" 2>/dev/null | while read line; do echo "  $line"; done
    else
        echo -e "  $WARN Ollama no responde en localhost:11434"
        if command -v ollama &>/dev/null; then
            echo -e "  $INFO Ollama esta instalado pero no esta corriendo."
            echo -e "  $INFO Intentando iniciar Ollama..."
            ollama serve &
            OLLAMA_PID=$!
            sleep 5

            if $PYTHON_CMD -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=5)" 2>/dev/null; then
                echo -e "  $OK Ollama iniciado correctamente! (PID: $OLLAMA_PID)"
            else
                echo -e "  $WARN Ollama no pudo iniciarse automaticamente."
                echo -e "  Inicielo manualmente: ollama serve"
            fi
        else
            echo -e "  $FAIL Ollama no encontrado. Instalalo desde: https://ollama.com"
            echo -e "  El agente usara fallback HTTP pero necesita Ollama corriendo."
        fi
    fi

    # ============================================================
    # 5. VERIFICAR DIRECTORIOS DE TRABAJO
    # ============================================================
    echo ""
    echo -e "${CYAN}━━━ VERIFICACION DE DIRECTORIOS ━━━${RESET}"
    echo ""

    REPOS_DIR="$HOME/repos"
    LEARN_DIR="$HOME/.ia-local/learning"

    for dir in "$REPOS_DIR" "$LEARN_DIR" "$LEARN_DIR/vectors"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            echo -e "  $OK Creado: $dir"
        else
            echo -e "  $OK Existe: $dir"
        fi
    done

    # ============================================================
    # 6. VERIFICACION DE IMPORTACIONES
    # ============================================================
    echo ""
    echo -e "${CYAN}━━━ VERIFICACION DE IMPORTACIONES ━━━${RESET}"
    echo ""

    cd "$AGENTE_DIR"

    check_import() {
        local name="$1"
        local code="$2"
        if $PYTHON_CMD -c "$code" 2>/dev/null; then
            echo -e "  $OK $name"
        else
            echo -e "  $FAIL Error importando $name"
        fi
    }

    check_import "config"          "from config import REPOS_DIR, IS_WINDOWS, logger"
    check_import "utils.security"  "from utils.security import is_dangerous_command, validate_path"
    check_import "utils.helpers"   "from utils.helpers import strip_prefixes, open_in_browser"
    check_import "memory.vectorstore" "from memory.vectorstore import VectorStore"
    check_import "memory.learning"    "from memory.learning import LearningSystem"
    check_import "memory.triple_memory" "from memory.triple_memory import TripleMemory"
    check_import "tools"           "from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS"
    check_import "llm"             "from llm import ollama"
    check_import "agent"           "from agent import ReactAgent"
fi

if [ $CHECK_ONLY -eq 1 ]; then
    echo ""
    echo -e "${CYAN}━━━ VERIFICACION COMPLETADA ━━━${RESET}"
    echo -e "  $OK Todo correcto! El agente esta listo para ejecutarse."
    exit 0
fi

# ============================================================
# 7. INSTALAR DEPENDENCIAS FALTANTES
# ============================================================
if [ $PKG_MISSING -eq 1 ]; then
    echo ""
    echo -e "${CYAN}━━━ INSTALANDO DEPENDENCIAS FALTANTES ━━━${RESET}"
    echo ""

    echo -e "  $INFO Instalando streamlit..."
    $PYTHON_CMD -m pip install streamlit --quiet && echo -e "  $OK streamlit instalado" || echo -e "  $FAIL Error instalando streamlit"

    echo -e "  $INFO Instalando ollama..."
    $PYTHON_CMD -m pip install ollama --quiet && echo -e "  $OK ollama instalado" || echo -e "  $WARN Error instalando ollama (se usara HTTP como fallback)"

    echo ""
    echo -e "  $OK Dependencias instaladas."
fi

if [ $FORCE_INSTALL -eq 1 ]; then
    echo ""
    echo -e "${CYAN}━━━ INSTALACION FORZADA DE DEPENDENCIAS ━━━${RESET}"
    echo ""
    echo -e "  $INFO Instalando/actualizando todas las dependencias..."
    $PYTHON_CMD -m pip install streamlit ollama --upgrade --quiet
    echo -e "  $OK Dependencias instaladas/actualizadas."
fi

# ============================================================
# 8. RESUMEN PRE-INICIO
# ============================================================
echo ""
echo -e "${CYAN}━━━ RESUMEN ━━━${RESET}"
echo ""
echo "  Proyecto:  $AGENTE_DIR"
echo "  Python:    $PYTHON_CMD"
echo "  Interfaz:  Streamlit (web)"
echo "  LLM:       Ollama (local)"
echo ""
echo "  Comandos utiles:"
echo "    ./start.sh           - Inicio completo con verificacion"
echo "    ./start.sh --skip    - Inicio rapido (sin verificar)"
echo "    ./start.sh --check   - Solo verificar, no iniciar"
echo "    ./start.sh --install - Instalar/actualizar dependencias"
echo ""

# ============================================================
# 9. INICIAR AGENTE
# ============================================================
echo -e "${CYAN}━━━ INICIANDO AGENTE ━━━${RESET}"
echo ""
echo -e "  $INFO Ejecutando: streamlit run app.py"
echo -e "  $INFO Se abrira el navegador automaticamente."
echo -e "  $INFO Presiona Ctrl+C para detener el agente."
echo ""

cd "$AGENTE_DIR"
$PYTHON_CMD -m streamlit run app.py --server.port 8501 --server.headless true
