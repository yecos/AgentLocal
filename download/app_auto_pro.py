"""
=============================================================================
  AGENTE AUTÓNOMO PRO - IA Local con Ejecución de Comandos
  Versión mejorada con herramientas de sistema, git, npm y más
=============================================================================
  Funcionalidades:
  - Agente autónomo con Plan → Ejecutar → Replanear → Responder
  - Ejecución de comandos del sistema (git, npm, python, etc.)
  - Clonar repositorios de GitHub
  - Instalar dependencias (npm, pip)
  - Leer, escribir y modificar archivos
  - Buscar en la web
  - RAG con documentos
  - Asistente de código
  
  Modelos recomendados:
  - Agente: qwen2.5:14b (mejor razonamiento)
  - Chat: llama3.1:8b
  - Código: qwen2.5-coder:7b
  
  Requisitos:
  pip install streamlit ollama langchain-ollama chromadb pypdf ddgs
=============================================================================
"""

import streamlit as st
import ollama
import json
import os
import sys
import subprocess
import platform
import datetime
import re
import shutil
import time
import signal
from pathlib import Path

# =====================================================================
# CONFIGURACIÓN
# =====================================================================

AGENT_MODEL = "qwen2.5:14b"
CHAT_MODEL = "llama3.1:8b"
CODE_MODEL = "qwen2.5-coder:7b"
OLLAMA_URL = "http://localhost:11434"

# Detectar sistema operativo
IS_WINDOWS = platform.system() == "Windows"

# Directorios del usuario
USER_HOME = os.path.expanduser("~")
DOWNLOADS_DIR = os.path.join(USER_HOME, "Downloads")
DOCUMENTS_DIR = os.path.join(USER_HOME, "Documents")
DESKTOP_DIR = os.path.join(USER_HOME, "Desktop")

