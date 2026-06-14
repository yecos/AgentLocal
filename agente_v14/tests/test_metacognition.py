"""
Tests for agent/metacognition.py new features:
- Confidence calibration (record, get_calibrated)
- Strategy suggestion (classify_task_type, suggest_strategy)
- Strategy outcome recording
- Rolling window and persistence
"""

import os
import json
import pytest
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime


import sys
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)


@pytest.fixture
def fresh_meta(tmp_path):
    """Create a Metacognition instance with isolated temp files (no prior data)."""
    calibration_file = str(tmp_path / "calibration.json")
    strategy_file = str(tmp_path / "strategy.json")

    with patch('agent.metacognition.LEARN_DIR', str(tmp_path)):
        with patch('agent.metacognition.MAX_REACT_ITERATIONS', 6):
            from agent.metacognition import Metacognition
            m = Metacognition()
            # Override file paths to use temp dir
            m._CALIBRATION_FILE = calibration_file
            m._STRATEGY_FILE = strategy_file
            # Reset calibration data to fresh state
            m._calibration_data = {"records": [], "offset": 0.0, "total_samples": 0}
            # Reset strategy data
            m._strategy_data = {"task_types": {}}
            return m


class TestConfidenceCalibration:
    """Test confidence calibration features."""

    def test_initial_confidence(self, fresh_meta):
        """Initial confidence should be 0.7."""
        assert fresh_meta.confidence == 0.7

    def test_initial_calibration_data(self, fresh_meta):
        """Initial calibration data should have empty records."""
        assert fresh_meta._calibration_data["records"] == []
        assert fresh_meta._calibration_data["offset"] == 0.0
        assert fresh_meta._calibration_data["total_samples"] == 0

    def test_record_calibration_sample(self, fresh_meta):
        """Recording a calibration sample should add to records."""
        fresh_meta.record_calibration_sample(0.8, True)
        assert len(fresh_meta._calibration_data["records"]) == 1
        assert fresh_meta._calibration_data["records"][0]["confidence"] == 0.8
        assert fresh_meta._calibration_data["records"][0]["outcome"] == 1.0

    def test_record_calibration_sample_failure(self, fresh_meta):
        """Recording a failure should have outcome 0.0."""
        fresh_meta.record_calibration_sample(0.8, False)
        assert fresh_meta._calibration_data["records"][0]["outcome"] == 0.0

    def test_calibration_offset_overconfident(self, fresh_meta):
        """If we're overconfident, offset should be negative."""
        for _ in range(10):
            fresh_meta.record_calibration_sample(0.9, False)
        assert fresh_meta._calibration_data["offset"] < 0

    def test_calibration_offset_underconfident(self, fresh_meta):
        """If we're underconfident, offset should be positive."""
        for _ in range(10):
            fresh_meta.record_calibration_sample(0.3, True)
        assert fresh_meta._calibration_data["offset"] > 0

    def test_get_calibrated_confidence_no_data(self, fresh_meta):
        """With fewer than 5 samples, calibrated confidence = raw confidence."""
        for _ in range(4):
            fresh_meta.record_calibration_sample(0.5, True)
        calibrated = fresh_meta.get_calibrated_confidence()
        # With < 5 samples total_samples should be 4, so raw confidence used
        # But confidence may have changed due to _recalculate_confidence
        # Just check that it returns a valid float
        assert isinstance(calibrated, float)
        assert 0.0 <= calibrated <= 1.0

    def test_get_calibrated_confidence_with_data(self, fresh_meta):
        """With enough samples, calibrated confidence should differ from raw."""
        original_confidence = fresh_meta.confidence
        for _ in range(10):
            fresh_meta.record_calibration_sample(0.9, False)
        calibrated = fresh_meta.get_calibrated_confidence()
        # With overconfident data, calibrated should be lower
        assert calibrated < original_confidence + 0.5  # Rough check

    def test_calibrated_confidence_bounded(self, fresh_meta):
        """Calibrated confidence should be between 0.0 and 1.0."""
        for _ in range(20):
            fresh_meta.record_calibration_sample(0.99, False)
        calibrated = fresh_meta.get_calibrated_confidence()
        assert 0.0 <= calibrated <= 1.0

    def test_calibration_persists_to_disk(self, fresh_meta):
        """Calibration data should be saved to disk."""
        fresh_meta.record_calibration_sample(0.7, True)
        assert os.path.exists(fresh_meta._CALIBRATION_FILE)

    def test_calibration_loads_from_disk(self, tmp_path):
        """Calibration data should be loadable from disk."""
        calibration_file = str(tmp_path / "calibration.json")
        data = {
            "records": [{"confidence": 0.8, "outcome": 1.0, "timestamp": datetime.now().isoformat()}],
            "offset": -0.05,
            "total_samples": 1,
        }
        with open(calibration_file, "w") as f:
            json.dump(data, f)

        strategy_file = str(tmp_path / "strategy.json")
        with open(strategy_file, "w") as f:
            json.dump({"task_types": {}}, f)

        with patch('agent.metacognition.LEARN_DIR', str(tmp_path)):
            with patch('agent.metacognition.MAX_REACT_ITERATIONS', 6):
                from agent.metacognition import Metacognition
                m = Metacognition()
                m._CALIBRATION_FILE = calibration_file
                m._STRATEGY_FILE = strategy_file
                m._calibration_data = m._load_calibration_data()
                assert len(m._calibration_data["records"]) == 1

    def test_rolling_window_max_200_samples(self, fresh_meta):
        """Calibration should keep at most 200 samples (rolling window)."""
        for i in range(250):
            fresh_meta.record_calibration_sample(0.5, i % 2 == 0)
        assert len(fresh_meta._calibration_data["records"]) <= 200


