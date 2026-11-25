"""Verify the built web app and Bridge against a local Ollama fixture."""

import http.server
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from contextlib import ExitStack, contextmanager
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3:4b"
ANSWER = "Respuesta de prueba"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OllamaFixture(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, payload, streaming=False):
        body = (json.dumps(payload) + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson" if streaming else "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self.respond({"models": [{"name": MODEL, "model": MODEL, "size": 1}]})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.respond({
            "model": body["model"],
            "message": {"role": "assistant", "content": ANSWER},
            "done": True,
            "done_reason": "stop",
        }, streaming=body.get("stream", False))


def request(url, payload=None, timeout=15):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with OPENER.open(req, timeout=timeout) as response:
        return response.read().decode("utf-8")


def wait_ready(url, process):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited with code {process.returncode} while waiting for {url}")
        try:
            return request(url, timeout=5)
        except OSError as error:
            last_error = error
            time.sleep(0.25)
    raise TimeoutError(f"Server unavailable at {url}") from last_error


@contextmanager
def server_process(command, cwd, env, shutdown_on_eof=False):
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE if shutdown_on_eof else None)
    try:
        yield process
    finally:
        if process.stdin is not None:
            process.stdin.close()
        if process.poll() is None:
            if not shutdown_on_eof:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def start_bridge(profile):
    agent_dir = ROOT / "agente_v14"
    sys.path.insert(0, str(agent_dir))
    expanduser = os.path.expanduser

    def isolated_expanduser(path):
        original = os.fspath(path)
        if original == "~" or original.startswith(("~/", "~\\")):
            return str(profile) + original[1:]
        return expanduser(path)

    with patch.object(os.path, "expanduser", isolated_expanduser):
        import uvicorn
        from bridge_api import app

        server = uvicorn.Server(uvicorn.Config(
            app, host=os.environ["BRIDGE_HOST"], port=int(os.environ["BRIDGE_PORT"]),
        ))

        def stop_on_eof():
            sys.stdin.read()
            server.should_exit = True

        threading.Thread(target=stop_on_eof, daemon=True).start()
        server.run()


def verify():
    standalone = ROOT / ".next" / "standalone"
    if not (standalone / "server.js").is_file():
        raise SystemExit("Run npm run build before verifying the local stack.")
    shutil.copytree(ROOT / ".next" / "static", standalone / ".next" / "static", dirs_exist_ok=True)
    shutil.copytree(ROOT / "public", standalone / "public", dirs_exist_ok=True)

    with ExitStack() as stack:
        try:
            model = stack.enter_context(http.server.ThreadingHTTPServer(("127.0.0.1", 11434), OllamaFixture))
        except OSError as error:
            raise SystemExit(f"The Ollama fixture requires port 11434: {error}") from error
        threading.Thread(target=model.serve_forever, daemon=True).start()
        stack.callback(model.shutdown)
        profile = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="agentlocal-qa-")))
        workspace = profile / "workspace"
        workspace.mkdir()
        fixture = workspace / "fixture.txt"
        fixture.write_text("AgentLocal QA file", encoding="utf-8")

        with socket.socket() as bridge_socket, socket.socket() as web_socket:
            bridge_socket.bind(("127.0.0.1", 0))
            web_socket.bind(("127.0.0.1", 0))
            bridge_port = str(bridge_socket.getsockname()[1])
            web_port = str(web_socket.getsockname()[1])
        env = {
            **os.environ,
            "AGENT_REPOS_DIR": str(workspace),
            "AGENT_LEARN_DIR": str(profile / "learning"),
            "BRIDGE_HOST": "127.0.0.1",
            "BRIDGE_PORT": bridge_port,
            "BRIDGE_TOKEN": secrets.token_urlsafe(24),
            "OLLAMA_HOST": "http://127.0.0.1:11434",
            "HOSTNAME": "127.0.0.1",
            "PORT": web_port,
            "DATABASE_URL": "file:" + (profile / "qa.db").as_posix(),
        }
        subprocess.run(
            ["node", "node_modules/prisma/build/index.js", "db", "push", "--skip-generate"],
            cwd=ROOT, env=env, check=True, timeout=60,
        )
        bridge = stack.enter_context(server_process(
            [sys.executable, "-u", __file__, "--bridge", str(profile)], ROOT / "agente_v14", env,
            shutdown_on_eof=True,
        ))
        web = stack.enter_context(server_process(["node", "server.js"], standalone, env))
        health = json.loads(wait_ready(f"http://127.0.0.1:{bridge_port}/api/health", bridge))
        assert health["agent"] and health["ollama"] == "ok", health
        print("PASS: Bridge health and Ollama discovery", flush=True)

        base = f"http://127.0.0.1:{web_port}"
        assert "AgentLocal" in wait_ready(base, web)
        print("PASS: Next.js home page", flush=True)

        result = json.loads(request(base + "/api/execute", {
            "tool_name": "leer_archivo", "arguments": {"ruta": str(fixture)},
        }))
        assert result["success"] and "AgentLocal QA file" in result["result"], result
        print("PASS: Next.js to Bridge tool execution", flush=True)

        conversation = json.loads(request(base + "/api/conversations", {"title": "AgentLocal QA"}))
        saved = json.loads(request(base + "/api/conversations/" + conversation["id"]))
        assert saved["title"] == "AgentLocal QA", saved
        print("PASS: SQLite conversation create and read", flush=True)

        for use_agent in (False, True):
            response = request(base + "/api/chat", {
                "model": MODEL,
                "messages": [{"role": "user", "content": "Hola"}],
                "useAgent": use_agent,
            }, timeout=35)
            assert ANSWER in response and "data: [DONE]" in response, response
            print(f"PASS: Chat streaming in {'agent' if use_agent else 'simple'} mode", flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--bridge":
        start_bridge(Path(sys.argv[2]))
    else:
        verify()
