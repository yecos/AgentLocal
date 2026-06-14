"""
=============================================================
AGENTE v14 - Environment Manager
=============================================================
Manages development environments (Python virtualenvs, conda
environments, Node.js versions) so the agent can properly
isolate project dependencies.

Capabilities:
  - Detect available environment managers (python, conda, nvm, etc.)
  - Create Python virtual environments (venv / virtualenv)
  - Install Python packages (pip / poetry)
  - Install Node.js packages (npm / yarn / pnpm / bun)
  - Get / set Node.js version (nvm / fnm)
  - Detect project environment (venv, requirements, package.json, etc.)
  - Run commands inside the project's appropriate environment

v1: Initial implementation.
=============================================================
"""

import os
import sys
import time
import shlex
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional, List

from config import REPOS_DIR, logger
from utils.security import validate_path, is_dangerous_command


# ============================================================
# CONSTANTS
# ============================================================

_CACHE_TTL = 300  # 5 minutes in seconds

# Managers to detect: (command_name, version_flag)
_MANAGER_PROBES = {
    "python3":   ("python3", "--version"),
    "pip":       ("pip", "--version"),
    "venv":      ("python3", "-m", "venv", "--help"),  # no --version, use --help
    "virtualenv":("virtualenv", "--version"),
    "conda":     ("conda", "--version"),
    "poetry":    ("poetry", "--version"),
    "nvm":       ("nvm", "--version"),       # sourced in shell, may not work directly
    "fnm":       ("fnm", "--version"),
    "node":      ("node", "--version"),
    "npm":       ("npm", "--version"),
    "yarn":      ("yarn", "--version"),
    "pnpm":      ("pnpm", "--version"),
    "bun":       ("bun", "--version"),
    "docker":    ("docker", "--version"),
}

# Lock files that indicate which Node package manager is in use
_NODE_LOCK_FILES = {
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock":      "yarn",
    "bun.lockb":      "bun",
    "package-lock.json": "npm",
}

# Python environment indicator files/dirs
_PYTHON_ENV_INDICATORS = [
    ".venv", "venv", ".virtualenv",
    "requirements.txt", "Pipfile", "pyproject.toml",
    "setup.py", "setup.cfg",
]

# Node environment indicator files/dirs
_NODE_ENV_INDICATORS = [
    "package.json", "node_modules", ".nvmrc", ".node-version",
]


# ============================================================
# HELPER: run command with timeout
# ============================================================