# Directorio de proyectos
PROJECTS_DIR = os.path.join(USER_HOME, "Projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

# Directorio de backups
BACKUP_DIR = os.path.join(USER_HOME, ".ia-backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

# Comandos peligrosos que requieren confirmación
DANGEROUS_COMMANDS = [
    "rm ", "del ", "rmdir", "format", "mkfs", "dd ", 
    "shutdown", "restart", "reboot",
    "reg ", "registry", "net user", "net localgroup",
    "taskkill", "kill ", "pkill",
    "format ", "fdisk", "diskpart",
    "cipher", "icacls",
    "wget", "curl -X DELETE",
    "docker rm", "docker rmi", "docker system prune",
    "> ", "2>nul", "out-null",
    "Remove-Item", "rm -rf", "rm -r",
]

# Comandos BLOQUEADOS (nunca se ejecutan)
BLOCKED_COMMANDS = [
    "format c:", "format d:", "del /f /s /q c:", "del /f /s /q d:",
    "rm -rf /", "rm -rf /*", "rd /s /q c:", "rd /s /q d:",
    "shutdown /s", "shutdown /r",
]

# Timeout por defecto para comandos (segundos)
DEFAULT_COMMAND_TIMEOUT = 120

# =====================================================================
# CONFIGURACIÓN DE PÁGINA
# =====================================================================

st.set_page_config(
    page_title="IA Local Pro - Agente Autónomo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================================
# ESTILOS CSS
# =====================================================================

st.markdown("""
<style>
    .stApp { max-width: 1400px; margin: 0 auto; }
    .tool-result {
        background: #1e1e2e;
        border: 1px solid #45475a;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        font-family: 'Consolas', monospace;
        font-size: 13px;
        color: #cdd6f4;
        white-space: pre-wrap;
        max-height: 400px;
        overflow-y: auto;
    }
    .tool-cmd {
        background: #1e1e2e;
        border: 1px solid #89b4fa;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        font-family: 'Consolas', monospace;
        font-size: 13px;
        color: #89b4fa;
    }
    .tool-warning {
        background: #1e1e2e;
        border: 1px solid #f38ba8;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        color: #f38ba8;
    }
    .tool-success {
        background: #1e1e2e;
        border: 1px solid #a6e3a1;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        color: #a6e3a1;
    }
    .plan-box {
        background: linear-gradient(135deg, #1e1e2e, #313244);
        border: 1px solid #cba6f7;
        border-radius: 10px;
        padding: 16px;
        margin: 12px 0;
        color: #cba6f7;
    }
    .confirm-box {
        background: #1e1e2e;
        border: 2px solid #f9e2af;
        border-radius: 10px;
        padding: 16px;
        margin: 12px 0;
        color: #f9e2af;
    }
    .step-badge {
        display: inline-block;
        background: #45475a;
        color: #cdd6f4;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 12px;
        margin-right: 8px;
    }
</style>
""", unsafe_allow_html=True)

# =====================================================================
# FUNCIONES AUXILIARES
# =====================================================================

def create_backup(filepath):
    """Crea backup de un archivo antes de modificarlo"""
    try:
        if os.path.exists(filepath):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            basename = os.path.basename(filepath)
            backup_name = f"{basename}.{timestamp}.bak"
            backup_path = os.path.join(BACKUP_DIR, backup_name)
            shutil.copy2(filepath, backup_path)
            return backup_path
    except Exception as e:
        return f"Error creando backup: {str(e)}"
    return None

def is_dangerous_command(cmd):
    """Verifica si un comando es potencialmente peligroso"""
    cmd_lower = cmd.lower().strip()
    
    # Verificar comandos bloqueados
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return "blocked"
    
    # Verificar comandos peligrosos
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous.lower() in cmd_lower:
            return "dangerous"
    
    return "safe"

def run_command(command, cwd=None, timeout=DEFAULT_COMMAND_TIMEOUT):
    """Ejecuta un comando del sistema de forma segura"""
    try:
        # Verificar si es peligroso
        danger_level = is_dangerous_command(command)
        if danger_level == "blocked":
            return "⛔ COMANDO BLOQUEADO por seguridad. No se puede ejecutar.", -1
        
        if danger_level == "dangerous":
            return "⚠️ Comando peligroso detectado. Requiere confirmación del usuario.", -2
        
        # Ejecutar comando
        shell = IS_WINDOWS
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            encoding='utf-8',
            errors='replace'
        )
        
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[STDERR]: {result.stderr}"
        
        if not output.strip():
            output = "(Comando ejecutado sin salida visible)"
        
        return output.strip(), result.returncode
        
    except subprocess.TimeoutExpired:
        return f"⏱️ Tiempo de espera agotado ({timeout}s). El comando tardó demasiado.", -3
    except FileNotFoundError:
        return f"❌ Comando no encontrado. ¿Está instalado?", -4
    except Exception as e:
        return f"❌ Error ejecutando comando: {str(e)}", -5

def force_run_command(command, cwd=None, timeout=DEFAULT_COMMAND_TIMEOUT):
    """Ejecuta un comando incluso si es peligroso (con confirmación previa del usuario)"""
    try:
        shell = IS_WINDOWS
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            encoding='utf-8',
            errors='replace'
        )
        
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[STDERR]: {result.stderr}"
        
        if not output.strip():
            output = "(Comando ejecutado sin salida visible)"
        
        return output.strip(), result.returncode
        
    except subprocess.TimeoutExpired:
        return f"⏱️ Tiempo de espera agotado ({timeout}s)", -3
    except Exception as e:
        return f"❌ Error: {str(e)}", -5

# =====================================================================
# DEFINICIÓN DE HERRAMIENTAS
# =====================================================================

TOOLS = {
    "ejecutar_comando": {
        "description": "Ejecuta un comando del sistema operativo (PowerShell/CMD en Windows, Bash en Linux). Puede ejecutar git, npm, pip, python, dir, ls, cd, etc.",
        "params": ["comando", "directorio?"],
        "example": 'ejecutar_comando("git clone https://github.com/user/repo.git", "C:\\Projects")'
    },
    "clonar_repositorio": {
        "description": "Clona un repositorio de GitHub. automáticamente crea el directorio y descarga el proyecto.",
        "params": ["url_repositorio", "directorio_destino?"],
        "example": 'clonar_repositorio("https://github.com/yecos/signalTrade.git")'
    },
    "instalar_dependencias": {
        "description": "Instala dependencias de un proyecto (npm install, pip install, etc.). Detecta automáticamente qué tipo de proyecto es.",
        "params": ["directorio_proyecto", "tipo?"],
        "example": 'instalar_dependencias("C:\\Projects\\signalTrade", "npm")'
    },
    "listar_archivos": {
        "description": "Lista archivos y carpetas de un directorio. Muestra estructura del proyecto.",
        "params": ["ruta", "profundidad?"],
        "example": 'listar_archivos("C:\\Projects\\signalTrade", 2)'
    },
    "leer_archivo": {
        "description": "Lee el contenido completo de un archivo de texto o código.",
        "params": ["ruta_archivo"],
        "example": 'leer_archivo("C:\\Projects\\signalTrade\\package.json")'
    },
    "escribir_archivo": {
        "description": "Escribe contenido en un archivo. Crea el archivo si no existe. Hace backup automático del archivo anterior.",
        "params": ["ruta_archivo", "contenido"],
        "example": 'escribir_archivo("C:\\Projects\\signalTrade\\test.txt", "Hola mundo")'
    },
    "modificar_archivo": {
        "description": "Modifica una parte específica de un archivo. Busca el texto_original y lo reemplaza con texto_nuevo. Más seguro que escribir todo el archivo.",
        "params": ["ruta_archivo", "texto_original", "texto_nuevo"],
        "example": 'modificar_archivo("C:\\Projects\\signalTrade\\package.json", "\"version\": \"1.0.0\"", "\"version\": \"1.1.0\"")'
    },
    "buscar_en_archivos": {
        "description": "Busca un texto o patrón dentro de todos los archivos de un directorio (como grep).",
        "params": ["directorio", "texto_buscar", "extension?"],
        "example": 'buscar_en_archivos("C:\\Projects\\signalTrade", "useEffect", ".tsx")'
    },
    "calcular": {
        "description": "Evalúa una expresión matemática. Solo acepta números y operadores, NO variables.",
        "params": ["expresion"],
        "example": 'calcular("2 + 3 * 4")'
    },
    "buscar": {
        "description": "Busca información en internet usando DuckDuckGo.",
        "params": ["consulta"],
        "example": 'buscar("Next.js 14 app router tutorial")'
    },
    "info_sistema": {
        "description": "Muestra información del sistema: OS, RAM, disco, CPU, procesos.",
        "params": [],
        "example": 'info_sistema()'
    }
}

# =====================================================================
# IMPLEMENTACIÓN DE HERRAMIENTAS
# =====================================================================

def tool_ejecutar_comando(comando, directorio=None):
    """Ejecuta un comando del sistema"""
    cwd = directorio if directorio and os.path.isdir(directorio) else None
    
    if cwd:
        result, code = run_command(comando, cwd=cwd)
    else:
        result, code = run_command(comando)
    
    if code == -2:
        return result + f"\n\nSi estás seguro, puedes usar ejecutar_comando_forzado para confirmar la ejecución."
    
    return result

def tool_ejecutar_comando_forzado(comando, directorio=None):
    """Ejecuta un comando del sistema incluso si es peligroso (confirmado por usuario)"""
    cwd = directorio if directorio and os.path.isdir(directorio) else None
    result, code = force_run_command(comando, cwd=cwd)
    return result

def tool_clonar_repositorio(url, directorio_destino=None):
    """Clona un repositorio de GitHub"""
    # Validar URL
    if not url.startswith("https://github.com/") and not url.startswith("git@github.com:"):
        return "❌ URL inválida. Debe ser una URL de GitHub (https://github.com/...)"
    
    # Directorio destino
    if not directorio_destino:
        # Extraer nombre del repo de la URL
        repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
        directorio_destino = os.path.join(PROJECTS_DIR, repo_name)
    
    # Verificar si ya existe
    if os.path.exists(directorio_destino):
        return f"⚠️ El directorio ya existe: {directorio_destino}\nUsa ejecutar_comando('git pull', '{directorio_destino}') para actualizar."
    
    # Ejecutar git clone
    result, code = run_command(f'git clone {url} "{directorio_destino}"')
    
    if code == 0:
        return f"✅ Repositorio clonado exitosamente en: {directorio_destino}\n\nContenido:\n" + tool_listar_archivos(directorio_destino, 2)
    else:
        return f"❌ Error clonando repositorio:\n{result}"

def tool_instalar_dependencias(directorio, tipo=None):
    """Instala dependencias de un proyecto"""
    if not os.path.isdir(directorio):
        return f"❌ Directorio no encontrado: {directorio}"
    
    # Auto-detectar tipo si no se especifica
    if not tipo:
        if os.path.exists(os.path.join(directorio, "package.json")):
            tipo = "npm"
        elif os.path.exists(os.path.join(directorio, "requirements.txt")):
            tipo = "pip"
        elif os.path.exists(os.path.join(directorio, "Pipfile")):
            tipo = "pipenv"
        elif os.path.exists(os.path.join(directorio, "pyproject.toml")):
            tipo = "pip"
        else:
            return "❌ No se pudo detectar el tipo de proyecto. Especifica: npm, pip, pipenv"
    
    if tipo == "npm":
        result, code = run_command("npm install", cwd=directorio, timeout=300)
        if code == 0:
            return f"✅ Dependencias npm instaladas correctamente en: {directorio}\n\n{result[:500]}"
        else:
            return f"❌ Error instalando dependencias npm:\n{result}"
    
    elif tipo == "pip":
        req_file = os.path.join(directorio, "requirements.txt")
        if os.path.exists(req_file):
            result, code = run_command(f'pip install -r "{req_file}"', cwd=directorio, timeout=300)
            if code == 0:
                return f"✅ Dependencias pip instaladas desde requirements.txt\n\n{result[:500]}"
            else:
                return f"❌ Error instalando dependencias:\n{result}"
        else:
            return "❌ No se encontró requirements.txt"
    
    elif tipo == "pipenv":
        result, code = run_command("pipenv install", cwd=directorio, timeout=300)
        return result
    
    else:
        return f"❌ Tipo no soportado: {tipo}. Usa: npm, pip, pipenv"

def tool_listar_archivos(ruta, profundidad=3):
    """Lista archivos y carpetas de un directorio"""
    if not os.path.exists(ruta):
        return f"❌ Ruta no encontrada: {ruta}"
    
    if os.path.isfile(ruta):
        size = os.path.getsize(ruta)
        return f"📄 Archivo: {ruta} ({size} bytes)"
    
    resultado = []
    resultado.append(f"📂 {ruta}\n")
    
    for root, dirs, files in os.walk(ruta):
        # Calcular profundidad
        rel_path = os.path.relpath(root, ruta)
        depth = rel_path.count(os.sep) if rel_path != "." else 0
        
        if depth >= profundidad:
            dirs.clear()  # No seguir más profundo
            continue
        
        # Ocultar node_modules, .git, .next, etc.
        skip_dirs = ['node_modules', '.git', '.next', '__pycache__', '.venv', 'venv', 'dist', '.cache', '.turbo']
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
        
        indent = "  " * (depth + 1)
        
        for d in sorted(dirs):
            resultado.append(f"{indent}📁 {d}/")
        
        for f in sorted(files):
            size = 0
            try:
                size = os.path.getsize(os.path.join(root, f))
            except:
                pass
            size_str = f" ({size}b)" if size < 1024 else f" ({size//1024}kb)"
            resultado.append(f"{indent}📄 {f}{size_str}")
    
    return "\n".join(resultado)

def tool_leer_archivo(ruta):
    """Lee el contenido de un archivo"""
    if not os.path.exists(ruta):
        return f"❌ Archivo no encontrado: {ruta}"
    
    try:
        with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
            contenido = f.read()
        
        # Limitar a 15000 caracteres para no saturar
        if len(contenido) > 15000:
            contenido = contenido[:15000] + f"\n\n... [Archivo truncado - {len(contenido)} caracteres total. Lee por secciones si necesitas más.]"
        
        return contenido
    except Exception as e:
        return f"❌ Error leyendo archivo: {str(e)}"

def tool_escribir_archivo(ruta, contenido):
    """Escribe contenido en un archivo (con backup automático)"""
    try:
        # Crear directorio si no existe
        directorio = os.path.dirname(ruta)
        if directorio:
            os.makedirs(directorio, exist_ok=True)
        
        # Hacer backup si el archivo ya existe
        backup_path = create_backup(ruta)
        backup_msg = f"📦 Backup creado: {backup_path}" if backup_path else ""
        
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(contenido)
        
        size = len(contenido)
        return f"✅ Archivo escrito exitosamente: {ruta} ({size} caracteres)\n{backup_msg}"
    except Exception as e:
        return f"❌ Error escribiendo archivo: {str(e)}"

def tool_modificar_archivo(ruta, texto_original, texto_nuevo):
    """Modifica una parte específica de un archivo (con backup automático)"""
    if not os.path.exists(ruta):
        return f"❌ Archivo no encontrado: {ruta}"
    
    try:
        with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
            contenido = f.read()
        
        if texto_original not in contenido:
            # Intentar búsqueda flexible (ignorando espacios extra)
            texto_orig_limpio = re.sub(r'\s+', ' ', texto_original.strip())
            contenido_limpio = re.sub(r'\s+', ' ', contenido)
            if texto_orig_limpio in contenido_limpio:
                return f"❌ Texto no encontrado exactamente. El texto es similar pero con espacios/indentación diferente.\nSugerencia: Usa leer_archivo primero para copiar el texto exacto."
            return f"❌ Texto original no encontrado en el archivo.\nSugerencia: Usa leer_archivo('{ruta}') para ver el contenido actual."
        
        # Contar ocurrencias
        ocurrencias = contenido.count(texto_original)
        if ocurrencias > 1:
            return f"⚠️ El texto aparece {ocurrencias} veces. Se reemplazarán TODAS.\nUsa escribir_archivo si necesitas más control."
        
        # Hacer backup
        backup_path = create_backup(ruta)
        backup_msg = f"\n📦 Backup: {backup_path}" if backup_path else ""
        
        # Reemplazar
        nuevo_contenido = contenido.replace(texto_original, texto_nuevo)
        
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(nuevo_contenido)
        
        # Mostrar diff
        diff = f"Archivo: {ruta}\n"
        diff += f"Eliminado: {texto_original[:200]}{'...' if len(texto_original) > 200 else ''}\n"
        diff += f"Agregado: {texto_nuevo[:200]}{'...' if len(texto_nuevo) > 200 else ''}\n"
        diff += f"✅ Archivo modificado exitosamente.{backup_msg}"
        
        return diff
    except Exception as e:
        return f"❌ Error modificando archivo: {str(e)}"

def tool_buscar_en_archivos(directorio, texto, extension=None):
    """Busca un texto dentro de archivos de un directorio"""
    if not os.path.isdir(directorio):
        return f"❌ Directorio no encontrado: {directorio}"
    
    resultados = []
    skip_dirs = ['node_modules', '.git', '.next', '__pycache__', '.venv', 'venv', 'dist', '.cache', '.turbo', 'build']
    skip_exts = ['.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.woff', '.woff2', '.ttf', '.eot', '.map', '.lock']
    
    for root, dirs, files in os.walk(directorio):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
        
        for fname in files:
            fpath = os.path.join(root, fname)
            _, ext = os.path.splitext(fname)
            
            if ext.lower() in skip_exts:
                continue
            if extension and ext.lower() != extension.lower():
                continue
            
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    for i, line in enumerate(f, 1):
                        if texto.lower() in line.lower():
                            rel_path = os.path.relpath(fpath, directorio)
                            line_clean = line.strip()[:120]
                            resultados.append(f"{rel_path}:{i} → {line_clean}")
                            if len(resultados) >= 50:
                                return "\n".join(resultados) + "\n\n... [Resultados limitados a 50]"
            except:
                continue
    
    if not resultados:
        return f"🔍 No se encontró '{texto}' en {directorio}"
    
    return "\n".join(resultados)

def tool_calcular(expresion):
    """Evalúa una expresión matemática de forma segura"""
    # Limpiar expresión
    expresion = expresion.replace("^", "**")
    # Solo permitir números, operadores y funciones matemáticas
    permitido = re.match(r'^[\d\s\+\-\*\/\.\(\)eE]+$', expresion)
    if not permitido:
        return "❌ Solo se permiten números y operadores (+, -, *, /, (), **)"
    try:
        resultado = eval(expresion, {"__builtins__": {}}, {})
        return str(resultado)
    except Exception as e:
        return f"❌ Error en cálculo: {str(e)}"

def tool_buscar(consulta):
    """Busca en internet con DuckDuckGo"""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(consulta, max_results=5))
        if not results:
            return "🔍 No se encontraron resultados"
        salida = []
        for r in results:
            salida.append(f"📌 {r.get('title', 'Sin título')}\n   {r.get('body', '')}\n   🔗 {r.get('href', '')}")
        return "\n\n".join(salida)
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(consulta, max_results=5))
            if not results:
                return "🔍 No se encontraron resultados"
            salida = []
            for r in results:
                salida.append(f"📌 {r.get('title', 'Sin título')}\n   {r.get('body', '')}\n   🔗 {r.get('href', '')}")
            return "\n\n".join(salida)
        except ImportError:
            return "❌ Instala: pip install ddgs"
    except Exception as e:
        return f"❌ Error buscando: {str(e)}"

