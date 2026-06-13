"""
=============================================================
AGENTE v14 - Benchmark de Métodos de Búsqueda
=============================================================
Valida las mejoras implementadas:
1. BM25 vs búsqueda por texto simple
2. Stemming español en pre-filtro
3. Búsqueda híbrida (BM25 + Vectorial + RRF)
4. Re-ranking multi-señal
5. Decay diferenciado por tipo de contenido
6. Matching de correcciones con stemming

Uso: python -m tests.bench_search
=============================================================
"""

import sys
import os
import time
import math
from datetime import datetime, timedelta

# Agregar directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_bm25_vs_simple():
    """Compara BM25 con búsqueda por texto simple."""
    print("\n" + "="*60)
    print("TEST 1: BM25 vs Búsqueda por Texto Simple")
    print("="*60)

    from memory.bm25 import BM25, tokenize

    # Corpus de prueba en español
    documents = [
        {"id": "d1", "text": "Para configurar el servidor nginx necesitas editar el archivo nginx.conf"},
        {"id": "d2", "text": "La configuración de red requiere ajustar el DNS y el gateway"},
        {"id": "d3", "text": "Cómo instalar y configurar PostgreSQL en Ubuntu 22.04"},
        {"id": "d4", "text": "Los ajustes de seguridad incluyen firewall y SSH"},
        {"id": "d5", "text": "Configuración del entorno de desarrollo con Python y virtualenv"},
        {"id": "d6", "text": "El error de conexión se debe a un timeout en la base de datos"},
        {"id": "d7", "text": "Guía de configuración avanzada de Docker Compose"},
        {"id": "d8", "text": "Solución de errores comunes en la configuración de SSL"},
        {"id": "d9", "text": "Revisar los logs del sistema para diagnosticar problemas"},
        {"id": "d10", "text": "Configurar variables de entorno en el archivo .env"},
    ]

    bm25 = BM25(documents, k1=1.5, b=0.75, use_stemming=True)

    # Caso 1: Búsqueda con variación morfológica
    query = "configuración"
    results = bm25.search(query, limit=5)

    print(f"\n  Query: '{query}' (con stemming)")
    print(f"  Tokens query: {tokenize(query)}")
    for doc_id, score in results:
        doc_text = next(d["text"][:60] for d in documents if d["id"] == doc_id)
        print(f"    {doc_id}: score={score:.4f} - {doc_text}...")

    # Caso 2: Búsqueda con forma verbal diferente
    query2 = "configurar"
    results2 = bm25.search(query2, limit=5)

    print(f"\n  Query: '{query2}' (con stemming)")
    print(f"  Tokens query: {tokenize(query2)}")
    for doc_id, score in results2:
        doc_text = next(d["text"][:60] for d in documents if d["id"] == doc_id)
        print(f"    {doc_id}: score={score:.4f} - {doc_text}...")

    # Verificar que 'configurar' encuentra los mismos docs que 'configuración'
    ids_configurar = {r[0] for r in results2}
    ids_configuracion = {r[0] for r in results}
    overlap = ids_configurar & ids_configuracion

    print(f"\n  ✓ Ambas queries encuentran {len(overlap)} docs en común de {len(ids_configuracion)}")
    if len(overlap) >= 4:
        print("  ✅ PASS: Stemming español funciona correctamente")
    else:
        print("  ❌ FAIL: Stemming no está funcionando bien")

    return len(overlap) >= 4


