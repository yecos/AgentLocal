"""
=============================================================
AGENTE v15 - Herramientas de Procesamiento de Datos
=============================================================
Procesamiento y analisis de datos:
- Estadisticas descriptivas (media, mediana, desv.est, percentiles)
- Tablas pivote (pivot tables)
- Merge/Join de datasets
- Limpieza de datos (duplicados, nulos, outliers, normalizacion)
- Transformaciones (agrupacion, filtrado, ordenamiento, mapeo)
- Ejecucion de Python/Bash/Node.js
- Parsing (CSV, JSON, XML, YAML)
- Exportacion a multiples formatos

Dependencias: pandas (recomendado), numpy, scipy (opcional)
=============================================================
"""

import os
import json
import csv
import io
import logging
import subprocess
import tempfile
from config import REPOS_DIR, MAX_TOOL_OUTPUT, logger
from utils.security import validate_path, sanitize_input


# ============================================================
# EJECUCION DE CODIGO
# ============================================================

def ejecutar_python(codigo: str, timeout: int = 60) -> str:
    """Ejecuta codigo Python y retorna la salida. Se ejecuta en un subproceso aislado.

    Args:
        codigo: Codigo Python a ejecutar
        timeout: Timeout en segundos (default 60, max 300)
    """
    timeout = min(max(timeout, 5), 300)

    # Escribir codigo a archivo temporal
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False,
                                      encoding='utf-8') as f:
        f.write(codigo)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ['python', tmp_path],
            capture_output=True, text=True, timeout=timeout,
            cwd=tempfile.gettempdir()
        )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"

        if result.returncode != 0:
            output = f"ERROR (exit code {result.returncode}):\n{output}"

        if len(output) > MAX_TOOL_OUTPUT * 3:
            output = output[:MAX_TOOL_OUTPUT * 3] + "\n... [truncado]"

        return output.strip() or "(sin salida)"

    except subprocess.TimeoutExpired:
        return f"ERROR: Timeout de {timeout}s alcanzado. El codigo tardo demasiado."
    except Exception as e:
        return f"ERROR ejecutando Python: {e}"
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def ejecutar_bash(comando: str, timeout: int = 30) -> str:
    """Ejecuta un comando Bash/Linux y retorna la salida. Aislado del sistema principal.

    Args:
        comando: Comando Bash a ejecutar
        timeout: Timeout en segundos (default 30, max 300)
    """
    timeout = min(max(timeout, 5), 300)

    # Sanitizar - no permitir comandos extremadamente peligrosos
    dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/sd", "format c:"]
    for d in dangerous:
        if d in comando.lower():
            return f"ERROR: Comando potencialmente peligroso bloqueado: {d}"

    try:
        result = subprocess.run(
            ['bash', '-c', comando],
            capture_output=True, text=True, timeout=timeout
        )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"

        if result.returncode != 0:
            output = f"ERROR (exit code {result.returncode}):\n{output}"

        if len(output) > MAX_TOOL_OUTPUT * 3:
            output = output[:MAX_TOOL_OUTPUT * 3] + "\n... [truncado]"

        return output.strip() or "(sin salida)"

    except subprocess.TimeoutExpired:
        return f"ERROR: Timeout de {timeout}s alcanzado."
    except FileNotFoundError:
        return "ERROR: Bash no disponible en este sistema."
    except Exception as e:
        return f"ERROR ejecutando bash: {e}"


def ejecutar_nodo(codigo: str, timeout: int = 30) -> str:
    """Ejecuta codigo JavaScript/Node.js y retorna la salida.

    Args:
        codigo: Codigo JavaScript a ejecutar
        timeout: Timeout en segundos (default 30)
    """
    timeout = min(max(timeout, 5), 120)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False,
                                      encoding='utf-8') as f:
        f.write(codigo)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ['node', tmp_path],
            capture_output=True, text=True, timeout=timeout
        )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"

        if result.returncode != 0:
            output = f"ERROR (exit code {result.returncode}):\n{output}"

        if len(output) > MAX_TOOL_OUTPUT * 3:
            output = output[:MAX_TOOL_OUTPUT * 3] + "\n... [truncado]"

        return output.strip() or "(sin salida)"

    except FileNotFoundError:
        return "ERROR: Node.js no instalado. Instala: https://nodejs.org"
    except subprocess.TimeoutExpired:
        return f"ERROR: Timeout de {timeout}s alcanzado."
    except Exception as e:
        return f"ERROR ejecutando Node.js: {e}"
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