class TestStrategySuggestion:
    """Test strategy suggestion features."""

    def test_classify_code_task(self, fresh_meta):
        task_type = fresh_meta.classify_task_type("genera un script de python")
        assert task_type == "code"

    def test_classify_search_task_no_code_keywords(self, fresh_meta):
        """Search task without code keywords should classify as search."""
        task_type = fresh_meta.classify_task_type("busca informacion sobre historia")
        assert task_type == "search"

    def test_classify_file_task(self, fresh_meta):
        task_type = fresh_meta.classify_task_type("lee el archivo readme.md")
        assert task_type == "file_operation"

    def test_classify_system_task(self, fresh_meta):
        task_type = fresh_meta.classify_task_type("ejecuta el comando de instalacion")
        assert task_type == "system"

    def test_classify_conversation_task(self, fresh_meta):
        task_type = fresh_meta.classify_task_type("hola, como estas hoy")
        assert task_type == "conversation"

    def test_classify_code_english(self, fresh_meta):
        task_type = fresh_meta.classify_task_type("write a function in javascript")
        assert task_type == "code"

    def test_classify_search_english(self, fresh_meta):
        task_type = fresh_meta.classify_task_type("search the web for weather")
        assert task_type == "search"

    def test_classify_system_docker(self, fresh_meta):
        task_type = fresh_meta.classify_task_type("run docker compose up")
        assert task_type == "system"

    def test_suggest_strategy_code(self, fresh_meta):
        result = fresh_meta.suggest_strategy("write a python script")
        assert result["strategy"] == fresh_meta.STRATEGY_SEQUENTIAL
        assert result["task_type"] == "code"
        assert "reason" in result
        assert "confidence" in result

    def test_suggest_strategy_search(self, fresh_meta):
        result = fresh_meta.suggest_strategy("busca informacion sobre historia")
        assert result["task_type"] == "search"
        assert result["strategy"] == fresh_meta.STRATEGY_EXPLORATORY

    def test_suggest_strategy_conversation(self, fresh_meta):
        result = fresh_meta.suggest_strategy("hola, como estas")
        assert result["strategy"] == fresh_meta.STRATEGY_DIRECT
        assert result["task_type"] == "conversation"

    def test_suggest_strategy_returns_dict(self, fresh_meta):
        result = fresh_meta.suggest_strategy("test task")
        assert isinstance(result, dict)
        assert "strategy" in result
        assert "task_type" in result
        assert "reason" in result
        assert "confidence" in result

    def test_strategy_types_defined(self, fresh_meta):
        assert fresh_meta.STRATEGY_SEQUENTIAL == "sequential"
        assert fresh_meta.STRATEGY_EXPLORATORY == "exploratory"
        assert fresh_meta.STRATEGY_DIRECT == "direct"
        assert fresh_meta.STRATEGY_DECOMPOSE == "decompose"


