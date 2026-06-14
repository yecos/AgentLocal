"""
=============================================================
AGENTE v24 - Cliente MCP (Model Context Protocol)
=============================================================
Protocolo estandar para integrar herramientas externas.

MCP permite al agente descubrir y usar herramientas de
servidores externos sin necesidad de programar integraciones.

Transportes soportados:
- stdio: Comunicacion via stdin/stdout (proceso local)
- HTTP/SSE: Comunicacion via HTTP con Server-Sent Events

Servidores por defecto:
- filesystem: Operaciones de archivos avanzadas
- github: Operaciones con repositorios GitHub
- sqlite: Base de datos SQLite avanzada
- brave-search: Busqueda web con Brave Search API
- google-drive: Acceso a Google Drive

Uso:
    from mcp.client import MCPClient
    client = MCPClient()
    await client.connect_server("filesystem", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/path"])
    tools = await client.discover_tools("filesystem")
    result = await client.call_tool("filesystem", "read_file", {"path": "/tmp/test.txt"})

v24: Implementacion inicial con transporte stdio y HTTP.
=============================================================
"""

import os
import json
import asyncio
import logging
import subprocess
import time
from datetime import datetime
from typing import Any, Callable, Optional
from pathlib import Path

logger = logging.getLogger("mcp_client")


# ============================================================
# CONFIGURACION MCP
# ============================================================

MCP_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".ia-local")
MCP_CONFIG_FILE = os.path.join(MCP_CONFIG_DIR, "mcp_config.json")

# Servidores MCP por defecto (para referencia, no se auto-inician)
DEFAULT_MCP_SERVERS = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem"],
        "description": "Operaciones avanzadas de sistema de archivos",
        "transport": "stdio",
    },
    "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "description": "Operaciones con repositorios GitHub",
        "transport": "stdio",
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
    },
    "sqlite": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sqlite"],
        "description": "Base de datos SQLite avanzada",
        "transport": "stdio",
    },
    "brave-search": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "description": "Busqueda web con Brave Search API",
        "transport": "stdio",
        "env": {"BRAVE_API_KEY": ""},
    },
}


# ============================================================
# MCP SERVER (representa un servidor MCP conectado)
# ============================================================