def tool_info_sistema():
    """Información del sistema"""
    info = []
    info.append(f"🖥️ Sistema: {platform.system()} {platform.release()}")
    info.append(f"💻 Procesador: {platform.processor()}")
    info.append(f"🏠 Usuario: {USER_HOME}")
    info.append(f"📂 Descargas: {DOWNLOADS_DIR}")
    info.append(f"📂 Documentos: {DOCUMENTS_DIR}")
    info.append(f"📂 Escritorio: {DESKTOP_DIR}")
    info.append(f"📂 Proyectos: {PROJECTS_DIR}")
    
    # Disco
    try:
        if IS_WINDOWS:
            for drive in ['C:', 'D:']:
                if os.path.exists(drive + '\\'):
                    usage = shutil.disk_usage(drive + '\\')
                    free_gb = usage.free // (1024**3)
                    total_gb = usage.total // (1024**3)
                    info.append(f"💾 Disco {drive}: {free_gb}GB libres de {total_gb}GB")
        else:
            usage = shutil.disk_usage('/')
            free_gb = usage.free // (1024**3)
            total_gb = usage.total // (1024**3)
            info.append(f"💾 Disco: {free_gb}GB libres de {total_gb}GB")
    except:
        pass
    
    # RAM
    try:
        import psutil
        mem = psutil.virtual_memory()
        info.append(f"🧠 RAM: {mem.available // (1024**3)}GB disponibles de {mem.total // (1024**3)}GB")
    except:
        info.append("🧠 RAM: (instala psutil: pip install psutil)")
    
    # Proyectos existentes
    if os.path.exists(PROJECTS_DIR):
        proyectos = [d for d in os.listdir(PROJECTS_DIR) if os.path.isdir(os.path.join(PROJECTS_DIR, d))]
        if proyectos:
            info.append(f"📁 Proyectos existentes: {', '.join(proyectos)}")
    
    return "\n".join(info)

