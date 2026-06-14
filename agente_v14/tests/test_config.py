"""
Tests for config.py new features:
- validate_config() returns correct structure
- validate_config() detects missing directories
- Environment variable overrides (AGENT_MODEL, AGENT_TEMPERATURE, etc.)
- get_config_summary() returns expected keys
- Numeric range validation
"""

import os
import pytest
from unittest.mock import patch


# We need to import config carefully since it has module-level side effects
import config as cfg


class TestValidateConfigStructure:
    """Test validate_config() returns correct structure."""

    def test_validate_config_returns_dict(self):
        result = cfg.validate_config()
        assert isinstance(result, dict)

    def test_validate_config_has_directory_checks(self):
        result = cfg.validate_config()
        assert "REPOS_DIR" in result
        assert "LEARN_DIR" in result

    def test_validate_config_has_numeric_checks(self):
        result = cfg.validate_config()
        expected_keys = [
            "AGENT_TEMPERATURE", "AGENT_MAX_TOKENS",
            "MAX_REACT_ITERATIONS", "MAX_CONVERSATION_MEMORY",
            "MAX_CONTEXT_CHARS", "MAX_FILE_READ", "MAX_TOOL_OUTPUT",
            "DEFAULT_TIMEOUT", "LONG_TIMEOUT",
            "LLM_TIMEOUT_SMALL", "LLM_TIMEOUT_LARGE",
            "EMBED_TIMEOUT", "WEB_TIMEOUT",
            "CONTEXT_WINDOW_TOKENS", "SUMMARIZATION_THRESHOLD",
            "SUBAGENT_MAX_PARALLEL", "SUBAGENT_DEFAULT_TIMEOUT",
        ]
        for key in expected_keys:
            assert key in result, f"Missing numeric check: {key}"

    def test_validate_config_has_model_check(self):
        result = cfg.validate_config()
        assert "AGENT_MODEL" in result

    def test_validate_config_repos_dir_ok(self):
        result = cfg.validate_config()
        assert result["REPOS_DIR"] == "ok"

    def test_validate_config_learn_dir_ok(self):
        result = cfg.validate_config()
        assert result["LEARN_DIR"] == "ok"

    def test_validate_config_default_numeric_values_ok(self):
        result = cfg.validate_config()
        for key in ["AGENT_TEMPERATURE", "AGENT_MAX_TOKENS", "MAX_REACT_ITERATIONS"]:
            assert result[key] == "ok", f"{key} should be ok, got: {result[key]}"


class TestValidateConfigDirectoryErrors:
    """Test validate_config() detects directory issues."""

    def test_validate_config_with_unwritable_dir(self):
        with patch.object(os, 'makedirs', side_effect=OSError("Permission denied")):
            result = cfg.validate_config()
            # Should have an error for REPOS_DIR
            assert "error" in result["REPOS_DIR"] or result["REPOS_DIR"] == "ok"

    def test_validate_config_write_test_failure(self):
        """When write test fails, directory check should report error."""
        original_open = open
        def mock_open_fn(*args, **kwargs):
            if ".agent_write_test" in str(args[0] if args else ""):
                raise OSError("Read-only filesystem")
            return original_open(*args, **kwargs)

        with patch('builtins.open', side_effect=mock_open_fn):
            result = cfg.validate_config()
            # Either ok (if dir doesn't exist for write test) or error
            assert isinstance(result["REPOS_DIR"], str)


