"""
=============================================================
AGENTE v14.7 - Herramientas de Documentos (Super Agente)
=============================================================
Lectura y extraccion de texto de documentos de todo tipo:
- PDF (PyMuPDF / pdfplumber / comando)
- DOCX (python-docx / comando)
- XLSX (openpyxl / comando)
- PPTX (python-pptx / comando)
- CSV estructurado
- RTF, ePub

Cada herramienta intenta primero la libreria Python,
y si no esta instalada, hace fallback a comandos del sistema.
=============================================================
"""

import os
import csv
import io
import logging
from config import REPOS_DIR, MAX_FILE_READ, MAX_TOOL_OUTPUT, logger
from utils.security import validate_path


# ============================================================
# LECTURA DE PDF
# ============================================================

def leer_pdf(ruta: str, pagina_inicio: int = None, pagina_fin: int = None) -> str:
    """Lee el contenido de un archivo PDF. Extrae texto, tablas e info de paginas.

    Args:
        ruta: Ruta del archivo PDF
        pagina_inicio: Pagina inicial (1-indexed, opcional)
        pagina_fin: Pagina final (inclusive, opcional)
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    ruta = _resolve_path(ruta)
    if not ruta:
        return f"Archivo no encontrado: {ruta}"

    if not ruta.lower().endswith('.pdf'):
        return "ERROR: El archivo no es un PDF."

    # Intentar con PyMuPDF (fitz)
    result = _leer_pdf_fitz(ruta, pagina_inicio, pagina_fin)
    if result is not None:
        return result

    # Intentar con pdfplumber
    result = _leer_pdf_plumber(ruta, pagina_inicio, pagina_fin)
    if result is not None:
        return result

    # Fallback: comando pdftotext
    result = _leer_pdf_comando(ruta, pagina_inicio, pagina_fin)
    if result is not None:
        return result

    return ("ERROR: No se pudo leer el PDF. Instala una libreria:\n"
            "  pip install PyMuPDF   (recomendado)\n"
            "  pip install pdfplumber (alternativa)\n"
            "  O instala pdftotext: sudo apt install poppler-utils")


def _leer_pdf_fitz(ruta, pagina_inicio, pagina_fin):
    """Lee PDF con PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(ruta)

        total_pages = len(doc)
        start = max(0, (pagina_inicio or 1) - 1)
        end = min(total_pages, pagina_fin or total_pages)

        parts = [f"PDF: {os.path.basename(ruta)} ({total_pages} paginas)\n"]

        for i in range(start, end):
            page = doc[i]
            text = page.get_text("text")
            if text.strip():
                parts.append(f"--- Pagina {i + 1} ---")
                parts.append(text)

            # Extraer tablas si hay
            try:
                tables = page.find_tables()
                if tables and tables.tables:
                    for ti, table in enumerate(tables.tables):
                        table_data = table.extract()
                        if table_data:
                            parts.append(f"  Tabla {ti + 1}:")
                            for row in table_data[:20]:
                                parts.append("  | " + " | ".join(str(c or "") for c in row) + " |")
            except Exception:
                pass  # Tabla extraction no critica

        doc.close()

        content = "\n".join(parts)
        if len(content) > MAX_FILE_READ:
            content = content[:MAX_FILE_READ] + f"\n... [truncado, {total_pages} paginas total]"

        return content

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"PyMuPDF fallo: {e}")
        return None


def _leer_pdf_plumber(ruta, pagina_inicio, pagina_fin):
    """Lee PDF con pdfplumber (alternativa)."""
    try:
        import pdfplumber

        with pdfplumber.open(ruta) as pdf:
            total_pages = len(pdf.pages)
            start = max(0, (pagina_inicio or 1) - 1)
            end = min(total_pages, pagina_fin or total_pages)

            parts = [f"PDF: {os.path.basename(ruta)} ({total_pages} paginas)\n"]

            for i in range(start, end):
                page = pdf.pages[i]
                text = page.extract_text()
                if text and text.strip():
                    parts.append(f"--- Pagina {i + 1} ---")
                    parts.append(text)

                # Extraer tablas
                try:
                    tables = page.extract_tables()
                    for ti, table in enumerate(tables[:3]):
                        parts.append(f"  Tabla {ti + 1}:")
                        for row in table[:20]:
                            parts.append("  | " + " | ".join(str(c or "") for c in row) + " |")
                except Exception:
                    pass

            content = "\n".join(parts)
            if len(content) > MAX_FILE_READ:
                content = content[:MAX_FILE_READ] + f"\n... [truncado, {total_pages} paginas total]"
            return content

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"pdfplumber fallo: {e}")
        return None


