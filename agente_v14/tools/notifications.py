"""
=============================================================
AGENTE v23 - Notifications Framework
=============================================================
Sistema de notificaciones multi-canal para el agente:
- In-app notifications (stored in JSON, shown in Streamlit)
- Email notifications (SMTP, with templates)
- Webhook notifications (HTTP POST to external services)
- Desktop notifications (OS-level via subprocess)
- Notification rules: when/what/how to notify
- Rate limiting: avoid notification spam
- Priority levels: low, medium, high, critical
- Notification history and status tracking

v23: Primera implementacion - multi-channel notifications
     + rules engine + rate limiting + priority system
=============================================================
"""

import os
import json
import time
import uuid
import hashlib
import hmac as hmac_module
import threading
import subprocess
import platform
import smtplib
import logging
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from tools.registry import register_tool
from config import logger

# ============================================================
# CONFIGURACION
# ============================================================

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.normpath(os.path.join(_AGENT_DIR, "..", "data"))
_NOTIFICATIONS_FILE = os.path.join(_DATA_DIR, "notifications.json")

# Credenciales para SMTP
_CREDENTIALS_DIR = os.path.normpath(os.path.join(_AGENT_DIR, "..", "credentials"))
_CREDENTIALS_FILE = os.path.join(_CREDENTIALS_DIR, "api_keys.json")

# Rate limiting defaults
_MAX_PER_CHANNEL_PER_MINUTE = 10
_MAX_BURST_PER_10_SECONDS = 3

# Retencion de notificaciones (dias)
_DEFAULT_RETENTION_DAYS = 30

# Prioridades validas
VALID_PRIORITIES = ("low", "medium", "high", "critical")

# Canales validos
VALID_CHANNELS = ("in_app", "email", "webhook", "desktop")

# Categorias por defecto
VALID_CATEGORIES = ("general", "task", "error", "scheduler", "deployment", "security", "system")


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class Notification:
    """Representa una notificacion del sistema.

    Attributes:
        id: Identificador unico de la notificacion
        title: Titulo corto de la notificacion
        message: Mensaje descriptivo
        channel: Canal por el que se envio (in_app, email, webhook, desktop)
        priority: Nivel de prioridad (low, medium, high, critical)
        category: Categoria de la notificacion
        created_at: Timestamp de creacion (ISO format)
        read: Si la notificacion fue leida
        dismissed: Si la notificacion fue descartada
    """
    id: str = ""
    title: str = ""
    message: str = ""
    channel: str = "in_app"
    priority: str = "medium"
    category: str = "general"
    created_at: str = ""
    read: bool = False
    dismissed: bool = False

    def __post_init__(self):
        """Genera ID y timestamp si no se proporcionan."""
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """Serializa la notificacion a diccionario.

        Returns:
            Dict con todos los campos de la notificacion
        """
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "channel": self.channel,
            "priority": self.priority,
            "category": self.category,
            "created_at": self.created_at,
            "read": self.read,
            "dismissed": self.dismissed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Notification":
        """Deserializa una notificacion desde diccionario.

        Args:
            data: Diccionario con campos de la notificacion

        Returns:
            Nueva instancia de Notification
        """
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            message=data.get("message", ""),
            channel=data.get("channel", "in_app"),
            priority=data.get("priority", "medium"),
            category=data.get("category", "general"),
            created_at=data.get("created_at", ""),
            read=data.get("read", False),
            dismissed=data.get("dismissed", False),
        )


@dataclass
class NotificationRule:
    """Regla que define cuando y como notificar.

    Attributes:
        rule_id: Identificador unico de la regla
        name: Nombre descriptivo de la regla
        condition: Condicion que dispara la regla (callable o dict con event_type + params)
        channel: Canal por el que enviar la notificacion
        priority: Prioridad de la notificacion resultante
        enabled: Si la regla esta activa
    """
    rule_id: str = ""
    name: str = ""
    condition: object = None  # callable or dict
    channel: str = "in_app"
    priority: str = "medium"
    enabled: bool = True

    def __post_init__(self):
        """Genera ID si no se proporciona."""
        if not self.rule_id:
            self.rule_id = str(uuid.uuid4())[:8]

    def to_dict(self) -> dict:
        """Serializa la regla a diccionario.

        Nota: las condiciones callable no se pueden serializar,
        se guardan como dict con event_type si es posible.

        Returns:
            Dict con campos de la regla (sin condition callable)
        """
        cond_data = self.condition
        if callable(self.condition):
            cond_data = {"type": "callable", "note": "No serializable"}
        elif isinstance(self.condition, dict):
            cond_data = self.condition
        else:
            cond_data = {"type": "unknown"}

        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "condition": cond_data,
            "channel": self.channel,
            "priority": self.priority,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationRule":
        """Deserializa una regla desde diccionario.

        Args:
            data: Diccionario con campos de la regla

        Returns:
            Nueva instancia de NotificationRule
        """
        return cls(
            rule_id=data.get("rule_id", ""),
            name=data.get("name", ""),
            condition=data.get("condition"),
            channel=data.get("channel", "in_app"),
            priority=data.get("priority", "medium"),
            enabled=data.get("enabled", True),
        )

    def evaluate(self, event_type: str, context: dict) -> bool:
        """Evalua si la regla aplica a un evento.

        Args:
            event_type: Tipo de evento (task_failure, scheduler_trigger, etc.)
            context: Contexto del evento con datos adicionales

        Returns:
            True si la regla aplica al evento
        """
        if not self.enabled:
            return False

        # Si condition es callable, ejecutarla
        if callable(self.condition):
            try:
                return self.condition(event_type, context)
            except Exception as e:
                logger.debug(f"[Notifications] Error evaluando regla callable '{self.name}': {e}")
                return False

        # Si condition es dict, comparar por event_type y parametros
        if isinstance(self.condition, dict):
            cond_type = self.condition.get("event_type", "")
            if cond_type and cond_type != event_type:
                return False

            # Verificar parametros adicionales en el contexto
            params = self.condition.get("params", {})
            for key, value in params.items():
                if key in context:
                    if isinstance(value, (int, float)) and isinstance(context[key], (int, float)):
                        if context[key] > value:
                            continue
                        else:
                            return False
                    elif str(context.get(key)) != str(value):
                        return False
                # Si el key no esta en context, no aplica
                else:
                    return False
            return True

        return False


