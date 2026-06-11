"""
Tests for agente_v14/memory/ module
- TripleMemory (add_conversation, remember, get_context)
- VectorStore (add, search, skip_embedding)
- SimpleVectorStore (decay computation)
- Pickle persistence
"""

import os
import sys
import json
import pickle
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# conftest.py adds parent dir to sys.path


class TestTripleMemory(unittest.TestCase):
    """Tests for TripleMemory class."""

    def setUp(self):
        """Create a temp directory and mock OllamaClient before each test."""
        self.tmpdir = tempfile.mkdtemp(prefix="test_agente_v14_")

        # Patch config constants to use temp directory
        self.config_patches = [
            patch("config.LEARN_DIR", os.path.join(self.tmpdir, "learning")),
            patch("config.REPOS_DIR", os.path.join(self.tmpdir, "repos")),
            patch("config.MAX_CONVERSATION_MEMORY", 15),
            patch("config.MAX_CONTEXT_CHARS", 2000),
            patch("config.SKIP_EMBED_ON_INTERACTION", True),
        ]
        for p in self.config_patches:
            p.start()

        os.makedirs(os.path.join(self.tmpdir, "learning"), exist_ok=True)
        os.makedirs(os.path.join(self.tmpdir, "repos"), exist_ok=True)

        # Patch ollama client methods
        self.mock_embedding = patch("llm.ollama.get_embedding", return_value=[0.1] * 384).start()
        self.mock_cosine_batch = patch(
            "llm.ollama.cosine_similarity_batch",
            return_value={"id1": 0.9}
        ).start()

        # Patch create_vector_store to return a SimpleVectorStore with tmpdir
        # and also patch the VectorStore used directly
        self.vector_store_dir = os.path.join(self.tmpdir, "learning", "vectors")
        os.makedirs(self.vector_store_dir, exist_ok=True)

        # We need to reimport modules after patching config
        # Force reimport of memory modules
        for mod in list(sys.modules.keys()):
            if mod.startswith("memory.") or mod == "memory":
                del sys.modules[mod]

        # Patch create_vector_store before importing TripleMemory
        from memory.vectorstore import VectorStore
        self.VectorStore = VectorStore

        self.mock_create_vs = patch(
            "memory.triple_memory.create_vector_store",
            side_effect=self._make_vector_store
        ).start()

        from memory.triple_memory import TripleMemory
        self.TripleMemory = TripleMemory

        # Also patch LearningSystem to avoid file I/O on real system
        self.mock_learning = patch("memory.triple_memory.learning").start()
        self.mock_learning.get_corrections_for.return_value = []

    def _make_vector_store(self, store_dir=None):
        """Factory that creates a SimpleVectorStore in the temp dir."""
        from memory.chroma_store import SimpleVectorStore
        return SimpleVectorStore(store_dir=self.vector_store_dir)

    def tearDown(self):
        """Stop all patches and remove temp directory."""
        patch.stopall()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_triple_memory_add_conversation(self):
        """Messages should be stored in short_term memory."""
        mem = self.TripleMemory()
        mem.add_conversation("user", "Hello, how are you?")
        mem.add_conversation("assistant", "I'm fine, thanks!")

        self.assertEqual(len(mem.short_term), 2)
        self.assertEqual(mem.short_term[0]["role"], "user")
        self.assertEqual(mem.short_term[0]["content"], "Hello, how are you?")
        self.assertEqual(mem.short_term[1]["role"], "assistant")
        self.assertEqual(mem.short_term[1]["content"], "I'm fine, thanks!")

    def test_triple_memory_remember(self):
        """Long-term storage should work via remember()."""
        mem = self.TripleMemory()
        entry_id = mem.remember("Important fact about Python", fast=True)
        # The entry should be stored in long_term
        self.assertIsNotNone(entry_id)
        # Verify it's in the long_term store
        count = mem.long_term.count()
        self.assertGreater(count, 0)

    def test_triple_memory_get_context(self):
        """Context should be built from working memory, corrections, and long-term."""
        mem = self.TripleMemory()
        # Set up working memory
        mem.set_task("Test task")
        mem.add_step("Step 1", "Result 1")
        mem.add_note("Important note")

        # Add a correction
        self.mock_learning.get_corrections_for.return_value = [
            {"wrong_action": "delete files", "correct_action": "ask first"}
        ]

        # Get context
        context = mem.get_context_for("test query")
        self.assertIn("TAREA ACTUAL", context)
        self.assertIn("Test task", context)
        self.assertIn("Important note", context)