def _run_cmd(
    cmd: List[str],
    cwd: str = None,
    timeout: int = 120,
    env: dict = None,
) -> dict:
    """Execute a subprocess command and return a structured result.

    Args:
        cmd: Command and arguments as a list.
        cwd: Working directory.
        timeout: Timeout in seconds.
        env: Optional environment variables override.

    Returns:
        Dict with success, stdout, stderr, exit_code.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "exit_code": -1,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command not found: {cmd[0] if isinstance(cmd, list) else cmd.split()[0]}",
            "exit_code": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
        }


# ============================================================
# EnvironmentManager
# ============================================================

class EnvironmentManager:
    """Manages development environments for the autonomous agent.

    Handles Python virtual environments, Node.js version managers,
    and package installation across pip, poetry, npm, yarn, pnpm, bun.
    Thread-safe via internal lock. Caches manager availability for 5 min.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._managers_cache: dict = {}
        self._managers_cache_ts: float = 0.0

    # ----------------------------------------------------------
    # 1. detect_available_managers
    # ----------------------------------------------------------

    def detect_available_managers(self) -> dict:
        """Check which environment managers are installed and return
        a dict mapping manager name -> version string.

        Results are cached for 5 minutes (CACHE_TTL).

        Returns:
            Dict like {"python3": "3.11.4", "pip": "23.2", ...}
        """
        now = time.time()
        with self._lock:
            if self._managers_cache and (now - self._managers_cache_ts) < _CACHE_TTL:
                return dict(self._managers_cache)

        available = {}
        for name, probe in _MANAGER_PROBES.items():
            try:
                result = _run_cmd(list(probe), timeout=10)
                if result["success"]:
                    version = result["stdout"].strip()
                    # Clean up common prefixes
                    for prefix in ("Python ", "pip ", "virtualenv ", "conda ", "Poetry ",
                                   "nvm ", "fnm ", "npm ", "yarn ", "pnpm ", "bun ",
                                   "Docker ", "v"):
                        if version.startswith(prefix):
                            version = version[len(prefix):]
                    available[name] = version.split("\n")[0].strip()
                else:
                    # nvm is a shell function, try sourcing it
                    if name == "nvm":
                        nvm_check = self._check_nvm()
                        if nvm_check:
                            available["nvm"] = nvm_check
            except Exception as e:
                logger.debug(f"Error detecting {name}: {e}")

        with self._lock:
            self._managers_cache = dict(available)
            self._managers_cache_ts = time.time()

        logger.info(f"Detected environment managers: {list(available.keys())}")
        return available

    def _check_nvm(self) -> Optional[str]:
        """nvm is typically a shell function; try to detect it via
        the NVM_DIR environment variable or the nvm.sh script."""
        # Check NVM_DIR
        nvm_dir = os.environ.get("NVM_DIR")
        if nvm_dir and os.path.isdir(nvm_dir):
            nvm_sh = os.path.join(nvm_dir, "nvm.sh")
            if os.path.isfile(nvm_sh):
                try:
                    result = _run_cmd(
                        ["bash", "-c", f"source {nvm_sh} && nvm --version"],
                        timeout=10,
                    )
                    if result["success"]:
                        return result["stdout"].strip()
                except Exception:
                    pass
        # Check common install locations
        for candidate in (
            os.path.expanduser("~/.nvm/nvm.sh"),
            "/usr/local/nvm/nvm.sh",
        ):
            if os.path.isfile(candidate):
                try:
                    result = _run_cmd(
                        ["bash", "-c", f"source {candidate} && nvm --version"],
                        timeout=10,
                    )
                    if result["success"]:
                        return result["stdout"].strip()
                except Exception:
                    pass
        return None

    # ----------------------------------------------------------
    # 2. create_venv
    # ----------------------------------------------------------

    def create_venv(
        self,
        project_path: str,
        name: str = ".venv",
        python_version: Optional[str] = None,
    ) -> dict:
        """Create a Python virtual environment in the project directory.

        Uses ``python3 -m venv`` by default; falls back to ``virtualenv``
        if the venv module is not available.

        Args:
            project_path: Path to the project directory.
            name: Name of the venv directory (default: ``.venv``).
            python_version: Optional Python version to use (e.g. ``"3.11"``).
                            If provided and ``virtualenv`` is available, it will
                            be used with ``-p pythonX.Y``.

        Returns:
            Dict with success, venv_path, python_path, pip_path on success
            or success=False and error on failure.
        """
        validated = validate_path(project_path)
        if not validated or validated.startswith("ACCESO DENEGADO"):
            return {"success": False, "error": f"Path not allowed: {project_path}"}

        project_dir = Path(validated)
        venv_dir = project_dir / name

        # If venv already exists, return its info
        if venv_dir.is_dir():
            python_path, pip_path = self._venv_bin_paths(venv_dir)
            if python_path and os.path.isfile(python_path):
                logger.info(f"Virtual environment already exists at {venv_dir}")
                return {
                    "success": True,
                    "venv_path": str(venv_dir),
                    "python_path": python_path,
                    "pip_path": pip_path,
                    "message": "Virtual environment already exists",
                }

        # Determine which tool to use
        managers = self.detect_available_managers()
        use_virtualenv = False
        python_cmd = "python3"

        if python_version:
            # Try to find the specific python version binary
            versioned_cmd = f"python{python_version}"
            if shutil.which(versioned_cmd):
                python_cmd = versioned_cmd
            elif "virtualenv" in managers:
                use_virtualenv = True
                python_cmd = f"python{python_version}"
            else:
                return {
                    "success": False,
                    "error": f"Python {python_version} not found and virtualenv not available",
                }

        # Build the command
        if use_virtualenv or ("venv" not in managers and "virtualenv" in managers):
            # Use virtualenv
            cmd = ["virtualenv", str(venv_dir)]
            if python_version:
                cmd.extend(["-p", python_cmd])
            logger.info(f"Creating venv with virtualenv: {' '.join(cmd)}")
        else:
            # Use python3 -m venv
            cmd = [python_cmd, "-m", "venv", str(venv_dir)]
            logger.info(f"Creating venv with {python_cmd} -m venv: {str(venv_dir)}")

        result = _run_cmd(cmd, cwd=str(project_dir), timeout=120)

        if not result["success"]:
            error_msg = result["stderr"] or result["stdout"] or "Unknown error"
            logger.error(f"Failed to create venv: {error_msg}")

            # Try fallback to virtualenv if venv failed
            if not use_virtualenv and "virtualenv" in managers:
                logger.info("Falling back to virtualenv...")
                fallback_cmd = ["virtualenv", str(venv_dir)]
                if python_version:
                    fallback_cmd.extend(["-p", f"python{python_version}"])
                result = _run_cmd(fallback_cmd, cwd=str(project_dir), timeout=120)
                if not result["success"]:
                    return {"success": False, "error": result["stderr"] or error_msg}
            else:
                return {"success": False, "error": error_msg}

        # Locate binaries
        python_path, pip_path = self._venv_bin_paths(venv_dir)
        if not pip_path or not os.path.isfile(pip_path):
            return {
                "success": False,
                "error": "Virtual environment created but pip not found inside it",
            }

        # Upgrade pip inside the new venv
        try:
            _run_cmd([python_path, "-m", "pip", "install", "--upgrade", "pip"],
                     timeout=120)
        except Exception:
            logger.debug("Could not upgrade pip in new venv (non-critical)")

        logger.info(f"Virtual environment created at {venv_dir}")
        return {
            "success": True,
            "venv_path": str(venv_dir),
            "python_path": python_path,
            "pip_path": pip_path,
        }

    def _venv_bin_paths(self, venv_dir: Path) -> tuple:
        """Return (python_path, pip_path) for a venv directory,
        accounting for Windows vs POSIX layouts."""
        if sys.platform == "win32":
            bin_dir = venv_dir / "Scripts"
            python_path = str(bin_dir / "python.exe")
            pip_path = str(bin_dir / "pip.exe")
        else:
            bin_dir = venv_dir / "bin"
            python_path = str(bin_dir / "python")
            pip_path = str(bin_dir / "pip")
        return python_path, pip_path

    def _find_venv(self, project_path: str) -> Optional[str]:
        """Find a virtual environment in the project directory.
        Looks for .venv/ and venv/ subdirectories.

        Returns:
            The venv directory path if found, else None.
        """
        project_dir = Path(project_path)
        for candidate in (".venv", "venv", ".virtualenv"):
            venv_dir = project_dir / candidate
            python_path, _ = self._venv_bin_paths(venv_dir)
            if os.path.isfile(python_path):
                return str(venv_dir)
        return None

    # ----------------------------------------------------------
    # 3. install_python_packages
    # ----------------------------------------------------------

    def install_python_packages(
        self,
        packages: List[str],
        project_path: Optional[str] = None,
        venv: bool = True,
        dev: bool = False,
    ) -> dict:
        """Install Python packages using pip or poetry.

        If ``venv=True`` and a venv exists in the project, uses that pip.
        If ``pyproject.toml`` with ``[tool.poetry]`` exists, uses poetry instead.

        Args:
            packages: List of package names to install.
            project_path: Path to the project directory.
            venv: Whether to look for / use a virtual environment.
            dev: If True, add as dev dependency (poetry add --group dev,
                 or pip install into the venv without freezing).

        Returns:
            Dict with success, installed, failed lists.
        """
        if not packages:
            return {"success": False, "error": "No packages specified", "installed": [], "failed": []}

        validated_path = None
        if project_path:
            validated = validate_path(project_path)
            if not validated or validated.startswith("ACCESO DENEGADO"):
                return {"success": False, "error": f"Path not allowed: {project_path}",
                        "installed": [], "failed": list(packages)}
            validated_path = validated

        # Determine install method
        use_poetry = False
        pip_cmd = ["pip"]

        if validated_path:
            # Check for poetry project
            pyproject = Path(validated_path) / "pyproject.toml"
            if pyproject.is_file():
                try:
                    content = pyproject.read_text(encoding="utf-8", errors="ignore")
                    if "[tool.poetry]" in content:
                        use_poetry = True
                except Exception:
                    pass

            # Find venv pip if requested
            if venv and not use_poetry:
                venv_dir = self._find_venv(validated_path)
                if venv_dir:
                    _, pip_path = self._venv_bin_paths(Path(venv_dir))
                    if os.path.isfile(pip_path):
                        pip_cmd = [pip_path]

        installed = []
        failed = []

        if use_poetry:
            # Use poetry add
            for pkg in packages:
                cmd = ["poetry", "add"]
                if dev:
                    cmd.append("--group")
                    cmd.append("dev")
                cmd.append(pkg)
                result = _run_cmd(cmd, cwd=validated_path, timeout=300)
                if result["success"]:
                    installed.append(pkg)
                else:
                    failed.append({"package": pkg, "error": result["stderr"] or result["stdout"]})
                    logger.warning(f"poetry add {pkg} failed: {result['stderr']}")
        else:
            # Use pip install
            cmd = pip_cmd + ["install"]
            cmd.extend(packages)
            result = _run_cmd(cmd, cwd=validated_path, timeout=300)

            if result["success"]:
                installed = list(packages)
            else:
                # Try installing packages one by one to identify failures
                for pkg in packages:
                    single_cmd = pip_cmd + ["install", pkg]
                    single_result = _run_cmd(single_cmd, cwd=validated_path, timeout=300)
                    if single_result["success"]:
                        installed.append(pkg)
                    else:
                        failed.append({"package": pkg, "error": single_result["stderr"] or single_result["stdout"]})
                        logger.warning(f"pip install {pkg} failed: {single_result['stderr']}")

        return {
            "success": len(installed) > 0,
            "installed": installed,
            "failed": failed,
        }

    # ----------------------------------------------------------
    # 4. install_node_packages
    # ----------------------------------------------------------

    def install_node_packages(
        self,
        packages: List[str],
        project_path: Optional[str] = None,
        dev: bool = False,
        manager: Optional[str] = None,
    ) -> dict:
        """Install Node.js packages.

        Auto-detects the package manager from lock files:
        pnpm > yarn > bun > npm (based on presence of lock files).
        Falls back to npm if no lock file is found.

        Args:
            packages: List of package names to install.
            project_path: Path to the project directory.
            dev: If True, add as dev dependency (--save-dev / -D).
            manager: Force a specific manager (``"npm"``, ``"yarn"``,
                     ``"pnpm"``, ``"bun"``).

        Returns:
            Dict with success, installed list, and manager used.
        """
        if not packages:
            return {"success": False, "error": "No packages specified",
                    "installed": [], "manager": manager or "unknown"}

        validated_path = None
        if project_path:
            validated = validate_path(project_path)
            if not validated or validated.startswith("ACCESO DENEGADO"):
                return {"success": False, "error": f"Path not allowed: {project_path}",
                        "installed": [], "manager": manager or "unknown"}
            validated_path = validated

        # Determine package manager
        if manager:
            resolved_manager = manager
        else:
            resolved_manager = self._detect_node_manager(validated_path)

        # Verify the chosen manager is available
        managers = self.detect_available_managers()
        if resolved_manager not in managers:
            # Try fallbacks
            for fallback in ("npm", "yarn", "pnpm", "bun"):
                if fallback in managers:
                    resolved_manager = fallback
                    break
            else:
                return {
                    "success": False,
                    "error": f"No Node.js package manager available (tried {resolved_manager})",
                    "installed": [],
                    "manager": resolved_manager,
                }

        # Build the install command
        dev_flag = {
            "npm": "--save-dev",
            "yarn": "--dev",
            "pnpm": "--save-dev",
            "bun": "--dev",
        }.get(resolved_manager, "--save-dev")

        cmd = [resolved_manager, "install"] if resolved_manager == "bun" and not packages else [resolved_manager]
        if resolved_manager == "npm":
            cmd.append("install")
        elif resolved_manager == "yarn":
            cmd.append("add")
        elif resolved_manager == "pnpm":
            cmd.append("add")
        elif resolved_manager == "bun":
            cmd.append("add")

        if dev:
            cmd.append(dev_flag)

        cmd.extend(packages)

        logger.info(f"Installing Node packages with {resolved_manager}: {' '.join(packages)}")
        result = _run_cmd(cmd, cwd=validated_path, timeout=300)

        if result["success"]:
            return {
                "success": True,
                "installed": list(packages),
                "manager": resolved_manager,
            }
        else:
            # Try one by one
            installed = []
            failed = []
            for pkg in packages:
                single_cmd = [resolved_manager]
                if resolved_manager == "npm":
                    single_cmd.append("install")
                elif resolved_manager == "yarn":
                    single_cmd.append("add")
                elif resolved_manager == "pnpm":
                    single_cmd.append("add")
                elif resolved_manager == "bun":
                    single_cmd.append("add")
                if dev:
                    single_cmd.append(dev_flag)
                single_cmd.append(pkg)

                single_result = _run_cmd(single_cmd, cwd=validated_path, timeout=300)
                if single_result["success"]:
                    installed.append(pkg)
                else:
                    failed.append(pkg)
                    logger.warning(f"{resolved_manager} install {pkg} failed: {single_result['stderr']}")

            return {
                "success": len(installed) > 0,
                "installed": installed,
                "failed": failed,
                "manager": resolved_manager,
            }

    def _detect_node_manager(self, project_path: Optional[str]) -> str:
        """Auto-detect Node package manager from lock files.

        Priority: pnpm > yarn > bun > npm (based on lock file presence).
        """
        if project_path:
            project_dir = Path(project_path)
            for lock_file, mgr in _NODE_LOCK_FILES.items():
                if (project_dir / lock_file).is_file():
                    return mgr

        # No lock file; fall back to what's installed
        managers = self.detect_available_managers()
        for preferred in ("pnpm", "yarn", "bun", "npm"):
            if preferred in managers:
                return preferred

        return "npm"

    # ----------------------------------------------------------
    # 5. get_node_version
    # ----------------------------------------------------------

    def get_node_version(self) -> str:
        """Return the current Node.js version string.

        Returns:
            Version string (e.g. ``"v18.17.0"``) or ``"not installed"``.
        """
        result = _run_cmd(["node", "--version"], timeout=10)
        if result["success"]:
            return result["stdout"].strip()
        return "not installed"

    # ----------------------------------------------------------
    # 6. set_node_version
    # ----------------------------------------------------------

    def set_node_version(
        self,
        version: str,
        project_path: Optional[str] = None,
    ) -> dict:
        """Set the Node.js version for the current session or project.

        Uses ``nvm use`` or ``fnm use`` depending on availability.
        Creates a ``.nvmrc`` or ``.node-version`` file in project_path.

        Args:
            version: Node.js version string (e.g. ``"18"``, ``"18.17.0"``).
            project_path: Optional project directory to write version file.

        Returns:
            Dict with success, version, manager used.
        """
        managers = self.detect_available_managers()
        version_set = False
        manager_used = None

        # Try nvm first
        if "nvm" in managers:
            nvm_dir = os.environ.get("NVM_DIR") or os.path.expanduser("~/.nvm")
            nvm_sh = os.path.join(nvm_dir, "nvm.sh") if os.path.isdir(nvm_dir) else None
            if not nvm_sh or not os.path.isfile(nvm_sh):
                # Try common location
                nvm_sh = os.path.expanduser("~/.nvm/nvm.sh")

            if os.path.isfile(nvm_sh):
                result = _run_cmd(
                    ["bash", "-c", f"source {nvm_sh} && nvm install {version} && nvm use {version}"],
                    timeout=120,
                )
                if result["success"]:
                    version_set = True
                    manager_used = "nvm"
                else:
                    logger.warning(f"nvm use {version} failed: {result['stderr']}")

        # Try fnm
        if not version_set and "fnm" in managers:
            # fnm install if needed, then use
            _run_cmd(["fnm", "install", version], timeout=120)
            result = _run_cmd(["fnm", "use", version], timeout=30)
            if result["success"]:
                version_set = True
                manager_used = "fnm"
            else:
                logger.warning(f"fnm use {version} failed: {result['stderr']}")

        # Create version file in project
        version_file_created = False
        if project_path:
            validated = validate_path(project_path)
            if validated and not validated.startswith("ACCESO DENEGADO"):
                project_dir = Path(validated)
                # Write .nvmrc (nvm compatible)
                nvmrc = project_dir / ".nvmrc"
                try:
                    nvmrc.write_text(version + "\n", encoding="utf-8")
                    version_file_created = True
                except Exception as e:
                    logger.warning(f"Could not write .nvmrc: {e}")

                # Write .node-version (fnm / other managers compatible)
                node_version_file = project_dir / ".node-version"
                try:
                    node_version_file.write_text(version + "\n", encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Could not write .node-version: {e}")

        if not version_set:
            suggestion = []
            if "nvm" not in managers:
                suggestion.append("Install nvm: curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash")
            if "fnm" not in managers:
                suggestion.append("Install fnm: curl -fsSL https://fnm.vercel.app/install | bash")
            return {
                "success": False,
                "error": f"Cannot set Node.js version: no nvm or fnm available",
                "suggestion": suggestion,
                "version_file_created": version_file_created,
            }

        return {
            "success": True,
            "version": version,
            "manager": manager_used,
            "version_file_created": version_file_created,
        }

    # ----------------------------------------------------------
    # 7. detect_project_environment
    # ----------------------------------------------------------

    def detect_project_environment(self, project_path: str) -> dict:
        """Scan a project directory for environment indicators.

        Checks for Python venvs, requirements.txt, Pipfile, pyproject.toml,
        package.json, node_modules, .nvmrc, .python-version, etc.

        Args:
            project_path: Path to the project directory.

        Returns:
            Dict with ``"python"`` and ``"node"`` sub-dicts describing
            the detected environment.
        """
        validated = validate_path(project_path)
        if not validated or validated.startswith("ACCESO DENEGADO"):
            return {"success": False, "error": f"Path not allowed: {project_path}"}

        project_dir = Path(validated)
        result = {"python": {}, "node": {}}

        # ---- Python detection ----
        python_info: dict = {"venv": False, "path": None, "packages": 0}

        # Check for virtual environments
        venv_dir = self._find_venv(validated)
        if venv_dir:
            python_info["venv"] = True
            python_info["path"] = venv_dir
            # Count installed packages
            _, pip_path = self._venv_bin_paths(Path(venv_dir))
            if os.path.isfile(pip_path):
                pkg_result = _run_cmd([pip_path, "list", "--format=json"], timeout=30)
                if pkg_result["success"]:
                    try:
                        import json
                        pkg_list = json.loads(pkg_result["stdout"])
                        python_info["packages"] = len(pkg_list)
                    except (json.JSONDecodeError, ValueError):
                        # Fallback: count lines from pip list
                        lines = pkg_result["stdout"].strip().split("\n")
                        python_info["packages"] = max(0, len(lines) - 2)  # skip header

        # Check for Python project files
        python_info["requirements_txt"] = (project_dir / "requirements.txt").is_file()
        python_info["pipfile"] = (project_dir / "Pipfile").is_file()
        python_info["pyproject_toml"] = (project_dir / "pyproject.toml").is_file()
        python_info["setup_py"] = (project_dir / "setup.py").is_file()

        # Check .python-version
        python_version_file = project_dir / ".python-version"
        if python_version_file.is_file():
            try:
                python_info["python_version"] = python_version_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass

        result["python"] = python_info

        # ---- Node detection ----
        node_info: dict = {"version": self.get_node_version(), "manager": None, "packages": 0}

        # Check for package.json
        package_json = project_dir / "package.json"
        if package_json.is_file():
            node_info["has_package_json"] = True
            # Detect package manager
            node_info["manager"] = self._detect_node_manager(validated)
            # Count dependencies
            try:
                import json
                data = json.loads(package_json.read_text(encoding="utf-8"))
                deps = list(data.get("dependencies", {}).keys())
                dev_deps = list(data.get("devDependencies", {}).keys())
                node_info["packages"] = len(deps) + len(dev_deps)
                node_info["dependencies_count"] = len(deps)
                node_info["dev_dependencies_count"] = len(dev_deps)
            except (json.JSONDecodeError, ValueError):
                pass
        else:
            node_info["has_package_json"] = False

        # Check node_modules
        node_modules = project_dir / "node_modules"
        if node_modules.is_dir():
            node_info["node_modules"] = True
            try:
                # Count top-level directories in node_modules
                node_info["installed_packages"] = sum(
                    1 for _ in node_modules.iterdir() if _.is_dir() and not _.name.startswith(".")
                )
            except Exception:
                node_info["installed_packages"] = 0
        else:
            node_info["node_modules"] = False

        # Check .nvmrc / .node-version
        nvmrc = project_dir / ".nvmrc"
        if nvmrc.is_file():
            try:
                node_info["nvmrc"] = nvmrc.read_text(encoding="utf-8").strip()
            except Exception:
                pass

        node_version_file = project_dir / ".node-version"
        if node_version_file.is_file():
            try:
                node_info["node_version_file"] = node_version_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass

        result["node"] = node_info
        result["success"] = True
        return result

    # ----------------------------------------------------------
    # 8. run_in_env
    # ----------------------------------------------------------

    def run_in_env(
        self,
        command: str,
        project_path: str,
        timeout: int = 60,
    ) -> dict:
        """Run a command in the project's appropriate environment.

        If a Python venv exists in the project, it is activated before
        running the command. If a Node project with ``node_modules/.bin/``
        is detected, that directory is prepended to PATH.

        Args:
            command: The shell command to execute.
            project_path: Path to the project directory.
            timeout: Timeout in seconds (default 60).

        Returns:
            Dict with success, stdout, stderr, exit_code.
        """
        # Validate path
        validated = validate_path(project_path)
        if not validated or validated.startswith("ACCESO DENEGADO"):
            return {"success": False, "stdout": "", "stderr": f"Path not allowed: {project_path}", "exit_code": -1}

        # Check for dangerous commands
        if is_dangerous_command(command):
            return {"success": False, "stdout": "", "stderr": "Command rejected: potentially dangerous", "exit_code": -1}

        # Build environment
        env = os.environ.copy()
        project_dir = Path(validated)

        # Detect and activate Python venv
        venv_dir = self._find_venv(validated)
        if venv_dir:
            venv_path = Path(venv_dir)
            if sys.platform == "win32":
                bin_dir = str(venv_path / "Scripts")
            else:
                bin_dir = str(venv_path / "bin")

            # Prepend venv bin to PATH
            env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
            env["VIRTUAL_ENV"] = str(venv_path)
            # Remove PYTHONHOME if set (can interfere with venv)
            env.pop("PYTHONHOME", None)

            logger.info(f"Running command in Python venv: {venv_dir}")

        # Detect and add node_modules/.bin to PATH
        node_bin = project_dir / "node_modules" / ".bin"
        if node_bin.is_dir():
            env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")
            logger.info(f"Added node_modules/.bin to PATH")

        # If nvm is available, source it for Node version management
        nvm_dir = os.environ.get("NVM_DIR") or os.path.expanduser("~/.nvm")
        nvm_sh = os.path.join(nvm_dir, "nvm.sh") if os.path.isdir(nvm_dir) else None
        if not nvm_sh or not os.path.isfile(nvm_sh):
            nvm_sh_candidate = os.path.expanduser("~/.nvm/nvm.sh")
            if os.path.isfile(nvm_sh_candidate):
                nvm_sh = nvm_sh_candidate
            else:
                nvm_sh = None

        # Check for .nvmrc in project
        nvmrc = project_dir / ".nvmrc"
        if nvm_sh and nvmrc.is_file() and "node" in command.lower():
            try:
                nvm_version = nvmrc.read_text(encoding="utf-8").strip()
                # Source nvm and use the version from .nvmrc
                command = f'source {nvm_sh} && nvm use {nvm_version} && {command}'
            except Exception:
                pass

        # Execute the command
        logger.info(f"run_in_env: {command} (cwd={validated}, timeout={timeout})")
        result = _run_cmd(
            ["bash", "-c", command],
            cwd=validated,
            timeout=timeout,
            env=env,
        )

        return result


# ============================================================
# SINGLETON
# ============================================================

_manager: Optional[EnvironmentManager] = None
_manager_lock = threading.Lock()


def get_env_manager() -> EnvironmentManager:
    """Return the singleton EnvironmentManager instance.

    Thread-safe: uses a module-level lock to ensure only one
    instance is created even across threads.
    """
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = EnvironmentManager()
    return _manager