# ============================================================
# NOTIFICATION STORE
# ============================================================

class NotificationStore:
    """Almacen persistente de notificaciones en JSON.

    Thread-safe con Lock. Soporta CRUD, limpieza por retencion,
    y consultas por categoria, estado de lectura, etc.
    """

    def __init__(self, filepath: str = None):
        """Inicializa el store.

        Args:
            filepath: Ruta al archivo JSON de persistencia.
                      Por defecto usa data/notifications.json
        """
        self._file = filepath or _NOTIFICATIONS_FILE
        self._lock = threading.Lock()
        self._notifications: list[dict] = []
        self._rules: list[dict] = []
        self._rate_limits: dict = {}
        self._load()

    def _load(self) -> None:
        """Carga las notificaciones desde el archivo JSON."""
        if not os.path.exists(self._file):
            self._notifications = []
            self._rules = []
            self._rate_limits = {}
            return

        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._notifications = data.get("notifications", [])
            self._rules = data.get("rules", [])
            self._rate_limits = data.get("rate_limits", {})
            logger.debug(f"[NotificationStore] Cargadas {len(self._notifications)} notificaciones")
        except Exception as e:
            logger.warning(f"[NotificationStore] Error cargando notificaciones: {e}")
            self._notifications = []
            self._rules = []
            self._rate_limits = {}

    def _save(self) -> None:
        """Guarda las notificaciones al archivo JSON."""
        try:
            os.makedirs(os.path.dirname(self._file), exist_ok=True)
            data = {
                "notifications": self._notifications,
                "rules": self._rules,
                "rate_limits": self._rate_limits,
            }
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[NotificationStore] Error guardando notificaciones: {e}")

    def add(self, notification: Notification) -> str:
        """Agrega una notificacion al store.

        Args:
            notification: Objeto Notification a agregar

        Returns:
            ID de la notificacion creada
        """
        with self._lock:
            self._notifications.append(notification.to_dict())
            self._save()
        return notification.id

    def get(self, notification_id: str) -> Optional[Notification]:
        """Obtiene una notificacion por ID.

        Args:
            notification_id: ID de la notificacion

        Returns:
            Notification o None si no existe
        """
        with self._lock:
            for n in self._notifications:
                if n.get("id") == notification_id:
                    return Notification.from_dict(n)
        return None

    def mark_read(self, notification_id: str) -> bool:
        """Marca una notificacion como leida.

        Args:
            notification_id: ID de la notificacion

        Returns:
            True si se encontro y marco, False si no existe
        """
        with self._lock:
            for n in self._notifications:
                if n.get("id") == notification_id:
                    n["read"] = True
                    self._save()
                    return True
        return False

    def dismiss(self, notification_id: str) -> bool:
        """Descarta una notificacion.

        Args:
            notification_id: ID de la notificacion

        Returns:
            True si se encontro y descarto, False si no existe
        """
        with self._lock:
            for n in self._notifications:
                if n.get("id") == notification_id:
                    n["dismissed"] = True
                    n["read"] = True
                    self._save()
                    return True
        return False

    def get_unread(self) -> list[Notification]:
        """Obtiene todas las notificaciones no leidas.

        Returns:
            Lista de Notification no leidas y no descartadas
        """
        with self._lock:
            result = []
            for n in self._notifications:
                if not n.get("read") and not n.get("dismissed"):
                    result.append(Notification.from_dict(n))
            return result

    def get_by_category(self, category: str) -> list[Notification]:
        """Obtiene notificaciones por categoria.

        Args:
            category: Categoria a filtrar

        Returns:
            Lista de Notification de la categoria especificada
        """
        with self._lock:
            result = []
            for n in self._notifications:
                if n.get("category") == category and not n.get("dismissed"):
                    result.append(Notification.from_dict(n))
            return result

    def get_history(self, limit: int = 50) -> list[Notification]:
        """Obtiene el historial de notificaciones.

        Args:
            limit: Maximo de notificaciones a retornar

        Returns:
            Lista de Notification ordenadas por fecha (mas recientes primero)
        """
        with self._lock:
            result = [Notification.from_dict(n) for n in self._notifications if not n.get("dismissed")]
            # Ordenar por fecha descendente
            result.sort(key=lambda n: n.created_at, reverse=True)
            return result[:limit]

    def cleanup(self, retention_days: int = None) -> int:
        """Elimina notificaciones antiguas.

        Args:
            retention_days: Dias de retencion. Por defecto usa _DEFAULT_RETENTION_DAYS

        Returns:
            Numero de notificaciones eliminadas
        """
        days = retention_days or _DEFAULT_RETENTION_DAYS
        cutoff = datetime.now().timestamp() - (days * 86400)

        with self._lock:
            original_count = len(self._notifications)
            self._notifications = [
                n for n in self._notifications
                if self._parse_timestamp(n.get("created_at", "")) > cutoff or not n.get("dismissed")
            ]
            removed = original_count - len(self._notifications)
            if removed > 0:
                self._save()
                logger.info(f"[NotificationStore] Cleanup: {removed} notificaciones eliminadas (retencion: {days} dias)")
            return removed

    def _parse_timestamp(self, iso_str: str) -> float:
        """Parsea un ISO timestamp a unix timestamp.

        Args:
            iso_str: String en formato ISO 8601

        Returns:
            Unix timestamp o 0 si falla
        """
        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.timestamp()
        except (ValueError, TypeError):
            return 0.0

    # --- Metodos para reglas ---

    def add_rule(self, rule: NotificationRule) -> str:
        """Agrega una regla al store.

        Args:
            rule: Objeto NotificationRule a agregar

        Returns:
            ID de la regla creada
        """
        with self._lock:
            self._rules.append(rule.to_dict())
            self._save()
        return rule.rule_id

    def remove_rule(self, rule_id: str) -> bool:
        """Elimina una regla del store.

        Args:
            rule_id: ID de la regla

        Returns:
            True si se elimino, False si no existia
        """
        with self._lock:
            original = len(self._rules)
            self._rules = [r for r in self._rules if r.get("rule_id") != rule_id]
            if len(self._rules) < original:
                self._save()
                return True
        return False

    def get_rules(self) -> list[dict]:
        """Obtiene todas las reglas almacenadas.

        Returns:
            Lista de diccionarios con las reglas
        """
        with self._lock:
            return list(self._rules)

    # --- Metodos para rate limiting ---

    def record_rate(self, channel: str) -> None:
        """Registra un envio de notificacion para rate limiting.

        Args:
            channel: Canal por el que se envio
        """
        now = time.time()
        with self._lock:
            if channel not in self._rate_limits:
                self._rate_limits[channel] = []
            self._rate_limits[channel].append(now)
            # Limpiar timestamps viejos (mayor a 2 minutos)
            self._rate_limits[channel] = [
                t for t in self._rate_limits[channel] if now - t < 120
            ]

    def get_rate_count(self, channel: str, window_seconds: int = 60) -> int:
        """Obtiene el conteo de notificaciones en una ventana de tiempo.

        Args:
            channel: Canal a consultar
            window_seconds: Ventana de tiempo en segundos

        Returns:
            Numero de notificaciones enviadas en la ventana
        """
        now = time.time()
        with self._lock:
            timestamps = self._rate_limits.get(channel, [])
            return sum(1 for t in timestamps if now - t < window_seconds)

    def get_rate_limits_data(self) -> dict:
        """Obtiene los datos de rate limiting para persistencia.

        Returns:
            Dict con los timestamps de rate limiting
        """
        return self._rate_limits


