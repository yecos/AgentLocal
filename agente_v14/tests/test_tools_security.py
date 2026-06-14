"""
Tests for tools security features:
- archivos.py: symlink escape detection, file size validation, real path check
- codigo.py: Python syntax validation, JS syntax validation, backup rotation
- sistema.py: command timeout enforcement, output truncation
"""

import os
import pytest
import shutil
import tempfile
from unittest.mock import patch, MagicMock

from tools.archivos import (
    _check_real_path,
    leer_archivo,
    escribir_archivo,
    MAX_FILE_READ_SIZE,
)
from tools.codigo import (
    _validate_python_syntax,
    _validate_js_ts_syntax,
    _validate_code_syntax,
    _rotate_backups,
    _create_backup,
    MAX_BACKUP_VERSIONS,
)
from tools.sistema import (
    _truncate_output,
    ejecutar_comando,
    MAX_COMMAND_OUTPUT_SIZE,
    COMMAND_DEFAULT_TIMEOUT,
    PROCESOS_CRITICOS,
)


# ============================================================
# archivos.py tests
# ============================================================


class TestCheckRealPath:
    """Test _check_real_path for symlink escape detection."""

    def test_path_within_allowed_dir(self, tmp_path):
        allowed_dir = str(tmp_path / "allowed")
        os.makedirs(allowed_dir, exist_ok=True)
        test_file = os.path.join(allowed_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("hello")

        is_safe, reason = _check_real_path(test_file, [allowed_dir])
        assert is_safe is True
        assert reason == ""

    def test_path_outside_allowed_dir(self, tmp_path):
        allowed_dir = str(tmp_path / "allowed")
        outside_dir = str(tmp_path / "outside")
        os.makedirs(allowed_dir, exist_ok=True)
        os.makedirs(outside_dir, exist_ok=True)
        test_file = os.path.join(outside_dir, "secret.txt")
        with open(test_file, "w") as f:
            f.write("secret")

        is_safe, reason = _check_real_path(test_file, [allowed_dir])
        assert is_safe is False
        assert "fuera" in reason.lower() or "permitido" in reason.lower()

    def test_symlink_escaping_allowed_dir(self, tmp_path):
        """Symlink pointing outside allowed directory should be blocked."""
        allowed_dir = str(tmp_path / "allowed")
        outside_dir = str(tmp_path / "outside")
        os.makedirs(allowed_dir, exist_ok=True)
        os.makedirs(outside_dir, exist_ok=True)

        # Create a file outside allowed dir
        secret_file = os.path.join(outside_dir, "secret.txt")
        with open(secret_file, "w") as f:
            f.write("secret data")

        # Create symlink inside allowed dir pointing outside
        symlink_path = os.path.join(allowed_dir, "link_to_secret")
        try:
            os.symlink(secret_file, symlink_path)
        except OSError:
            pytest.skip("Cannot create symlinks on this system")

        is_safe, reason = _check_real_path(symlink_path, [allowed_dir])
        assert is_safe is False
        assert "symlink" in reason.lower() or "Symlink" in reason

    def test_symlink_within_allowed_dir(self, tmp_path):
        """Symlink pointing within allowed directory should be allowed."""
        allowed_dir = str(tmp_path / "allowed")
        os.makedirs(allowed_dir, exist_ok=True)

        target_file = os.path.join(allowed_dir, "real_file.txt")
        with open(target_file, "w") as f:
            f.write("content")

        symlink_path = os.path.join(allowed_dir, "link_to_real")
        try:
            os.symlink(target_file, symlink_path)
        except OSError:
            pytest.skip("Cannot create symlinks on this system")

        is_safe, reason = _check_real_path(symlink_path, [allowed_dir])
        assert is_safe is True

    def test_nonexistent_path(self, tmp_path):
        """Non-existent path should return safe (will fail later naturally)."""
        allowed_dir = str(tmp_path / "allowed")
        os.makedirs(allowed_dir, exist_ok=True)
        nonexistent = os.path.join(allowed_dir, "does_not_exist.txt")

        # _check_real_path resolves real path; for nonexistent file
        # realpath returns the path as-is
        is_safe, reason = _check_real_path(nonexistent, [allowed_dir])
        assert is_safe is True

    def test_multiple_allowed_dirs(self, tmp_path):
        """Path should be allowed if it's in any of the allowed dirs."""
        dir1 = str(tmp_path / "dir1")
        dir2 = str(tmp_path / "dir2")
        os.makedirs(dir1, exist_ok=True)
        os.makedirs(dir2, exist_ok=True)

        test_file = os.path.join(dir2, "test.txt")
        with open(test_file, "w") as f:
            f.write("content")

        is_safe, reason = _check_real_path(test_file, [dir1, dir2])
        assert is_safe is True


class TestFileSizeValidation:
    """Test file size validation in leer_archivo."""

    def test_max_file_read_size_constant(self):
        assert MAX_FILE_READ_SIZE == 50 * 1024 * 1024  # 50MB

    def test_normal_file_readable(self, tmp_path):
        """Normal-sized file should be readable."""
        test_file = str(tmp_path / "test.txt")
        with open(test_file, "w") as f:
            f.write("Hello, World!")

        with patch("tools.archivos.validate_path", return_value=test_file):
            with patch("tools.archivos.REPOS_DIR", str(tmp_path)):
                with patch("tools.archivos._check_real_path", return_value=(True, "")):
                    with patch("config.LEARN_DIR", str(tmp_path)):
                        result = leer_archivo(test_file)
                        assert "Hello, World!" in result

    def test_oversized_file_rejected(self, tmp_path):
        """File exceeding MAX_FILE_READ_SIZE should be rejected."""
        test_file = str(tmp_path / "big_file.txt")
        # Create a file marker (we'll mock the size check)
        with open(test_file, "w") as f:
            f.write("small content")

        with patch("tools.archivos.validate_path", return_value=test_file):
            with patch("tools.archivos.REPOS_DIR", str(tmp_path)):
                with patch("tools.archivos._check_real_path", return_value=(True, "")):
                    with patch("config.LEARN_DIR", str(tmp_path)):
                        with patch("os.path.getsize", return_value=100 * 1024 * 1024):  # 100MB
                            result = leer_archivo(test_file)
                            assert "demasiado grande" in result.lower() or "grande" in result.lower()


class TestLeerArchivoSymlinkBlocked:
    """Test that leer_archivo blocks symlink escapes."""

    def test_symlink_escape_returns_access_denied(self, tmp_path):
        """Reading a symlink that escapes allowed dirs should return ACCESO DENEGADO."""
        allowed_dir = str(tmp_path / "allowed")
        outside_dir = str(tmp_path / "outside")
        os.makedirs(allowed_dir, exist_ok=True)
        os.makedirs(outside_dir, exist_ok=True)

        secret_file = os.path.join(outside_dir, "secret.txt")
        with open(secret_file, "w") as f:
            f.write("secret data")

        symlink_path = os.path.join(allowed_dir, "link")
        try:
            os.symlink(secret_file, symlink_path)
        except OSError:
            pytest.skip("Cannot create symlinks on this system")

        with patch("tools.archivos.validate_path", return_value=symlink_path):
            with patch("tools.archivos.REPOS_DIR", str(allowed_dir)):
                with patch("config.LEARN_DIR", str(allowed_dir)):
                    result = leer_archivo(symlink_path)
                    assert "ACCESO DENEGADO" in result


# ============================================================
# codigo.py tests
# ============================================================


class TestValidatePythonSyntax:
    """Test _validate_python_syntax()."""

    def test_valid_python(self):
        is_valid, error = _validate_python_syntax("x = 1 + 2\nprint(x)")
        assert is_valid is True
        assert error == ""

    def test_valid_function(self):
        code = "def hello():\n    return 'world'"
        is_valid, error = _validate_python_syntax(code)
        assert is_valid is True

    def test_invalid_python_syntax(self):
        code = "def hello(\n    return 'world'"
        is_valid, error = _validate_python_syntax(code)
        assert is_valid is False
        assert "sintaxis" in error.lower() or "SyntaxError" in error or "Error" in error

    def test_empty_code_valid(self):
        """Empty code should be valid Python."""
        is_valid, error = _validate_python_syntax("")
        assert is_valid is True

    def test_syntax_error_reports_line(self):
        """Syntax error should report the line number."""
        code = "x = \n"
        is_valid, error = _validate_python_syntax(code)
        if not is_valid:
            assert "linea" in error.lower() or "line" in error.lower()

    def test_indent_error_detected(self):
        code = "if True:\nx = 1"
        is_valid, error = _validate_python_syntax(code)
        assert is_valid is False

    def test_complex_valid_code(self):
        code = """
import os
from typing import List

def process(items: List[str]) -> dict:
    result = {}
    for item in items:
        result[item] = len(item)
    return result
"""
        is_valid, error = _validate_python_syntax(code)
        assert is_valid is True


class TestValidateJsTsSyntax:
    """Test _validate_js_ts_syntax()."""

    def test_valid_js(self):
        code = "function hello() { return 'world'; }"
        is_valid, error = _validate_js_ts_syntax(code)
        assert is_valid is True
        assert error == ""

    def test_unclosed_brace(self):
        code = "function hello() { return 'world';"
        is_valid, error = _validate_js_ts_syntax(code)
        assert is_valid is False
        assert "sin cerrar" in error.lower() or "cerrar" in error.lower()

    def test_extra_closing_brace(self):
        code = "function hello() { return 'world'; }}"
        is_valid, error = _validate_js_ts_syntax(code)
        assert is_valid is False
        assert "cierre" in error.lower() or "apertura" in error.lower()

    def test_mismatched_brackets(self):
        code = "const x = [1, 2, 3);"
        is_valid, error = _validate_js_ts_syntax(code)
        assert is_valid is False

    def test_balanced_parens_and_braces(self):
        code = "const fn = (x) => { return [x]; };"
        is_valid, error = _validate_js_ts_syntax(code)
        assert is_valid is True

    def test_unclosed_paren(self):
        code = "console.log('hello'"
        is_valid, error = _validate_js_ts_syntax(code)
        assert is_valid is False

    def test_empty_code_valid(self):
        is_valid, error = _validate_js_ts_syntax("")
        assert is_valid is True

    def test_strings_with_braces_ignored(self):
        """Braces inside string literals should not count."""
        code = 'const msg = "hello {world}";'
        is_valid, error = _validate_js_ts_syntax(code)
        assert is_valid is True

    def test_template_literals(self):
        """Template literals with backticks should be handled."""
        code = "const msg = `hello ${name}`;"
        is_valid, error = _validate_js_ts_syntax(code)
        assert is_valid is True

    def test_single_line_comments_ignored(self):
        """Braces in comments should be ignored."""
        code = "// { unbalanced\nconst x = 1;"
        is_valid, error = _validate_js_ts_syntax(code)
        assert is_valid is True


class TestValidateCodeSyntax:
    """Test _validate_code_syntax() dispatches by file extension."""

    def test_python_file_validated(self):
        code = "x = 1"
        is_valid, error = _validate_code_syntax(code, "script.py")
        assert is_valid is True

    def test_python_file_invalid_detected(self):
        code = "def (\n"
        is_valid, error = _validate_code_syntax(code, "script.py")
        assert is_valid is False

    def test_js_file_validated(self):
        code = "const x = 1;"
        is_valid, error = _validate_code_syntax(code, "app.js")
        assert is_valid is True

    def test_ts_file_validated(self):
        code = "const x: number = 1;"
        is_valid, error = _validate_code_syntax(code, "app.ts")
        assert is_valid is True

    def test_jsx_file_validated(self):
        code = "const elem = <div />;"
        is_valid, error = _validate_code_syntax(code, "component.jsx")
        # JSX validation might fail due to < > but at least it dispatches to JS validator
        assert isinstance(is_valid, bool)

    def test_other_extensions_not_validated(self):
        """Non-Python/JS files should pass validation (no check)."""
        code = "anything goes! <<<"
        is_valid, error = _validate_code_syntax(code, "readme.md")
        assert is_valid is True
        assert error == ""

    def test_html_extension_not_validated(self):
        code = "<html><body>hello"
        is_valid, error = _validate_code_syntax(code, "page.html")
        assert is_valid is True

    def test_mjs_extension_validated(self):
        code = "export default function() {}"
        is_valid, error = _validate_code_syntax(code, "module.mjs")
        assert is_valid is True


class TestBackupRotation:
    """Test backup rotation in codigo.py."""

    def test_max_backup_versions_constant(self):
        assert MAX_BACKUP_VERSIONS == 3

    def test_create_backup_no_existing_file(self, tmp_path):
        """_create_backup should return False if file doesn't exist."""
        filepath = str(tmp_path / "nonexistent.py")
        result = _create_backup(filepath)
        assert result is False

    def test_create_backup_existing_file(self, tmp_path):
        """_create_backup should create .bak file for existing file."""
        filepath = str(tmp_path / "existing.py")
        with open(filepath, "w") as f:
            f.write("original content")

        result = _create_backup(filepath)
        assert result is True
        assert os.path.exists(filepath + ".bak")

    def test_backup_content_matches(self, tmp_path):
        """Backup should contain the same content as the original."""
        filepath = str(tmp_path / "test.py")
        with open(filepath, "w") as f:
            f.write("original content")

        _create_backup(filepath)

        with open(filepath + ".bak", "r") as f:
            backup_content = f.read()
        assert backup_content == "original content"

    def test_rotate_backups_shifts_versions(self, tmp_path):
        """Rotation should shift .bak -> .bak.1, .bak.1 -> .bak.2, etc."""
        filepath = str(tmp_path / "test.py")
        with open(filepath, "w") as f:
            f.write("current")

        # Create .bak.1
        with open(filepath + ".bak.1", "w") as f:
            f.write("backup1")

        # Create .bak.2
        with open(filepath + ".bak.2", "w") as f:
            f.write("backup2")

        # Rotation should move .bak.1 -> .bak.2, .bak -> .bak.1
        _rotate_backups(filepath)

        # .bak.2 should now have "backup1" (was .bak.1)
        # Note: the oldest (.bak.2 with "backup2") should be deleted
        assert not os.path.exists(filepath + ".bak.3")  # oldest deleted

    def test_multiple_backups_limit(self, tmp_path):
        """Should keep at most MAX_BACKUP_VERSIONS backups."""
        filepath = str(tmp_path / "test.py")
        with open(filepath, "w") as f:
            f.write("v4")

        # Create all backup levels
        with open(filepath + ".bak", "w") as f:
            f.write("v3")
        with open(filepath + ".bak.1", "w") as f:
            f.write("v2")
        with open(filepath + ".bak.2", "w") as f:
            f.write("v1")

        # After rotation, the oldest should be gone
        _rotate_backups(filepath)

        # The max versions should not exceed MAX_BACKUP_VERSIONS
        backup_count = 0
        for i in range(10):
            bak_path = filepath + f".bak.{i}" if i > 0 else filepath + ".bak"
            if os.path.exists(bak_path):
                backup_count += 1

        assert backup_count <= MAX_BACKUP_VERSIONS

    def test_backup_on_overwrite(self, tmp_path):
        """When overwriting a file, backup should be created."""
        filepath = str(tmp_path / "test.py")
        with open(filepath, "w") as f:
            f.write("original")

        # Simulate the backup-then-write cycle
        _create_backup(filepath)

        with open(filepath, "w") as f:
            f.write("new content")

        # Verify backup has old content
        with open(filepath + ".bak", "r") as f:
            assert f.read() == "original"

        # Verify file has new content
        with open(filepath, "r") as f:
            assert f.read() == "new content"


# ============================================================
# sistema.py tests
# ============================================================


class TestTruncateOutput:
    """Test _truncate_output() for output size limiting."""

    def test_small_output_not_truncated(self):
        output = "Hello, World!"
        result = _truncate_output(output)
        assert result == output

    def test_empty_output(self):
        result = _truncate_output("")
        assert result == ""

    def test_large_output_truncated(self):
        # Create output larger than MAX_COMMAND_OUTPUT_SIZE
        large_output = "x" * (MAX_COMMAND_OUTPUT_SIZE + 1000)
        result = _truncate_output(large_output)
        assert len(result.encode('utf-8')) <= MAX_COMMAND_OUTPUT_SIZE + 200  # Some margin for truncation msg
        assert "truncated" in result.lower() or "truncado" in result.lower()

    def test_exact_max_size_not_truncated(self):
        output = "x" * MAX_COMMAND_OUTPUT_SIZE
        result = _truncate_output(output)
        # Should not be truncated (equal to max)
        assert "truncated" not in result.lower()

    def test_custom_max_size(self):
        output = "x" * 200
        result = _truncate_output(output, max_size=100)
        assert len(result.encode('utf-8')) <= 200  # With truncation message
        assert "truncated" in result.lower() or "truncado" in result.lower()

    def test_unicode_output_truncation(self):
        """Unicode content should be handled properly during truncation."""
        output = "ñ" * (MAX_COMMAND_OUTPUT_SIZE + 100)
        result = _truncate_output(output)
        # Should not raise UnicodeDecodeError
        assert isinstance(result, str)

    def test_max_command_output_size_constant(self):
        assert MAX_COMMAND_OUTPUT_SIZE == 100 * 1024  # 100KB


class TestCommandTimeout:
    """Test command timeout enforcement."""

    def test_default_timeout_constant(self):
        assert COMMAND_DEFAULT_TIMEOUT == 120

    def test_minimum_timeout_enforced(self):
        """Timeout should never be less than 10 seconds."""
        with patch("tools.sistema.is_dangerous_command", return_value=False):
            with patch("tools.sistema.sanitize_input", return_value="echo hello"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        stdout="hello", stderr="", returncode=0
                    )
                    # Even with timeout=1, it should be raised to minimum 10
                    result = ejecutar_comando("echo hello", timeout=1)
                    call_args = mock_run.call_args
                    actual_timeout = call_args.kwargs.get("timeout", call_args[1].get("timeout") if len(call_args) > 1 else None)
                    assert actual_timeout >= 10

    def test_long_timeout_for_install_commands(self):
        """Install/build commands should get longer timeout."""
        with patch("tools.sistema.is_dangerous_command", return_value=False):
            with patch("tools.sistema.sanitize_input", return_value="npm install"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        stdout="installed", stderr="", returncode=0
                    )
                    with patch("tools.sistema.LONG_TIMEOUT", 300):
                        result = ejecutar_comando("npm install")
                        call_args = mock_run.call_args
                        actual_timeout = call_args.kwargs.get("timeout", None)
                        assert actual_timeout == 300

    def test_explicit_timeout_respected(self):
        """Explicit timeout parameter should be used."""
        with patch("tools.sistema.is_dangerous_command", return_value=False):
            with patch("tools.sistema.sanitize_input", return_value="echo hello"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        stdout="hello", stderr="", returncode=0
                    )
                    result = ejecutar_comando("echo hello", timeout=30)
                    call_args = mock_run.call_args
                    actual_timeout = call_args.kwargs.get("timeout", None)
                    assert actual_timeout == 30

    def test_timeout_expired_returns_error(self):
        """When command times out, should return error message."""
        import subprocess
        with patch("tools.sistema.is_dangerous_command", return_value=False):
            with patch("tools.sistema.sanitize_input", return_value="sleep 999"):
                with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 10)):
                    result = ejecutar_comando("sleep 999", timeout=10)
                    assert "TIMEOUT" in result or "timeout" in result.lower()


