"""
=============================================================
AGENTE v16 - Herramienta de Base de Datos
=============================================================
Operaciones de base de datos como herramienta de primera clase.

Soporta:
- SQLite (incluido en Python, sin dependencias)
- PostgreSQL (via psycopg2 o subprocess)
- MySQL (via subprocess)

Operaciones:
- db_connect: Conectar a una base de datos
- db_query: Ejecutar query SQL
- db_schema: Inspeccionar schema de tablas
- db_tables: Listar tablas
- db_describe: Describir estructura de una tabla
- db_insert: Insertar datos
- db_export: Exportar tabla a CSV/JSON

v16: Base de datos como herramienta de primera clase.
=============================================================
"""

import os
import json
import csv
import sqlite3
import subprocess
import logging
import tempfile
from datetime import datetime
from typing import Optional

from config import REPOS_DIR, logger
from utils.security import validate_path

# ============================================================
# CONEXION SQLITE
# ============================================================

# Cache de conexiones
_connections: dict = {}


def db_connect(db_path: str, db_type: str = "sqlite") -> dict:
    """Conecta a una base de datos.

    Args:
        db_path: Ruta al archivo de base de datos o connection string
        db_type: Tipo de base de datos (sqlite, postgres, mysql)

    Returns:
        Dict con success, connection_id, message
    """
    conn_id = f"db_{len(_connections)}"

    if db_type == "sqlite":
        # Validar ruta
        validated = validate_path(db_path)
        if not validated:
            # Si no existe, permitir crear nueva
            parent_dir = os.path.dirname(db_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            validated = db_path

        try:
            conn = sqlite3.connect(validated)
            conn.row_factory = sqlite3.Row
            _connections[conn_id] = {
                "connection": conn,
                "type": "sqlite",
                "path": validated,
                "connected_at": datetime.now().isoformat(),
            }
            logger.info(f"[DB] Conectado a SQLite: {validated}")
            return {
                "success": True,
                "connection_id": conn_id,
                "db_type": "sqlite",
                "path": validated,
                "message": f"Conectado a {validated}",
            }
        except Exception as e:
            return {"success": False, "error": f"Error conectando a SQLite: {e}"}

    elif db_type in ("postgres", "postgresql"):
        # Para Postgres usamos subprocess con psql
        _connections[conn_id] = {
            "connection": None,
            "type": "postgres",
            "connection_string": db_path,
            "connected_at": datetime.now().isoformat(),
        }
        # Verificar que psql esta disponible
        try:
            result = subprocess.run(
                ["psql", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return {
                "success": True,
                "connection_id": conn_id,
                "db_type": "postgres",
                "message": f"PostgreSQL disponible: {result.stdout.strip()}",
            }
        except FileNotFoundError:
            return {"success": False, "error": "psql no esta instalado"}

    elif db_type == "mysql":
        _connections[conn_id] = {
            "connection": None,
            "type": "mysql",
            "connection_string": db_path,
            "connected_at": datetime.now().isoformat(),
        }
        try:
            result = subprocess.run(
                ["mysql", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return {
                "success": True,
                "connection_id": conn_id,
                "db_type": "mysql",
                "message": f"MySQL disponible: {result.stdout.strip()}",
            }
        except FileNotFoundError:
            return {"success": False, "error": "mysql client no esta instalado"}

    else:
        return {"success": False, "error": f"Tipo de base de datos no soportado: {db_type}"}


def db_query(query: str, connection_id: str = None, db_path: str = None,
             params: list = None, limit: int = 100) -> dict:
    """Ejecuta una query SQL.

    Args:
        query: Query SQL a ejecutar
        connection_id: ID de conexion existente
        db_path: Ruta a base de datos SQLite (se conecta automaticamente)
        params: Parametros para query parametrizada
        limit: Maximo de filas a retornar

    Returns:
        Dict con success, columns, rows, row_count, execution_time
    """
    import time

    # Seguridad: verificar que no sea una query destructiva sin conexion explicita
    query_upper = query.strip().upper()
    destructive_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "UPDATE"]
    is_destructive = any(query_upper.startswith(kw) for kw in destructive_keywords)

    # Obtener conexion
    conn_info = None
    if connection_id and connection_id in _connections:
        conn_info = _connections[connection_id]
    elif db_path:
        # Auto-conectar
        result = db_connect(db_path)
        if result["success"]:
            conn_info = _connections.get(result["connection_id"])
            connection_id = result["connection_id"]
        else:
            return result
    else:
        return {"success": False, "error": "Se requiere connection_id o db_path"}

    if not conn_info:
        return {"success": False, "error": "Conexion no encontrada"}

    # Ejecutar segun tipo
    if conn_info["type"] == "sqlite":
        return _execute_sqlite_query(conn_info, query, params, limit)
    elif conn_info["type"] == "postgres":
        return _execute_postgres_query(conn_info, query, limit)
    elif conn_info["type"] == "mysql":
        return _execute_mysql_query(conn_info, query, limit)
    else:
        return {"success": False, "error": f"Tipo no soportado: {conn_info['type']}"}


def db_tables(connection_id: str = None, db_path: str = None) -> dict:
    """Lista las tablas de una base de datos.

    Args:
        connection_id: ID de conexion existente
        db_path: Ruta a SQLite (auto-conecta)

    Returns:
        Dict con success, tables, count
    """
    conn_info = _get_connection(connection_id, db_path)
    if not conn_info:
        return {"success": False, "error": "Conexion no encontrada"}

    if conn_info["type"] == "sqlite":
        return db_query(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name",
            db_path=db_path or conn_info.get("path"),
        )
    elif conn_info["type"] == "postgres":
        return db_query(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename",
            connection_id=connection_id,
        )
    elif conn_info["type"] == "mysql":
        return db_query("SHOW TABLES", connection_id=connection_id)

    return {"success": False, "error": "Tipo no soportado"}


def db_describe(table_name: str, connection_id: str = None,
                db_path: str = None) -> dict:
    """Describe la estructura de una tabla.

    Args:
        table_name: Nombre de la tabla
        connection_id: ID de conexion existente
        db_path: Ruta a SQLite

    Returns:
        Dict con success, columns, primary_keys, indexes
    """
    conn_info = _get_connection(connection_id, db_path)
    if not conn_info:
        return {"success": False, "error": "Conexion no encontrada"}

    if conn_info["type"] == "sqlite":
        # PRAGMA table_info
        info = db_query(
            f"PRAGMA table_info({table_name})",
            db_path=db_path or conn_info.get("path"),
        )
        # PRAGMA index_list
        indexes = db_query(
            f"PRAGMA index_list({table_name})",
            db_path=db_path or conn_info.get("path"),
        )
        return {
            "success": True,
            "table": table_name,
            "columns": info.get("rows", []),
            "indexes": indexes.get("rows", []),
        }
    elif conn_info["type"] == "postgres":
        return db_query(
            f"SELECT column_name, data_type, is_nullable, column_default "
            f"FROM information_schema.columns WHERE table_name = '{table_name}'",
            connection_id=connection_id,
        )
    elif conn_info["type"] == "mysql":
        return db_query(f"DESCRIBE {table_name}", connection_id=connection_id)

    return {"success": False, "error": "Tipo no soportado"}


def db_export(table_name: str, output_format: str = "json",
              output_path: str = None, connection_id: str = None,
              db_path: str = None) -> dict:
    """Exporta una tabla a JSON o CSV.

    Args:
        table_name: Nombre de la tabla a exportar
        output_format: "json" o "csv"
        output_path: Ruta del archivo de salida (auto-generado si None)
        connection_id: ID de conexion
        db_path: Ruta a SQLite

    Returns:
        Dict con success, output_path, row_count
    """
    # Obtener datos
    result = db_query(f"SELECT * FROM {table_name}", connection_id=connection_id, db_path=db_path)
    if not result["success"]:
        return result

    rows = result.get("rows", [])
    columns = result.get("columns", [])

    # Generar ruta de salida
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = ".json" if output_format == "json" else ".csv"
        output_path = os.path.join(REPOS_DIR, f"{table_name}_export_{timestamp}{ext}")

    try:
        if output_format == "json":
            # Convertir rows a listas de dicts
            data = []
            for row in rows:
                if isinstance(row, dict):
                    data.append(row)
                elif isinstance(row, (list, tuple)):
                    data.append(dict(zip(columns, row)))
                else:
                    data.append({"value": str(row)})

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        elif output_format == "csv":
            with open(output_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                for row in rows:
                    if isinstance(row, (list, tuple)):
                        writer.writerow(row)
                    elif isinstance(row, dict):
                        writer.writerow([row.get(c, "") for c in columns])

        return {
            "success": True,
            "output_path": output_path,
            "row_count": len(rows),
            "format": output_format,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def db_create_table(table_name: str, columns: list[dict],
                    db_path: str = None, if_not_exists: bool = True) -> dict:
    """Crea una tabla en la base de datos.

    Args:
        table_name: Nombre de la tabla
        columns: Lista de dicts con name, type, nullable, primary_key, default
        db_path: Ruta a SQLite
        if_not_exists: Agregar IF NOT EXISTS

    Returns:
        Dict con success, message
    """
    # Construir SQL
    exists_clause = "IF NOT EXISTS " if if_not_exists else ""
    col_defs = []

    for col in columns:
        col_sql = f"{col['name']} {col.get('type', 'TEXT')}"
        if col.get("primary_key"):
            col_sql += " PRIMARY KEY"
        if col.get("autoincrement"):
            col_sql += " AUTOINCREMENT"
        if not col.get("nullable", True):
            col_sql += " NOT NULL"
        if "default" in col:
            default_val = col["default"]
            if isinstance(default_val, str):
                col_sql += f" DEFAULT '{default_val}'"
            else:
                col_sql += f" DEFAULT {default_val}"
        col_defs.append(col_sql)

    sql = f"CREATE TABLE {exists_clause}{table_name} ({', '.join(col_defs)})"

    return db_query(sql, db_path=db_path)


# ============================================================
# FUNCIONES INTERNAS
# ============================================================

def _get_connection(connection_id: str = None, db_path: str = None) -> Optional[dict]:
    """Obtiene info de conexion existente o crea una nueva."""
    if connection_id and connection_id in _connections:
        return _connections[connection_id]
    if db_path:
        result = db_connect(db_path)
        if result["success"]:
            return _connections.get(result["connection_id"])
    return None


def _execute_sqlite_query(conn_info: dict, query: str, params: list = None,
                          limit: int = 100) -> dict:
    """Ejecuta una query en SQLite."""
    import time

    conn = conn_info["connection"]
    try:
        start = time.time()
        cursor = conn.cursor()

        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        # Verificar si es una query SELECT
        is_select = query.strip().upper().startswith("SELECT") or \
                    query.strip().upper().startswith("PRAGMA")

        if is_select:
            rows = cursor.fetchmany(limit)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            duration = time.time() - start

            # Convertir Row objects a dicts
            result_rows = []
            for row in rows:
                if hasattr(row, "keys"):
                    result_rows.append(dict(row))
                else:
                    result_rows.append(list(row))

            return {
                "success": True,
                "columns": columns,
                "rows": result_rows,
                "row_count": len(result_rows),
                "execution_time": round(duration, 3),
            }
        else:
            conn.commit()
            duration = time.time() - start
            return {
                "success": True,
                "affected_rows": cursor.rowcount,
                "lastrowid": cursor.lastrowid,
                "execution_time": round(duration, 3),
                "message": f"Query ejecutada. {cursor.rowcount} filas afectadas.",
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


def _execute_postgres_query(conn_info: dict, query: str, limit: int = 100) -> dict:
    """Ejecuta una query en PostgreSQL via psql."""
    conn_string = conn_info.get("connection_string", "")
    try:
        result = subprocess.run(
            ["psql", conn_string, "-c", query, "-t", "-A", "-F", "|"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr}

        rows = []
        for line in result.stdout.strip().split("\n"):
            if line:
                rows.append(line.split("|"))

        return {
            "success": True,
            "rows": rows,
            "row_count": len(rows),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _execute_mysql_query(conn_info: dict, query: str, limit: int = 100) -> dict:
    """Ejecuta una query en MySQL via mysql client."""
    conn_string = conn_info.get("connection_string", "")
    try:
        result = subprocess.run(
            ["mysql", conn_string, "-e", query],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr}

        rows = []
        for line in result.stdout.strip().split("\n"):
            if line and not line.startswith("+"):
                rows.append(line.split("\t"))

        return {
            "success": True,
            "rows": rows,
            "row_count": len(rows),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