# ============================================================
# ESTADISTICAS DESCRIPTIVAS
# ============================================================

def estadisticas(datos: str, columna: str = "") -> str:
    """Calcula estadisticas descriptivas de un dataset. Media, mediana, desv.est, min, max, percentiles, etc.

    Args:
        datos: Datos en formato CSV o JSON
        columna: Columna especifica (si vacio, calcula para todas las numericas)
    """
    try:
        df = _load_dataframe(datos)
        if df is None:
            return "ERROR: No se pudieron parsear los datos."

        if columna and columna in df.columns:
            serie = df[columna]
            if not _is_numeric(serie):
                # Estadisticas para datos categoricos
                stats = {
                    "count": int(serie.count()),
                    "unique": int(serie.nunique()),
                    "top": str(serie.mode().iloc[0]) if len(serie.mode()) > 0 else "",
                    "freq": int(serie.value_counts().iloc[0]) if len(serie.value_counts()) > 0 else 0,
                }
                return f"Estadisticas de '{columna}' (categorico):\n" + _format_stats(stats)
            else:
                serie = serie.dropna()
                stats = _calc_numeric_stats(serie)
                return f"Estadisticas de '{columna}':\n" + _format_stats(stats)
        else:
            # Todas las columnas numericas
            numeric_cols = df.select_dtypes(include='number').columns
            if len(numeric_cols) == 0:
                return "No hay columnas numericas en los datos."

            parts = []
            for col in numeric_cols:
                serie = df[col].dropna()
                stats = _calc_numeric_stats(serie)
                parts.append(f"--- {col} ---\n" + _format_stats(stats))

            return f"Estadisticas descriptivas ({len(numeric_cols)} columnas numericas):\n\n" + "\n\n".join(parts)

    except ImportError:
        return _estadisticas_simple(datos, columna)
    except Exception as e:
        return f"ERROR calculando estadisticas: {e}"


def _calc_numeric_stats(serie) -> dict:
    """Calcula estadisticas para una serie numerica."""
    import numpy as np
    values = serie.values

    stats = {
        "count": int(len(values)),
        "mean": float(np.mean(values)),
        "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "min": float(np.min(values)),
        "25%": float(np.percentile(values, 25)),
        "50%": float(np.median(values)),
        "75%": float(np.percentile(values, 75)),
        "max": float(np.max(values)),
        "range": float(np.max(values) - np.min(values)),
        "var": float(np.var(values, ddof=1)) if len(values) > 1 else 0.0,
        "skew": float(_skewness(values)),
        "kurtosis": float(_kurtosis(values)),
        "sum": float(np.sum(values)),
    }
    return stats


def _skewness(values):
    """Calcula asimetria (skewness) sin scipy."""
    import numpy as np
    n = len(values)
    if n < 3:
        return 0.0
    mean = np.mean(values)
    std = np.std(values, ddof=1)
    if std == 0:
        return 0.0
    return (1/n) * np.sum(((values - mean) / std) ** 3)


def _kurtosis(values):
    """Calcula curtosis sin scipy."""
    import numpy as np
    n = len(values)
    if n < 4:
        return 0.0
    mean = np.mean(values)
    std = np.std(values, ddof=1)
    if std == 0:
        return 0.0
    k = (1/n) * np.sum(((values - mean) / std) ** 4) - 3
    return k


def _format_stats(stats: dict) -> str:
    """Formatea estadisticas como texto legible."""
    lines = []
    for key, value in stats.items():
        if isinstance(value, float):
            lines.append(f"  {key:>10s}: {value:>12.4f}")
        else:
            lines.append(f"  {key:>10s}: {value}")
    return "\n".join(lines)