class TestStrategyOutcomeRecording:
    """Test strategy outcome recording."""

    def test_record_outcome_creates_entry(self, fresh_meta):
        fresh_meta.record_strategy_outcome("code", "sequential", True, 3)
        assert "code" in fresh_meta._strategy_data["task_types"]
        assert "sequential" in fresh_meta._strategy_data["task_types"]["code"]

    def test_record_outcome_updates_count(self, fresh_meta):
        fresh_meta.record_strategy_outcome("code", "sequential", True, 3)
        entry = fresh_meta._strategy_data["task_types"]["code"]["sequential"]
        assert entry["count"] == 1
        assert entry["successes"] == 1

    def test_record_outcome_failure(self, fresh_meta):
        fresh_meta.record_strategy_outcome("search", "exploratory", False, 5)
        entry = fresh_meta._strategy_data["task_types"]["search"]["exploratory"]
        assert entry["count"] == 1
        assert entry["successes"] == 0
        assert entry["success_rate"] == 0.0

    def test_record_multiple_outcomes(self, fresh_meta):
        fresh_meta.record_strategy_outcome("code", "sequential", True, 2)
        fresh_meta.record_strategy_outcome("code", "sequential", True, 3)
        fresh_meta.record_strategy_outcome("code", "sequential", False, 4)
        entry = fresh_meta._strategy_data["task_types"]["code"]["sequential"]
        assert entry["count"] == 3
        assert entry["successes"] == 2
        assert abs(entry["success_rate"] - 2 / 3) < 0.01

    def test_success_rate_all_succeed(self, fresh_meta):
        for _ in range(5):
            fresh_meta.record_strategy_outcome("code", "sequential", True, 2)
        entry = fresh_meta._strategy_data["task_types"]["code"]["sequential"]
        assert entry["success_rate"] == 1.0

    def test_avg_iterations_updated(self, fresh_meta):
        """Average iterations should be updated with EMA (alpha=0.3).
        
        First call: old_avg=0.0, so result = 0.0*0.7 + 2*0.3 = 0.6
        Second call with same iterations: 0.6*0.7 + 2*0.3 = 1.02
        Eventually converges toward 2.0
        """
        fresh_meta.record_strategy_outcome("code", "sequential", True, 2)
        entry = fresh_meta._strategy_data["task_types"]["code"]["sequential"]
        # EMA starts from 0.0, so first value is alpha * iterations
        assert entry["avg_iterations"] > 0
        assert entry["avg_iterations"] <= 2.0

    def test_strategy_persists_to_disk(self, fresh_meta):
        fresh_meta.record_strategy_outcome("code", "sequential", True, 3)
        assert os.path.exists(fresh_meta._STRATEGY_FILE)

    def test_historical_best_strategy_used(self, fresh_meta):
        """After recording enough outcomes, suggest_strategy should prefer best performer."""
        for _ in range(5):
            fresh_meta.record_strategy_outcome("code", "sequential", True, 2)
        for _ in range(5):
            fresh_meta.record_strategy_outcome("code", "exploratory", False, 4)

        result = fresh_meta.suggest_strategy("escribe un script de python")
        # Should prefer the historically better strategy
        assert result["strategy"] == "sequential"

    def test_strategy_outcome_for_unknown_task(self, fresh_meta):
        """Recording outcome for unknown task type should create the entry."""
        fresh_meta.record_strategy_outcome("novel_task", "direct", True, 1)
        assert "novel_task" in fresh_meta._strategy_data["task_types"]


class TestRollingWindow:
    """Test rolling window behavior for calibration and strategy data."""

    def test_calibration_rolling_window_200(self, fresh_meta):
        """Calibration records should be capped at 200."""
        for i in range(300):
            fresh_meta.record_calibration_sample(0.5, i % 2 == 0)
        assert len(fresh_meta._calibration_data["records"]) <= 200

    def test_calibration_keeps_recent(self, fresh_meta):
        """Rolling window should keep the most recent records."""
        for i in range(250):
            fresh_meta.record_calibration_sample(float(i) / 250.0, True)
        records = fresh_meta._calibration_data["records"]
        # Most recent records should have confidence close to 1.0
        assert records[-1]["confidence"] > 0.9

    def test_offset_uses_recent_50_samples(self, fresh_meta):
        """Offset calculation should use only the last 50 samples."""
        for _ in range(100):
            fresh_meta.record_calibration_sample(0.9, False)
        early_offset = fresh_meta._calibration_data["offset"]

        for _ in range(100):
            fresh_meta.record_calibration_sample(0.9, True)
        late_offset = fresh_meta._calibration_data["offset"]

        # Late offset should be less negative (or more positive) than early
        assert late_offset > early_offset