# Mapa de funciones
TOOL_FUNCTIONS = {
    "ejecutar_comando": tool_ejecutar_comando,
    "ejecutar_comando_forzado": tool_ejecutar_comando_forzado,
    "clonar_repositorio": tool_clonar_repositorio,
    "instalar_dependencias": tool_instalar_dependencias,
    "listar_archivos": tool_listar_archivos,
    "leer_archivo": tool_leer_archivo,
    "escribir_archivo": tool_escribir_archivo,
    "modificar_archivo": tool_modificar_archivo,
    "buscar_en_archivos": tool_buscar_en_archivos,
    "calcular": tool_calcular,
    "buscar": tool_buscar,
    "info_sistema": tool_info_sistema,
}

# =====================================================================
# PROMPT DEL AGENTE AUTÓNOMO
# =====================================================================

AGENT_SYSTEM_PROMPT = """Eres un agente de IA autónomo avanzado que PUEDE hacer cosas reales en el sistema del usuario.

## TUS CAPACIDADES (PUEDES hacer todo esto):
- ✅ Ejecutar comandos del sistema (git, npm, pip, python, dir, etc.)
- ✅ Clonar repositorios de GitHub
- ✅ Instalar dependencias de proyectos
- ✅ Leer, escribir y modificar archivos
- ✅ Buscar texto dentro de archivos de un proyecto
- ✅ Buscar información en internet
- ✅ Hacer cálculos matemáticos
- ✅ Ver información del sistema

## HERRAMIENTAS DISPONIBLES:

1. ejecutar_comando(comando, directorio?) - Ejecuta un comando del sistema
   Ejemplo: ejecutar_comando("git status", "C:\\Projects\\signalTrade")
   
2. clonar_repositorio(url, directorio_destino?) - Clona un repo de GitHub
   Ejemplo: clonar_repositorio("https://github.com/yecos/signalTrade.git")
   
3. instalar_dependencias(directorio, tipo?) - Instala dependencias (npm/pip)
   Ejemplo: instalar_dependencias("C:\\Projects\\signalTrade", "npm")
   
4. listar_archivos(ruta, profundidad?) - Lista archivos de un directorio
   Ejemplo: listar_archivos("C:\\Projects\\signalTrade", 3)
   
5. leer_archivo(ruta) - Lee el contenido de un archivo
   Ejemplo: leer_archivo("C:\\Projects\\signalTrade\\package.json")
   
6. escribir_archivo(ruta, contenido) - Escribe un archivo completo
   Ejemplo: escribir_archivo("C:\\Projects\\signalTrade\\test.js", "console.log('hello')")
   
7. modificar_archivo(ruta, texto_original, texto_nuevo) - Modifica parte de un archivo
   Ejemplo: modificar_archivo("app.js", "version: 1.0", "version: 2.0")
   
8. buscar_en_archivos(directorio, texto, extension?) - Busca en archivos
   Ejemplo: buscar_en_archivos("C:\\Projects\\signalTrade", "useEffect", ".tsx")
   
9. calcular(expresion) - Calcula expresión matemática
   Ejemplo: calcular("100 * 0.15")
   
10. buscar(consulta) - Busca en internet
    Ejemplo: buscar("Next.js 14 server components tutorial")
    
11. info_sistema() - Información del sistema

## CÓMO FUNCIONAS:

Cuando recibas una tarea del usuario, sigue este proceso:

### PASO 1: PLANIFICAR
Piensa qué necesitas hacer y en qué orden. Devuelve un JSON:
```json
{
  "pensamiento": "Qué necesito hacer y por qué",
  "pasos": [
    {"paso": 1, "accion": "descripción", "herramienta": "nombre_herramienta", "parametros": ["param1", "param2"]},
    {"paso": 2, "accion": "...", "herramienta": "...", "parametros": [...]}
  ]
}
```

### PASO 2: EJECUTAR
Ejecuta cada paso usando las herramientas. Muestra los resultados.

### PASO 3: REPLANIFICAR
Si los resultados no son los esperados, ajusta tu plan y ejecuta nuevas herramientas.

### PASO 4: RESPONDER
Da una respuesta final clara al usuario.

## REGLAS IMPORTANTES:

1. **SIEMPRE usa las herramientas** - No digas "no puedo", ÚSALAS.
2. **Para proyectos nuevos**, primero clona el repo con clonar_repositorio, luego instala dependencias con instalar_dependencias.
3. **Para modificar código**, primero lee el archivo con leer_archivo, luego usa modificar_archivo para cambiar partes específicas.
4. **Para crear archivos nuevos**, usa escribir_archivo.
5. **Los directorios del usuario son**: Descargas={downloads_dir}, Documentos={documents_dir}, Proyectos={projects_dir}
6. **Antes de modificar un archivo**, siempre léelo primero para entender el contexto.
7. **Si un comando falla**, intenta diagnosticar el problema y buscar alternativas.
8. **NUNCA digas que no puedes acceder a archivos** - Tienes herramientas para hacerlo.
9. **Los backups son automáticos** - No te preocupes por perder datos.
10. **Responde SIEMPRE en español**.
""".format(
    downloads_dir=DOWNLOADS_DIR,
    documents_dir=DOCUMENTS_DIR,
    projects_dir=PROJECTS_DIR
)

