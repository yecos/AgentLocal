"""
=============================================================================
  IA BRIDGE - Puente entre tu agente local y IA avanzada en la nube
=============================================================================
  Permite que tu agente local (Ollama) consulte con una IA más poderosa
  cuando necesite ayuda con tareas complejas.

  Proveedores soportados:
  - OpenAI (GPT-4, GPT-3.5)
  - Groq (Llama, Mixtral - GRATIS y súper rápido)
  - OpenRouter (acceso a múltiples modelos)
  - Cualquier API compatible con OpenAI

  Configuración:
  1. Obtén una API key del proveedor que elijas
  2. Configúrala en el panel de ajustes de la app
  3. Tu agente podrá usar consultar_experto() automáticamente
=============================================================================
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime

# =====================================================================
# CONFIGURACIÓN DE PROVEEDORES
# =====================================================================

PROVEEDORES = {
    "groq": {
        "nombre": "Groq (GRATIS - Súper rápido)",
        "url_base": "https://api.groq.com/openai/v1",
        "modelos": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it"
        ],
        "modelo_default": "llama-3.3-70b-versatile",
        "como_obtener_key": "https://console.groq.com/keys",
        "gratis": True,
        "descripcion": "Gratis, muy rápido, buenos modelos. Ideal para empezar."
    },
    "openrouter": {
        "nombre": "OpenRouter (Múltiples modelos)",
        "url_base": "https://openrouter.ai/api/v1",
        "modelos": [
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
            "deepseek/deepseek-chat:free",
            "qwen/qwen-2.5-72b-instruct:free",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o"
        ],
        "modelo_default": "meta-llama/llama-3.3-70b-instruct:free",
        "como_obtener_key": "https://openrouter.ai/keys",
        "gratis": True,
        "descripcion": "Acceso a muchos modelos. Tiene opciones gratuitas y de pago."
    },
    "openai": {
        "nombre": "OpenAI (GPT-4)",
        "url_base": "https://api.openai.com/v1",
        "modelos": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo"
        ],
        "modelo_default": "gpt-4o-mini",
        "como_obtener_key": "https://platform.openai.com/api-keys",
        "gratis": False,
        "descripcion": "La IA más conocida. De pago pero muy capaz."
    },
    "deepseek": {
        "nombre": "DeepSeek (Barato y muy bueno)",
        "url_base": "https://api.deepseek.com/v1",
        "modelos": [
            "deepseek-chat",
            "deepseek-reasoner"
        ],
        "modelo_default": "deepseek-chat",
        "como_obtener_key": "https://platform.deepseek.com/api_keys",
        "gratis": False,
        "descripcion": "Muy buen razonamiento a bajo precio. Excelente para código."
    }
}

# =====================================================================
# ARCHIVO DE CONFIGURACIÓN
# =====================================================================

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".ia-local")
CONFIG_FILE = os.path.join(CONFIG_DIR, "bridge_config.json")

def load_config():
    """Carga la configuración del bridge"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    
    return {
        "proveedor": "groq",
        "api_key": "",
        "modelo": "",
        "auto_consultar": True,
        "umbral_confianza": 0.5,
        "contexto_proyecto": "",
        "historial_consultas": []
    }