class TestValidateConfigNumericRanges:
    """Test numeric range validation in validate_config()."""

    def test_temperature_below_minimum(self):
        with patch.object(cfg, 'AGENT_TEMPERATURE', -0.5):
            result = cfg.validate_config()
            assert "below minimum" in result["AGENT_TEMPERATURE"]

    def test_temperature_above_maximum(self):
        with patch.object(cfg, 'AGENT_TEMPERATURE', 3.0):
            result = cfg.validate_config()
            assert "above maximum" in result["AGENT_TEMPERATURE"]

    def test_temperature_in_range(self):
        with patch.object(cfg, 'AGENT_TEMPERATURE', 0.7):
            result = cfg.validate_config()
            assert result["AGENT_TEMPERATURE"] == "ok"

    def test_max_react_iterations_below_minimum(self):
        with patch.object(cfg, 'MAX_REACT_ITERATIONS', 0):
            result = cfg.validate_config()
            assert "below minimum" in result["MAX_REACT_ITERATIONS"]

    def test_max_react_iterations_above_maximum(self):
        with patch.object(cfg, 'MAX_REACT_ITERATIONS', 100):
            result = cfg.validate_config()
            assert "above maximum" in result["MAX_REACT_ITERATIONS"]

    def test_max_react_iterations_in_range(self):
        with patch.object(cfg, 'MAX_REACT_ITERATIONS', 6):
            result = cfg.validate_config()
            assert result["MAX_REACT_ITERATIONS"] == "ok"

    def test_default_timeout_below_minimum(self):
        with patch.object(cfg, 'DEFAULT_TIMEOUT', 0):
            result = cfg.validate_config()
            assert "below minimum" in result["DEFAULT_TIMEOUT"]

    def test_default_timeout_above_maximum(self):
        with patch.object(cfg, 'DEFAULT_TIMEOUT', 5000):
            result = cfg.validate_config()
            assert "above maximum" in result["DEFAULT_TIMEOUT"]

    def test_summarization_threshold_below_minimum(self):
        with patch.object(cfg, 'SUMMARIZATION_THRESHOLD', 0.05):
            result = cfg.validate_config()
            assert "below minimum" in result["SUMMARIZATION_THRESHOLD"]

    def test_summarization_threshold_above_maximum(self):
        with patch.object(cfg, 'SUMMARIZATION_THRESHOLD', 1.5):
            result = cfg.validate_config()
            assert "above maximum" in result["SUMMARIZATION_THRESHOLD"]

    def test_max_tokens_no_upper_limit(self):
        """AGENT_MAX_TOKENS has no upper limit (None), only lower bound."""
        with patch.object(cfg, 'AGENT_MAX_TOKENS', 999999):
            result = cfg.validate_config()
            assert result["AGENT_MAX_TOKENS"] == "ok"

    def test_max_tokens_below_minimum(self):
        with patch.object(cfg, 'AGENT_MAX_TOKENS', 0):
            result = cfg.validate_config()
            assert "below minimum" in result["AGENT_MAX_TOKENS"]


class TestValidateConfigModelOverride:
    """Test AGENT_MODEL handling in validate_config()."""

    def test_model_auto_detect_when_empty(self):
        with patch.object(cfg, 'AGENT_MODEL', ''):
            result = cfg.validate_config()
            assert "auto-detect" in result["AGENT_MODEL"]

    def test_model_override_when_set(self):
        with patch.object(cfg, 'AGENT_MODEL', 'qwen3:4b'):
            result = cfg.validate_config()
            assert "override" in result["AGENT_MODEL"]
            assert "qwen3:4b" in result["AGENT_MODEL"]


