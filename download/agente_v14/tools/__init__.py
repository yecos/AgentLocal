"""
Registro centralizado de herramientas.
El agente importa TOOL_FUNCTIONS y TOOL_SCHEMAS desde aqui.
"""
from .sistema import ejecutar_comando, procesos_activos, matar_proceso
from .archivos import leer_archivo, escribir_archivo, listar_archivos, buscar_en_archivos
from .apps import abrir_aplicacion, abrir_url, buscar_youtube
from .proyecto import analizar_proyecto, clonar_repositorio, instalar_dependencias
from .codigo import generar_codigo
from .web import buscar_web
from .schemas import TOOL_SCHEMAS

TOOL_FUNCTIONS = {
    "ejecutar_comando": ejecutar_comando,
    "abrir_aplicacion": abrir_aplicacion,
    "abrir_url": abrir_url,
    "buscar_youtube": buscar_youtube,
    "generar_codigo": generar_codigo,
    "leer_archivo": leer_archivo,
    "escribir_archivo": escribir_archivo,
    "listar_archivos": listar_archivos,
    "analizar_proyecto": analizar_proyecto,
    "clonar_repositorio": clonar_repositorio,
    "instalar_dependencias": instalar_dependencias,
    "buscar_en_archivos": buscar_en_archivos,
    "procesos_activos": procesos_activos,
    "matar_proceso": matar_proceso,
    "buscar_web": buscar_web,
}