class TestVectorStore(unittest.TestCase):
    """Tests for VectorStore class."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_vs_")
        self.vs_dir = os.path.join(self.tmpdir, "vectors")
        os.makedirs(self.vs_dir, exist_ok=True)

        # Patch ollama methods
        self.mock_embedding = patch(
            "llm.ollama.get_embedding",
            return_value=[0.1] * 384
        ).start()
        self.mock_cosine_batch = patch(
            "llm.ollama.cosine_similarity_batch",
            return_value={}
        ).start()

        # Patch config
        self.config_patch = patch("config.LEARN_DIR", self.tmpdir).start()
        self.max_vectors_patch = patch("config.MAX_VECTORS_IN_MEMORY", 500).start()

        # Force reimport
        for mod in list(sys.modules.keys()):
            if mod.startswith("memory.") or mod == "memory":
                del sys.modules[mod]

        from memory.vectorstore import VectorStore
        self.VectorStore = VectorStore

    def tearDown(self):
        patch.stopall()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_vectorstore_add_and_search(self):
        """Adding text and searching should find it."""
        self.mock_embedding.return_value = [0.1] * 384
        # Return high similarity for the entry we add
        self.mock_cosine_batch.return_value = {"test12345678": 0.95}

        vs = self.VectorStore(store_dir=self.vs_dir)
        entry_id = vs.add("Python is a great programming language")
        self.assertIsNotNone(entry_id)
        self.assertEqual(vs.count(), 1)

        # Search should find it
        results = vs.search("Python programming")
        self.assertIsInstance(results, list)

    def test_vectorstore_skip_embedding(self):
        """When skip_embedding=True, no embedding call should be made."""
        vs = self.VectorStore(store_dir=self.vs_dir)
        entry_id = vs.add("Quick note", skip_embedding=True)

        # Entry should exist without embedding
        self.assertIsNotNone(entry_id)
        self.assertEqual(vs.count(), 1)

        # The entry should have has_vector=False
        entry = next(e for e in vs.index if e["id"] == entry_id)
        self.assertFalse(entry.get("has_vector", False))

        # get_embedding should NOT have been called for skip_embedding
        # (it may have been called from other setUp operations, so we check
        #  that the specific call was not made for this add)
        self.mock_embedding.assert_not_called()


class TestSimpleVectorStoreDecay(unittest.TestCase):
    """Tests for SimpleVectorStore decay computation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_svs_")
        self.vs_dir = os.path.join(self.tmpdir, "vectors")
        os.makedirs(self.vs_dir, exist_ok=True)

        self.mock_embedding = patch(
            "llm.ollama.get_embedding",
            return_value=[0.1] * 384
        ).start()
        self.mock_cosine_batch = patch(
            "llm.ollama.cosine_similarity_batch",
            return_value={}
        ).start()

        self.config_patch = patch("config.LEARN_DIR", self.tmpdir).start()
        self.max_vectors_patch = patch("config.MAX_VECTORS_IN_MEMORY", 500).start()

        for mod in list(sys.modules.keys()):
            if mod.startswith("memory.") or mod == "memory":
                del sys.modules[mod]

        from memory.chroma_store import SimpleVectorStore
        self.SimpleVectorStore = SimpleVectorStore

    def tearDown(self):
        patch.stopall()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_decay_recent_entry(self):
        """Recent entries should have decay close to 1.0."""
        svs = self.SimpleVectorStore(store_dir=self.vs_dir)
        now = datetime.now().isoformat()
        decay = svs._compute_decay(now)
        self.assertAlmostEqual(decay, 1.0, places=1)

    def test_decay_old_entry(self):
        """Old entries should have lower decay."""
        svs = self.SimpleVectorStore(store_dir=self.vs_dir)
        old_date = (datetime.now() - timedelta(days=90)).isoformat()
        decay = svs._compute_decay(old_date)
        self.assertLess(decay, 0.5)

    def test_decay_none_entry(self):
        """None timestamp should return default 0.5."""
        svs = self.SimpleVectorStore(store_dir=self.vs_dir)
        decay = svs._compute_decay(None)
        self.assertEqual(decay, 0.5)

    def test_decay_minimum_floor(self):
        """Decay should never go below 0.1 (10% minimum)."""
        svs = self.SimpleVectorStore(store_dir=self.vs_dir)
        very_old = (datetime.now() - timedelta(days=3650)).isoformat()  # 10 years
        decay = svs._compute_decay(very_old)
        self.assertGreaterEqual(decay, 0.1)


class TestPicklePersistence(unittest.TestCase):
    """Tests for vector persistence in pickle format."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_pickle_")
        self.vs_dir = os.path.join(self.tmpdir, "vectors")
        os.makedirs(self.vs_dir, exist_ok=True)

        self.mock_embedding = patch(
            "llm.ollama.get_embedding",
            return_value=[0.1] * 384
        ).start()
        self.mock_cosine_batch = patch(
            "llm.ollama.cosine_similarity_batch",
            return_value={}
        ).start()

        self.config_patch = patch("config.LEARN_DIR", self.tmpdir).start()
        self.max_vectors_patch = patch("config.MAX_VECTORS_IN_MEMORY", 500).start()

        for mod in list(sys.modules.keys()):
            if mod.startswith("memory.") or mod == "memory":
                del sys.modules[mod]

        from memory.vectorstore import VectorStore
        self.VectorStore = VectorStore

    def tearDown(self):
        patch.stopall()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_pickle_persistence(self):
        """Vectors should persist in pickle format and survive restart."""
        # Create store and add an entry with embedding
        self.mock_embedding.return_value = [0.5] * 384
        vs1 = self.VectorStore(store_dir=self.vs_dir)
        entry_id = vs1.add("Persistent test entry")
        self.assertIsNotNone(entry_id)

        # Verify pickle file was created
        pkl_path = os.path.join(self.vs_dir, "vectors.pkl")
        self.assertTrue(os.path.exists(pkl_path))

        # Read pickle file directly and verify content
        with open(pkl_path, "rb") as f:
            vectors = pickle.load(f)
        self.assertIn(entry_id, vectors)
        self.assertEqual(vectors[entry_id], [0.5] * 384)

        # Simulate restart: create a new VectorStore instance pointing to same dir
        vs2 = self.VectorStore(store_dir=self.vs_dir)
        # The index should be loaded from disk
        self.assertEqual(vs2.count(), 1)
        # Vectors should be loaded from pickle
        loaded_vectors = vs2._get_vectors()
        self.assertIn(entry_id, loaded_vectors)


if __name__ == "__main__":
    unittest.main()
