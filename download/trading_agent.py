"""
Trading AI Agent - Agente de Trading Inteligente
Integracion con signalTrade y Ollama (IA local)

Requisitos:
    pip install streamlit langchain-ollama langchain-community langchain-text-splitters
    pip install chromadb duckduckgo-search

Uso:
    streamlit run trading_agent.py

Modelos Ollama necesarios:
    ollama pull qwen2.5:14b
    ollama pull qwen2.5-coder:7b
    ollama pull nomic-embed-text
"""

import os
import json
import re
from datetime import datetime

import streamlit as st
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS


# ============================================
# CONFIGURACION
# ============================================

AGENT_MODEL = "qwen2.5:14b"
CODE_MODEL = "qwen2.5-coder:7b"
EMBED_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://localhost:11434"
DB_DIR = r"C:\ia-local\trading_db"
SIGNAL_TRADE_PATH = r"C:\ia-local\signalTrade"
USUARIO = os.environ.get("USERNAME", "yecos")

st.set_page_config(page_title="Trading AI", page_icon="📈", layout="wide")


# ============================================
# HERRAMIENTAS
# ============================================

def listar_archivos(ruta):
    """Lista archivos y carpetas de una ruta."""
    try:
        if not os.path.exists(ruta):
            return "La ruta no existe: " + ruta
        items = os.listdir(ruta)
        carpetas = []
        archivos = []
        for item in items:
            ruta_item = os.path.join(ruta, item)
            if os.path.isdir(ruta_item):
                carpetas.append("[DIR]  " + item)
            else:
                archivos.append("[FILE] " + item)
        resultado = ""
        for c in sorted(carpetas):
            resultado += c + "\n"
        for a in sorted(archivos):
            resultado += a + "\n"
        return resultado[:3000] if resultado else "Carpeta vacia"
    except Exception as e:
        return "Error: " + str(e)


def leer_archivo(ruta):
    """Lee el contenido de un archivo de texto o codigo."""
    try:
        if not os.path.exists(ruta):
            return "El archivo no existe: " + ruta
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            contenido = f.read()
        return contenido[:5000]
    except Exception as e:
        return "Error al leer: " + str(e)


def buscar_internet(query):
    """Busca informacion en internet usando DuckDuckGo."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if not results:
                return "No se encontraron resultados para: " + query
            text = ""
            for i, r in enumerate(results, 1):
                title = r.get("title", "Sin titulo")
                body = r.get("body", "Sin descripcion")
                text += str(i) + ". " + title + "\n   " + body + "\n\n"
            return text[:3000]
    except Exception as e:
        return "Error al buscar: " + str(e)


def calcular(expresion):
    """Evalua una expresion matematica de forma segura."""
    try:
        clean = re.sub(r"[^\d\+\-\*\/\.\(\)\s]", "", expresion)
        if not clean.strip():
            return "Error: expresion invalida"
        resultado = eval(clean, {"__builtins__": {}}, {})
        return "Resultado: " + str(resultado)
    except Exception as e:
        return "Error: " + str(e)


def fecha():
    """Retorna la fecha y hora actual."""
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


# Registro de herramientas
TOOLS = {
    "listar_archivos": listar_archivos,
    "leer_archivo": leer_archivo,
    "buscar": buscar_internet,
    "calcular": calcular,
    "fecha": fecha,
}


# ============================================
# PROMPTS DEL AGENTE
# ============================================

TOOLS_DESC = """Eres un agente de trading inteligente con acceso al proyecto signalTrade del usuario.

Herramientas disponibles:
- listar_archivos(ruta): Lista archivos y carpetas. Ej: "C:\\ia-local\\signalTrade"
- leer_archivo(ruta): Lee un archivo de codigo. Ej: "C:\\ia-local\\signalTrade\\main.py"
- buscar(consulta): Busca informacion de mercado en internet. Ej: "precio bitcoin hoy"
- calcular(expr): Calcula una expresion matematica. Ej: "67500*0.5"
- fecha(): Retorna la fecha y hora actual