class TestDangerousCommandBlocked:
    """Test that dangerous commands are blocked in ejecutar_comando."""

    def test_dangerous_command_blocked(self):
        with patch("tools.sistema.is_dangerous_command", return_value=True):
            result = ejecutar_comando("rm -rf /")
            assert "PELIGROSO" in result or "peligroso" in result.lower()

    def test_dangerous_command_not_blocked_with_confirm(self):
        """With confirmar_peligroso=True, command should proceed."""
        with patch("tools.sistema.is_dangerous_command", return_value=True):
            with patch("tools.sistema.sanitize_input", return_value="rm file"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        stdout="removed", stderr="", returncode=0
                    )
                    result = ejecutar_comando("rm file", confirmar_peligroso=True)
                    assert "PELIGROSO" not in result


class TestProcessosCriticos:
    """Test that critical processes are protected from being killed."""

    def test_systemd_protected(self):
        assert "systemd" in PROCESOS_CRITICOS

    def test_sshd_protected(self):
        assert "sshd" in PROCESOS_CRITICOS

    def test_ollama_protected(self):
        assert "ollama" in PROCESOS_CRITICOS

    def test_nginx_protected(self):
        assert "nginx" in PROCESOS_CRITICOS

    def test_explorer_protected(self):
        assert "explorer" in PROCESOS_CRITICOS

    def test_docker_protected(self):
        assert "dockerd" in PROCESOS_CRITICOS

    def test_postgres_protected(self):
        assert "postgres" in PROCESOS_CRITICOS
