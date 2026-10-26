"""Real HTTP smoke check for the FastAPI app, kept separate from unit tests."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def request_json(url: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(url, data=body, headers={"Content-Type": "application/json"} if body else {})
    try:
        with urlopen(request, timeout=2) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def main() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError("Uvicorn exited before becoming ready")
            try:
                status, health = request_json(f"{base}/api/health")
                if status == 200 and health.get("status") == "ok":
                    break
            except (OSError, URLError):
                time.sleep(0.2)
        else:
            raise RuntimeError("MissionCut API did not become ready within 15 seconds")

        _, demo = request_json(f"{base}/api/demo")
        payload = {"graph": demo["graph"], "scenario": demo["scenarios"][0], "sources": ["suspect"]}
        status, result = request_json(f"{base}/api/scenarios/evaluate", payload)
        assert status == 200
        assert result["blocked_connection_count"] == 2
        assert result["paths_before"][0]["count"] == 2
        assert result["paths_after"][0]["count"] == 0
        assert "paths" in result["paths_before"][0]
        assert len(result["paths_before"][0]["paths"]) == 2

        invalid_graph = {"nodes": [], "edges": [{"id": "x", "source": "a", "target": "b"}]}
        status, error = request_json(f"{base}/api/graphs/validate", invalid_graph)
        assert status == 422 and error["error"]["code"] == "validation_error"
        print("HTTP smoke passed: health, demo, evaluation, and invalid-input response")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