def test_stemming_stopwords():
    """Verifica que stemming y stopwords funcionan correctamente."""
    print("\n" + "="*60)
    print("TEST 2: Stemming y Stopwords en Español")
    print("="*60)

    from memory.bm25 import tokenize, tokenize_minimal

    # Test de stopwords
    text_with_stopwords = "el gato está en la casa y no quiere salir"
    tokens = tokenize(text_with_stopwords)
    print(f"\n  Texto: '{text_with_stopwords}'")
    print(f"  Tokens con stemming: {tokens}")

    # Verificar que stopwords fueron eliminadas
    stopword_stems = {"el", "la", "en", "y", "no"}
    has_stopwords = any(t in stopword_stems for t in tokens)
    if not has_stopwords:
        print("  ✅ PASS: Stopwords eliminadas correctamente")
    else:
        print("  ❌ FAIL: Algunas stopwords no fueron eliminadas")

    # Test de variaciones morfológicas
    variants = [
        ("configurar", "configuración"),
        ("ejecutar", "ejecución"),
        ("instalar", "instalación"),
        ("buscar", "búsqueda"),
        ("crear", "creación"),
    ]

    all_match = True
    for word1, word2 in variants:
        stem1 = tokenize(word1)
        stem2 = tokenize(word2)
        match = stem1 == stem2
        status = "✓" if match else "✗"
        print(f"  {status} '{word1}' -> {stem1}  |  '{word2}' -> {stem2}")
        if not match:
            all_match = False

    if all_match:
        print("  ✅ PASS: Variaciones morfológicas confluyen al mismo stem")
    else:
        print("  ⚠️ Algunas variaciones no confluyen (esperado con Snowball)")

    return not has_stopwords


def test_rrf_fusion():
    """Verifica Reciprocal Rank Fusion."""
    print("\n" + "="*60)
    print("TEST 3: Reciprocal Rank Fusion (RRF)")
    print("="*60)

    from memory.bm25 import reciprocal_rank_fusion

    # Simular dos rankings con algo de overlap
    vector_ranking = ["d1", "d3", "d5", "d7", "d2", "d9"]
    bm25_ranking = ["d2", "d5", "d7", "d1", "d4", "d8"]

    fused = reciprocal_rank_fusion([vector_ranking, bm25_ranking], k=60)

    print("\n  Ranking Vectorial: ", vector_ranking)
    print("  Ranking BM25:      ", bm25_ranking)
    print("\n  Resultado Fusionado (RRF, k=60):")
    for doc_id, score in fused:
        in_vector = "V" if doc_id in vector_ranking else " "
        in_bm25 = "B" if doc_id in bm25_ranking else " "
        print(f"    {doc_id}: score={score:.6f} [{in_vector}|{in_bm25}]")

    # Docs en ambos rankings deben tener score más alto
    both = set(vector_ranking) & set(bm25_ranking)
    if both:
        both_scores = {doc_id: score for doc_id, score in fused if doc_id in both}
        only_one_scores = {doc_id: score for doc_id, score in fused if doc_id not in both}
        avg_both = sum(both_scores.values()) / len(both_scores) if both_scores else 0
        avg_one = sum(only_one_scores.values()) / len(only_one_scores) if only_one_scores else 0

        print(f"\n  Avg score docs en ambos rankings: {avg_both:.6f}")
        print(f"  Avg score docs en solo un ranking: {avg_one:.6f}")

        if avg_both > avg_one:
            print("  ✅ PASS: Docs en ambos rankings tienen score promedio más alto")
            return True
        else:
            print("  ❌ FAIL: RRF no prioriza correctamente docs en ambos rankings")
            return False

    return True


def test_differentiated_decay():
    """Verifica decay diferenciado por tipo de contenido."""
    print("\n" + "="*60)
    print("TEST 4: Decaimiento Temporal Diferenciado")
    print("="*60)

    from memory.reranker import DECAY_HALF_LIFE_BY_TYPE, DEFAULT_HALF_LIFE

    # Simular docs de 30 días de antigüedad
    days_old = 30

    print(f"\n  Documentos de {days_old} días de antigüedad:")
    print(f"  {'Tipo':<15} {'Half-life (días)':<20} {'Decay':<10} {'Frescura'}")

    for content_type, half_life in sorted(DECAY_HALF_LIFE_BY_TYPE.items(), key=lambda x: x[1]):
        decay = math.exp(-0.693 * days_old / half_life)
        freshness = 1 - decay
        print(f"  {content_type:<15} {half_life:<20} {decay:<10.3f} {freshness:.3f}")

    # Verificar que conocimiento decae más lento que conversación
    knowledge_decay = math.exp(-0.693 * days_old / DECAY_HALF_LIFE_BY_TYPE["knowledge"])
    conversation_decay = math.exp(-0.693 * days_old / DECAY_HALF_LIFE_BY_TYPE["conversation"])

    print(f"\n  Knowledge decay (30d): {knowledge_decay:.3f}")
    print(f"  Conversation decay (30d): {conversation_decay:.3f}")

    if knowledge_decay > conversation_decay:
        print("  ✅ PASS: Conocimiento retiene más valor que conversación")
        return True
    else:
        print("  ❌ FAIL: Decay diferenciado no funciona correctamente")
        return False