def save_config(config):
    """Guarda la configuración del bridge"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

# =====================================================================
# API CLIENT (sin dependencias extra - solo urllib)
# =====================================================================

def call_openai_api(url_base, api_key, model, messages, temperature=0.7, max_tokens=2048):
    """
    Llama a una API compatible con OpenAI usando solo urllib.
    No requiere instalar nada extra.
    """
    endpoint = f"{url_base}/chat/completions"
    
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }).encode('utf-8')
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Headers adicionales para OpenRouter
    if "openrouter" in url_base:
        headers["HTTP-Referer"] = "https://ia-local.app"
        headers["X-Title"] = "IA Local Pro - Agente Autónomo"
    
    req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            return {
                "success": True,
                "content": result["choices"][0]["message"]["content"],
                "model": result.get("model", model),
                "usage": result.get("usage", {}),
                "provider": url_base.split("//")[1].split(".")[0]
            }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("error", {}).get("message", error_body[:200])
        except:
            error_msg = error_body[:200]
        return {
            "success": False,
            "error": f"HTTP {e.code}: {error_msg}"
        }
    except urllib.error.URLError as e:
        return {
            "success": False,
            "error": f"Error de conexión: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error inesperado: {str(e)}"
        }

# =====================================================================
# FUNCIONES PRINCIPALES DEL BRIDGE
# =====================================================================

def consultar_experto(pregunta, contexto="", modo="general"):
    """
    Consulta con una IA avanzada en la nube.
    
    Args:
        pregunta: La pregunta o tarea a consultar
        contexto: Información adicional de contexto (código, errores, etc.)
        modo: Tipo de consulta - "general", "codigo", "analisis", "plan"
    
    Returns:
        Respuesta de la IA avanzada
    """
    config = load_config()
    
    if not config.get("api_key"):
        return "❌ No hay API key configurada. Ve a ⚙️ Configuración → IA Bridge en la app para configurar tu proveedor."
    
    proveedor = config.get("proveedor", "groq")
    prov_config = PROVEEDORES.get(proveedor, PROVEEDORES["groq"])
    modelo = config.get("modelo") or prov_config["modelo_default"]
    
    # Construir mensajes según modo
    system_prompts = {
        "general": "Eres un experto consultor de IA. Respondes en español de forma clara y detallada. Cuando te pidan ayuda con código, proporciona soluciones completas y funcionales.",
        "codigo": "Eres un programador experto senior. Proporcionas código limpio, bien estructurado y funcional. Respondes en español pero el código en inglés (convenciones). Incluye comentarios explicativos. Para TypeScript/Next.js usas las mejores prácticas modernas.",
        "analisis": "Eres un analista de software experto. Analizas código, arquitectura y sistemas de forma profunda. Identificas problemas, sugieres mejoras y das recomendaciones concretas. Respondes en español.",
        "plan": "Eres un arquitecto de software experto. Creas planes de implementación detallados, paso a paso. Consideras dependencias, riesgos y alternativas. Respondes en español."
    }
    
    messages = [
        {"role": "system", "content": system_prompts.get(modo, system_prompts["general"])}
    ]
    
    # Agregar contexto del proyecto si existe
    contexto_proyecto = config.get("contexto_proyecto", "")
    if contexto_proyecto:
        messages.append({"role": "system", "content": f"Contexto del proyecto del usuario:\n{contexto_proyecto}"})
    
    # Agregar contexto de la consulta
    if contexto:
        user_content = f"Contexto:\n{contexto}\n\nPregunta: {pregunta}"
    else:
        user_content = pregunta
    
    messages.append({"role": "user", "content": user_content})
    
    # Llamar a la API
    result = call_openai_api(
        url_base=prov_config["url_base"],
        api_key=config["api_key"],
        model=modelo,
        messages=messages,
        temperature=0.7 if modo != "plan" else 0.5,
        max_tokens=4096 if modo == "codigo" else 2048
    )
    
    # Registrar consulta
    consulta_record = {
        "fecha": datetime.now().isoformat(),
        "pregunta": pregunta[:100],
        "modo": modo,
        "exito": result.get("success", False),
        "modelo": modelo,
        "proveedor": proveedor
    }
    config.setdefault("historial_consultas", []).append(consulta_record)
    # Mantener solo últimas 100 consultas
    config["historial_consultas"] = config["historial_consultas"][-100:]
    save_config(config)
    
    if result["success"]:
        return result["content"]
    else:
        return f"❌ Error consultando IA: {result['error']}"

def consultar_con_codigo(pregunta, codigo, lenguaje="typescript"):
    """Consulta con la IA enviando código para analizar/modificar"""
    contexto = f"```{lenguaje}\n{codigo}\n```"
    return consultar_experto(pregunta, contexto=contexto, modo="codigo")

def consultar_plan(tarea, contexto_proyecto=""):
    """Pide a la IA avanzada que cree un plan de implementación"""
    return consultar_experto(tarea, contexto=contexto_proyecto, modo="plan")

def test_connection():
    """Prueba la conexión con el proveedor configurado"""
    config = load_config()
    
    if not config.get("api_key"):
        return False, "No hay API key configurada"
    
    proveedor = config.get("proveedor", "groq")
    prov_config = PROVEEDORES.get(proveedor, PROVEEDORES["groq"])
    modelo = config.get("modelo") or prov_config["modelo_default"]
    
    result = call_openai_api(
        url_base=prov_config["url_base"],
        api_key=config["api_key"],
        model=modelo,
        messages=[
            {"role": "user", "content": "Responde solo: CONEXION_OK"}
        ],
        temperature=0,
        max_tokens=10
    )
    
    if result["success"]:
        return True, f"✅ Conexión exitosa con {prov_config['nombre']} (modelo: {modelo})"
    else:
        return False, f"❌ Error: {result['error']}"

def get_stats():
    """Obtiene estadísticas de uso del bridge"""
    config = load_config()
    historial = config.get("historial_consultas", [])
    
    if not historial:
        return {
            "total_consultas": 0,
            "exitosas": 0,
            "fallidas": 0,
            "proveedor": config.get("proveedor", "No configurado"),
            "modelo": config.get("modelo", "No configurado"),
            "configurado": bool(config.get("api_key"))
        }
    
    exitosas = sum(1 for h in historial if h.get("exito"))
    
    return {
        "total_consultas": len(historial),
        "exitosas": exitosas,
        "fallidas": len(historial) - exitosas,
        "ultima_consulta": historial[-1].get("fecha", "N/A"),
        "proveedor": config.get("proveedor", "No configurado"),
        "modelo": config.get("modelo", "No configurado"),
        "configurado": bool(config.get("api_key"))
    }

# =====================================================================
# EXPORTAR PARA USO EN app_auto_pro.py
# =====================================================================

# Lista de herramientas del bridge para agregar al agente
BRIDGE_TOOLS = {
    "consultar_experto": {
        "description": "Consulta con una IA avanzada en la nube para tareas complejas, razonamiento profundo, o cuando el modelo local no es suficiente.",
        "params": ["pregunta", "modo?"],
        "example": 'consultar_experto("¿Cómo implementar un WebSocket server en Next.js?", "codigo")'
    },
    "consultar_con_codigo": {
        "description": "Envía código a la IA avanzada para analizar, mejorar, corregir o extender.",
        "params": ["pregunta", "codigo", "lenguaje?"],
        "example": 'consultar_con_codigo("Agrega manejo de errores a esta función", "function trade() { ... }", "typescript")'
    },
    "consultar_plan": {
        "description": "Pide a la IA avanzada que cree un plan de implementación detallado para una tarea.",
        "params": ["tarea", "contexto_proyecto?"],
        "example": 'consultar_plan("Agregar sistema de alertas por email al motor de trading")'
    }
}
