"""
=============================================================
AGENTE v16 - Sistema de Sub-Agentes con Herramientas Reales
=============================================================
Sub-agentes que ejecutan un mini-ReAct loop con herramientas reales.
Cada sub-agente puede pensar, seleccionar herramientas, ejecutarlas,
observar resultados y decidir su proxima accion.

Flujo:
1. Recibe tarea + contexto + herramientas disponibles
2. LLM analiza la tarea y decide si necesita herramientas
3. Si necesita herramienta: la ejecuta, observa resultado, repite
4. Si no necesita herramienta: genera respuesta final
5. Resultado se guarda en contexto compartido

Mejoras v16 vs v15:
- Sub-agentes ejecutan herramientas REALES (no solo texto)
- Mini-ReAct loop con max iteraciones configurable
- Tool schemas filtrados por tipo de sub-agente
- Observacion de resultados de herramientas
- Rate limiting por sub-agente
- Logging detallado de cada iteracion
=============================================================
"""

import os
import re
import json
import time
import logging
import threading
import concurrent.futures
from datetime import datetime
from config import LEARN_DIR, MAX_TOOL_OUTPUT, logger


# ============================================================
# CONFIGURACION DE SUB-AGENTES
# ============================================================

SUBAGENT_TYPES = {
    "researcher": {
        "description": "Busca y recopila informacion de multiples fuentes",
        "system_prompt": (
            "Eres un agente investigador especializado. Tu trabajo es buscar, "
            "recopilar y sintetizar informacion de multiples fuentes. "
            "Se preciso, cita fuentes, y organiza la informacion de forma clara. "
            "Cuando necesites informacion, USA las herramientas de busqueda. "
            "Responde en espanol."
        ),
        "tools": ["buscar_web", "resumir_url", "scrapear_web", "leer_documento",
                  "leer_archivo", "busqueda_profunda"],
        "max_iterations": 4,
    },
    "coder": {
        "description": "Genera, analiza y modifica codigo",
        "system_prompt": (
            "Eres un agente programador especializado. Tu trabajo es generar, "
            "analizar y modificar codigo. Escribe codigo limpio, documentado y funcional. "
            "Cuando necesites leer archivos, ejecutar codigo o crear proyectos, "
            "USA las herramientas disponibles. Responde en espanol."
        ),
        "tools": ["generar_codigo", "ejecutar_python", "ejecutar_bash",
                  "ejecutar_nodo", "leer_archivo", "escribir_archivo",
                  "listar_archivos", "buscar_en_archivos", "buscar_patron",
                  "editar_multiples"],
        "max_iterations": 4,
    },
    "analyst": {
        "description": "Analiza datos, calcula estadisticas y genera insights",
        "system_prompt": (
            "Eres un agente analista de datos especializado. Tu trabajo es analizar datos, "
            "calcular estadisticas, identificar patrones y generar insights accionables. "
            "Presenta resultados de forma clara con numeros y visualizaciones. "
            "USA las herramientas de datos y visualizacion disponibles. "
            "Responde en espanol."
        ),
        "tools": ["estadisticas", "transformar_datos", "crear_grafico_avanzado",
                  "limpiar_datos", "tabla_pivote", "merge_datos", "parsear_datos",
                  "exportar_datos", "ejecutar_python", "leer_csv", "leer_xlsx"],
        "max_iterations": 4,
    },
    "writer": {
        "description": "Redacta y crea contenido textual y documentos",
        "system_prompt": (
            "Eres un agente escritor especializado. Tu trabajo es redactar contenido "
            "de alta calidad: articulos, resumenes, documentos, correos, etc. "
            "Escribe de forma clara, profesional y bien estructurada. "
            "Si necesitas crear documentos, USA las herramientas de creacion. "
            "Responde en espanol."
        ),
        "tools": ["crear_docx", "crear_pdf", "crear_xlsx", "crear_pptx",
                  "escribir_archivo", "leer_archivo", "buscar_web",
                  "crear_grafico_avanzado"],
        "max_iterations": 3,
    },
    "reviewer": {
        "description": "Revisa y critica resultados de otros agentes",
        "system_prompt": (
            "Eres un agente revisor especializado. Tu trabajo es revisar el trabajo "
            "de otros agentes, identificar errores, inconsistencias o mejoras posibles. "
            "Se constructivo y especifico en tus criticas. "
            "USA las herramientas para verificar hechos y leer archivos. "
            "Responde en espanol."
        ),
        "tools": ["leer_archivo", "buscar_web", "buscar_en_archivos",
                  "buscar_patron", "listar_archivos", "resumir_url"],
        "max_iterations": 3,
    },
    "designer": {
        "description": "Crea visualizaciones, diagramas y contenido grafico",
        "system_prompt": (
            "Eres un agente disenador especializado. Tu trabajo es crear "
            "visualizaciones de datos, diagramas, graficos y contenido visual. "
            "USA las herramientas de visualizacion y diagramas disponibles. "
            "Responde en espanol."
        ),
        "tools": ["crear_grafico_avanzado", "crear_dashboard", "crear_diagrama",
                  "generar_mermaid", "editar_imagen", "generar_imagen"],
        "max_iterations": 3,
    },
    "webdev": {
        "description": "Crea proyectos web y aplicaciones",
        "system_prompt": (
            "Eres un agente desarrollador web especializado. Tu trabajo es crear "
            "proyectos web completos: sitios, aplicaciones, APIs. "
            "USA las herramientas de desarrollo web y codigo disponibles. "
            "Responde en espanol."
        ),
        "tools": ["crear_proyecto_web", "generar_codigo", "escribir_archivo",
                  "leer_archivo", "editar_multiples", "generacion_batch",
                  "ejecutar_bash", "ejecutar_nodo", "listar_archivos"],
        "max_iterations": 4,
    },
    "general": {
        "description": "Agente general para tareas variadas",
        "system_prompt": (
            "Eres un agente general versatil. Puedes realizar cualquier tipo de tarea "
            "usando las herramientas disponibles. Se eficiente y preciso. "
            "USA las herramientas cuando las necesites. "
            "Responde en espanol."
        ),
        "tools": [],  # Todas las herramientas disponibles
        "max_iterations": 4,
    },
}


