"""
Unit tests for utils/metrics.py
"""

import sys
import os
import time
import json
import tempfile
import unittest

# Ensure parent dir is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.metrics import MetricsCollector, timed, get_metrics


class TestMetricsCollectorBasic(unittest.TestCase):
    """Test basic MetricsCollector recording and retrieval."""

    def setUp(self):
        # Reset singleton for each test
        MetricsCollector._instance = None
        self.m = MetricsCollector()

    def test_initial_state(self):
        s = self.m.get_summary()
        self.assertEqual(s["llm_calls"], 0)
        self.assertEqual(s["llm_latency_ms"], 0.0)
        self.assertEqual(s["tool_calls_total"], 0)
        self.assertEqual(s["embeddings_generated"], 0)
        self.assertEqual(s["errors_total"], 0)
        self.assertEqual(s["session_messages"], 0)

    def test_record_llm_call(self):
        self.m.record_llm_call(100.0)
        self.m.record_llm_call(200.0)
        s = self.m.get_summary()
        self.assertEqual(s["llm_calls"], 2)
        self.assertAlmostEqual(s["llm_latency_ms"], 150.0, places=1)

    def test_record_tool_call(self):
        self.m.record_tool_call("leer_archivo", 50.0)
        self.m.record_tool_call("leer_archivo", 70.0)
        self.m.record_tool_call("ejecutar_comando", 120.0)
        s = self.m.get_summary()
        self.assertEqual(s["tool_calls"]["leer_archivo"], 2)
        self.assertEqual(s["tool_calls"]["ejecutar_comando"], 1)
        self.assertAlmostEqual(s["tool_latency_ms"]["leer_archivo"], 60.0, places=1)
        self.assertAlmostEqual(s["tool_latency_ms"]["ejecutar_comando"], 120.0, places=1)
        self.assertEqual(s["tool_calls_total"], 3)

    def test_record_embedding_call(self):
        self.m.record_embedding_call()
        self.m.record_embedding_call()
        self.m.record_embedding_call()
        s = self.m.get_summary()
        self.assertEqual(s["embeddings_generated"], 3)

    def test_record_memory_operation(self):
        self.m.record_memory_operation("add")
        self.m.record_memory_operation("add")
        self.m.record_memory_operation("search")
        s = self.m.get_summary()
        self.assertEqual(s["memory_operations"]["add"], 2)
        self.assertEqual(s["memory_operations"]["search"], 1)

    def test_record_memory_operation_unknown_type(self):
        self.m.record_memory_operation("custom")
        s = self.m.get_summary()
        self.assertEqual(s["memory_operations"]["custom"], 1)

    def test_record_error(self):
        self.m.record_error("llm_timeout")
        self.m.record_error("llm_timeout")
        self.m.record_error("tool:eje_comando")
        s = self.m.get_summary()
        self.assertEqual(s["errors"]["llm_timeout"], 2)
        self.assertEqual(s["errors"]["tool:eje_comando"], 1)
        self.assertEqual(s["errors_total"], 3)

    def test_record_user_message(self):
        self.m.record_user_message()
        self.m.record_user_message()
        s = self.m.get_summary()
        self.assertEqual(s["session_messages"], 2)

    def test_tool_latency_overall(self):
        self.m.record_tool_call("a", 100.0)
        self.m.record_tool_call("b", 200.0)
        s = self.m.get_summary()
        self.assertAlmostEqual(s["tool_latency_overall_ms"], 150.0, places=1)

    def test_tool_latency_single_tool(self):
        self.m.record_tool_call("a", 100.0)
        self.m.record_tool_call("a", 200.0)
        self.assertAlmostEqual(self.m.tool_latency_ms("a"), 150.0, places=1)
        self.assertAlmostEqual(self.m.tool_latency_ms("b"), 0.0, places=1)


class TestMetricsCollectorReset(unittest.TestCase):
    """Test reset functionality."""

    def setUp(self):
        MetricsCollector._instance = None
        self.m = MetricsCollector()

    def test_reset_clears_counters(self):
        self.m.record_llm_call(100.0)
        self.m.record_tool_call("x", 50.0)
        self.m.record_embedding_call()
        self.m.record_user_message()
        self.m.record_error("test")

        self.m.reset()
        s = self.m.get_summary()
        self.assertEqual(s["llm_calls"], 0)
        self.assertEqual(s["tool_calls_total"], 0)
        self.assertEqual(s["embeddings_generated"], 0)
        self.assertEqual(s["session_messages"], 0)
        self.assertEqual(s["errors_total"], 0)

    def test_reset_stores_previous_session(self):
        self.m.record_llm_call(100.0)
        self.m.record_tool_call("x", 50.0)
        self.m.reset()

        prev = self.m._previous_session
        self.assertIsNotNone(prev)
        self.assertEqual(prev["llm_calls"], 1)
        self.assertEqual(prev["tool_calls"]["x"], 1)


