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
        if "ACCESO DENEGADO" in str(validated):
            return {"success": False, "error": validated, "connection_id": None}
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


# ============================================================
# CONSULTA EN LENGUAJE NATURAL
# ============================================================

# Keywords that are NEVER allowed in NL->SQL conversion
_SQL_BLOCKED_KEYWORDS = [
    "DROP", "DELETE", "TRUNCATE", "ALTER", "UPDATE", "INSERT",
    "REPLACE", "CREATE", "ATTACH", "DETACH", "VACUUM", "REINDEX",
]


def query_natural_language(pregunta: str, tabla: str = "", db_path: str = "") -> str:
    """Consulta una base de datos en lenguaje natural. Convierte la pregunta a SQL, la ejecuta (solo SELECT) y formatea resultados.

    Args:
        pregunta: Pregunta en lenguaje natural sobre los datos
        tabla: Nombre de la tabla (opcional, ayuda al LLM a generar mejor SQL)
        db_path: Ruta al archivo de base de datos SQLite
    """
    if not pregunta:
        return "ERROR: Debes proporcionar una pregunta."

    if not db_path:
        return "ERROR: Debes indicar la ruta de la base de datos (db_path)."

    # Validar ruta
    validated = validate_path(db_path)
    if "ACCESO DENEGADO" in str(validated):
        return f"ERROR: {validated}"
    if not os.path.exists(validated):
        return f"ERROR: Base de datos no encontrada: {db_path}"

    # Obtener schema de la tabla (o de todas las tablas) para ayudar al LLM
    schema_info = _get_schema_for_llm(validated, tabla)

    # Generar SQL con el LLM
    sql = _generate_sql_from_question(pregunta, schema_info, tabla)

    if not sql:
        return "ERROR: No se pudo generar una consulta SQL a partir de la pregunta."

    # Safety: verify only SELECT / PRAGMA
    sql_upper = sql.strip().upper()
    for kw in _SQL_BLOCKED_KEYWORDS:
        if kw in sql_upper.split():
            return f"ERROR: Por seguridad, solo se permiten consultas SELECT. Se detecto: {kw}"

    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("PRAGMA")):
        return "ERROR: Por seguridad, solo se permiten consultas SELECT o PRAGMA."

    # Ejecutar
    result = db_query(sql, db_path=validated)

    if not result.get("success"):
        return f"ERROR ejecutando consulta: {result.get('error', 'Error desconocido')}\nSQL generado: {sql}"

    # Formatear resultados como tabla legible
    rows = result.get("rows", [])
    columns = result.get("columns", [])

    if not rows:
        return f"La consulta no retorno resultados.\nSQL generado: {sql}"

    # Format as readable table
    output_parts = [
        f"Resultados ({len(rows)} filas):",
        f"SQL generado: {sql}",
        "",
    ]

    # Table formatting
    if columns and rows:
        # Determine column widths
        col_widths = [max(len(str(c)), 3) for c in columns]
        for row in rows[:50]:
            if isinstance(row, dict):
                for i, col in enumerate(columns):
                    val = str(row.get(col, ""))
                    col_widths[i] = max(col_widths[i], min(len(val), 40))
            elif isinstance(row, (list, tuple)):
                for i, val in enumerate(row):
                    if i < len(col_widths):
                        col_widths[i] = max(col_widths[i], min(len(str(val)), 40))

        # Header
        header = " | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(columns))
        separator = "-+-".join("-" * w for w in col_widths)
        output_parts.append(header)
        output_parts.append(separator)

        # Rows
        for row in rows[:50]:
            if isinstance(row, dict):
                vals = [str(row.get(col, ""))[:40].ljust(col_widths[i]) for i, col in enumerate(columns)]
            elif isinstance(row, (list, tuple)):
                vals = [str(v)[:40].ljust(col_widths[i]) if i < len(col_widths) else str(v)[:40]
                        for i, v in enumerate(row)]
            else:
                vals = [str(row)[:40]]
            output_parts.append(" | ".join(vals))

        if len(rows) > 50:
            output_parts.append(f"... y {len(rows) - 50} filas mas")

    return "\n".join(output_parts)