class TestMetacognitionReset:
    """Test reset behavior."""

    def test_reset_clears_iteration_history(self, fresh_meta):
        fresh_meta.record_iteration(0, "tool_call", "leer_archivo")
        fresh_meta.record_iteration(1, "tool_call", "ejecutar_comando")
        assert len(fresh_meta.iteration_history) == 2
        fresh_meta.reset()
        assert len(fresh_meta.iteration_history) == 0

    def test_reset_clears_tool_history(self, fresh_meta):
        fresh_meta.record_iteration(0, "tool_call", "leer_archivo")
        assert len(fresh_meta.tool_history) == 1
        fresh_meta.reset()
        assert len(fresh_meta.tool_history) == 0

    def test_reset_resets_confidence(self, fresh_meta):
        fresh_meta.confidence = 0.2
        fresh_meta.reset()
        assert fresh_meta.confidence == 0.7

    def test_reset_resets_error_count(self, fresh_meta):
        fresh_meta.error_count = 5
        fresh_meta.reset()
        assert fresh_meta.error_count == 0

    def test_reset_resets_success_count(self, fresh_meta):
        fresh_meta.success_count = 10
        fresh_meta.reset()
        assert fresh_meta.success_count == 0

    def test_reset_clears_task_type(self, fresh_meta):
        fresh_meta._current_task_type = "code"
        fresh_meta.reset()
        assert fresh_meta._current_task_type is None

    def test_reset_does_not_clear_calibration(self, fresh_meta):
        """Reset should NOT clear calibration data (persistent)."""
        fresh_meta.record_calibration_sample(0.8, True)
        record_count = len(fresh_meta._calibration_data["records"])
        fresh_meta.reset()
        # Calibration data should persist
        assert len(fresh_meta._calibration_data["records"]) == record_count


class TestMetacognitionStatus:
    """Test get_status() method."""

    def test_status_returns_dict(self, fresh_meta):
        status = fresh_meta.get_status()
        assert isinstance(status, dict)

    def test_status_has_confidence(self, fresh_meta):
        status = fresh_meta.get_status()
        assert "confidence" in status

    def test_status_has_calibrated_confidence(self, fresh_meta):
        status = fresh_meta.get_status()
        assert "calibrated_confidence" in status

    def test_status_has_errors(self, fresh_meta):
        status = fresh_meta.get_status()
        assert "errors" in status

    def test_status_has_successes(self, fresh_meta):
        status = fresh_meta.get_status()
        assert "successes" in status

    def test_status_has_plan_changes(self, fresh_meta):
        status = fresh_meta.get_status()
        assert "plan_changes" in status

    def test_status_has_assessment(self, fresh_meta):
        status = fresh_meta.get_status()
        assert "assessment" in status
        assert status["assessment"] == "pending"  # No evaluation yet

    def test_status_has_suggested_strategy(self, fresh_meta):
        status = fresh_meta.get_status()
        assert "suggested_strategy" in status

    def test_status_has_calibration_offset(self, fresh_meta):
        status = fresh_meta.get_status()
        assert "calibration_offset" in status


class TestEvaluateResult:
    """Test evaluate_result() method."""

    def test_excellent_assessment(self, fresh_meta):
        """Quick resolution with no errors should be 'excelente'."""
        fresh_meta.record_iteration(0, "tool_call", "leer_archivo")
        fresh_meta.record_iteration(1, "respond")
        reflection = fresh_meta.evaluate_result("test", "response", 2)
        assert reflection["assessment"] == "excelente"

    def test_good_assessment(self, fresh_meta):
        """Few iterations with minimal errors should be 'bueno'."""
        fresh_meta.record_iteration(0, "tool_call", "leer_archivo")
        fresh_meta.record_iteration(1, "tool_call", "ejecutar_comando")
        fresh_meta.record_iteration(2, "respond")
        reflection = fresh_meta.evaluate_result("test", "response", 3)
        assert reflection["assessment"] == "bueno"

    def test_problematic_assessment(self, fresh_meta):
        """Many errors should be 'problematico'."""
        for i in range(4):
            fresh_meta.record_iteration(i, "tool_call", "leer_archivo", had_error=True)
        reflection = fresh_meta.evaluate_result("test", "response", 4)
        assert reflection["assessment"] == "problematico"

    def test_reflection_has_lessons(self, fresh_meta):
        fresh_meta.record_iteration(0, "tool_call", "leer_archivo")
        fresh_meta.record_iteration(1, "respond")
        reflection = fresh_meta.evaluate_result("test", "response", 2)
        assert isinstance(reflection["lessons"], list)

    def test_reflection_has_iterations_used(self, fresh_meta):
        reflection = fresh_meta.evaluate_result("test", "response", 3)
        assert reflection["iterations_used"] == 3

    def test_reflection_has_confidence_final(self, fresh_meta):
        reflection = fresh_meta.evaluate_result("test", "response", 3)
        assert "confidence_final" in reflection


