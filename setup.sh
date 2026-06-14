#!/usr/bin/env bash
# ============================================================
# AgentLocal - Script de Instalacion y Configuracion
# ============================================================
# Ejecutar DESPUES de clonar el repo:
#   git clone https://github.com/yecos/AgentLocal.git
#   cd AgentLocal
#   chmod +x setup.sh
#   ./setup.sh
# ============================================================

set -e

echo ""
echo "  ========================================================"
echo "   AgentLocal - Instalacion y Configuracion"
echo "  ========================================================"
echo ""

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "  Directorio del proyecto: $PROJECT_DIR"
echo ""

# ============================================================
# 1. VERIFICAR PRERREQUISITOS
# ============================================================
echo "  [1/8] Verificando prerrequisitos..."
echo ""

ERRORS=0

# Python
PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "  [XX] Python no encontrado. Instala Python 3.10+ desde https://www.python.org"
    ERRORS=1
else
    PY_VER=$($PYTHON_CMD --version 2>&1)
    echo "  [OK] Python: $PY_VER"
fi

# Node.js
if command -v node &>/dev/null; then
    NODE_VER=$(node --version 2>&1)
    echo "  [OK] Node.js: $NODE_VER"
else
    echo "  [XX] Node.js no encontrado. Instala Node.js 18+ desde https://nodejs.org"
    ERRORS=1
fi

# npm
if command -v npm &>/dev/null; then
    NPM_VER=$(npm --version 2>&1)
    echo "  [OK] npm: $NPM_VER"
else
    echo "  [XX] npm no encontrado."
    ERRORS=1
fi

# Git
if command -v git &>/dev/null; then
    echo "  [OK] Git: $(git --version 2>&1)"
else
    echo "  [!!] Git no encontrado (opcional para updates)"
fi

# Ollama
if command -v ollama &>/dev/null; then
    echo "  [OK] Ollama instalado"
else
    echo "  [!!] Ollama no encontrado. Instalalo desde https://ollama.com"
    echo "       Despues descarga un modelo: ollama pull qwen3:4b"
fi

if [ $ERRORS -eq 1 ]; then
    echo ""
    echo "  [XX] Faltan prerrequisitos. Instalalos y vuelve a ejecutar este script."
    exit 1
fi

echo ""

# ============================================================
# 2. LIMPIAR CLONES DUPLICADOS (si existen)
# ============================================================
echo "  [2/8] Limpiando duplicados..."
echo ""

# Eliminar directorios que son clones del mismo repo (no deben existir)
for dir in "AgentLocal" "AgentLocal-repo"; do
    if [ -d "$PROJECT_DIR/$dir" ]; then
        echo "  [..] Eliminando $dir/ (clon duplicado del mismo repo)"
        rm -rf "$PROJECT_DIR/$dir"
        echo "  [OK] $dir/ eliminado"
    fi
done

# Eliminar directorio download/ (archivos generados)
if [ -d "$PROJECT_DIR/download" ]; then
    echo "  [..] Eliminando download/ (archivos generados, no necesarios)"
    rm -rf "$PROJECT_DIR/download"
    echo "  [OK] download/ eliminado"
fi

echo "  [OK] Limpieza completada"
echo ""

# ============================================================
# 3. CREAR ARCHIVO .env
# ============================================================
echo "  [3/8] Configurando entorno..."
echo ""

if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo "  [OK] .env creado desde .env.example"
else
    echo "  [OK] .env ya existe"
fi

echo ""

# ============================================================
# 4. CREAR DIRECTORIOS NECESARIOS
# ============================================================
echo "  [4/8] Creando directorios de trabajo..."
echo ""

for dir in "db" "upload" "tool-results" "LEARN_DIR"; do
    if [ ! -d "$PROJECT_DIR/$dir" ]; then
        mkdir -p "$PROJECT_DIR/$dir"
        echo "  [OK] Creado: $dir/"
    else
        echo "  [OK] Existe: $dir/"
    fi
done

# Directorios del agente
for dir in "$HOME/repos" "$HOME/.ia-local/learning" "$HOME/.ia-local/learning/vectors"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "  [OK] Creado: $dir"
    else
        echo "  [OK] Existe: $dir"
    fi
done

echo ""

# ============================================================
# 5. INSTALAR DEPENDENCIAS PYTHON
# ============================================================
echo "  [5/8] Instalando dependencias Python..."
echo ""