# ============================================================
# NOTIFICATION CHANNELS (Abstract + Implementations)
# ============================================================

class NotificationChannel(ABC):
    """Clase base abstracta para canales de notificacion.

    Todos los canales deben implementar el metodo send().
    """

    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """Envia una notificacion por este canal.

        Args:
            notification: Notificacion a enviar

        Returns:
            True si se envio correctamente, False si fallo
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica si el canal esta disponible.

        Returns:
            True si el canal puede enviar notificaciones
        """
        ...


class InAppChannel(NotificationChannel):
    """Canal de notificaciones in-app.

    Las notificaciones se almacenan en el NotificationStore
    y se muestran en la interfaz (Streamlit).
    Siempre disponible.
    """

    def __init__(self, store: NotificationStore):
        """Inicializa el canal in-app.

        Args:
            store: NotificationStore donde guardar las notificaciones
        """
        self._store = store

    def send(self, notification: Notification) -> bool:
        """Guarda la notificacion en el store.

        Args:
            notification: Notificacion a almacenar

        Returns:
            True siempre (canal in-app nunca falla)
        """
        try:
            self._store.add(notification)
            logger.debug(f"[InAppChannel] Notificacion almacenada: {notification.id}")
            return True
        except Exception as e:
            logger.warning(f"[InAppChannel] Error almacenando notificacion: {e}")
            return False

    def is_available(self) -> bool:
        """El canal in-app siempre esta disponible.

        Returns:
            True
        """
        return True