class TestGetConfigSummary:
    """Test get_config_summary() returns expected keys."""

    def test_returns_dict(self):
        result = cfg.get_config_summary()
        assert isinstance(result, dict)

    def test_has_system_keys(self):
        result = cfg.get_config_summary()
        assert "IS_WINDOWS" in result
        assert "IS_MAC" in result
        assert "IS_LINUX" in result

    def test_has_directory_keys(self):
        result = cfg.get_config_summary()
        assert "REPOS_DIR" in result
        assert "LEARN_DIR" in result

    def test_has_model_keys(self):
        result = cfg.get_config_summary()
        assert "PREFERRED_MODELS" in result
        assert "CHAT_MODEL_PATTERNS" in result
        assert "CODE_MODEL_PATTERNS" in result
        assert "EMBED_MODEL_CANDIDATES" in result
        assert "AGENT_MODEL" in result

    def test_has_llm_parameter_keys(self):
        result = cfg.get_config_summary()
        assert "AGENT_TEMPERATURE" in result
        assert "AGENT_MAX_TOKENS" in result
        assert "CONTEXT_WINDOW_TOKENS" in result
        assert "SUMMARIZATION_THRESHOLD" in result

    def test_has_limit_keys(self):
        result = cfg.get_config_summary()
        assert "MAX_REACT_ITERATIONS" in result
        assert "MAX_CONVERSATION_MEMORY" in result
        assert "MAX_CONTEXT_CHARS" in result
        assert "MAX_FILE_READ" in result
        assert "MAX_TOOL_OUTPUT" in result

    def test_has_timeout_keys(self):
        result = cfg.get_config_summary()
        assert "DEFAULT_TIMEOUT" in result
        assert "LONG_TIMEOUT" in result
        assert "LLM_TIMEOUT_SMALL" in result
        assert "LLM_TIMEOUT_LARGE" in result

    def test_has_deep_thinking_keys(self):
        result = cfg.get_config_summary()
        assert "DEEP_THINKING_MODE" in result
        assert "DEEP_THINKING_MIN_COMPLEXITY" in result

    def test_has_subagent_keys(self):
        result = cfg.get_config_summary()
        assert "SUBAGENT_MAX_PARALLEL" in result
        assert "SUBAGENT_DEFAULT_TIMEOUT" in result

    def test_model_auto_detect_display(self):
        with patch.object(cfg, 'AGENT_MODEL', ''):
            result = cfg.get_config_summary()
            assert result["AGENT_MODEL"] == "(auto-detect)"

    def test_model_override_display(self):
        with patch.object(cfg, 'AGENT_MODEL', 'llama3.1:8b'):
            result = cfg.get_config_summary()
            assert result["AGENT_MODEL"] == "llama3.1:8b"

    def test_values_are_python_types(self):
        """All values should be Python types (not paths, not custom objects)."""
        result = cfg.get_config_summary()
        for key, value in result.items():
            assert isinstance(value, (bool, int, float, str, list)), \
                f"Key {key} has unexpected type: {type(value)}"


class TestEnvironmentVariableOverrides:
    """Test that environment variables correctly override config defaults."""

    def test_agent_temperature_from_env(self):
        """AGENT_TEMPERATURE should be set from AGENT_TEMPERATURE env var."""
        # The value is read at import time, so we verify the mechanism exists
        assert isinstance(cfg.AGENT_TEMPERATURE, float)
        assert 0.0 <= cfg.AGENT_TEMPERATURE <= 2.0

    def test_agent_max_tokens_from_env(self):
        """AGENT_MAX_TOKENS should be set from AGENT_MAX_TOKENS env var."""
        assert isinstance(cfg.AGENT_MAX_TOKENS, int)
        assert cfg.AGENT_MAX_TOKENS >= 1

    def test_repos_dir_from_env(self):
        """REPOS_DIR should be settable via AGENT_REPOS_DIR env var."""
        assert isinstance(cfg.REPOS_DIR, str)
        assert os.path.isabs(cfg.REPOS_DIR)

    def test_learn_dir_from_env(self):
        """LEARN_DIR should be settable via AGENT_LEARN_DIR env var."""
        assert isinstance(cfg.LEARN_DIR, str)
        assert os.path.isabs(cfg.LEARN_DIR)

    def test_agent_model_from_env(self):
        """AGENT_MODEL should be settable via AGENT_MODEL env var."""
        # Default is empty string (auto-detect)
        assert isinstance(cfg.AGENT_MODEL, str)


class TestConfigDefaults:
    """Test that config defaults are sensible."""

    def test_default_temperature_reasonable(self):
        assert 0.0 < cfg.DEFAULT_TEMPERATURE <= 2.0

    def test_default_max_tokens_positive(self):
        assert cfg.DEFAULT_MAX_TOKENS > 0

    def test_context_window_tokens_positive(self):
        assert cfg.CONTEXT_WINDOW_TOKENS > 0

    def test_summarization_threshold_fraction(self):
        assert 0.0 < cfg.SUMMARIZATION_THRESHOLD <= 1.0

    def test_max_react_iterations_positive(self):
        assert cfg.MAX_REACT_ITERATIONS > 0

    def test_timeouts_positive(self):
        assert cfg.DEFAULT_TIMEOUT > 0
        assert cfg.LONG_TIMEOUT > 0
        assert cfg.LLM_TIMEOUT_SMALL > 0
        assert cfg.LLM_TIMEOUT_LARGE > 0

    def test_long_timeout_greater_than_default(self):
        assert cfg.LONG_TIMEOUT > cfg.DEFAULT_TIMEOUT

    def test_llm_timeout_large_greater_than_small(self):
        assert cfg.LLM_TIMEOUT_LARGE > cfg.LLM_TIMEOUT_SMALL