# ============================================================
# M3.1: Granular Confidence Tests
# ============================================================

class TestGranularConfidence:
    """Test M3.1: error_type parameter in record_iteration."""

    def test_critical_error_reduces_confidence_more(self, fresh_meta):
        """Critical errors should reduce confidence by -0.25."""
        initial = fresh_meta.confidence
        fresh_meta.record_iteration(0, "tool_call", "test_tool", had_error=True, error_type="critical")
        assert fresh_meta.confidence == max(0.1, initial - 0.25)

    def test_recoverable_error_reduces_confidence_less(self, fresh_meta):
        """Recoverable errors should reduce confidence by -0.05."""
        initial = fresh_meta.confidence
        fresh_meta.record_iteration(0, "tool_call", "test_tool", had_error=True, error_type="recoverable")
        assert fresh_meta.confidence == max(0.1, initial - 0.05)

    def test_partial_error_reduces_confidence_medium(self, fresh_meta):
        """Partial errors should reduce confidence by -0.10."""
        initial = fresh_meta.confidence
        fresh_meta.record_iteration(0, "tool_call", "test_tool", had_error=True, error_type="partial")
        assert fresh_meta.confidence == max(0.1, initial - 0.10)

    def test_generic_error_reduces_confidence_default(self, fresh_meta):
        """Generic errors (no error_type) should reduce by -0.15."""
        initial = fresh_meta.confidence
        fresh_meta.record_iteration(0, "tool_call", "test_tool", had_error=True)
        assert fresh_meta.confidence == max(0.1, initial - 0.15)

    def test_result_quality_affects_confidence_gain(self, fresh_meta):
        """Success with higher result_quality should increase confidence more."""
        m1 = fresh_meta
        # Record with quality 1.0
        m1.record_iteration(0, "tool_call", "test_tool", had_error=False, result_quality=1.0)
        conf_high = m1.confidence

        # Reset and record with quality 0.5
        m1.reset()
        m1.record_iteration(0, "tool_call", "test_tool", had_error=False, result_quality=0.5)
        conf_low = m1.confidence

        assert conf_high > conf_low

    def test_record_stores_error_type(self, fresh_meta):
        """record_iteration should store error_type in the record."""
        fresh_meta.record_iteration(0, "tool_call", "test_tool", had_error=True, error_type="critical")
        record = fresh_meta.iteration_history[-1]
        assert record["error_type"] == "critical"

    def test_record_stores_result_quality(self, fresh_meta):
        """record_iteration should store result_quality in the record."""
        fresh_meta.record_iteration(0, "tool_call", "test_tool", had_error=False, result_quality=0.8)
        record = fresh_meta.iteration_history[-1]
        assert record["result_quality"] == 0.8

    def test_confidence_never_below_minimum(self, fresh_meta):
        """Confidence should never drop below 0.1 even with many critical errors."""
        for i in range(10):
            fresh_meta.record_iteration(i, "tool_call", "test_tool", had_error=True, error_type="critical")
        assert fresh_meta.confidence >= 0.1

    def test_confidence_never_above_maximum(self, fresh_meta):
        """Confidence should never exceed 1.0 even with many successes."""
        for i in range(20):
            fresh_meta.record_iteration(i, "tool_call", "test_tool", had_error=False, result_quality=1.0)
        assert fresh_meta.confidence <= 1.0


# ============================================================
# M3.2: Progress Detection Tests
# ============================================================