def _get_schema_for_llm(db_path: str, table_name: str = "") -> str:
    """Obtiene informacion del schema de la BD para ayudar al LLM."""
    parts = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if table_name:
            tables = [table_name]
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row[0] for row in cursor.fetchall()]

        for tbl in tables[:10]:  # Limitar a 10 tablas
            cursor.execute(f"PRAGMA table_info({tbl})")
            cols = cursor.fetchall()
            col_info = ", ".join(f"{c[1]} ({c[2]})" for c in cols)
            parts.append(f"Tabla '{tbl}': {col_info}")

            # Sample row
            try:
                cursor.execute(f"SELECT * FROM {tbl} LIMIT 1")
                sample = cursor.fetchone()
                if sample:
                    parts.append(f"  Ejemplo: {sample}")
            except Exception:
                pass

        conn.close()
    except Exception as e:
        parts.append(f"Error obteniendo schema: {e}")

    return "\n".join(parts)


def _generate_sql_from_question(pregunta: str, schema_info: str, tabla: str = "") -> str:
    """Usa el LLM para convertir una pregunta en lenguaje natural a SQL."""
    try:
        from llm import ollama

        table_hint = f"Tabla principal: {tabla}" if tabla else ""
        prompt = (
            "Eres un experto en SQL. Convierte la siguiente pregunta en lenguaje natural "
            "a una consulta SQL para SQLite. SOLO genera la consulta SQL, sin explicaciones.\n\n"
            f"Schema de la base de datos:\n{schema_info}\n\n"
            f"{table_hint}\n\n"
            f"Pregunta: {pregunta}\n\n"
            "REGLAS:\n"
            "- Solo genera SELECT, nunca INSERT/UPDATE/DELETE/DROP\n"
            "- Usa LIMIT 100 si no hay limite explicito\n"
            "- Responde SOLO con la consulta SQL, sin markdown ni explicaciones"
        )

        messages = [{"role": "user", "content": prompt}]
        response = ollama.generate_chat(messages)

        if not response:
            return ""

        # Clean up response - extract SQL
        sql = str(response).strip()

        # Remove markdown code blocks if present
        if sql.startswith("```"):
            lines = sql.split("\n")
            sql_lines = []
            in_code = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_code = not in_code
                    continue
                if in_code or not line.strip().startswith("```"):
                    sql_lines.append(line)
            sql = "\n".join(sql_lines).strip()

        # Remove trailing semicolon
        sql = sql.rstrip(";").strip()

        return sql

    except Exception as e:
        logger.error(f"Error generando SQL desde pregunta: {e}")
        return ""


# ============================================================
# S6.4: DATABASE MIGRATIONS
# ============================================================

_MIGRATIONS_DIR = os.path.join(REPOS_DIR, "db_migrations")

def db_migrate(
    db_path: str,
    accion: str = "status",
    migracion_id: str = "",
    sql_up: str = "",
    sql_down: str = "",
    descripcion: str = ""
) -> str:
    """S6.4: Gestiona migraciones de esquema de base de datos SQLite.

    Permite crear, aplicar y revertir migraciones de forma controlada:
    - create: Crea una nueva migracion con SQL up/down
    - up: Aplica la siguiente migracion pendiente (o una especifica)
    - down: Revierte una migracion especifica
    - status: Muestra el estado de las migraciones
    - generate: Genera SQL de migracion comparando tablas existentes vs deseadas

    Args:
        db_path: Ruta a la base de datos SQLite
        accion: Accion a ejecutar: create, up, down, status, generate
        migracion_id: ID de migracion para up/down especifico
        sql_up: SQL para aplicar la migracion (accion=create)
        sql_down: SQL para revertir la migracion (accion=create)
        descripcion: Descripcion de la migracion

    Returns:
        Resultado de la operacion de migracion
    """
    validation = validate_path(db_path)
    if validation != db_path:
        return validation

    # Asegurar directorio de migraciones
    os.makedirs(_MIGRATIONS_DIR, exist_ok=True)

    # Asegurar tabla de migraciones en la DB
    _ensure_migrations_table(db_path)

    if accion == "create":
        return _create_migration(sql_up, sql_down, descripcion)
    elif accion == "up":
        return _apply_migration(db_path, migracion_id)
    elif accion == "down":
        return _rollback_migration(db_path, migracion_id)
    elif accion == "status":
        return _migration_status(db_path)
    elif accion == "generate":
        return _generate_migration_sql(db_path, descripcion)
    else:
        return f"ERROR: Accion '{accion}' no reconocida. Usa: create, up, down, status, generate"