class EmailChannel(NotificationChannel):
    """Canal de notificaciones por email via SMTP.

    Configurable desde credentials/api_keys.json con:
    - smtp_host, smtp_port, smtp_user, smtp_password
    - email_from, email_to

    Incluye templates HTML para diferentes tipos de notificacion.
    Graceful fallback cuando SMTP no esta configurado.
    """

    def __init__(self):
        """Inicializa el canal de email cargando configuracion."""
        self._config = self._load_smtp_config()
        self._available = bool(self._config.get("smtp_host"))

    def _load_smtp_config(self) -> dict:
        """Carga la configuracion SMTP desde el archivo de credenciales.

        Returns:
            Dict con configuracion SMTP o dict vacio si no esta configurado
        """
        if not os.path.exists(_CREDENTIALS_FILE):
            return {}

        try:
            with open(_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Buscar seccion de email/smtp
            email_config = data.get("email", data.get("smtp", {}))
            if isinstance(email_config, dict) and email_config.get("smtp_host"):
                return email_config
            return {}
        except Exception as e:
            logger.debug(f"[EmailChannel] Error cargando config SMTP: {e}")
            return {}

    def is_available(self) -> bool:
        """Verifica si SMTP esta configurado y disponible.

        Returns:
            True si hay configuracion SMTP valida
        """
        return self._available

    def test_connection(self) -> dict:
        """Prueba la conexion SMTP.

        Returns:
            Dict con 'success' (bool) y 'message' (str)
        """
        if not self._available:
            return {"success": False, "message": "SMTP no configurado"}

        try:
            host = self._config["smtp_host"]
            port = int(self._config.get("smtp_port", 587))
            user = self._config.get("smtp_user", "")
            password = self._config.get("smtp_password", "")

            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls()
                if user and password:
                    server.login(user, password)

            return {"success": True, "message": f"Conexion exitosa a {host}:{port}"}
        except Exception as e:
            return {"success": False, "message": f"Error de conexion: {e}"}

    def send(self, notification: Notification) -> bool:
        """Envia una notificacion por email.

        Args:
            notification: Notificacion a enviar

        Returns:
            True si se envio, False si fallo o no esta configurado
        """
        if not self._available:
            logger.debug("[EmailChannel] SMTP no configurado, notificacion omitida")
            return False

        try:
            host = self._config["smtp_host"]
            port = int(self._config.get("smtp_port", 587))
            user = self._config.get("smtp_user", "")
            password = self._config.get("smtp_password", "")
            email_from = self._config.get("email_from", user)
            email_to = self._config.get("email_to", user)

            # Construir email HTML
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[AgentLocal] {notification.title}"
            msg["From"] = email_from
            msg["To"] = email_to

            # Generar HTML desde template
            html_body = self._render_template(notification)
            text_body = f"{notification.title}\n\n{notification.message}\n\nPrioridad: {notification.priority}\nCategoria: {notification.category}"

            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            # Enviar
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls()
                if user and password:
                    server.login(user, password)
                server.sendmail(email_from, [email_to], msg.as_string())

            logger.info(f"[EmailChannel] Notificacion enviada: {notification.id}")
            return True
        except Exception as e:
            logger.warning(f"[EmailChannel] Error enviando email: {e}")
            return False

    def _render_template(self, notification: Notification) -> str:
        """Renderiza un template HTML para la notificacion.

        Args:
            notification: Notificacion a renderizar

        Returns:
            String con HTML del email
        """
        # Colores por prioridad
        priority_colors = {
            "low": "#6c757d",
            "medium": "#0d6efd",
            "high": "#fd7e14",
            "critical": "#dc3545",
        }
        color = priority_colors.get(notification.priority, "#0d6efd")

        # Icono por categoria
        category_icons = {
            "general": "&#128276;",
            "task": "&#9989;",
            "error": "&#10060;",
            "scheduler": "&#9200;",
            "deployment": "&#128640;",
            "security": "&#128274;",
            "system": "&#9881;",
        }
        icon = category_icons.get(notification.category, "&#128276;")

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
  <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
    <div style="background-color: {color}; padding: 16px 24px; color: white;">
      <h2 style="margin: 0;">{icon} {notification.title}</h2>
    </div>
    <div style="padding: 24px;">
      <p style="font-size: 14px; color: #333; line-height: 1.6;">{notification.message}</p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 16px 0;">
      <p style="font-size: 12px; color: #888;">
        Prioridad: <strong style="color: {color};">{notification.priority.upper()}</strong> |
        Categoria: {notification.category} |
        {notification.created_at}
      </p>
    </div>
  </div>
</body>
</html>"""


class WebhookChannel(NotificationChannel):
    """Canal de notificaciones via HTTP POST (webhook).

    Configurable con URLs por categoria. Incluye:
    - Retry con exponential backoff
    - Signature verification (HMAC-SHA256)
    - Graceful fallback cuando no hay URL configurada
    """

    def __init__(self):
        """Inicializa el canal webhook."""
        self._urls = self._load_webhook_urls()
        self._default_url = self._urls.get("default", "")
        self._secret = self._urls.get("secret", "")
        self._available = bool(self._default_url or any(
            v for k, v in self._urls.items() if k not in ("default", "secret")
        ))

    def _load_webhook_urls(self) -> dict:
        """Carga las URLs de webhook desde credenciales.

        Returns:
            Dict con URLs por categoria
        """
        if not os.path.exists(_CREDENTIALS_FILE):
            return {}

        try:
            with open(_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("webhooks", {})
        except Exception as e:
            logger.debug(f"[WebhookChannel] Error cargando webhooks: {e}")
            return {}

    def is_available(self) -> bool:
        """Verifica si hay webhooks configurados.

        Returns:
            True si hay al menos una URL configurada
        """
        return self._available

    def send(self, notification: Notification) -> bool:
        """Envia una notificacion via HTTP POST.

        Incluye retry con exponential backoff y firma HMAC.

        Args:
            notification: Notificacion a enviar

        Returns:
            True si se envio, False si fallo
        """
        url = self._urls.get(notification.category, self._default_url)
        if not url:
            logger.debug(f"[WebhookChannel] No hay URL configurada para categoria '{notification.category}'")
            return False

        payload = {
            "title": notification.title,
            "message": notification.message,
            "priority": notification.priority,
            "category": notification.category,
            "channel": notification.channel,
            "timestamp": notification.created_at,
            "id": notification.id,
        }

        headers = {"Content-Type": "application/json"}

        # Agregar firma HMAC si hay secret configurado
        if self._secret:
            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            signature = hmac_module.new(
                self._secret.encode("utf-8"),
                body_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        # Retry con exponential backoff (3 intentos)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Usar urllib para evitar dependencias externas
                import urllib.request
                import urllib.error

                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status < 300:
                        logger.info(f"[WebhookChannel] Notificacion enviada: {notification.id} -> {url}")
                        return True
                    else:
                        logger.warning(
                            f"[WebhookChannel] HTTP {response.status} en intento {attempt + 1}"
                        )
            except urllib.error.HTTPError as e:
                logger.warning(
                    f"[WebhookChannel] HTTP Error {e.code} en intento {attempt + 1}: {e.reason}"
                )
            except urllib.error.URLError as e:
                logger.warning(
                    f"[WebhookChannel] URL Error en intento {attempt + 1}: {e.reason}"
                )
            except Exception as e:
                logger.warning(
                    f"[WebhookChannel] Error en intento {attempt + 1}: {e}"
                )

            # Exponential backoff: 1s, 2s, 4s
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)

        logger.error(f"[WebhookChannel] Fallo definitivo tras {max_retries} intentos: {notification.id}")
        return False


class DesktopChannel(NotificationChannel):
    """Canal de notificaciones de escritorio (OS-level).

    Soporta:
    - Linux: notify-send
    - macOS: osascript
    - Windows: PowerShell toast
    Auto-detecta OS y herramientas disponibles.
    Graceful fallback cuando no hay herramientas.
    """

    def __init__(self):
        """Inicializa el canal desktop detectando OS."""
        self._os = platform.system()
        self._tool = self._detect_tool()
        self._available = bool(self._tool)

    def _detect_tool(self) -> Optional[str]:
        """Detecta la herramienta de notificacion disponible.

        Returns:
            Nombre de la herramienta o None si no hay disponible
        """
        try:
            if self._os == "Linux":
                # Verificar notify-send
                result = subprocess.run(
                    ["which", "notify-send"],
                    capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    return "notify-send"

            elif self._os == "Darwin":
                # macOS siempre tiene osascript
                return "osascript"

            elif self._os == "Windows":
                # Windows tiene PowerShell
                return "powershell"

        except Exception as e:
            logger.debug(f"[DesktopChannel] Error detectando herramienta: {e}")

        return None

    def is_available(self) -> bool:
        """Verifica si hay herramienta de notificacion disponible.

        Returns:
            True si se detecto una herramienta
        """
        return self._available

    def send(self, notification: Notification) -> bool:
        """Envia una notificacion de escritorio.

        Args:
            notification: Notificacion a enviar

        Returns:
            True si se envio, False si fallo o no hay herramienta
        """
        if not self._available:
            logger.debug("[DesktopChannel] No hay herramienta de notificacion disponible")
            return False

        try:
            title = notification.title[:100]
            message = notification.message[:200]

            if self._tool == "notify-send":
                # Linux: notify-send
                result = subprocess.run(
                    ["notify-send", "-u", self._urgency(notification.priority), title, message],
                    capture_output=True, timeout=5
                )
                return result.returncode == 0

            elif self._tool == "osascript":
                # macOS: osascript
                # Escapar comillas para AppleScript
                safe_title = title.replace('"', '\\"').replace('\\', '\\\\')
                safe_msg = message.replace('"', '\\"').replace('\\', '\\\\')
                script = f'display notification "{safe_msg}" with title "{safe_title}"'
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, timeout=5
                )
                return result.returncode == 0

            elif self._tool == "powershell":
                # Windows: PowerShell toast notification
                safe_title = title.replace("'", "''")
                safe_msg = message.replace("'", "''")
                ps_script = f"""
                Add-Type -AssemblyName System.Windows.Forms
                $notify = New-Object System.Windows.Forms.NotifyIcon
                $notify.Icon = [System.Drawing.SystemIcons]::Information
                $notify.Visible = $true
                $notify.ShowBalloonTip(5000, '{safe_title}', '{safe_msg}', [System.Windows.Forms.ToolTipIcon]::Info)
                Start-Sleep -Milliseconds 5500
                $notify.Dispose()
                """
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    capture_output=True, timeout=10
                )
                return result.returncode == 0

        except subprocess.TimeoutExpired:
            logger.debug("[DesktopChannel] Timeout enviando notificacion de escritorio")
        except FileNotFoundError:
            logger.debug("[DesktopChannel] Herramienta no encontrada en el sistema")
        except Exception as e:
            logger.debug(f"[DesktopChannel] Error enviando notificacion: {e}")

        return False

    def _urgency(self, priority: str) -> str:
        """Mapea prioridad a urgencia de notify-send.

        Args:
            priority: Nivel de prioridad

        Returns:
            Nivel de urgencia para notify-send (low, normal, critical)
        """
        mapping = {
            "low": "low",
            "medium": "normal",
            "high": "normal",
            "critical": "critical",
        }
        return mapping.get(priority, "normal")


# ============================================================
# NOTIFICATION MANAGER (Singleton)
# ============================================================

class NotificationManager:
    """Gestor principal de notificaciones (Singleton).

    Centraliza el envio de notificaciones a traves de multiples canales,
    gestiona reglas de notificacion, rate limiting y historial.
    """

    _instance: Optional["NotificationManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Implementa patron Singleton thread-safe."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self, store: NotificationStore = None):
        """Inicializa el NotificationManager.

        Args:
            store: NotificationStore personalizado (para testing).
                   Por defecto crea uno con la ruta estandar.
        """
        if self._initialized:
            return

        self._store = store or NotificationStore()
        self._channels: dict[str, NotificationChannel] = {}
        self._rules: list[NotificationRule] = []
        self._rate_lock = threading.Lock()

        # Inicializar canales
        self._channels["in_app"] = InAppChannel(self._store)
        self._channels["email"] = EmailChannel()
        self._channels["webhook"] = WebhookChannel()
        self._channels["desktop"] = DesktopChannel()

        # Cargar reglas desde store y agregar default rules
        self._load_rules()
        self._ensure_default_rules()

        self._initialized = True
        logger.info(
            f"[NotificationManager] Inicializado - Canales: "
            f"{', '.join(k + ('+' if v.is_available() else '-') for k, v in self._channels.items())} | "
            f"Reglas: {len(self._rules)}"
        )

    def _load_rules(self) -> None:
        """Carga las reglas desde el store."""
        for rule_data in self._store.get_rules():
            try:
                rule = NotificationRule.from_dict(rule_data)
                self._rules.append(rule)
            except Exception as e:
                logger.debug(f"[NotificationManager] Error cargando regla: {e}")

    def _ensure_default_rules(self) -> None:
        """Crea las reglas por defecto si no existen."""
        default_rules = [
            NotificationRule(
                rule_id="default_task_failure",
                name="Task failure notification",
                condition={"event_type": "task_failure"},
                channel="in_app,desktop",
                priority="high",
                enabled=True,
            ),
            NotificationRule(
                rule_id="default_scheduler_trigger",
                name="Scheduler trigger notification",
                condition={"event_type": "scheduler_trigger"},
                channel="in_app",
                priority="low",
                enabled=True,
            ),
            NotificationRule(
                rule_id="default_error_rate",
                name="High error rate alert",
                condition={"event_type": "error_rate", "params": {"count": 5}},
                channel="in_app,email",
                priority="critical",
                enabled=True,
            ),
            NotificationRule(
                rule_id="default_deployment",
                name="New deployment notification",
                condition={"event_type": "new_deployment"},
                channel="webhook",
                priority="medium",
                enabled=True,
            ),
        ]

        # Solo agregar si no existen ya
        existing_ids = {r.rule_id for r in self._rules}
        for rule in default_rules:
            if rule.rule_id not in existing_ids:
                self._rules.append(rule)
                self._store.add_rule(rule)

    # --- API principal ---

    def notify(self, title: str, message: str, channel: str = "in_app",
               priority: str = "medium", category: str = "general") -> str:
        """Envia una notificacion a traves de los canales especificados.

        Args:
            title: Titulo de la notificacion
            message: Mensaje descriptivo
            channel: Canal o canales separados por coma (in_app, email, webhook, desktop)
            priority: Nivel de prioridad (low, medium, high, critical)
            category: Categoria de la notificacion

        Returns:
            ID de la notificacion (o string de error)
        """
        # Validar prioridad
        if priority not in VALID_PRIORITIES:
            priority = "medium"

        # Validar canales
        channels = [c.strip() for c in channel.split(",")]
        valid_channels = [c for c in channels if c in VALID_CHANNELS]
        if not valid_channels:
            valid_channels = ["in_app"]

        # Rate limiting check
        for ch in valid_channels:
            if not self._rate_limit_check(ch):
                logger.warning(f"[NotificationManager] Rate limit alcanzado para canal '{ch}', notificacion omitida")
                return f"rate_limited:{ch}"

        # Crear notificacion
        notification = Notification(
            title=title[:200],
            message=message[:2000],
            channel=",".join(valid_channels),
            priority=priority,
            category=category if category in VALID_CATEGORIES else "general",
        )

        # Enviar por cada canal
        results = {}
        for ch in valid_channels:
            channel_impl = self._channels.get(ch)
            if channel_impl and channel_impl.is_available():
                try:
                    success = channel_impl.send(notification)
                    results[ch] = success
                    if success:
                        self._store.record_rate(ch)
                except Exception as e:
                    results[ch] = False
                    logger.warning(f"[NotificationManager] Error enviando por {ch}: {e}")
            else:
                results[ch] = False
                logger.debug(f"[NotificationManager] Canal {ch} no disponible")

        # Siempre guardar en in_app como fallback (si no se envio ya)
        if "in_app" not in valid_channels and not results.get("in_app", False):
            in_app = self._channels.get("in_app")
            if in_app:
                in_app.send(notification)

        success_channels = [k for k, v in results.items() if v]
        if success_channels:
            logger.info(
                f"[NotificationManager] Notificacion {notification.id} enviada por: "
                f"{', '.join(success_channels)} (prioridad: {priority})"
            )
        else:
            # Fallback: siempre guardar en store
            self._store.add(notification)
            logger.warning(
                f"[NotificationManager] Notificacion {notification.id} solo almacenada "
                f"(ningun canal disponible)"
            )

        return notification.id

    def add_rule(self, rule: NotificationRule) -> str:
        """Agrega una regla de notificacion.

        Args:
            rule: NotificationRule a agregar

        Returns:
            ID de la regla
        """
        self._rules.append(rule)
        self._store.add_rule(rule)
        logger.info(f"[NotificationManager] Regla agregada: {rule.name} ({rule.rule_id})")
        return rule.rule_id

    def remove_rule(self, rule_id: str) -> bool:
        """Elimina una regla de notificacion.

        Args:
            rule_id: ID de la regla a eliminar

        Returns:
            True si se elimino, False si no existia
        """
        original = len(self._rules)
        self._rules = [r for r in self._rules if r.rule_id != rule_id]
        if len(self._rules) < original:
            self._store.remove_rule(rule_id)
            logger.info(f"[NotificationManager] Regla eliminada: {rule_id}")
            return True
        return False

    def check_rules(self, event_type: str, context: dict) -> list[str]:
        """Evalua las reglas contra un evento y envia notificaciones.

        Args:
            event_type: Tipo de evento (task_failure, scheduler_trigger, etc.)
            context: Contexto del evento con datos adicionales

        Returns:
            Lista de IDs de notificaciones enviadas
        """
        notification_ids = []
        for rule in self._rules:
            if rule.evaluate(event_type, context):
                try:
                    nid = self.notify(
                        title=f"Regla: {rule.name}",
                        message=f"Evento '{event_type}' disparo la regla '{rule.name}'. Contexto: {json.dumps(context, default=str)[:500]}",
                        channel=rule.channel,
                        priority=rule.priority,
                        category=context.get("category", "general"),
                    )
                    notification_ids.append(nid)
                except Exception as e:
                    logger.warning(f"[NotificationManager] Error ejecutando regla '{rule.name}': {e}")
        return notification_ids

    def _rate_limit_check(self, channel: str) -> bool:
        """Verifica si se puede enviar una notificacion al canal.

        Implementa dos limites:
        - Max N por minuto por canal
        - Max M en burst de 10 segundos

        Args:
            channel: Canal a verificar

        Returns:
            True si se puede enviar, False si se excede el limite
        """
        # Siempre permitir in_app (no tiene sentido rate-limitear almacenamiento)
        if channel == "in_app":
            return True

        per_minute = self._store.get_rate_count(channel, window_seconds=60)
        if per_minute >= _MAX_PER_CHANNEL_PER_MINUTE:
            return False

        burst = self._store.get_rate_count(channel, window_seconds=10)
        if burst >= _MAX_BURST_PER_10_SECONDS:
            return False

        return True

    def get_unread(self) -> list[Notification]:
        """Obtiene las notificaciones no leidas.

        Returns:
            Lista de Notification no leidas
        """
        return self._store.get_unread()

    def mark_read(self, notification_id: str) -> bool:
        """Marca una notificacion como leida.

        Args:
            notification_id: ID de la notificacion

        Returns:
            True si se encontro y marco
        """
        return self._store.mark_read(notification_id)

    def dismiss(self, notification_id: str) -> bool:
        """Descarta una notificacion.

        Args:
            notification_id: ID de la notificacion

        Returns:
            True si se encontro y descarto
        """
        return self._store.dismiss(notification_id)

    def get_history(self, limit: int = 50) -> list[Notification]:
        """Obtiene el historial de notificaciones.

        Args:
            limit: Maximo de notificaciones a retornar

        Returns:
            Lista de Notification ordenadas por fecha
        """
        return self._store.get_history(limit)

    def get_status(self) -> dict:
        """Obtiene el estado del sistema de notificaciones.

        Returns:
            Dict con canales disponibles, reglas activas, conteo de notificaciones
        """
        return {
            "channels": {
                name: {
                    "available": ch.is_available(),
                    "type": type(ch).__name__,
                }
                for name, ch in self._channels.items()
            },
            "rules": {
                "total": len(self._rules),
                "enabled": sum(1 for r in self._rules if r.enabled),
            },
            "notifications": {
                "total": len(self._store._notifications),
                "unread": len(self._store.get_unread()),
            },
        }


# ============================================================
# SINGLETON ACCESS
# ============================================================

_manager: Optional[NotificationManager] = None
_manager_lock = threading.Lock()


def get_manager() -> NotificationManager:
    """Retorna el NotificationManager singleton (inicializacion lazy).

    Thread-safe: multiples threads llamando esto concurrentemente
    obtendran la misma instancia.

    Returns:
        Instancia unica de NotificationManager
    """
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = NotificationManager()
    return _manager


# ============================================================
# TOOL FUNCTIONS
# ============================================================

def _notificar_tool(mensaje: str, prioridad: str = "medium", canal: str = "in_app") -> str:
    """Envia una notificacion al usuario a traves del canal especificado.

    Args:
        mensaje: Mensaje de la notificacion
        prioridad: Nivel de prioridad (low, medium, high, critical)
        canal: Canal de notificacion (in_app, email, webhook, desktop) o varios separados por coma

    Returns:
        Confirmacion con ID de la notificacion
    """
    manager = get_manager()
    # Usar primeras 80 chars como titulo, el resto como mensaje
    title = mensaje[:80] if len(mensaje) <= 80 else mensaje[:77] + "..."
    nid = manager.notify(
        title=title,
        message=mensaje,
        channel=canal,
        priority=prioridad,
        category="general",
    )

    if nid.startswith("rate_limited:"):
        return f"Rate limit alcanzado en canal {canal}. Notificacion omitida para evitar spam."

    return f"Notificacion enviada (ID: {nid}, prioridad: {prioridad}, canal: {canal})"


def _ver_notificaciones_tool(no_leidas: bool = True) -> str:
    """Muestra las notificaciones del sistema.

    Args:
        no_leidas: Si True, muestra solo las no leidas. Si False, muestra todas.

    Returns:
        Lista formateada de notificaciones
    """
    manager = get_manager()

    if no_leidas:
        notifications = manager.get_unread()
        header = "NOTIFICACIONES NO LEIDAS"
    else:
        notifications = manager.get_history(limit=20)
        header = "HISTORIAL DE NOTIFICACIONES (ultimas 20)"

    if not notifications:
        return "No hay notificaciones pendientes."

    # Iconos por prioridad
    priority_icons = {
        "low": "[LOW]",
        "medium": "[MED]",
        "high": "[HIGH]",
        "critical": "[CRIT]",
    }

    lines = [header, "=" * 50]
    for n in notifications[:20]:
        icon = priority_icons.get(n.priority, "[???]")
        status = "" if not n.read else " (leida)"
        lines.append(f"  {icon} {n.title}{status}")
        lines.append(f"       ID: {n.id} | Canal: {n.channel} | {n.created_at[:19]}")
        if n.message and len(n.message) > len(n.title):
            # Mostrar mensaje solo si es mas largo que el titulo
            lines.append(f"       {n.message[:120]}")
        lines.append("")

    return "\n".join(lines)


def _configurar_regla_tool(nombre: str, condicion: str, canal: str) -> str:
    """Configura una regla de notificacion automatica.

    Args:
        nombre: Nombre descriptivo de la regla
        condicion: Condicion que dispara la regla (event_type, ej: task_failure, error_rate)
        canal: Canal por el que enviar (in_app, email, webhook, desktop, o varios separados por coma)

    Returns:
        Confirmacion con ID de la regla creada
    """
    manager = get_manager()

    # Parsear la condicion: soporta formato "event_type" o "event_type:param=value"
    event_type = condicion.split(":")[0].strip()
    params = {}

    if ":" in condicion:
        parts = condicion.split(":", 1)
        if len(parts) > 1:
            for pair in parts[1].split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    try:
                        params[key.strip()] = float(value.strip())
                    except ValueError:
                        params[key.strip()] = value.strip()

    # Determinar prioridad basada en el tipo de evento
    priority_map = {
        "task_failure": "high",
        "error_rate": "critical",
        "scheduler_trigger": "low",
        "new_deployment": "medium",
        "security_alert": "critical",
    }
    priority = priority_map.get(event_type, "medium")

    # Determinar categoria
    category_map = {
        "task_failure": "task",
        "error_rate": "error",
        "scheduler_trigger": "scheduler",
        "new_deployment": "deployment",
        "security_alert": "security",
    }
    category = category_map.get(event_type, "general")

    rule = NotificationRule(
        name=nombre,
        condition={"event_type": event_type, "params": params, "category": category},
        channel=canal,
        priority=priority,
        enabled=True,
    )

    rule_id = manager.add_rule(rule)
    return f"Regla creada: '{nombre}' (ID: {rule_id}) - Condicion: {condicion} -> Canal: {canal}, Prioridad: {priority}"


# ============================================================
# REGISTRO DE HERRAMIENTAS
# ============================================================

register_tool(
    "notificar",
    _notificar_tool,
    schema={
        "type": "function",
        "function": {
            "name": "notificar",
            "description": "Envia una notificacion al usuario. Soporta multiples canales (in_app, email, webhook, desktop) y niveles de prioridad (low, medium, high, critical). Use para alertar sobre eventos importantes, errores, o resultados de tareas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mensaje": {
                        "type": "string",
                        "description": "Mensaje de la notificacion a enviar"
                    },
                    "prioridad": {
                        "type": "string",
                        "description": "Nivel de prioridad: low, medium, high, critical"
                    },
                    "canal": {
                        "type": "string",
                        "description": "Canal de notificacion: in_app, email, webhook, desktop (o varios separados por coma)"
                    },
                },
                "required": ["mensaje"],
            },
        },
    },
)

register_tool(
    "ver_notificaciones",
    _ver_notificaciones_tool,
    schema={
        "type": "function",
        "function": {
            "name": "ver_notificaciones",
            "description": "Muestra las notificaciones del sistema. Por defecto muestra solo las no leidas. Use para revisar alertas, resultados de tareas, o mensajes pendientes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "no_leidas": {
                        "type": "boolean",
                        "description": "Si True, muestra solo las no leidas. Si False, muestra el historial completo."
                    },
                },
                "required": [],
            },
        },
    },
)

register_tool(
    "configurar_notificacion_regla",
    _configurar_regla_tool,
    schema={
        "type": "function",
        "function": {
            "name": "configurar_notificacion_regla",
            "description": "Configura una regla de notificacion automatica que se dispara cuando ocurre un evento especifico. Ejemplos de condiciones: task_failure, error_rate, scheduler_trigger, new_deployment, security_alert.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": "Nombre descriptivo de la regla"
                    },
                    "condicion": {
                        "type": "string",
                        "description": "Condicion que dispara la regla. Formato: event_type o event_type:param=value. Ejemplos: task_failure, error_rate:count=5, scheduler_trigger"
                    },
                    "canal": {
                        "type": "string",
                        "description": "Canal por el que enviar la notificacion: in_app, email, webhook, desktop, o varios separados por coma"
                    },
                },
                "required": ["nombre", "condicion", "canal"],
            },
        },
    },
)

logger.info("[Notifications] Herramientas registradas: notificar, ver_notificaciones, configurar_notificacion_regla")