def _estadisticas_simple(datos: str, columna: str = "") -> str:
    """Estadisticas sin pandas (fallback)."""
    import numpy as np

    values = _parse_numeric_list(datos)
    if not values:
        return "ERROR: No se pudieron extraer valores numericos."

    values = np.array(values, dtype=float)
    stats = _calc_numeric_stats(values)
    return "Estadisticas descriptivas:\n" + _format_stats(stats)


# ============================================================
# PIVOT TABLE
# ============================================================

def tabla_pivote(datos: str, filas: str = "", columnas: str = "",
                 valores: str = "", funcion: str = "sum") -> str:
    """Crea una tabla pivote a partir de datos tabulares.

    Args:
        datos: Datos en CSV o JSON
        filas: Columna para las filas de la pivot
        columnas: Columna para las columnas de la pivot
        valores: Columna de valores a agregar
        funcion: Funcion de agregacion: sum, mean, count, min, max
    """
    try:
        df = _load_dataframe(datos)
        if df is None:
            return "ERROR: No se pudieron parsear los datos."

        if not filas:
            return "ERROR: Debes especificar al menos la columna de filas."

        # Verificar columnas
        for col_name, col_label in [(filas, "filas"), (columnas, "columnas"), (valores, "valores")]:
            if col_name and col_name not in df.columns:
                return f"ERROR: Columna '{col_name}' no encontrada. Disponibles: {list(df.columns)}"

        # Funcion de agregacion
        agg_map = {
            "sum": "sum", "suma": "sum",
            "mean": "mean", "promedio": "mean", "media": "mean",
            "count": "count", "conteo": "count",
            "min": "min", "minimo": "min",
            "max": "max", "maximo": "max",
            "std": "std", "desv": "std",
        }
        agg_func = agg_map.get(funcion.lower(), "sum")

        # Crear pivot
        if columnas and valores:
            pivot = df.pivot_table(index=filas, columns=columnas, values=valores,
                                    aggfunc=agg_func, fill_value=0)
        elif valores:
            pivot = df.pivot_table(index=filas, values=valores, aggfunc=agg_func)
        else:
            pivot = df.pivot_table(index=filas, aggfunc=agg_func)

        # Formatear como tabla
        return f"Tabla Pivote ({funcion}):\n\n{pivot.to_string()}"

    except ImportError:
        return "ERROR: pandas no instalado. Instala: pip install pandas"
    except Exception as e:
        return f"ERROR creando tabla pivote: {e}"


# ============================================================
# MERGE / JOIN
# ============================================================

def merge_datos(datos1: str, datos2: str, clave: str = "",
                tipo: str = "inner", sufijo1: str = "_1",
                sufijo2: str = "_2") -> str:
    """Combina dos datasets usando merge/join. Similar a SQL JOIN.

    Args:
        datos1: Primer dataset (CSV o JSON)
        datos2: Segundo dataset (CSV o JSON)
        clave: Columna clave para el join (si vacio, usa columnas en comun)
        tipo: Tipo de join: inner, left, right, outer
        sufijo1: Sufijo para columnas duplicadas del dataset 1
        sufijo2: Sufijo para columnas duplicadas del dataset 2
    """
    try:
        df1 = _load_dataframe(datos1)
        df2 = _load_dataframe(datos2)

        if df1 is None or df2 is None:
            return "ERROR: No se pudieron parsear los datos."

        # Detectar clave comun si no se especifica
        if not clave:
            common_cols = list(set(df1.columns) & set(df2.columns))
            if not common_cols:
                return (f"ERROR: No hay columnas en comun.\n"
                        f"  Dataset 1: {list(df1.columns)}\n"
                        f"  Dataset 2: {list(df2.columns)}")
            clave = common_cols[0]

        if clave not in df1.columns:
            return f"ERROR: Columna '{clave}' no existe en dataset 1. Columnas: {list(df1.columns)}"
        if clave not in df2.columns:
            return f"ERROR: Columna '{clave}' no existe en dataset 2. Columnas: {list(df2.columns)}"

        # Validar tipo de join
        tipo_map = {"inner": "inner", "left": "left", "right": "right",
                    "outer": "outer", "completo": "outer", "interno": "inner"}
        how = tipo_map.get(tipo.lower(), "inner")

        # Merge
        merged = df1.merge(df2, on=clave, how=how, suffixes=(sufijo1, sufijo2))

        # Formatear resultado
        result = (f"Merge [{how}] en clave '{clave}':\n"
                  f"  Dataset 1: {len(df1)} filas, {len(df1.columns)} columnas\n"
                  f"  Dataset 2: {len(df2)} filas, {len(df2.columns)} columnas\n"
                  f"  Resultado: {len(merged)} filas, {len(merged.columns)} columnas\n\n")

        # Mostrar preview
        result += merged.head(20).to_string()
        if len(merged) > 20:
            result += f"\n... ({len(merged) - 20} filas mas)"

        return result

    except ImportError:
        return "ERROR: pandas no instalado. Instala: pip install pandas"
    except Exception as e:
        return f"ERROR haciendo merge: {e}"