def _ensure_migrations_table(db_path: str):
    """Crea la tabla de tracking de migraciones si no existe."""
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id TEXT PRIMARY KEY,
                descripcion TEXT,
                sql_up TEXT,
                sql_down TEXT,
                applied_at TEXT,
                rolled_back_at TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"Error creando tabla de migraciones: {e}")


def _create_migration(sql_up: str, sql_down: str, descripcion: str) -> str:
    """Crea un archivo de migracion."""
    from datetime import datetime as _dt

    if not sql_up:
        return "ERROR: Debes proporcionar sql_up con el SQL para aplicar la migracion."

    # Generar ID de migracion
    migration_id = _dt.now().strftime("%Y%m%d_%H%M%S")
    if descripcion:
        # Slug de la descripcion
        slug = re.sub(r'[^a-z0-9]+', '_', descripcion.lower())[:30].strip('_')
        migration_id += f"_{slug}"

    # Guardar archivo de migracion
    migration_file = os.path.join(_MIGRATIONS_DIR, f"{migration_id}.json")
    migration_data = {
        "id": migration_id,
        "descripcion": descripcion,
        "sql_up": sql_up,
        "sql_down": sql_down or "-- No rollback SQL provided",
        "created_at": _dt.now().isoformat(),
    }

    try:
        with open(migration_file, "w", encoding="utf-8") as f:
            json.dump(migration_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"ERROR guardando migracion: {e}"

    return (
        f"Migracion creada exitosamente.\n"
        f"ID: {migration_id}\n"
        f"Descripcion: {descripcion or '(sin descripcion)'}\n"
        f"SQL UP: {sql_up[:100]}{'...' if len(sql_up) > 100 else ''}\n"
        f"SQL DOWN: {sql_down[:100] if sql_down else '(no proporcionado)'}\n"
        f"Para aplicar: db_migrate(db_path='{db_path}', accion='up', migracion_id='{migration_id}')"
    )


def _apply_migration(db_path: str, migration_id: str = "") -> str:
    """Aplica la siguiente migracion pendiente o una especifica."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)

        # Encontrar migraciones pendientes
        if migration_id:
            # Aplicar migracion especifica
            migration_file = os.path.join(_MIGRATIONS_DIR, f"{migration_id}.json")
            if not os.path.exists(migration_file):
                # Buscar en la tabla de migraciones
                cursor = conn.execute(
                    "SELECT id, sql_up FROM _migrations WHERE id = ? AND status = 'pending'",
                    (migration_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return f"ERROR: Migracion '{migration_id}' no encontrada o ya aplicada."
                sql_up = row[1]
            else:
                with open(migration_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sql_up = data["sql_up"]
                migration_id = data["id"]
        else:
            # Aplicar la siguiente pendiente
            # Buscar archivos de migracion no aplicados
            applied = set()
            cursor = conn.execute("SELECT id FROM _migrations WHERE status = 'applied'")
            for row in cursor.fetchall():
                applied.add(row[0])

            pending = []
            if os.path.exists(_MIGRATIONS_DIR):
                for fname in sorted(os.listdir(_MIGRATIONS_DIR)):
                    if fname.endswith(".json"):
                        mid = fname[:-5]
                        if mid not in applied:
                            pending.append(mid)

            if not pending:
                return "No hay migraciones pendientes por aplicar."

            # Aplicar la primera pendiente
            migration_id = pending[0]
            migration_file = os.path.join(_MIGRATIONS_DIR, f"{migration_id}.json")
            with open(migration_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            sql_up = data["sql_up"]

        # Ejecutar migracion en transaccion
        try:
            conn.execute("BEGIN")
            for statement in sql_up.split(";"):
                statement = statement.strip()
                if statement:
                    conn.execute(statement)

            # Registrar migracion aplicada
            from datetime import datetime as _dt
            conn.execute(
                "INSERT OR REPLACE INTO _migrations (id, sql_up, sql_down, applied_at, status) VALUES (?, ?, ?, ?, 'applied')",
                (migration_id, sql_up, "", _dt.now().isoformat())
            )
            conn.execute("COMMIT")

            return f"Migracion '{migration_id}' aplicada exitosamente."

        except Exception as e:
            conn.execute("ROLLBACK")
            return f"ERROR aplicando migracion '{migration_id}': {e}\nLa migracion fue revertida (rollback)."

    except Exception as e:
        return f"ERROR: {e}"
    finally:
        if conn:
            conn.close()


def _rollback_migration(db_path: str, migration_id: str) -> str:
    """Revierte una migracion especifica."""
    if not migration_id:
        return "ERROR: Debes especificar el migracion_id a revertir."

    conn = None
    try:
        conn = sqlite3.connect(db_path)

        # Verificar que la migracion fue aplicada
        cursor = conn.execute(
            "SELECT id, sql_down FROM _migrations WHERE id = ? AND status = 'applied'",
            (migration_id,)
        )
        row = cursor.fetchone()

        if not row:
            # Buscar en archivos
            migration_file = os.path.join(_MIGRATIONS_DIR, f"{migration_id}.json")
            if not os.path.exists(migration_file):
                return f"ERROR: Migracion '{migration_id}' no encontrada o no fue aplicada."

            with open(migration_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            sql_down = data.get("sql_down", "")
        else:
            sql_down = row[1]

        if not sql_down or sql_down.startswith("--"):
            return f"ERROR: No hay SQL de rollback para la migracion '{migration_id}'."

        # Ejecutar rollback en transaccion
        try:
            conn.execute("BEGIN")
            for statement in sql_down.split(";"):
                statement = statement.strip()
                if statement and not statement.startswith("--"):
                    conn.execute(statement)

            # Actualizar estado
            from datetime import datetime as _dt
            conn.execute(
                "UPDATE _migrations SET status = 'rolled_back', rolled_back_at = ? WHERE id = ?",
                (_dt.now().isoformat(), migration_id)
            )
            conn.execute("COMMIT")

            return f"Migracion '{migration_id}' revertida exitosamente."

        except Exception as e:
            conn.execute("ROLLBACK")
            return f"ERROR revirtiendo migracion '{migration_id}': {e}\nEl rollback fallo, datos pueden estar en estado inconsistente."

    except Exception as e:
        return f"ERROR: {e}"
    finally:
        if conn:
            conn.close()


def _migration_status(db_path: str) -> str:
    """Muestra el estado de todas las migraciones."""
    try:
        conn = sqlite3.connect(db_path)

        # Obtener migraciones aplicadas de la DB
        cursor = conn.execute(
            "SELECT id, descripcion, status, applied_at FROM _migrations ORDER BY id"
        )
        applied = {row[0]: {"desc": row[1], "status": row[2], "applied_at": row[3]} for row in cursor.fetchall()}
        conn.close()

        # Obtener todas las migraciones de archivos
        all_migrations = []
        if os.path.exists(_MIGRATIONS_DIR):
            for fname in sorted(os.listdir(_MIGRATIONS_DIR)):
                if fname.endswith(".json"):
                    try:
                        with open(os.path.join(_MIGRATIONS_DIR, fname), "r", encoding="utf-8") as f:
                            data = json.load(f)
                        mid = data["id"]
                        db_info = applied.get(mid, {})
                        all_migrations.append({
                            "id": mid,
                            "descripcion": data.get("descripcion", ""),
                            "status": db_info.get("status", "pending"),
                            "applied_at": db_info.get("applied_at", ""),
                        })
                    except Exception:
                        continue

        # Agregar las que solo estan en la DB (no tienen archivo)
        for mid, info in applied.items():
            if not any(m["id"] == mid for m in all_migrations):
                all_migrations.append({
                    "id": mid,
                    "descripcion": info.get("desc", ""),
                    "status": info["status"],
                    "applied_at": info.get("applied_at", ""),
                })

        if not all_migrations:
            return "No hay migraciones registradas."

        # Formatear
        lines = [f"Estado de migraciones ({len(all_migrations)} total):\n"]
        for m in sorted(all_migrations, key=lambda x: x["id"]):
            status_icon = {"applied": "OK", "pending": "..", "rolled_back": "XX"}.get(m["status"], "??")
            lines.append(
                f"  [{status_icon}] {m['id']}: {m.get('descripcion', '(sin descripcion)')}"
                f"{' (aplicada: ' + m['applied_at'][:10] + ')' if m.get('applied_at') else ''}"
            )

        applied_count = sum(1 for m in all_migrations if m["status"] == "applied")
        pending_count = sum(1 for m in all_migrations if m["status"] == "pending")

        lines.append(f"\nResumen: {applied_count} aplicadas, {pending_count} pendientes")

        return "\n".join(lines)

    except Exception as e:
        return f"ERROR obteniendo estado: {e}"


def _generate_migration_sql(db_path: str, descripcion: str = "") -> str:
    """Genera SQL de migracion comparando tablas existentes vs lo que se necesita.

    Usa LLM para generar el SQL de migracion basado en la descripcion
    de los cambios deseados y el esquema actual de la base de datos.
    """
    try:
        # Obtener esquema actual
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != '_migrations'"
        )
        tables = cursor.fetchall()
        conn.close()

        schema_info = "\n".join([f"TABLE {t[0]}:\n{t[1]}" for t in tables if t[1]])

        if not descripcion:
            return (
                f"Esquema actual de la base de datos:\n\n{schema_info}\n\n"
                f"Proporciona una descripcion de los cambios que necesitas para generar la migracion."
            )

        # Usar LLM para generar SQL
        from llm import ollama
        prompt = (
            f"Eres un experto en SQL para SQLite. Genera SQL de migracion para los siguientes cambios:\n\n"
            f"ESQUEMA ACTUAL:\n{schema_info}\n\n"
            f"CAMBIOS SOLICITADOS: {descripcion}\n\n"
            f"Genera DOS bloques SQL:\n"
            f"1. SQL_UP: Sentencias SQL para APLICAR la migracion\n"
            f"2. SQL_DOWN: Sentencias SQL para REVERTIR la migracion\n\n"
            f"Formato de respuesta:\n"
            f"```sql_up\n...SQL para aplicar...\n```\n"
            f"```sql_down\n...SQL para revertir...\n```"
        )

        messages = [{"role": "user", "content": prompt}]
        response = ollama.generate_chat(messages)
        result = str(response).strip() if response else ""

        if not result:
            return "ERROR: No se pudo generar SQL de migracion."

        # Parsear resultado
        sql_up = ""
        sql_down = ""
        if "```sql_up" in result:
            parts = result.split("```sql_up")
            if len(parts) > 1:
                sql_up = parts[1].split("```")[0].strip()
        if "```sql_down" in result:
            parts = result.split("```sql_down")
            if len(parts) > 1:
                sql_down = parts[1].split("```")[0].strip()

        if not sql_up:
            # Fallback: usar todo el resultado como sql_up
            sql_up = result
            sql_down = ""

        output = (
            f"SQL de migracion generado para: {descripcion}\n\n"
            f"== SQL UP (aplicar) ==\n{sql_up}\n\n"
            f"== SQL DOWN (revertir) ==\n{sql_down or '-- No se genero SQL de rollback'}\n\n"
            f"Para crear la migracion:\n"
            f"db_migrate(db_path='{db_path}', accion='create', sql_up='''{sql_up[:200]}''', sql_down='''{sql_down[:200] if sql_down else ''}''', descripcion='{descripcion}')"
        )

        return output

    except Exception as e:
        return f"ERROR generando migracion: {e}"
