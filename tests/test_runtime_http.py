from __future__ import annotations

import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from agnes_provisioner.config import Settings, save_settings
from agnes_provisioner.web import WebAppController, make_handler


@pytest.fixture
def app(tmp_path):
    config = tmp_path / "settings.toml"
    save_settings(Settings(database=tmp_path / "http.db", vault=tmp_path / "http.dpapi"), config)
    controller = WebAppController(config)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(controller))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False,
                      timeout=20) as client:
        yield client, controller
    if controller._runtime and controller.runtime.worker:
        controller.runtime.worker.join(20)
    server.shutdown()
    server.server_close()
    worker.join(5)


def test_runtime_http_import_run_exact_count_log_export_and_restart(app):
    client, controller = app
    pkg = json.loads((Path(__file__).resolve().parents[1] /
                      "examples/script-demo-accounts.json").read_text(encoding="utf-8"))
    assert client.post("/api/runtime/scripts/import", json=pkg).status_code == 200
    request = {"script_id": "demo-accounts", "version": "1.0.0", "count": 20,
               "concurrency": 2, "bindings": {}, "request_id": uuid4().hex}
    response = client.post("/api/runtime/start", json=request)
    assert response.status_code == 200, response.text
    batch = response.json()["batch"]["id"]
    duplicate = client.post("/api/runtime/start", json=request)
    assert duplicate.json()["batch"]["id"] == batch
    assert client.post("/api/runtime/start", json={**request, "request_id": uuid4().hex}
                       ).status_code == 400
    controller.runtime.worker.join(20)
    tasks = client.get("/api/runtime/tasks", params={"batch": batch}).json()
    assert tasks["summary"]["total"] == 20
    assert tasks["summary"]["succeeded"] == 17
    assert tasks["summary"]["failed"] == 3
    assert tasks["tasks"][0]["results"]["password"] == "••••••"
    revealed = client.get("/api/runtime/tasks", params={"batch": batch, "reveal": "1"}).json()
    assert revealed["tasks"][0]["results"]["password"] == "demo-password-1"
    assert "demo-password-1" not in client.get("/api/runtime/export",
                                               params={"batch": batch}).text
    assert "demo-password-1" in client.get("/api/runtime/export", params={
        "batch": batch, "include_secrets": "1"}).text
    events = client.get("/api/runtime/events", params={"batch": batch,
                                                     "task": tasks["tasks"][0]["id"]}).json()
    assert events["events"] and all(e["task_id"] == tasks["tasks"][0]["id"]
                                    for e in events["events"])
    controller._runtime = None
    assert client.get("/api/runtime/tasks", params={"batch": batch}).json() == tasks


def test_runtime_api_rejects_cross_site_invalid_values_and_invalid_packages(app):
    client, _ = app
    assert client.post("/api/runtime/start", json={}, headers={
        "Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/runtime/scripts/import", json={"source": "secret"}
                       ).status_code == 400
    assert client.post("/api/runtime/start", json={"request_id": uuid4().hex, "count": True}
                       ).status_code == 400
    assert client.get("/api/runtime/tasks", params={"batch": "missing"}).status_code == 400
    assert client.get("/api/runtime/unknown").status_code == 404


def test_runtime_settings_persist_and_unknown_is_not_healthy(app):
    client, controller = app
    response = client.post("/api/runtime/resources/save", json={
        "kind": "mailbox", "name": "测试邮箱", "config": {
            "source": "outlook", "transport": "graph",
            "accounts": "fiction@example.com----fiction-password----client-test----refresh-test",
        },
    })
    assert response.status_code == 200, response.text
    resource = response.json()["resource"]
    assert resource["status"] not in {"HEALTHY", "READY", "healthy", "ready"}
    overview = client.get("/api/runtime/overview").text
    assert "fiction-password" not in overview and "refresh-test" not in overview
    controller._runtime = None
    resources = client.get("/api/runtime/overview").json()["resources"]
    assert any(r["id"] == resource["id"] for r in resources)


def test_mutual_exclusion_is_cross_process(tmp_path):
    """Use an actual child process, not only two controller objects."""
    import os
    import subprocess
    import sys

    from agnes_provisioner.lock import RunLock

    db = tmp_path / "lock.db"
    ready = tmp_path / "ready"
    code = (
        "from pathlib import Path; import time; from agnes_provisioner.lock import RunLock; "
        f"lock=RunLock(Path({str(db)!r})); lock.__enter__(); "
        f"Path({str(ready)!r}).write_text('ready'); time.sleep(30)"
    )
    process = subprocess.Popen([sys.executable, "-c", code], env=os.environ.copy())
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists()
        with pytest.raises(Exception, match="调度器"):
            with RunLock(db):
                pass
    finally:
        if os.name == "nt":
            # uv's Windows venv python is a launcher; terminate its actual child too.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           check=True, capture_output=True)
        else:
            process.terminate()
        process.wait(10)
    with RunLock(db):
        pass