RUTA DEL PROYECTO signalTrade: """ + SIGNAL_TRADE_PATH + """
Carpeta Descargas: C:\\Users\\""" + USUARIO + """\\Downloads

IMPORTANTE:
- Tu PUEDES leer codigo, acceder a archivos y buscar en internet.
- NUNCA digas que no puedes acceder al codigo - USA las herramientas.
- Responde siempre en espanol.
- Si te preguntan sobre signalTrade, primero lista los archivos y luego lee los relevantes.
"""

PLAN_PROMPT = """{tools_desc}

PREGUNTA DEL USUARIO: {pregunta}

PLANIFICA tu respuesta. Decide que herramientas necesitas usar.
Responde SOLO en JSON (sin markdown, sin acentos en las claves):
{{
    "pensamiento": "tu analisis de la pregunta",
    "necesita_herramientas": true,
    "plan": [
        {{"paso": 1, "herramienta": "nombre_herramienta", "parametro": "valor", "razon": "porque la necesito"}}
    ]
}}

Si NO necesitas herramientas:
{{
    "pensamiento": "puedo responder directamente",
    "necesita_herramientas": false,
    "respuesta_directa": "tu respuesta aqui"
}}"""

REPLAN_PROMPT = """PREGUNTA ORIGINAL: {pregunta}

RESULTADOS OBTENIDOS:
{resultados}

Analiza los resultados. Si tienes toda la informacion necesaria, responde.
Si necesitas mas informacion, indica que pasos adicionales tomar.

Responde SOLO en JSON:
Si tienes toda la info:
{{
    "completado": true,
    "respuesta_final": "respuesta completa al usuario"
}}