# =====================================================================
# AGENTE AUTÓNOMO
# =====================================================================

def parse_tool_calls(text):
    """Extrae llamadas a herramientas del texto del agente"""
    calls = []
    
    # Patrón: herramienta("param1", "param2") o herramienta(param1, param2)
    pattern = r'(\w+)\((.*?)\)'
    matches = re.finditer(pattern, text, re.DOTALL)
    
    for match in matches:
        tool_name = match.group(1)
        params_str = match.group(2)
        
        if tool_name not in TOOL_FUNCTIONS:
            continue
        
        # Parsear parámetros
        params = []
        try:
            # Intentar parsear como JSON
            params = json.loads(f'[{params_str}]')
        except:
            # Intentar extraer strings entre comillas
            quoted = re.findall(r'"([^"]*)"', params_str)
            if quoted:
                params = quoted
            else:
                quoted = re.findall(r"'([^']*)'", params_str)
                if quoted:
                    params = quoted
                else:
                    params = [p.strip().strip('"').strip("'") for p in params_str.split(",")]
        
        calls.append({
            "tool": tool_name,
            "params": params
        })
    
    return calls

def execute_tool_call(tool_name, params):
    """Ejecuta una llamada a herramienta"""
    if tool_name not in TOOL_FUNCTIONS:
        return f"❌ Herramienta no encontrada: {tool_name}"
    
    func = TOOL_FUNCTIONS[tool_name]
    
    try:
        result = func(*params)
        return result
    except TypeError as e:
        # Intentar con menos parámetros
        try:
            result = func(*params[:func.__code__.co_argcount])
            return result
        except:
            return f"❌ Error en parámetros de {tool_name}: {str(e)}"
    except Exception as e:
        return f"❌ Error ejecutando {tool_name}: {str(e)}"