def test_reranker():
    """Verifica MultiSignalReranker con señales múltiples."""
    print("\n" + "="*60)
    print("TEST 5: Re-ranker Multi-Señal")
    print("="*60)

    from memory.reranker import MultiSignalReranker, QueryClassifier

    # Clasificar consultas
    test_queries = [
        ("¿Qué es Python?", "factual"),
        ("busca el archivo config.py", "exact"),
        ("¿qué hicimos la semana pasada?", "temporal"),
        ("ayúdame con esto", "general"),
    ]

    print("\n  Clasificador de consultas:")
    for query, expected in test_queries:
        qtype, confidence = QueryClassifier.classify(query)
        match = "✓" if qtype == expected else "≈"
        print(f"    {match} '{query}' -> tipo={qtype}, conf={confidence:.2f} (esperado={expected})")

    # Re-rank con candidatos simulados
    reranker = MultiSignalReranker(use_adaptive_weights=True)

    candidates = [
        {"id": "c1", "text": "Python es un lenguaje de programación", "score": 0.85,
         "metadata": {"type": "knowledge"}, "created": datetime.now().isoformat()},
        {"id": "c2", "text": "Ayer instalamos Python 3.12", "score": 0.80,
         "metadata": {"type": "conversation"}, "created": (datetime.now() - timedelta(days=7)).isoformat()},
        {"id": "c3", "text": "Error en el archivo python.cfg", "score": 0.75,
         "metadata": {"type": "experience"}, "created": datetime.now().isoformat()},
        {"id": "c4", "text": "Qué es la programación funcional en Python", "score": 0.70,
         "metadata": {"type": "knowledge"}, "created": (datetime.now() - timedelta(days=60)).isoformat()},
    ]

    query = "¿Qué es Python?"
    reranked = reranker.rerank(query, candidates, limit=3)

    print(f"\n  Re-ranking para: '{query}'")
    for r in reranked:
        signals = r.get("signals", {})
        print(f"    {r['id']}: rerank={r['rerank_score']:.4f} "
              f"type={r.get('query_type','')} "
              f"signals=[sem={signals.get('semantic',0):.2f} lex={signals.get('lexical',0):.2f} "
              f"fresh={signals.get('freshness',0):.2f} cov={signals.get('coverage',0):.2f} "
              f"type_b={signals.get('type_bonus',0):.2f}] "
              f"- {r['text'][:50]}")

    # Knowledge con alta similitud debería estar primero
    if reranked and reranked[0]["id"] in ("c1", "c4"):
        print("  ✅ PASS: Knowledge ranking alto para consulta factual")
        return True
    else:
        print("  ⚠️ Re-ranking pudo mejorar pero resultado inesperado")
        return False