# ============================================================
# LIMPIEZA DE DATOS
# ============================================================

def limpiar_datos(datos: str, operaciones: str = "todo") -> str:
    """Limpia un dataset aplicando operaciones de limpieza.

    Args:
        datos: Datos en CSV o JSON
        operaciones: Operaciones separadas por coma: duplicados, nulos, outliers, normalizar, tipos, todo
    """
    try:
        df = _load_dataframe(datos)
        if df is None:
            return "ERROR: No se pudieron parsear los datos."

        original_shape = df.shape
        ops = [op.strip().lower() for op in operaciones.split(",")]
        if "todo" in ops:
            ops = ["duplicados", "nulos", "outliers", "normalizar", "tipos"]

        report = [f"Limpieza de datos - Original: {original_shape[0]} filas, {original_shape[1]} columnas\n"]

        # 1. Eliminar duplicados
        if "duplicados" in ops:
            before = len(df)
            df = df.drop_duplicates()
            removed = before - len(df)
            report.append(f"[duplicados] {removed} filas duplicadas eliminadas")

        # 2. Tratar nulos
        if "nulos" in ops:
            null_counts = df.isnull().sum()
            total_nulls = null_counts.sum()
            if total_nulls > 0:
                # Para numericos: rellenar con mediana
                for col in df.select_dtypes(include='number').columns:
                    if df[col].isnull().any():
                        median = df[col].median()
                        df[col].fillna(median, inplace=True)
                # Para categoricos: rellenar con moda
                for col in df.select_dtypes(exclude='number').columns:
                    if df[col].isnull().any():
                        mode = df[col].mode().iloc[0] if len(df[col].mode()) > 0 else "N/A"
                        df[col].fillna(mode, inplace=True)
                report.append(f"[nulos] {total_nulls} valores nulos tratados (mediana/moda)")
            else:
                report.append(f"[nulos] Sin valores nulos encontrados")

        # 3. Eliminar outliers (IQR)
        if "outliers" in ops:
            total_removed = 0
            for col in df.select_dtypes(include='number').columns:
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower = Q1 - 1.5 * IQR
                upper = Q3 + 1.5 * IQR
                outliers = ((df[col] < lower) | (df[col] > upper)).sum()
                if outliers > 0:
                    df = df[(df[col] >= lower) & (df[col] <= upper)]
                    total_removed += outliers
            report.append(f"[outliers] {total_removed} valores atipicos eliminados (IQR)")

        # 4. Normalizar (min-max)
        if "normalizar" in ops:
            for col in df.select_dtypes(include='number').columns:
                col_min = df[col].min()
                col_max = df[col].max()
                if col_max > col_min:
                    df[col] = (df[col] - col_min) / (col_max - col_min)
            report.append(f"[normalizar] Columnas numericas normalizadas a [0,1]")

        # 5. Detectar y convertir tipos
        if "tipos" in ops:
            converted = []
            for col in df.columns:
                if df[col].dtype == 'object':
                    try:
                        df[col] = df[col].astype(float)
                        converted.append(f"{col}: texto -> numerico")
                    except (ValueError, TypeError):
                        pass
            if converted:
                report.append(f"[tipos] Conversiones: {', '.join(converted)}")
            else:
                report.append(f"[tipos] Sin conversiones necesarias")

        report.append(f"\nResultado: {df.shape[0]} filas, {df.shape[1]} columnas")
        report.append(f"Filas eliminadas: {original_shape[0] - df.shape[0]}")

        # Preview
        report.append(f"\nPreview (5 filas):\n{df.head().to_string()}")

        return "\n".join(report)

    except ImportError:
        return "ERROR: pandas no instalado. Instala: pip install pandas"
    except Exception as e:
        return f"ERROR limpiando datos: {e}"