def run_agent(user_message, history=[]):
    """Ejecuta el agente autónomo completo"""
    
    # Construir mensajes
    messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    messages.extend(history[-6:])  # Últimos 6 mensajes de contexto
    messages.append({"role": "user", "content": user_message})
    
    # === PASO 1: PLANIFICAR ===
    plan_prompt = messages.copy()
    plan_prompt.append({
        "role": "user", 
        "content": "\n\nPlanifica tu respuesta. Devuelve SOLO el JSON con tu plan. No ejecutes nada todavía."
    })
    
    try:
        plan_response = ollama.chat(
            model=AGENT_MODEL,
            messages=plan_prompt,
            stream=False
        )
        plan_text = plan_response["message"]["content"]
    except Exception as e:
        return f"❌ Error conectando con Ollama: {str(e)}", []
    
    # Mostrar plan
    plan_placeholder = st.markdown(f"""
    <div class="plan-box">
    <strong>📋 Plan del Agente:</strong><br><br>
    {plan_text.replace(chr(10), '<br>')}
    </div>
    """, unsafe_allow_html=True)
    
    # === PASO 2: EJECUTAR HERRAMIENTAS ===
    tool_calls = parse_tool_calls(plan_text)
    
    # Si no encontró herramientas en el plan, pedir ejecución directa
    if not tool_calls:
        exec_prompt = messages.copy()
        exec_prompt.append({
            "role": "assistant",
            "content": plan_text
        })
        exec_prompt.append({
            "role": "user",
            "content": "Ahora ejecuta las herramientas necesarias para completar la tarea. Usa las herramientas directamente, una por una. Formato: herramienta(\"param1\", \"param2\")"
        })
        
        try:
            exec_response = ollama.chat(
                model=AGENT_MODEL,
                messages=exec_prompt,
                stream=False
            )
            exec_text = exec_response["message"]["content"]
            tool_calls = parse_tool_calls(exec_text)
        except Exception as e:
            return f"❌ Error: {str(e)}", []
    
    # Ejecutar cada herramienta
    results = []
    tool_results_container = st.container()
    
    for i, call in enumerate(tool_calls):
        with tool_results_container:
            st.markdown(f'<div class="tool-cmd">🔧 Paso {i+1}: {call["tool"]}({", ".join(str(p)[:50] for p in call["params"])})</div>', unsafe_allow_html=True)
            
            result = execute_tool_call(call["tool"], call["params"])
            results.append({
                "tool": call["tool"],
                "params": call["params"],
                "result": result
            })
            
            # Mostrar resultado
            result_preview = str(result)[:800]
            st.markdown(f'<div class="tool-result">{result_preview}</div>', unsafe_allow_html=True)
    
    # === PASO 3: REPLANIFICAR si es necesario ===
    replan_needed = any(
        "❌" in r["result"] or "Error" in r["result"] or "no encontrado" in r["result"].lower()
        for r in results
    )
    
    if replan_needed and len(results) > 0:
        replan_prompt = messages.copy()
        replan_prompt.append({"role": "assistant", "content": plan_text})
        
        # Agregar resultados
        results_text = "Resultados de la ejecución:\n\n"
        for r in results:
            results_text += f"- {r['tool']}({', '.join(str(p)[:30] for p in r['params'])}): {str(r['result'])[:300]}\n"
        
        replan_prompt.append({"role": "user", "content": results_text + "\n\nAlgunas herramientas fallaron. Replanifica y ejecuta las herramientas corregidas."})
        
        try:
            replan_response = ollama.chat(
                model=AGENT_MODEL,
                messages=replan_prompt,
                stream=False
            )
            replan_text = replan_response["message"]["content"]
            replan_calls = parse_tool_calls(replan_text)
            
            # Ejecutar nuevas herramientas
            for i, call in enumerate(replan_calls):
                with tool_results_container:
                    st.markdown(f'<div class="tool-cmd">🔄 Replan {i+1}: {call["tool"]}({", ".join(str(p)[:50] for p in call["params"])})</div>', unsafe_allow_html=True)
                    
                    result = execute_tool_call(call["tool"], call["params"])
                    results.append({
                        "tool": call["tool"],
                        "params": call["params"],
                        "result": result
                    })
                    
                    result_preview = str(result)[:800]
                    st.markdown(f'<div class="tool-result">{result_preview}</div>', unsafe_allow_html=True)
        except:
            pass
    
    # === PASO 4: RESPUESTA FINAL ===
    final_prompt = messages.copy()
    final_prompt.append({"role": "assistant", "content": plan_text})
    
    results_summary = "Resultados de las herramientas:\n\n"
    for r in results:
        results_summary += f"- {r['tool']}: {str(r['result'])[:500]}\n"
    
    final_prompt.append({
        "role": "user", 
        "content": results_summary + "\n\nBasándote en estos resultados, da una respuesta final clara y útil al usuario en español."
    })
    
    try:
        final_response = ollama.chat(
            model=AGENT_MODEL,
            messages=final_prompt,
            stream=False
        )
        final_text = final_response["message"]["content"]
    except Exception as e:
        final_text = f"Error generando respuesta final: {str(e)}\n\nResultados obtenidos:\n{results_summary}"
    
    # Actualizar historial
    new_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": final_text}
    ]
    
    return final_text, new_history