# ============================================================
# CONTEXTO COMPARTIDO
# ============================================================

class SharedContext:
    """Contexto compartido entre sub-agentes para comunicacion."""

    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def set(self, key: str, value):
        with self._lock:
            self._data[key] = value

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def update(self, data: dict):
        with self._lock:
            self._data.update(data)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)

    def clear(self):
        with self._lock:
            self._data.clear()


# Contexto global compartido
_shared_context = SharedContext()


# ============================================================
# MINI REACT LOOP PARA SUB-AGENTES
# ============================================================

class SubAgentReAct:
    """Motor ReAct mini para sub-agentes con ejecucion real de herramientas."""

    def __init__(self, tipo: str, tarea: str, contexto: str = "",
                 timeout: int = 120, max_iter: int = 4):
        self.tipo = tipo
        self.tarea = tarea
        self.contexto = contexto
        self.timeout = timeout
        self.max_iter = max_iter
        self.config = SUBAGENT_TYPES.get(tipo, SUBAGENT_TYPES["general"])
        self.tool_names = self.config.get("tools", [])
        self.log = []
        self.tool_calls = 0
        self.max_tool_calls = 8  # Limite de llamadas a herramientas por sub-agente

    def run(self) -> str:
        """Ejecuta el mini-ReAct loop del sub-agente."""
        logger.info(f"Sub-agente [{self.tipo}] iniciado: {self.tarea[:80]}...")

        start_time = time.time()

        # Obtener herramientas y schemas disponibles
        tools, schemas = self._get_available_tools()

        if not tools:
            # Sin herramientas: ejecutar como chat simple
            result = self._run_simple_chat()
        else:
            # Con herramientas: ejecutar ReAct loop
            result = self._run_react_loop(tools, schemas)

        elapsed = time.time() - start_time

        # Guardar en contexto compartido
        result_key = f"subagent_{self.tipo}_{int(start_time)}"
        _shared_context.set(result_key, {
            "type": self.tipo,
            "task": self.tarea,
            "result": result[:2000],
            "tool_calls": self.tool_calls,
            "elapsed": elapsed,
            "timestamp": datetime.now().isoformat(),
        })

        logger.info(
            f"Sub-agente [{self.tipo}] completado en {elapsed:.1f}s "
            f"({self.tool_calls} tool calls)"
        )

        return result

    def _get_available_tools(self):
        """Obtiene las herramientas y schemas disponibles para este sub-agente."""
        try:
            from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
        except ImportError:
            return {}, []

        # Si no hay tool_names definidos, usar todas
        if not self.tool_names:
            return dict(TOOL_FUNCTIONS), list(TOOL_SCHEMAS)

        # Filtrar solo las herramientas de este sub-agente
        tools = {}
        schemas = []
        schema_by_name = {
            s.get("function", {}).get("name"): s for s in TOOL_SCHEMAS
        }

        for name in self.tool_names:
            if name in TOOL_FUNCTIONS:
                tools[name] = TOOL_FUNCTIONS[name]
                if name in schema_by_name:
                    schemas.append(schema_by_name[name])

        return tools, schemas

    def _run_simple_chat(self) -> str:
        """Ejecuta el sub-agente como chat simple (sin herramientas)."""
        system_prompt = self.config["system_prompt"]

        user_prompt = f"TAREA: {self.tarea}\n"
        if self.contexto:
            user_prompt += f"\nCONTEXTO:\n{self.contexto[:2000]}\n"
        user_prompt += "\nRealiza la tarea de forma completa y precisa."

        return self._call_llm(system_prompt, user_prompt)

    def _run_react_loop(self, tools: dict, schemas: list) -> str:
        """Ejecuta el mini-ReAct loop con herramientas reales."""
        system_prompt = self._build_system_prompt(tools)

        # Mensajes de la conversacion
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Primer mensaje del usuario
        user_msg = f"TAREA: {self.tarea}\n"
        if self.contexto:
            user_msg += f"\nCONTEXTO PREVIO:\n{self.contexto[:2000]}\n"
        user_msg += "\nRealiza la tarea usando las herramientas disponibles cuando sea necesario."
        messages.append({"role": "user", "content": user_msg})

        # Intentar con function calling nativo primero
        result = self._react_with_native_tools(messages, tools, schemas)
        if result is not None:
            return result

        # Fallback: ReAct con JSON manual
        return self._react_with_json(messages, tools)

    def _react_with_native_tools(self, messages: list, tools: dict, schemas: list) -> str | None:
        """ReAct loop usando function calling nativo de Ollama."""
        try:
            from llm import ollama
        except ImportError:
            return None

        for iteration in range(self.max_iter):
            if self.tool_calls >= self.max_tool_calls:
                logger.debug(f"Sub-agente [{self.tipo}] max tool calls alcanzado")
                break

            try:
                # Llamar al LLM con herramientas
                if hasattr(ollama, '_try_chat_http'):
                    response = self._call_llm_with_tools_http(messages, schemas)
                elif hasattr(ollama, 'generate'):
                    # Usar generate() que soporta tools via HTTP nativo
                    response = ollama.generate(
                        messages=messages,
                        tools=schemas if schemas else None,
                    )
                else:
                    return None

                if not response:
                    break

                # Extraer respuesta y tool calls
                msg = response if isinstance(response, dict) else {}
                content = msg.get("message", {}).get("content", "")
                tool_calls = msg.get("message", {}).get("tool_calls", [])

                if tool_calls:
                    # Ejecutar cada tool call
                    messages.append(msg.get("message", {"role": "assistant"}))

                    for tc in tool_calls:
                        func = tc.get("function", {})
                        tool_name = func.get("name", "")
                        tool_args = func.get("arguments", {})

                        if tool_name in tools:
                            # Ejecutar la herramienta
                            observation = self._execute_tool(tools[tool_name], tool_name, tool_args)
                            messages.append({
                                "role": "tool",
                                "name": tool_name,
                                "content": observation[:MAX_TOOL_OUTPUT],
                            })
                        else:
                            messages.append({
                                "role": "tool",
                                "name": tool_name,
                                "content": f"ERROR: Herramienta '{tool_name}' no disponible.",
                            })

                elif content:
                    # Sin tool calls = respuesta final
                    return content.strip()

            except Exception as e:
                logger.debug(f"Sub-agente [{self.tipo}] error en iteracion {iteration}: {e}")
                break

        # Si llegamos aqui, pedir respuesta final
        messages.append({
            "role": "user",
            "content": "Por favor, proporciona tu respuesta final basada en lo que encontraste."
        })
        return self._call_llm_messages(messages)

    def _react_with_json(self, messages: list, tools: dict) -> str:
        """ReAct loop usando JSON manual (fallback)."""
        tool_list = ", ".join(tools.keys())

        # Agregar instrucciones de formato JSON al system prompt
        json_instructions = (
            f"\n\nHERRAMIENTAS DISPONIBLES: {tool_list}\n\n"
            f"Si necesitas usar una herramienta, responde con JSON:\n"
            f'{{"pensamiento": "tu razonamiento", '
            f'"herramienta": "nombre_herramienta", '
            f'"parametros": {{...}}, '
            f'"respuesta": ""}}\n\n'
            f"Si NO necesitas herramientas, responde con JSON:\n"
            f'{{"pensamiento": "tu razonamiento", '
            f'"herramienta": "", '
            f'"parametros": {{}}, '
            f'"respuesta": "tu respuesta final"}}\n\n'
            f"IMPORTANTE: Responde SIEMPRE en formato JSON valido."
        )

        # Reconstruir mensajes con instrucciones JSON
        json_messages = [{"role": "system", "content": messages[0]["content"] + json_instructions}]
        if len(messages) > 1:
            user_msg = messages[1]["content"]
            json_messages.append({"role": "user", "content": user_msg})

        for iteration in range(self.max_iter):
            if self.tool_calls >= self.max_tool_calls:
                break

            try:
                response_text = self._call_llm_messages(json_messages)
                if not response_text:
                    break

                # Intentar parsear como JSON
                parsed = self._parse_json_response(response_text)

                if not parsed:
                    # No es JSON, tratar como respuesta final
                    return response_text.strip()

                tool_name = parsed.get("herramienta", parsed.get("tool", ""))
                tool_args = parsed.get("parametros", parsed.get("params", {}))
                final_answer = parsed.get("respuesta", parsed.get("answer", ""))

                if final_answer and not tool_name:
                    # Respuesta final sin herramientas
                    return final_answer.strip()

                if tool_name and tool_name in tools:
                    # Ejecutar herramienta
                    observation = self._execute_tool(tools[tool_name], tool_name, tool_args)

                    # Agregar al contexto
                    json_messages.append({
                        "role": "assistant",
                        "content": response_text[:500]
                    })
                    json_messages.append({
                        "role": "user",
                        "content": (
                            f"Resultado de {tool_name}: {observation[:1500]}\n\n"
                            f"Continua con la tarea o proporciona tu respuesta final."
                        )
                    })
                else:
                    # Herramienta no reconocida o respuesta final
                    if final_answer:
                        return final_answer.strip()
                    return response_text.strip()

            except Exception as e:
                logger.debug(f"Sub-agente [{self.tipo}] JSON react error: {e}")
                break

        # Pedir respuesta final
        json_messages.append({
            "role": "user",
            "content": "Proporciona tu respuesta final."
        })
        return self._call_llm_messages(json_messages)

    def _execute_tool(self, func: callable, name: str, args: dict) -> str:
        """Ejecuta una herramienta y retorna el resultado."""
        self.tool_calls += 1
        logger.info(f"Sub-agente [{self.tipo}] ejecutando: {name}({list(args.keys())})")

        try:
            # Sanitizar argumentos
            clean_args = {}
            for k, v in args.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_args[k] = v
                elif isinstance(v, (list, dict)):
                    clean_args[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) and not isinstance(v, str) else str(v)
                else:
                    clean_args[k] = str(v)

            result = func(**clean_args)

            if not isinstance(result, str):
                result = str(result)

            # Truncar si es muy largo
            if len(result) > MAX_TOOL_OUTPUT:
                result = result[:MAX_TOOL_OUTPUT] + "\n... [truncado]"

            self.log.append({
                "iteration": self.tool_calls,
                "tool": name,
                "args": {k: str(v)[:100] for k, v in clean_args.items()},
                "result_length": len(result),
            })

            return result

        except TypeError as e:
            # Intentar con argumentos como strings simples
            try:
                # Si la funcion espera argumentos posicionales
                sig = _get_func_signature(func)
                if sig:
                    positional_args = []
                    for param_name in sig:
                        if param_name in args:
                            positional_args.append(str(args[param_name]))
                    if positional_args:
                        result = func(*positional_args)
                        if not isinstance(result, str):
                            result = str(result)
                        return result[:MAX_TOOL_OUTPUT]
            except Exception:
                pass

            error_msg = f"Error ejecutando {name}: {e}"
            logger.debug(error_msg)
            return error_msg

        except Exception as e:
            error_msg = f"Error ejecutando {name}: {e}"
            logger.error(f"Sub-agente [{self.tipo}] tool error: {e}")
            return error_msg

    def _build_system_prompt(self, tools: dict) -> str:
        """Construye el system prompt del sub-agente con lista de herramientas."""
        base_prompt = self.config["system_prompt"]

        tool_descriptions = []
        for name, func in tools.items():
            doc = func.__doc__ or ""
            first_line = doc.strip().split("\n")[0].strip() if doc else ""
            tool_descriptions.append(f"  - {name}: {first_line}")

        tools_section = (
            f"\n\nHERRAMIENTAS DISPONIBLES ({len(tools)}):\n"
            + "\n".join(tool_descriptions)
            + "\n\nUsa las herramientas cuando las necesites para completar la tarea. "
            "No inventes informacion - busca o lee archivos si necesitas datos reales."
        )

        return base_prompt + tools_section

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Llamada simple al LLM."""
        try:
            from llm import ollama

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            return self._call_llm_messages(messages)

        except Exception as e:
            return f"ERROR: No se pudo ejecutar el sub-agente: {e}"

    def _call_llm_messages(self, messages: list) -> str:
        """Llamada al LLM con mensajes completos."""
        try:
            from llm import ollama

            if hasattr(ollama, 'generate_chat'):
                # generate_chat() es el metodo dedicado para chat con mensajes
                return ollama.generate_chat(messages)
            elif hasattr(ollama, 'generate'):
                # Concatenar mensajes en un solo prompt
                parts = []
                for m in messages:
                    role = m.get("role", "user")
                    content = m.get("content", "")
                    if role == "system":
                        parts.append(f"SISTEMA: {content}")
                    elif role == "user":
                        parts.append(f"USUARIO: {content}")
                    elif role == "assistant":
                        parts.append(f"ASISTENTE: {content}")
                    elif role == "tool":
                        parts.append(f"RESULTADO HERRAMIENTA: {content}")

                return ollama.generate("\n\n".join(parts))

            return "ERROR: No hay metodo de comunicacion con el LLM."

        except ImportError:
            return self._call_llm_cli(messages)
        except Exception as e:
            return f"ERROR LLM: {e}"

    def _call_llm_with_tools_http(self, messages: list, schemas: list) -> dict | None:
        """Llamada al LLM via HTTP con tools (para function calling nativo)."""
        try:
            from llm import ollama
            import httpx

            # Detectar modelo
            model = None
            if hasattr(ollama, '_chat_model'):
                model = ollama._chat_model
            elif hasattr(ollama, 'chat_model'):
                model = ollama.chat_model
            if not model:
                return None

            # Construir payload
            payload = {
                "model": model,
                "messages": messages,
                "tools": schemas,
                "stream": False,
            }

            # Encontrar host
            host = "http://localhost:11434"
            if hasattr(ollama, '_host'):
                host = ollama._host
            elif hasattr(ollama, 'host'):
                host = ollama.host

            response = httpx.post(
                f"{host}/api/chat",
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                return response.json()

        except Exception as e:
            logger.debug(f"HTTP tool calling fallo: {e}")

        return None

    def _call_llm_cli(self, messages: list) -> str:
        """Fallback: LLM via CLI de ollama."""
        import subprocess

        try:
            # Detectar modelo
            result = subprocess.run(
                ['ollama', 'list'], capture_output=True, text=True, timeout=5
            )
            models = result.stdout.strip().split('\n')
            chat_model = None
            for line in models:
                model_name = line.split()[0] if line.strip() else ""
                for pattern in ["qwen", "llama", "mistral", "gemma"]:
                    if pattern in model_name.lower():
                        chat_model = model_name
                        break
                if chat_model:
                    break

            if not chat_model:
                return "ERROR: No se encontro modelo de chat."

            # Concatenar mensajes
            full_prompt = "\n\n".join(
                f"{m.get('role', 'user').upper()}: {m.get('content', '')}"
                for m in messages
            )

            result = subprocess.run(
                ['ollama', 'run', chat_model, full_prompt],
                capture_output=True, text=True, timeout=self.timeout
            )

            if result.returncode == 0:
                return result.stdout.strip()
            return f"ERROR: {result.stderr[:500]}"

        except FileNotFoundError:
            return "ERROR: Ollama no instalado."
        except subprocess.TimeoutExpired:
            return f"ERROR: Timeout de {self.timeout}s."
        except Exception as e:
            return f"ERROR: {e}"

    def _parse_json_response(self, text: str) -> dict | None:
        """Intenta parsear una respuesta JSON del LLM."""
        text = text.strip()

        # Intentar directo
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Buscar JSON en la respuesta
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'\{[^{}]*"herramienta"[^{}]*\}',
            r'\{[^{}]*"tool"[^{}]*\}',
            r'\{.*\}',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    json_str = match.group(1) if '```' in pattern else match.group()
                    result = json.loads(json_str)
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    continue

        return None


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def _get_func_signature(func):
    """Obtiene los nombres de parametros de una funcion."""
    import inspect
    try:
        sig = inspect.signature(func)
        return [
            name for name, param in sig.parameters.items()
            if name not in ('self', 'cls')
        ]
    except (ValueError, TypeError):
        return None


# ============================================================
# API PUBLICA
# ============================================================

def ejecutar_subagente(
    tipo: str,
    tarea: str,
    contexto: str = "",
    timeout: int = 120,
    max_iteraciones: int = None,
) -> str:
    """Ejecuta un sub-agente especializado con herramientas reales.

    El sub-agente ejecuta un mini-ReAct loop: piensa, selecciona
    herramientas, las ejecuta, observa resultados y decide su
    proxima accion hasta completar la tarea.

    Args:
        tipo: Tipo de sub-agente: researcher, coder, analyst, writer, reviewer, designer, webdev, general
        tarea: Descripcion de la tarea a realizar
        contexto: Contexto adicional para el sub-agente (informacion previa)
        timeout: Timeout en segundos (default 120)
        max_iteraciones: Maximo de iteraciones ReAct (default: segun tipo)
    """
    tipo = tipo.lower().strip()
    if tipo not in SUBAGENT_TYPES:
        return (f"ERROR: Tipo de sub-agente '{tipo}' no reconocido.\n"
                f"Tipos disponibles: {', '.join(SUBAGENT_TYPES.keys())}")

    config = SUBAGENT_TYPES[tipo]
    max_iter = max_iteraciones or config["max_iterations"]

    agent = SubAgentReAct(tipo, tarea, contexto, timeout, max_iter)
    return agent.run()


def ejecutar_paralelo(tareas: str, agregar_resultados: bool = True) -> str:
    """Ejecuta multiples sub-agentes en paralelo con herramientas reales.

    Cada sub-agente ejecuta su propio mini-ReAct loop de forma
    independiente y los resultados se sintetizan al final.

    Args:
        tareas: Lista JSON de tareas: [{"tipo": "researcher", "tarea": "..."}, ...]
        agregar_resultados: Si True, agrega y sintetiza todos los resultados
    """
    try:
        task_list = json.loads(tareas)
    except json.JSONDecodeError:
        return "ERROR: Formato de tareas invalido. Usa JSON: [{tipo, tarea}, ...]"

    if not task_list:
        return "ERROR: Lista de tareas vacia."

    if len(task_list) > 8:
        return "ERROR: Maximo 8 sub-agentes en paralelo."

    # Validar tareas
    for t in task_list:
        tipo = t.get("tipo", "general")
        if tipo not in SUBAGENT_TYPES:
            return f"ERROR: Tipo '{tipo}' no reconocido en tarea: {t.get('tarea', '?')}"

    logger.info(f"Ejecutando {len(task_list)} sub-agentes en paralelo...")

    results = {}
    errors = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(task_list), 4)) as executor:
        future_to_task = {}

        for i, task in enumerate(task_list):
            tipo = task.get("tipo", "general")
            tarea = task.get("tarea", task.get("task", ""))
            contexto = task.get("contexto", task.get("context", ""))
            timeout = task.get("timeout", 120)

            future = executor.submit(ejecutar_subagente, tipo, tarea, contexto, timeout)
            future_to_task[future] = (i, tipo, tarea)

        for future in concurrent.futures.as_completed(future_to_task):
            i, tipo, tarea = future_to_task[future]
            try:
                result = future.result(timeout=180)
                results[i] = {
                    "tipo": tipo,
                    "tarea": tarea[:80],
                    "resultado": result,
                }
            except Exception as e:
                errors[i] = {
                    "tipo": tipo,
                    "tarea": tarea[:80],
                    "error": str(e),
                }

    # Construir respuesta
    parts = [f"Sub-agentes ejecutados: {len(results)} exitosos, {len(errors)} errores\n"]

    for i in sorted(results.keys()):
        r = results[i]
        parts.append(f"\n--- Sub-agente [{r['tipo']}] ---")
        parts.append(f"Tarea: {r['tarea']}")
        parts.append(f"Resultado:\n{r['resultado']}")

    if errors:
        parts.append(f"\n--- ERRORES ---")
        for i in sorted(errors.keys()):
            e = errors[i]
            parts.append(f"[{e['tipo']}] {e['tarea']}: {e['error']}")

    # Sintesis final si se solicita
    if agregar_resultados and len(results) > 1:
        synthesis = _synthesize_results(results)
        if synthesis:
            parts.append(f"\n--- SINTESIS ---")
            parts.append(synthesis)

    return "\n".join(parts)


def _synthesize_results(results: dict) -> str:
    """Sintetiza los resultados de multiples sub-agentes."""
    try:
        from llm import ollama

        summaries = []
        for i in sorted(results.keys()):
            r = results[i]
            summaries.append(f"[{r['tipo']}] {r['tarea']}: {r['resultado'][:500]}")

        prompt = (
            "Sintetiza los siguientes resultados de sub-agentes en un resumen "
            "coherente y unificado. Destaca los hallazgos clave, contradicciones, "
            "y conclusiones:\n\n" + "\n\n".join(summaries)
        )

        if hasattr(ollama, 'generate'):
            return ollama.generate(prompt)
        elif hasattr(ollama, 'generate_chat'):
            return ollama.generate_chat(
                messages=[{"role": "user", "content": prompt}]
            )

    except Exception as e:
        logger.debug(f"Sintesis fallo: {e}")

    return ""


# ============================================================
# ORQUESTACION AVANZADA
# ============================================================

def orquestar(tarea_principal: str, estrategia: str = "auto",
              max_subagentes: int = 4) -> str:
    """Orquesta automaticamente sub-agentes para una tarea compleja.
    Divide la tarea, asigna sub-agentes y sintetiza resultados.
    Cada sub-agente ejecuta herramientas reales via mini-ReAct.

    Args:
        tarea_principal: Descripcion de la tarea compleja
        estrategia: Estrategia: auto, secuencial, paralelo, mixto
        max_subagentes: Maximo numero de sub-agentes a usar
    """
    logger.info(f"Orquestando tarea: {tarea_principal[:100]}...")

    # Paso 1: Planificacion
    plan = _plan_task(tarea_principal, max_subagentes)

    if not plan:
        return "ERROR: No se pudo planificar la tarea. Intenta con una descripcion mas especifica."

    # Paso 2: Ejecucion segun estrategia
    if estrategia == "auto":
        has_deps = any(t.get("depende_de") for t in plan)
        estrategia = "secuencial" if has_deps else "paralelo"

    if estrategia == "paralelo":
        result = _execute_parallel(plan, tarea_principal)
    elif estrategia == "secuencial":
        result = _execute_sequential(plan, tarea_principal)
    else:
        result = _execute_mixed(plan, tarea_principal)

    return result


def _plan_task(tarea: str, max_subagentes: int) -> list:
    """Planifica subtareas usando el LLM."""
    try:
        from llm import ollama

        prompt = f"""Divide la siguiente tarea en subtareas para sub-agentes especializados.