cd "$PROJECT_DIR/agente_v14"

if [ -f "requirements.txt" ]; then
    $PYTHON_CMD -m pip install -r requirements.txt --quiet 2>&1 | tail -5
    echo "  [OK] Dependencias Python instaladas"
else
    echo "  [!!] requirements.txt no encontrado, instalando lo basico..."
    $PYTHON_CMD -m pip install fastapi uvicorn ollama chromadb streamlit --quiet
    echo "  [OK] Dependencias basicas instaladas"
fi

echo ""

# ============================================================
# 6. INSTALAR DEPENDENCIAS NODE.JS
# ============================================================
echo "  [6/8] Instalando dependencias Node.js..."
echo ""

cd "$PROJECT_DIR"

if [ -f "package.json" ]; then
    npm install --legacy-peer-deps 2>&1 | tail -10
    echo "  [OK] Dependencias Node.js instaladas"
else
    echo "  [!!] package.json no encontrado"
fi

echo ""

# ============================================================
# 7. VERIFICAR OLLAMA
# ============================================================
echo "  [7/8] Verificando Ollama..."
echo ""

if $PYTHON_CMD -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)" 2>/dev/null; then
    echo "  [OK] Ollama corriendo en localhost:11434"
    echo ""
    echo "  Modelos disponibles:"
    $PYTHON_CMD -c "
import urllib.request, json
try:
    resp = urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3)
    data = json.loads(resp.read())
    for m in data.get('models', []):
        size_gb = m.get('size', 0) / (1024**3)
        print(f'    - {m[\"name\"]} ({size_gb:.1f} GB)')
    if not data.get('models'):
        print('    (ninguno) - Descarga uno: ollama pull qwen3:4b')
except Exception as e:
    print(f'    Error: {e}')
" 2>/dev/null
else
    echo "  [!!] Ollama no esta corriendo"
    echo "       Inicialo con: ollama serve"
    echo "       En otra terminal, descarga un modelo: ollama pull qwen3:4b"
fi

echo ""

# ============================================================
# 8. VERIFICACION FINAL DE IMPORTS
# ============================================================
echo "  [8/8] Verificando imports del agente..."
echo ""

cd "$PROJECT_DIR/agente_v14"

IMPORT_ERRORS=0
for module in "config" "llm" "utils.security" "utils.helpers" "memory.triple_memory" "memory.vectorstore" "memory.learning" "tools" "agent"; do
    if $PYTHON_CMD -c "import $module" 2>/dev/null; then
        echo "  [OK] $module"
    else
        # Intentar con path absoluto
        if $PYTHON_CMD -c "import sys; sys.path.insert(0, '.'); import $module" 2>/dev/null; then
            echo "  [OK] $module (con path)"
        else
            echo "  [XX] $module - Error importando"
            IMPORT_ERRORS=1
        fi
    fi
done

# Verificar FastAPI para el bridge
if $PYTHON_CMD -c "from fastapi import FastAPI" 2>/dev/null; then
    echo "  [OK] fastapi (bridge_api)"
else
    echo "  [XX] fastapi - Error importando"
    IMPORT_ERRORS=1
fi

echo ""

# ============================================================
# RESUMEN FINAL
# ============================================================
echo "  ========================================================"
echo "   INSTALACION COMPLETADA"
echo "  ========================================================"
echo ""

if [ $IMPORT_ERRORS -eq 1 ]; then
    echo "  [!!] Hubo errores de importacion. Algunas funciones pueden fallar."
    echo "      Intenta: pip install -r agente_v14/requirements.txt"
    echo ""
fi

echo "  Para iniciar el agente necesitas 2 terminales:"
echo ""
echo "  TERMINAL 1 - Bridge API (backend Python):"
echo "    cd $PROJECT_DIR/agente_v14"
echo "    python bridge_api.py"
echo ""
echo "  TERMINAL 2 - Interfaz web (Next.js):"
echo "    cd $PROJECT_DIR"
echo "    npm run dev"
echo ""
echo "  Luego abre: http://localhost:3000"
echo ""
echo "  Alternativa rapida (solo agente, sin web):"
echo "    cd $PROJECT_DIR/agente_v14"
echo "    ./start.sh"
echo ""
echo "  ========================================================"