class TestMetricsCollectorPersistence(unittest.TestCase):
    """Test save/load persistence."""

    def setUp(self):
        MetricsCollector._instance = None
        self.m = MetricsCollector()
        self.tmpdir = tempfile.mkdtemp()
        # Override the metrics file path
        self.original_file = None
        import utils.metrics as metrics_mod
        self.original_file = metrics_mod._METRICS_FILE
        self.test_file = os.path.join(self.tmpdir, "metrics.json")
        metrics_mod._METRICS_FILE = self.test_file

    def tearDown(self):
        import utils.metrics as metrics_mod
        if self.original_file:
            metrics_mod._METRICS_FILE = self.original_file
        # Clean up
        if os.path.exists(self.tmpdir):
            import shutil
            shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_creates_file(self):
        self.m.record_llm_call(50.0)
        self.m.save()
        self.assertTrue(os.path.exists(self.test_file))

    def test_save_content(self):
        self.m.record_llm_call(50.0)
        self.m.record_tool_call("test", 25.0)
        self.m.save()
        with open(self.test_file, "r") as f:
            data = json.load(f)
        self.assertEqual(data["llm_calls"], 1)
        self.assertEqual(data["tool_calls"]["test"], 1)
        self.assertIn("saved_at", data)

    def test_load_previous(self):
        self.m.record_llm_call(99.0)
        self.m.save()

        prev = self.m._load_previous()
        self.assertIsNotNone(prev)
        self.assertEqual(prev["llm_calls"], 1)

    def test_load_previous_no_file(self):
        prev = self.m._load_previous()
        self.assertIsNone(prev)


class TestTimedDecorator(unittest.TestCase):
    """Test the @timed decorator."""

    def setUp(self):
        MetricsCollector._instance = None

    def test_timed_llm(self):
        @timed("llm")
        def fake_generate():
            time.sleep(0.005)
            return "result"

        m = get_metrics()
        result = fake_generate()
        self.assertEqual(result, "result")
        s = m.get_summary()
        self.assertEqual(s["llm_calls"], 1)
        self.assertGreater(s["llm_latency_ms"], 0)

    def test_timed_tool(self):
        @timed("tool")
        def leer_archivo():
            return "content"

        m = get_metrics()
        result = leer_archivo()
        self.assertEqual(result, "content")
        s = m.get_summary()
        self.assertEqual(s["tool_calls"]["leer_archivo"], 1)

    def test_timed_embedding(self):
        @timed("embedding")
        def get_embedding():
            return [0.1, 0.2]

        m = get_metrics()
        result = get_embedding()
        self.assertEqual(result, [0.1, 0.2])
        s = m.get_summary()
        self.assertEqual(s["embeddings_generated"], 1)

    def test_timed_memory_add(self):
        @timed("memory")
        def add_conversation():
            return True

        m = get_metrics()
        add_conversation()
        s = m.get_summary()
        self.assertEqual(s["memory_operations"]["add"], 1)

    def test_timed_memory_search(self):
        @timed("memory")
        def search_memory():
            return []

        m = get_metrics()
        search_memory()
        s = m.get_summary()
        self.assertEqual(s["memory_operations"]["search"], 1)

    def test_timed_error_recording(self):
        @timed("llm")
        def failing_generate():
            raise RuntimeError("test error")

        m = get_metrics()
        with self.assertRaises(RuntimeError):
            failing_generate()
        s = m.get_summary()
        self.assertEqual(s["errors"]["llm"], 1)

    def test_timed_preserves_function_metadata(self):
        @timed("llm")
        def my_func():
            """My docstring."""
            pass

        self.assertEqual(my_func.__name__, "my_func")
        self.assertEqual(my_func.__doc__, "My docstring.")

    def test_timed_passes_args_kwargs(self):
        @timed("tool")
        def my_tool(a, b, c=None):
            return (a, b, c)

        m = get_metrics()
        result = my_tool(1, 2, c=3)
        self.assertEqual(result, (1, 2, 3))


class TestMetricsCollectorSingleton(unittest.TestCase):
    """Test singleton behavior."""

    def setUp(self):
        MetricsCollector._instance = None

    def test_singleton_returns_same_instance(self):
        m1 = MetricsCollector.get()
        m2 = MetricsCollector.get()
        self.assertIs(m1, m2)

    def test_get_metrics_returns_singleton(self):
        m1 = get_metrics()
        m2 = get_metrics()
        self.assertIs(m1, m2)

    def test_get_metrics_is_metrics_collector(self):
        m = get_metrics()
        self.assertIsInstance(m, MetricsCollector)


class TestGetFormattedSummary(unittest.TestCase):
    """Test formatted summary output."""

    def setUp(self):
        MetricsCollector._instance = None
        self.m = MetricsCollector()

    def test_formatted_summary_contains_key_info(self):
        self.m.record_llm_call(100.0)
        self.m.record_user_message()
        text = self.m.get_formatted_summary()
        self.assertIn("LLM calls", text)
        self.assertIn("1", text)
        self.assertIn("Mensajes", text)

    def test_formatted_summary_shows_tools(self):
        self.m.record_tool_call("leer_archivo", 50.0)
        text = self.m.get_formatted_summary()
        self.assertIn("leer_archivo", text)

    def test_formatted_summary_shows_errors(self):
        self.m.record_error("timeout")
        text = self.m.get_formatted_summary()
        self.assertIn("timeout", text)

    def test_formatted_summary_shows_previous_session(self):
        self.m.record_llm_call(100.0)
        self.m.reset()
        text = self.m.get_formatted_summary()
        self.assertIn("Sesion anterior", text)


if __name__ == "__main__":
    unittest.main()