def _leer_pdf_comando(ruta, pagina_inicio, pagina_fin):
    """Fallback: lee PDF con comando pdftotext."""
    import subprocess
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", ruta, "-"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            content = f"PDF: {os.path.basename(ruta)}\n\n{result.stdout}"
            if len(content) > MAX_FILE_READ:
                content = content[:MAX_FILE_READ] + "\n... [truncado]"
            return content
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as e:
        logger.debug(f"pdftotext fallo: {e}")
    return None


# ============================================================
# LECTURA DE DOCX (Word)
# ============================================================

def leer_docx(ruta: str) -> str:
    """Lee el contenido de un archivo Word (.docx). Extrae texto, tablas y estilos.

    Args:
        ruta: Ruta del archivo .docx
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    ruta = _resolve_path(ruta)
    if not ruta:
        return f"Archivo no encontrado: {ruta}"

    if not ruta.lower().endswith('.docx'):
        return "ERROR: El archivo no es un .docx (para .doc viejo usar comando antiword)."

    # Intentar con python-docx
    result = _leer_docx_python(ruta)
    if result is not None:
        return result

    # Fallback: comando
    return _leer_docx_comando(ruta)


def _leer_docx_python(ruta):
    """Lee DOCX con python-docx."""
    try:
        from docx import Document

        doc = Document(ruta)
        parts = [f"DOCX: {os.path.basename(ruta)}\n"]

        # Extraer parrafos
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                # Indicar estilo si es heading
                style_name = para.style.name if para.style else ""
                if "Heading" in style_name or "heading" in style_name:
                    level = "".join(c for c in style_name if c.isdigit()) or "1"
                    parts.append(f"{'#' * int(level)} {text}")
                else:
                    parts.append(text)

        # Extraer tablas
        for ti, table in enumerate(doc.tables):
            parts.append(f"\nTabla {ti + 1}:")
            for row in table.rows[:20]:
                cells = [cell.text.strip() for cell in row.cells]
                parts.append("| " + " | ".join(cells) + " |")

        content = "\n".join(parts)
        if len(content) > MAX_FILE_READ:
            content = content[:MAX_FILE_READ] + "\n... [truncado]"
        return content

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"python-docx fallo: {e}")
        return f"ERROR leyendo DOCX: {e}"


def _leer_docx_comando(ruta):
    """Fallback: lee DOCX con comando (unzip + xml parse)."""
    import subprocess
    try:
        # docx es un ZIP con word/document.xml
        result = subprocess.run(
            ["python3", "-c",
             f"import zipfile,xml.etree.ElementTree as ET;"
             f"z=zipfile.ZipFile('{ruta}');"
             f"tree=ET.parse(z.open('word/document.xml'));"
             f"root=tree.getroot();"
             f"ns={{'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}};"
             f"print('\\n'.join(t.text for t in root.findall('.//w:t',ns) if t.text))"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            content = f"DOCX: {os.path.basename(ruta)}\n\n{result.stdout}"
            if len(content) > MAX_FILE_READ:
                content = content[:MAX_FILE_READ] + "\n... [truncado]"
            return content
    except Exception:
        pass

    return ("ERROR: No se pudo leer el DOCX. Instala:\n"
            "  pip install python-docx   (recomendado)")


# ============================================================
# LECTURA DE XLSX (Excel)
# ============================================================

def leer_xlsx(ruta: str, hoja: str = None, max_filas: int = 50) -> str:
    """Lee el contenido de un archivo Excel (.xlsx). Extrae datos de hojas y tablas.

    Args:
        ruta: Ruta del archivo .xlsx
        hoja: Nombre de la hoja (opcional, por defecto la primera)
        max_filas: Maximo de filas a leer por hoja (default 50)
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    ruta = _resolve_path(ruta)
    if not ruta:
        return f"Archivo no encontrado: {ruta}"

    if not ruta.lower().endswith(('.xlsx', '.xls')):
        return "ERROR: El archivo no es un Excel (.xlsx/.xls)."

    # Intentar con openpyxl
    result = _leer_xlsx_openpyxl(ruta, hoja, max_filas)
    if result is not None:
        return result

    # Fallback: comando
    return _leer_xlsx_comando(ruta, hoja, max_filas)


