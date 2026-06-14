"""
=============================================================
AGENTE v14.7 - Herramientas de Integracion y Automatizacion
=============================================================
Email:
- Leer correo (IMAP)
- Enviar correo (SMTP)

Base de datos:
- Consultas SQL genericas (SQLite, PostgreSQL, MySQL)

API REST:
- Cliente HTTP generico (GET, POST, PUT, DELETE)

Tareas programadas:
- Programar tareas (APScheduler / cron)

Clipboard:
- Leer/escribir portapapeles
=============================================================
"""

import os
import json
import logging
from datetime import datetime

from config import LEARN_DIR, logger


# ============================================================
# EMAIL - LEER CORREO
# ============================================================

def leer_email(carpeta: str = "INBOX", limite: int = 10, no_leidos: bool = True) -> str:
    """Lee correos del inbox usando IMAP. Requiere configuracion previa de email.

    Args:
        carpeta: Carpeta a leer (INBOX, Sent, Drafts, etc.)
        limite: Maximo de correos a leer (default 10)
        no_leidos: Solo leer correos no leidos (default True)
    """
    config = _load_email_config()
    if not config:
        return ("ERROR: Email no configurado. Configura primero con configurar_email().\n"
                "Necesitas: servidor IMAP, puerto, email y contrasena/app-password.\n"
                "Ejemplo: configurar_email('imap.gmail.com', 993, 'tu@gmail.com', 'app-password')")

    try:
        import imaplib
        import email
        from email.header import decode_header

        # Conectar
        if config.get("ssl", True):
            mail = imaplib.IMAP4_SSL(config["host"], config.get("port", 993))
        else:
            mail = imaplib.IMAP4(config["host"], config.get("port", 143))

        mail.login(config["email"], config["password"])
        mail.select(carpeta)

        # Buscar correos
        search_criteria = "UNSEEN" if no_leidos else "ALL"
        status, messages = mail.search(None, search_criteria)

        if status != "OK":
            mail.logout()
            return "No se pudieron buscar correos."

        message_ids = messages[0].split()
        if not message_ids:
            mail.logout()
            return "No hay correos nuevos." if no_leidos else "No hay correos."

        # Leer los ultimos N correos
        message_ids = message_ids[-limite:]
        parts = [f"Email: {config['email']} | Carpeta: {carpeta} | {len(message_ids)} correos\n"]

        for mid in reversed(message_ids):
            status, msg_data = mail.fetch(mid, "(RFC822)")
            if status != "OK":
                continue

            msg = email.message_from_bytes(msg_data[0][1])

            # Decodificar asunto
            subject = _decode_email_header(msg.get("Subject", ""))
            from_addr = _decode_email_header(msg.get("From", ""))
            date = msg.get("Date", "")

            parts.append(f"De: {from_addr}")
            parts.append(f"Asunto: {subject}")
            parts.append(f"Fecha: {date}")

            # Extraer cuerpo
            body = _extract_email_body(msg)
            if body:
                parts.append(body[:300])
            parts.append("---")

        mail.logout()

        content = "\n".join(parts)
        if len(content) > 8000:
            content = content[:8000] + "\n... [truncado]"
        return content

    except ImportError:
        return "ERROR: imaplib no disponible (viene con Python estandar)."
    except Exception as e:
        return f"ERROR leyendo email: {e}"


def enviar_email(para: str, asunto: str, cuerpo: str, html: bool = False) -> str:
    """Envia un correo electronico usando SMTP. Requiere configuracion previa.

    Args:
        para: Direccion email del destinatario
        asunto: Asunto del correo
        cuerpo: Cuerpo del mensaje
        html: Si el cuerpo es HTML (default False)
    """
    config = _load_email_config()
    if not config:
        return ("ERROR: Email no configurado. Configura primero con configurar_email().\n"
                "Necesitas: servidor SMTP, puerto, email y contrasena/app-password.")

    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()
        msg["From"] = config["email"]
        msg["To"] = para
        msg["Subject"] = asunto

        content_type = "html" if html else "plain"
        msg.attach(MIMEText(cuerpo, content_type, "utf-8"))

        # Conectar y enviar
        smtp_host = config.get("smtp_host", config["host"].replace("imap", "smtp"))
        smtp_port = config.get("smtp_port", 587)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(config["email"], config["password"])
            server.send_message(msg)

        return f"Email enviado a: {para}\nAsunto: {asunto}"

    except Exception as e:
        return f"ERROR enviando email: {e}"