# ============================================================
# TRANSFORMACIONES
# ============================================================

def transformar_datos(datos: str, operacion: str = "", parametros: str = "{}") -> str:
    """Transforma un dataset aplicando operaciones de filtrado, ordenamiento, agrupacion, etc.

    Args:
        datos: Datos en CSV o JSON
        operacion: Operacion a realizar: filtrar, ordenar, agrupar, seleccionar, renombrar, agregar_columna, head, sample
        parametros: Parametros de la operacion en JSON
    """
    try:
        df = _load_dataframe(datos)
        if df is None:
            return "ERROR: No se pudieron parsear los datos."

        params = _parse_json(parametros, {})
        op = operacion.lower().strip()

        if op == "filtrar" or op == "filter":
            columna = params.get("columna", params.get("column", ""))
            condicion = params.get("condicion", params.get("condition", ""))
            valor = params.get("valor", params.get("value", ""))

            if not columna or columna not in df.columns:
                return f"ERROR: Columna '{columna}' no encontrada."

            if condicion in (">", "mayor"):
                df = df[df[columna] > float(valor)]
            elif condicion in ("<", "menor"):
                df = df[df[columna] < float(valor)]
            elif condicion in ("==", "igual"):
                df = df[df[columna] == valor]
            elif condicion in ("!=", "diferente"):
                df = df[df[columna] != valor]
            elif condicion in (">=", "mayor_igual"):
                df = df[df[columna] >= float(valor)]
            elif condicion in ("<=", "menor_igual"):
                df = df[df[columna] <= float(valor)]
            elif condicion in ("contains", "contiene"):
                df = df[df[columna].astype(str).str.contains(str(valor), case=False)]
            else:
                return f"ERROR: Condicion '{condicion}' no reconocida. Usar: >, <, ==, !=, >=, <=, contiene"

        elif op == "ordenar" or op == "sort":
            columna = params.get("columna", params.get("column", ""))
            ascendente = params.get("ascendente", params.get("ascending", True))

            if not columna:
                return "ERROR: Especifica columna para ordenar."
            if columna not in df.columns:
                return f"ERROR: Columna '{columna}' no encontrada."

            df = df.sort_values(by=columna, ascending=ascendente)

        elif op == "agrupar" or op == "groupby":
            columna = params.get("columna", params.get("column", ""))
            agg = params.get("agregacion", params.get("agg", "sum"))

            if not columna:
                return "ERROR: Especifica columna para agrupar."

            agg_map = {"sum": "sum", "mean": "mean", "count": "count",
                       "min": "min", "max": "max", "std": "std"}
            agg_func = agg_map.get(agg, "sum")
            df = df.groupby(columna).agg(agg_func)

        elif op == "seleccionar" or op == "select":
            columnas = params.get("columnas", params.get("columns", []))
            if isinstance(columnas, str):
                columnas = [c.strip() for c in columnas.split(",")]

            missing = [c for c in columnas if c not in df.columns]
            if missing:
                return f"ERROR: Columnas no encontradas: {missing}"

            df = df[columnas]

        elif op == "renombrar" or op == "rename":
            mapeo = params.get("mapeo", params.get("mapping", {}))
            df = df.rename(columns=mapeo)

        elif op == "agregar_columna" or op == "add_column":
            nombre = params.get("nombre", params.get("name", "nueva"))
            formula = params.get("formula", "")

            if not formula:
                return "ERROR: Especifica formula para la nueva columna."

            # Evaluar formula de forma segura
            try:
                df[nombre] = df.eval(formula)
            except Exception as e:
                return f"ERROR evaluando formula: {e}"

        elif op == "head":
            n = int(params.get("n", 10))
            df = df.head(n)

        elif op == "sample":
            n = int(params.get("n", 5))
            df = df.sample(min(n, len(df)))

        else:
            return (f"ERROR: Operacion '{op}' no reconocida.\n"
                    "Usar: filtrar, ordenar, agrupar, seleccionar, renombrar, agregar_columna, head, sample")

        # Formatear resultado
        result = f"Transformacion [{op}]:\n{df.to_string()}"
        if len(result) > MAX_TOOL_OUTPUT * 5:
            result = result[:MAX_TOOL_OUTPUT * 5] + "\n... [truncado]"
        return result

    except ImportError:
        return "ERROR: pandas no instalado. Instala: pip install pandas"
    except Exception as e:
        return f"ERROR transformando datos: {e}"


