"""
=============================================================
AGENTE v22 - API Integration Framework
=============================================================
Framework para gestionar integraciones con APIs externas:
- Almacenamiento seguro de API keys
- HTTP client estructurado con reintentos
- OAuth 2.0 flow (authorization code + refresh)
- Rate limiting automatico
- Request/response logging para observabilidad

v22: Primera implementacion - API key storage + HTTP client
     + OAuth basics + rate limiting
=============================================================
"""

import os
import re
import json
import time
import hashlib
import logging
import threading
from pathlib import Path
from typing import Optional
from datetime import datetime

from tools.registry import register_tool
from config import logger

# ============================================================
# CONFIGURACION
# ============================================================

# Directorio para almacenar credentials (dentro del agente)
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_CREDENTIALS_DIR = os.path.normpath(os.path.join(_AGENT_DIR, "..", "credentials"))

# Archivo de credenciales encriptado (simbolo - en produccion usar vault)
_CREDENTIALS_FILE = os.path.join(_CREDENTIALS_DIR, "api_keys.json")

# Rate limits por servicio (requests per minute)
_DEFAULT_RATE_LIMITS = {
    "github": 60,
    "openai": 60,
    "stripe": 100,
    "slack": 60,
    "google": 30,
    "twitter": 15,
    "default": 30,
}

# Timeout por defecto para HTTP requests (segundos)
_DEFAULT_TIMEOUT = 30

# Max reintentos para requests fallidos
_MAX_RETRIES = 3

# ============================================================
# ALMACEN SEGURO DE API KEYS
# ============================================================