def _leer_xlsx_openpyxl(ruta, hoja, max_filas):
    """Lee XLSX con openpyxl."""
    try:
        from openpyxl import load_workbook

        wb = load_workbook(ruta, read_only=True, data_only=True)
        parts = [f"XLSX: {os.path.basename(ruta)} ({len(wb.sheetnames)} hojas)\n"]
        parts.append(f"Hojas: {', '.join(wb.sheetnames)}\n")

        # Determinar hojas a leer
        if hoja:
            if hoja in wb.sheetnames:
                sheets = [wb[hoja]]
            else:
                return f"Hoja '{hoja}' no encontrada. Disponibles: {', '.join(wb.sheetnames)}"
        else:
            sheets = [wb[name] for name in wb.sheetnames[:3]]  # Max 3 hojas

        for ws in sheets:
            parts.append(f"=== Hoja: {ws.title} ===")

            row_count = 0
            for row in ws.iter_rows(values_only=True):
                if row_count >= max_filas:
                    parts.append(f"... [truncado, {max_filas} filas maximo]")
                    break
                cells = [str(c) if c is not None else "" for c in row]
                if any(cells):  # Skip filas vacias
                    parts.append("| " + " | ".join(cells) + " |")
                    row_count += 1

            parts.append(f"({row_count} filas leidas)\n")

        wb.close()

        content = "\n".join(parts)
        if len(content) > MAX_FILE_READ:
            content = content[:MAX_FILE_READ] + "\n... [truncado]"
        return content

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"openpyxl fallo: {e}")
        return f"ERROR leyendo XLSX: {e}"