# =====================================================================
# CHAT SIMPLE
# =====================================================================

def chat_simple(message, history=[]):
    """Chat simple sin herramientas"""
    messages = [
        {"role": "system", "content": "Eres un asistente útil y amigable. Respondes en español de forma clara y concisa."}
    ]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": message})
    
    try:
        response = ollama.chat(model=CHAT_MODEL, messages=messages, stream=False)
        return response["message"]["content"]
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =====================================================================
# RAG - DOCUMENTOS
# =====================================================================

def init_chroma():
    """Inicializa ChromaDB"""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=os.path.join(USER_HOME, ".ia-chromadb"))
        collection = client.get_or_create_collection("documentos")
        return client, collection
    except Exception as e:
        st.error(f"Error inicializando ChromaDB: {e}")
        return None, None

def add_document_to_chroma(text, source, collection):
    """Agrega un documento a ChromaDB"""
    try:
        import chromadb
        
        # Dividir en chunks
        chunk_size = 500
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"{source}_{i}"
            
            # Generar embedding
            embedding_response = ollama.embeddings(
                model="nomic-embed-text",
                prompt=chunk
            )
            
            collection.add(
                ids=[chunk_id],
                embeddings=[embedding_response["embedding"]],
                documents=[chunk],
                metadatas=[{"source": source, "chunk": i}]
            )
        
        return len(chunks)
    except Exception as e:
        st.error(f"Error agregando documento: {e}")
        return 0

def rag_query(question, collection):
    """Consulta RAG"""
    try:
        # Generar embedding de la pregunta
        query_embedding = ollama.embeddings(
            model="nomic-embed-text",
            prompt=question
        )["embedding"]
        
        # Buscar en ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=5
        )
        
        if not results["documents"][0]:
            return "No encontré documentos relevantes."
        
        # Construir contexto
        context = "\n\n".join(results["documents"][0])
        
        # Generar respuesta
        messages = [
            {"role": "system", "content": f"Responde basándote en este contexto:\n\n{context}\n\nSi la respuesta no está en el contexto, dilo. Responde en español."},
            {"role": "user", "content": question}
        ]
        
        response = ollama.chat(model=CHAT_MODEL, messages=messages, stream=False)
        return response["message"]["content"]
    except Exception as e:
        return f"❌ Error en RAG: {str(e)}"

# =====================================================================
# ASISTENTE DE CÓDIGO
# =====================================================================