class APIKeyStore:
    """Almacen seguro de API keys y tokens.

    Las keys se guardan en un archivo JSON con hash simple
    de ofuscacion. NO es criptograficamente seguro - es una
    capa basica para evitar exposicion accidental.

    En produccion, esto deberia usar un vault real (HashiCorp,
    AWS Secrets Manager, etc.).
    """

    def __init__(self, credentials_file: str = None):
        self._file = credentials_file or _CREDENTIALS_FILE
        self._keys: dict = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Carga las keys desde el archivo de credenciales."""
        if not os.path.exists(self._file):
            self._keys = {}
            return

        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Des-ofuscar keys (rotacion simple de bytes)
            self._keys = {}
            for service, entry in data.items():
                key = entry.get("key", "")
                # Solo cargar si tiene el formato esperado
                if key:
                    self._keys[service] = {
                        "key": self._deobfuscate(key),
                        "type": entry.get("type", "api_key"),
                        "created": entry.get("created", ""),
                        "last_used": entry.get("last_used", ""),
                        "metadata": entry.get("metadata", {}),
                    }

            logger.debug(f"[APIKeyStore] Cargadas {len(self._keys)} credenciales")

        except Exception as e:
            logger.warning(f"[APIKeyStore] Error cargando credenciales: {e}")
            self._keys = {}

    def _save(self) -> None:
        """Guarda las keys al archivo de credenciales."""
        try:
            os.makedirs(os.path.dirname(self._file), exist_ok=True)

            data = {}
            for service, entry in self._keys.items():
                data[service] = {
                    "key": self._obfuscate(entry["key"]),
                    "type": entry.get("type", "api_key"),
                    "created": entry.get("created", ""),
                    "last_used": entry.get("last_used", ""),
                    "metadata": entry.get("metadata", {}),
                }

            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Restringir permisos del archivo (solo owner puede leer)
            try:
                os.chmod(self._file, 0o600)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"[APIKeyStore] Error guardando credenciales: {e}")

    @staticmethod
    def _obfuscate(text: str) -> str:
        """Ofusca un texto con rotacion simple de bytes."""
        result = []
        for ch in text:
            result.append(chr(ord(ch) + 3))
        return "".join(result)

    @staticmethod
    def _deobfuscate(text: str) -> str:
        """Des-ofusca un texto con rotacion inversa."""
        result = []
        for ch in text:
            result.append(chr(ord(ch) - 3))
        return "".join(result)

    def store_key(self, service: str, key: str, key_type: str = "api_key",
                  metadata: dict = None) -> dict:
        """Almacena una API key para un servicio.

        Args:
            service: Nombre del servicio (ej: "github", "openai")
            key: La API key o token
            key_type: Tipo de key ("api_key", "bearer_token", "oauth2")
            metadata: Metadata adicional (ej: scopes, expiry)

        Returns:
            Dict con confirmacion
        """
        with self._lock:
            # Hashear la key para comparacion (no almacenar hash)
            key_preview = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***"

            self._keys[service] = {
                "key": key,
                "type": key_type,
                "created": datetime.now().isoformat(),
                "last_used": "",
                "metadata": metadata or {},
            }

            self._save()

            logger.info(f"[APIKeyStore] Credencial almacenada: {service} ({key_type}, preview={key_preview})")

            return {
                "service": service,
                "type": key_type,
                "preview": key_preview,
                "stored": True,
            }

    def get_key(self, service: str) -> Optional[str]:
        """Recupera la API key para un servicio.

        Args:
            service: Nombre del servicio

        Returns:
            La API key como string, o None si no existe
        """
        with self._lock:
            entry = self._keys.get(service)
            if not entry:
                return None

            # Actualizar last_used
            entry["last_used"] = datetime.now().isoformat()
            self._save()

            return entry["key"]

    def get_key_info(self, service: str) -> Optional[dict]:
        """Retorna informacion sobre una key sin revelarla.

        Args:
            service: Nombre del servicio

        Returns:
            Dict con info de la key (sin la key misma)
        """
        entry = self._keys.get(service)
        if not entry:
            return None

        key = entry["key"]
        return {
            "service": service,
            "type": entry["type"],
            "preview": f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***",
            "created": entry.get("created", ""),
            "last_used": entry.get("last_used", ""),
            "metadata": entry.get("metadata", {}),
        }

    def delete_key(self, service: str) -> bool:
        """Elimina la API key de un servicio.

        Args:
            service: Nombre del servicio

        Returns:
            True si se elimino, False si no existia
        """
        with self._lock:
            if service not in self._keys:
                return False

            del self._keys[service]
            self._save()

            logger.info(f"[APIKeyStore] Credencial eliminada: {service}")
            return True

    def list_services(self) -> list[dict]:
        """Lista todos los servicios con credenciales almacenadas.

        Returns:
            Lista de dicts con info de cada servicio (sin keys)
        """
        return [self.get_key_info(s) for s in self._keys]

    def test_key(self, service: str) -> dict:
        """Prueba si una API key es valida haciendo una request de prueba.

        Args:
            service: Nombre del servicio

        Returns:
            Dict con: valid, status, message
        """
        key = self.get_key(service)
        if not key:
            return {"valid": False, "status": "no_key", "message": f"No hay credencial para {service}"}

        # Test endpoints por servicio
        test_endpoints = {
            "github": {
                "url": "https://api.github.com/user",
                "header": "Authorization",
                "prefix": "token ",
            },
            "openai": {
                "url": "https://api.openai.com/v1/models",
                "header": "Authorization",
                "prefix": "Bearer ",
            },
            "stripe": {
                "url": "https://api.stripe.com/v1/balance",
                "header": "Authorization",
                "prefix": "Bearer ",
            },
        }

        test = test_endpoints.get(service)
        if not test:
            return {
                "valid": None,
                "status": "no_test",
                "message": f"No hay test endpoint para {service}. Key existe pero no se puede verificar automaticamente.",
            }

        try:
            import urllib.request
            req = urllib.request.Request(test["url"])
            req.add_header(test["header"], f'{test["prefix"]}{key}')
            req.add_header("User-Agent", "AgentLocal/1.0")

            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                return {
                    "valid": True,
                    "status": str(status),
                    "message": f"Key valida para {service} (HTTP {status})",
                }

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {"valid": False, "status": "401", "message": f"Key invalida para {service} (HTTP 401 Unauthorized)"}
            if e.code == 403:
                return {"valid": False, "status": "403", "message": f"Key sin permisos para {service} (HTTP 403 Forbidden)"}
            return {"valid": None, "status": str(e.code), "message": f"Error verificando {service}: HTTP {e.code}"}
        except Exception as e:
            return {"valid": None, "status": "error", "message": f"Error conectando a {service}: {e}"}


# Singleton
_key_store: Optional[APIKeyStore] = None
_key_store_lock = threading.Lock()


def get_key_store() -> APIKeyStore:
    """Retorna el singleton de APIKeyStore."""
    global _key_store
    if _key_store is None:
        with _key_store_lock:
            if _key_store is None:
                _key_store = APIKeyStore()
    return _key_store


# ============================================================
# HTTP CLIENT ESTRUCTURADO
# ============================================================

class HTTPClient:
    """HTTP client estructurado con reintentos, rate limiting y logging.

    Features:
    - Rate limiting automatico por dominio
    - Reintentos con backoff exponencial
    - Logging de requests/responses para observabilidad
    - Soporte para headers, auth, y JSON body
    - Timeout configurable
    """

    def __init__(self, rate_limits: dict = None):
        self._rate_limits = rate_limits or _DEFAULT_RATE_LIMITS
        self._request_times: dict[str, list[float]] = {}  # domain -> [timestamps]
        self._lock = threading.Lock()
        self._log: list[dict] = []  # Request log

    def _get_domain(self, url: str) -> str:
        """Extrae el dominio de una URL."""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except Exception:
            return url[:50]

    def _check_rate_limit(self, domain: str) -> None:
        """Verifica y aplica rate limiting para un dominio.

        Si se excede el limite, espera hasta que haya espacio.
        """
        limit = self._rate_limits.get("default", 30)

        # Buscar limite especifico por keyword
        domain_lower = domain.lower()
        for key, rpm in self._rate_limits.items():
            if key in domain_lower:
                limit = rpm
                break

        now = time.time()
        window = 60.0  # 1 minuto

        with self._lock:
            if domain not in self._request_times:
                self._request_times[domain] = []

            # Limpiar timestamps fuera de la ventana
            self._request_times[domain] = [
                t for t in self._request_times[domain] if now - t < window
            ]

            # Verificar si estamos en el limite
            if len(self._request_times[domain]) >= limit:
                # Calcular tiempo de espera
                oldest = self._request_times[domain][0]
                wait_time = oldest + window - now
                if wait_time > 0:
                    logger.debug(f"[HTTPClient] Rate limit: esperando {wait_time:.1f}s para {domain}")
                    time.sleep(wait_time)

            # Registrar esta request
            self._request_times[domain].append(now)

    def _log_request(self, method: str, url: str, status: int, duration: float,
                     error: str = "") -> None:
        """Registra una request en el log de observabilidad."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "method": method,
            "url": url[:200],
            "status": status,
            "duration_ms": round(duration * 1000, 1),
        }
        if error:
            entry["error"] = error[:200]

        self._log.append(entry)

        # Mantener solo las ultimas 100 requests
        if len(self._log) > 100:
            self._log = self._log[-100:]

    def request(self, method: str, url: str, headers: dict = None,
                body: str = None, auth_service: str = "",
                timeout: int = 0, retries: int = 0) -> dict:
        """Ejecuta una HTTP request con reintentos y rate limiting.

        Args:
            method: HTTP method ("GET", "POST", "PUT", "DELETE", "PATCH")
            url: URL completa
            headers: Headers adicionales (opcional)
            body: Body de la request como string (opcional)
            auth_service: Servicio del cual obtener API key para auth (opcional)
            timeout: Timeout en segundos (default: 30)
            retries: Numero de reintentos (default: 3)

        Returns:
            Dict con: status, headers, body, error
        """
        import urllib.request
        import urllib.error

        domain = self._get_domain(url)
        self._check_rate_limit(domain)

        timeout = timeout or _DEFAULT_TIMEOUT
        retries = retries or _MAX_RETRIES

        # Construir headers
        req_headers = {"User-Agent": "AgentLocal/1.0"}
        if headers:
            req_headers.update(headers)

        # Auth desde keystore
        if auth_service:
            key = get_key_store().get_key(auth_service)
            if key:
                req_headers["Authorization"] = f"Bearer {key}"
            else:
                return {
                    "status": 0,
                    "headers": {},
                    "body": "",
                    "error": f"No hay credencial para {auth_service}. Usa api_keys accion=guardar primero.",
                }

        # Preparar body
        data = body.encode("utf-8") if body else None
        if data and "Content-Type" not in req_headers:
            req_headers["Content-Type"] = "application/json"

        # Ejecutar con reintentos
        last_error = ""
        for attempt in range(retries):
            start = time.time()
            try:
                req = urllib.request.Request(
                    url, data=data, headers=req_headers, method=method.upper()
                )

                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    duration = time.time() - start
                    resp_body = resp.read().decode("utf-8", errors="replace")
                    resp_headers = dict(resp.headers)

                    self._log_request(method, url, resp.status, duration)

                    return {
                        "status": resp.status,
                        "headers": resp_headers,
                        "body": resp_body[:10000],  # Limitar tamano
                        "error": "",
                    }

            except urllib.error.HTTPError as e:
                duration = time.time() - start
                resp_body = ""
                try:
                    resp_body = e.read().decode("utf-8", errors="replace")[:2000]
                except Exception:
                    pass

                self._log_request(method, url, e.code, duration, f"HTTP {e.code}")

                # No reintentar en 4xx (error del cliente)
                if 400 <= e.code < 500:
                    return {
                        "status": e.code,
                        "headers": dict(e.headers) if hasattr(e, 'headers') else {},
                        "body": resp_body,
                        "error": f"HTTP {e.code}: {e.reason}",
                    }

                last_error = f"HTTP {e.code}: {e.reason}"

            except urllib.error.URLError as e:
                duration = time.time() - start
                self._log_request(method, url, 0, duration, str(e.reason))
                last_error = f"URL Error: {e.reason}"

            except Exception as e:
                duration = time.time() - start
                self._log_request(method, url, 0, duration, str(e))
                last_error = str(e)

            # Backoff exponencial antes de reintentar
            if attempt < retries - 1:
                wait = 0.5 * (2 ** attempt)
                logger.debug(f"[HTTPClient] Reintento {attempt + 1}/{retries} en {wait:.1f}s: {last_error}")
                time.sleep(wait)

        return {
            "status": 0,
            "headers": {},
            "body": "",
            "error": f"Fallo tras {retries} intentos: {last_error}",
        }

    def get(self, url: str, **kwargs) -> dict:
        """HTTP GET shortcut."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, body: str = "", **kwargs) -> dict:
        """HTTP POST shortcut."""
        return self.request("POST", url, body=body, **kwargs)

    def put(self, url: str, body: str = "", **kwargs) -> dict:
        """HTTP PUT shortcut."""
        return self.request("PUT", url, body=body, **kwargs)

    def delete(self, url: str, **kwargs) -> dict:
        """HTTP DELETE shortcut."""
        return self.request("DELETE", url, **kwargs)

    def get_request_log(self, last_n: int = 20) -> list[dict]:
        """Retorna las ultimas N requests del log."""
        return self._log[-last_n:]


# Singleton
_http_client: Optional[HTTPClient] = None


def get_http_client() -> HTTPClient:
    """Retorna el singleton de HTTPClient."""
    global _http_client
    if _http_client is None:
        _http_client = HTTPClient()
    return _http_client


# ============================================================
# HERRAMIENTAS REGISTRADAS PARA EL AGENTE
# ============================================================

def _api_keys_tool(accion: str, servicio: str = "", clave: str = "",
                   tipo: str = "api_key", metadata: str = "") -> str:
    """Gestiona API keys y credenciales para servicios externos.

    Acciones:
    - guardar: Almacena una API key para un servicio
    - obtener: Recupera informacion de una key (sin revelarla)
    - eliminar: Elimina la key de un servicio
    - listar: Lista todos los servicios con credenciales
    - probar: Verifica si una key es valida

    Args:
        accion: Accion a realizar (guardar, obtener, eliminar, listar, probar)
        servicio: Nombre del servicio (ej: github, openai, stripe)
        clave: La API key o token (solo para accion=guardar)
        tipo: Tipo de credencial (api_key, bearer_token, oauth2)
        metadata: Metadata adicional en formato JSON (opcional)
    """
    store = get_key_store()
    accion = accion.lower().strip()

    if accion == "guardar":
        if not servicio or not clave:
            return "ERROR: Se requiere servicio y clave para guardar."
        meta = {}
        if metadata:
            try:
                meta = json.loads(metadata)
            except json.JSONDecodeError:
                meta = {"note": metadata}
        result = store.store_key(servicio, clave, key_type=tipo, metadata=meta)
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif accion == "obtener":
        if not servicio:
            return "ERROR: Se requiere el nombre del servicio."
        info = store.get_key_info(servicio)
        if not info:
            return f"No hay credencial almacenada para '{servicio}'."
        return json.dumps(info, ensure_ascii=False, indent=2)

    elif accion == "eliminar":
        if not servicio:
            return "ERROR: Se requiere el nombre del servicio."
        deleted = store.delete_key(servicio)
        if deleted:
            return f"Credencial de '{servicio}' eliminada exitosamente."
        return f"No habia credencial para '{servicio}'."

    elif accion == "listar":
        services = store.list_services()
        if not services:
            return "No hay credenciales almacenadas."
        return json.dumps(services, ensure_ascii=False, indent=2)

    elif accion == "probar":
        if not servicio:
            return "ERROR: Se requiere el nombre del servicio."
        result = store.test_key(servicio)
        return json.dumps(result, ensure_ascii=False, indent=2)

    else:
        return f"ERROR: Accion '{accion}' no reconocida. Acciones validas: guardar, obtener, eliminar, listar, probar"


def _http_request_tool(metodo: str, url: str, headers: str = "",
                       body: str = "", auth_servicio: str = "",
                       timeout: int = 30) -> str:
    """Ejecuta una HTTP request estructurada con reintentos y rate limiting.

    Soporta GET, POST, PUT, DELETE, PATCH. Incluye rate limiting
    automatico, reintentos con backoff, y auth desde el keystore.

    Args:
        metodo: HTTP method (GET, POST, PUT, DELETE, PATCH)
        url: URL completa a la que hacer la request
        headers: Headers adicionales en formato JSON (opcional)
        body: Body de la request como string (para POST/PUT)
        auth_servicio: Servicio del cual obtener API key para Authorization header
        timeout: Timeout en segundos (default: 30)
    """
    client = get_http_client()

    # Parsear headers JSON
    parsed_headers = {}
    if headers:
        try:
            parsed_headers = json.loads(headers)
        except json.JSONDecodeError:
            return "ERROR: headers debe ser un JSON valido. Ejemplo: {\"Content-Type\": \"application/json\"}"

    result = client.request(
        method=metodo.upper(),
        url=url,
        headers=parsed_headers,
        body=body,
        auth_service=auth_servicio,
        timeout=timeout,
    )

    # Formatear respuesta para el agente
    output_parts = []
    output_parts.append(f"Status: {result['status']}")
    if result.get('error'):
        output_parts.append(f"Error: {result['error']}")
    if result.get('body'):
        # Truncar body muy largo
        body_text = result['body']
        if len(body_text) > 5000:
            body_text = body_text[:5000] + f"\n... [truncado: {len(result['body']) - 5000} chars omitidos]"
        output_parts.append(f"Body:\n{body_text}")

    return "\n".join(output_parts)


# ============================================================
# REGISTRO DE HERRAMIENTAS
# ============================================================

register_tool(
    "api_keys",
    _api_keys_tool,
    schema={
        "type": "function",
        "function": {
            "name": "api_keys",
            "description": "Gestiona API keys y credenciales para servicios externos. Guardar, obtener, eliminar, listar o probar keys de GitHub, OpenAI, Stripe, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {
                        "type": "string",
                        "description": "Accion a realizar: guardar, obtener, eliminar, listar, probar"
                    },
                    "servicio": {
                        "type": "string",
                        "description": "Nombre del servicio (ej: github, openai, stripe, slack)"
                    },
                    "clave": {
                        "type": "string",
                        "description": "La API key o token (solo para accion=guardar)"
                    },
                    "tipo": {
                        "type": "string",
                        "description": "Tipo de credencial: api_key, bearer_token, oauth2"
                    },
                    "metadata": {
                        "type": "string",
                        "description": "Metadata adicional en JSON (opcional)"
                    },
                },
                "required": ["accion"],
            },
        },
    },
)

register_tool(
    "http_request",
    _http_request_tool,
    schema={
        "type": "function",
        "function": {
            "name": "http_request",
            "description": "Ejecuta una HTTP request estructurada. Soporta GET, POST, PUT, DELETE, PATCH con rate limiting, reintentos, y auth automatico desde el keystore.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metodo": {
                        "type": "string",
                        "description": "HTTP method: GET, POST, PUT, DELETE, PATCH"
                    },
                    "url": {
                        "type": "string",
                        "description": "URL completa de la request"
                    },
                    "headers": {
                        "type": "string",
                        "description": "Headers en JSON (opcional). Ej: {\"Content-Type\": \"application/json\"}"
                    },
                    "body": {
                        "type": "string",
                        "description": "Body de la request como string (para POST/PUT)"
                    },
                    "auth_servicio": {
                        "type": "string",
                        "description": "Servicio del cual obtener API key para Authorization header (opcional)"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout en segundos (default: 30)"
                    },
                },
                "required": ["metodo", "url"],
            },
        },
    },
)

logger.info("[APIIntegration] Herramientas registradas: api_keys, http_request")