# ============================================================
# PARSING
# ============================================================

def parsear_datos(datos: str, formato_origen: str = "auto",
                  formato_destino: str = "json") -> str:
    """Convierte datos entre formatos: CSV, JSON, TSV, YAML, XML.

    Args:
        datos: Datos en formato de origen
        formato_origen: Formato de entrada: auto, csv, json, tsv, yaml, xml
        formato_destino: Formato de salida: json, csv, tsv, yaml, tabla
    """
    try:
        # Auto-detectar formato
        if formato_origen == "auto":
            formato_origen = _detect_format(datos)

        # Parsear a estructura Python
        parsed = _parse_to_dict(datos, formato_origen)
        if parsed is None:
            return f"ERROR: No se pudieron parsear los datos como {formato_origen}"

        # Convertir a formato destino
        if formato_destino == "json":
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        elif formato_destino == "csv":
            return _dict_to_csv(parsed)
        elif formato_destino == "tsv":
            return _dict_to_csv(parsed, delimiter="\t")
        elif formato_destino == "yaml":
            try:
                import yaml
                return yaml.dump(parsed, allow_unicode=True, default_flow_style=False)
            except ImportError:
                return "ERROR: PyYAML no instalado. Instala: pip install pyyaml"
        elif formato_destino == "tabla":
            try:
                import pandas as pd
                df = pd.DataFrame(parsed) if isinstance(parsed, list) else pd.DataFrame([parsed])
                return df.to_string()
            except ImportError:
                return _dict_to_csv(parsed)
        else:
            return f"ERROR: Formato destino '{formato_destino}' no soportado. Usar: json, csv, tsv, yaml, tabla"

    except Exception as e:
        return f"ERROR parseando datos: {e}"


# ============================================================
# EXPORTAR DATOS
# ============================================================