def code_assistant(message, mode="explicar"):
    """Asistente de código"""
    prompts = {
        "explicar": "Explica el siguiente código de forma clara y detallada en español:",
        "mejorar": "Mejora el siguiente código. Devuelve SOLO el código mejorado con comentarios explicativos en español:",
        "corregir": "Corrige los errores del siguiente código. Devuelve el código corregido con comentarios de qué se cambió:",
        "crear": "Crea el código solicitado. Devuelve código limpio, bien comentado y funcional:"
    }
    
    system_prompt = """Eres un programador experto. Cuando escribas código:
1. Siempre incluye comentarios explicativos en español
2. Usa buenas prácticas y patrones modernos
3. Maneja errores apropiadamente
4. El código debe ser funcional y listo para usar
5. Para TypeScript/Next.js: usa tipos apropiados, server components cuando sea posible, y sigue las convenciones de Next.js 14+
6. Responde en español pero el código en inglés (convenciones de programación)
"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{prompts.get(mode, prompts['explicar'])}\n\n{message}"}
    ]
    
    try:
        response = ollama.chat(model=CODE_MODEL, messages=messages, stream=False)
        return response["message"]["content"]
    except Exception as e:
        return f"❌ Error: {str(e)}"

# =====================================================================
# INTERFAZ STREAMLIT
# =====================================================================

def main():
    # Sidebar
    with st.sidebar:
        st.title("🤖 IA Local Pro")
        st.caption("Agente Autónomo con Ejecución de Comandos")
        
        mode = st.radio(
            "Modo",
            ["🚀 Agente Autónomo", "💬 Chat Simple", "📚 RAG Documentos", "💻 Código"],
            index=0
        )
        
        st.divider()
        
        # Modelos
        st.subheader("⚙️ Configuración")
        agente_model = st.selectbox(
            "Modelo Agente",
            ["qwen2.5:14b", "qwen2.5:7b", "llama3.1:8b", "llama3.1:70b"],
            index=0
        )
        
        global AGENT_MODEL
        AGENT_MODEL = agente_model
        
        st.divider()
        
        # Proyectos
        st.subheader("📁 Proyectos")
        if os.path.exists(PROJECTS_DIR):
            proyectos = [d for d in os.listdir(PROJECTS_DIR) if os.path.isdir(os.path.join(PROJECTS_DIR, d))]
            if proyectos:
                selected_project = st.selectbox("Proyecto activo", proyectos)
                st.session_state['active_project'] = os.path.join(PROJECTS_DIR, selected_project)
            else:
                st.info("Clona un repositorio para empezar")
        
        st.divider()
        
        # Herramientas
        st.subheader("🔧 Herramientas")
        with st.expander("Ver herramientas disponibles"):
            for name, info in TOOLS.items():
                st.markdown(f"**{name}**: {info['description']}")
                st.caption(f"Ej: `{info['example']}`")
        
        st.divider()
        
        # Botón de info
        if st.button("📊 Info del Sistema"):
            info = tool_info_sistema()
            st.text(info)
        
        # Limpiar historial
        if st.button("🗑️ Limpiar Historial"):
            st.session_state['history'] = []
            st.rerun()
    
    # Contenido principal
    if "🚀" in mode:
        render_autonomous_agent()
    elif "💬" in mode:
        render_simple_chat()
    elif "📚" in mode:
        render_rag()
    elif "💻" in mode:
        render_code_assistant()

def render_autonomous_agent():
    st.title("🚀 Agente Autónomo Pro")
    st.markdown("Pídele cualquier tarea y el agente la ejecutará usando herramientas reales.")
    
    # Accesos rápidos
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📥 Clonar signalTrade"):
            st.session_state['quick_task'] = "Clona el repositorio https://github.com/yecos/signalTrade.git en mi carpeta de proyectos"
    with col2:
        if st.button("📦 Instalar Deps"):
            project = st.session_state.get('active_project', '')
            if project and os.path.exists(project):
                st.session_state['quick_task'] = f"Instala las dependencias del proyecto en {project}"
            else:
                st.warning("Primero clona un proyecto")
    with col3:
        if st.button("🔍 Analizar Proyecto"):
            project = st.session_state.get('active_project', '')
            if project and os.path.exists(project):
                st.session_state['quick_task'] = f"Analiza la estructura y el código del proyecto en {project}. Lee el package.json, README, y los archivos principales. Dame un resumen completo de qué hace la app y qué tecnologías usa."
            else:
                st.warning("Primero clona un proyecto")
    
    # Inicializar historial
    if 'history' not in st.session_state:
        st.session_state['history'] = []
    
    # Mostrar historial
    for msg in st.session_state['history']:
        if msg["role"] == "user":
            st.chat_message("user").write(msg["content"])
        elif msg["role"] == "assistant":
            st.chat_message("assistant").write(msg["content"])
    
    # Input
    quick_task = st.session_state.pop('quick_task', None)
    prompt = st.chat_input("¿Qué quieres que haga el agente?")
    
    user_input = quick_task or prompt
    
    if user_input:
        st.chat_message("user").write(user_input)
        
        with st.chat_message("assistant"):
            with st.spinner("🤖 Agente trabajando..."):
                response, new_history = run_agent(user_input, st.session_state['history'])
                st.session_state['history'] = new_history
                st.markdown(response)

def render_simple_chat():
    st.title("💬 Chat Simple")
    st.markdown(f"Chat directo con {CHAT_MODEL}")
    
    if 'chat_history' not in st.session_state:
        st.session_state['chat_history'] = []
    
    for msg in st.session_state['chat_history']:
        st.chat_message(msg["role"]).write(msg["content"])
    
    prompt = st.chat_input("Escribe tu mensaje...")
    if prompt:
        st.chat_message("user").write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                response = chat_simple(prompt, st.session_state['chat_history'])
                st.markdown(response)
        
        st.session_state['chat_history'].append({"role": "user", "content": prompt})
        st.session_state['chat_history'].append({"role": "assistant", "content": response})

def render_rag():
    st.title("📚 RAG - Documentos")
    st.markdown("Sube documentos y pregunta sobre su contenido.")
    
    # Inicializar ChromaDB
    client, collection = init_chroma()
    
    if collection:
        # Upload
        uploaded = st.file_uploader("Subir documento", type=["pdf", "txt", "md"])
        if uploaded:
            with st.spinner("Procesando documento..."):
                text = ""
                if uploaded.name.endswith(".pdf"):
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(uploaded)
                        for page in reader.pages:
                            text += page.extract_text() or ""
                    except:
                        st.error("Instala: pip install pypdf")
                else:
                    text = uploaded.getvalue().decode("utf-8", errors="replace")
                
                if text:
                    chunks = add_document_to_chroma(text, uploaded.name, collection)
                    st.success(f"✅ Documento agregado: {uploaded.name} ({chunks} fragmentos)")
        
        # Chat
        if 'rag_history' not in st.session_state:
            st.session_state['rag_history'] = []
        
        for msg in st.session_state['rag_history']:
            st.chat_message(msg["role"]).write(msg["content"])
        
        prompt = st.chat_input("Pregunta sobre tus documentos...")
        if prompt:
            st.chat_message("user").write(prompt)
            with st.chat_message("assistant"):
                response = rag_query(prompt, collection)
                st.markdown(response)
            
            st.session_state['rag_history'].append({"role": "user", "content": prompt})
            st.session_state['rag_history'].append({"role": "assistant", "content": response})

def render_code_assistant():
    st.title("💻 Asistente de Código")
    st.markdown(f"Asistente especializado con {CODE_MODEL}")
    
    mode = st.selectbox("Modo", ["explicar", "mejorar", "corregir", "crear"])
    
    if 'code_history' not in st.session_state:
        st.session_state['code_history'] = []
    
    for msg in st.session_state['code_history']:
        st.chat_message(msg["role"]).write(msg["content"])
    
    prompt = st.chat_input("Pega tu código o describe qué quieres crear...")
    if prompt:
        st.chat_message("user").write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Generando código..."):
                response = code_assistant(prompt, mode)
                st.markdown(response)
        
        st.session_state['code_history'].append({"role": "user", "content": prompt})
        st.session_state['code_history'].append({"role": "assistant", "content": response})

# =====================================================================
# EJECUCIÓN
# =====================================================================

if __name__ == "__main__":
    main()