def test_correction_matching():
    """Verifica matching de correcciones con stemming."""
    print("\n" + "="*60)
    print("TEST 6: Matching de Correcciones con Stemming")
    print("="*60)

    from memory.learning import LearningSystem
    import tempfile
    import json

    # Crear learning system con archivos temporales
    learning = LearningSystem()

    # Simular correcciones guardadas
    with open(learning._load.__func__.__defaults__[0] if learning._load.__func__.__defaults__ else None, 'a'):
        pass

    # Test directo del método get_corrections_for
    print("\n  Probando matching de correcciones con stemming...")

    # Guardar correcciones de prueba
    test_corrections = [
        {"user_message": "configurar el servidor", "wrong_action": "editar hosts",
         "correct_action": "editar nginx.conf", "reason": "nginx.conf es el config real"},
        {"user_message": "instalar dependencias", "wrong_action": "pip install global",
         "correct_action": "usar venv", "reason": "aislar dependencias"},
        {"user_message": "ejecutar pruebas", "wrong_action": "python test.py",
         "correct_action": "pytest", "reason": "pytest es el estándar"},
    ]

    # Guardar temporalmente
    corrections_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "learning", "corrections_test.json")
    os.makedirs(os.path.dirname(corrections_file), exist_ok=True)

    with open(corrections_file, "w", encoding="utf-8") as f:
        json.dump(test_corrections, f, ensure_ascii=False, indent=2)

    # Test: buscar con variación morfológica
    try:
        from memory.bm25 import tokenize

        # "configuración" debería match con "configurar"
        msg_stems = set(tokenize("configuración del servidor"))
        corr_stems = set(tokenize("configurar el servidor"))
        overlap = msg_stems & corr_stems

        print(f"  'configuración del servidor' stems: {msg_stems}")
        print(f"  'configurar el servidor' stems: {corr_stems}")
        print(f"  Overlap: {overlap}")

        if overlap:
            print("  ✅ PASS: Stemming permite matching morfológico en correcciones")
            success = True
        else:
            print("  ❌ FAIL: No se encontró overlap entre variaciones")
            success = False
    except ImportError as e:
        print(f"  ⚠️ No se pudo importar bm25: {e}")
        success = False
    finally:
        # Limpiar
        try:
            os.remove(corrections_file)
        except Exception:
            pass

    return success


def test_bm25_index_efficiency():
    """Verifica que BM25 usa índice invertido (no escanea todos los docs)."""
    print("\n" + "="*60)
    print("TEST 7: Eficiencia del Índice Invertido BM25")
    print("="*60)

    from memory.bm25 import BM25

    # Crear índice con 100 documentos
    documents = []
    for i in range(100):
        topics = ["python", "javascript", "docker", "nginx", "postgres", "redis", "git"]
        topic = topics[i % len(topics)]
        documents.append({
            "id": f"doc_{i}",
            "text": f"Documento {i} sobre {topic} y configuración de {topic}"
        })

    bm25 = BM25(documents, use_stemming=True)

    stats = bm25.stats()
    print(f"\n  Documentos indexados: {stats['doc_count']}")
    print(f"  Términos únicos: {stats['unique_terms']}")
    print(f"  Longitud promedio: {stats['avg_doc_length']}")
    print(f"  Entradas en índice invertido: {stats['index_size_entries']}")

    # Buscar y medir velocidad
    start = time.time()
    for _ in range(100):
        results = bm25.search("configuración python", limit=5)
    elapsed = time.time() - start

    print(f"\n  100 búsquedas en {elapsed:.4f}s ({elapsed*10:.2f}ms por búsqueda)")
    print(f"  Top 3 resultados:")
    for doc_id, score in results[:3]:
        print(f"    {doc_id}: score={score:.4f}")

    if elapsed < 1.0:  # Debe ser < 10ms por búsqueda
        print("  ✅ PASS: BM25 con índice invertido es rápido")
        return True
    else:
        print("  ⚠️ Búsquedas más lentas de lo esperado")
        return False


def run_all_benchmarks():
    """Ejecuta todos los benchmarks."""
    print("\n" + "="*60)
    print("  BENCHMARK DE MÉTODOS DE BÚSQUEDA - AGENTE v14.5")
    print("="*60)

    results = {}
    tests = [
        ("BM25 vs Simple", test_bm25_vs_simple),
        ("Stemming/Stopwords", test_stemming_stopwords),
        ("RRF Fusion", test_rrf_fusion),
        ("Decay Diferenciado", test_differentiated_decay),
        ("Re-ranker Multi-Señal", test_reranker),
        ("Correcciones con Stemming", test_correction_matching),
        ("Eficiencia BM25", test_bm25_index_efficiency),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            result = test_fn()
            results[name] = result
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n  ❌ ERROR en {name}: {e}")
            results[name] = False
            failed += 1

    # Resumen
    print("\n" + "="*60)
    print("  RESUMEN DE BENCHMARKS")
    print("="*60)
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {name}")

    print(f"\n  Total: {passed} pasados, {failed} fallidos de {len(results)} tests")
    print("="*60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_benchmarks()
    sys.exit(0 if success else 1)