Si necesitas mas pasos:
{{
    "completado": false,
    "plan_adicional": [
        {{"paso": 1, "herramienta": "nombre", "parametro": "valor", "razon": "porque"}}
    ]
}}"""


# ============================================
# MODELOS
# ============================================

@st.cache_resource
def get_agent_llm():
    """Retorna el modelo principal del agente de trading."""
    return OllamaLLM(model=AGENT_MODEL, base_url=OLLAMA_URL)


@st.cache_resource
def get_code_llm():
    """Retorna el modelo especializado en codigo."""
    return OllamaLLM(model=CODE_MODEL, base_url=OLLAMA_URL)


@st.cache_resource
def get_embeddings():
    """Retorna el modelo de embeddings para RAG."""
    return OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_URL)


# ============================================
# LOGICA DEL AGENTE
# ============================================

def ejecutar_herramienta(nombre, parametro):
    """Ejecuta una herramienta por nombre con el parametro dado."""
    if nombre not in TOOLS:
        return "Herramienta no encontrada: " + nombre
    try:
        if nombre == "fecha":
            return fecha()
        return TOOLS[nombre](parametro)
    except Exception as e:
        return "Error ejecutando " + nombre + ": " + str(e)


def parsear_json_respuesta(texto):
    """Intenta parsear JSON de la respuesta del LLM, limpiando markdown."""
    texto = texto.strip()
    # Remover bloques de codigo markdown
    if "```" in texto:
        texto = re.sub(r"```\w*\n?", "", texto)
        texto = texto.replace("```", "")
    texto = texto.strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return None


def run_agent(pregunta, llm):
    """
    Ejecuta el agente de trading con planificacion y replanificacion.
    Retorna (respuesta, lista_de_pasos).
    """
    pasos = []

    # --- PASO 1: Planificar ---
    prompt_plan = PLAN_PROMPT.format(tools_desc=TOOLS_DESC, pregunta=pregunta)
    try:
        resp_plan = llm.invoke(prompt_plan)
    except Exception as e:
        return "Error al consultar el modelo: " + str(e), pasos

    plan_data = parsear_json_respuesta(resp_plan)

    if plan_data is None:
        # No se pudo parsear, devolver la respuesta directa
        return resp_plan, pasos

    if not plan_data.get("necesita_herramientas", False):
        respuesta = plan_data.get("respuesta_directa", resp_plan)
        return respuesta, pasos

    # --- PASO 2: Ejecutar herramientas del plan ---
    for step in plan_data.get("plan", []):
        herramienta = step.get("herramienta", "")
        parametro = step.get("parametro", "")
        razon = step.get("razon", "")

        resultado = ejecutar_herramienta(herramienta, parametro)

        pasos.append({
            "herramienta": herramienta,
            "parametro": parametro,
            "razon": razon,
            "resultado": str(resultado)[:1000],
        })

    # --- PASO 3: Replanificar ---
    resultados_texto = "\n".join([
        p["herramienta"] + "(" + p["parametro"][:50] + "): " + p["resultado"]
        for p in pasos
    ])

    prompt_replan = REPLAN_PROMPT.format(
        pregunta=pregunta,
        resultados=resultados_texto,
    )

    try:
        resp_replan = llm.invoke(prompt_replan)
    except Exception:
        # Si falla la replanificacion, generar respuesta con lo que tenemos
        pass
    else:
        replan_data = parsear_json_respuesta(resp_replan)
        if replan_data is not None:
            if replan_data.get("completado", False):
                return replan_data.get("respuesta_final", resp_replan), pasos

            # Ejecutar pasos adicionales
            for step in replan_data.get("plan_adicional", []):
                herramienta = step.get("herramienta", "")
                parametro = step.get("parametro", "")
                razon = step.get("razon", "")

                resultado = ejecutar_herramienta(herramienta, parametro)

                pasos.append({
                    "herramienta": herramienta,
                    "parametro": parametro,
                    "razon": razon,
                    "resultado": str(resultado)[:1000],
                })

    # --- PASO 4: Generar respuesta final ---
    resultados_finales = "\n".join([
        p["herramienta"] + ": " + p["resultado"]
        for p in pasos
    ])

    prompt_final = (
        "Responde en espanol de forma clara y completa.\n\n"
        "PREGUNTA: " + pregunta + "\n\n"
        "INFORMACION RECOPILADA:\n" + resultados_finales + "\n\n"
        "RESPUESTA:"
    )

    try:
        respuesta_final = llm.invoke(prompt_final)
    except Exception as e:
        respuesta_final = "Error al generar respuesta final: " + str(e)

    return respuesta_final, pasos


# ============================================
# INTERFAZ STREAMLIT
# ============================================

def main():
    llm = get_agent_llm()
    code_llm = get_code_llm()
    embeddings = get_embeddings()

    # --- Sidebar ---
    with st.sidebar:
        st.title("📈 Trading AI Agent")
        st.markdown("---")

        modo = st.radio("Modo de operacion:", [
            "🧠 Agente Trading",
            "💻 Codigo signalTrade",
            "📄 RAG sobre codigo",
            "🌐 Analisis de Mercado",
        ])

        if modo == "📄 RAG sobre codigo":
            st.markdown("---")
            if st.button("📥 Indexar codigo signalTrade", use_container_width=True):
                if os.path.exists(SIGNAL_TRADE_PATH):
                    with st.spinner("Indexando archivos del proyecto..."):
                        docs = []
                        for root, dirs, files in os.walk(SIGNAL_TRADE_PATH):
                            # Ignorar carpetas ocultas y __pycache__
                            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                            for fname in files:
                                if fname.endswith((".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg")):
                                    filepath = os.path.join(root, fname)
                                    try:
                                        loader = TextLoader(filepath, encoding="utf-8")
                                        docs.extend(loader.load())
                                    except Exception:
                                        pass

                        if docs:
                            splitter = RecursiveCharacterTextSplitter(
                                chunk_size=500,
                                chunk_overlap=50,
                            )
                            chunks = splitter.split_documents(docs)
                            Chroma.from_documents(
                                chunks,
                                embeddings,
                                persist_directory=DB_DIR,
                            )
                            st.success(str(len(chunks)) + " fragmentos indexados correctamente!")
                        else:
                            st.warning("No se encontraron archivos en " + SIGNAL_TRADE_PATH)
                else:
                    st.error(
                        "No se encontro signalTrade en " + SIGNAL_TRADE_PATH + "\n\n"
                        "Ejecuta primero:\n"
                        "```\n"
                        "cd C:\\ia-local\n"
                        "git clone https://github.com/yecos/signalTrade.git\n"
                        "```"
                    )

        st.markdown("---")
        st.caption("Agente: " + AGENT_MODEL)
        st.caption("Codigo: " + CODE_MODEL)
        st.caption("Embeddings: " + EMBED_MODEL)

        if st.button("🗑️ Limpiar chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # --- Chat principal ---
    st.title(modo)
    st.markdown("Pregunta sobre trading, tu codigo signalTrade, o analisis de mercado.")

    # Inicializar historial de mensajes
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Mostrar historial
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input del usuario
    if prompt := st.chat_input("Escribe tu pregunta sobre trading o signalTrade..."):
        # Mostrar mensaje del usuario
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Generar respuesta segun el modo
        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                respuesta = ""

                if modo == "🧠 Agente Trading":
                    respuesta, pasos = run_agent(prompt, llm)
                    if pasos:
                        with st.expander("🔍 Ver pasos del agente", expanded=False):
                            for i, p in enumerate(pasos, 1):
                                st.write(
                                    "**Paso " + str(i) + ": " + p["herramienta"] + "**"
                                )
                                if p.get("razon"):
                                    st.caption(p["razon"])
                                st.code(p["resultado"][:500], language="text")
                    st.markdown(respuesta)

                elif modo == "💻 Codigo signalTrade":
                    code_prompt = (
                        "Eres un experto en trading algoritmico y programacion Python. "
                        "Responde siempre en espanol.\n"
                        "El usuario tiene un proyecto llamado signalTrade ubicado en: "
                        + SIGNAL_TRADE_PATH + "\n\n"
                        "Pregunta: " + prompt
                    )
                    respuesta = code_llm.invoke(code_prompt)
                    st.markdown(respuesta)

                elif modo == "📄 RAG sobre codigo":
                    try:
                        vectorstore = Chroma(
                            persist_directory=DB_DIR,
                            embedding_function=embeddings,
                        )
                        results = vectorstore.similarity_search(prompt, k=3)
                        if results:
                            contexto = "\n\n---\n\n".join([
                                "Archivo: " + str(d.metadata.get("source", "desconocido"))
                                + "\n" + d.page_content
                                for d in results
                            ])
                            rag_prompt = (
                                "Eres un experto en el proyecto signalTrade. "
                                "Responde en espanol basandote en el codigo proporcionado.\n\n"
                                "CODIGO DE signalTrade:\n" + contexto
                                + "\n\nPREGUNTA: " + prompt
                                + "\n\nRESPUESTA:"
                            )
                            respuesta = llm.invoke(rag_prompt)
                        else:
                            respuesta = "No se encontraron fragmentos relevantes. Intenta indexar el codigo primero."
                    except Exception as e:
                        respuesta = (
                            "Error al consultar la base de datos vectorial.\n\n"
                            "Asegurate de haber indexado el codigo primero (boton en sidebar).\n\n"
                            "Error: " + str(e)
                        )
                    st.markdown(respuesta)

                elif modo == "🌐 Analisis de Mercado":
                    market_prompt = (
                        "Eres un analista de mercados financiero experto. "
                        "Responde en espanol con analisis detallado.\n"
                        "Si necesitas datos actuales, indica que el usuario "
                        "deberia usar el modo Agente Trading para buscar en internet.\n\n"
                        "Pregunta: " + prompt
                    )
                    respuesta, pasos = run_agent(prompt, llm)
                    if pasos:
                        with st.expander("🔍 Fuentes consultadas", expanded=False):
                            for i, p in enumerate(pasos, 1):
                                st.write("**" + p["herramienta"] + "**: " + p["parametro"][:80])
                                st.caption(p["resultado"][:200])
                    st.markdown(respuesta)

        # Guardar respuesta en historial
        st.session_state.messages.append({"role": "assistant", "content": respuesta})


if __name__ == "__main__":
    main()