Tipos disponibles: {', '.join(SUBAGENT_TYPES.keys())}

TAREA: {tarea}

Responde SOLO con un JSON array, sin markdown, sin explicaciones:
[{{"tipo": "researcher", "tarea": "descripcion de la subtarea", "depende_de": null}},
 ...]

Maximo {max_subagentes} subtareas. Cada subtarea debe ser independiente o tener dependencias claras."""

        if hasattr(ollama, 'generate'):
            response = ollama.generate(prompt)
        elif hasattr(ollama, 'generate_chat'):
            response = ollama.generate_chat(
                messages=[{"role": "user", "content": prompt}]
            )
        else:
            return []

        return _extract_json_list(response)

    except Exception as e:
        logger.error(f"Planificacion fallo: {e}")
        return []


def _execute_parallel(plan: list, tarea_principal: str) -> str:
    tareas_json = json.dumps(plan, ensure_ascii=False)
    return ejecutar_paralelo(tareas_json, agregar_resultados=True)


def _execute_sequential(plan: list, tarea_principal: str) -> str:
    all_results = []
    accumulated_context = ""

    for i, subtask in enumerate(plan):
        tipo = subtask.get("tipo", "general")
        tarea = subtask.get("tarea", "")
        contexto = accumulated_context

        result = ejecutar_subagente(tipo, tarea, contexto)

        all_results.append(f"--- Sub-agente [{tipo}] (paso {i+1}/{len(plan)}) ---\n{result}")
        accumulated_context += f"\n[Paso {i+1}] {tarea[:50]}: {result[:500]}"

    return "\n\n".join(all_results)


def _execute_mixed(plan: list, tarea_principal: str) -> str:
    levels = _group_by_dependency(plan)
    all_results = []
    accumulated_context = ""

    for level, tasks in levels.items():
        if len(tasks) == 1:
            t = tasks[0]
            result = ejecutar_subagente(t["tipo"], t["tarea"], accumulated_context)
            all_results.append(f"--- [{t['tipo']}] (nivel {level}) ---\n{result}")
        else:
            tareas_json = json.dumps(tasks, ensure_ascii=False)
            result = ejecutar_paralelo(tareas_json, agregar_resultados=False)
            all_results.append(f"--- Nivel {level} (paralelo, {len(tasks)} agentes) ---\n{result}")

        accumulated_context += f"\n[Nivel {level}]: {result[:500]}"

    return "\n\n".join(all_results)


def _group_by_dependency(plan: list) -> dict:
    levels = {}
    for i, task in enumerate(plan):
        dep = task.get("depende_de")
        level = 0
        if dep is not None:
            for j, other in enumerate(plan):
                if j == dep or (isinstance(dep, str) and str(j) == dep):
                    level = max(level, 1)
                    break
        levels.setdefault(level, []).append(task)
    return levels


def _extract_json_list(text: str) -> list:
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    patterns = [
        r'```json\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
        r'\[.*\]',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1) if '```' in pattern else match.group())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                continue

    return []


# ============================================================
# UTILIDADES
# ============================================================

def listar_subagentes() -> str:
    """Lista los tipos de sub-agentes disponibles y sus capacidades."""
    parts = [f"Sub-agentes disponibles ({len(SUBAGENT_TYPES)}):\n"]
    for tipo, config in SUBAGENT_TYPES.items():
        parts.append(f"  [{tipo}]")
        parts.append(f"    Descripcion: {config['description']}")
        parts.append(f"    Herramientas: {', '.join(config['tools']) or 'todas'}")
        parts.append(f"    Max iteraciones: {config['max_iterations']}")
        parts.append("")

    return "\n".join(parts)


def ver_contexto_compartido() -> str:
    """Muestra el contenido del contexto compartido entre sub-agentes."""
    ctx = _shared_context.snapshot()
    if not ctx:
        return "Contexto compartido vacio."

    parts = [f"Contexto compartido ({len(ctx)} entradas):\n"]
    for key, value in ctx.items():
        if isinstance(value, dict):
            parts.append(f"  {key}:")
            parts.append(f"    Tipo: {value.get('type', '?')}")
            parts.append(f"    Tarea: {value.get('task', '?')[:80]}")
            parts.append(f"    Tool calls: {value.get('tool_calls', 0)}")
            parts.append(f"    Tiempo: {value.get('elapsed', 0):.1f}s")
        else:
            parts.append(f"  {key}: {str(value)[:100]}")

    return "\n".join(parts)


def limpiar_contexto() -> str:
    """Limpia el contexto compartido."""
    count = len(_shared_context.snapshot())
    _shared_context.clear()
    return f"Contexto compartido limpiado ({count} entradas eliminadas)."
