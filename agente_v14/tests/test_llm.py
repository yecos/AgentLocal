"""
Tests for agente_v14/llm.py
- Cosine similarity (single and batch)
- LRU Cache (basic operations and eviction)
"""

import unittest
import math

# conftest.py adds parent dir to sys.path
from llm import LRUCache, OllamaClient


class TestCosineSimilarityIdentical(unittest.TestCase):
    """Identical vectors should return 1.0."""

    def test_identical_simple(self):
        vec = [1.0, 2.0, 3.0, 4.0]
        result = OllamaClient.cosine_similarity(vec, vec)
        self.assertAlmostEqual(result, 1.0, places=5)

    def test_identical_unit(self):
        vec = [1.0, 0.0, 0.0, 0.0]
        result = OllamaClient.cosine_similarity(vec, vec)
        self.assertAlmostEqual(result, 1.0, places=5)

    def test_identical_zeros(self):
        """Zero vectors have zero norm -> returns 0.0 (not 1.0)."""
        vec = [0.0, 0.0, 0.0]
        result = OllamaClient.cosine_similarity(vec, vec)
        self.assertEqual(result, 0.0)

    def test_identical_negative(self):
        vec = [-1.0, -2.0, -3.0]
        result = OllamaClient.cosine_similarity(vec, vec)
        self.assertAlmostEqual(result, 1.0, places=5)


class TestCosineSimilarityOrthogonal(unittest.TestCase):
    """Orthogonal vectors should return 0.0."""

    def test_x_y_orthogonal(self):
        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        result = OllamaClient.cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(result, 0.0, places=5)

    def test_3d_orthogonal(self):
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        result = OllamaClient.cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(result, 0.0, places=5)

    def test_mixed_orthogonal(self):
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 0.0, 5.0]
        result = OllamaClient.cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(result, 0.0, places=5)


class TestCosineSimilarityEmpty(unittest.TestCase):
    """Empty or mismatched vectors should return 0.0."""

    def test_both_empty(self):
        result = OllamaClient.cosine_similarity([], [])
        self.assertEqual(result, 0.0)

    def test_one_empty(self):
        result = OllamaClient.cosine_similarity([1.0, 2.0], [])
        self.assertEqual(result, 0.0)

    def test_none_vectors(self):
        result = OllamaClient.cosine_similarity(None, [1.0])
        self.assertEqual(result, 0.0)

    def test_mismatched_lengths(self):
        result = OllamaClient.cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])
        self.assertEqual(result, 0.0)


class TestCosineSimilarityBatch(unittest.TestCase):
    """Batch computation should match individual calls."""

    def test_batch_matches_individual(self):
        query = [1.0, 0.0, 0.0]
        vectors = {
            "a": [1.0, 0.0, 0.0],  # identical -> 1.0
            "b": [0.0, 1.0, 0.0],  # orthogonal -> 0.0
            "c": [0.5, 0.5, 0.0],  # 45 degrees -> ~0.707
        }
        batch_results = OllamaClient.cosine_similarity_batch(query, vectors)

        # Compare each individual result
        for key, vec in vectors.items():
            individual = OllamaClient.cosine_similarity(query, vec)
            self.assertAlmostEqual(batch_results[key], individual, places=4,
                                   msg=f"Batch vs individual mismatch for key '{key}'")

    def test_batch_empty_query(self):
        result = OllamaClient.cosine_similarity_batch([], {"a": [1.0]})
        self.assertEqual(result, {})

    def test_batch_empty_vectors(self):
        result = OllamaClient.cosine_similarity_batch([1.0, 2.0], {})
        self.assertEqual(result, {})

    def test_batch_mismatched_lengths_filtered(self):
        """Vectors with wrong length should be filtered out."""
        query = [1.0, 0.0]
        vectors = {
            "good": [1.0, 0.0],
            "bad": [1.0, 0.0, 0.0],  # wrong length
        }
        result = OllamaClient.cosine_similarity_batch(query, vectors)
        self.assertIn("good", result)
        self.assertNotIn("bad", result)


class TestLRUCacheBasic(unittest.TestCase):
    """Basic put and get operations."""

    def test_put_and_get(self):
        cache = LRUCache(maxsize=10)
        cache.put("key1", "value1")
        self.assertEqual(cache.get("key1"), "value1")

    def test_get_nonexistent(self):
        cache = LRUCache(maxsize=10)
        self.assertIsNone(cache.get("missing"))

    def test_put_overwrite(self):
        cache = LRUCache(maxsize=10)
        cache.put("key1", "old")
        cache.put("key1", "new")
        self.assertEqual(cache.get("key1"), "new")

    def test_len(self):
        cache = LRUCache(maxsize=10)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertEqual(len(cache), 2)

    def test_clear(self):
        cache = LRUCache(maxsize=10)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.clear()
        self.assertEqual(len(cache), 0)
        self.assertIsNone(cache.get("a"))


class TestLRUCacheEviction(unittest.TestCase):
    """Oldest items should be evicted when cache is full."""

    def test_eviction_order(self):
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        # Cache is full. Adding "d" should evict "a" (oldest)
        cache.put("d", 4)
        self.assertIsNone(cache.get("a"))
        self.assertEqual(cache.get("b"), 2)
        self.assertEqual(cache.get("c"), 3)
        self.assertEqual(cache.get("d"), 4)

    def test_access_renews_entry(self):
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        # Access "a" to make it most recently used
        _ = cache.get("a")
        # Adding "d" should now evict "b" (oldest unused)
        cache.put("d", 4)
        self.assertEqual(cache.get("a"), 1)  # Still present
        self.assertIsNone(cache.get("b"))    # Evicted
        self.assertEqual(cache.get("c"), 3)
        self.assertEqual(cache.get("d"), 4)

    def test_update_renews_entry(self):
        cache = LRUCache(maxsize=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        # Update "a" to make it most recently used
        cache.put("a", 10)
        # Adding "d" should evict "b" (oldest unused)
        cache.put("d", 4)
        self.assertEqual(cache.get("a"), 10)  # Updated value, still present
        self.assertIsNone(cache.get("b"))     # Evicted

    def test_maxsize_one(self):
        cache = LRUCache(maxsize=1)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertIsNone(cache.get("a"))
        self.assertEqual(cache.get("b"), 2)


if __name__ == "__main__":
    unittest.main()