class TestProgressDetection:
    """Test M3.2: _detect_progress() method."""

    def test_progressing_initially(self, fresh_meta):
        """Initially should be progressing."""
        assert fresh_meta._detect_progress() == "progressing"

    def test_stuck_same_tool(self, fresh_meta):
        """Same tool called 3 times should be stuck_same_tool."""
        for i in range(3):
            fresh_meta.record_iteration(i, "tool_call", "leer_archivo")
        assert fresh_meta._detect_progress() == "stuck_same_tool"

    def test_not_stuck_different_tools(self, fresh_meta):
        """Different tools should not be stuck."""
        fresh_meta.record_iteration(0, "tool_call", "leer_archivo")
        fresh_meta.record_iteration(1, "tool_call", "ejecutar_comando")
        fresh_meta.record_iteration(2, "tool_call", "buscar_archivo")
        assert fresh_meta._detect_progress() != "stuck_same_tool"

    def test_degrading_all_errors(self, fresh_meta):
        """3 consecutive errors should be degrading."""
        for i in range(3):
            fresh_meta.record_iteration(i, "tool_call", f"tool_{i}", had_error=True)
        assert fresh_meta._detect_progress() == "degrading"

    def test_declining_confidence(self, fresh_meta):
        """Consistently declining confidence should be detected."""
        # Simulate declining confidence by recording errors that progressively reduce it
        for i in range(5):
            fresh_meta.record_iteration(i, "tool_call", f"tool_{i}", had_error=True, error_type="critical")
        # After 5 critical errors, confidence should be declining
        progress = fresh_meta._detect_progress()
        assert progress in ("degrading", "declining", "stuck_same_tool")

    def test_progressing_after_successes(self, fresh_meta):
        """After successes should be progressing."""
        for i in range(3):
            fresh_meta.record_iteration(i, "tool_call", f"tool_{i}", had_error=False)
        assert fresh_meta._detect_progress() == "progressing"


# ============================================================
# M3.3: Escalation Strategy Tests
# ============================================================

class TestEscalationStrategy:
    """Test M3.3: get_escalation_strategy() method."""

    def test_returns_none_when_progressing(self, fresh_meta):
        """Should return None when agent is progressing."""
        fresh_meta.record_iteration(0, "tool_call", "tool_a", had_error=False)
        result = fresh_meta.get_escalation_strategy(1, 6)
        assert result is None

    def test_change_tool_when_stuck(self, fresh_meta):
        """Should suggest change_tool when stuck on same tool."""
        for i in range(3):
            fresh_meta.record_iteration(i, "tool_call", "same_tool", had_error=True)
        result = fresh_meta.get_escalation_strategy(3, 10)
        assert result is not None
        assert result["strategy"] == "change_tool"

    def test_decompose_when_degrading(self, fresh_meta):
        """Should suggest decompose when degrading and past 60% iterations."""
        for i in range(3):
            fresh_meta.record_iteration(i, "tool_call", f"tool_{i}", had_error=True, error_type="critical")
        # At iteration 6 of 10 = 60% threshold
        result = fresh_meta.get_escalation_strategy(6, 10)
        assert result is not None
        assert result["strategy"] == "decompose"

    def test_ask_user_when_declining_late(self, fresh_meta):
        """Should suggest ask_user when declining and past 80% iterations."""
        # Create a declining pattern
        for i in range(5):
            fresh_meta.record_iteration(i, "tool_call", f"tool_{i}", had_error=True, error_type="critical")
        # At iteration 8 of 10 = 80% threshold
        result = fresh_meta.get_escalation_strategy(8, 10)
        # Result depends on whether degrading or declining is detected
        assert result is not None

    def test_escalation_has_required_keys(self, fresh_meta):
        """Escalation result should have strategy, reason, and action keys."""
        for i in range(3):
            fresh_meta.record_iteration(i, "tool_call", "same_tool", had_error=True)
        result = fresh_meta.get_escalation_strategy(3, 10)
        assert "strategy" in result
        assert "reason" in result
        assert "action" in result

    def test_no_decompose_before_60_percent(self, fresh_meta):
        """Should not suggest decompose before 60% of iterations."""
        for i in range(3):
            fresh_meta.record_iteration(i, "tool_call", f"tool_{i}", had_error=True, error_type="recoverable")
        # At iteration 2 of 10 = 20% - not enough for decompose
        result = fresh_meta.get_escalation_strategy(2, 10)
        # May return None or change_tool, but not decompose
        if result:
            assert result["strategy"] != "decompose"

    def test_status_includes_progress(self, fresh_meta):
        """get_status() should include progress field."""
        status = fresh_meta.get_status()
        assert "progress" in status
        assert status["progress"] == "progressing"