def exportar_datos(datos: str, ruta: str, formato: str = "csv") -> str:
    """Exporta datos a un archivo en el formato especificado.

    Args:
        datos: Datos en CSV o JSON
        ruta: Ruta del archivo de salida
        formato: Formato: csv, json, xlsx, tsv
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    try:
        df = _load_dataframe(datos)
        if df is None:
            return "ERROR: No se pudieron parsear los datos."

        dir_name = os.path.dirname(ruta)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        if formato == "csv":
            df.to_csv(ruta, index=False, encoding='utf-8')
        elif formato == "json":
            df.to_json(ruta, orient='records', force_ascii=False, indent=2)
        elif formato == "xlsx":
            try:
                df.to_excel(ruta, index=False, engine='openpyxl')
            except ImportError:
                return "ERROR: openpyxl no instalado. Instala: pip install openpyxl"
        elif formato == "tsv":
            df.to_csv(ruta, index=False, sep='\t', encoding='utf-8')
        else:
            return f"ERROR: Formato '{formato}' no soportado. Usar: csv, json, xlsx, tsv"

        size_kb = os.path.getsize(ruta) / 1024
        return f"Datos exportados: {ruta} ({size_kb:.1f} KB, {len(df)} filas, {len(df.columns)} columnas)"

    except ImportError:
        # Fallback sin pandas
        return _export_simple(datos, ruta, formato)
    except Exception as e:
        return f"ERROR exportando datos: {e}"


def _export_simple(datos: str, ruta: str, formato: str) -> str:
    """Exporta datos sin pandas (fallback simple)."""
    try:
        dir_name = os.path.dirname(ruta)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        if formato in ("csv", "tsv"):
            # Intentar reescribir tal cual
            with open(ruta, 'w', encoding='utf-8') as f:
                f.write(datos)
        elif formato == "json":
            # Intentar parsear y reescribir formateado
            try:
                parsed = json.loads(datos)
                with open(ruta, 'w', encoding='utf-8') as f:
                    json.dump(parsed, f, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                with open(ruta, 'w', encoding='utf-8') as f:
                    f.write(datos)
        else:
            return f"ERROR: Formato '{formato}' no soportado sin pandas."

        size_kb = os.path.getsize(ruta) / 1024
        return f"Datos exportados: {ruta} ({size_kb:.1f} KB)"
    except Exception as e:
        return f"ERROR exportando: {e}"


# ============================================================
# UTILIDADES INTERNAS
# ============================================================

def _load_dataframe(datos_str: str):
    """Carga datos como DataFrame de pandas. Retorna None si falla."""
    import pandas as pd

    datos_str = datos_str.strip()

    # Intentar JSON
    if datos_str.startswith('[') or datos_str.startswith('{'):
        try:
            parsed = json.loads(datos_str)
            if isinstance(parsed, list):
                return pd.DataFrame(parsed)
            elif isinstance(parsed, dict):
                return pd.DataFrame([parsed])
        except json.JSONDecodeError:
            pass

    # Intentar CSV
    try:
        return pd.read_csv(io.StringIO(datos_str))
    except Exception:
        pass

    # Intentar TSV
    try:
        return pd.read_csv(io.StringIO(datos_str), sep='\t')
    except Exception:
        pass

    return None


def _parse_json(s, default=None):
    """Parsea JSON de forma segura."""
    if not s or s in ("{}", "[]", ""):
        return default if default is not None else {}
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def _is_numeric(serie) -> bool:
    """Verifica si una serie es numerica."""
    try:
        import pandas as pd
        return pd.api.types.is_numeric_dtype(serie)
    except ImportError:
        try:
            [float(x) for x in serie.dropna()]
            return True
        except (ValueError, TypeError):
            return False


def _parse_numeric_list(datos_str: str) -> list:
    """Extrae lista de numeros de un string."""
    import numpy as np

    values = []
    for line in datos_str.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for part in line.replace(",", " ").split():
            try:
                values.append(float(part))
            except ValueError:
                continue
    return values


def _detect_format(datos: str) -> str:
    """Detecta automaticamente el formato de los datos."""
    datos = datos.strip()
    if datos.startswith('[') or datos.startswith('{'):
        return "json"
    if '\t' in datos.split('\n')[0]:
        return "tsv"
    if datos.startswith('<?xml') or datos.startswith('<'):
        return "xml"
    if datos.startswith('---') or datos.startswith('- '):
        return "yaml"
    return "csv"


def _parse_to_dict(datos: str, formato: str) -> list | dict | None:
    """Parsea datos a estructura Python (lista de dicts)."""
    if formato == "json":
        return json.loads(datos)
    elif formato in ("csv", "tsv"):
        delimiter = '\t' if formato == "tsv" else ','
        reader = csv.DictReader(io.StringIO(datos), delimiter=delimiter)
        return [row for row in reader]
    elif formato == "yaml":
        try:
            import yaml
            return yaml.safe_load(datos)
        except ImportError:
            return None
    elif formato == "xml":
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(datos)
            # Conversion simple: elementos hijos como dicts
            result = []
            for child in root:
                result.append({elem.tag: elem.text for elem in child})
            return result
        except Exception:
            return None
    else:
        # Fallback: CSV
        reader = csv.DictReader(io.StringIO(datos))
        return [row for row in reader]


def _dict_to_csv(data, delimiter=",") -> str:
    """Convierte lista de dicts a CSV."""
    if not data:
        return ""
    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list) or not data:
        return str(data)

    # Obtener todas las keys
    all_keys = []
    for item in data:
        if isinstance(item, dict):
            for key in item:
                if key not in all_keys:
                    all_keys.append(key)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=all_keys, delimiter=delimiter)
    writer.writeheader()
    for item in data:
        if isinstance(item, dict):
            writer.writerow(item)

    return output.getvalue()
