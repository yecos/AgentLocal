# memory.py - Sistema de Memoria y Aprendizaje Persistente del Agente
# Usa SQLite para que el conocimiento sobreviva entre sesiones.
import sqlite3
import hashlib
import json
from datetime import datetime


class MemoriaAgente:
    """Memoria persistente del agente. Guarda conocimiento, soluciones
    y conversaciones para que el agente aprenda con el tiempo."""

    def __init__(self, db_path="memoria_agente.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._crear_tablas()

    def _crear_tablas(self):
        """Crea las tablas de la base de datos si no existen."""
        # Tabla de conocimiento general
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS conocimiento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tema TEXT,
                hash_pregunta TEXT UNIQUE,
                pregunta TEXT,
                respuesta TEXT,
                fuente TEXT DEFAULT 'razonamiento',
                veces_usado INTEGER DEFAULT 1,
                ultima_vez_usado TEXT,
                fecha_creacion TEXT
            )
        """)

        # Tabla de soluciones (qué funcionó y qué no)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS soluciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                problema TEXT,
                solucion TEXT,
                exito INTEGER,
                herramienta_usada TEXT,
                fecha TEXT
            )
        """)

        # Tabla de conversaciones (resumen de sesiones)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                resumen TEXT,
                temas TEXT
            )
        """)

        self.conn.commit()

    # ── Guardar y Buscar Conocimiento ───────────────────────

    def guardar_conocimiento(self, pregunta: str, respuesta: str, fuente: str = "razonamiento"):
        """Guarda nuevo conocimiento o actualiza si ya existe (incrementa uso)."""
        hash_preg = hashlib.md5(pregunta.lower().strip().encode()).hexdigest()
        tema = self._extraer_tema(pregunta)
        ahora = datetime.now().isoformat()

        try:
            existente = self.cursor.execute(
                "SELECT id, veces_usado FROM conocimiento WHERE hash_pregunta = ?",
                (hash_preg,),
            ).fetchone()

            if existente:
                # Ya existe: actualizar contador y respuesta mejorada
                self.cursor.execute(
                    "UPDATE conocimiento SET veces_usado = ?, respuesta = ?, "
                    "ultima_vez_usado = ? WHERE id = ?",
                    (existente[1] + 1, respuesta, ahora, existente[0]),
                )
            else:
                # Nuevo conocimiento
                self.cursor.execute(
                    "INSERT INTO conocimiento "
                    "(tema, hash_pregunta, pregunta, respuesta, fuente, "
                    "ultima_vez_usado, fecha_creacion) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (tema, hash_preg, pregunta, respuesta, fuente, ahora, ahora),
                )

            self.conn.commit()
        except Exception as e:
            print(f"[Memoria] Error guardando conocimiento: {e}")

    def buscar_relevante(self, pregunta: str, limite: int = 3) -> list:
        """Busca conocimiento previo relevante por tema o similitud de texto."""
        tema = self._extraer_tema(pregunta)

        resultados = self.cursor.execute(
            """
            SELECT pregunta, respuesta, veces_usado, fuente
            FROM conocimiento
            WHERE pregunta LIKE ? OR tema LIKE ?
            ORDER BY veces_usado DESC
            LIMIT ?
            """,
            (f"%{pregunta[:30]}%", f"%{tema}%", limite),
        ).fetchall()

        return [
            {
                "pregunta": r[0],
                "respuesta": r[1],
                "veces_usado": r[2],
                "fuente": r[3],
            }
            for r in resultados
        ]

    # ── Soluciones (qué funcionó y qué no) ──────────────────

    def guardar_solucion(self, problema: str, solucion: str, exito: bool, herramienta: str = ""):
        """Registra si una solución funcionó o no, para aprender de errores."""
        self.cursor.execute(
            "INSERT INTO soluciones (problema, solucion, exito, herramienta_usada, fecha) "
            "VALUES (?, ?, ?, ?, ?)",
            (problema, solucion, 1 if exito else 0, herramienta, datetime.now().isoformat()),
        )
        self.conn.commit()

    def buscar_soluciones(self, problema: str, limite: int = 3) -> list:
        """Busca soluciones previas para un problema similar."""
        resultados = self.cursor.execute(
            """
            SELECT problema, solucion, exito, herramienta_usada, fecha
            FROM soluciones
            WHERE problema LIKE ?
            ORDER BY fecha DESC
            LIMIT ?
            """,
            (f"%{problema[:30]}%", limite),
        ).fetchall()

        return [
            {
                "problema": r[0],
                "solucion": r[1],
                "funciono": bool(r[2]),
                "herramienta": r[3],
                "fecha": r[4],
            }
            for r in resultados
        ]

    # ── Conversaciones ──────────────────────────────────────

    def guardar_conversacion(self, resumen: str, temas: list):
        """Guarda un resumen de la conversación actual."""
        self.cursor.execute(
            "INSERT INTO conversaciones (fecha, resumen, temas) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), resumen, json.dumps(temas)),
        )
        self.conn.commit()

    # ── Estadísticas ────────────────────────────────────────

    def estadisticas(self) -> dict:
        """Devuelve estadísticas del conocimiento acumulado."""
        total = self.cursor.execute("SELECT COUNT(*) FROM conocimiento").fetchone()[0]

        total_soluciones = self.cursor.execute("SELECT COUNT(*) FROM soluciones").fetchone()[0]

        exitosas = self.cursor.execute(
            "SELECT COUNT(*) FROM soluciones WHERE exito = 1"
        ).fetchone()[0]

        top = self.cursor.execute(
            "SELECT pregunta, veces_usado FROM conocimiento "
            "ORDER BY veces_usado DESC LIMIT 5"
        ).fetchall()

        return {
            "total_conocimientos": total,
            "total_soluciones": total_soluciones,
            "soluciones_exitosas": exitosas,
            "top_conocimientos": [
                {"pregunta": t[0], "veces_usado": t[1]} for t in top
            ],
        }

    # ── Utilidades ──────────────────────────────────────────

    def _extraer_tema(self, texto: str) -> str:
        """Extrae las palabras clave de un texto para usar como tema."""
        stopwords = {
            "cómo", "qué", "cuál", "cuáles", "por", "qué", "es", "la", "los",
            "el", "las", "un", "una", "unos", "unas", "de", "en", "con", "por",
            "para", "al", "del", "se", "su", "sus", "me", "te", "le", "lo",
            "the", "is", "a", "an", "and", "or", "of", "in", "to", "for",
        }
        palabras = [
            p for p in texto.lower().split()
            if p not in stopwords and len(p) > 2
        ]
        return " ".join(palabras[:5])

    def cerrar(self):
        """Cierra la conexión a la base de datos."""
        self.conn.close()

    def __del__(self):
        try:
            self.conn.close()
        except Exception:
            pass
