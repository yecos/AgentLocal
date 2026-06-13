# agent.py - Agente Inteligente con Bucle Agéntico (ReAct)
# Este es el CEREBRO del agente. Implementa el patrón:
# PENSAR → ACTUAR → OBSERVAR → repetir hasta tener respuesta sólida.
import ollama
import json
import re
import time
from memory import MemoriaAgente
from tools import TOOL_REGISTRY
from config import Config


class PasoPensamiento:
    """Representa un paso del proceso de pensamiento del agente.
    Se usa para mostrar EN PANTALLA lo que el agente está pensando."""

    def __init__(self, tipo: str, contenido: str, datos: dict = None):
        self.tipo = tipo  # "pensamiento", "accion", "observacion", "respuesta"
        self.contenido = contenido
        self.datos = datos or {}
        self.timestamp = time.strftime("%H:%M:%S")

    def __repr__(self):
        iconos = {
            "pensamiento": "💭",
            "accion": "🔧",
            "observacion": "👁",
            "respuesta": "✅",
            "error": "❌",
        }
        icono = iconos.get(self.tipo, "📌")
        return f"[{self.timestamp}] {icono} {self.tipo.upper()}: {self.contenido[:100]}"


class AgenteInteligente:
    """Agente inteligente con bucle agéntico ReAct (Reason + Act).

    Flujo:
    1. Recibe pregunta del usuario
    2. Busca en memoria si ya sabe la respuesta
    3. Si no sabe, entra en bucle: pensar → actuar → observar
    4. Repite hasta tener respuesta sólida o alcanzar MAX_ITERATIONS
    5. Guarda lo aprendido en memoria
    """

    def __init__(self, model_name=None):
        self.model = model_name or Config.MODEL_NAME
        self.memory = MemoriaAgente(Config.MEMORY_DB)
        self.max_iterations = Config.MAX_ITERATIONS
        self.historial_pasos = []  # Lista de PasoPensamiento para la UI
        self.on_paso = None  # Callback para la UI: on_paso(PasoPensamiento)

        # Construir descripción de herramientas para el prompt
        self.tools_description = self._construir_descripcion_herramientas()

        self.system_prompt = f"""Eres un agente de IA inteligente, autónomo y proactivo. Tu nombre es "Agente Local".

REGLAS FUNDAMENTALES:
1. NUNCA digas "no puedo" sin antes intentar resolver el problema.
2. Si no sabes algo, BUSCA en internet usando buscar_internet.
3. Si la primera solución no funciona, intenta OTRA. Máximo {Config.MAX_ITERATIONS} intentos.
4. Descompón problemas complejos en pasos más pequeños.
5. Piensa paso a paso antes de actuar.
6. Aprende de cada interacción — si encuentras una solución que funciona, recuérdala.
7. Siempre muestra tu razonamiento antes de actuar.

FORMATO DE RAZONAMIENTO (DEBES seguir este formato):
PENSAMIENTO: [qué sé y qué necesito saber]
ACCIÓN: herramienta_name({{"parametro": "valor"}})
OBSERVACIÓN: [resultado de la acción]
PENSAMIENTO: [¿es suficiente o necesito ir más profundo?]
... (repetir hasta tener respuesta sólida)
RESPUESTA FINAL: [tu respuesta al usuario]

HERRAMIENTAS DISPONIBLES:
{self.tools_description}

REGLAS DE HERRAMIENTAS:
- Para buscar en internet: ACCIÓN: buscar_internet({{"query": "tu búsqueda"}})
- Para ejecutar código Python: ACCIÓN: ejecutar_python({{"codigo": "tu código"}})
- Para leer un archivo: ACCIÓN: leer_archivo({{"ruta": "/ruta/al/archivo"}})
- Para escribir un archivo: ACCIÓN: escribir_archivo({{"ruta": "/ruta", "contenido": "texto"}})
- Para listar un directorio: ACCIÓN: listar_directorio({{"ruta": "/ruta"}})

COMIENZA SIEMPRE pensando antes de actuar. NUNCA respondas sin pensar primero.
Si tienes conocimiento previo relevante, úsalo. Si no, busca."""

    def _construir_descripcion_herramientas(self) -> str:
        """Construye la descripción de herramientas para el prompt del sistema."""
        descripciones = []
        for nombre, tool in TOOL_REGISTRY.items():
            params = list(tool["parameters"].get("properties", {}).keys())
            params_str = ", ".join(params)
            descripciones.append(
                f"- {nombre}({params_str}): {tool['description']}"
            )
        return "\n".join(descripciones)

    def _emitir_paso(self, tipo: str, contenido: str, datos: dict = None):
        """Emite un paso de pensamiento. Se usa para mostrar en pantalla
        lo que el agente está pensando/haciendo."""
        paso = PasoPensamiento(tipo, contenido, datos)
        self.historial_pasos.append(paso)
        if self.on_paso:
            self.on_paso(paso)

    def think(self, user_message: str) -> dict:
        """Bucle principal de razonamiento del agente.

        Devuelve un dict con:
        - "respuesta": la respuesta final al usuario
        - "pasos": lista de PasoPensamiento con todo el proceso
        - "iteraciones": cuántas iteraciones tomó
        - "herramientas_usadas": lista de herramientas usadas
        """
        self.historial_pasos = []
        herramientas_usadas = []
        respuesta_final = ""

        # ── 1. Buscar en memoria ────────────────────────────
        self._emitir_paso("pensamiento", "Buscando en memoria conocimiento relevante...")

        if Config.MEMORY_ENABLED:
            memories = self.memory.buscar_relevante(user_message)
            memory_context = ""
            if memories:
                memory_context = "\n\nCONOCIMIENTO PREVIO APRENDIDO:\n"
                for m in memories:
                    memory_context += (
                        f"- P: {m['pregunta']}\n"
                        f"  R: {m['respuesta']}\n"
                        f"  (usado {m['veces_usado']} veces, fuente: {m['fuente']})\n"
                    )
                self._emitir_paso(
                    "observacion",
                    f"Encontré {len(memories)} conocimiento(s) previo(s) relevante(s)",
                    {"memorias": memories},
                )
            else:
                self._emitir_paso("observacion", "No encontré conocimiento previo relevante")
        else:
            memory_context = ""

        # ── 2. Construir mensajes ───────────────────────────
        messages = [
            {"role": "system", "content": self.system_prompt + memory_context},
            {"role": "user", "content": user_message},
        ]

        # ── 3. Bucle agéntico ───────────────────────────────
        for i in range(self.max_iterations):
            self._emitir_paso(
                "pensamiento",
                f"Iteración {i + 1}/{self.max_iterations} — Analizando...",
            )

            # Llamar al modelo
            try:
                response = ollama.chat(
                    model=self.model,
                    messages=messages,
                    options={"temperature": Config.TEMPERATURE},
                )
                text = response["message"]["content"]
            except Exception as e:
                self._emitir_paso("error", f"Error llamando al modelo: {e}")
                respuesta_final = f"Error del modelo: {e}"
                break

            # ── 4. Verificar si quiere usar una herramienta ──
            accion = self._parse_accion(text)

            if accion is None:
                # No hay acción = respuesta final
                # Extraer la respuesta final del texto
                respuesta_final = self._extraer_respuesta_final(text)
                self._emitir_paso("respuesta", respuesta_final)
                break

            # ── 5. Ejecutar herramienta ──────────────────────
            tool_name = accion["tool"]
            tool_params = accion["params"]

            self._emitir_paso(
                "accion",
                f"Ejecutando: {tool_name}({json.dumps(tool_params, ensure_ascii=False)})",
                {"tool": tool_name, "params": tool_params},
            )

            if tool_name in TOOL_REGISTRY:
                try:
                    result = TOOL_REGISTRY[tool_name]["func"](**tool_params)
                    result_str = json.dumps(result, ensure_ascii=False, indent=2)

                    self._emitir_paso(
                        "observacion",
                        f"Resultado de {tool_name}: {result_str[:500]}",
                        {"resultado": result},
                    )

                    herramientas_usadas.append({
                        "tool": tool_name,
                        "params": tool_params,
                        "exito": result.get("exito", False),
                    })

                except Exception as e:
                    result_str = f"Error ejecutando {tool_name}: {e}"
                    self._emitir_paso("error", result_str)
                    herramientas_usadas.append({
                        "tool": tool_name,
                        "params": tool_params,
                        "exito": False,
                        "error": str(e),
                    })

                # Agregar al contexto del modelo
                messages.append({"role": "assistant", "content": text})
                messages.append({
                    "role": "user",
                    "content": (
                        f"OBSERVACIÓN de {tool_name}:\n{result_str}\n\n"
                        f"¿Es suficiente para responder o necesitas "
                        f"buscar/analizar más? Si ya tienes la respuesta, "
                        f"da la RESPUESTA FINAL."
                    ),
                })
            else:
                # Herramienta no existe
                available = list(TOOL_REGISTRY.keys())
                error_msg = (
                    f"La herramienta '{tool_name}' no existe. "
                    f"Herramientas disponibles: {available}"
                )
                self._emitir_paso("error", error_msg)
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": error_msg})

        else:
            # Alcanzó el máximo de iteraciones
            respuesta_final = self._extraer_respuesta_final(text)
            self._emitir_paso(
                "pensamiento",
                f"Alcanzado máximo de iteraciones ({self.max_iterations})",
            )

        # ── 6. Guardar en memoria ───────────────────────────
        if Config.MEMORY_ENABLED and respuesta_final:
            self.memory.guardar_conocimiento(user_message, respuesta_final)

            # Guardar si las soluciones funcionaron
            for h in herramientas_usadas:
                self.memory.guardar_solucion(
                    problema=user_message,
                    solucion=f"{h['tool']}({json.dumps(h['params'], ensure_ascii=False)})",
                    exito=h.get("exito", False),
                    herramienta=h["tool"],
                )

        return {
            "respuesta": respuesta_final,
            "pasos": self.historial_pasos,
            "iteraciones": i + 1 if 'i' in dir() else 0,
            "herramientas_usadas": herramientas_usadas,
        }

    def _parse_accion(self, text: str) -> dict:
        """Extrae una acción del texto del modelo.
        Busca el patrón: ACCIÓN: herramienta({"param": "valor"})"""
        # Patrón 1: ACCIÓN: herramienta({...})
        pattern1 = r"ACCI[ÓO]N:\s*(\w+)\s*\((\{[^}]*\})\)"
        match = re.search(pattern1, text, re.DOTALL)
        if match:
            tool_name = match.group(1)
            try:
                params = json.loads(match.group(2))
                return {"tool": tool_name, "params": params}
            except json.JSONDecodeError:
                pass

        # Patrón 2: Bloque JSON con tool call
        pattern2 = r"```json\s*(\{.*?\})\s*```"
        match = re.search(pattern2, text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if "name" in data or "tool" in data:
                    return {
                        "tool": data.get("name", data.get("tool")),
                        "params": data.get("arguments", data.get("params", {})),
                    }
            except (json.JSONDecodeError, KeyError):
                pass

        # Patrón 3: ACCIÓN: herramienta(parametro="valor")
        pattern3 = r"ACCI[ÓO]N:\s*(\w+)\s*\((.+?)\)\s*$"
        match = re.search(pattern3, text, re.MULTILINE)
        if match:
            tool_name = match.group(1)
            raw_params = match.group(2)
            # Parsear parámetros simples tipo: query="valor"
            params = {}
            for p_match in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', raw_params):
                params[p_match.group(1)] = p_match.group(2)
            for p_match in re.finditer(r"(\w+)\s*=\s*'([^']*)'", raw_params):
                params[p_match.group(1)] = p_match.group(2)
            if params:
                return {"tool": tool_name, "params": params}

        return None

    def _extraer_respuesta_final(self, text: str) -> str:
        """Extrae la respuesta final del texto del modelo."""
        # Buscar "RESPUESTA FINAL:" explícito
        match = re.search(
            r"RESPUESTA FINAL:\s*(.*)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

        # Si no hay marcador, devolver todo el texto limpio
        # Eliminar secciones de pensamiento/acción ya procesadas
        cleaned = re.sub(r"PENSAMIENTO:.*?\n", "", text, flags=re.DOTALL)
        cleaned = re.sub(r"ACCI[ÓO]N:.*?\n", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"OBSERVACI[ÓO]N:.*?\n", "", cleaned, flags=re.DOTALL)
        cleaned = cleaned.strip()

        return cleaned if cleaned else text.strip()

    def obtener_estadisticas(self) -> dict:
        """Devuelve estadísticas del agente y su memoria."""
        return self.memory.estadisticas()