def _leer_xlsx_comando(ruta, hoja, max_filas):
    """Fallback: lee XLSX con comando python + zipfile (basico)."""
    import subprocess
    try:
        python_code = (
            "import zipfile,xml.etree.ElementTree as ET;"
            f"z=zipfile.ZipFile('{ruta}');"
            "tree=ET.parse(z.open('xl/sharedStrings.xml'));"
            "root=tree.getroot();"
            "ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'};"
            "strings=[t.text or '' for t in root.findall('.//s:t',ns)];"
            "print('Strings:', len(strings));"
            "print('Sheets:', z.namelist())"
        )
        result = subprocess.run(
            ["python3", "-c", python_code],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return f"XLSX (basico): {os.path.basename(ruta)}\n{result.stdout}\nInstala openpyxl para lectura completa: pip install openpyxl"
    except Exception:
        pass

    return ("ERROR: No se pudo leer el XLSX. Instala:\n"
            "  pip install openpyxl   (recomendado)")


# ============================================================
# LECTURA DE PPTX (PowerPoint)
# ============================================================

def leer_pptx(ruta: str) -> str:
    """Lee el contenido de una presentacion PowerPoint (.pptx). Extrae texto de diapositivas.

    Args:
        ruta: Ruta del archivo .pptx
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    ruta = _resolve_path(ruta)
    if not ruta:
        return f"Archivo no encontrado: {ruta}"

    if not ruta.lower().endswith('.pptx'):
        return "ERROR: El archivo no es un .pptx."

    # Intentar con python-pptx
    result = _leer_pptx_python(ruta)
    if result is not None:
        return result

    # Fallback: comando
    return _leer_pptx_comando(ruta)


def _leer_pptx_python(ruta):
    """Lee PPTX con python-pptx."""
    try:
        from pptx import Presentation

        prs = Presentation(ruta)
        parts = [f"PPTX: {os.path.basename(ruta)} ({len(prs.slides)} diapositivas)\n"]

        for i, slide in enumerate(prs.slides):
            parts.append(f"=== Diapositiva {i + 1} ===")

            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if text:
                            parts.append(text)

                # Tablas en diapositivas
                if shape.has_table:
                    table = shape.table
                    for row in table.rows:
                        cells = [cell.text.strip() for cell in row.cells]
                        parts.append("| " + " | ".join(cells) + " |")

            parts.append("")  # Separador entre diapositivas

        content = "\n".join(parts)
        if len(content) > MAX_FILE_READ:
            content = content[:MAX_FILE_READ] + "\n... [truncado]"
        return content

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"python-pptx fallo: {e}")
        return f"ERROR leyendo PPTX: {e}"


def _leer_pptx_comando(ruta):
    """Fallback: lee PPTX con unzip + xml."""
    import subprocess
    try:
        result = subprocess.run(
            ["python3", "-c",
             f"import zipfile,xml.etree.ElementTree as ET;"
             f"z=zipfile.ZipFile('{ruta}');"
             f"ns={{'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}};"
             f"slides=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')];"
             f"slides.sort();"
             f"print(f'{{len(slides)}} diapositivas');"
             f"[print(f'Slide {{i+1}}:', '\\n'.join(t.text for t in ET.parse(z.open(s)).getroot().findall('.//a:t',ns) if t.text)) for i,s in enumerate(slates[:20])]"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return f"PPTX (basico): {os.path.basename(ruta)}\n{result.stdout}"
    except Exception:
        pass

    return ("ERROR: No se pudo leer el PPTX. Instala:\n"
            "  pip install python-pptx   (recomendado)")


# ============================================================
# LECTURA DE CSV ESTRUCTURADO
# ============================================================

def leer_csv(ruta: str, separador: str = ",", max_filas: int = 50) -> str:
    """Lee un archivo CSV de forma estructurada. Detecta delimitador y codificacion.

    Args:
        ruta: Ruta del archivo CSV
        separador: Separador de columnas (default: coma)
        max_filas: Maximo de filas a leer (default 50)
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    ruta = _resolve_path(ruta)
    if not ruta:
        return f"Archivo no encontrado: {ruta}"

    try:
        # Intentar detectar codificacion
        encodings = ['utf-8', 'latin-1', 'cp1252', 'utf-16']
        content = None

        for enc in encodings:
            try:
                with open(ruta, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            return "ERROR: No se pudo detectar la codificacion del CSV."

        # Parsear CSV
        reader = csv.reader(io.StringIO(content), delimiter=separador)
        rows = list(reader)

        if not rows:
            return "CSV vacio."

        headers = rows[0] if rows else []
        data_rows = rows[1:max_filas + 1]

        parts = [f"CSV: {os.path.basename(ruta)} ({len(rows) - 1} filas, {len(headers)} columnas)\n"]
        parts.append(f"Columnas: {', '.join(headers)}\n")

        # Formato tabla
        for row in data_rows:
            # Rellenar filas cortas
            while len(row) < len(headers):
                row.append("")
            parts.append("| " + " | ".join(row[:len(headers)]) + " |")

        if len(rows) - 1 > max_filas:
            parts.append(f"\n... [truncado, mostrando {max_filas} de {len(rows) - 1} filas]")

        result = "\n".join(parts)
        if len(result) > MAX_FILE_READ:
            result = result[:MAX_FILE_READ] + "\n... [truncado]"
        return result

    except Exception as e:
        return f"ERROR leyendo CSV: {e}"


# ============================================================
# LECTURA DE ARCHIVOS COMPRIMIDOS
# ============================================================

def leer_archivo_comprimido(ruta: str, archivo_interno: str = None) -> str:
    """Lista o extrae contenido de archivos ZIP, TAR, GZ, RAR.

    Args:
        ruta: Ruta del archivo comprimido
        archivo_interno: Archivo interno a extraer (opcional, si no se especifica lista contenido)
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    ruta = _resolve_path(ruta)
    if not ruta:
        return f"Archivo no encontrado: {ruta}"

    ext = ruta.lower()

    if ext.endswith('.zip'):
        return _leer_zip(ruta, archivo_interno)
    elif ext.endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2')):
        return _leer_tar(ruta, archivo_interno)
    else:
        return "ERROR: Formato no soportado. Usar .zip, .tar, .tar.gz, .tar.bz2"


def _leer_zip(ruta, archivo_interno):
    """Lee contenido de archivo ZIP."""
    try:
        import zipfile
        with zipfile.ZipFile(ruta, 'r') as zf:
            names = zf.namelist()

            if archivo_interno:
                # Extraer archivo interno especifico
                if archivo_interno in names:
                    with zf.open(archivo_interno) as f:
                        content = f.read()
                        try:
                            text = content.decode('utf-8')
                        except UnicodeDecodeError:
                            text = content.decode('latin-1')

                        if len(text) > MAX_FILE_READ:
                            text = text[:MAX_FILE_READ] + "\n... [truncado]"
                        return f"Contenido de {archivo_interno}:\n\n{text}"
                else:
                    return f"Archivo '{archivo_interno}' no encontrado en ZIP. Disponibles:\n" + "\n".join(f"  {n}" for n in names[:30])
            else:
                # Listar contenido
                parts = [f"ZIP: {os.path.basename(ruta)} ({len(names)} archivos)\n"]
                for name in names[:50]:
                    info = zf.getinfo(name)
                    size = info.file_size
                    parts.append(f"  {'[DIR]' if name.endswith('/') else '[FILE]'} {name} ({size:,} bytes)")

                if len(names) > 50:
                    parts.append(f"\n... y {len(names) - 50} archivos mas")

                return "\n".join(parts)

    except Exception as e:
        return f"ERROR leyendo ZIP: {e}"


def _leer_tar(ruta, archivo_interno):
    """Lee contenido de archivo TAR."""
    try:
        import tarfile
        with tarfile.open(ruta, 'r:*') as tf:
            members = tf.getmembers()

            if archivo_interno:
                for member in members:
                    if member.name == archivo_interno:
                        f = tf.extractfile(member)
                        if f:
                            content = f.read()
                            try:
                                text = content.decode('utf-8')
                            except UnicodeDecodeError:
                                text = content.decode('latin-1')
                            if len(text) > MAX_FILE_READ:
                                text = text[:MAX_FILE_READ] + "\n... [truncado]"
                            return f"Contenido de {archivo_interno}:\n\n{text}"
                return f"Archivo '{archivo_interno}' no encontrado en TAR."

            # Listar contenido
            parts = [f"TAR: {os.path.basename(ruta)} ({len(members)} archivos)\n"]
            for m in members[:50]:
                type_str = "[DIR]" if m.isdir() else "[FILE]"
                parts.append(f"  {type_str} {m.name} ({m.size:,} bytes)")

            if len(members) > 50:
                parts.append(f"\n... y {len(members) - 50} archivos mas")

            return "\n".join(parts)

    except Exception as e:
        return f"ERROR leyendo TAR: {e}"


# ============================================================
# LECTURA DE BASES DE DATOS SQLITE
# ============================================================

def consultar_sqlite(ruta: str, consulta: str = None, tabla: str = None, max_filas: int = 50) -> str:
    """Consulta una base de datos SQLite. Puede listar tablas o ejecutar consultas SELECT.

    Args:
        ruta: Ruta del archivo .db o .sqlite
        consulta: Consulta SQL SELECT (opcional)
        tabla: Nombre de tabla para ver contenido (opcional)
        max_filas: Maximo de filas a retornar (default 50)
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    ruta = _resolve_path(ruta)
    if not ruta:
        return f"Archivo no encontrado: {ruta}"

    try:
        import sqlite3
        conn = sqlite3.connect(ruta)
        cursor = conn.cursor()

        if consulta:
            # Seguridad: solo permitir SELECT
            consulta_upper = consulta.strip().upper()
            if not consulta_upper.startswith("SELECT") and not consulta_upper.startswith("PRAGMA"):
                conn.close()
                return "ERROR: Solo se permiten consultas SELECT o PRAGMA por seguridad."

            # Bloquear comandos peligrosos
            dangerous = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "ATTACH", "DETACH"]
            for word in dangerous:
                if word in consulta_upper.split():
                    conn.close()
                    return f"ERROR: Comando {word} no permitido por seguridad."

            cursor.execute(consulta)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            parts = [f"Consulta: {consulta}"]
            if columns:
                parts.append("| " + " | ".join(columns) + " |")
            for row in rows[:max_filas]:
                parts.append("| " + " | ".join(str(c) for c in row) + " |")

            if len(rows) > max_filas:
                parts.append(f"\n... [truncado, {len(rows)} filas total]")

            parts.append(f"\n({len(rows)} filas)")
            conn.close()
            return "\n".join(parts)

        elif tabla:
            # Ver contenido de una tabla
            cursor.execute(f'SELECT * FROM "{tabla}" LIMIT {max_filas}')
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            parts = [f"Tabla: {tabla} ({len(rows)} filas mostradas)\n"]
            parts.append("| " + " | ".join(columns) + " |")
            for row in rows:
                parts.append("| " + " | ".join(str(c) for c in row) + " |")

            conn.close()
            return "\n".join(parts)

        else:
            # Listar tablas
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = cursor.fetchall()

            parts = [f"SQLite: {os.path.basename(ruta)} ({len(tables)} tablas)\n"]

            for (table_name,) in tables:
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                count = cursor.fetchone()[0]
                parts.append(f"  {table_name} ({count:,} filas)")

                # Mostrar schema
                cursor.execute(f'PRAGMA table_info("{table_name}")')
                cols = cursor.fetchall()
                col_info = ", ".join(f"{c[1]}({c[2]})" for c in cols[:8])
                parts.append(f"    Columnas: {col_info}")

            conn.close()
            return "\n".join(parts)

    except ImportError:
        return "ERROR: sqlite3 no disponible (viene con Python estandar, esto no deberia pasar)."
    except Exception as e:
        return f"ERROR consultando SQLite: {e}"


# ============================================================
# LECTURA DE ePub
# ============================================================

def leer_epub(ruta: str, max_capitulos: int = 10) -> str:
    """Lee el contenido de un libro electronico ePub. Extrae texto de capitulos.

    Args:
        ruta: Ruta del archivo .epub
        max_capitulos: Maximo de capitulos a leer (default 10)
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    ruta = _resolve_path(ruta)
    if not ruta:
        return f"Archivo no encontrado: {ruta}"

    # Intentar con ebooklib
    try:
        import ebooklib
        from ebooklib import epub
        from html.parser import HTMLParser

        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.skip = False

            def handle_starttag(self, tag, attrs):
                if tag in ('script', 'style'):
                    self.skip = True

            def handle_endtag(self, tag):
                if tag in ('script', 'style'):
                    self.skip = False
                elif tag in ('p', 'div', 'h1', 'h2', 'h3', 'br'):
                    self.text.append('\n')

            def handle_data(self, data):
                if not self.skip:
                    self.text.append(data.strip())

        book = epub.read_epub(ruta)
        parts = [f"ePub: {os.path.basename(ruta)}\n"]

        # Metadata
        title = book.get_metadata('DC', 'title')
        author = book.get_metadata('DC', 'author')
        if title:
            parts.append(f"Titulo: {title[0][0]}")
        if author:
            parts.append(f"Autor: {author[0][0]}")

        # Extraer texto de documentos
        chapters = 0
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            if chapters >= max_capitulos:
                break
            content = item.get_content().decode('utf-8', errors='replace')
            extractor = _TextExtractor()
            extractor.feed(content)
            text = " ".join(extractor.text).strip()
            if text and len(text) > 50:
                parts.append(f"\n--- Capitulo {chapters + 1} ---")
                parts.append(text[:2000])
                chapters += 1

        content = "\n".join(parts)
        if len(content) > MAX_FILE_READ:
            content = content[:MAX_FILE_READ] + "\n... [truncado]"
        return content

    except ImportError:
        # Fallback: tratar como ZIP y buscar HTML
        return _leer_epub_zip(ruta, max_capitulos)
    except Exception as e:
        return f"ERROR leyendo ePub: {e}"


def _leer_epub_zip(ruta, max_capitulos):
    """Fallback: lee ePub como ZIP (formato basico)."""
    try:
        import zipfile
        from html.parser import HTMLParser

        class _SimpleText(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
            def handle_data(self, data):
                self.text.append(data.strip())

        with zipfile.ZipFile(ruta, 'r') as zf:
            html_files = [n for n in zf.namelist() if n.endswith(('.html', '.xhtml'))]

            parts = [f"ePub (basico): {os.path.basename(ruta)} ({len(html_files)} secciones)\n"]

            for i, name in enumerate(html_files[:max_capitulos]):
                content = zf.open(name).read().decode('utf-8', errors='replace')
                extractor = _SimpleText()
                extractor.feed(content)
                text = " ".join(t for t in extractor.text if t)
                if text:
                    parts.append(f"--- Seccion {i + 1} ---")
                    parts.append(text[:1500])

            content = "\n".join(parts)
            if len(content) > MAX_FILE_READ:
                content = content[:MAX_FILE_READ] + "\n... [truncado]"
            return content

    except Exception as e:
        return f"ERROR leyendo ePub: {e}\nInstala: pip install ebooklib"


# ============================================================
# LECTOR UNIVERSAL (auto-detectar formato)
# ============================================================

def leer_documento(ruta: str, **kwargs) -> str:
    """Lee cualquier documento detectando automaticamente el formato.
    Soporta: PDF, DOCX, XLSX, PPTX, CSV, ZIP, TAR, SQLite, ePub, y texto plano.

    Args:
        ruta: Ruta del archivo a leer
        **kwargs: Argumentos adicionales segun el tipo (hoja, consulta, etc.)
    """
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    ruta_resolved = _resolve_path(ruta)
    if not ruta_resolved:
        return f"Archivo no encontrado: {ruta}"

    ext = ruta_resolved.lower()

    if ext.endswith('.pdf'):
        return leer_pdf(ruta_resolved, **{k: v for k, v in kwargs.items() if k in ('pagina_inicio', 'pagina_fin')})
    elif ext.endswith('.docx'):
        return leer_docx(ruta_resolved)
    elif ext.endswith(('.xlsx', '.xls')):
        return leer_xlsx(ruta_resolved, **{k: v for k, v in kwargs.items() if k in ('hoja', 'max_filas')})
    elif ext.endswith('.pptx'):
        return leer_pptx(ruta_resolved)
    elif ext.endswith('.csv'):
        return leer_csv(ruta_resolved, **{k: v for k, v in kwargs.items() if k in ('separador', 'max_filas')})
    elif ext.endswith(('.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2')):
        return leer_archivo_comprimido(
            ruta_resolved,
            **{k: v for k, v in kwargs.items() if k in ('archivo_interno',)}
        )
    elif ext.endswith(('.db', '.sqlite', '.sqlite3')):
        return consultar_sqlite(
            ruta_resolved,
            **{k: v for k, v in kwargs.items() if k in ('consulta', 'tabla', 'max_filas')}
        )
    elif ext.endswith('.epub'):
        return leer_epub(ruta_resolved)
    else:
        # Fallback: intentar como texto
        try:
            with open(ruta_resolved, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            if len(content) > MAX_FILE_READ:
                content = content[:MAX_FILE_READ] + "\n... [truncado]"
            return content
        except Exception as e:
            return f"ERROR: No se pudo leer {ruta_resolved}: {e}"


# ============================================================
# UTILIDADES
# ============================================================

def _resolve_path(ruta):
    """Resuelve la ruta del archivo, buscando en ubicaciones alternativas."""
    if os.path.isabs(ruta) and os.path.exists(ruta):
        return ruta

    # Ruta relativa
    if os.path.exists(ruta):
        return ruta

    # Buscar en REPOS_DIR
    alt = os.path.join(REPOS_DIR, ruta)
    if os.path.exists(alt):
        return alt

    # Buscar en subdirectorios
    try:
        for d in os.listdir(REPOS_DIR):
            alt2 = os.path.join(REPOS_DIR, d, ruta)
            if os.path.exists(alt2):
                return alt2
    except OSError:
        pass

    # Buscar en home
    home = os.path.expanduser("~")
    alt3 = os.path.join(home, ruta)
    if os.path.exists(alt3):
        return alt3

    return None