class MCPServer:
    """Representa un servidor MCP conectado.

    Maneja la conexion, descubrimiento de herramientas y ejecucion.
    """

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.transport = config.get("transport", "stdio")
        self.command = config.get("command", "")
        self.args = config.get("args", [])
        self.env = config.get("env", {})
        self.url = config.get("url", "")

        self.connected = False
        self.tools = []  # Lista de herramientas descubiertas
        self.process = None  # Proceso hijo (stdio)
        self._request_id = 0
        self._last_ping = None
        self._error_count = 0

    async def connect(self) -> bool:
        """Conecta al servidor MCP."""
        try:
            if self.transport == "stdio":
                return await self._connect_stdio()
            elif self.transport in ("http", "sse"):
                return await self._connect_http()
            else:
                logger.error(f"Transporte no soportado: {self.transport}")
                return False
        except Exception as e:
            logger.error(f"Error conectando a MCP server {self.name}: {e}")
            self._error_count += 1
            return False

    async def _connect_stdio(self) -> bool:
        """Conecta via stdin/stdout."""
        try:
            env = dict(os.environ)
            env.update(self.env)

            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # Enviar initialize request
            init_response = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "AgentLocal",
                    "version": "24.0.0",
                },
            })

            if init_response:
                # Enviar initialized notification
                await self._send_notification("notifications/initialized", {})
                self.connected = True
                self._last_ping = time.time()
                logger.info(f"MCP server {self.name} conectado via stdio")
                return True
            else:
                logger.error(f"Fallo initialize con {self.name}")
                return False

        except Exception as e:
            logger.error(f"Error en conexion stdio con {self.name}: {e}")
            return False

    async def _connect_http(self) -> bool:
        """Conecta via HTTP/SSE."""
        try:
            # Para HTTP, verificamos que el servidor responde
            import urllib.request
            req = urllib.request.Request(
                f"{self.url}/health",
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            if resp.status == 200:
                self.connected = True
                self._last_ping = time.time()
                logger.info(f"MCP server {self.name} conectado via HTTP")
                return True
        except Exception as e:
            logger.error(f"Error en conexion HTTP con {self.name}: {e}")

        return False

    async def discover_tools(self) -> list:
        """Descubre las herramientas disponibles en el servidor."""
        if not self.connected:
            logger.warning(f"Servidor {self.name} no conectado, no se pueden descubrir herramientas")
            return []

        response = await self._send_request("tools/list", {})
        if response and "tools" in response:
            self.tools = response["tools"]
            logger.info(f"Descubiertas {len(self.tools)} herramientas en {self.name}")
            return self.tools

        return []

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Ejecuta una herramienta en el servidor MCP.

        Args:
            tool_name: Nombre de la herramienta
            arguments: Argumentos para la herramienta

        Returns:
            Resultado de la ejecucion
        """
        if not self.connected:
            return {"error": f"Servidor {self.name} no conectado"}

        response = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        if response:
            if "content" in response:
                # Formato MCP: content es una lista de items
                contents = response["content"]
                if isinstance(contents, list):
                    # Extraer texto de los items
                    text_parts = []
                    for item in contents:
                        if isinstance(item, dict) and "text" in item:
                            text_parts.append(item["text"])
                        elif isinstance(item, str):
                            text_parts.append(item)
                    return "\n".join(text_parts) if text_parts else str(contents)
                return str(contents)
            return response

        return {"error": f"Sin respuesta del servidor {self.name}"}

    async def _send_request(self, method: str, params: dict) -> Optional[dict]:
        """Envia una request JSON-RPC al servidor."""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        try:
            if self.transport == "stdio" and self.process:
                return await self._send_stdio_request(request)
            elif self.transport in ("http", "sse") and self.url:
                return await self._send_http_request(request)
        except Exception as e:
            logger.error(f"Error enviando request a {self.name}: {e}")
            self._error_count += 1

        return None

    async def _send_stdio_request(self, request: dict) -> Optional[dict]:
        """Envia una request via stdin y lee la respuesta de stdout."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            return None

        message = json.dumps(request) + "\n"
        self.process.stdin.write(message.encode())
        await self.process.stdin.drain()

        # Leer respuesta con timeout
        try:
            response_line = await asyncio.wait_for(
                self.process.stdout.readline(), timeout=30.0
            )
            if response_line:
                return json.loads(response_line.decode().strip())
        except asyncio.TimeoutError:
            logger.warning(f"Timeout esperando respuesta de {self.name}")
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando respuesta de {self.name}: {e}")

        return None

    async def _send_http_request(self, request: dict) -> Optional[dict]:
        """Envia una request via HTTP POST."""
        try:
            import urllib.request
            data = json.dumps(request).encode()
            req = urllib.request.Request(
                self.url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read().decode())
        except Exception as e:
            logger.error(f"Error en HTTP request a {self.name}: {e}")
            return None

    async def _send_notification(self, method: str, params: dict):
        """Envia una notificacion JSON-RPC (sin esperar respuesta)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        try:
            if self.transport == "stdio" and self.process and self.process.stdin:
                message = json.dumps(notification) + "\n"
                self.process.stdin.write(message.encode())
                await self.process.stdin.drain()
        except Exception as e:
            logger.error(f"Error enviando notificacion a {self.name}: {e}")

    async def disconnect(self):
        """Desconecta del servidor MCP."""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

        self.connected = False
        self.tools = []
        self.process = None
        logger.info(f"MCP server {self.name} desconectado")

    def get_status(self) -> dict:
        """Retorna el estado del servidor."""
        return {
            "name": self.name,
            "connected": self.connected,
            "transport": self.transport,
            "tools_count": len(self.tools),
            "tools": [t.get("name", "") for t in self.tools],
            "error_count": self._error_count,
            "last_ping": self._last_ping,
        }


# ============================================================
# MCP CLIENT (gestiona todos los servidores)
# ============================================================

class MCPClient:
    """Cliente MCP que gestiona multiples servidores.

    Uso:
        client = MCPClient()
        client.add_server("filesystem", {...})
        await client.connect_all()
        tools = client.get_all_tools()
    """

    def __init__(self):
        self.servers: dict[str, MCPServer] = {}
        self._registered_tools = {}  # tool_name -> (server_name, tool_info)
        self._config = self._load_config()

        # Restaurar servidores de la config
        for name, server_config in self._config.get("servers", {}).items():
            self.servers[name] = MCPServer(name, server_config)

    def _load_config(self) -> dict:
        """Carga la configuracion MCP desde disco."""
        if os.path.exists(MCP_CONFIG_FILE):
            try:
                with open(MCP_CONFIG_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error cargando config MCP: {e}")
        return {"servers": {}}

    def _save_config(self):
        """Guarda la configuracion MCP a disco."""
        os.makedirs(MCP_CONFIG_DIR, exist_ok=True)
        config = {
            "servers": {
                name: {
                    "command": srv.command,
                    "args": srv.args,
                    "transport": srv.transport,
                    "url": srv.url,
                    "env": srv.env,
                }
                for name, srv in self.servers.items()
            }
        }
        try:
            with open(MCP_CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Error guardando config MCP: {e}")

    def add_server(self, name: str, config: dict) -> MCPServer:
        """Agrega un servidor MCP.

        Args:
            name: Nombre del servidor
            config: Configuracion del servidor (command, args, transport, url, env)

        Returns:
            El servidor MCP creado
        """
        server = MCPServer(name, config)
        self.servers[name] = server
        self._save_config()
        logger.info(f"Servidor MCP agregado: {name}")
        return server

    def remove_server(self, name: str) -> bool:
        """Elimina un servidor MCP."""
        if name in self.servers:
            server = self.servers.pop(name)
            if server.connected:
                # Desconectar de forma asincrona requiere event loop
                logger.warning(f"Servidor {name} eliminado pero aun conectado")
            self._save_config()
            # Limpiar herramientas registradas
            self._registered_tools = {
                k: v for k, v in self._registered_tools.items()
                if v[0] != name
            }
            return True
        return False

    async def connect_server(self, name: str) -> bool:
        """Conecta a un servidor especifico."""
        server = self.servers.get(name)
        if not server:
            logger.error(f"Servidor MCP no encontrado: {name}")
            return False

        success = await server.connect()
        if success:
            # Descubrir herramientas
            tools = await server.discover_tools()
            for tool in tools:
                tool_name = tool.get("name", "")
                if tool_name:
                    # Prefijar con nombre del servidor para evitar colisiones
                    qualified_name = f"mcp_{name}_{tool_name}"
                    self._registered_tools[qualified_name] = (name, tool)

        return success

    async def connect_all(self) -> dict:
        """Conecta a todos los servidores configurados.

        Returns:
            dict con el resultado de cada conexion
        """
        results = {}
        for name, server in self.servers.items():
            try:
                success = await self.connect_server(name)
                results[name] = {"connected": success, "tools": len(server.tools)}
            except Exception as e:
                results[name] = {"connected": False, "error": str(e)}
        return results

    async def disconnect_all(self):
        """Desconecta todos los servidores."""
        for server in self.servers.values():
            if server.connected:
                await server.disconnect()

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """Ejecuta una herramienta en un servidor MCP.

        Args:
            server_name: Nombre del servidor
            tool_name: Nombre de la herramienta (sin prefijo)
            arguments: Argumentos para la herramienta

        Returns:
            Resultado de la ejecucion
        """
        server = self.servers.get(server_name)
        if not server:
            return {"error": f"Servidor MCP no encontrado: {server_name}"}

        if not server.connected:
            return {"error": f"Servidor {server_name} no conectado"}

        return await server.call_tool(tool_name, arguments)

    def get_all_tools(self) -> list:
        """Retorna todas las herramientas descubiertas de todos los servidores."""
        all_tools = []
        for name, server in self.servers.items():
            if server.connected:
                for tool in server.tools:
                    tool_copy = dict(tool)
                    tool_copy["server"] = name
                    tool_copy["qualified_name"] = f"mcp_{name}_{tool.get('name', '')}"
                    all_tools.append(tool_copy)
        return all_tools

    def get_all_tools_schemas(self) -> list:
        """Retorna schemas en formato Ollama function calling para todas las herramientas MCP."""
        schemas = []
        for qualified_name, (server_name, tool_info) in self._registered_tools.items():
            # Convertir schema MCP a formato Ollama
            mcp_schema = tool_info.get("inputSchema", {})
            description = tool_info.get("description", f"Herramienta MCP: {qualified_name}")

            schema = {
                "type": "function",
                "function": {
                    "name": qualified_name,
                    "description": description,
                    "parameters": mcp_schema if mcp_schema else {
                        "type": "object",
                        "properties": {},
                    },
                },
            }
            schemas.append(schema)

        return schemas

    def get_status(self) -> dict:
        """Retorna el estado de todos los servidores MCP."""
        return {
            "total_servers": len(self.servers),
            "connected_servers": sum(1 for s in self.servers.values() if s.connected),
            "total_tools": len(self._registered_tools),
            "servers": {
                name: server.get_status()
                for name, server in self.servers.items()
            },
        }


# ============================================================
# SYNC WRAPPER (para uso desde codigo sincrono)
# ============================================================

class MCPClientSync:
    """Wrapper sincrono del cliente MCP para uso desde el agente ReAct.

    El agente ReAct es sincrono, asi que este wrapper ejecuta
    las operaciones async en un event loop separado.
    """

    def __init__(self):
        self._client = MCPClient()
        self._loop = None
        self._thread = None

    def _ensure_loop(self):
        """Asegura que hay un event loop corriendo."""
        if self._loop is None or not self._loop.is_running():
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
            self._thread.start()

    def add_server(self, name: str, config: dict) -> MCPServer:
        """Agrega un servidor MCP (sincrono)."""
        return self._client.add_server(name, config)

    def connect_server(self, name: str) -> bool:
        """Conecta a un servidor MCP (sincrono)."""
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._client.connect_server(name), self._loop
        )
        return future.result(timeout=30)

    def discover_tools(self, name: str) -> list:
        """Descubre herramientas de un servidor (sincrono)."""
        server = self._client.servers.get(name)
        if server and server.connected:
            return server.tools
        return []

    def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """Ejecuta una herramienta MCP (sincrono)."""
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._client.call_tool(server_name, tool_name, arguments), self._loop
        )
        try:
            return future.result(timeout=60)
        except Exception as e:
            return {"error": f"Error ejecutando herramienta MCP: {e}"}

    def get_all_tools_schemas(self) -> list:
        """Retorna schemas de herramientas MCP (sincrono)."""
        return self._client.get_all_tools_schemas()

    def get_status(self) -> dict:
        """Retorna estado de servidores MCP (sincrono)."""
        return self._client.get_status()

    def remove_server(self, name: str) -> bool:
        """Elimina un servidor MCP (sincrono)."""
        return self._client.remove_server(name)


# ============================================================
# SINGLETON
# ============================================================

import threading

_sync_client: Optional[MCPClientSync] = None

def get_mcp_client() -> MCPClientSync:
    """Obtiene la instancia singleton del cliente MCP sincrono."""
    global _sync_client
    if _sync_client is None:
        _sync_client = MCPClientSync()
    return _sync_client
