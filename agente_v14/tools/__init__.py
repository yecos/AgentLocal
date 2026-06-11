"""
Registro centralizado de herramientas.
El agente importa TOOL_FUNCTIONS y TOOL_SCHEMAS desde aqui.
"""
import json
import os

from .sistema import ejecutar_comando, procesos_activos, matar_proceso
from .archivos import leer_archivo, escribir_archivo, listar_archivos, buscar_en_archivos
from .apps import abrir_aplicacion, abrir_url, buscar_youtube
from .proyecto import analizar_proyecto, clonar_repositorio, instalar_dependencias
from .codigo import generar_codigo
from .web import buscar_web
from .schemas import TOOL_SCHEMAS


def analizar_imagen(ruta: str, pregunta: str = "Describe esta imagen") -> str:
    """Analiza una imagen usando el modelo de vision del LLM."""
    from llm import ollama
    result = ollama.generate_with_image(pregunta, ruta)
    return result


def configurar_perfil(nombre: str = "", rol: str = "", intereses: str = "",
                      idioma: str = "", estilo: str = "") -> str:
    """Configura el perfil del usuario para personalizar las respuestas del agente.
    
    Args:
        nombre: Nombre del usuario
        rol: Rol profesional (ej: desarrollador, arquitecto, estudiante)
        intereses: Intereses principales separados por coma
        idioma: Idioma preferido para respuestas (ej: espanol, ingles)
        estilo: Estilo de respuesta (conciso, detallado, tecnico, simple)
    """
    from config import USER_PROFILE_FILE, logger
    
    # Cargar perfil existente
    profile = {}
    try:
        if os.path.exists(USER_PROFILE_FILE):
            with open(USER_PROFILE_FILE, "r", encoding="utf-8") as f:
                profile = json.load(f)
    except Exception:
        pass
    
    # Actualizar solo los campos proporcionados
    if nombre:
        profile["name"] = nombre
    if rol:
        profile["role"] = rol
    if intereses:
        profile["interests"] = intereses
    if idioma:
        profile["language"] = idioma
    if estilo:
        profile["style"] = estilo
    
    # Guardar perfil
    try:
        with open(USER_PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        logger.info(f"Perfil de usuario actualizado: {list(profile.keys())}")
    except Exception as e:
        return f"ERROR guardando perfil: {e}"
    
    # Formatear resumen
    parts = []
    field_map = {"name": "Nombre", "role": "Rol", "interests": "Intereses", 
                 "language": "Idioma", "style": "Estilo"}
    for key, label in field_map.items():
        if key in profile:
            parts.append(f"  {label}: {profile[key]}")
    
    return f"Perfil configurado:\n" + "\n".join(parts)


def crear_nota(titulo: str, contenido: str) -> str:
    """Crea una nota rapida y la guarda en la memoria del agente.
    
    Args:
        titulo: Titulo de la nota
        contenido: Contenido de la nota
    """
    from config import LEARN_DIR, logger
    from utils.security import sanitize_input
    
    titulo = sanitize_input(titulo)
    
    notes_file = os.path.join(LEARN_DIR, "notes.json")
    notes = []
    try:
        if os.path.exists(notes_file):
            with open(notes_file, "r", encoding="utf-8") as f:
                notes = json.load(f)
    except Exception:
        pass
    
    from datetime import datetime
    note = {
        "id": len(notes) + 1,
        "title": titulo,
        "content": contenido[:1000],
        "created": datetime.now().isoformat(),
    }
    notes.append(note)
    
    try:
        with open(notes_file, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
        logger.info(f"Nota creada: {titulo}")
    except Exception as e:
        return f"ERROR guardando nota: {e}"
    
    return f"Nota creada: '{titulo}' (ID: {note['id']})"


def ver_notas() -> str:
    """Lista todas las notas guardadas."""
    from config import LEARN_DIR
    
    notes_file = os.path.join(LEARN_DIR, "notes.json")
    try:
        if not os.path.exists(notes_file):
            return "No hay notas guardadas."
        with open(notes_file, "r", encoding="utf-8") as f:
            notes = json.load(f)
        if not notes:
            return "No hay notas guardadas."
        result = "NOTAS GUARDADAS:\n"
        for n in notes[-10:]:  # Ultimas 10
            result += f"  [{n.get('id', '?')}] {n.get('title', 'Sin titulo')} - {n.get('content', '')[:80]}\n"
        return result
    except Exception as e:
        return f"ERROR leyendo notas: {e}"


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
    "analizar_imagen": analizar_imagen,
    "configurar_perfil": configurar_perfil,
    "crear_nota": crear_nota,
    "ver_notas": ver_notas,
}
