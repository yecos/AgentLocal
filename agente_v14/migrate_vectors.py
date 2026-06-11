"""
=============================================================
AGENTE v14 - Migracion de VectorStore a ChromaDB
=============================================================
Migra los datos del VectorStore casero (JSON) a ChromaDB.
Se ejecuta una sola vez, cuando el usuario instala ChromaDB.

Uso: python migrate_vectors.py
    python migrate_vectors.py --dry-run   (ver que migraria sin hacerlo)
    python migrate_vectors.py --force     (migrar incluso si ya hay datos)
=============================================================
"""

import os
import sys
import json
import time

# Agregar directorio del script al path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from config import LEARN_DIR, logger


def check_chromadb():
    """Verifica que ChromaDB este instalado."""
    try:
        import chromadb
        return True
    except ImportError:
        return False


def load_old_vectorstore():
    """Carga los datos del VectorStore casero."""
    vectors_dir = os.path.join(LEARN_DIR, "vectors")
    index_file = os.path.join(vectors_dir, "index.json")
    vectors_file = os.path.join(vectors_dir, "vectors.json")

    if not os.path.exists(index_file):
        print("  No se encontro index.json - No hay datos para migrar.")
        return None, None

    with open(index_file, "r", encoding="utf-8") as f:
        index = json.load(f)

    vectors = {}
    if os.path.exists(vectors_file):
        with open(vectors_file, "r", encoding="utf-8") as f:
            vectors = json.load(f)

    return index, vectors


def migrate(dry_run=False, force=False):
    """Ejecuta la migracion del VectorStore casero a ChromaDB."""
    print()
    print("=" * 60)
    print("  MIGRACION: VectorStore casero -> ChromaDB")
    print("=" * 60)
    print()

    # 1. Verificar ChromaDB
    if not check_chromadb():
        print("  [XX] ChromaDB no esta instalado.")
        print("      Instalalo con: pip install chromadb")
        print("      Luego vuelve a ejecutar este script.")
        return False
    print("  [OK] ChromaDB instalado")

    # 2. Cargar datos viejos
    print("  Cargando datos del VectorStore casero...")
    index, vectors = load_old_vectorstore()

    if index is None:
        print("  No hay datos para migrar. Todo listo!")
        return True

    entries_with_vectors = sum(1 for e in index if e.get("has_vector"))
    entries_without_vectors = len(index) - entries_with_vectors
    print(f"  Encontrados: {len(index)} entradas ({entries_with_vectors} con vectores, {entries_without_vectors} sin vectores)")

    if not index:
        print("  No hay datos para migrar.")
        return True

    # 3. Verificar si ChromaDB ya tiene datos
    from memory.chroma_store import ChromaVectorStore, CHROMADB_AVAILABLE

    if not CHROMADB_AVAILABLE:
        print("  [XX] ChromaDB no disponible.")
        return False

    store = ChromaVectorStore()
    existing_count = store.count()
    print(f"  ChromaDB tiene {existing_count} entradas actualmente")

    if existing_count > 0 and not force:
        print()
        print("  [!!] ChromaDB ya tiene datos. Usar --force para sobreescribir.")
        print("      Los datos existentes NO se borraran, se agregaran los nuevos.")
        # Continuar de todos modos (solo agregar, no sobreescribir)

    # 4. Dry run
    if dry_run:
        print()
        print("  --- DRY RUN (no se migrara nada) ---")
        print(f"  Se migrarian {len(index)} entradas:")
        for entry in index[:10]:
            has_vec = "con vector" if entry.get("has_vector") else "sin vector"
            print(f"    - [{has_vec}] {entry.get('text', '')[:80]}...")
        if len(index) > 10:
            print(f"    ... y {len(index) - 10} mas")
        print()
        return True

    # 5. Migrar
    print()
    print(f"  Migrando {len(index)} entradas...")

    migrated = 0
    skipped = 0
    errors = 0

    for i, entry in enumerate(index):
        entry_id = entry.get("id", "")
        text = entry.get("text", "")
        metadata = entry.get("metadata", {})
        has_vector = entry.get("has_vector", False)
        created = entry.get("created", "")

        if not text:
            skipped += 1
            continue

        # Preservar metadatos originales
        if created:
            metadata["created"] = created
        metadata["migrated_from"] = "vectorstore_json"
        metadata["original_id"] = entry_id

        try:
            # Si tiene vector, intentar usarlo directamente
            if has_vector and entry_id in vectors:
                vec = vectors[entry_id]
                # Agregar directamente con el vector existente (sin re-calcular embedding)
                store._collection.add(
                    ids=[entry_id],
                    embeddings=[vec],
                    documents=[text[:500]],
                    metadatas=[metadata]
                )
                migrated += 1
            else:
                # Sin vector, agregar y que ChromaDB calcule el embedding via add()
                store.add(text, metadata=metadata, entry_id=entry_id)
                migrated += 1
        except Exception as e:
            # Probablemente duplicado
            if "already exists" in str(e).lower() or "unique constraint" in str(e).lower():
                skipped += 1
            else:
                errors += 1
                if errors <= 3:
                    print(f"    [XX] Error en entrada {i}: {e}")

        # Progreso
        if (i + 1) % 50 == 0:
            print(f"    Progreso: {i + 1}/{len(index)} (migradas: {migrated}, saltadas: {skipped}, errores: {errors})")

    # 6. Resumen
    print()
    print("=" * 60)
    print("  MIGRACION COMPLETADA")
    print("=" * 60)
    print(f"  Total entradas:  {len(index)}")
    print(f"  Migradas:        {migrated}")
    print(f"  Saltadas (duplicados/vacias): {skipped}")
    print(f"  Errores:         {errors}")
    print(f"  ChromaDB ahora tiene: {store.count()} entradas")
    print()

    if errors > 0:
        print("  Nota: Algunas entradas tuvieron errores. Revisa el log para detalles.")

    # 7. Backup
    if migrated > 0:
        backup_dir = os.path.join(LEARN_DIR, "vectors_backup_pre_chromadb")
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            # Copiar archivos viejos como backup
            import shutil
            vectors_dir = os.path.join(LEARN_DIR, "vectors")
            for fname in ["index.json", "vectors.json"]:
                src = os.path.join(vectors_dir, fname)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(backup_dir, fname))
            print(f"  Backup creado en: {backup_dir}")
            print("  Los archivos originales NO se borraron (puedes borrarlos manualmente).")
        else:
            print(f"  Backup ya existe en: {backup_dir}")

    print()
    return True


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    force = "--force" in args
    migrate(dry_run=dry_run, force=force)
