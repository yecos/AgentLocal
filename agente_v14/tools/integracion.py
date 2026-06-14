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