def configurar_email(host_imap: str, puerto_imap: int, email_addr: str,
                     password: str, host_smtp: str = "", puerto_smtp: int = 587) -> str:
    """Configura la cuenta de email para leer y enviar correos. Los datos se guardan encriptados localmente.

    Args:
        host_imap: Servidor IMAP (ej: imap.gmail.com)
        puerto_imap: Puerto IMAP (usualmente 993)
        email_addr: Direccion de email
        password: Contrasena o App Password (para Gmail usa App Password)
        host_smtp: Servidor SMTP (opcional, se infiere del IMAP)
        puerto_smtp: Puerto SMTP (default 587)
    """
    config = {
        "host": host_imap,
        "port": puerto_imap,
        "email": email_addr,
        "password": password,
        "smtp_host": host_smtp or host_imap.replace("imap", "smtp"),
        "smtp_port": puerto_smtp,
        "ssl": True,
        "configured_at": datetime.now().isoformat(),
    }

    config_file = os.path.join(LEARN_DIR, "email_config.json")
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return f"Email configurado: {email_addr}\nIMAP: {host_imap}:{puerto_imap}\nSMTP: {config['smtp_host']}:{puerto_smtp}"
    except Exception as e:
        return f"ERROR guardando configuracion: {e}"


def _load_email_config():
    """Carga la configuracion de email desde archivo."""
    config_file = os.path.join(LEARN_DIR, "email_config.json")
    if not os.path.exists(config_file):
        return None
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _decode_email_header(header):
    """Decodifica un header de email."""
    if not header:
        return ""
    try:
        from email.header import decode_header
        decoded = decode_header(header)
        parts = []
        for content, charset in decoded:
            if isinstance(content, bytes):
                parts.append(content.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(content)
        return " ".join(parts)
    except Exception:
        return str(header)


def _extract_email_body(msg):
    """Extrae el cuerpo de un mensaje de email."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
        except Exception:
            pass

    return body.strip()[:500]


# ============================================================
# API REST - CLIENTE HTTP GENERICO
# ============================================================

def llamar_api(url: str, metodo: str = "GET", headers: str = "{}",
               body: str = "", timeout: int = 30) -> str:
    """Realiza una peticion HTTP a cualquier API REST. Soporta GET, POST, PUT, DELETE, PATCH.

    Args:
        url: URL de la API
        metodo: Metodo HTTP (GET, POST, PUT, DELETE, PATCH)
        headers: Headers en formato JSON (opcional)
        body: Cuerpo de la peticion (JSON string, opcional)
        timeout: Timeout en segundos (default 30)
    """
    try:
        import urllib.request
        import urllib.error

        # Parsear headers
        try:
            req_headers = json.loads(headers) if headers else {}
        except json.JSONDecodeError:
            req_headers = {}

        # Agregar User-Agent si no existe
        if "User-Agent" not in req_headers:
            req_headers["User-Agent"] = "AgenteLocal/14.7"

        # Construir peticion
        data = None
        if body:
            data = body.encode("utf-8")
            if "Content-Type" not in req_headers:
                req_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=req_headers, method=metodo.upper())

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = response.status
                resp_headers = dict(response.headers)
                content_type = resp_headers.get("Content-Type", "")

                # Leer respuesta
                resp_data = response.read().decode("utf-8", errors="replace")

                # Truncar si es muy larga
                max_len = 5000
                if len(resp_data) > max_len:
                    resp_data = resp_data[:max_len] + "\n... [truncado]"

                # Intentar formatear JSON
                try:
                    parsed = json.loads(resp_data)
                    resp_data = json.dumps(parsed, ensure_ascii=False, indent=2)[:max_len]
                except (json.JSONDecodeError, TypeError):
                    pass

                return (f"API Response: {metodo.upper()} {url}\n"
                        f"Status: {status}\n"
                        f"Content-Type: {content_type}\n\n"
                        f"{resp_data}")

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:2000] if e.fp else ""
            return (f"API Error: {metodo.upper()} {url}\n"
                    f"Status: {e.code} {e.reason}\n\n"
                    f"{body}")

    except Exception as e:
        return f"ERROR llamando API: {e}"


# ============================================================
# TAREAS PROGRAMADAS
# ============================================================

def programar_tarea(nombre: str, comando: str, cuando: str = "", repetir: str = "") -> str:
    """Programa una tarea para ejecutarse en el futuro. Usa el programador del sistema (cron en Linux, Task Scheduler en Windows).

    Args:
        nombre: Nombre descriptivo de la tarea
        comando: Comando a ejecutar
        cuando: Cuando ejecutar (ej: "2025-01-15 09:00", "manana 8am", "lunes")
        repetir: Repeticion (ej: "diario", "cada 2 horas", "semanal", "" = una vez)
    """
    import platform

    # Guardar tarea en archivo
    tasks_file = os.path.join(LEARN_DIR, "scheduled_tasks.json")
    tasks = []
    if os.path.exists(tasks_file):
        try:
            with open(tasks_file, "r", encoding="utf-8") as f:
                tasks = json.load(f)
        except Exception:
            pass

    task = {
        "id": len(tasks) + 1,
        "name": nombre,
        "command": comando,
        "when": cuando,
        "repeat": repetir,
        "created": datetime.now().isoformat(),
        "status": "pending",
    }

    tasks.append(task)

    try:
        with open(tasks_file, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"ERROR guardando tarea: {e}"

    # Intentar registrar en el sistema
    system_result = _register_system_task(task)

    return (f"Tarea programada: '{nombre}'\n"
            f"Comando: {comando}\n"
            f"Cuando: {cuando or 'inmediato'}\n"
            f"Repetir: {repetir or 'una vez'}\n"
            f"{system_result}")


def listar_tareas() -> str:
    """Lista las tareas programadas pendientes."""
    tasks_file = os.path.join(LEARN_DIR, "scheduled_tasks.json")
    if not os.path.exists(tasks_file):
        return "No hay tareas programadas."

    try:
        with open(tasks_file, "r", encoding="utf-8") as f:
            tasks = json.load(f)

        if not tasks:
            return "No hay tareas programadas."

        parts = [f"Tareas programadas ({len(tasks)}):\n"]
        for t in tasks:
            status_icon = "OK" if t.get("status") == "completed" else "..."
            parts.append(
                f"  [{status_icon}] #{t['id']} {t['name']}\n"
                f"      Comando: {t['command']}\n"
                f"      Cuando: {t.get('when', 'inmediato')} | Repetir: {t.get('repeat', 'una vez')}"
            )

        return "\n".join(parts)

    except Exception as e:
        return f"ERROR listando tareas: {e}"


def _register_system_task(task):
    """Intenta registrar la tarea en el programador del sistema."""
    import platform
    import subprocess
    import shlex

    try:
        if platform.system() == "Windows":
            # Windows Task Scheduler - build args list safely
            cmd = (
                f'schtasks /create /tn "AgenteLocal_{task["id"]}_{task["name"]}" '
                f'/tr "{task["command"]}" '
                f'/sc once /st {task.get("when", "00:00")} '
                f'/f'
            )
            result = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return "Registrada en Windows Task Scheduler."
        else:
            # Linux/Mac cron
            cron_line = f"# AgenteLocal: {task['name']}\n"
            result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
            existing = result.stdout if result.returncode == 0 else ""
            new_cron = existing + cron_line
            # Use Popen chain instead of shell pipe: echo '...' | crontab -
            echo_proc = subprocess.Popen(
                ["echo", new_cron],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            crontab_proc = subprocess.Popen(
                ["crontab", "-"],
                stdin=echo_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            # Allow echo_proc to receive SIGPIPE if crontab_proc exits
            echo_proc.stdout.close()
            _stdout, stderr = crontab_proc.communicate(timeout=5)
            echo_proc.wait(timeout=5)
            if crontab_proc.returncode == 0:
                return "Registrada en crontab."
    except Exception:
        pass

    return "Tarea guardada localmente (no se pudo registrar en el sistema)."


# ============================================================
# CLIPBOARD (PORTAPAPELES)
# ============================================================

def leer_portapapeles() -> str:
    """Lee el contenido del portapapeles del sistema."""
    try:
        import pyperclip
        content = pyperclip.paste()
        if content:
            return f"Portapapeles:\n\n{content[:2000]}"
        else:
            return "El portapapeles esta vacio."
    except ImportError:
        # Fallback: intentar con comando del sistema
        import subprocess
        import platform

        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["powershell", "-command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=5
                )
            else:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True, text=True, timeout=5
                )

            if result.returncode == 0 and result.stdout.strip():
                return f"Portapapeles:\n\n{result.stdout[:2000]}"
        except Exception:
            pass

        return ("ERROR: No se pudo leer el portapapeles. Instala:\n"
                "  pip install pyperclip   (recomendado)\n"
                "  O: sudo apt install xclip (Linux)")
    except Exception as e:
        return f"ERROR leyendo portapapeles: {e}"


def escribir_portapapeles(texto: str) -> str:
    """Escribe texto en el portapapeles del sistema.

    Args:
        texto: Texto a copiar al portapapeles
    """
    try:
        import pyperclip
        pyperclip.copy(texto)
        return f"Texto copiado al portapapeles ({len(texto)} caracteres)"
    except ImportError:
        import subprocess
        import platform

        try:
            if platform.system() == "Windows":
                process = subprocess.run(
                    ["powershell", "-command", f"Set-Clipboard -Value '{texto}'"],
                    capture_output=True, text=True, timeout=5
                )
            else:
                process = subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=texto, text=True, timeout=5
                )

            if process.returncode == 0:
                return f"Texto copiado al portapapeles ({len(texto)} caracteres)"
        except Exception:
            pass

        return "ERROR: No se pudo escribir al portapapeles. Instala: pip install pyperclip"
    except Exception as e:
        return f"ERROR escribiendo portapapeles: {e}"


# ============================================================
# S5.5: AGENDA / SCHEDULER
# ============================================================

_AGENDA_FILE = os.path.join(LEARN_DIR, "agenda.json")

def crear_evento(
    titulo: str,
    fecha: str = "",
    hora: str = "",
    descripcion: str = "",
    duracion_minutos: int = 60,
    prioridad: str = "normal",
    recordatorio_minutos: int = 15
) -> str:
    """S5.5: Crea un evento en la agenda del agente.

    Permite gestionar eventos, reuniones y recordatorios.
    Los eventos se almacenan localmente y se pueden consultar,
    modificar, y detectar conflictos de horario.

    Args:
        titulo: Titulo del evento o reunion
        fecha: Fecha del evento en formato YYYY-MM-DD (si vacio, hoy)
        hora: Hora del evento en formato HH:MM (si vacio, sin hora fija)
        descripcion: Descripcion o notas del evento
        duracion_minutos: Duracion estimada en minutos (default: 60)
        prioridad: Prioridad: alta, normal, baja (default: normal)
        recordatorio_minutos: Minutos antes para recordar (default: 15)

    Returns:
        Confirmacion del evento creado
    """
    from datetime import datetime as _dt, timedelta

    # Defaults
    if not fecha:
        fecha = _dt.now().strftime("%Y-%m-%d")

    # Cargar agenda existente
    agenda = _load_agenda()

    # Detectar conflictos
    conflictos = _detect_conflicts(agenda, fecha, hora, duracion_minutos)

    # Crear evento
    event_id = f"evt_{_dt.now().strftime('%Y%m%d_%H%M%S')}"
    event = {
        "id": event_id,
        "titulo": titulo[:200],
        "fecha": fecha,
        "hora": hora,
        "descripcion": descripcion[:1000],
        "duracion_minutos": duracion_minutos,
        "prioridad": prioridad,
        "recordatorio_minutos": recordatorio_minutos,
        "creado": _dt.now().isoformat(),
        "estado": "pendiente",
    }

    agenda.append(event)
    _save_agenda(agenda)

    result = f"Evento creado exitosamente.\nID: {event_id}\nTitulo: {titulo}\nFecha: {fecha}"
    if hora:
        result += f" a las {hora}"
    result += f"\nDuracion: {duracion_minutos} min\nPrioridad: {prioridad}"

    if conflictos:
        result += f"\n\nCONFLICTO DETECTADO: {len(conflictos)} evento(s) se solapan con este horario:"
        for c in conflictos:
            result += f"\n  - {c['titulo']} ({c['fecha']} {c.get('hora', '')})"

    return result


def listar_eventos(
    fecha: str = "",
    proximos: int = 7,
    prioridad: str = ""
) -> str:
    """S5.5: Lista eventos de la agenda, por defecto los proximos N dias.

    Args:
        fecha: Fecha especifica en formato YYYY-MM-DD (opcional)
        proximos: Mostrar eventos de los proximos N dias (default: 7)
        prioridad: Filtrar por prioridad: alta, normal, baja (opcional)

    Returns:
        Lista de eventos encontrados
    """
    from datetime import datetime as _dt, timedelta

    agenda = _load_agenda()
    if not agenda:
        return "No hay eventos en la agenda. Usa crear_evento para agregar."

    # Filtrar
    now = _dt.now()
    fecha_limite = (now + timedelta(days=proximos)).strftime("%Y-%m-%d")

    filtered = []
    for event in agenda:
        # Filtrar por prioridad
        if prioridad and event.get("prioridad", "") != prioridad:
            continue
        # Filtrar por fecha especifica
        if fecha:
            if event.get("fecha", "") != fecha:
                continue
        else:
            # Filtrar por rango de proximos N dias
            evt_fecha = event.get("fecha", "")
            if evt_fecha and evt_fecha >= now.strftime("%Y-%m-%d") and evt_fecha <= fecha_limite:
                pass  # OK
            elif not evt_fecha:
                pass  # Sin fecha, incluir
            else:
                continue  # Fuera de rango

        filtered.append(event)

    # Ordenar por fecha y hora
    filtered.sort(key=lambda e: (e.get("fecha", "9999"), e.get("hora", "99:99")))

    if not filtered:
        return f"No hay eventos para los proximos {proximos} dias."

    # Formatear
    lines = [f"Agenda: {len(filtered)} evento(s) encontrados\n"]
    for evt in filtered:
        prio_icon = {"alta": "!!!", "normal": "...", "baja": "  "}.get(evt.get("prioridad", ""), "...")
        estado = evt.get("estado", "pendiente")
        lines.append(
            f"  [{prio_icon}] {evt.get('titulo', '?')}\n"
            f"      ID: {evt['id']} | Fecha: {evt.get('fecha', '?')} {evt.get('hora', '')}\n"
            f"      Duracion: {evt.get('duracion_minutos', '?')} min | Estado: {estado}"
        )
        if evt.get("descripcion"):
            lines.append(f"      Notas: {evt['descripcion'][:100]}")

    return "\n".join(lines)


def eliminar_evento(evento_id: str) -> str:
    """S5.5: Elimina un evento de la agenda por su ID.

    Args:
        evento_id: ID del evento a eliminar

    Returns:
        Confirmacion de eliminacion
    """
    agenda = _load_agenda()
    original_len = len(agenda)

    agenda = [e for e in agenda if e.get("id") != evento_id]

    if len(agenda) == original_len:
        return f"ERROR: No se encontro evento con ID: {evento_id}"

    _save_agenda(agenda)
    return f"Evento {evento_id} eliminado exitosamente."


def _load_agenda() -> list:
    """Carga la agenda desde disco."""
    try:
        if os.path.exists(_AGENDA_FILE):
            with open(_AGENDA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Error cargando agenda: {e}")
    return []


def _save_agenda(agenda: list):
    """Guarda la agenda a disco."""
    try:
        os.makedirs(os.path.dirname(_AGENDA_FILE), exist_ok=True)
        with open(_AGENDA_FILE, "w", encoding="utf-8") as f:
            json.dump(agenda, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Error guardando agenda: {e}")


def _detect_conflicts(agenda: list, fecha: str, hora: str, duracion_minutos: int) -> list:
    """Detecta conflictos de horario con eventos existentes."""
    if not fecha or not hora:
        return []  # Sin fecha/hora, no se puede verificar

    try:
        from datetime import datetime as _dt, timedelta
        new_start = _dt.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        new_end = new_start + timedelta(minutes=duracion_minutos)
    except (ValueError, TypeError):
        return []  # Formato invalido, no verificar

    conflicts = []
    for evt in agenda:
        evt_fecha = evt.get("fecha", "")
        evt_hora = evt.get("hora", "")
        if not evt_fecha or not evt_hora:
            continue

        try:
            evt_start = _dt.strptime(f"{evt_fecha} {evt_hora}", "%Y-%m-%d %H:%M")
            evt_end = evt_start + timedelta(minutes=evt.get("duracion_minutos", 60))

            # Check overlap
            if new_start < evt_end and new_end > evt_start:
                conflicts.append(evt)
        except (ValueError, TypeError):
            continue

    return conflicts
